"""Keyboard focus stays visible in long pages and compact dialogs."""

from PySide6.QtCore import Q_ARG, QMetaObject, QPointF, Qt, QUrl
from PySide6.QtTest import QTest
import unittest

from liarte_core.inventory_io import write_snapshot
from tests import test_platform
from tests.test_inventory import sample
from tests.test_qt import APP, pump


class AuditQmlTests(unittest.TestCase):
    item = test_platform.PlatformUiTests.item
    load_imports = test_platform.PlatformUiTests.load

    def setUp(self):
        test_platform.PlatformUiTests.setUp(self)
        self.inventory = self.bundle.inventory
        self.inventory._cache = None
        self.inventory._bundled = None
        self.bundle.preferences.setPreference("reducedMotion", True)

    def tearDown(self):
        self.inventory.shutdown()
        test_platform.PlatformUiTests.tearDown(self)

    def load_inventory(self):
        path = self.directory / "stock.liarte"
        write_snapshot(sample(), path)
        self.inventory.openFile(QUrl.fromLocalFile(str(path)))
        self.assertTrue(pump(lambda: not self.inventory.state["busy"], 15))
        self.assertTrue(self.inventory.state["loaded"], self.inventory.state["error"])

    def assert_in_view(self, item, viewport):
        self.assertIsNotNone(item)
        self.assertTrue(item.isVisible())
        top = item.mapToItem(viewport, QPointF()).y()
        self.assertGreaterEqual(top, -1)
        self.assertLessEqual(top + item.height(), viewport.height() + 1)

    def settle_layout(self):
        self.window.update()
        pump(timeout=0.08)

    def open_inventory(self):
        self.platform.openModule("inventory")
        self.settle_layout()

    def test_stock_return_preserves_scroll_and_focuses_visible_control(self):
        self.load_inventory()
        self.open_inventory()
        scroll = self.item("stockScroll")
        scroll.setProperty("contentY", scroll.property("contentHeight") - scroll.height())
        self.settle_layout()
        previous_scroll = scroll.property("contentY")
        self.platform.openModule("home")
        self.settle_layout()
        self.open_inventory()
        self.assert_in_view(self.window.activeFocusItem(), scroll)
        self.assertAlmostEqual(scroll.property("contentY"), previous_scroll, delta=1)
        before = self.inventory.state["selection"]["search"]
        QTest.keyClick(self.window, Qt.Key.Key_X)
        APP.processEvents()
        self.assertEqual(self.inventory.state["selection"]["search"], before)
        self.assertEqual(self.bundle.messages, [])

    def test_explicit_find_reveals_stock_search(self):
        self.load_inventory()
        self.open_inventory()
        scroll = self.item("stockScroll")
        scroll.setProperty("contentY", scroll.property("contentHeight") - scroll.height())
        QTest.keyClick(self.window, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
        self.settle_layout()
        self.assertEqual(self.window.activeFocusItem().objectName(), "stockSearch")
        self.assert_in_view(self.window.activeFocusItem(), scroll)
        self.assertEqual(scroll.property("contentY"), 0)

    def assert_home_focus(self):
        self.platform.openModule("home")
        self.settle_layout()
        self.assert_in_view(self.window.activeFocusItem(), self.item("homeScroll"))
        self.assertEqual(self.bundle.messages, [])

    def test_home_focus_with_zero_one_and_two_summaries_in_compact_window(self):
        self.window.resize(500, 400)
        # Force the navigation callback even when the application starts at Home.
        self.platform.openModule("imports")
        self.assert_home_focus()
        self.load_imports()
        self.assert_home_focus()
        self.load_inventory()
        self.open_inventory()
        self.assert_home_focus()

    def test_home_return_keeps_visible_action_near_persisted_scroll(self):
        self.window.resize(500, 400)
        self.load_inventory()
        self.load_imports()
        self.assert_home_focus()
        scroll = self.item("homeScroll")
        scroll.setProperty("contentY", scroll.property("contentHeight") - scroll.height())
        self.settle_layout()
        previous_scroll = scroll.property("contentY")
        self.platform.openModule("imports")
        self.assert_home_focus()
        self.assertAlmostEqual(scroll.property("contentY"), previous_scroll, delta=1)

    def test_stock_last_section_is_products_at_end_in_tall_windows(self):
        self.load_inventory()
        self.open_inventory()
        workspace, scroll = self.item("inventoryWorkspace"), self.item("stockScroll")
        for width, height in ((1380, 900), (1920, 1080)):
            with self.subTest(size=(width, height)):
                self.window.resize(width, height)
                self.settle_layout()
                scroll.setProperty("contentY", scroll.property("contentHeight") - scroll.height())
                APP.processEvents()
                self.assertEqual(workspace.property("activeSection"), "products")
                QMetaObject.invokeMethod(
                    workspace, "navigate", Qt.ConnectionType.DirectConnection,
                    Q_ARG("QVariant", "products"),
                )
                APP.processEvents()
                self.assertEqual(workspace.property("activeSection"), "products")

    def test_detail_keyboard_reveals_chart_readout_and_previous_control(self):
        self.window.resize(500, 400)
        self.load_inventory()
        self.open_inventory()
        self.inventory.selectRow(0)
        dialog = self.item("stockDetail")
        QMetaObject.invokeMethod(dialog, "open")
        self.assertTrue(pump(lambda: dialog.property("opened")))
        combo = self.item("stockDetailMeasure")
        combo.forceActiveFocus()
        self.settle_layout()
        viewport = dialog.property("bodyViewport")
        self.assert_in_view(combo, viewport)
        QTest.keyClick(self.window, Qt.Key.Key_Tab)
        self.settle_layout()
        chart = self.item("stockDetailTrend")
        readout = self.item("stockDetailTrendReadout")
        self.assertTrue(chart.hasActiveFocus())
        self.assert_in_view(chart, viewport)
        self.assert_in_view(readout, viewport)
        self.assertGreaterEqual(chart.height(), 110)
        QTest.keyClick(self.window, Qt.Key.Key_Right)
        self.settle_layout()
        self.assertTrue(readout.property("text"))
        self.assert_in_view(chart, viewport)
        self.assert_in_view(readout, viewport)
        QTest.keyClick(self.window, Qt.Key.Key_Backtab)
        self.settle_layout()
        self.assert_in_view(combo, viewport)
        self.assertTrue(combo.hasActiveFocus())
        QMetaObject.invokeMethod(dialog, "close")
        self.assertTrue(pump(lambda: not dialog.property("visible")))
        self.assertEqual(self.bundle.messages, [])
