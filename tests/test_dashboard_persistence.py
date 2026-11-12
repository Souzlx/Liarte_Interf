"""Offline restart, consistent backups and bounded caches with synthetic data."""

from contextlib import closing, contextmanager
from dataclasses import replace
from pathlib import Path
import sqlite3
import tempfile
from threading import Event, get_ident
import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent, QSettings

from liarte_core.comex_historical import HistoricalComexProvider
from liarte_core.comex_history import HistoryStore
from liarte_core.comex_history_backup import create_backup, restore_to_new_file, verify_backup
from liarte_core.domain import Period, Selection, ImportRecord
from liarte_core.query import Cancelled, DatasetQuery
from liarte_core.query_session import (
    SessionWriter,
    import_selection,
    import_session,
    load_session,
    save_session,
)
from liarte_desktop.controller import DesktopController
from liarte_desktop.inventory import InventoryController
from liarte_core.inventory_io import write_snapshot
from tests import test_comex_history as fixture
from tests import test_comex_historical as provider_fixture
from tests.test_inventory import sample
from tests.test_qt import APP, pump, settled


class QuerySessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "session.json"

    def tearDown(self):
        self.temp.cleanup()

    def test_previous_complete_session_recovers_corrupted_primary(self):
        save_session(self.path, {"value": 1})
        save_session(self.path, {"value": 2})
        self.path.write_bytes(b"broken")
        self.assertEqual(load_session(self.path), {"value": 1})

    def test_failed_final_replace_preserves_previous_primary(self):
        save_session(self.path, {"value": 1})
        from liarte_core import query_session

        original = query_session.os.replace

        def fail(source, target):
            if Path(target) == self.path:
                raise OSError("synthetic publication failure")
            original(source, target)

        with patch.object(query_session.os, "replace", side_effect=fail):
            with self.assertRaises(OSError):
                save_session(self.path, {"value": 2})
        self.assertEqual(load_session(self.path), {"value": 1})
        self.assertEqual(list(self.path.parent.glob(".session*")), [])

    def test_bounded_writer_flushes_latest_accepted_value_on_close(self):
        writer = SessionWriter(self.path)
        for i in range(100):
            writer.submit({"value": i})
        writer.close()
        self.assertEqual(load_session(self.path), {"value": 99})
        self.assertFalse(writer.error)

    def test_selection_roundtrip_catalog_and_invalid_input(self):
        selection = Selection(
            Period("2017-02", "2018-01"), country_values=("País sintético",), page=3, search="ação"
        )
        saved = import_session(selection, "catalog-A", "revision-1")
        self.assertEqual(import_selection(saved, "catalog-A"), selection)
        with self.assertRaises(ValueError):
            import_selection(saved, "catalog-B")
        with self.assertRaises(ValueError):
            save_session(self.path, {"value": "x" * 100_000})
        self.assertIsNone(load_session(self.path))


class HistoryBackupTests(fixture._Fixture, unittest.TestCase):
    def test_backup_includes_committed_wal_and_recovers_both_exact_bases(self):
        self.accept(rows=[fixture.general(fob=10**24 + 1)])
        with closing(sqlite3.connect(self.path)) as pinned:
            pinned.execute("BEGIN")
            pinned.execute("SELECT * FROM active").fetchall()
            self.store.record_state("ready")
            backup = create_backup(self.store)
        metadata = verify_backup(backup)
        self.assertEqual(metadata["revision"], self.store.status()["local_revision"])
        restored = restore_to_new_file(backup, self.path.parent / "recovered.sqlite3")
        copied = HistoryStore(restored, fixture.CODES)
        period = Period("2024-01", "2024-02")
        self.assertEqual(copied.read(period, Event()), self.store.read(period, Event()))
        self.assertEqual(create_backup(self.store), backup)

    def test_corrupt_copy_and_existing_destination_never_replace_live_data(self):
        self.accept()
        backup = create_backup(self.store)
        original = self.store.read(Period("2024-01", "2024-02"), Event())
        with self.assertRaises(ValueError):
            restore_to_new_file(backup, self.path)
        with (backup / "historico.sqlite3").open("ab") as stream:
            stream.write(b"corrupt")
        with self.assertRaises(ValueError):
            verify_backup(backup)
        self.assertEqual(original, self.store.read(Period("2024-01", "2024-02"), Event()))

    def test_cancel_preserves_valid_copy_and_retention_keeps_newest(self):
        self.accept()
        first = create_backup(self.store, keep=2)
        for value in (203, 307):
            self.accept(rows=[fixture.general(fob=value)])
            last = create_backup(self.store, keep=2)
        self.assertFalse(first.exists())
        self.assertTrue(last.exists())
        self.accept(rows=[fixture.general(fob=409)])
        cancel = Event()
        cancel.set()
        with self.assertRaises(Cancelled):
            create_backup(self.store, cancel, keep=2)
        self.assertTrue(last.exists())
        self.assertEqual(len(list(last.parent.glob(".backup-*"))), 0)

    def test_empty_history_does_not_create_a_successful_backup(self):
        self.assertIsNone(create_backup(self.store))


class DashboardCacheTests(fixture._Fixture, unittest.TestCase):
    def test_existing_schema_upgrades_index_without_changing_catalog_or_data(self):
        self.accept()
        period = Period("2024-01", "2024-02")
        expected = self.store.read(period, Event())
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("DROP INDEX manifest_by_period")
        reopened = HistoryStore(self.path, fixture.CODES)
        self.assertEqual(reopened.catalog_key, self.store.catalog_key)
        self.assertEqual(reopened.read(period, Event()), expected)
        reopened.record_state("ready")
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 1)
            self.assertIsNotNone(
                db.execute("SELECT 1 FROM sqlite_master WHERE name='manifest_by_period'").fetchone()
            )
        self.assertEqual(reopened.read(period, Event()), expected)

    def test_history_read_query_count_is_bounded_independent_of_month_count(self):
        self.accept(start="2024-01", end="2024-12")
        original = self.store._connection
        statements = []

        @contextmanager
        def traced():
            with original() as db:
                db.set_trace_callback(statements.append)
                yield db

        with patch.object(self.store, "_connection", side_effect=traced):
            data = self.store.read(Period("2024-01", "2024-12"), Event())
        self.assertEqual(len(data.general), 1)
        self.assertLessEqual(sum(s.lstrip().upper().startswith("SELECT") for s in statements), 4)

    def test_search_indexes_are_reused_across_filters_and_invalidated_with_source(self):
        rows = tuple(
            ImportRecord(
                i, "2024-01", "29161220", "Produto ação", "SP", country, "Porto", 100, 10, 1, 2
            )
            for i, country in enumerate(("A", "B", "A", "B"))
        )
        query = DatasetQuery(rows)
        a = Selection(Period("2024-01", "2024-01"), country="A", search="acao")
        b = replace(a, country="B")
        for selection in (a, b, replace(a, search="produto")):
            self.assertEqual(query.query(selection, Event(), lambda *_: None).table_count, 2)
        self.assertEqual(query.cache_info["search_builds"], 2)
        query._rows = rows[:1]
        self.assertEqual(query.query(a, Event(), lambda *_: None).table_count, 1)
        self.assertEqual(query.cache_info["search_builds"], 3)

    def test_period_cache_reuses_validated_conversion_but_rejects_new_revision(self):
        self.accept()
        provider = HistoricalComexProvider(
            self.path.parent, codes=fixture.CODES, history=self.store
        )
        try:
            january, february = Period("2024-01", "2024-01"), Period("2024-02", "2024-02")
            first = provider.load(january, Event(), lambda *_: None)
            provider.load(february, Event(), lambda *_: None)
            with patch.object(
                provider, "_convert", side_effect=AssertionError("conversion repeated")
            ):
                self.assertIs(provider.load(january, Event(), lambda *_: None), first)
            self.accept(rows=[fixture.general(fob=321)])
            new = provider.load(january, Event(), lambda *_: None)
            self.assertNotEqual(first.local_revision, new.local_revision)
            self.assertEqual(new.general_records[0].fob_cents, 32100)
        finally:
            provider.close()


class DashboardResumeTests(unittest.TestCase):
    setUp = provider_fixture.HistoricalComexProviderTests.setUp
    accept = provider_fixture.HistoricalComexProviderTests.accept
    tearDown = provider_fixture.HistoricalComexProviderTests.tearDown

    def controller(self):
        settings = QSettings(str(self.directory / "preferences.ini"), QSettings.Format.IniFormat)
        return DesktopController(self.provider, settings)

    def dispose(self, controller):
        controller.shutdown()
        controller.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        APP.processEvents()

    def test_last_accepted_query_restores_offline_with_search_sort_page_and_exact_totals(self):
        self.accept()
        controller = self.controller()
        with patch.object(controller.history, "request_check"):
            controller.queryPeriod(self.period.start, self.period.end)
            settled(controller)
        controller.setFilter("search", "sintetico")
        settled(controller)
        expected = controller._result
        self.dispose(controller)
        self.provider.close()
        self.provider = HistoricalComexProvider(self.directory, codes=(provider_fixture.CODE,))
        controller = self.controller()
        try:
            with patch.object(
                controller.history,
                "request_check",
                side_effect=AssertionError("unexpected acquisition"),
            ):
                controller.restoreLastQuery()
                settled(controller)
            self.assertTrue(controller.state["loaded"], controller.state["error"])
            self.assertTrue(controller.state["restoredQuery"])
            self.assertEqual(controller._result, expected)
            self.assertEqual(controller._provider.snapshot.api_requests, 0)
            self.assertIn("base local", controller.state["sessionNotice"])
        finally:
            self.dispose(controller)

    def test_empty_profile_does_not_invent_a_query(self):
        controller = self.controller()
        try:
            controller.restoreLastQuery()
            APP.processEvents()
            self.assertFalse(controller.state["loaded"])
        finally:
            self.dispose(controller)

    def test_session_write_error_is_visible_and_clears_after_recovery(self):
        controller = self.controller()
        try:
            controller._session_writer.error = (
                "Não foi possível salvar a última consulta neste perfil."
            )
            controller._sync_access_status()
            self.assertIn("não foi possível", controller.state["sessionNotice"].lower())
            controller._session_writer.error = ""
            controller._sync_access_status()
            self.assertEqual(controller.state["sessionNotice"], "")
        finally:
            self.dispose(controller)

    def test_dashboard_formatting_runs_on_worker_and_cached_pages_do_not_repeat_it(self):
        from liarte_desktop import controller as module

        self.accept()
        controller = self.controller()
        threads = []
        original = module.prepare_result

        def observe(result):
            threads.append(get_ident())
            return original(result)

        try:
            with (
                patch.object(module, "prepare_result", side_effect=observe),
                patch.object(controller.history, "request_check"),
            ):
                controller.queryPeriod(self.period.start, self.period.end)
                settled(controller)
                controller.setPageSize(25)
                settled(controller)
            self.assertEqual(len(threads), 1)
            self.assertNotEqual(threads[0], get_ident())
        finally:
            self.dispose(controller)

    def test_changed_source_recalculates_saved_query_and_failure_preserves_checkpoint(self):
        self.accept()
        controller = self.controller()
        with patch.object(controller.history, "request_check"):
            controller.queryPeriod(self.period.start, self.period.end)
            settled(controller)
        self.dispose(controller)
        self.accept(general=[provider_fixture.synthetic_general(amount=203)])
        controller = self.controller()
        try:
            controller.restoreLastQuery()
            settled(controller)
            self.assertEqual(controller._result.totals.value_cents, 20800)
            self.assertIn("revisão local atual", controller.state["sessionNotice"])
            with patch.object(controller.history, "request_check"):
                controller.queryPeriod("1997-01", "1997-01")
                settled(controller)
        finally:
            self.dispose(controller)
        saved = load_session(self.directory / "ultima-consulta.json")
        self.assertEqual(import_selection(saved, self.store.catalog_key).period, self.period)

    def test_application_startup_restores_without_entering_imports_or_calling_network(self):
        from liarte_desktop.app import create_bundle
        from liarte_desktop.runtime_profile import RuntimeProfile

        self.accept()
        controller = self.controller()
        with patch.object(controller.history, "request_check"):
            controller.queryPeriod(self.period.start, self.period.end)
            settled(controller)
        self.dispose(controller)
        self.provider.close()
        self.provider = HistoricalComexProvider(self.directory, codes=(provider_fixture.CODE,))
        settings = QSettings(str(self.directory / "preferences.ini"), QSettings.Format.IniFormat)
        bundle = create_bundle(
            settings=settings,
            provider=self.provider,
            profile=RuntimeProfile(self.directory, development=True),
        )
        try:
            self.assertTrue(pump(lambda: bundle.controller.state["loaded"], 10))
            self.assertEqual(bundle.platform.activeModule, "home")
            self.assertTrue(bundle.controller.state["restoredQuery"])
            self.assertEqual(bundle.controller._result.totals.value_cents, 10600)
            self.assertEqual(bundle.controller.state["defaultStart"], self.period.start)
            self.assertEqual(bundle.controller.state["defaultEnd"], self.period.end)
            self.assertTrue(pump(lambda: not bundle.engine.rootObjects()[0].property("draftPeriod")))
            self.assertEqual(bundle.messages, [])
        finally:
            bundle.controller.shutdown()
            bundle.inventory.shutdown()
            for window in bundle.engine.rootObjects():
                window.close()
                window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            bundle.engine.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            bundle.services.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            APP.processEvents()


class StockResumeTests(unittest.TestCase):
    def test_accepted_stock_filters_and_month_reopen_from_local_snapshot(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            cache = root / "base.liarte"
            write_snapshot(sample(), cache)
            settings = QSettings(str(root / "settings.ini"), QSettings.Format.IniFormat)

            def idle(c):
                self.assertTrue(
                    pump(lambda: not c.state["busy"] and not c._debounce.isActive(), 15)
                )

            c = InventoryController(settings, cache_path=cache)
            try:
                c.ensureLoaded()
                idle(c)
                c.setFilter("unit", "KG")
                idle(c)
                c.sortPositions(9, True)
                idle(c)
                expected = c._applied_selection, c._monthly_period, c._monthly_unit, c._applied_sort
            finally:
                c.shutdown()
            c = InventoryController(settings, cache_path=cache)
            try:
                c.ensureLoaded()
                idle(c)
                self.assertEqual(
                    (c._applied_selection, c._monthly_period, c._monthly_unit, c._applied_sort),
                    expected,
                )
            finally:
                c.shutdown()
