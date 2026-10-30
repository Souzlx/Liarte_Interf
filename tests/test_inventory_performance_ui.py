"""Product investigations use cached facts without disturbing the stock session."""

from dataclasses import replace
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import patch

from PySide6.QtCore import QThread, QUrl
from PySide6.QtTest import QSignalSpy

from liarte_core.inventory import (
    SCALE, Balance, Closing, InventoryData, Product, Sale, StockSelection, month_range,
)
from liarte_core.inventory_monthly import analyze_monthly_inventory
from liarte_core.inventory_io import write_snapshot
from liarte_desktop import inventory as stock_desktop
from liarte_desktop import inventory_performance as desktop
from tests.test_qt import APP, pump


def performance_sample(count=25):
    """Fourteen complete months, mixed units and a historical-only product."""
    periods = month_range("2025-01", "2026-02")
    products = tuple(
        Product(f"P{index:03}", "Ácido especial" if index == 10 else f"Produto {index:03}", "G", "PA", "KG")
        for index in range(1, count + 1)
    ) + (
        Product("OLD", "Produto só histórico", "G", "PA", "KG"),
        Product("LIQ", "Produto em litros", "G", "PA", "L"),
    )

    def sold(product, period):
        if product.code == "OLD":
            return 4 * SCALE
        if product.code == "LIQ":
            return 999 * SCALE
        index = int(product.code[1:])
        if index == 1:
            return (1 if period == "2026-02" else 20) * SCALE
        return index * (2 if period == "2026-02" else 1) * SCALE

    return InventoryData(
        date(2026, 3, 15), "Desempenho sintético.pbix", "a" * 64, products,
        tuple(
            Balance(p.code, "01", "01", p.unit, 100 * SCALE, 10000)
            for p in products if p.code != "OLD"
        ),
        tuple(
            Closing(p.code, "01", "01", p.unit, period, 100 * SCALE, 10000, index / 10, 30)
            for period in periods for index, p in enumerate(products, 1)
            if p.code != "OLD" or period != "2026-02"
        ),
        tuple(
            Sale(p.code, "01", p.unit, date.fromisoformat(period + "-01"), sold(p, period), 100)
            for period in periods for p in products
        ),
    )


def performance_months(data=None, **filters):
    selection = StockSelection("2025-01", "2026-02", **filters)
    return analyze_monthly_inventory(data or performance_sample(), selection), selection


class InventoryPerformanceUiTests(unittest.TestCase):
    def setUp(self):
        self.c = desktop.InventoryPerformanceController()
        self.addCleanup(self.c.shutdown)

    def idle(self):
        self.assertTrue(pump(lambda: not self.c.state["busy"], 15), self.c.state)
        APP.processEvents()

    def load(self, data=None, **filters):
        months, selected = performance_months(data, **filters)
        self.c.set_source(months, selected)
        self.c.refresh()
        self.idle()
        self.assertTrue(self.c.state["current"], self.c.state)
        self.assertFalse(self.c.state["error"])
        return months, selected

    def configure(self, unit="KG", window=1, sort="most", query=""):
        self.c.configure(unit, window, sort, query)
        self.idle()
        self.assertTrue(self.c.state["current"], self.c.state)

    def test_no_source_does_not_invent_a_list_or_start_work(self):
        self.assertFalse(self.c.state["available"])
        self.c.refresh()
        self.c.investigate("P001", "KG")
        self.c.setPage(2)
        self.idle()
        self.assertFalse(self.c.state["current"])
        self.assertEqual(self.c.summary.get("rows", []), [])
        self.assertFalse(self.c.detail)

    def test_setting_a_source_is_lazy_until_the_investigation_is_opened(self):
        months, selected = performance_months()
        with patch.object(desktop, "analyze_product_performance") as analyze:
            self.c.set_source(months, selected)
            APP.processEvents()
            analyze.assert_not_called()
        self.assertTrue(self.c.state["available"])
        self.assertFalse(self.c.state["busy"])

        self.assertFalse(self.c.state["current"])

    def test_preparation_runs_on_worker_and_never_rereads_or_reanalyzes_source(self):
        months, selected = performance_months()
        original = desktop.analyze_product_performance
        visits = []

        def observed(*args, **kwargs):
            visits.append(QThread.currentThread() == APP.thread())
            return original(*args, **kwargs)

        with (
            patch.object(desktop, "analyze_product_performance", side_effect=observed),
            patch.object(stock_desktop, "load_inventory", side_effect=AssertionError("Source reread")),
            patch.object(stock_desktop, "analyze_inventory", side_effect=AssertionError("Stock reanalysis")),
            patch.object(stock_desktop, "analyze_monthly_inventory", side_effect=AssertionError("History reread")),
        ):
            self.c.set_source(months, selected)
            self.c.refresh()
            self.idle()
        self.assertEqual(visits, [False])
        self.assertTrue(self.c.state["current"], self.c.state)

    def test_refresh_is_idempotent_while_the_same_source_is_already_being_prepared(self):
        months, selected = performance_months()
        entered, release = Event(), Event()
        original = desktop.analyze_product_performance
        calls = []

        def delayed(*args, **kwargs):
            calls.append(True)
            entered.set()
            if not release.wait(10):
                raise RuntimeError("Test did not release refresh worker")
            return original(*args, **kwargs)

        try:
            with patch.object(desktop, "analyze_product_performance", side_effect=delayed):
                self.c.set_source(months, selected)
                self.c.refresh()
                self.assertTrue(pump(entered.is_set))
                self.c.refresh()
                self.c.refresh()
                release.set()
                self.idle()
            self.assertEqual(len(calls), 1)
            self.assertTrue(self.c.state["current"], self.c.state)
        finally:
            release.set()

    def test_rankings_are_unit_specific_and_only_a_page_reaches_qml(self):
        self.load()
        self.configure()
        self.assertEqual(self.c.state["unit"], "KG")
        self.assertEqual({u["value"] for u in self.c.state["units"]}, {"KG", "L"})
        self.assertEqual(self.c.state["count"], 26)
        self.assertEqual(self.c.state["pages"], 3)
        self.assertEqual(len(self.c.summary["rows"]), 10)
        self.assertEqual(self.c.summary["rows"][0]["code"], "P025")
        self.assertTrue(all(row["unit"] == "KG" for row in self.c.summary["rows"]))
        self.configure(unit="L")
        self.assertEqual(self.c.state["count"], 1)
        self.assertEqual(self.c.summary["rows"][0]["code"], "LIQ")

    def test_pagination_uses_cached_report_and_keeps_options(self):
        self.load()
        self.configure()
        first = self.c.summary["rows"]
        with patch.object(desktop, "analyze_product_performance", side_effect=AssertionError("Page reanalysis")):
            self.c.setPage(2)
            self.idle()
        self.assertEqual(self.c.state["page"], 2)
        self.assertEqual(len(self.c.summary["rows"]), 10)
        self.assertFalse({r["code"] for r in first} & {r["code"] for r in self.c.summary["rows"]})
        self.assertEqual(self.c.state["window"], 1)
        self.assertEqual(self.c.state["unit"], "KG")

    def test_search_and_sort_use_cached_report_instead_of_recomputing_facts(self):
        self.load()
        self.configure()
        with patch.object(desktop, "analyze_product_performance", side_effect=AssertionError("Search reanalysis")):
            self.configure(query="p010")
            self.assertEqual(self.c.state["count"], 1)
            self.assertEqual(self.c.summary["rows"][0]["code"], "P010")
            self.configure(query="ESPECIAL")
            self.assertEqual(self.c.summary["rows"][0]["code"], "P010")
            self.configure(sort="decline")
        self.assertEqual([row["code"] for row in self.c.summary["rows"]], ["P001"])

    def test_least_sold_with_stock_excludes_missing_closing_and_preserves_known_low_values(self):
        self.load()
        self.configure(sort="least")
        self.assertEqual(self.c.summary["rows"][0]["code"], "P001")
        codes = set()
        for page in range(1, self.c.state["pages"] + 1):
            self.c.setPage(page)
            self.idle()
            codes.update(r["code"] for r in self.c.summary["rows"])
        self.assertNotIn("OLD", codes)
        self.assertEqual(len(codes), 25)

    def test_all_products_keeps_zero_negative_and_historical_records_accessible(self):
        data = performance_sample(3)
        data = replace(data, sales=tuple(
            replace(sale, quantity=-SCALE if sale.product == "P002" else 0)
            if sale.day == date(2026, 2, 1) and sale.product in {"P002", "P003"}
            else sale
            for sale in data.sales
        ))
        self.load(data)
        self.configure(sort="all")
        self.assertEqual(self.c.state["count"], 4)
        rows = {row["code"]: row for row in self.c.summary["rows"]}
        self.assertEqual(set(rows), {"P001", "P002", "P003", "OLD"})
        self.assertEqual(rows["P002"]["status"], "Quantidade líquida < 0")
        self.assertEqual(rows["P003"]["status"], "Quantidade líquida = 0")
        self.assertEqual(rows["OLD"]["stock"], "Sem fechamento")
        self.c.investigate("P002", "KG")
        self.idle()
        self.assertEqual(self.c.detail["code"], "P002")
        self.assertTrue(self.c.detail["indicators"])
        self.assertNotIn("evidence", self.c.detail)
        self.assertNotIn("hypotheses", self.c.detail)
        self.assertTrue(all(set(("key", "label", "value", "detail")) <= row.keys()
                            for row in self.c.detail["indicators"]))

    def test_windows_are_cached_independently_and_source_change_invalidates_them(self):
        original = desktop.analyze_product_performance
        calls = []

        def observed(*args, **kwargs):
            calls.append(kwargs.get("window", 3))
            return original(*args, **kwargs)

        with patch.object(desktop, "analyze_product_performance", side_effect=observed):
            self.load()
            self.configure(window=1)
            self.configure(window=6)
            self.configure(window=1)
            self.assertEqual(calls, [3, 1, 6])
            months, selected = performance_months(performance_sample(3))
            self.c.set_source(months, selected)
            self.c.refresh()
            self.idle()
        self.assertEqual(calls, [3, 1, 6, 1])
        self.assertEqual(self.c.state["count"], 4)

    def test_historical_product_can_be_investigated_without_a_current_position(self):
        self.load()
        self.configure(query="OLD")
        self.c.investigate("OLD", "KG")
        self.idle()
        self.assertEqual(self.c.detail["code"], "OLD")
        self.assertEqual(self.c.detail["unit"], "KG")
        self.assertEqual(len(self.c.detail["series"]["sales"]["points"]), 14)
        self.assertIsNone(self.c.detail["series"]["quantity"]["points"][-1]["value"])
        self.assertTrue(self.c.detail["limitations"])

    def test_detail_runs_on_worker_and_leaves_listing_search_page_and_source_intact(self):
        months, selected = self.load()
        self.configure()
        self.c.setPage(2)
        self.idle()
        before = self.c.summary
        original = desktop.product_performance_detail
        visits = []

        def observed(*args, **kwargs):
            visits.append(QThread.currentThread() == APP.thread())
            return original(*args, **kwargs)

        code = before["rows"][0]["code"]
        with patch.object(desktop, "product_performance_detail", side_effect=observed):
            self.c.investigate(code, "KG")
            self.idle()
        self.assertEqual(visits, [False])
        self.assertEqual(self.c.detail["code"], code)
        self.assertEqual(self.c.state["page"], 2)
        self.assertEqual(self.c.summary, before)
        self.c.closeDetail()
        self.assertFalse(self.c.detail)
        self.assertEqual(self.c.summary, before)
        self.assertEqual(selected, StockSelection("2025-01", "2026-02"))
        self.assertEqual(len(months), 14)

    def test_unknown_product_never_reuses_another_products_detail(self):
        self.load()
        self.configure()
        self.c.investigate("P001", "KG")
        self.idle()
        self.c.closeDetail()
        self.c.investigate("MISSING", "KG")
        self.idle()
        self.assertFalse(self.c.detail)

    def test_replacing_source_during_preparation_discards_old_result(self):
        old_months, selected = performance_months()
        new_months, _ = performance_months(performance_sample(3))
        entered, release = Event(), Event()
        original = desktop.analyze_product_performance
        calls = []

        def delayed(months, *args, **kwargs):
            calls.append(months)
            if months is old_months:
                entered.set()
                if not release.wait(10):
                    raise RuntimeError("Test did not release product worker")
            return original(months, *args, **kwargs)

        try:
            with patch.object(desktop, "analyze_product_performance", side_effect=delayed):
                self.c.set_source(old_months, selected)
                self.c.refresh()
                self.assertTrue(pump(entered.is_set))
                self.c.set_source(new_months, selected)
                self.assertFalse(self.c.state["current"])
                self.c.refresh()
                release.set()
                self.idle()
            self.assertTrue(self.c.state["current"], self.c.state)
            self.assertEqual(self.c.state["count"], 4)
            self.assertEqual(len(calls), 2)
        finally:
            release.set()

    def test_invalidated_source_blocks_previous_product_actions(self):
        self.load()
        self.configure()
        self.c.set_source(None, None)
        self.c.investigate("P001", "KG")
        self.c.setPage(2)
        self.idle()
        self.assertFalse(self.c.state["available"])
        self.assertFalse(self.c.state["current"])
        self.assertFalse(self.c.detail)

    def test_failure_is_visible_without_claiming_old_results_are_current_and_refresh_recovers(self):
        months, selected = performance_months()
        with (
            self.assertLogs("liarte.desktop", level="ERROR") as logs,
            patch.object(desktop, "analyze_product_performance", side_effect=ValueError("Falha sintética")),
        ):
            self.c.set_source(months, selected)
            self.c.refresh()
            self.idle()
        self.assertIn("Falha sintética", "\n".join(logs.output))
        self.assertFalse(self.c.state["current"])
        self.assertTrue(self.c.state["error"])
        self.assertFalse(self.c.state["busy"])
        self.c.refresh()
        self.idle()
        self.assertTrue(self.c.state["current"], self.c.state)
        self.assertFalse(self.c.state["error"])

    def test_closing_detail_while_pending_cancels_it_without_replacing_the_list(self):
        self.load()
        self.configure()
        before = self.c.summary
        entered, release = Event(), Event()
        original = desktop.product_performance_detail

        def delayed(*args, **kwargs):
            entered.set()
            if not release.wait(10):
                raise RuntimeError("Test did not release detail worker")
            return original(*args, **kwargs)

        try:
            with patch.object(desktop, "product_performance_detail", side_effect=delayed):
                self.c.investigate("P001", "KG")
                self.assertTrue(pump(entered.is_set))
                self.c.closeDetail()
                release.set()
                self.idle()
            self.assertFalse(self.c.detail)
            self.assertEqual(self.c.summary, before)
            self.assertTrue(self.c.state["current"], self.c.state)
        finally:
            release.set()

    def test_shutdown_cancels_worker_and_joins_native_thread(self):
        months, selected = performance_months()
        entered = Event()
        original = desktop.analyze_product_performance

        def delayed(*args, **kwargs):
            entered.set()
            if not kwargs["cancel"].wait(10):
                raise RuntimeError("Shutdown did not request cancellation")
            return original(*args, **kwargs)

        with patch.object(desktop, "analyze_product_performance", side_effect=delayed):
            self.c.set_source(months, selected)
            self.c.refresh()
            self.assertTrue(pump(entered.is_set))
            self.assertTrue(self.c.shutdown())
        self.assertFalse(self.c.state["busy"])

class InventoryPerformanceIntegrationTests(unittest.TestCase):
    """The stock owner invalidates cached facts and owns both thread lifetimes."""

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name).resolve()
        self.c = stock_desktop.InventoryController()
        self.addCleanup(self.c.shutdown)
        self.p = self.c.performance
        self.source_count = 0

    def idle(self):
        self.assertTrue(pump(
            lambda: not self.c.state["busy"] and not self.c._debounce.isActive()
            and not self.p.state["busy"],
            15,
        ), (self.c.state, self.p.state))
        APP.processEvents()

    def load(self, data=None):
        self.source_count += 1
        source = self.directory / f"source-{self.source_count}.liarte"
        write_snapshot(data or performance_sample(), source)
        self.c.openFile(QUrl.fromLocalFile(str(source)))
        self.idle()
        self.assertTrue(self.c.state["loaded"], self.c.state)
        self.assertTrue(self.c.state["current"], self.c.state)
        self.assertFalse(self.c.state["error"])

    def investigate(self, code="OLD", unit="KG"):
        self.p.refresh()
        self.idle()
        self.p.configure(unit, 1, "all", "")
        self.idle()
        self.p.investigate(code, unit)
        self.idle()
        self.assertEqual(self.p.detail["code"], code)

    def test_loaded_base_only_supplies_cached_source_until_performance_is_opened(self):
        with patch.object(desktop, "analyze_product_performance") as analyze:
            self.load()
            analyze.assert_not_called()
        self.assertTrue(self.p.state["available"])
        self.assertFalse(self.p.state["current"])
        self.assertFalse(self.p.state["busy"])
        self.assertEqual(self.p.summary, {})
        self.p.refresh()
        self.idle()
        self.assertTrue(self.p.state["current"], self.p.state)
        self.assertTrue(self.p.summary["rows"])

    def test_filter_invalidates_before_debounce_and_replaces_pending_product_work(self):
        self.load()
        self.p.refresh()
        self.idle()
        entered, release = Event(), Event()
        self.addCleanup(release.set)
        original = desktop.analyze_product_performance
        old_months = self.c._monthly_data

        def delayed(months, *args, **kwargs):
            if months is old_months:
                entered.set()
                if not release.wait(10):
                    raise RuntimeError("Test did not release old filtered investigation")
            return original(months, *args, **kwargs)

        try:
            with patch.object(desktop, "analyze_product_performance", side_effect=delayed):
                self.p.configure("KG", 6, "all", "")
                self.assertTrue(pump(entered.is_set))
                self.c.setFilter("unit", "L")
                self.assertTrue(self.c._debounce.isActive())
                self.assertFalse(self.p.state["available"])
                self.assertFalse(self.p.state["current"])
                self.assertFalse(self.p.detail)
                self.assertTrue(pump(
                    lambda: not self.c.state["busy"] and not self.c._debounce.isActive()
                    and self.c.state["current"] and self.p.state["available"],
                    15,
                ), self.c.state)
                self.assertFalse(self.p.state["current"])
                release.set()
                self.idle()
            self.assertTrue(self.p.state["current"], self.p.state)
            self.assertEqual(self.p.state["unit"], "L")
            self.assertEqual([r["code"] for r in self.p.summary["rows"]], ["LIQ"])
            self.assertEqual(self.c.state["selection"]["unit"], "L")
        finally:
            release.set()

    def test_historical_investigation_only_changes_global_filter_after_explicit_focus(self):
        self.load()
        before = self.c.state["selection"]
        with (
            patch.object(stock_desktop, "analyze_inventory", side_effect=AssertionError("Unrequested stock analysis")),
            patch.object(stock_desktop, "analyze_monthly_inventory", side_effect=AssertionError("Unrequested monthly analysis")),
            patch.object(stock_desktop, "load_inventory", side_effect=AssertionError("Source reread")),
        ):
            self.investigate()
            self.assertEqual(self.c.state["selection"], before)
            self.c.focusPerformanceProduct("OLD", "L")
            self.assertEqual(self.c.state["selection"], before)
        original = stock_desktop.analyze_inventory
        with patch.object(stock_desktop, "analyze_inventory", wraps=original) as analyze:
            self.c.focusPerformanceProduct("OLD", "KG")
            self.assertEqual(self.c.state["selection"]["product"], "OLD")
            self.assertEqual(self.c.state["selection"]["unit"], "KG")
            self.assertTrue(self.c._debounce.isActive())
            self.assertFalse(self.p.state["current"])
            self.idle()
        self.assertEqual(analyze.call_count, 1)
        self.assertEqual(self.c.state["count"], 0)
        self.assertEqual(self.c.monthly["product"], "OLD")
        self.assertTrue(self.c.monthly["series"]["sales"]["points"])
        self.assertTrue(self.c.state["current"])

    def test_investigation_and_back_preserve_stock_page_detail_month_and_comparison(self):
        self.load(performance_sample(70))
        self.c.setPage(2)
        self.c.selectRow(0)
        with (
            patch.object(stock_desktop, "analyze_inventory", side_effect=AssertionError("Unexpected reanalysis")),
            patch.object(stock_desktop, "analyze_monthly_inventory", side_effect=AssertionError("Unexpected history scan")),
        ):
            self.c.setMonthlyPeriod("2026-01")
            self.c.setMonthlyUnit("L")
            self.assertEqual(self.c.monthly["period"], "2026-01")
            self.assertEqual(self.c.monthly["unit"], "L")
            self.assertFalse(self.c.state["busy"])
            before = (
                self.c.table.rows, self.c.detail, self.c.monthly, self.c.comparison,
                self.c.comparisonState, self.c.state["selection"],
            )
            self.investigate()
            self.p.closeDetail()
            self.assertFalse(self.p.detail)
        self.assertEqual(self.c.state["page"], 2)
        self.assertEqual(self.c.state["selectedRow"], 0)
        self.assertEqual((
            self.c.table.rows, self.c.detail, self.c.monthly, self.c.comparison,
            self.c.comparisonState, self.c.state["selection"],
        ), before)
        self.assertTrue(self.p.state["current"])

    def test_excel_captures_complete_accepted_window_and_current_raw_detail(self):
        self.load(performance_sample(70))
        self.investigate()
        self.assertEqual(self.p.state["window"], 1)
        self.assertEqual(len(self.p.summary["rows"]), 10)
        captured = []

        def exported(*args, **kwargs):
            captured.append((args, kwargs, QThread.currentThread() == APP.thread()))

        from liarte_core.inventory_performance import analyze_product_performance

        calculated_windows = []

        def prepare_only_unopened_priorities(*args, **kwargs):
            # The accepted one-month performance report must be reused. The
            # unopened priorities view keeps its own three-month default.
            self.assertEqual(kwargs.get("window"), 3)
            calculated_windows.append(kwargs["window"])
            return analyze_product_performance(*args, **kwargs)

        with (
            patch.object(stock_desktop, "export_inventory", side_effect=exported),
            patch("liarte_core.inventory_performance.analyze_product_performance",
                  side_effect=prepare_only_unopened_priorities),
        ):
            self.c.exportExcel(QUrl.fromLocalFile(str(self.directory / "desempenho.xlsx")))
            self.idle()
        self.assertEqual(len(captured), 1)
        args, kwargs, on_gui = captured[0]
        self.assertFalse(on_gui)
        self.assertEqual(args[2], self.c._applied_selection)
        self.assertEqual(kwargs["performance"]["window"], 1)
        self.assertEqual(len(kwargs["performance"]["rows"]), 72)
        self.assertEqual(kwargs["performance_detail"]["row"]["code"], "OLD")
        self.assertEqual(kwargs["performance_detail"]["row"]["unit"], "KG")
        self.assertEqual(kwargs["priorities"]["window"], 3)
        self.assertEqual(calculated_windows, [3])

    def test_owner_shutdown_waits_for_pending_child_native_thread_and_emits_once(self):
        self.load()
        entered, release = Event(), Event()
        self.addCleanup(release.set)
        original = desktop.analyze_product_performance
        stopped = QSignalSpy(self.c.shutdownFinished)

        def delayed(*args, **kwargs):
            entered.set()
            if not release.wait(10):
                raise RuntimeError("Test did not release performance shutdown worker")
            return original(*args, **kwargs)

        try:
            with patch.object(desktop, "analyze_product_performance", side_effect=delayed):
                self.p.refresh()
                self.assertTrue(pump(entered.is_set))
                self.assertFalse(self.c.shutdown(wait_ms=0))
                self.assertEqual(stopped.count(), 0)
                self.assertIn(self.c, stock_desktop._SHUTTING_DOWN)
                release.set()
                self.assertTrue(pump(lambda: stopped.count() == 1, 15))
            self.assertIsNone(self.p._thread)
            self.assertNotIn(self.c, stock_desktop._SHUTTING_DOWN)
            self.assertTrue(self.c.shutdown(wait_ms=0))
            self.assertEqual(stopped.count(), 1)
        finally:
            release.set()
