"""Monthly comparisons remain usable in the actual Qt inventory workspace."""

from dataclasses import replace
from datetime import date
import unittest
from unittest.mock import patch

from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QSignalSpy, QTest

from liarte_core.inventory import SCALE, Closing, Sale
from liarte_core.inventory_io import write_snapshot
from tests import test_inventory
from tests import test_inventory_alerts_qml as alert_tests
from tests.test_inventory_monthly import monthly_sample
from tests.test_qt import pump


def variant(value):
    return value.toVariant() if hasattr(value, "toVariant") else value


def comparison_sample():
    data = monthly_sample()
    return replace(
        data,
        closings=(
            *data.closings,
            Closing("A", "01", "01", "KG", "2026-03", 80 * SCALE, 8000, 2, 15),
            Closing("A", "01", "02", "KG", "2026-03", 50 * SCALE, 5000, 2, 15),
            Closing("B", "01", "01", "L", "2026-03", 30 * SCALE, 3000, 2, 15),
            Closing("C", "01", "01", "KG", "2026-03", 20 * SCALE, 3000, 2, 15),
            Closing("A", "01", "01", "KG", "2026-04", 100 * SCALE, 10000, 2, 15),
        ),
        sales=(
            *data.sales,
            Sale("B", "01", "L", date(2026, 3, 1), 9 * SCALE, 900),
            Sale("C", "01", "KG", date(2026, 3, 2), 2 * SCALE, 200),
            Sale("D", "03", "KG", date(2026, 3, 6), 300 * SCALE, 30000),
            Sale("A", "01", "KG", date(2026, 4, 1), 10 * SCALE, 1000),
        ),
    )


class InventoryComparisonQmlTests(unittest.TestCase):
    tearDown = test_inventory.InventoryUiTests.tearDown
    load = test_inventory.InventoryUiTests.load
    item = alert_tests.InventoryAlertQmlTests.item
    reveal = alert_tests.InventoryAlertQmlTests.reveal
    workspace_geometry = alert_tests.InventoryAlertQmlTests.workspace_geometry
    click_workspace = alert_tests.InventoryAlertQmlTests.click_workspace

    def setUp(self):
        test_inventory.InventoryUiTests.setUp(self)
        self.bundle.preferences.setPreference("reducedMotion", True)
        write_snapshot(comparison_sample(), self.base)

    def idle(self):
        self.assertTrue(pump(
            lambda: not self.c.state["busy"]
            and not self.c._debounce.isActive()
            and not self.c.comparisonState["busy"],
            15,
        ), (self.c.state, self.c.comparisonState))

    def open_comparison(self):
        comparison = self.item("stockComparison")
        if not comparison.property("expanded"):
            self.click_workspace(self.item("stockCompareToggle"))
            self.assertTrue(pump(lambda: comparison.property("expanded")))
        return comparison

    def select_combo(self, name, value):
        control = self.item(name)
        options = variant(control.property("model"))
        index = next(i for i, option in enumerate(options) if option["value"] == value)
        self.reveal(control)
        previous = None

        def ready():
            nonlocal previous
            self.reveal(control)
            frame = self.window.grabWindow()
            geometry = self.workspace_geometry(control)
            stable = previous == geometry
            previous = geometry
            x, y, width, height = geometry["control"]
            viewport_width, viewport_height = geometry["viewport"]
            return (
                stable and not frame.isNull() and geometry["enabled"]
                and geometry["visible"] and not geometry["moving"]
                and x >= -1 and y >= -1
                and x + width <= viewport_width + 1
                and y + height <= viewport_height + 1
            )

        self.assertTrue(pump(ready), self.workspace_geometry(control))
        if variant(control.property("currentValue")) == value:
            return
        activations = QSignalSpy(control.activated)
        control.forceActiveFocus(Qt.FocusReason.TabFocusReason)
        QTest.keyClick(self.window, Qt.Key.Key_Home)
        for _ in range(index):
            QTest.keyClick(self.window, Qt.Key.Key_Down)
        self.assertTrue(pump(
            lambda: variant(control.property("currentValue")) == value
        ), (name, value, variant(control.property("currentValue"))))
        self.assertGreater(activations.count(), 0, name)
        self.assertFalse(self.window.grabWindow().isNull())

    def compare(self, base="2026-01", target="2026-03"):
        self.open_comparison()
        self.select_combo("stockCompareBase", base)
        self.select_combo("stockCompareTarget", target)
        self.click_workspace(self.item("stockCompareApply"))
        self.idle()
        self.assertEqual((self.c.comparison["base"], self.c.comparison["target"]), (base, target))
        self.assertTrue(self.c.comparisonState["current"])

    def active_metric(self):
        return variant(self.item("stockComparison").property("activeMetric"))

    def row_for(self, key):
        rows = variant(self.item("stockComparison").property("rows"))
        index = next(index for index, row in enumerate(rows) if row["key"] == key)
        return self.item("stockCompareRow" + str(index))

    def visible_in_scroll(self, control):
        viewport = self.item("stockScroll")
        point = control.mapToItem(viewport, QPointF())
        return (
            point.x() >= -1 and point.y() >= -1
            and point.x() + control.width() <= viewport.width() + 1
            and point.y() + control.height() <= viewport.height() + 1
        )

    def test_drafts_and_swap_apply_nonconsecutive_months_without_reloading_analysis(self):
        self.load()
        self.assertFalse(self.item("stockComparison").property("expanded"))
        self.c.selectRow(0)
        original = (self.c.table.rows, self.c.detail, self.c.monthly["period"])
        applied = (self.c.comparison["base"], self.c.comparison["target"])
        analyses = QSignalSpy(self.c.analysisChanged)
        self.open_comparison()
        self.select_combo("stockCompareBase", "2026-01")
        self.select_combo("stockCompareTarget", "2026-03")
        self.assertEqual((self.c.comparison["base"], self.c.comparison["target"]), applied)
        with patch.object(self.bundle.controller._provider, "query") as query:
            self.click_workspace(self.item("stockCompareApply"))
            self.idle()
            query.assert_not_called()
        self.assertEqual((self.c.comparison["base"], self.c.comparison["target"]), ("2026-01", "2026-03"))
        self.assertIn("180,00", self.item("stockCompareSummary0Value").property("text"))
        self.assertIn("190,00", self.item("stockCompareSummary1Value").property("text"))
        self.assertIn("+R$ 10,00", self.item("stockCompareSummary2Value").property("text"))
        self.click_workspace(self.item("stockCompareSwap"))
        self.assertEqual((self.c.comparison["base"], self.c.comparison["target"]), ("2026-01", "2026-03"))
        self.click_workspace(self.item("stockCompareApply"))
        self.idle()
        self.assertEqual((self.c.comparison["base"], self.c.comparison["target"]), ("2026-03", "2026-01"))
        self.assertIn("−R$ 10,00", self.item("stockCompareSummary2Value").property("text"))
        self.assertEqual((self.c.table.rows, self.c.detail, self.c.monthly["period"]), original)
        self.assertEqual(analyses.count(), 0)
        self.assertEqual(self.bundle.messages, [])

    def test_indicator_and_unit_changes_preserve_the_pair_and_known_zero_sales(self):
        self.load()
        self.compare()
        analyses = QSignalSpy(self.c.analysisChanged)
        self.select_combo("stockMonthlyUnit", "KG")
        self.select_combo("stockCompareMetric", "quantity")
        self.assertIn("160,000 KG", self.item("stockCompareSummary0Value").property("text"))
        self.assertIn("150,000 KG", self.item("stockCompareSummary1Value").property("text"))
        self.assertIn("−10,000 KG", self.item("stockCompareSummary2Value").property("text"))
        self.select_combo("stockMonthlyUnit", "L")
        self.assertIn("20,000 L", self.item("stockCompareSummary0Value").property("text"))
        self.assertIn("30,000 L", self.item("stockCompareSummary1Value").property("text"))
        self.select_combo("stockCompareMetric", "sales")
        self.assertIn("+5,000 L", self.item("stockCompareSummary2Value").property("text"))
        self.select_combo("stockMonthlyUnit", "UN")
        self.assertTrue(self.active_metric()["available"])
        self.assertIn("0,000 UN", self.item("stockCompareSummary0Value").property("text"))
        self.assertIn("0,000 UN", self.item("stockCompareSummary2Value").property("text"))
        self.assertEqual((self.c.comparison["base"], self.c.comparison["target"]), ("2026-01", "2026-03"))
        self.assertEqual(analyses.count(), 0)
        self.assertEqual(self.bundle.messages, [])

    def test_historical_product_contribution_keeps_months_and_monthly_workspace(self):
        self.load()
        self.compare()
        with patch.object(self.bundle.controller._provider, "query") as query:
            self.click_workspace(self.row_for("C"))
            self.idle()
            query.assert_not_called()
        self.assertEqual(self.c.state["selection"]["product"], "C")
        self.assertEqual(self.c.state["count"], 0)
        self.assertEqual(self.c.monthly["product"], "C")
        self.assertEqual((self.c.comparison["base"], self.c.comparison["target"]), ("2026-01", "2026-03"))
        self.assertTrue(self.active_metric()["available"])
        self.assertIn("+R$ 20,00", self.item("stockCompareSummary2Value").property("text"))
        self.assertTrue(pump(lambda: self.item("inventoryWorkspace").property("activeSection") == "monthly"))
        self.assertEqual(self.bundle.messages, [])

    def test_branch_contribution_can_investigate_sales_without_current_stock(self):
        self.load()
        self.compare()
        self.select_combo("stockMonthlyUnit", "KG")
        self.select_combo("stockCompareMetric", "sales")
        self.select_combo("stockCompareDimension", "branch")
        self.click_workspace(self.row_for("03"))
        self.idle()
        self.assertEqual(self.c.state["selection"]["branch"], "03")
        self.assertEqual(self.c.state["count"], 0)
        self.assertEqual((self.c.comparison["base"], self.c.comparison["target"]), ("2026-01", "2026-03"))
        self.assertTrue(self.active_metric()["available"])
        self.assertIn("+300,000 KG", self.item("stockCompareSummary2Value").property("text"))
        self.assertTrue(pump(lambda: self.item("inventoryWorkspace").property("activeSection") == "monthly"))
        self.assertEqual(self.bundle.messages, [])

    def test_partial_month_and_warehouse_sales_remain_explicitly_unavailable(self):
        self.load()
        self.compare(target="2026-04")
        self.assertFalse(self.active_metric()["available"])
        self.assertEqual(self.item("stockCompareSummary2Value").property("text"), "—")
        self.assertIn("parcial", self.item("stockCompareReason").property("text"))
        self.select_combo("stockCompareMetric", "sales")
        self.assertFalse(self.active_metric()["available"])
        self.assertFalse(self.item("stockCompareEmpty").isVisible())
        self.compare()
        self.c.setFilter("warehouse", "01")
        self.idle()
        self.assertEqual((self.c.comparison["base"], self.c.comparison["target"]), ("2026-01", "2026-03"))
        self.assertFalse(self.active_metric()["available"])
        self.assertIn("armazém", self.item("stockCompareReason").property("text"))
        self.assertEqual(self.bundle.messages, [])

    def test_new_base_syncs_untouched_month_drafts_and_preserves_user_edits(self):
        self.load()
        comparison = self.open_comparison()
        original = comparison_sample()
        complete = replace(original, as_of=date(2026, 4, 30))

        def assert_drafts(base, target):
            self.assertTrue(pump(lambda: (
                comparison.property("draftBase"), comparison.property("draftTarget"),
                variant(self.item("stockCompareBase").property("currentValue")),
                variant(self.item("stockCompareTarget").property("currentValue")),
            ) == (base, target, base, target)), (base, target, self.c.comparisonState))

        self.assertEqual((self.c.comparison["base"], self.c.comparison["target"]), ("2026-02", "2026-03"))
        assert_drafts("2026-02", "2026-03")
        write_snapshot(complete, self.base)
        self.load()
        self.assertEqual((self.c.comparison["base"], self.c.comparison["target"]), ("2026-03", "2026-04"))
        assert_drafts("2026-03", "2026-04")

        self.select_combo("stockCompareBase", "2026-01")
        self.select_combo("stockCompareTarget", "2026-03")
        write_snapshot(original, self.base)
        self.load()
        self.assertEqual((self.c.comparison["base"], self.c.comparison["target"]), ("2026-02", "2026-03"))
        assert_drafts("2026-01", "2026-03")

        # Equal choices are a normal intermediate state while editing the pair.
        # A publication must not replace one of them before the user finishes.
        self.select_combo("stockCompareBase", "2026-03")
        self.assertFalse(self.item("stockCompareApply").isEnabled())
        write_snapshot(complete, self.base)
        self.load()
        self.assertEqual((self.c.comparison["base"], self.c.comparison["target"]), ("2026-03", "2026-04"))
        assert_drafts("2026-03", "2026-03")
        self.assertFalse(self.item("stockCompareApply").isEnabled())
        self.assertEqual(self.bundle.messages, [])

    def test_failed_comparison_can_be_retried_by_the_same_real_apply_button(self):
        self.load()
        previous = (self.c.comparison["base"], self.c.comparison["target"])
        self.open_comparison()
        self.select_combo("stockCompareBase", "2026-01")
        self.select_combo("stockCompareTarget", "2026-03")
        with (
            patch("liarte_desktop.inventory.compare_inventory_months", side_effect=ValueError("Falha sintética de comparação")),
            self.assertLogs("liarte.desktop", level="ERROR"),
        ):
            self.click_workspace(self.item("stockCompareApply"))
            self.idle()
        self.assertFalse(self.c.comparisonState["current"])
        self.assertTrue(self.c.state["current"])
        self.assertEqual(self.c.state["error"], "")
        self.assertEqual((self.c.comparison["base"], self.c.comparison["target"]), previous)
        self.assertIn("Falha sintética", self.item("stockCompareStatus").property("text"))
        self.assertTrue(self.item("stockCompareApply").isEnabled())
        self.click_workspace(self.item("stockCompareApply"))
        self.idle()
        self.assertTrue(self.c.comparisonState["current"])
        self.assertEqual(self.c.comparisonState["error"], "")
        self.assertEqual((self.c.comparison["base"], self.c.comparison["target"]), ("2026-01", "2026-03"))
        self.assertEqual(self.bundle.messages, [])

    def test_compact_wide_controls_fit_and_tab_reveals_the_comparison_inputs(self):
        self.load()
        for name in (
            "stockCompareToggle", "stockCompareBase", "stockCompareTarget",
            "stockCompareSwap", "stockCompareApply", "stockCompareMetric", "stockCompareDimension",
        ):
            control = self.item(name)
            font = control.property("font")
            font.setStretch(200)
            control.setProperty("font", font)
        self.window.resize(500, 400)
        self.assertTrue(pump(lambda: abs(self.window.contentItem().width() - 500) < 1))
        comparison = self.open_comparison()
        self.assertFalse(self.window.grabWindow().isNull())
        for name in (
            "stockCompareBase", "stockCompareTarget", "stockCompareSwap", "stockCompareApply",
            "stockCompareMetric", "stockCompareDimension", "stockCompareSummaries", "stockCompareRows",
        ):
            control = self.item(name)
            point = control.mapToItem(comparison, QPointF())
            self.assertGreaterEqual(point.x(), -1, name)
            self.assertLessEqual(point.x() + control.width(), comparison.width() + 1, name)
        base = self.item("stockCompareBase")
        self.reveal(base)
        base.forceActiveFocus(Qt.FocusReason.TabFocusReason)
        self.assertTrue(pump(lambda: self.visible_in_scroll(base)))
        for name in (
            "stockCompareTarget", "stockCompareSwap", "stockCompareApply",
            "stockCompareMetric", "stockCompareDimension",
        ):
            QTest.keyClick(self.window, Qt.Key.Key_Tab)
            control = self.item(name)
            self.assertTrue(pump(control.hasActiveFocus), name)
            self.assertTrue(
                pump(lambda: self.visible_in_scroll(control)),
                self.workspace_geometry(control),
            )
        QTest.keyClick(self.window, Qt.Key.Key_Backtab)
        metric = self.item("stockCompareMetric")
        self.assertTrue(pump(metric.hasActiveFocus))
        self.assertTrue(pump(lambda: self.visible_in_scroll(metric)))
        # A focused comparison control also stays reachable when the layout
        # changes around it, without another Tab press or a manual scroll.
        for width, height in ((760, 500), (500, 400)):
            self.window.resize(width, height)
            self.assertTrue(pump(lambda: abs(self.window.contentItem().width() - width) < 1))
            self.assertFalse(self.window.grabWindow().isNull())
            self.assertTrue(pump(metric.hasActiveFocus))
            self.assertTrue(pump(lambda: self.visible_in_scroll(metric)))
        self.assertEqual(self.bundle.messages, [])
