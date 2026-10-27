"""Explicit stock sorting stays synchronized and usable in the real Qt UI."""

from dataclasses import replace
import unittest
from unittest.mock import patch

from PySide6.QtCore import Q_ARG, QMetaObject, QPointF, Qt
from PySide6.QtTest import QSignalSpy, QTest

from liarte_core.inventory import SCALE, Closing
from liarte_core.inventory_io import write_snapshot
from tests import test_inventory, test_inventory_alerts_qml as stock_qml
from tests.test_qt import APP, pump


def variant(value):
    return value.toVariant() if hasattr(value, "toVariant") else value


class StockPositionsSortingQmlTests(unittest.TestCase):
    tearDown = test_inventory.InventoryUiTests.tearDown
    load = test_inventory.InventoryUiTests.load
    idle = test_inventory.InventoryUiTests.idle
    item = stock_qml.InventoryAlertQmlTests.item
    reveal = stock_qml.InventoryAlertQmlTests.reveal
    click_workspace = stock_qml.InventoryAlertQmlTests.click_workspace
    workspace_geometry = stock_qml.InventoryAlertQmlTests.workspace_geometry

    def setUp(self):
        test_inventory.InventoryUiTests.setUp(self)
        self.bundle.preferences.setPreference("reducedMotion", True)
        data = test_inventory.sample()
        write_snapshot(replace(data, closings=(
            *(replace(row, turnover=0.5, days=60)
              if row.product == "0002" and row.period == "2026-03" else row
              for row in data.closings),
            Closing("0001", "01", "02", "KG", "2026-03", 50 * SCALE, 6000, 0, 30),
        )), self.base)

    def choose(self, column):
        control = self.item("stockPositionsSort")
        options = variant(control.property("model"))
        index = next(index for index, row in enumerate(options) if row["value"] == column)
        self.reveal(control)
        self.assertFalse(self.window.grabWindow().isNull())
        control.forceActiveFocus(Qt.FocusReason.TabFocusReason)
        QTest.keyClick(self.window, Qt.Key.Key_Home)
        for _ in range(index):
            QTest.keyClick(self.window, Qt.Key.Key_Down)
        self.idle()
        self.assertTrue(pump(lambda: variant(control.property("currentValue")) == column))
        self.assertEqual(self.c.state["sortColumn"], column)

    def navigate(self, section):
        QMetaObject.invokeMethod(
            self.item("inventoryWorkspace"), "navigate", Qt.ConnectionType.DirectConnection,
            Q_ARG("QVariant", section),
        )
        self.assertTrue(pump(lambda: self.item("inventoryWorkspace").property("activeSection") == section))
        self.window.grabWindow()
        APP.processEvents()

    def test_keyboard_sort_and_direction_use_numeric_source_values_without_reanalysis(self):
        self.load()
        analysis = self.c._analysis
        with patch("liarte_desktop.inventory.analyze_inventory", side_effect=AssertionError("Unrequested analysis")):
            self.choose(9)
            self.assertTrue(self.c.presentation["descending"])
            self.assertEqual([row.turnover for row in self.c.table.rows], [3, 0.5, 0, None])
            self.assertEqual(self.item("stockPositionsSortDirection").property("text"), "Maior giro primeiro")
            self.click_workspace(self.item("stockPositionsSortDirection"))
            self.idle()
            self.assertFalse(self.c.presentation["descending"])
            self.assertEqual([row.turnover for row in self.c.table.rows], [0, 0.5, 3, None])
            self.assertEqual(self.item("stockPositionsSortDirection").property("text"), "Menor giro primeiro")
        self.assertIs(self.c._analysis, analysis)
        self.assertEqual(self.bundle.messages, [])

    def test_header_order_is_reflected_in_controls_and_survives_navigation(self):
        self.load()
        self.navigate("products")
        self.c.sortByColumn(8)
        self.idle()
        self.assertEqual(variant(self.item("stockPositionsSort").property("currentValue")), 8)
        self.assertEqual(self.item("stockPositionsSortDirection").property("text"), "Venda mais antiga")
        self.c.sortByColumn(8)
        self.assertEqual(self.item("stockPositionsSortDirection").property("text"), "Venda mais recente")
        before = self.c.presentation["selection"]
        for section in ("monthly", "overview", "products"):
            self.navigate(section)
        self.assertEqual(self.c.presentation["sortColumn"], 8)
        self.assertTrue(self.c.presentation["descending"])
        self.assertEqual(self.c.presentation["selection"], before)
        self.assertEqual(variant(self.item("stockPositionsSort").property("currentValue")), 8)
        self.assertEqual(self.bundle.messages, [])

    def test_compact_toolbar_with_wide_fonts_fits_and_remains_keyboard_operable(self):
        self.load()
        self.window.resize(500, 400)
        self.navigate("products")
        combo = self.item("stockPositionsSort")
        direction = self.item("stockPositionsSortDirection")
        performance = self.item("stockPerformanceOpen")
        detail = self.item("stockPositionDetail")
        for control in (combo, direction, performance, detail):
            font = control.property("font")
            font.setStretch(200)
            control.setProperty("font", font)
        self.choose(9)
        for control in (combo, direction, performance, detail):
            self.reveal(control)
            self.assertFalse(self.window.grabWindow().isNull())
            scroll = self.item("stockScroll")
            point = control.mapToItem(scroll, QPointF())
            self.assertGreaterEqual(point.x(), -1)
            self.assertLessEqual(point.x() + control.width(), scroll.width() + 1)
            self.assertGreaterEqual(point.y(), -1)
            self.assertLessEqual(point.y() + control.height(), scroll.height() + 1)
        self.reveal(direction)
        direction.forceActiveFocus(Qt.FocusReason.TabFocusReason)
        activated = QSignalSpy(direction.clicked)
        QTest.keyClick(self.window, Qt.Key.Key_Space)
        self.assertEqual(activated.count(), 1)
        self.idle()
        self.assertFalse(self.c.presentation["descending"])
        self.assertEqual(self.bundle.messages, [])
