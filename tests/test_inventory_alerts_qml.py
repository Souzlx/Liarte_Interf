"""Stock review rules remain editable and usable in the real Qt workspace."""

from dataclasses import replace
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from PySide6.QtCore import Q_ARG, QMetaObject, QObject, QPointF, QSettings, Qt
from PySide6.QtTest import QSignalSpy, QTest

from liarte_core.inventory import SCALE
from liarte_core.inventory_io import write_snapshot
from tests import test_inventory
from tests.test_qt import APP, click, pump


def alert_sample():
    data = test_inventory.sample()
    return replace(
        data,
        balances=(
            replace(data.balances[0], quantity=SCALE),
            replace(data.balances[1], quantity=SCALE),
            data.balances[2],
            replace(data.balances[3], quantity=2 * SCALE, cost=200),
        ),
        sales=tuple(sale for sale in data.sales if not (
            sale.product == "0002" and sale.day.month == 3
        )),
    )


class InventoryAlertQmlTests(unittest.TestCase):
    tearDown = test_inventory.InventoryUiTests.tearDown
    idle = test_inventory.InventoryUiTests.idle
    load = test_inventory.InventoryUiTests.load

    def setUp(self):
        test_inventory.InventoryUiTests.setUp(self)
        self.bundle.preferences.setPreference("reducedMotion", True)
        self.settings = QSettings(
            str(Path(self.temp.name) / "alert-settings.ini"), QSettings.Format.IniFormat
        )
        self.c._settings = self.settings
        write_snapshot(alert_sample(), self.base)

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
        workspace = self.item("inventoryWorkspace")
        owner = None
        for ancestor in InventoryAlertQmlTests.ancestors(item):
            name = ancestor.objectName()
            if name == "stockMonthly" or name.startswith("stockCompare"):
                owner = "monthly"
                break
            if name == "stockPositionsSection" or name in {"stockTable", "stockPerformanceOpen"}:
                owner = "products"
                break
            if name == "stockOverviewSection" or name.startswith("stockAlert"):
                owner = "overview"
                break
        if owner and workspace.property("activeSection") != owner:
            QMetaObject.invokeMethod(
                workspace, "navigate", Qt.ConnectionType.DirectConnection,
                Q_ARG("QVariant", owner),
            )
            APP.processEvents()
        if (
            owner == "overview" and item.objectName().startswith("stockAlert")
            and item.objectName() != "stockAlertsToggle" and not workspace.property("showAlerts")
        ):
            self.click_workspace(self.item("stockAlertsToggle"))
        scroll = self.item("stockScroll")
        point = item.mapToItem(scroll, QPointF())
        target = scroll.property("contentY") + point.y() - 30
        maximum = max(0, scroll.property("contentHeight") - scroll.height())
        scroll.setProperty("contentY", max(0, min(maximum, target)))
        self.window.update()
        APP.processEvents()

    @staticmethod
    def ancestors(item):
        while item is not None:
            yield item
            item = item.parentItem()

    def click_workspace(self, control):
        self.window.requestActivate()
        previous = None

        def rendered_control_is_ready():
            nonlocal previous
            # A load publication changes the height above these controls. Let Qt
            # polish/render that layout before trusting a scroll/click position.
            # Requiring two equal rendered geometries also covers native resize.
            self.reveal(control)
            frame = self.window.grabWindow()
            geometry = self.workspace_geometry(control)
            stable = geometry == previous
            previous = geometry
            x, y, width, height = geometry["control"]
            viewport_width, viewport_height = geometry["viewport"]
            return (
                stable
                and not frame.isNull()
                and abs(frame.width() / self.window.devicePixelRatio() - self.window.width()) <= 1
                and geometry["visible"]
                and geometry["enabled"]
                and not geometry["moving"]
                and width > 0
                and height > 0
                and x >= -1
                and y >= -1
                and x + width <= viewport_width + 1
                and y + height <= viewport_height + 1
            )

        self.assertTrue(pump(rendered_control_is_ready), self.workspace_geometry(control))
        # A clicked alert row may be destroyed by the resulting publication.
        # Capture diagnostics first; the signal spy survives that model reset.
        geometry = self.workspace_geometry(control)
        clicks = QSignalSpy(control.clicked)
        click(self.window, control)
        self.assertEqual(clicks.count(), 1, geometry)

    def open_settings(self):
        button = self.item("stockAlertSettingsButton")
        dialog = self.item("stockAlertSettingsDialog")
        self.assertTrue(pump(lambda: not dialog.property("visible")))
        self.click_workspace(button)
        self.assertTrue(pump(lambda: dialog.property("opened")), self.workspace_geometry(button))
        self.assertTrue(pump(lambda: self.item("stockAlertStaleDays").hasActiveFocus()))
        self.assertFalse(self.window.grabWindow().isNull())
        return dialog

    def workspace_geometry(self, control):
        scroll = self.item("stockScroll")
        point = control.mapToItem(scroll, QPointF())
        return {
            "name": control.objectName(),
            "window": (self.window.width(), self.window.height()),
            "content": (self.window.contentItem().width(), self.window.contentItem().height()),
            "viewport": (scroll.width(), scroll.height()),
            "control": tuple(round(value, 3) for value in (
                point.x(), point.y(), control.width(), control.height()
            )),
            "visible": control.isVisible(),
            "enabled": control.isEnabled(),
            "moving": scroll.property("moving"),
            "current": self.c.state["current"],
            "busy": self.c.state["busy"],
            "modal": self.item("inventoryWorkspace").property("modalOpen"),
        }

    def set_text(self, item, text):
        item.forceActiveFocus(Qt.FocusReason.TabFocusReason)
        QTest.keyClick(self.window, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        QTest.keyClick(self.window, Qt.Key.Key_Backspace)
        for character in text:
            QTest.keyClick(self.window, Qt.Key(ord(character)))
        APP.processEvents()
        # Focus reveal is queued by AppDialog, and its scroll/layout must be
        # rendered before a following mouse click uses the action's position.
        self.assertFalse(self.window.grabWindow().isNull())

    def dialog_visible_rect(self, dialog, item):
        viewport = dialog.property("bodyViewport")
        point = item.mapToItem(viewport, QPointF())
        return (
            point.x() >= -1
            and point.y() >= -1
            and point.x() + item.width() <= viewport.width() + 1
            and point.y() + item.height() <= viewport.height() + 1
        )

    def test_cancel_defaults_and_escape_do_not_apply_draft_limits(self):
        self.load()
        dialog = self.open_settings()
        self.assertTrue(self.item("inventoryWorkspace").property("modalOpen"))
        self.set_text(self.item("stockAlertStaleDays"), "120")
        self.set_text(self.item("stockAlertCoverageDays"), "15")
        click(self.window, self.item("stockAlertDefaults"))
        self.assertEqual(self.item("stockAlertStaleDays").property("text"), "90")
        self.assertEqual(self.item("stockAlertCoverageDays").property("text"), "30")
        self.set_text(self.item("stockAlertStaleDays"), "240")
        QTest.keyClick(self.window, Qt.Key.Key_Escape)
        self.assertTrue(pump(lambda: not dialog.property("visible")))
        self.assertTrue(pump(lambda: self.item("stockAlertSettingsButton").hasActiveFocus()))
        self.assertFalse(self.item("inventoryWorkspace").property("modalOpen"))
        self.assertEqual(self.c.alertSettings["staleDays"], 90)
        self.assertIsNone(self.settings.value("inventory/alerts/limits", None))
        self.open_settings()
        self.assertEqual(self.item("stockAlertStaleDays").property("text"), "90")
        click(self.window, self.item("stockAlertCancel"))
        self.assertTrue(pump(lambda: not dialog.property("visible")))
        self.assertEqual(self.bundle.messages, [])

    def test_apply_updates_both_rules_and_reopening_uses_the_saved_limits(self):
        self.load()
        dialog = self.open_settings()
        self.set_text(self.item("stockAlertStaleDays"), "120")
        self.set_text(self.item("stockAlertCoverageDays"), "7")
        with patch.object(self.bundle.controller._provider, "query") as query:
            click(self.window, self.item("stockAlertApply"))
            self.idle()
            query.assert_not_called()
        self.assertTrue(pump(lambda: not dialog.property("visible")))
        self.assertTrue(pump(lambda: self.item("stockAlertSettingsButton").hasActiveFocus()))
        self.assertEqual(self.c.alertSettings["staleDays"], 120)
        self.assertEqual(self.c.alertSettings["coverageDays"], 7)
        self.assertEqual(
            json.loads(self.settings.value("inventory/alerts/limits")),
            {"staleDays": 120, "coverageDays": 7},
        )
        categories = {item["key"]: item for item in self.c.alerts["categories"]}
        self.assertEqual(categories["stale"]["count"], 0)
        self.assertEqual(categories["low_coverage"]["count"], 1)
        self.open_settings()
        self.assertEqual(self.item("stockAlertStaleDays").property("text"), "120")
        self.assertEqual(self.item("stockAlertCoverageDays").property("text"), "7")
        self.assertEqual(self.bundle.messages, [])

    def test_invalid_and_ambiguous_numeric_drafts_disable_apply(self):
        self.load()
        self.open_settings()
        field = self.item("stockAlertStaleDays")
        apply = self.item("stockAlertApply")
        for value in ("", "0", "3651", "1,000", "1.000", "+1"):
            with self.subTest(value=value):
                # Set an invalid draft directly: keyboard validators may reject
                # the keystroke before the control can contain the value.
                field.setProperty("text", value)
                APP.processEvents()
                self.assertFalse(apply.isEnabled())
                self.assertEqual(self.c.alertSettings["staleDays"], 90)
        field.setProperty("text", "3650")
        APP.processEvents()
        self.assertTrue(apply.isEnabled())
        self.assertEqual(self.bundle.messages, [])

    def test_failed_evaluation_can_be_retried_from_the_settings_dialog(self):
        self.load()
        dialog = self.open_settings()
        self.set_text(self.item("stockAlertStaleDays"), "30")
        self.set_text(self.item("stockAlertCoverageDays"), "300")
        with (
            patch(
                "liarte_desktop.inventory.analyze_stock_alerts",
                side_effect=ValueError("Falha sintética ao avaliar os alertas"),
            ),
            self.assertLogs("liarte.desktop", level="ERROR"),
        ):
            self.item("stockAlertApply").forceActiveFocus(Qt.FocusReason.TabFocusReason)
            QTest.keyClick(self.window, Qt.Key.Key_Space)
            self.idle()
        self.assertFalse(dialog.property("visible"))
        self.assertFalse(self.c.state["current"])
        self.assertIn("Falha sintética", self.c.state["error"])
        self.assertIsNone(self.settings.value("inventory/alerts/limits", None))
        self.assertTrue(self.item("stockAlertSettingsButton").isEnabled())
        self.assertTrue(pump(lambda: self.item("stockAlertSettingsButton").hasActiveFocus()))
        self.assertFalse(self.item("stockAlertCategory_stale").isEnabled())

        self.open_settings()
        self.assertEqual(self.item("stockAlertStaleDays").property("text"), "30")
        self.assertEqual(self.item("stockAlertCoverageDays").property("text"), "300")
        self.assertTrue(self.item("stockAlertApply").isEnabled())
        self.item("stockAlertApply").forceActiveFocus(Qt.FocusReason.TabFocusReason)
        QTest.keyClick(self.window, Qt.Key.Key_Space)
        self.idle()
        self.assertTrue(self.c.state["current"])
        self.assertEqual(self.c.state["error"], "")
        self.assertEqual(
            json.loads(self.settings.value("inventory/alerts/limits")),
            {"staleDays": 30, "coverageDays": 300},
        )
        self.assertTrue(pump(lambda: self.item("stockAlertSettingsButton").hasActiveFocus()))
        self.assertEqual(self.bundle.messages, [])

    def test_category_and_alert_click_filter_the_exact_product_branch_and_unit(self):
        self.load()
        self.assertFalse(self.item("stockAlerts").property("showOccurrences"))
        low = self.item("stockAlertCategory_low_coverage")
        self.click_workspace(low)
        self.assertTrue(pump(lambda: self.item("stockAlerts").property("showOccurrences")))
        row = self.item("stockAlertRow0")
        model = row.property("modelData")
        model = model.toVariant() if hasattr(model, "toVariant") else model
        self.assertEqual(model["code"], "0001")
        with patch.object(self.bundle.controller._provider, "query") as query:
            self.click_workspace(row)
            self.idle()
            query.assert_not_called()
        selected = self.c.state["selection"]
        self.assertEqual((selected["product"], selected["branch"], selected["unit"]), ("0001", "01", "KG"))
        self.assertEqual(selected["search"], "")
        self.assertEqual({row.balance.product for row in self.c.table.rows}, {"0001"})
        self.assertTrue(pump(
            lambda: self.item("inventoryWorkspace").property("activeSection") == "products"
        ))
        self.assertEqual(self.bundle.messages, [])

    def test_warehouse_filter_explains_unavailable_coverage_without_calling_it_zero(self):
        self.load()
        self.c.setFilter("warehouse", "01")
        self.idle()
        category = self.item("stockAlertCategory_low_coverage")
        self.click_workspace(category)
        self.assertIn("armazém", self.item("stockAlertCategoryNotice").property("text"))
        data = {item["key"]: item for item in self.c.alerts["categories"]}["low_coverage"]
        self.assertFalse(data["available"])
        self.assertEqual(data["items"], [])
        self.assertFalse(self.item("stockAlertEmpty").isVisible())
        self.assertEqual(self.bundle.messages, [])

    def test_compact_wide_font_dialog_reveals_keyboard_actions_and_returns_focus(self):
        self.load()
        for name in ("stockAlertSettingsButton", "stockAlertApply", "stockAlertCancel", "stockAlertDefaults"):
            control = self.item(name)
            font = control.property("font")
            font.setStretch(200)
            control.setProperty("font", font)
        self.window.resize(500, 400)
        self.assertTrue(pump(lambda: abs(self.window.contentItem().width() - 500) < 1))
        self.window.grabWindow()
        viewport = self.item("stockScroll")
        for key in ("stale", "low_coverage", "no_sale"):
            category = self.item("stockAlertCategory_" + key)
            self.reveal(category)
            point = category.mapToItem(viewport, QPointF())
            self.assertGreaterEqual(point.x(), -1, key)
            self.assertLessEqual(point.x() + category.width(), viewport.width() + 1, key)
        dialog = self.open_settings()
        self.assertTrue(self.dialog_visible_rect(dialog, self.item("stockAlertStaleDays")))
        for name in ("stockAlertCoverageDays", "stockAlertDefaults", "stockAlertCancel", "stockAlertApply"):
            QTest.keyClick(self.window, Qt.Key.Key_Tab)
            control = self.item(name)
            self.assertTrue(pump(control.hasActiveFocus), name)
            self.assertTrue(pump(lambda: self.dialog_visible_rect(dialog, control)), name)
        QTest.keyClick(self.window, Qt.Key.Key_Backtab)
        self.assertTrue(pump(lambda: self.item("stockAlertCancel").hasActiveFocus()))
        QTest.keyClick(self.window, Qt.Key.Key_Space)
        self.assertTrue(pump(lambda: not dialog.property("visible")))
        self.assertTrue(pump(lambda: self.item("stockAlertSettingsButton").hasActiveFocus()))
        self.assertEqual(self.bundle.messages, [])
