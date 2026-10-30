"""Task views preserve the accepted session without querying or recalculating it."""

import unittest
from threading import Event
from unittest.mock import patch

from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QSignalSpy, QTest

from liarte_core.inventory_io import write_snapshot
from liarte_core.query import Cancelled
from liarte_desktop import inventory as stock_desktop
from tests import test_comex, test_inventory
from tests import test_inventory_alerts_qml as stock_qml
from tests import test_interface
from tests.test_inventory_compare_ui import comparison_volume
from tests.test_qt import APP, click, pump, settled


def variant(value):
    return value.toVariant() if hasattr(value, "toVariant") else value


class _NavigationActions:
    def render(self):
        self.window.update()
        self.assertFalse(self.window.grabWindow().isNull())
        APP.processEvents()

    def navigate(self, section, *, keyboard=False):
        control = self.item(self.navigation_prefix + section)
        control.forceActiveFocus(Qt.FocusReason.TabFocusReason)
        previous = None

        def ready():
            nonlocal previous
            frame = self.window.grabWindow()
            point = control.mapToScene(QPointF())
            geometry = (point.x(), point.y(), control.width(), control.height())
            stable = previous == geometry
            previous = geometry
            return (
                stable and not frame.isNull() and control.isVisible() and control.isEnabled()
                and point.x() >= -1 and point.y() >= -1
                and point.x() + control.width() <= self.window.width() + 1
                and point.y() + control.height() <= self.window.height() + 1
            )

        self.assertTrue(pump(ready), (section, previous))
        activated = QSignalSpy(control.clicked)
        if keyboard:
            QTest.keyClick(self.window, Qt.Key.Key_Space)
        else:
            click(self.window, control)
        self.assertEqual(activated.count(), 1, section)
        self.assertTrue(pump(lambda: self.workspace.property("activeSection") == section))
        self.render()

    def assert_visible_in(self, control, viewport):
        self.assertTrue(control.isVisible(), control.objectName())
        point = control.mapToItem(viewport, QPointF())
        self.assertGreaterEqual(point.x(), -1, control.objectName())
        self.assertGreaterEqual(point.y(), -1, control.objectName())
        self.assertLessEqual(point.x() + control.width(), viewport.width() + 1, control.objectName())
        self.assertLessEqual(point.y() + control.height(), viewport.height() + 1, control.objectName())

    def focused_and_visible_in(self, control, viewport):
        # Focus can be assigned before a queued Qt Quick layout has wrapped its
        # preceding controls. Render it and inspect the resulting viewport too.
        frame = self.window.grabWindow()
        point = control.mapToItem(viewport, QPointF())
        return (
            not frame.isNull() and control.hasActiveFocus() and control.isVisible()
            and point.x() >= -1 and point.y() >= -1
            and point.x() + control.width() <= viewport.width() + 1
            and point.y() + control.height() <= viewport.height() + 1
        )


class InventoryWorkspaceNavigationTests(_NavigationActions, unittest.TestCase):
    navigation_prefix = "stockJump_"
    tearDown = test_inventory.InventoryUiTests.tearDown
    item = stock_qml.InventoryAlertQmlTests.item
    load = test_inventory.InventoryUiTests.load

    def setUp(self):
        test_inventory.InventoryUiTests.setUp(self)
        self.bundle.preferences.setPreference("reducedMotion", True)
        write_snapshot(comparison_volume(70), self.base)
        self.workspace = self.item("inventoryWorkspace")

    def idle(self):
        self.assertTrue(pump(
            lambda: not self.c.state["busy"] and not self.c._debounce.isActive()
            and not self.c.comparisonState["busy"], 15,
        ), (self.c.state, self.c.comparisonState))

    def assert_section(self, active):
        for section, name in (
            ("overview", "stockOverviewSection"),
            ("monthly", "stockMonthly"),
            ("products", "stockProductsSection"),
        ):
            self.assertEqual(self.item(name).isVisible(), section == active, name)

    def test_three_exclusive_views_reuse_the_same_accepted_inventory(self):
        self.load()
        original = self.c.analysis
        data = self.c._data
        with (
            patch.object(stock_desktop, "load_inventory", side_effect=AssertionError("Source reread")),
            patch.object(stock_desktop, "analyze_inventory", side_effect=AssertionError("Stock recalculation")),
            patch.object(stock_desktop, "analyze_monthly_inventory", side_effect=AssertionError("History recalculation")),
            patch.object(self.bundle.controller._provider, "query", side_effect=AssertionError("Unrequested API call")),
        ):
            for section in ("overview", "monthly", "products", "overview"):
                self.navigate(section)
                self.assert_section(section)
                self.assertIs(self.c._data, data)
                self.assertEqual(self.c.analysis, original)
                self.assertFalse(self.c.state["busy"])
        self.assertEqual(self.bundle.messages, [])

    def test_navigation_preserves_table_page_detail_month_unit_and_comparison(self):
        self.load()
        self.c.setPage(2)
        self.c.selectRow(0)
        self.c.setMonthlyPeriod("2026-01")
        self.c.setMonthlyUnit("UN")
        self.c.setComparisonMonths("2026-01", "2026-03")
        self.idle()
        before = (
            self.c.state["selection"], self.c.state["page"], self.c.table.rows,
            self.c.detail, self.c.monthly, self.c.comparison,
        )
        for section in ("products", "monthly", "overview", "products"):
            self.navigate(section, keyboard=True)
        self.assertEqual((
            self.c.state["selection"], self.c.state["page"], self.c.table.rows,
            self.c.detail, self.c.monthly, self.c.comparison,
        ), before)
        self.assertEqual(self.bundle.messages, [])

    def test_scroll_and_resize_do_not_select_another_task(self):
        self.load()
        scroll = self.item("stockScroll")
        for width, height in ((500, 400), (900, 700), (1380, 900)):
            self.window.resize(width, height)
            for section in ("overview", "monthly", "products"):
                self.navigate(section, keyboard=True)
                scroll.setProperty("contentY", max(0, scroll.property("contentHeight") - scroll.height()))
                self.render()
                self.assertEqual(self.workspace.property("activeSection"), section)
                self.assert_section(section)
        self.assertEqual(self.bundle.messages, [])

    def test_find_reveals_the_shared_product_search_in_every_task(self):
        self.load()
        self.window.resize(500, 400)
        for section in ("monthly", "products", "overview"):
            self.navigate(section, keyboard=True)
            scroll = self.item("stockScroll")
            scroll.setProperty("contentY", max(0, scroll.property("contentHeight") - scroll.height()))
            QTest.keyClick(self.window, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
            self.assertTrue(pump(lambda: self.item("stockSearch").hasActiveFocus()))
            self.assertTrue(pump(lambda: self.item("stockSearch").mapToItem(scroll, QPointF()).y() >= -1))
            self.assert_visible_in(self.item("stockSearch"), scroll)
            self.assertEqual(self.workspace.property("activeSection"), section)
        self.assertEqual(self.bundle.messages, [])


class ImportsWorkspaceNavigationTests(_NavigationActions, unittest.TestCase):
    navigation_prefix = "jump_"
    setUp = test_comex.RealQtTests.setUp
    tearDown = test_comex.RealQtTests.tearDown
    item = test_interface.InterfaceTests.item

    @property
    def workspace(self):
        return self.item("importsWorkspace")

    def load(self):
        test_comex.RealQtTests.load(self)
        self.controller.setPreference("reducedMotion", True)

    def assert_section(self, section):
        self.assertEqual(self.item("trendPanel").isVisible(), section == "summary")
        self.assertEqual(self.item("buyingSection").isVisible(), section == "buying")
        self.assertEqual(self.item("recordsPanel").isVisible(), section == "records")

    def test_summary_buying_and_records_are_exclusive_without_refetching(self):
        self.load()
        self.controller.setFilters("country", ["China"])
        settled(self.controller)
        before = self.controller.analysis
        rows = self.controller.table.rows
        calls = list(self.transport.calls)
        with patch.object(self.provider, "query", side_effect=AssertionError("Unrequested API call")):
            for section in ("summary", "buying", "records", "summary"):
                self.navigate(section)
                self.assert_section(section)
                self.assertEqual(self.controller.analysis, before)
                self.assertEqual(self.controller.table.rows, rows)
                self.assertEqual(self.controller.state["countryValues"], ["China"])
        self.assertEqual(self.transport.calls, calls)
        self.assertEqual(self.bundle.messages, [])

    def test_table_selection_and_search_survive_other_tasks(self):
        self.load()
        self.navigate("records")
        self.controller.setFilter("search", "China")
        settled(self.controller)
        self.controller.selectRow(0)
        before = (
            self.controller._selection, self.controller.table.rows,
            self.controller.state["selection"], self.controller.state["selectedText"],
        )
        calls = list(self.transport.calls)
        for section in ("buying", "summary", "records"):
            self.navigate(section, keyboard=True)
        self.assertEqual((
            self.controller._selection, self.controller.table.rows,
            self.controller.state["selection"], self.controller.state["selectedText"],
        ), before)
        self.assertEqual(self.transport.calls, calls)
        self.assertEqual(self.bundle.messages, [])

    def test_compact_navigation_keeps_task_and_applied_scope(self):
        self.load()
        calls = list(self.transport.calls)
        before = self.controller._selection
        scroll = self.item("contentScroll")
        for width, height in ((500, 400), (900, 700), (1380, 900)):
            self.window.resize(width, height)
            for section in ("buying", "records", "summary"):
                self.navigate(section, keyboard=True)
                scroll.setProperty("contentY", max(0, scroll.property("contentHeight") - scroll.height()))
                self.render()
                self.assertEqual(self.workspace.property("activeSection"), section)
                self.assert_section(section)
        self.assertEqual(self.controller._selection, before)
        self.assertEqual(self.transport.calls, calls)
        self.assertEqual(self.bundle.messages, [])

    def test_find_opens_records_and_reveals_its_search_without_querying(self):
        self.load()
        self.window.resize(500, 400)
        calls = list(self.transport.calls)
        self.navigate("buying", keyboard=True)
        QTest.keyClick(self.window, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
        self.assertTrue(pump(lambda: self.workspace.property("activeSection") == "records"))
        search = self.item("searchBox")
        scroll = self.item("contentScroll")
        self.assertTrue(pump(lambda: self.focused_and_visible_in(search, scroll)))
        self.assert_visible_in(search, scroll)
        # A later relayout must keep the keyboard search usable without another
        # shortcut. This also covers headers wrapping with Windows font metrics.
        self.workspace.setProperty("periodExpanded", True)
        self.render()
        self.assertTrue(pump(lambda: self.focused_and_visible_in(search, scroll)))
        self.assert_visible_in(search, scroll)
        self.window.resize(500, 340)
        self.render()
        self.assertTrue(pump(lambda: self.focused_and_visible_in(search, scroll)))
        self.assert_visible_in(search, scroll)
        self.assertEqual(self.transport.calls, calls)
        self.assertEqual(self.bundle.messages, [])

    def test_f5_keeps_cancel_available_when_query_fields_are_collapsed(self):
        self.load()
        self.assertFalse(self.workspace.property("periodExpanded"))
        previous = self.controller.table.rows
        selection = self.controller._selection
        calls = list(self.transport.calls)
        entered = Event()

        def blocked(_selection, cancel, _progress):
            entered.set()
            if not cancel.wait(10):
                raise RuntimeError("The test did not cancel the consultation")
            raise Cancelled()

        try:
            with patch.object(self.provider, "query", side_effect=blocked) as query:
                QTest.keyClick(self.window, Qt.Key.Key_F5)
                self.assertTrue(pump(entered.is_set))
                self.assertTrue(self.controller.state["busy"])
                self.assertFalse(self.workspace.property("periodExpanded"))
                cancel = self.item("cancelButton")
                self.assertTrue(cancel.isVisible())
                self.assertEqual(cancel.property("text"), "Cancelar")
                clicked = QSignalSpy(cancel.clicked)
                test_comex.click(self.window, cancel)
                self.assertEqual(clicked.count(), 1)
                settled(self.controller)
                query.assert_called_once()
        finally:
            self.controller.cancel()
            settled(self.controller)
        self.assertFalse(self.workspace.property("periodExpanded"))
        self.assertEqual(self.controller.table.rows, previous)
        self.assertEqual(self.controller._selection, selection)
        self.assertEqual(self.transport.calls, calls)
        self.assertEqual(self.bundle.messages, [])
