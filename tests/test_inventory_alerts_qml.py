"""Stock review rules remain editable and usable in the real Qt workspace."""

from dataclasses import replace
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from PySide6.QtCore import QObject, QPointF, QSettings, Qt
from PySide6.QtTest import QTest

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
        scroll = self.item("stockScroll")
        point = item.mapToItem(scroll, QPointF())
        target = scroll.property("contentY") + point.y() - 30
        maximum = max(0, scroll.property("contentHeight") - scroll.height())
        scroll.setProperty("contentY", max(0, min(maximum, target)))
        self.window.update()
        APP.processEvents()

    def open_settings(self):
        button = self.item("stockAlertSettingsButton")
        self.reveal(button)
        click(self.window, button)
        dialog = self.item("stockAlertSettingsDialog")
        self.assertTrue(pump(lambda: dialog.property("opened")))
        self.assertTrue(pump(lambda: self.item("stockAlertStaleDays").hasActiveFocus()))
        return dialog

    def set_text(self, item, text):
        item.forceActiveFocus(Qt.FocusReason.TabFocusReason)
        QTest.keyClick(self.window, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        QTest.keyClick(self.window, Qt.Key.Key_Backspace)
        for character in text:
            QTest.keyClick(self.window, Qt.Key(ord(character)))
        APP.processEvents()

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

    def test_category_and_alert_click_filter_the_exact_product_branch_and_unit(self):
        self.load()
        self.assertFalse(self.item("stockAlerts").property("showOccurrences"))
        low = self.item("stockAlertCategory_low_coverage")
        self.reveal(low)
        click(self.window, low)
        self.assertTrue(self.item("stockAlerts").property("showOccurrences"))
        row = self.item("stockAlertRow0")
        model = row.property("modelData")
        model = model.toVariant() if hasattr(model, "toVariant") else model
        self.assertEqual(model["code"], "0001")
        self.reveal(row)
        with patch.object(self.bundle.controller._provider, "query") as query:
            click(self.window, row)
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
        self.reveal(category)
        click(self.window, category)
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
