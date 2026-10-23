"""Monthly exploration preserves source scope and the current stock session."""

from dataclasses import replace
from datetime import date
import unittest
from unittest.mock import patch

from PySide6.QtCore import QMetaObject, QObject, QPointF, Qt
from PySide6.QtTest import QSignalSpy, QTest

from liarte_core.inventory import SCALE, Closing, Product, Sale
from liarte_core.inventory_io import write_snapshot
from tests import test_inventory as inventory_tests
from tests.test_qt import APP, click, pump


def variant(value):
    return value.toVariant() if hasattr(value, "toVariant") else value


class InventoryMonthlyUiTests(unittest.TestCase):
    setUp = inventory_tests.InventoryUiTests.setUp
    tearDown = inventory_tests.InventoryUiTests.tearDown
    idle = inventory_tests.InventoryUiTests.idle
    load = inventory_tests.InventoryUiTests.load

    def item(self, name):
        def visual(item):
            if item.objectName() == name:
                return item
            for child in item.childItems():
                found = visual(child)
                if found is not None:
                    return found
            return None

        result = self.window.findChild(QObject, name)
        if result is None:
            result = visual(self.window.contentItem())
        self.assertIsNotNone(result, name)
        return result

    def reveal(self, item):
        scroll = self.item("stockScroll")
        point = item.mapToItem(scroll, QPointF())
        target = scroll.property("contentY") + point.y() - 90
        maximum = max(0, scroll.property("contentHeight") - scroll.height())
        scroll.setProperty("contentY", max(0, min(maximum, target)))
        APP.processEvents()

    def test_focus_changes_month_and_unit_without_reanalysis_or_network(self):
        self.load()
        original = self.c.table.rows
        selected = self.c.state["selection"]
        self.assertEqual(self.c.monthly["period"], "2026-03")
        analyses = QSignalSpy(self.c.analysisChanged)
        with patch.object(self.bundle.controller._provider, "query") as query:
            self.c.setMonthlyPeriod("2026-02")
            self.c.setMonthlyUnit("KG")
            self.assertEqual(self.c.monthly["period"], "2026-02")
            self.assertEqual(self.c.monthly["unit"], "KG")
            self.assertEqual(self.c.monthly["metrics"][0]["value"], "—")
            query.assert_not_called()
        self.assertEqual(analyses.count(), 0)
        self.assertEqual(self.c.table.rows, original)
        self.assertEqual(self.c.state["selection"], selected)
        self.assertEqual(self.bundle.messages, [])

    def test_historical_branch_and_unit_options_do_not_depend_on_current_positions(self):
        data = inventory_tests.sample()
        data = replace(
            data,
            products=(*data.products, Product("OLD", "Produto histórico", "G", "PA", "M2")),
            closings=(
                *data.closings,
                Closing("OLD", "03", "99", "M2", "2026-03", 7 * SCALE, 900, 1.5, 20),
            ),
            sales=(*data.sales, Sale("OLD", "03", "M2", date(2026, 3, 2), 3 * SCALE, 100)),
        )
        write_snapshot(data, self.base)
        self.load()
        options = {o["key"]: {v["value"] for v in o["values"]} for o in self.c.options}
        self.assertIn("03", options["branch"])
        self.assertIn("99", options["warehouse"])
        self.assertIn("M2", options["unit"])
        self.c.setFilter("branch", "03")
        self.idle()
        self.c.setMonthlyUnit("M2")
        self.assertEqual(self.c.state["count"], 0)
        self.assertEqual(self.c.monthly["metrics"][0]["value"], "R$ 9,00")
        self.assertEqual(self.c.monthly["sellers"][0]["code"], "OLD")
        self.assertEqual(self.bundle.messages, [])

    def test_monthly_product_selection_preserves_focus_and_shows_monthly_series(self):
        self.load()
        self.c.setMonthlyPeriod("2026-01")
        self.c.setMonthlyUnit("KG")
        APP.processEvents()
        row = self.item("stockMonthlyRow0")
        self.reveal(row)
        click(self.window, row)
        self.idle()
        self.assertEqual(self.c.state["selection"]["product"], "0001")
        self.assertEqual(self.c.monthly["period"], "2026-01")
        self.c.selectRow(0)
        self.assertEqual(self.c.detail["stockQuantityTrend"][0]["value"], 80)
        self.assertIsNone(self.c.detail["stockQuantityTrend"][1]["value"])
        self.assertEqual(self.c.detail["stockCostTrend"][2]["value"], 60)
        clear = self.item("stockMonthlyClearProduct")
        self.reveal(clear)
        click(self.window, clear)
        self.idle()
        self.assertEqual(self.c.monthly["period"], "2026-01")
        self.assertEqual(self.c.monthly["product"], "")
        self.assertEqual(self.bundle.messages, [])

    def test_monthly_layout_signed_rows_and_expansion_fit_compact_and_wide_windows(self):
        data = inventory_tests.sample()
        data = replace(
            data,
            closings=(
                *data.closings,
                Closing("0001", "01", "01", "KG", "2026-02", 90 * SCALE, 9000, 2, 15),
            ),
        )
        write_snapshot(data, self.base)
        self.load()
        section = self.item("stockMonthly")
        section.setProperty("rankingKey", "changes")
        APP.processEvents()
        self.assertEqual(self.item("stockMonthlyRow0Value").property("text"), "−R$ 30,00")
        for width in (500, 760, 1380):
            with self.subTest(width=width):
                self.window.resize(width, 900)
                APP.processEvents()
                for child_name, parent_name in (
                    ("stockMonthlyPlot", "stockMonthlyChartCard"),
                    ("stockMonthlyRows", "stockMonthlyRankingCard"),
                ):
                    child, parent = self.item(child_name), self.item(parent_name)
                    point = child.mapToItem(parent, QPointF())
                    self.assertGreaterEqual(point.x(), -1)
                    self.assertGreaterEqual(point.y(), -1)
                    self.assertLessEqual(point.x() + child.width(), parent.width() + 1)
                    self.assertLessEqual(point.y() + child.height(), parent.height() + 1)
                self.assertFalse(self.window.grabWindow().isNull())
        section.setProperty("metricKey", "sales")
        APP.processEvents()
        points = variant(self.item("stockMonthlyPlot").property("points"))
        QMetaObject.invokeMethod(self.item("stockMonthlyChartDialog"), "open")
        self.assertTrue(pump(lambda: self.item("stockMonthlyChartDialog").property("opened")))
        self.assertTrue(self.item("inventoryWorkspace").property("modalOpen"))
        self.assertEqual(
            variant(self.item("stockMonthlyChartDialogPlot").property("points")), points
        )
        QTest.keyClick(self.window, Qt.Key.Key_Escape)
        self.assertTrue(pump(lambda: not self.item("stockMonthlyChartDialog").property("visible")))
        self.assertEqual(self.bundle.messages, [])

    def test_pending_filter_cannot_change_the_focus_of_previous_results(self):
        self.load()
        before = self.c.monthly
        self.c.setFilter("unit", "KG")
        self.c.setMonthlyPeriod("2026-01")
        self.c.setMonthlyUnit("L")
        self.assertEqual(self.c.monthly, before)
        self.c.cancel()
        self.idle()
        self.assertEqual(self.c.monthly, before)
        self.assertEqual(self.bundle.messages, [])
