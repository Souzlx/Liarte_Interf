"""Whole stock drafts apply once; reading UI status never copies fact series."""

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import PropertyMock, patch

from PySide6.QtCore import QPointF, Qt, QUrl
from PySide6.QtTest import QSignalSpy, QTest

from liarte_core.inventory_io import write_snapshot
from liarte_desktop.inventory import InventoryController
from tests import test_inventory, test_inventory_alerts_qml as stock_qml
from tests.test_qt import pump


def variant(value):
    return value.toVariant() if hasattr(value, "toVariant") else value


class UXStockFilterControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.c = InventoryController()
        self.addCleanup(self.c.shutdown)
        path = Path(self.temp.name).resolve() / "filters.liarte"
        write_snapshot(test_inventory.sample(), path)
        self.c.openFile(QUrl.fromLocalFile(str(path)))
        self.idle()
        self.assertTrue(self.c.presentation["loaded"])

    def idle(self):
        self.assertTrue(pump(
            lambda: not self.c.presentation["busy"] and not self.c._debounce.isActive(), 15
        ), self.c.presentation)

    def test_draft_replaces_multiple_fields_with_one_generation_and_one_analysis(self):
        before = self.c.presentation["selection"]
        generation = self.c._generation
        publications = QSignalSpy(self.c.analysisChanged)
        changed = QSignalSpy(self.c.changed)
        self.assertTrue(self.c.applyFilters({
            "start": "2026-02", "end": "2026-03", "unit": "KG", "branch": "01",
        }))
        self.assertEqual(self.c._generation, generation + 1)
        self.assertEqual(changed.count(), 1)
        self.assertEqual(self.c.presentation["appliedSelection"], before)
        self.assertFalse(self.c.presentation["current"])
        self.idle()
        self.assertEqual(publications.count(), 1)
        self.assertEqual(self.c.presentation["appliedSelection"]["unit"], "KG")
        self.assertEqual(self.c.presentation["selection"]["start"], "2026-02")
        self.assertTrue(self.c.presentation["current"])

    def test_invalid_drafts_do_not_touch_accepted_results_or_schedule_work(self):
        before = self.c.presentation
        analysis, monthly = self.c._analysis, self.c._monthly_data
        generation = self.c._generation
        changed = QSignalSpy(self.c.changed)
        for draft in (
            {"start": "2026-03", "end": "2026-01"}, {"unit": "INVALID"},
            {"branch": "99"}, {"unrecognized": "value"}, {"unit": 1},
            {"product": "0001", "search": "solvente"}, {"search": "x" * 201},
        ):
            with self.subTest(draft=draft):
                self.assertFalse(self.c.applyFilters(draft))
                self.assertTrue(self.c.filterState["error"])
                self.assertEqual(self.c.presentation["selection"], before["selection"])
                self.assertEqual(self.c._generation, generation)
                self.assertIs(self.c._analysis, analysis)
                self.assertIs(self.c._monthly_data, monthly)
                self.assertFalse(self.c._debounce.isActive())
                self.assertFalse(self.c.presentation["busy"])
        self.assertEqual(changed.count(), 0)

    def test_unchanged_draft_can_clear_error_without_recomputing(self):
        self.assertFalse(self.c.applyFilters({"unit": "INVALID"}))
        generation = self.c._generation
        publications = QSignalSpy(self.c.analysisChanged)
        self.assertTrue(self.c.applyFilters(self.c.presentation["selection"]))
        self.assertEqual(self.c.filterState["error"], "")
        self.assertEqual(self.c._generation, generation)
        self.assertFalse(self.c._debounce.isActive())
        self.assertEqual(publications.count(), 0)

    def test_product_and_text_are_exclusive_without_scanning_gui_product_options(self):
        with patch.object(InventoryController, "options", new_callable=PropertyMock,
                          side_effect=AssertionError("Full option list scanned on GUI")):
            self.assertTrue(self.c.applyFilters({"product": "0001"}))
            self.idle()
            self.assertEqual(self.c.presentation["selection"]["product"], "0001")
            self.assertTrue(self.c.applyFilters({"search": "solvente"}))
            self.idle()
        self.assertEqual(self.c.presentation["selection"]["product"], "")
        self.assertEqual(self.c.presentation["selection"]["search"], "solvente")
        self.assertNotIn("product", {group["key"] for group in self.c.filterOptions})
        self.assertIn("product", {group["key"] for group in self.c.options})

    def test_cancel_restores_whole_accepted_selection(self):
        before = self.c.presentation["selection"]
        self.assertTrue(self.c.applyFilters({"unit": "KG", "end": "2026-02"}))
        self.c.cancel()
        self.idle()
        self.assertEqual(self.c.presentation["selection"], before)
        self.assertEqual(self.c.presentation["appliedSelection"], before)
        self.assertTrue(self.c.presentation["current"])

    def test_light_presentation_does_not_iterate_series_or_copy_selected_history(self):
        class NotForStatus:
            def __iter__(self):
                raise AssertionError("Series copied by lightweight status")

        self.c._analysis = replace(
            self.c._analysis, metrics=NotForStatus(), trend=NotForStatus(),
            ranking=NotForStatus(), activity=NotForStatus(),
        )
        self.c._detail = {"salesTrend": NotForStatus()}
        for _ in range(10):
            view = self.c.presentation
            self.c.changed.emit()
            self.assertTrue(view["loaded"])
            self.assertTrue(view["current"])
            for key in ("metrics", "trend", "ranking", "activityChart", "detail"):
                self.assertNotIn(key, view)
        with self.assertRaisesRegex(AssertionError, "lightweight status"):
            _ = self.c.state


class UXStockFilterDialogTests(unittest.TestCase):
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

    def open(self):
        self.click_workspace(self.item("stockRefineFilters"))
        dialog = self.item("stockFiltersDialog")
        self.assertTrue(pump(lambda: dialog.property("opened")))
        return dialog

    def click_dialog(self, control):
        viewport = self.item("stockFiltersDialog").property("bodyViewport")
        point = control.mapToItem(viewport, QPointF())
        maximum = max(0, viewport.property("contentHeight") - viewport.height())
        viewport.setProperty("contentY", max(0, min(maximum, viewport.property("contentY") + point.y() - 12)))
        self.window.grabWindow()
        control.forceActiveFocus(Qt.FocusReason.TabFocusReason)
        activated = QSignalSpy(control.clicked)
        QTest.keyClick(self.window, Qt.Key.Key_Space)
        self.assertEqual(activated.count(), 1)

    def test_closing_or_cancelling_draft_preserves_all_filters(self):
        self.load()
        before = self.c.presentation["selection"]
        dialog = self.open()
        draft = dict(variant(dialog.property("draft")), unit="KG", warehouse="02")
        dialog.setProperty("draft", draft)
        self.assertEqual(self.c.presentation["selection"], before)
        QTest.keyClick(self.window, Qt.Key.Key_Escape)
        self.assertTrue(pump(lambda: not dialog.property("visible")))
        self.assertEqual(self.c.presentation["selection"], before)
        self.open()
        self.assertEqual(variant(dialog.property("draft")), before)
        self.click_dialog(self.item("stockFiltersCancel"))
        self.assertTrue(pump(lambda: not dialog.property("visible")))
        self.assertEqual(self.c.presentation["selection"], before)
        self.assertEqual(self.bundle.messages, [])

    def test_apply_publishes_one_complete_draft_and_invalid_period_is_explained(self):
        self.load()
        dialog = self.open()
        before = self.c.presentation["selection"]
        dialog.setProperty("draft", dict(before, start="2026-03", end="2026-01"))
        self.assertFalse(self.item("stockFiltersApply").isEnabled())
        self.assertTrue(self.item("stockFiltersPeriodNotice").isVisible())
        self.assertEqual(self.c.presentation["selection"], before)
        dialog.setProperty("draft", dict(before, start="2026-02", end="2026-03", unit="KG"))
        count = QSignalSpy(self.c.analysisChanged)
        self.click_dialog(self.item("stockFiltersApply"))
        self.assertTrue(pump(lambda: not dialog.property("visible")))
        self.idle()
        self.assertEqual(count.count(), 1)
        self.assertEqual(self.c.presentation["appliedSelection"]["unit"], "KG")
        self.assertIn("02/2026", self.item("stockAppliedScope").property("text"))
        self.assertEqual(self.bundle.messages, [])

    def test_compact_dialog_keeps_choices_reachable_with_wide_fonts(self):
        self.load()
        self.window.resize(500, 400)
        dialog = self.open()
        viewport = dialog.property("bodyViewport")
        for name in ("stockDraft_start", "stockDraft_end", "stockDraft_unit", "stockFiltersApply"):
            control = self.item(name)
            font = control.property("font")
            font.setStretch(150)
            control.setProperty("font", font)
            control.forceActiveFocus(Qt.FocusReason.TabFocusReason)
            self.assertTrue(pump(lambda: (
                control.mapToItem(viewport, QPointF()).y() >= -1
                and control.mapToItem(viewport, QPointF()).y() + control.height() <= viewport.height() + 1
            )), name)
            point = control.mapToItem(viewport, QPointF())
            self.assertGreaterEqual(point.x(), -1, name)
            self.assertLessEqual(point.x() + control.width(), viewport.width() + 1, name)
        self.assertEqual(self.bundle.messages, [])
