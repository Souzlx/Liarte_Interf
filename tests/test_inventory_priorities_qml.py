"""Product priorities stay explicit, scoped and usable through actual Qt controls."""

import unittest
from threading import Event
from unittest.mock import patch

from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QSignalSpy, QTest

from liarte_core.inventory_io import write_snapshot
from tests import test_inventory, test_inventory_alerts_qml as alert_tests
from tests.test_inventory_performance_ui import performance_sample
from tests.test_qt import APP, click, pump


def variant(value):
    return value.toVariant() if hasattr(value, "toVariant") else value


class InventoryPrioritiesQmlTests(unittest.TestCase):
    tearDown = test_inventory.InventoryUiTests.tearDown
    load = test_inventory.InventoryUiTests.load
    item = alert_tests.InventoryAlertQmlTests.item

    def setUp(self):
        test_inventory.InventoryUiTests.setUp(self)
        self.bundle.preferences.setPreference("reducedMotion", True)
        write_snapshot(performance_sample(25), self.base)
        self.workspace = self.item("inventoryWorkspace")

    def idle(self):
        self.assertTrue(pump(
            lambda: not self.c.state["busy"] and not self.c._debounce.isActive(), 15,
        ), self.c.state)

    def priorities_idle(self):
        self.assertTrue(pump(
            lambda: not self.c.priorities.state["busy"], 15,
        ), self.c.priorities.state)
        self.assertTrue(self.c.priorities.state["current"], self.c.priorities.state)
        self.assertFalse(self.c.priorities.state["error"], self.c.priorities.state)

    def viewport(self, control=None):
        if control is not None and control.objectName().startswith("stockJump_"):
            return self.window.contentItem()
        for name in ("stockPerformanceDialog", "stockPrioritiesDetail"):
            dialog = self.item(name)
            if dialog.property("visible"):
                return dialog.property("bodyViewport")
        return self.item("stockScroll")

    def geometry(self, control):
        viewport = self.viewport(control)
        point = control.mapToItem(viewport, QPointF())
        return {
            "name": control.objectName(),
            "control": tuple(round(value, 3) for value in (
                point.x(), point.y(), control.width(), control.height(),
            )),
            "viewport": (viewport.width(), viewport.height()),
            "visible": control.isVisible(), "enabled": control.isEnabled(),
            "moving": viewport.property("moving"),
        }

    def reveal(self, control):
        viewport = self.viewport(control)
        if viewport == self.window.contentItem():
            self.window.update()
            APP.processEvents()
            return
        point = control.mapToItem(viewport, QPointF())
        maximum = max(0, viewport.property("contentHeight") - viewport.height())
        target = viewport.property("contentY") + point.y() - 16
        viewport.setProperty("contentY", max(0, min(maximum, target)))
        self.window.update()
        APP.processEvents()

    def ready(self, control):
        previous = None

        def rendered():
            nonlocal previous
            self.reveal(control)
            frame = self.window.grabWindow()
            geometry = self.geometry(control)
            stable = geometry == previous
            previous = geometry
            x, y, width, height = geometry["control"]
            vw, vh = geometry["viewport"]
            return (
                stable and not frame.isNull() and geometry["visible"]
                and geometry["enabled"] and not geometry["moving"]
                and width > 0 and height > 0 and x >= -1 and y >= -1
                and x + width <= vw + 1 and y + height <= vh + 1
            )

        self.assertTrue(pump(rendered), self.geometry(control))

    def click_control(self, control, *, keyboard=False):
        self.ready(control)
        geometry = self.geometry(control)
        activated = QSignalSpy(control.clicked)
        if keyboard:
            control.forceActiveFocus(Qt.FocusReason.TabFocusReason)
            QTest.keyClick(self.window, Qt.Key.Key_Space)
        else:
            click(self.window, control)
        self.assertEqual(activated.count(), 1, geometry)

    def navigate(self, section):
        self.click_control(self.item("stockJump_" + section), keyboard=True)
        self.assertTrue(pump(lambda: self.workspace.property("activeSection") == section))

    def open_priorities(self):
        self.load()
        self.navigate("products")
        self.assertEqual(self.workspace.property("productView"), "priorities")
        self.priorities_idle()
        self.assertTrue(self.item("stockPrioritiesSection").isVisible())
        return self.c.priorities

    def configure(self, unit="KG", window=1, category="capital", query=""):
        self.c.priorities.configure(unit, window, category, query)
        self.priorities_idle()
        self.assertFalse(self.window.grabWindow().isNull())

    def choose(self, name, value):
        control = self.item(name)
        options = variant(control.property("model"))
        index = next(index for index, row in enumerate(options) if row["value"] == value)
        self.ready(control)
        control.forceActiveFocus(Qt.FocusReason.TabFocusReason)
        QTest.keyClick(self.window, Qt.Key.Key_Home)
        for _ in range(index):
            QTest.keyClick(self.window, Qt.Key.Key_Down)
        self.assertTrue(pump(lambda: variant(control.property("currentValue")) == value))

    def type_search(self, query):
        control = self.item("stockPrioritiesSearch")
        self.ready(control)
        control.forceActiveFocus(Qt.FocusReason.TabFocusReason)
        QTest.keyClick(self.window, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        QTest.keyClick(self.window, Qt.Key.Key_Backspace)
        for character in query:
            QTest.keyClick(self.window, Qt.Key(ord(character)))
        self.assertEqual(control.property("text").casefold(), query.casefold())

    def test_products_opens_priorities_lazily_and_navigation_reuses_the_accepted_source(self):
        from liarte_desktop import inventory_priorities as desktop

        self.load()
        self.assertTrue(self.c.priorities.state["available"])
        self.assertFalse(self.c.priorities.state["current"])
        self.assertFalse(self.c.priorities.state["busy"])
        before = (self.c.state["selection"], self.c.table.rows, self.c.monthly)
        self.navigate("products")
        self.priorities_idle()
        self.assertEqual(self.workspace.property("productView"), "priorities")
        self.assertFalse(self.item("stockPositionsSection").isVisible())
        with patch.object(desktop, "analyze_product_performance", side_effect=AssertionError("Unrequested recalculation")):
            self.navigate("overview")
            self.navigate("products")
            self.priorities_idle()
        self.assertEqual((self.c.state["selection"], self.c.table.rows, self.c.monthly), before)
        self.assertEqual(self.bundle.messages, [])

    def test_unit_window_focus_and_search_remain_drafts_until_apply(self):
        priorities = self.open_priorities()
        before = (priorities.state["unit"], priorities.state["window"],
                  priorities.state["category"], priorities.state["query"])
        self.choose("stockPrioritiesUnit", "L")
        self.choose("stockPrioritiesWindow", 1)
        self.choose("stockPrioritiesCategory", "capital")
        self.type_search("LIQ")
        query = self.item("stockPrioritiesSearch").property("text")
        self.assertEqual((priorities.state["unit"], priorities.state["window"],
                          priorities.state["category"], priorities.state["query"]), before)
        self.click_control(self.item("stockPrioritiesApply"))
        self.priorities_idle()
        self.assertEqual((priorities.state["unit"], priorities.state["window"],
                          priorities.state["category"], priorities.state["query"]),
                         ("L", 1, "capital", query))
        self.assertEqual([row["code"] for row in priorities.summary["rows"]], ["LIQ"])
        period = self.item("stockPrioritiesPeriod").property("text")
        self.assertTrue(priorities.summary["closingLabel"])
        self.assertIn(priorities.summary["closingLabel"], period)
        self.assertIn(priorities.summary["targetLabel"], period)
        self.assertNotIn(self.c.state["asOf"], period)
        self.assertEqual(self.bundle.messages, [])

    def test_investigation_shows_numeric_criteria_without_changing_global_filters_or_list(self):
        priorities = self.open_priorities()
        self.configure()
        first = priorities.summary["rows"][0]
        before = (self.c.state["selection"], self.c.table.rows, self.c.monthly,
                  priorities.state["category"], priorities.state["page"])
        self.click_control(self.item("stockPrioritiesRow_0"))
        dialog = self.item("stockPrioritiesDetail")
        self.assertTrue(pump(lambda: dialog.property("opened")))
        self.assertEqual((priorities.detail["code"], priorities.detail["unit"]),
                         (first["code"], first["unit"]))
        self.assertTrue(priorities.detail["metrics"])
        self.assertTrue(priorities.detail["criteria"])
        for index, criterion in enumerate(priorities.detail["criteria"]):
            self.assertEqual(self.item(f"stockPrioritiesCriterionValue_{index}").property("text"),
                             criterion["value"])
            self.assertEqual(self.item(f"stockPrioritiesCriterionReference_{index}").property("text"),
                             criterion["detail"])
        self.assertEqual(self.item("stockPrioritiesCriterion_0").property("text"), first["criterion"])
        self.assertEqual((self.c.state["selection"], self.c.table.rows, self.c.monthly,
                          priorities.state["category"], priorities.state["page"]), before)
        self.assertTrue(self.workspace.property("modalOpen"))
        QTest.keyClick(self.window, Qt.Key.Key_Escape)
        self.assertTrue(pump(lambda: not dialog.property("visible")))
        self.assertTrue(pump(lambda: not self.workspace.property("modalOpen")))
        self.assertEqual(self.bundle.messages, [])

    def test_numeric_detail_keeps_all_criteria_visible_at_wide_and_compact_sizes(self):
        priorities = self.open_priorities()
        self.configure(category="review")
        if not priorities.summary["rows"]:
            self.configure(category="capital")
        self.click_control(self.item("stockPrioritiesRow_0"))
        self.assertTrue(pump(lambda: self.item("stockPrioritiesDetail").property("opened")))
        criteria = priorities.detail["criteria"]
        self.assertTrue(criteria)
        for width, height in ((1380, 900), (900, 700), (500, 400)):
            with self.subTest(width=width):
                self.window.resize(width, height)
                self.assertTrue(pump(lambda: abs(self.window.contentItem().width() - width) < 1))
                for index, criterion in enumerate(criteria):
                    row = self.item(f"stockPrioritiesCriterionRow_{index}")
                    self.ready(row)
                    value = self.item(f"stockPrioritiesCriterionValue_{index}")
                    self.assertEqual(value.property("text"), criterion["value"])
                    for control in (row, value):
                        x, y, control_width, control_height = self.geometry(control)["control"]
                        viewport = self.geometry(control)["viewport"]
                        self.assertGreaterEqual(x, -1)
                        self.assertLessEqual(x + control_width, viewport[0] + 1)
                        self.assertGreater(control_height, 0)

        def texts(item):
            value = item.property("text")
            if isinstance(value, str) and item.isVisible():
                yield value
            for child in item.childItems():
                yield from texts(child)

        rendered = "\n".join(texts(self.window.contentItem()))
        self.assertNotIn("Próximo passo:", rendered)
        self.assertNotIn("Confira demanda", rendered)
        self.assertNotIn("Revisar reposição", rendered)
        self.assertIn("Critérios quantitativos", rendered)
        self.assertEqual(self.bundle.messages, [])

    def test_history_opens_the_same_product_unit_and_window_without_filtering_inventory(self):
        priorities = self.open_priorities()
        self.configure(window=1)
        first = priorities.summary["rows"][0]
        before = (self.c.state["selection"], self.c.table.rows, self.c.monthly)
        self.click_control(self.item("stockPrioritiesRow_0"))
        self.assertTrue(pump(lambda: self.item("stockPrioritiesDetail").property("opened")))
        self.click_control(self.item("stockPrioritiesHistory"))
        performance = self.c.performance
        self.assertTrue(pump(lambda: (
            performance.state["current"] and not performance.state["busy"]
            and performance.detail.get("code") == first["code"]
            and performance.detail.get("unit") == first["unit"]
        ), 15), performance.state)
        self.assertTrue(self.item("stockPerformanceDialog").property("visible"))
        self.assertEqual(performance.state["window"], 1)
        self.assertTrue(performance.detail["indicators"])
        self.click_control(self.item("stockPerformanceIndicatorsToggle"))
        self.assertEqual(self.item("stockPerformanceIndicatorValue_0").property("text"),
                         performance.detail["indicators"][0]["value"])
        self.assertEqual((self.c.state["selection"], self.c.table.rows, self.c.monthly), before)
        self.assertEqual(self.bundle.messages, [])

    def test_view_positions_applies_only_the_selected_product_and_unit_then_changes_view(self):
        priorities = self.open_priorities()
        self.configure()
        first = priorities.summary["rows"][0]
        before = self.c.state["selection"].copy()
        self.click_control(self.item("stockPrioritiesRow_0"))
        self.assertTrue(pump(lambda: self.item("stockPrioritiesDetail").property("opened")))
        self.click_control(self.item("stockPrioritiesViewPositions"))
        self.idle()
        self.assertTrue(pump(lambda: self.workspace.property("productView") == "positions"))
        self.assertEqual(self.c.state["selection"]["product"], first["code"])
        self.assertEqual(self.c.state["selection"]["unit"], first["unit"])
        for key, value in before.items():
            if key not in {"product", "unit", "search"}:
                self.assertEqual(self.c.state["selection"][key], value, key)
        self.assertTrue(self.item("stockPositionsSection").isVisible())
        self.assertFalse(self.item("stockPrioritiesSection").isVisible())
        self.assertEqual(self.bundle.messages, [])

    def test_pages_and_product_views_preserve_the_priority_context(self):
        priorities = self.open_priorities()
        self.configure()
        self.assertGreater(priorities.state["pages"], 1)
        self.assertEqual(len(priorities.summary["rows"]), 8)
        self.click_control(self.item("stockPrioritiesNext"))
        self.priorities_idle()
        self.assertEqual(priorities.state["page"], 2)
        before = (priorities.state["unit"], priorities.state["window"],
                  priorities.state["category"], priorities.state["query"],
                  priorities.summary["rows"])
        self.click_control(self.item("stockProductsView_positions"))
        self.assertEqual(self.workspace.property("productView"), "positions")
        self.navigate("overview")
        self.navigate("products")
        self.assertEqual(self.workspace.property("productView"), "positions")
        self.click_control(self.item("stockProductsView_priorities"))
        self.priorities_idle()
        self.assertEqual(priorities.state["page"], 2)
        self.assertEqual((priorities.state["unit"], priorities.state["window"],
                          priorities.state["category"], priorities.state["query"],
                          priorities.summary["rows"]), before)
        self.assertEqual(self.bundle.messages, [])

    def test_compact_toolbar_and_detail_actions_fit_with_larger_fonts_and_keyboard(self):
        self.open_priorities()
        self.configure()
        for name in ("stockPrioritiesCategory", "stockPrioritiesUnit", "stockPrioritiesWindow",
                     "stockPrioritiesSearch", "stockPrioritiesApply"):
            control = self.item(name)
            font = control.property("font")
            font.setPixelSize(round(max(12, font.pixelSize()) * 1.25))
            font.setStretch(125)
            control.setProperty("font", font)
        for width, height in ((1380, 900), (900, 700), (500, 400)):
            with self.subTest(width=width):
                self.window.resize(width, height)
                self.assertTrue(pump(lambda: abs(self.window.contentItem().width() - width) < 1))
                for name in ("stockPrioritiesCategory", "stockPrioritiesUnit", "stockPrioritiesWindow",
                             "stockPrioritiesSearch", "stockPrioritiesApply", "stockPrioritiesRow_0"):
                    self.ready(self.item(name))
        self.click_control(self.item("stockPrioritiesRow_0"), keyboard=True)
        self.assertTrue(pump(lambda: self.item("stockPrioritiesDetail").property("opened")))
        for name in ("stockPrioritiesViewPositions", "stockPrioritiesHistory"):
            self.ready(self.item(name))
        QTest.keyClick(self.window, Qt.Key.Key_Escape)
        self.assertTrue(pump(lambda: not self.item("stockPrioritiesDetail").property("visible")))
        self.assertEqual(self.bundle.messages, [])

    def test_busy_priority_request_disables_actions_and_cancel_restores_the_applied_view(self):
        from liarte_desktop import inventory_priorities as desktop

        priorities = self.open_priorities()
        self.configure()
        before = (priorities.state["window"], priorities.state["category"],
                  priorities.state["page"], priorities.summary["rows"])
        entered, release = Event(), Event()
        original = desktop.analyze_product_performance

        def delayed(*args, **kwargs):
            entered.set()
            if not release.wait(10):
                raise RuntimeError("Priority test did not release its worker")
            return original(*args, **kwargs)

        try:
            with patch.object(desktop, "analyze_product_performance", side_effect=delayed):
                priorities.configure("KG", 6, "capital", "")
                self.assertTrue(pump(entered.is_set))
                self.assertFalse(self.item("stockPrioritiesApply").isEnabled())
                self.assertFalse(self.item("stockPrioritiesNext").isEnabled())
                self.click_control(self.item("stockPrioritiesCancel"))
                release.set()
                self.priorities_idle()
        finally:
            release.set()
            priorities.cancel()
            self.priorities_idle()
        self.assertEqual((priorities.state["window"], priorities.state["category"],
                          priorities.state["page"], priorities.summary["rows"]), before)
        self.assertEqual(self.bundle.messages, [])

    def test_cancelling_first_preparation_stays_idle_until_an_explicit_retry(self):
        from liarte_core.query import checkpoint
        from liarte_desktop import inventory_priorities as desktop

        self.load()
        priorities = self.c.priorities
        self.assertFalse(priorities.state["current"])
        entered = Event()
        calls = []
        original = desktop.analyze_product_performance

        def cancellable(*args, **kwargs):
            calls.append(True)
            if len(calls) == 1:
                entered.set()
                cancel = kwargs["cancel"]
                if not cancel.wait(10):
                    raise RuntimeError("First preparation was not cancelled by the test")
                checkpoint(cancel)
            return original(*args, **kwargs)

        try:
            with patch.object(desktop, "analyze_product_performance", side_effect=cancellable):
                self.navigate("products")
                self.assertTrue(pump(entered.is_set))
                self.click_control(self.item("stockPrioritiesCancel"))
                self.assertTrue(pump(lambda: not priorities.state["busy"], 15))
                # Let queued visibility/state callbacks run. They must not
                # silently undo the user's first cancellation by starting again.
                pump(lambda: False, 0.15)
                self.assertEqual(len(calls), 1)
                self.assertFalse(priorities.state["busy"])
                self.assertFalse(priorities.state["current"])
                self.assertTrue(priorities.state["cancelled"])
                self.click_control(self.item("stockPrioritiesRefresh"))
                self.priorities_idle()
                self.assertEqual(len(calls), 2)
                self.assertFalse(priorities.state["cancelled"])
        finally:
            priorities.cancel()
            self.assertTrue(pump(lambda: not priorities.state["busy"], 15))
        self.assertEqual(self.bundle.messages, [])

    def test_closing_history_while_it_loads_does_not_reopen_the_dialog(self):
        from liarte_desktop import inventory_performance as desktop

        self.open_priorities()
        self.configure()
        first = self.c.priorities.summary["rows"][0]
        entered, release = Event(), Event()
        original = desktop.analyze_product_performance

        def delayed(*args, **kwargs):
            entered.set()
            if not release.wait(10):
                raise RuntimeError("History test did not release its worker")
            return original(*args, **kwargs)

        try:
            with patch.object(desktop, "analyze_product_performance", side_effect=delayed):
                self.click_control(self.item("stockPrioritiesRow_0"))
                self.assertTrue(pump(lambda: self.item("stockPrioritiesDetail").property("opened")))
                self.click_control(self.item("stockPrioritiesHistory"))
                self.assertTrue(pump(entered.is_set))
                dialog = self.item("stockPerformanceDialog")
                self.assertTrue(dialog.property("visible"))
                QTest.keyClick(self.window, Qt.Key.Key_Escape)
                self.assertTrue(pump(lambda: not dialog.property("visible")))
                release.set()
                self.assertTrue(pump(lambda: not self.c.performance.state["busy"], 15))
                APP.processEvents()
                self.assertFalse(dialog.property("visible"))
                self.assertNotEqual(self.c.performance.detail.get("code"), first["code"])
        finally:
            release.set()
        self.assertEqual(self.bundle.messages, [])
