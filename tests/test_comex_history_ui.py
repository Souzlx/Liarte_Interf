"""Sincronização e consultas Qt com histórico sintético, sem acesso à rede."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile
from threading import Event, get_ident
import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QUrl
from PySide6.QtTest import QSignalSpy

from liarte_core.comex import Availability, ComexError, ComexProvider, Snapshot
from liarte_core.query import Cancelled, checkpoint
from liarte_desktop.app import create_bundle, install_availability_refresh
from liarte_desktop.controller import DesktopController
from tests.test_comex import Transport
from tests.test_qt import APP, pump, settled


@dataclass(frozen=True, slots=True)
class SyntheticHistoricalSnapshot(Snapshot):
    local_revision: str = ""


class SyntheticHistoricalProvider(ComexProvider):
    """Fonte controlada da apresentação; não simula o armazenamento SQLite."""

    is_historical = True

    def __init__(self, directory, *, available=True):
        super().__init__(directory, codes=("29161220",))
        self.transport = Transport()
        self.available = available
        self.pause = 0
        self.global_revision = self.period_revision = "1"
        self.sync_count = self.query_count = 0
        self.sync_started, self.sync_release = Event(), Event()
        self.sync_release.set()
        self.sync_error = ""
        self.sync_thread = None
        self.on_sync = None
        self.publication = Availability("2026-09", "2026-10-07", "2026-10-07T12:00:00+00:00")

    def history_status(self):
        return {
            "catalog_key": "synthetic-catalog", "local_revision": self.global_revision if self.available else "",
            "coverage_start": "2026-08" if self.available else "",
            "coverage_end": "2026-09" if self.available else "",
            "complete_months": 2 if self.available else 0, "complete": self.available,
            "publication": {"latest": "2026-09", "updated": "2026-10-07"} if self.available else {},
            "checked_at": "2026-10-07T12:00:00+00:00" if self.available else "",
            "last_full_sync_at": "2026-10-07T12:00:00+00:00" if self.available else "",
        }

    def access_status(self):
        return {
            "historical_mode": True, "pause_seconds": self.pause,
            "pause_status": 429 if self.pause else 0, "pause_reason": "source" if self.pause else "",
        }

    def has_local_period(self, start, end):
        return self.available and "2026-08" <= start <= end <= "2026-09"

    def local_period_revision(self, start, end):
        return self.period_revision if self.has_local_period(start, end) else ""

    def load(self, period, cancel, progress):
        checkpoint(cancel)
        if not self.has_local_period(period.start, period.end):
            raise ComexError("O histórico local ainda não cobre o período solicitado. Aguarde a carga inicial.")
        if self._snapshot is not None and self._snapshot.period == period and self._snapshot.local_revision == self.period_revision:
            self._revalidate_next = False
            return self._snapshot
        general = tuple(dict(row) for row in self.transport.general)
        municipal = tuple(dict(row) for row in self.transport.municipal)
        records, cities = self._convert(general, municipal, cancel)
        snapshot = SyntheticHistoricalSnapshot(
            period, general, municipal, records, cities, self.publication,
            "2026-10-07T12:00:00+00:00", 0, 0,
            source_channels=("comex-local-history",), response_validated=True,
            local_revision=self.period_revision,
        )
        with self._lock:
            checkpoint(cancel)
            self._snapshot = snapshot
            self._general._rows, self._municipal._rows = records, cities
            for kind, rows in (("general", records), ("municipal", cities)):
                self._options[kind] = {
                    "countries": sorted({r.country for r in rows}),
                    "states": sorted({r.state for r in rows}),
                    "ports": sorted({r.port for r in rows if r.port}),
                    "cities": sorted({r.city for r in rows}) if kind == "municipal" else [],
                    "headings": sorted({(r.heading, r.product) for r in rows}) if kind == "municipal" else [],
                    "products": sorted({(r.ncm, r.product) for r in rows}) if kind == "general" else [],
                }
            self._refresh_next = self._revalidate_next = False
        return snapshot

    def cached_query(self, selection):
        if self.snapshot is None or self.snapshot.local_revision != self.period_revision:
            return None
        return super().cached_query(selection)

    def query(self, *args, **kwargs):
        self.query_count += 1
        return super().query(*args, **kwargs)

    def synchronize(self, cancel, progress, *, force=False, audit=False):
        self.sync_count += 1
        self.sync_thread = get_ident()
        self.sync_started.set()
        progress(5, "Verificação sintética · nenhuma requisição de rede")
        while not self.sync_release.wait(0.005):
            checkpoint(cancel)
        checkpoint(cancel)
        if self.sync_error:
            raise RuntimeError(self.sync_error)
        if self.on_sync:
            self.on_sync()
        progress(100, "Histórico sintético conferido")
        return {"status": "complete", "local_revision": self.global_revision}

    def publish(self, *, change_period=True):
        self.available = True
        self.global_revision = str(int(self.global_revision) + 1)
        if change_period:
            self.period_revision = str(int(self.period_revision) + 1)
            for metric in ("metricFOB", "metricCIF"):
                self.transport.general[0][metric] = str(int(self.transport.general[0][metric]) + 1)


class ComexHistoryUiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.provider = SyntheticHistoricalProvider(Path(self.temp.name))
        self.controller = DesktopController(self.provider)

    def tearDown(self):
        self.provider.sync_release.set()
        self.controller.shutdown()
        self.provider.close()
        self.controller.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        APP.processEvents()
        self.temp.cleanup()

    def load(self):
        self.controller.queryPeriod("2026-09", "2026-09")
        settled(self.controller)
        self.assertTrue(self.controller.state["loaded"], self.controller.state["error"])

    def test_constructor_does_not_start_a_network_task_or_a_query(self):
        APP.processEvents()
        self.assertTrue(self.controller.state["historicalMode"])
        self.assertFalse(self.controller.state["loaded"])
        self.assertEqual(self.provider.sync_count, 0)
        self.assertEqual(self.provider.query_count, 0)

    def test_query_reads_locally_during_an_api_pause_and_leaves_the_pause_intact(self):
        self.provider.pause = 180
        self.load()
        self.assertEqual(self.provider.pause, 180)
        self.assertEqual(self.provider.sync_count, 0)
        self.assertEqual(self.controller.state["sourcePauseSeconds"], 180)
        self.assertFalse(self.controller.state["error"])
        self.assertEqual(self.controller.state["sourceStatus"], "Base local · Comex Stat")

    def test_sync_runs_in_a_different_worker_and_does_not_block_local_queries(self):
        self.provider.sync_release.clear()
        self.controller.history.startAutomatic()
        self.assertTrue(pump(self.provider.sync_started.is_set))
        self.load()
        self.assertTrue(self.controller.history.state["busy"])
        self.assertFalse(self.controller.state["busy"])
        self.assertNotEqual(self.provider.sync_thread, get_ident())
        self.assertEqual(self.provider.sync_count, 1)

    def test_repeated_checks_are_coalesced_and_success_applies_a_cooldown(self):
        self.provider.sync_release.clear()
        owner = self.controller.history
        owner.startAutomatic()
        self.assertTrue(pump(self.provider.sync_started.is_set))
        for _ in range(20):
            owner.request_check(force=True)
        self.assertEqual(self.provider.sync_count, 1)
        self.provider.sync_release.set()
        self.assertTrue(pump(lambda: not owner.running))
        for _ in range(20):
            owner.request_check()
        self.assertEqual(self.provider.sync_count, 1)
        owner.check()
        self.assertTrue(pump(lambda: self.provider.sync_count == 2 and not owner.running))

    def test_sync_failure_is_separate_from_the_current_analysis_and_query_error(self):
        self.provider.sync_error = "Fonte sintética indisponível"
        self.load()
        self.assertTrue(pump(lambda: not self.controller.history.running))
        self.assertIn("indisponível", self.controller.history.state["error"])
        self.assertFalse(self.controller.state["error"])
        self.assertTrue(self.controller.state["loaded"])

    def test_publication_refreshes_only_a_changed_period_and_preserves_filters(self):
        self.load()
        self.assertTrue(pump(lambda: not self.controller.history.running))
        self.controller.setFilter("country", "China")
        settled(self.controller)
        before = self.provider.query_count
        self.provider.publish(change_period=False)
        self.controller.history.refresh()
        APP.processEvents()
        self.assertEqual(self.provider.query_count, before)
        self.provider.publish()
        self.controller.history.refresh()
        self.assertTrue(pump(lambda: self.provider.query_count > before))
        settled(self.controller)
        self.assertEqual(self.controller.state["countryFilter"], "China")
        self.assertEqual(self.provider.snapshot.local_revision, self.provider.period_revision)

    def test_first_load_publishes_no_query_until_requested_period_is_covered(self):
        self.provider.available = False
        self.provider.sync_release.clear()
        self.controller.history.refresh()
        self.controller.queryPeriod("2026-09", "2026-09")
        settled(self.controller)
        self.assertFalse(self.controller.state["loaded"])
        self.assertIn("não cobre", self.controller.state["error"])
        self.provider.publish()
        self.controller.history.refresh()
        settled(self.controller)
        self.assertTrue(self.controller.state["loaded"], self.controller.state["error"])

    def test_cancelled_sync_stays_stopped_until_explicit_update_and_local_queries_continue(self):
        self.provider.sync_release.clear()
        owner = self.controller.history
        owner.startAutomatic()
        self.assertTrue(pump(self.provider.sync_started.is_set))
        owner.cancel()
        self.assertTrue(pump(lambda: not owner.running))
        self.assertTrue(owner.state["stopped"])
        self.load()
        self.assertEqual(self.provider.sync_count, 1)
        self.provider.sync_release.set()
        owner.check()
        self.assertTrue(pump(lambda: self.provider.sync_count == 2 and not owner.running))

    def test_close_waits_for_the_sync_thread_without_destroying_it(self):
        self.provider.sync_release.clear()
        self.controller.history.startAutomatic()
        self.assertTrue(pump(self.provider.sync_started.is_set))
        ready = QSignalSpy(self.controller.readyToClose)
        self.controller.requestClose()
        self.assertEqual(ready.count(), 0)
        self.assertTrue(pump(lambda: ready.count() == 1))
        self.assertFalse(self.controller.history.running)

    def test_idle_close_is_idempotent_when_multiple_workers_notify_completion(self):
        ready = QSignalSpy(self.controller.readyToClose)
        self.controller.requestClose()
        self.controller._try_close()
        self.controller.history.request_close()
        self.assertEqual(ready.count(), 1)

    def test_pause_expiration_schedules_only_one_background_check(self):
        self.provider.pause = 180
        owner = self.controller.history
        owner.startAutomatic()
        for _ in range(5):
            owner._tick()
        self.assertEqual(self.provider.sync_count, 0)
        self.provider.pause = 0
        owner._tick()
        self.assertTrue(pump(lambda: self.provider.sync_count == 1 and not owner.running))
        for _ in range(5):
            owner._tick()
        self.assertEqual(self.provider.sync_count, 1)

    def test_accepted_publication_clamps_only_untouched_default_periods(self):
        self.assertEqual(self.controller.state["defaultEnd"], "2026-09")
        self.controller.setDraftPeriod("start", "2026-08")
        self.provider.publication = Availability("2026-08", "2026-09-07", "2026-09-07T12:00:00+00:00")
        original_status = self.provider.history_status

        def older_publication():
            value = original_status()
            value["publication"] = {"latest": "2026-08", "municipal_latest": "2026-08", "updated": "2026-09-07"}
            return value

        with patch.object(self.provider, "history_status", side_effect=older_publication):
            self.controller._sync_history_limits()
        self.assertEqual(self.controller.state["defaultStart"], "2026-08")
        self.assertEqual(self.controller.state["defaultEnd"], "2026-09")
        self.assertEqual(self.controller.periods[-1]["value"], "2026-09")
        self.assertIn("fora da base local", self.controller.periods[-1]["label"])
        before = self.provider.query_count
        self.controller.queryPeriod("2026-08", "2026-09")
        self.assertEqual(self.provider.query_count, before)
        self.assertIn("intervalo disponível", self.controller.state["error"])

    def test_cancelled_refresh_keeps_the_displayed_snapshot_for_export_and_options(self):
        self.provider.pause = 180
        self.load()
        accepted = self.controller._accepted_snapshot
        previous_options = self.controller.countries
        original_fob = accepted.general[0]["metricFOB"]
        self.provider.publish()

        def cancel_after_loading(selection, cancel, progress):
            self.provider.load(selection.period, cancel, progress)
            raise Cancelled()

        captured = []
        from liarte_core.exports import export_document

        def real_export(request, *args):
            captured.append(request.snapshot)
            return export_document(request, *args)

        with patch.object(self.controller.history, "refresh", return_value=None):
            with patch.object(self.provider, "query", side_effect=cancel_after_loading):
                self.controller.queryPeriod("2026-09", "2026-09")
                settled(self.controller)
            self.assertIs(self.controller._accepted_snapshot, accepted)
            self.assertIsNot(self.provider.snapshot, accepted)
            self.assertEqual(accepted.general[0]["metricFOB"], original_fob)
            self.assertEqual(self.controller.countries, previous_options)
            destination = Path(self.temp.name) / "accepted.xlsx"
            with patch("liarte_desktop.jobs.export_document", side_effect=real_export):
                self.controller.exportTo("excel", QUrl.fromLocalFile(str(destination)))
                self.assertTrue(pump(lambda: not self.controller.state["exportBusy"], 10))
            self.assertEqual(captured, [accepted])
            self.assertTrue(destination.is_file(), self.controller.state["exportError"])

    def test_expanded_catalog_uses_accepted_descriptions_and_allows_filtering_new_codes(self):
        self.provider.pause = 180
        code = "99887766"
        self.provider.codes = ("29161220", code)
        products = {item["value"]: item["label"] for item in self.controller.products}
        self.assertEqual(products[code], code)
        extra = dict(self.provider.transport.general[0], coNcm=code, ncm="Produto sintético adicional")
        self.provider.transport.general.append(extra)
        self.load()
        products = {item["value"]: item["label"] for item in self.controller.products}
        self.assertIn("Produto sintético adicional", products[code])
        self.controller.setFilter("ncm", code)
        settled(self.controller)
        self.assertFalse(self.controller.state["error"])
        self.assertEqual(self.controller.state["ncmFilter"], code)
        self.assertEqual(self.controller._result.totals.ncms, 1)


class ComexHistoryCompositionTests(unittest.TestCase):
    def test_module_entry_starts_automatic_update_but_home_and_inventory_do_not(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = SyntheticHistoricalProvider(Path(directory))
            bundle = create_bundle(provider=provider)
            try:
                install_availability_refresh(bundle)
                APP.processEvents()
                self.assertEqual(provider.sync_count, 0)
                bundle.platform.openModule("inventory")
                APP.processEvents()
                self.assertEqual(provider.sync_count, 0)
                bundle.platform.openModule("imports")
                self.assertTrue(pump(lambda: provider.sync_count == 1 and not bundle.controller.history.running))
                bundle.platform.openModule("home")
                bundle.platform.openModule("imports")
                APP.processEvents()
                self.assertEqual(provider.sync_count, 1)
                self.assertEqual(bundle.messages, [])
                self.assertIsNotNone(bundle.engine.rootObjects()[0].findChild(QObject, "comexHistoryStatus"))
            finally:
                bundle.controller.shutdown()
                bundle.inventory.shutdown()
                bundle.engine.rootObjects()[0].close()
                bundle.engine.deleteLater()
                QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                APP.processEvents()
                provider.close()
