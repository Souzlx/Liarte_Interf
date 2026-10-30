"""Priority views reuse monthly facts and preserve the stock session."""

from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import patch

from PySide6.QtCore import QThread, QUrl
from PySide6.QtTest import QSignalSpy
from openpyxl import load_workbook

from liarte_core.inventory_io import write_snapshot
from liarte_desktop import inventory as stock_desktop
from liarte_desktop import inventory_performance as performance_desktop
from liarte_desktop import inventory_priorities as desktop
from tests.test_inventory_performance_ui import performance_months, performance_sample
from tests.test_qt import APP, pump


class InventoryPrioritiesUiTests(unittest.TestCase):
    def setUp(self):
        self.c = desktop.InventoryPrioritiesController()
        self.addCleanup(self.c.shutdown)

    def idle(self):
        self.assertTrue(pump(lambda: not self.c.state["busy"], 15), self.c.state)
        APP.processEvents()

    def load(self, *, count=25, **filters):
        months, selected = performance_months(performance_sample(count), **filters)
        self.c.set_source(months, selected)
        self.c.refresh()
        self.idle()
        self.assertTrue(self.c.state["current"], self.c.state)
        self.assertFalse(self.c.state["error"])
        return months, selected

    def configure(self, *, unit="KG", window=1, category="capital", query=""):
        self.c.configure(unit, window, category, query)
        self.idle()
        self.assertTrue(self.c.state["current"], self.c.state)

    def test_no_source_is_idle_and_monthly_source_is_lazy_until_opened(self):
        self.c.refresh()
        self.c.investigate("P001", "KG")
        self.assertFalse(self.c.state["available"])
        self.assertEqual(self.c.summary, {})
        months, selected = performance_months()
        fresh = desktop.InventoryPrioritiesController()
        self.addCleanup(fresh.shutdown)
        with patch.object(desktop, "analyze_product_performance") as analyze:
            fresh.set_source(months, selected)
            APP.processEvents()
            analyze.assert_not_called()
        self.assertTrue(fresh.state["available"])
        self.assertFalse(fresh.state["current"])
        self.assertFalse(fresh.state["busy"])

    def test_analysis_runs_outside_gui_and_only_a_unit_specific_page_reaches_qml(self):
        original = desktop.analyze_product_performance
        visits = []

        def observed(*args, **kwargs):
            visits.append(QThread.currentThread() == APP.thread())
            return original(*args, **kwargs)

        with patch.object(desktop, "analyze_product_performance", side_effect=observed):
            self.load()
            self.configure()
        self.assertEqual(visits, [False, False])
        self.assertEqual(self.c.state["count"], 25)
        self.assertEqual(self.c.state["pages"], 4)
        self.assertEqual(len(self.c.summary["rows"]), desktop.PAGE_SIZE)
        self.assertTrue(all(row["unit"] == "KG" for row in self.c.summary["rows"]))
        self.configure(unit="L")
        self.assertEqual(self.c.state["count"], 1)
        self.assertEqual(self.c.summary["rows"][0]["code"], "LIQ")

    def test_pages_focus_and_accent_folded_search_reuse_accepted_calculation(self):
        self.load()
        self.configure()
        with (
            patch.object(desktop, "analyze_product_performance", side_effect=AssertionError("Monthly facts recomputed")),
            patch.object(desktop, "analyze_product_priorities", side_effect=AssertionError("Priorities recomputed")),
        ):
            self.c.setPage(2)
            self.idle()
            self.assertEqual(self.c.state["page"], 2)
            row = self.c.summary["rows"][0]
            self.c.investigate(row["code"], row["unit"])
            self.assertEqual(self.c.detail["code"], row["code"])
            self.c.setPage(3)
            self.idle()
            self.assertEqual(self.c.detail["code"], row["code"])
            self.c.configure("KG", 1, "capital", "acido")
            self.idle()
        self.assertEqual(self.c.state["page"], 1)
        self.assertEqual(self.c.state["count"], 1)
        self.assertEqual(self.c.summary["rows"][0]["code"], "P010")
        self.assertFalse(self.c.detail)
        counts = {item["value"]: item["count"] for item in self.c.state["categories"]}
        self.assertEqual(counts["capital"], 1)

    def test_detail_has_reference_facts_and_full_export_is_not_the_visible_page(self):
        self.load()
        self.configure()
        row = self.c.summary["rows"][0]
        self.c.investigate(row["code"], row["unit"])
        detail = self.c.detail
        self.assertEqual((detail["code"], detail["unit"]), (row["code"], row["unit"]))
        self.assertEqual(len(detail["metrics"]), 5)
        self.assertTrue(detail["reasons"])
        self.assertTrue(all(set(("key", "title", "fact", "nextStep")) <= reason.keys()
                            for reason in detail["reasons"]))
        report, raw = self.c.export_snapshot()
        self.assertEqual(report["window"], 1)
        self.assertGreater(len(report["rows"]), len(self.c.summary["rows"]))
        self.assertEqual(raw["code"], row["code"])
        self.c.investigate("missing", "KG")
        self.assertEqual(self.c.detail, detail)
        self.c.closeDetail()
        self.assertFalse(self.c.detail)
        self.assertIsNone(self.c.export_snapshot()[1])

    def test_limit_update_only_reclassifies_cached_performance(self):
        months, selected = self.load()
        original = desktop.analyze_product_priorities
        calls = []

        def classified(report, **kwargs):
            calls.append(kwargs["coverage_days"])
            return original(report, **kwargs)

        with (
            patch.object(desktop, "analyze_product_performance", side_effect=AssertionError("Monthly facts recomputed")),
            patch.object(desktop, "analyze_product_priorities", side_effect=classified),
        ):
            self.c.set_source(months, selected, 365)
            self.assertFalse(self.c.state["current"])
            self.assertFalse(self.c.detail)
            self.idle()
        self.assertEqual(calls, [365])
        self.assertEqual(self.c.report["coverageDays"], 365)

    def test_failure_restores_options_page_detail_and_accepted_window(self):
        self.load()
        self.configure()
        self.c.setPage(2)
        self.idle()
        row = self.c.summary["rows"][0]
        self.c.investigate(row["code"], row["unit"])
        before = self.c.summary, self.c.detail, self.c.export_snapshot()
        with (
            patch.object(desktop, "analyze_product_performance", side_effect=ValueError("Synthetic failure")),
            self.assertLogs("liarte.desktop", level="ERROR"),
        ):
            self.c.configure("KG", 6, "review", "other")
            self.idle()
        self.assertEqual((self.c.state["window"], self.c.state["category"], self.c.state["query"], self.c.state["page"]), (1, "capital", "", 2))
        self.assertTrue(self.c.state["error"])
        self.assertTrue(self.c.state["current"])
        self.assertEqual((self.c.summary, self.c.detail, self.c.export_snapshot()), before)

    def test_cancel_restores_applied_options_without_relabeling_accepted_results(self):
        self.load()
        self.configure()
        before = self.c.summary
        entered, release = Event(), Event()
        self.addCleanup(release.set)
        original = desktop.analyze_product_performance

        def delayed(*args, **kwargs):
            entered.set()
            if not release.wait(10):
                raise RuntimeError("Test did not release priority worker")
            return original(*args, **kwargs)

        try:
            with patch.object(desktop, "analyze_product_performance", side_effect=delayed):
                self.c.configure("KG", 6, "review", "other")
                self.assertTrue(pump(entered.is_set))
                self.c.cancel()
                release.set()
                self.idle()
            self.assertEqual(self.c.summary, before)
            self.assertEqual((self.c.state["window"], self.c.state["category"], self.c.state["query"]), (1, "capital", ""))
            self.assertTrue(self.c.state["current"])
            self.assertTrue(self.c.state["cancelled"])
            with patch.object(desktop, "analyze_product_performance", side_effect=AssertionError("Unrequested recalculation")):
                self.c.configure("KG", 1, "capital", "")
                self.assertFalse(self.c.state["cancelled"])
                self.assertTrue(self.c.state["current"])
        finally:
            release.set()

    def test_cancel_initial_analysis_stays_idle_until_explicit_refresh(self):
        months, selected = performance_months()
        self.c.set_source(months, selected)
        entered, release = Event(), Event()
        self.addCleanup(release.set)
        original = desktop.analyze_product_performance
        calls = []

        def delayed(*args, **kwargs):
            calls.append(True)
            entered.set()
            if not release.wait(10):
                raise RuntimeError("Test did not release first preparation")
            return original(*args, **kwargs)

        try:
            with patch.object(desktop, "analyze_product_performance", side_effect=delayed):
                self.c.refresh()
                self.assertTrue(pump(entered.is_set))
                self.c.cancel()
                self.assertTrue(self.c.state["cancelled"])
                release.set()
                self.idle()
                pump(lambda: False, 0.04)
                self.assertEqual(len(calls), 1)
                self.assertTrue(self.c.state["cancelled"])
                self.assertFalse(self.c.state["current"])
                self.assertFalse(self.c.state["error"])
                self.assertEqual(self.c.export_snapshot(), (None, None))
                self.c.refresh()
                self.idle()
            self.assertEqual(len(calls), 2)
            self.assertFalse(self.c.state["cancelled"])
            self.assertTrue(self.c.state["current"])
        finally:
            release.set()

    def test_new_source_resumes_requested_view_after_initial_cancellation(self):
        months, selected = performance_months()
        self.c.set_source(months, selected)
        entered, release = Event(), Event()
        self.addCleanup(release.set)
        original = desktop.analyze_product_performance

        def delayed(*args, **kwargs):
            entered.set()
            if not release.wait(10):
                raise RuntimeError("Test did not release initial source")
            return original(*args, **kwargs)

        try:
            with patch.object(desktop, "analyze_product_performance", side_effect=delayed):
                self.c.refresh()
                self.assertTrue(pump(entered.is_set))
                self.c.cancel()
                release.set()
                self.idle()
            self.assertTrue(self.c.state["cancelled"])
            months, selected = performance_months(unit="L")
            self.c.set_source(months, selected)
            self.assertFalse(self.c.state["cancelled"])
            self.idle()
            self.assertTrue(self.c.state["current"])
            self.assertEqual(self.c.state["unit"], "L")
        finally:
            release.set()

    def test_latest_request_wins_and_old_source_never_publishes_after_invalidation(self):
        old_months, old_selection = self.load()
        entered, release = Event(), Event()
        self.addCleanup(release.set)
        original = desktop.analyze_product_performance

        def delayed(months, *args, **kwargs):
            if months is old_months:
                entered.set()
                if not release.wait(10):
                    raise RuntimeError("Test did not release old source")
            return original(months, *args, **kwargs)

        try:
            with patch.object(desktop, "analyze_product_performance", side_effect=delayed):
                self.c.configure("KG", 6, "capital", "")
                self.assertTrue(pump(entered.is_set))
                self.c.set_source(None, None)
                self.assertFalse(self.c.state["available"])
                self.assertEqual(self.c.summary, {})
                self.assertEqual(self.c.export_snapshot(), (None, None))
                months, selected = performance_months(unit="L")
                self.c.set_source(months, selected)
                self.c.configure("L", 1, "capital", "")
                release.set()
                self.idle()
            self.assertEqual(self.c.state["window"], 1)
            self.assertEqual(self.c.state["unit"], "L")
            self.assertEqual([row["code"] for row in self.c.summary["rows"]], ["LIQ"])
            self.assertNotEqual(selected, old_selection)
        finally:
            release.set()

    def test_invalid_options_and_unit_do_not_replace_accepted_results(self):
        self.load()
        self.configure()
        before = self.c.summary
        for values in (("invalid", 1, "capital", ""), ("KG", 2, "capital", ""),
                       ("KG", 1, "invalid", ""), ("KG", 1, "capital", "x" * 201)):
            self.c.configure(*values)
            self.assertEqual(self.c.summary, before)
            self.assertTrue(self.c.state["current"])
            self.assertTrue(self.c.state["error"])


class InventoryPrioritiesIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.c = stock_desktop.InventoryController()
        self.addCleanup(self.c.shutdown)
        self.p = self.c.priorities

    def idle(self):
        self.assertTrue(pump(lambda: not self.c.state["busy"] and not self.c._debounce.isActive()
                            and not self.p.state["busy"], 15), (self.c.state, self.p.state))
        APP.processEvents()

    def load(self):
        source = self.root / "stock.liarte"
        write_snapshot(performance_sample(), source)
        self.c.openFile(QUrl.fromLocalFile(str(source)))
        self.idle()
        self.assertTrue(self.c.state["current"])

    def inspect(self):
        self.p.refresh()
        self.idle()
        self.p.configure("KG", 1, "capital", "")
        self.idle()
        self.p.investigate("P001", "KG")
        self.assertEqual(self.p.detail["code"], "P001")

    def test_owner_load_is_lazy_and_explicit_focus_applies_only_product_and_unit(self):
        with patch.object(desktop, "analyze_product_performance") as analyze:
            self.load()
            analyze.assert_not_called()
        self.assertTrue(self.p.state["available"])
        self.assertFalse(self.p.state["current"])
        before = self.c.state["selection"]
        with patch.object(stock_desktop, "load_inventory", side_effect=AssertionError("Source reread")):
            self.inspect()
            self.assertEqual(self.c.state["selection"], before)
            self.c.focusPriorityProduct("P001", "L")
            self.assertEqual(self.c.state["selection"], before)
            self.c.focusPriorityProduct("P001", "KG")
            self.assertEqual(self.c.state["selection"]["product"], "P001")
            self.assertEqual(self.c.state["selection"]["unit"], "KG")
            for key, value in before.items():
                if key not in ("product", "unit", "search"):
                    self.assertEqual(self.c.state["selection"][key], value)
            self.assertFalse(self.p.state["available"])
            self.idle()
        self.assertTrue(self.p.state["current"])

    def test_owner_limit_update_reuses_priority_monthly_cache_and_applies_committed_policy(self):
        self.load()
        self.inspect()
        with patch.object(desktop, "analyze_product_performance", side_effect=AssertionError("Unrequested monthly analysis")):
            self.c.setAlertThresholds(90, 365)
            self.idle()
        self.assertEqual(self.p.report["coverageDays"], 365)
        self.assertEqual(self.c._applied_alert_policy.coverage_days, 365)

    def test_owner_filter_invalidates_visible_priority_before_debounce(self):
        self.load()
        self.inspect()
        self.c.setFilter("unit", "L")
        self.assertTrue(self.c._debounce.isActive())
        self.assertFalse(self.p.state["available"])
        self.assertEqual(self.p.summary, {})
        self.assertFalse(self.p.detail)
        self.idle()
        self.assertEqual(self.p.state["unit"], "L")
        self.assertTrue(self.p.state["current"])

    def test_owner_excel_exports_complete_accepted_priority_snapshot_with_real_workbook(self):
        self.load()
        self.p.refresh()
        self.idle()
        self.p.configure("KG", 1, "capital", "P00")
        self.idle()
        self.p.setPage(2)
        self.idle()
        self.assertEqual(self.p.state["page"], 2)
        self.assertEqual(self.p.state["count"], 9)
        self.assertEqual(len(self.p.summary["rows"]), 1)
        accepted, _ = self.p.export_snapshot()
        path = self.root / "priorities-complete.xlsx"
        with patch("liarte_core.inventory_priorities.analyze_product_priorities",
                   side_effect=AssertionError("Accepted priorities were recomputed")):
            self.c.exportExcel(QUrl.fromLocalFile(str(path)))
            self.idle()
        self.assertTrue(path.is_file(), self.c.state)
        self.assertFalse(self.c.state["error"])
        book = load_workbook(path)
        try:
            sheet = book["Prioridades dos produtos"]
            values = list(sheet.values)
            self.assertEqual(len(values[0]), 25)
            rows = [dict(zip(values[0], row, strict=True)) for row in values[1:]]
            self.assertEqual(len(rows), len(accepted["rows"]))
            self.assertEqual({(row["Código"], row["UM"]) for row in rows},
                             {(row["code"], row["unit"]) for row in accepted["rows"]})
            self.assertIn(("LIQ", "L"), {(row["Código"], row["UM"]) for row in rows})
            self.assertIn("P010", {row["Código"] for row in rows})
            for row in rows:
                self.assertEqual(row["Mês do fechamento"], "2026-02")
                self.assertEqual(row["Janela anterior"], "01/2026")
                self.assertEqual(row["Janela recente"], "02/2026")
                self.assertEqual(row["Limite de cobertura (dias)"], 30)
                self.assertIn(self.c._data.source_name, row["Fonte, base e filtros"])
                self.assertIn("2026-03-15", row["Fonte, base e filtros"])
                self.assertIn("sem os limites de busca", row["Definição e limites"])
            definitions = dict(book["Leitura dos indicadores"].values)
            self.assertIn("Prioridades dos produtos · referência", definitions)
            self.assertIn("2026-02", definitions["Prioridades dos produtos · referência"])
            self.assertIn("Prioridades dos produtos · critérios e abrangência", definitions)
        finally:
            book.close()

    def test_owner_shutdown_retains_both_child_threads_and_emits_once_after_join(self):
        self.load()
        entered, performance_entered, release = Event(), Event(), Event()
        self.addCleanup(release.set)
        original = desktop.analyze_product_performance
        stopped = QSignalSpy(self.c.shutdownFinished)

        def delayed(*args, **kwargs):
            entered.set()
            if not release.wait(10):
                raise RuntimeError("Test did not release shutdown worker")
            return original(*args, **kwargs)

        def delayed_performance(*args, **kwargs):
            performance_entered.set()
            if not release.wait(10):
                raise RuntimeError("Test did not release performance shutdown worker")
            return original(*args, **kwargs)

        try:
            with (
                patch.object(desktop, "analyze_product_performance", side_effect=delayed),
                patch.object(performance_desktop, "analyze_product_performance", side_effect=delayed_performance),
            ):
                self.p.refresh()
                self.c.performance.refresh()
                self.assertTrue(pump(entered.is_set))
                self.assertTrue(pump(performance_entered.is_set))
                self.assertFalse(self.c.shutdown(wait_ms=0))
                self.assertEqual(stopped.count(), 0)
                self.assertIn(self.c, stock_desktop._SHUTTING_DOWN)
                release.set()
                self.assertTrue(pump(lambda: stopped.count() == 1, 15))
            self.assertIsNone(self.p._thread)
            self.assertIsNone(self.c.performance._thread)
            self.assertNotIn(self.c, stock_desktop._SHUTTING_DOWN)
            self.assertTrue(self.c.shutdown(wait_ms=0))
            self.assertEqual(stopped.count(), 1)
        finally:
            release.set()
