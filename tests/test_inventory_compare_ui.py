"""Qt month comparisons reuse history and preserve the current stock session."""

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import patch

from PySide6.QtCore import QThread, QUrl

from liarte_core.inventory import SCALE, Closing, Sale
from liarte_core.inventory_io import write_snapshot
from liarte_desktop import inventory as desktop
from tests.test_audit_desktop import expanded
from tests.test_inventory import sample
from tests.test_inventory_monthly import monthly_sample
from tests.test_qt import APP, pump


def comparison_volume(count=70):
    data = expanded(count)
    return replace(
        data,
        closings=tuple(
            Closing(
                product.code, "01", "01", "UN", period,
                (index + step) * SCALE, (index + step) * 100, 1.0, 30.0,
            )
            for period, step in (("2026-01", 1), ("2026-03", 3))
            for index, product in enumerate(data.products)
        ),
        sales=tuple(
            Sale(product.code, "01", "UN", day, (index + step) * SCALE, 100)
            for day, step in ((data.sales[0].day, 1), (data.sales[0].day.replace(month=3), 3))
            for index, product in enumerate(data.products)
        ),
    )


class InventoryComparisonUiTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name).resolve()
        self.c = desktop.InventoryController()
        self.addCleanup(self.c.shutdown)
        self.source_count = 0

    def idle(self):
        self.assertTrue(
            pump(
                lambda: not self.c.state["busy"]
                and not self.c._debounce.isActive()
                and not self.c.comparisonState["busy"],
                15,
            ),
            (self.c.state, self.c.comparisonState),
        )

    def load(self, data=None):
        self.source_count += 1
        source = self.directory / f"source-{self.source_count}.liarte"
        write_snapshot(sample() if data is None else data, source)
        self.c.openFile(QUrl.fromLocalFile(str(source)))
        self.idle()
        self.assertTrue(self.c.state["loaded"], self.c.state["error"])
        self.assertTrue(self.c.comparisonState["current"], self.c.comparisonState)
        self.assertFalse(self.c.comparisonState["error"])

    def compare(self, base, target):
        self.c.setComparisonMonths(base, target)
        self.idle()
        self.assertTrue(self.c.comparisonState["current"], self.c.comparisonState)
        self.assertEqual((self.c.comparison["base"], self.c.comparison["target"]), (base, target))

    def metric(self, key):
        return next(item for item in self.c.comparison["metrics"] if item["key"] == key)

    def test_unloaded_controller_has_no_invented_comparison(self):
        self.assertFalse(self.c.comparisonState["available"])
        self.assertEqual(self.c.comparisonState["months"], [])
        self.c.setComparisonMonths("2026-01", "2026-03")
        self.assertFalse(self.c.state["busy"])
        self.assertFalse(self.c.comparisonState["available"])

    def test_default_uses_the_last_two_complete_closings_despite_gap_and_partial_month(self):
        data = sample()
        data = replace(data, closings=(*data.closings, Closing(
            "0001", "01", "01", "KG", "2026-04", 99 * SCALE, 9900, 1.0, 30.0,
        )))
        self.load(data)
        self.assertEqual(
            (self.c.comparison["base"], self.c.comparison["target"]),
            ("2026-01", "2026-03"),
        )
        periods = {item["value"] for item in self.c.comparisonState["months"]}
        self.assertEqual(periods, {"2026-01", "2026-02", "2026-03", "2026-04"})
        self.assertEqual(self.c._comparison_result["stock"]["before"], 17000)
        self.assertEqual(self.c._comparison_result["stock"]["after"], 16000)
        self.assertEqual(self.c._comparison_result["stock"]["change"], -1000)
        self.assertTrue(self.metric("stock")["available"])

    def test_comparison_runs_on_worker_without_reloading_and_preserves_page_detail_and_month(self):
        self.load(comparison_volume())
        self.c.setPage(2)
        self.c.selectRow(0)
        self.c.setMonthlyPeriod("2026-01")
        before_rows = self.c.table.rows
        before_detail = self.c.detail
        before_month = self.c.monthly
        before_selection = self.c.state["selection"]
        original = desktop.compare_inventory_months
        on_gui = []

        def observed(*args, **kwargs):
            on_gui.append(QThread.currentThread() == APP.thread())
            return original(*args, **kwargs)

        with (
            patch.object(desktop, "load_inventory", side_effect=AssertionError("Source reread")),
            patch.object(desktop, "analyze_inventory", side_effect=AssertionError("Stock reanalysis")),
            patch.object(
                desktop, "analyze_monthly_inventory", side_effect=AssertionError("History reanalysis")
            ),
            patch.object(desktop, "compare_inventory_months", side_effect=observed),
        ):
            self.compare("2026-03", "2026-01")
        self.assertEqual(on_gui, [False])
        self.assertEqual(self.c.state["page"], 2)
        self.assertEqual(self.c.state["selectedRow"], 0)
        self.assertEqual(self.c.table.rows, before_rows)
        self.assertEqual(self.c.detail, before_detail)
        self.assertEqual(self.c.monthly, before_month)
        self.assertEqual(self.c.state["selection"], before_selection)
        self.assertTrue(self.c.state["current"])

    def test_branch_metadata_is_read_by_the_worker_and_preserves_displayed_names(self):
        self.load()
        visits_on_gui = []

        class TrackedTuple(tuple):
            def __iter__(self):
                visits_on_gui.append(QThread.currentThread() == APP.thread())
                return super().__iter__()

        self.c._data = replace(
            self.c._data, branches=TrackedTuple(self.c._data.branches)
        )
        self.compare("2026-03", "2026-01")
        self.assertTrue(visits_on_gui)
        self.assertFalse(any(visits_on_gui), visits_on_gui)
        self.assertEqual(self.c._comparison_result["stock"]["change"], 1000)
        branch = next(row for row in self.metric("stock")["branches"] if row["key"] == "01")
        self.assertIn("Filial de teste", branch["name"])

    def test_missing_closing_and_observed_zero_sales_do_not_share_the_same_state(self):
        self.load()
        self.compare("2026-02", "2026-02")
        result = self.c._comparison_result
        self.assertFalse(result["stock"]["available"])
        self.assertIsNone(result["stock"]["before"])
        self.assertIsNone(result["stock"]["change"])
        self.assertTrue(result["salesByUnit"]["KG"]["available"])
        self.assertEqual(result["salesByUnit"]["KG"]["before"], 0)
        self.assertEqual(result["salesByUnit"]["KG"]["change"], 0)
        self.assertEqual(self.metric("stock")["before"], "—")

    def test_same_known_month_is_a_valid_zero_and_reversed_pair_changes_direction(self):
        self.load()
        self.compare("2026-01", "2026-01")
        self.assertEqual(self.c._comparison_result["stock"]["change"], 0)
        self.assertTrue(self.c._comparison_result["stock"]["available"])
        self.compare("2026-03", "2026-01")
        self.assertEqual(self.c._comparison_result["stock"]["change"], 1000)
        self.assertEqual(self.c._comparison_result["salesByUnit"]["KG"]["change"], -20 * SCALE)

    def test_invalid_months_do_not_replace_last_result_or_mutate_stock_filters(self):
        self.load()
        before = self.c.comparison
        selection = self.c.state["selection"]
        for base, target in (("", "2026-03"), ("bad", "2026-03"), ("2025-12", "2026-01")):
            with self.subTest(base=base, target=target):
                self.c.setComparisonMonths(base, target)
                self.idle()
                self.assertEqual(self.c.comparison, before)
                self.assertEqual(self.c.state["selection"], selection)
                self.assertTrue(self.c.comparisonState["error"])
                self.assertTrue(self.c.state["current"])

    def test_unit_changes_remain_synchronous_without_recomputing_the_comparison(self):
        self.load()
        before_pair = (self.c.comparison["base"], self.c.comparison["target"])
        before_month = self.c.monthly["period"]
        with (
            patch.object(
                desktop, "compare_inventory_months", side_effect=AssertionError("Unit reanalysis")
            ),
            patch.object(desktop, "analyze_inventory", side_effect=AssertionError("Stock reanalysis")),
            patch.object(
                desktop, "analyze_monthly_inventory", side_effect=AssertionError("History reanalysis")
            ),
        ):
            self.c.setMonthlyUnit("L")
            self.assertEqual(self.c.monthly["unit"], "L")
            self.assertEqual(self.c.comparison["unit"], "L")
            self.assertEqual((self.c.comparison["base"], self.c.comparison["target"]), before_pair)
            self.assertEqual(self.c.monthly["period"], before_month)
            self.assertFalse(self.c.state["busy"])
            self.c.setMonthlyPeriod("2026-01")
            self.assertEqual(self.c.monthly["period"], "2026-01")
            self.assertEqual(self.c.comparison["unit"], "L")
        self.assertEqual(self.c._comparison_result["quantityByUnit"]["L"]["change"], 0)

    def test_cancellation_restores_the_applied_pair_without_touching_the_stock_session(self):
        self.load(comparison_volume())
        self.c.setPage(2)
        self.c.selectRow(0)
        self.c.setMonthlyPeriod("2026-01")
        before = self.c.comparison
        rows, detail, month = self.c.table.rows, self.c.detail, self.c.monthly
        entered, release = Event(), Event()
        original = desktop.compare_inventory_months

        def delayed(*args, **kwargs):
            entered.set()
            if not release.wait(5):
                raise RuntimeError("Test did not release comparison worker")
            return original(*args, **kwargs)

        try:
            with patch.object(desktop, "compare_inventory_months", side_effect=delayed):
                self.c.setComparisonMonths("2026-03", "2026-01")
                self.assertTrue(pump(entered.is_set))
                self.c.cancel()
                release.set()
                self.idle()
            self.assertEqual(self.c.comparison, before)
            self.assertTrue(self.c.comparisonState["current"])
            self.assertEqual(self.c.table.rows, rows)
            self.assertEqual(self.c.detail, detail)
            self.assertEqual(self.c.monthly, month)
            self.assertEqual(self.c.state["page"], 2)
            self.assertTrue(self.c.state["current"])
        finally:
            release.set()

    def test_latest_pair_wins_while_an_earlier_comparison_is_running(self):
        self.load()
        entered, release = Event(), Event()
        original = desktop.compare_inventory_months
        calls = []

        def delayed(months, base, target, **kwargs):
            calls.append((base, target))
            if len(calls) == 1:
                entered.set()
                if not release.wait(5):
                    raise RuntimeError("Test did not release comparison worker")
            return original(months, base, target, **kwargs)

        try:
            with patch.object(desktop, "compare_inventory_months", side_effect=delayed):
                self.c.setComparisonMonths("2026-03", "2026-01")
                self.assertTrue(pump(entered.is_set))
                self.c.setComparisonMonths("2026-01", "2026-01")
                release.set()
                self.idle()
            self.assertEqual(
                (self.c.comparison["base"], self.c.comparison["target"]),
                ("2026-01", "2026-01"),
            )
            self.assertTrue(self.c.comparisonState["current"])
            self.assertEqual(self.c._comparison_result["stock"]["change"], 0)
            self.assertEqual(calls[-1], ("2026-01", "2026-01"))
        finally:
            release.set()

    def test_comparison_state_notifies_qt_consumers_when_the_worker_becomes_idle(self):
        self.load()
        notifications = []
        self.c.comparisonChanged.connect(lambda: notifications.append(self.c.comparisonState))
        self.compare("2026-03", "2026-01")
        self.assertTrue(notifications)
        # A QML property binding only sees values captured on its notify signal;
        # reading the Python getter after the thread finishes is insufficient.
        self.assertFalse(notifications[-1]["busy"], notifications)
        self.assertTrue(notifications[-1]["current"], notifications)
        self.assertEqual(
            (notifications[-1]["base"], notifications[-1]["target"]),
            ("2026-03", "2026-01"),
        )

    def test_failed_comparison_keeps_analysis_and_can_retry_the_same_requested_pair(self):
        self.load()
        before = self.c.comparison
        rows = self.c.table.rows
        destination = self.directory / "preserved.xlsx"
        destination.write_bytes(b"previous export")
        with patch.object(desktop, "compare_inventory_months", side_effect=ValueError("Comparison failed")):
            self.c.setComparisonMonths("2026-03", "2026-01")
            self.idle()
        self.assertEqual(self.c.comparison, before)
        self.assertEqual(self.c.table.rows, rows)
        self.assertTrue(self.c.state["current"])
        self.assertEqual(self.c.state["error"], "")
        self.assertFalse(self.c.comparisonState["current"])
        self.assertTrue(self.c.comparisonState["error"])
        with patch.object(desktop, "export_inventory", side_effect=AssertionError("Stale export")):
            self.c.exportExcel(QUrl.fromLocalFile(str(destination)))
            self.idle()
        self.assertEqual(destination.read_bytes(), b"previous export")
        self.compare("2026-03", "2026-01")
        self.assertEqual(self.c.comparisonState["error"], "")

    def test_stock_filter_preserves_a_still_valid_comparison_pair(self):
        self.load()
        self.compare("2026-03", "2026-01")
        self.c.setFilter("unit", "KG")
        self.idle()
        self.assertEqual(self.c.state["selection"]["unit"], "KG")
        self.assertEqual(
            (self.c.comparison["base"], self.c.comparison["target"]),
            ("2026-03", "2026-01"),
        )
        self.assertTrue(self.c.comparisonState["current"])
        self.assertEqual(self.c._comparison_result["stock"]["change"], 2000)

    def test_comparison_request_cannot_interrupt_loading_a_base(self):
        source = self.directory / "delayed-source.liarte"
        write_snapshot(sample(), source)
        entered, release = Event(), Event()
        original = desktop.load_inventory

        def delayed(*args, **kwargs):
            entered.set()
            if not release.wait(5):
                raise RuntimeError("Test did not release source worker")
            return original(*args, **kwargs)

        try:
            with patch.object(desktop, "load_inventory", side_effect=delayed):
                self.c.openFile(QUrl.fromLocalFile(str(source)))
                self.assertTrue(pump(entered.is_set))
                self.c.setComparisonMonths("2026-03", "2026-01")
                release.set()
                self.idle()
            self.assertTrue(self.c.state["loaded"], self.c.state["error"])
            self.assertEqual(
                (self.c.comparison["base"], self.c.comparison["target"]),
                ("2026-01", "2026-03"),
            )
        finally:
            release.set()

    def test_comparison_request_cannot_replace_the_pair_used_by_a_running_export(self):
        self.load()
        applied = self.c._comparison_result
        entered, release = Event(), Event()
        captured = []

        def delayed(data, analysis, selected, path, cancel, **kwargs):
            captured.append(kwargs["comparison"])
            entered.set()
            if not release.wait(5):
                raise RuntimeError("Test did not release Excel worker")

        try:
            with patch.object(desktop, "export_inventory", side_effect=delayed):
                self.c.exportExcel(QUrl.fromLocalFile(str(self.directory / "export.xlsx")))
                self.assertTrue(pump(entered.is_set))
                self.c.setComparisonMonths("2026-03", "2026-01")
                release.set()
                self.idle()
            self.assertEqual(captured, [applied])
            self.assertEqual(
                (self.c.comparison["base"], self.c.comparison["target"]),
                ("2026-01", "2026-03"),
            )
            self.assertTrue(self.c.comparisonState["current"])
        finally:
            release.set()

    def test_new_base_chooses_its_own_complete_months(self):
        self.load()
        self.compare("2026-03", "2026-01")
        self.load(monthly_sample())
        self.assertEqual(
            (self.c.comparison["base"], self.c.comparison["target"]),
            ("2026-01", "2026-02"),
        )

    def test_historical_product_focus_does_not_require_current_balance(self):
        self.load(monthly_sample())
        self.assertIn("C", {row["key"] for row in self.metric("stock")["products"]})
        self.c.focusComparison("product", "C")
        self.idle()
        self.assertEqual(self.c.state["selection"]["product"], "C")
        self.assertEqual(self.c.state["count"], 0)
        self.assertEqual(
            (self.c.comparison["base"], self.c.comparison["target"]),
            ("2026-01", "2026-02"),
        )
        self.assertEqual(self.c._comparison_result["stock"]["before"], 1000)
        self.assertIsNone(self.c._comparison_result["stock"]["after"])

    def test_sales_only_branch_focus_and_invalid_targets_preserve_historical_scope(self):
        self.load(monthly_sample())
        before = self.c.state["selection"]
        for dimension, key in (("unsupported", "C"), ("product", "not a product"), ("branch", "99")):
            with self.subTest(dimension=dimension, key=key):
                self.c.focusComparison(dimension, key)
                self.assertEqual(self.c.state["selection"], before)
        self.c.focusComparison("branch", "03")
        self.idle()
        self.assertEqual(self.c.state["selection"]["branch"], "03")
        self.assertEqual(self.c.state["count"], 0)
        self.assertEqual(self.c._comparison_result["salesByUnit"]["KG"]["change"], 200 * SCALE)

    def test_presentation_is_bounded_but_export_receives_the_complete_applied_result(self):
        self.load(comparison_volume())
        self.assertEqual(len(self.c._comparison_result["stock"]["products"]), 70)
        self.assertEqual(len(self.metric("stock")["products"]), 8)
        self.compare("2026-03", "2026-01")
        applied = self.c._comparison_result
        destination = self.directory / "comparison.xlsx"
        captured = []

        def exported(data, analysis, selected, path, cancel, **kwargs):
            captured.append(kwargs["comparison"])

        with patch.object(desktop, "export_inventory", side_effect=exported):
            self.c.exportExcel(QUrl.fromLocalFile(str(destination)))
            self.idle()
        self.assertEqual(captured, [applied])
        self.assertEqual(captured[0]["base"], "2026-03")
        self.assertEqual(len(captured[0]["stock"]["products"]), 70)
