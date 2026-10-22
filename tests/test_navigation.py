"""Navegação local: exatidão, modelo incremental e continuidade visual Qt."""

from __future__ import annotations

from dataclasses import replace
from threading import Event
import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QPointF, Qt
from PySide6.QtTest import QAbstractItemModelTester, QSignalSpy

from liarte_core.domain import Period, Selection
from liarte_core.query import DatasetQuery
from liarte_desktop.app import create_bundle
from liarte_desktop.table_model import ImportTableModel, cells
from tests.test_core import record
from tests.test_comex import ComexFixtureCase, RealQtTests
from tests.test_qt import APP, pump, settled


class NavigationCoreTests(unittest.TestCase):
    def setUp(self):
        self.rows = tuple(record(i, fob_cents=10_000 + i) for i in range(237))
        self.provider = DatasetQuery(self.rows)
        self.selection = Selection(Period("2026-01", "2026-09"), sort_column=6)

    def query(self, selection=None):
        return self.provider.query(
            selection or self.selection, Event(), lambda *_: None
        )

    def test_cached_pages_match_worker_results_without_filtering_or_sorting(self):
        original = self.query()
        for size in (25, 50, 100, 200):
            for page in (1, 2, 999):
                selection = replace(self.selection, page_size=size, page=page)
                expected = self.query(selection)
                with (
                    patch.object(self.provider, "_dataset", side_effect=AssertionError),
                    patch.object(self.provider, "_scope", side_effect=AssertionError),
                    patch.object(self.provider, "_ordered", side_effect=AssertionError),
                ):
                    result = self.provider.cached_query(selection)
                self.assertEqual(result, expected)
                self.assertIs(result.totals, original.totals)
                self.assertIs(result.procurement, original.procurement)

    def test_unprepared_scope_or_order_never_returns_an_old_view(self):
        self.assertIsNone(self.provider.cached_query(self.selection))
        self.query()
        for changes in (
            {"country": "Holanda"},
            {"search": "China"},
            {"period": Period("2026-02", "2026-03")},
            {"sort_column": 9},
            {"descending": True},
            {"kind": "municipal"},
        ):
            with self.subTest(changes=changes):
                self.assertIsNone(
                    self.provider.cached_query(replace(self.selection, **changes))
                )

    def test_replacing_the_source_invalidates_even_the_same_selection(self):
        self.query()
        self.provider._rows = (record(999),)
        self.assertIsNone(self.provider.cached_query(self.selection))
        self.query()
        self.assertEqual(
            self.provider.cached_query(self.selection).rows, (record(999),)
        )

    def test_empty_completed_views_are_reused_without_requerying(self):
        selection = replace(self.selection, search="produto que não existe")
        result = self.query(selection)
        self.assertEqual(result.table_count, 0)
        self.assertEqual(self.provider.cached_query(selection), result)

    def test_evicted_views_are_not_rebuilt_on_the_visual_thread(self):
        self.query()
        for i in range(self.provider.VIEW_LIMIT + 1):
            self.query(replace(self.selection, search=str(i)))
        self.assertIsNone(self.provider.cached_query(self.selection))
        self.assertLessEqual(
            self.provider.cache_info["views"], self.provider.VIEW_LIMIT
        )


class NavigationModelTests(unittest.TestCase):
    def setUp(self):
        self.model = ImportTableModel()
        self.tester = QAbstractItemModelTester(
            self.model, QAbstractItemModelTester.FailureReportingMode.Fatal
        )
        self.resets = QSignalSpy(self.model.modelReset)
        self.columns = QSignalSpy(self.model.columnsChanged)
        self.content = QSignalSpy(self.model.contentChanged)

    def test_pagination_updates_cells_without_resetting_columns_or_model(self):
        self.model.replace(tuple(record(i) for i in range(50)))
        changes = QSignalSpy(self.model.dataChanged)
        new = tuple(record(i + 50, fob_cents=200_000 + i) for i in range(50))
        self.model.replace(new)
        self.assertEqual(self.resets.count(), 0)
        self.assertEqual(self.columns.count(), 0)
        self.assertEqual(changes.count(), 1)
        self.assertEqual(self.model.rows, new)
        for i, row in enumerate(new):
            for column, expected in enumerate(cells(row)):
                self.assertEqual(
                    self.model.data(
                        self.model.index(i, column), Qt.ItemDataRole.ToolTipRole
                    ),
                    expected,
                )

    def test_row_insertions_removals_and_empty_pages_keep_model_contract(self):
        for count in (50, 25, 200, 1, 0, 100, 0):
            self.model.replace(tuple(record(i + count) for i in range(count)))
            self.assertEqual(self.model.rowCount(), count)
            self.assertEqual(len(self.model._display), count)
        self.assertEqual(self.resets.count(), 0)
        self.assertEqual(self.columns.count(), 0)

    def test_identical_rows_do_not_trigger_redraws(self):
        rows = (record(1), record(2))
        self.model.replace(rows)
        before = self.content.count()
        changes = QSignalSpy(self.model.dataChanged)
        self.model.replace(list(rows))
        self.assertEqual(self.content.count(), before)
        self.assertEqual(changes.count(), 0)

    def test_schema_and_profile_changes_still_notify_the_view(self):
        self.model.replace((), "municipal")
        self.assertEqual(self.model.columnCount(), 9)
        self.assertEqual(self.resets.count(), 1)
        self.assertEqual(self.columns.count(), 1)
        self.model.setProfile("buying")
        self.assertEqual(self.model.columnCount(), 8)
        self.assertEqual(self.resets.count(), 2)
        self.model.replace((), "general")
        self.assertEqual(self.model.headers[2], "NCM")
        self.assertEqual(self.resets.count(), 3)


class NavigationQtTests(unittest.TestCase):
    def setUp(self):
        self.bundle = create_bundle(initial_module="imports", size=4000)
        self.controller = self.bundle.controller
        self.window = self.bundle.engine.rootObjects()[0]
        self.window.show()
        APP.processEvents()
        self.controller.queryPeriod("2026-04", "2026-09")
        settled(self.controller)

    def tearDown(self):
        self.controller.shutdown()
        self.window.close()
        self.bundle.engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        APP.processEvents()

    def item(self, name):
        obj = self.window.findChild(QObject, name)
        self.assertIsNotNone(obj, name)
        return obj

    def test_ready_pagination_has_no_worker_global_progress_or_analysis_reset(self):
        c = self.controller
        query = self.item("queryPanel")
        table = self.item("recordsTable")
        table.setProperty("contentX", 150)
        scroll = self.item("contentScroll")
        scroll.setProperty(
            "contentY", scroll.property("contentHeight") - scroll.height()
        )
        APP.processEvents()
        before = (
            query.height(),
            scroll.property("contentY"),
            table.property("contentX"),
        )
        analysis = QSignalSpy(c.analysisChanged)
        resets = QSignalSpy(c.table.modelReset)
        columns = QSignalSpy(c.table.columnsChanged)
        totals = c._result.totals
        for page in (2, 3, 4, 2, 1):
            c.setPage(page)
            self.assertIsNone(c._thread)
            self.assertFalse(c.state["busy"])
            APP.processEvents()
            self.assertEqual(c.state["page"], page)
            self.assertEqual(c._result.totals, totals)
            self.assertFalse(self.item("queryProgress").property("visible"))
            self.assertAlmostEqual(query.height(), before[0], delta=0.1)
            self.assertAlmostEqual(scroll.property("contentY"), before[1], delta=0.1)
            self.assertAlmostEqual(table.property("contentX"), before[2], delta=0.1)
        self.assertEqual(analysis.count(), 0)
        self.assertEqual(resets.count(), 0)
        self.assertEqual(columns.count(), 0)
        self.assertEqual(self.bundle.messages, [])

    def test_page_size_change_reuses_the_same_prepared_order(self):
        c = self.controller
        analysis = QSignalSpy(c.analysisChanged)
        for size in (25, 100, 200, 50):
            c.setPageSize(size)
            APP.processEvents()
            self.assertIsNone(c._thread)
            self.assertEqual(c.table.rowCount(), size)
            self.assertEqual(c.state["page"], 1)
        self.assertEqual(analysis.count(), 0)
        self.assertEqual(self.bundle.messages, [])

    def test_debounced_filters_keep_the_layout_stable(self):
        height = self.item("queryPanel").height()
        self.controller.setFilter("country", "China")
        APP.processEvents()
        self.assertFalse(self.item("queryProgress").property("visible"))
        self.assertAlmostEqual(self.item("queryPanel").height(), height, delta=0.1)
        self.assertFalse(self.controller.state["canExport"])
        settled(self.controller)
        self.assertTrue(all(r.country == "China" for r in self.controller.table.rows))
        self.assertAlmostEqual(self.item("queryPanel").height(), height, delta=0.1)
        self.assertEqual(self.bundle.messages, [])

    def test_long_local_update_uses_only_a_delayed_thin_indicator_and_can_cancel(self):
        c = self.controller
        original = c._provider.query
        before = c.table.rows
        height = self.item("queryPanel").height()

        def slow(selection, cancel, progress):
            cancel.wait(0.6)
            return original(selection, cancel, progress)

        with patch.object(c._provider, "query", side_effect=slow):
            c.sortByColumn(6)
            self.assertTrue(c.state["busy"])
            self.assertTrue(c.state["localBusy"])
            APP.processEvents()
            self.assertFalse(self.item("localProgress").property("visible"))
            self.assertTrue(
                pump(lambda: self.item("localProgress").property("visible"))
            )
            self.assertFalse(self.item("queryProgress").property("visible"))
            self.assertAlmostEqual(self.item("queryPanel").height(), height, delta=0.1)
            self.assertEqual(c.table.rows, before)
            c.cancel()
            settled(c)
        self.assertEqual(c.table.rows, before)
        self.assertFalse(c.state["localBusy"])
        self.assertFalse(self.item("localProgress").property("visible"))
        self.assertEqual(self.bundle.messages, [])

    def test_cached_lookup_never_runs_concurrently_with_a_worker(self):
        c = self.controller
        original = c._provider.query

        def slow(selection, cancel, progress):
            cancel.wait(0.1)
            return original(selection, cancel, progress)

        with patch.object(c._provider, "query", side_effect=slow):
            c.sortByColumn(6)
            self.assertIsNotNone(c._thread)
            with patch.object(
                c._provider, "cached_query", wraps=c._provider.cached_query
            ) as lookup:
                c.setPage(2)
                lookup.assert_not_called()
                settled(c)
        self.assertEqual(c.state["page"], 2)
        self.assertEqual(c.state["sortColumn"], 6)
        self.assertEqual(self.bundle.messages, [])

    def test_subtle_transition_never_blanks_the_table_and_obeys_reduced_motion(self):
        c = self.controller
        c.setPage(2)
        APP.processEvents()
        table = self.item("recordsTable")
        self.assertGreaterEqual(table.property("opacity"), 0.89)
        c.setPreference("reducedMotion", True)
        APP.processEvents()
        self.assertFalse(self.item("recordsTransition").property("running"))
        self.assertEqual(table.property("opacity"), 1)
        c.setPreference("dark", True)
        c.setPage(3)
        APP.processEvents()
        self.assertFalse(self.item("recordsTransition").property("running"))
        self.assertEqual(table.property("opacity"), 1)
        self.assertEqual(self.bundle.messages, [])

    def test_an_explicit_query_still_uses_the_validated_worker_path(self):
        c = self.controller
        with patch.object(
            c._provider, "cached_query", side_effect=AssertionError
        ) as lookup:
            c.queryPeriod("2026-04", "2026-09")
            self.assertTrue(c.state["busy"])
            self.assertFalse(c.state["localBusy"])
            settled(c)
            lookup.assert_not_called()
        self.assertFalse(c.state["error"])

    def test_pending_explicit_query_survives_a_new_filter_during_local_work(self):
        c = self.controller
        original = c._provider.query
        release = Event()

        def blocked(selection, cancel, progress):
            release.wait(2)
            return original(selection, cancel, progress)

        with patch.object(c._provider, "query", side_effect=blocked):
            c.sortByColumn(6)
            self.assertTrue(c.state["localBusy"])
            try:
                c.queryPeriod("2026-04", "2026-09")
                self.assertTrue(c._pending_source_query)
                c.setFilter("country", "China")
                self.assertTrue(
                    pump(
                        lambda: c._pending is not None and c._pending.country == "China"
                    )
                )
                self.assertTrue(c._pending_source_query)
            finally:
                release.set()
                settled(c)
        self.assertEqual(c._result.selection.country, "China")
        self.assertFalse(c.state["error"])


class NavigationComexTests(ComexFixtureCase):
    def test_explicit_revalidation_and_force_refresh_refuse_cached_navigation(self):
        self.query()
        self.assertIsNotNone(self.provider.cached_query(self.selection))
        for request in (self.provider.revalidate_next, self.provider.force_refresh):
            request()
            self.assertIsNone(self.provider.cached_query(self.selection))
            self.provider.cancel_pending_options()
            self.assertIsNotNone(self.provider.cached_query(self.selection))
        self.assertIsNone(
            self.provider.cached_query(
                replace(self.selection, period=Period("2026-08", "2026-08"))
            )
        )


class NavigationMunicipalTests(unittest.TestCase):
    # Reuse fixture setup/helpers, without inheriting all unrelated test cases.
    setUp = RealQtTests.setUp
    tearDown = RealQtTests.tearDown
    item = RealQtTests.item
    load = RealQtTests.load

    def test_visible_cell_values_match_the_model_after_base_theme_and_search_changes(
        self,
    ):
        self.load()
        c = self.controller
        for dark, kind in (
            (True, "municipal"),
            (False, "general"),
            (True, "municipal"),
        ):
            c.setPreference("dark", dark)
            c.setDataset(kind)
            settled(c)
            c.setFilter("search", "China")
            settled(c)
            c.clearFilters()
            settled(c)
            table = self.item("recordsTable")
            # Views apply the new model during frame polish, after the Python
            # worker has finished. Inspect the frame the user actually sees.
            frames = QSignalSpy(self.window.frameSwapped)
            self.window.update()
            self.assertTrue(frames.wait(1000))
            checked = []

            def inspect(item, checked):
                row, column = item.property("row"), item.property("column")
                if row == 0 and isinstance(column, int) and item.isVisible():
                    expected = c.table.data(c.table.index(row, column))
                    self.assertEqual(item.property("display"), expected)
                    texts = [child.property("text") for child in item.childItems()]
                    self.assertIn(expected, texts)
                    checked.append(column)
                for child in item.childItems():
                    inspect(child, checked)

            inspect(table.property("contentItem"), checked)
            self.assertGreaterEqual(len(checked), 4)
        self.assertEqual(self.bundle.messages, [])

    def test_table_has_no_residual_pixels_after_schema_changes(self):
        self.load()
        c = self.controller
        c.setPreference("reducedMotion", True)
        for dark, kind in (
            (True, "municipal"),
            (False, "general"),
            (True, "municipal"),
        ):
            c.setPreference("dark", dark)
            c.setDataset(kind)
            settled(c)
            c.setFilter("search", "China")
            settled(c)
            c.clearFilters()
            settled(c)
        scroll = self.item("contentScroll")
        scroll.setProperty(
            "contentY", scroll.property("contentHeight") - scroll.height()
        )
        pump(lambda: False, 0.1)
        table = self.item("recordsTable")
        origin = table.mapToScene(QPointF(0, 0))

        def capture():
            image = self.window.grabWindow()
            scale = image.devicePixelRatio()
            return image.copy(
                round((origin.x() + 2) * scale),
                round((origin.y() + 2) * scale),
                round((table.width() - 22) * scale),
                round((table.height() - 4) * scale),
            )

        before = capture()
        self.window.hide()
        self.window.show()
        pump(lambda: False, 0.1)
        after = capture()
        self.assertFalse(before.isNull())
        self.assertEqual(before, after, "A tabela reteve pixels da base anterior.")
        self.assertEqual(self.bundle.messages, [])

    def test_base_switches_keep_the_window_and_source_and_reuse_prepared_results(self):
        self.load()
        c = self.controller
        before = c._result
        snapshot = self.provider.snapshot
        calls = len(self.transport.calls)
        height = self.item("queryPanel").height()
        c.setDataset("municipal")
        self.assertTrue(c.state["localBusy"])
        APP.processEvents()
        self.assertFalse(self.item("queryProgress").property("visible"))
        settled(c)
        municipal = c._result
        self.assertEqual(municipal.totals.basis, "FOB")
        self.assertAlmostEqual(self.item("queryPanel").height(), height, delta=0.1)
        with patch.object(self.provider, "query", side_effect=AssertionError):
            for kind, result in (
                ("general", before),
                ("municipal", municipal),
                ("general", before),
            ):
                c.setDataset(kind)
                APP.processEvents()
                self.assertIsNone(c._thread)
                self.assertEqual(c._result.totals, result.totals)
                self.assertEqual(c._result.rows, result.rows)
                self.assertTrue(c.state["canExport"])
        self.assertIs(self.provider.snapshot, snapshot)
        self.assertEqual(len(self.transport.calls), calls)
        self.assertEqual(self.bundle.messages, [])

    def test_explicit_same_period_query_cannot_skip_the_provider_after_navigation(self):
        self.load()
        c = self.controller
        with patch.object(self.provider, "query", wraps=self.provider.query) as query:
            c.queryPeriod("2026-09", "2026-09")
            settled(c)
            self.assertEqual(query.call_count, 1)
        self.assertTrue(self.provider.snapshot.response_validated)
        self.assertFalse(c.state["error"])

    def test_rapid_base_switch_cancels_unfinished_municipal_view_without_stale_rows(
        self,
    ):
        self.load()
        c = self.controller
        before = c._result
        original = self.provider.query
        calls = len(self.transport.calls)

        def slow(selection, cancel, progress):
            cancel.wait(0.3)
            return original(selection, cancel, progress)

        with patch.object(self.provider, "query", side_effect=slow):
            c.setDataset("municipal")
            APP.processEvents()
            self.assertTrue(self.item("generalTab").property("enabled"))
            c.setDataset("general")
            settled(c)
        self.assertEqual(c.state["appliedKind"], "general")
        self.assertEqual(c._result.rows, before.rows)
        self.assertEqual(c._result.totals, before.totals)
        self.assertEqual(len(self.transport.calls), calls)
        self.assertFalse(c.state["busy"])
        self.assertFalse(c.state["localBusy"])
        self.assertEqual(self.bundle.messages, [])

    def test_pending_filter_does_not_turn_an_explicit_source_query_into_cached_navigation(
        self,
    ):
        self.load()
        c = self.controller
        c.setFilter("country", "China")
        settled(c)
        c.clearFilters()
        settled(c)
        original = self.provider.query
        observed = []

        def slow(selection, cancel, progress):
            cancel.wait(0.4)
            observed.append(selection)
            return original(selection, cancel, progress)

        with patch.object(self.provider, "query", side_effect=slow):
            c.queryPeriod("2026-09", "2026-09")
            c.setFilter("country", "China")
            self.assertTrue(pump(lambda: c._pending is not None))
            self.assertTrue(c._pending_source_query)
            settled(c)
        self.assertEqual(len(observed), 2)
        self.assertEqual(c._result.selection.country, "China")
        self.assertTrue(self.provider.snapshot.response_validated)
        self.assertTrue(c.state["canExport"])
        self.assertEqual(self.bundle.messages, [])
