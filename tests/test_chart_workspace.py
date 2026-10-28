"""Os painéis se reorganizam e ampliam os dados sem nova consulta."""

import unittest

from PySide6.QtCore import Q_ARG, QMetaObject, QPointF, Qt
from PySide6.QtTest import QTest

from tests import test_home_indicators as home_tests
from tests.test_qt import click, pump


class ChartWorkspaceTests(unittest.TestCase):
    setUp = home_tests.HomeIndicatorsTests.setUp
    tearDown = home_tests.HomeIndicatorsTests.tearDown
    item = home_tests.HomeIndicatorsTests.item
    load = home_tests.HomeIndicatorsTests.load
    load_inventory = home_tests.HomeIndicatorsTests.load_inventory
    inventory_idle = home_tests.HomeIndicatorsTests.inventory_idle
    render = home_tests.HomeIndicatorsTests.render

    def show_import_visual(self, visual):
        workspace = self.item("importsWorkspace")
        QMetaObject.invokeMethod(workspace, "navigate", Qt.ConnectionType.DirectConnection,
                                 Q_ARG("QVariant", "summary"))
        workspace.setProperty("primaryVisual", visual)
        self.render()

    def show_stock_visual(self, visual):
        choice = self.item("stockOverviewMeasure")
        choice.setProperty("currentIndex", 0 if visual == "history" else 1)
        self.render()

    def inside(self, child, parent):
        point = child.mapToItem(parent, QPointF())
        self.assertGreaterEqual(point.x(), -1)
        self.assertGreaterEqual(point.y(), -1)
        self.assertLessEqual(point.x() + child.width(), parent.width() + 1)
        self.assertLessEqual(point.y() + child.height(), parent.height() + 1)

    def reveal_and_click(self, item, scroll):
        y = item.mapToScene(QPointF()).y()
        target = scroll.property("contentY") + y - self.window.height() / 2
        maximum = max(0, scroll.property("contentHeight") - scroll.height())
        scroll.setProperty("contentY", max(0, min(maximum, target)))
        self.render()
        click(self.window, item)

    def test_import_panels_fit_after_resizing_without_changing_data_or_requerying(self):
        self.load()
        self.platform.openModule("imports")
        self.controller.setPreference("reducedMotion", True)
        original = self.controller.table.rows
        calls = list(self.transport.calls)
        for width in (500, 760, 1120, 1380):
            with self.subTest(width=width):
                self.window.resize(width, 900)
                self.show_import_visual("trend")
                chart, panel = self.item("monthlyChart"), self.item("trendPanel")
                self.assertTrue(panel.isVisible())
                self.assertFalse(self.item("originsPanel").isVisible())
                self.assertGreaterEqual(chart.height(), 220)
                self.inside(chart, panel)
                self.inside(self.item("trendReadout"), panel)
                self.inside(self.item("openTrendChart"), panel)
                self.show_import_visual("origins")
                self.assertTrue(self.item("originsPanel").isVisible())
                self.assertFalse(panel.isVisible())
                self.inside(self.item("originChart"), self.item("originsPanel"))
        self.assertEqual(self.controller.table.rows, original)
        self.assertEqual(self.transport.calls, calls)
        self.assertEqual(self.bundle.messages, [])

    def test_import_chart_opens_with_same_points_and_resizes_without_an_api_call(self):
        self.load()
        self.platform.openModule("imports")
        calls = list(self.transport.calls)
        points = home_tests.variant(self.item("monthlyChart").property("points"))
        self.reveal_and_click(self.item("openTrendChart"), self.item("contentScroll"))
        dialog = self.item("importChartDialog")
        self.assertTrue(pump(lambda: dialog.property("opened")))
        chart = self.item("importChartDialogPlot")
        self.assertEqual(home_tests.variant(chart.property("points")), points)
        for width, height in ((500, 400), (1380, 900)):
            self.window.resize(width, height)
            self.render()
            self.assertLessEqual(dialog.property("width"), width)
            self.assertLessEqual(dialog.property("height"), height)
            self.assertGreater(chart.width(), 200)
        QTest.keyClick(self.window, Qt.Key.Key_Escape)
        self.assertTrue(pump(lambda: not dialog.property("visible")))
        self.assertEqual(self.transport.calls, calls)
        self.assertEqual(self.bundle.messages, [])

    def test_stock_panels_fit_ranking_and_legends_without_changing_the_selection(self):
        self.load_inventory()
        self.platform.openModule("inventory")
        selected = self.inventory.state["selection"]
        for width in (500, 760, 1120, 1380):
            with self.subTest(width=width):
                self.window.resize(width, 900)
                self.show_stock_visual("history")
                self.assertTrue(self.item("stockHistoryCard").isVisible())
                self.assertFalse(self.item("stockCapitalCard").isVisible())
                self.inside(self.item("stockTrend"), self.item("stockHistoryCard"))
                self.assertGreaterEqual(self.item("stockTrend").height(), 220)
                self.inside(self.item("stockTrendReadout"), self.item("stockHistoryCard"))
                self.inside(self.item("openStockChart"), self.item("stockHistoryCard"))
                self.show_stock_visual("capital")
                self.assertTrue(self.item("stockCapitalCard").isVisible())
                self.assertFalse(self.item("stockHistoryCard").isVisible())
                self.inside(self.item("stockRanking"), self.item("stockCapitalCard"))
        self.assertEqual(self.inventory.state["selection"], selected)
        self.assertEqual(self.bundle.messages, [])

    def test_expanded_stock_chart_preserves_mode_average_points_and_filter(self):
        self.load_inventory()
        self.platform.openModule("inventory")
        points = home_tests.variant(self.item("stockTrend").property("points"))
        selected = self.inventory.state["selection"]
        self.item("stockTrend").setProperty("mode", "column")
        self.item("stockTrend").setProperty("movingAverage", False)
        self.reveal_and_click(self.item("openStockChart"), self.item("stockScroll"))
        dialog = self.item("stockChartDialog")
        self.assertTrue(pump(lambda: dialog.property("opened")))
        chart = self.item("stockChartDialogPlot")
        self.assertEqual(home_tests.variant(chart.property("points")), points)
        self.assertEqual(chart.property("mode"), "column")
        self.assertFalse(chart.property("movingAverage"))
        self.window.resize(500, 400)
        self.render()
        self.assertLessEqual(dialog.property("height"), self.window.height())
        QTest.keyClick(self.window, Qt.Key.Key_Escape)
        self.assertTrue(pump(lambda: not dialog.property("visible")))
        self.assertEqual(self.inventory.state["selection"], selected)
        self.assertEqual(self.bundle.messages, [])
