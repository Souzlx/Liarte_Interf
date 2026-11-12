"""Native V6 shell and export-anchor regressions with isolated test data."""

import unittest

from PySide6.QtCore import QMetaObject, QPointF, Qt
from PySide6.QtTest import QTest

from tests.test_comex import click
from tests.test_platform import PlatformUiTests
from tests.test_qt import APP, pump, settled


class RedesignVisualTests(unittest.TestCase):
    setUp = PlatformUiTests.setUp
    tearDown = PlatformUiTests.tearDown
    item = PlatformUiTests.item
    load = PlatformUiTests.load

    def settle(self):
        self.window.update()
        pump(timeout=0.08)

    def assert_inside(self, child, parent):
        point = child.mapToItem(parent, QPointF())
        self.assertGreaterEqual(point.x(), -1)
        self.assertGreaterEqual(point.y(), -1)
        self.assertLessEqual(point.x() + child.width(), parent.width() + 1)
        self.assertLessEqual(point.y() + child.height(), parent.height() + 1)

    def test_native_shell_does_not_overlap_at_supported_viewports(self):
        for width, height in ((500, 400), (1366, 768), (1600, 900), (1920, 1080)):
            with self.subTest(viewport=(width, height)):
                self.window.resize(width, height)
                self.settle()
                topbar, sidebar, stack = (self.item(name) for name in ("topbar", "sidebar", "moduleStack"))
                viewport = self.window.contentItem()
                for child in (topbar, sidebar, stack):
                    self.assert_inside(child, viewport)
                sidebar_position = sidebar.mapToItem(viewport, QPointF())
                stack_position = stack.mapToItem(viewport, QPointF())
                self.assertGreaterEqual(sidebar_position.y(), topbar.height() - 1)
                self.assertGreaterEqual(stack_position.y(), topbar.height() - 1)
                self.assertGreaterEqual(stack_position.x(), sidebar_position.x() + sidebar.width() - 1)
                self.assertEqual(sidebar.property("color").name(), "#101d31")
                self.assertFalse(self.window.grabWindow().isNull())
        self.assertEqual(self.bundle.messages, [])

    def assert_export_popup(self, button):
        click(self.window, button)
        menu = self.item("quickExportMenu")
        self.assertTrue(pump(lambda: menu.property("opened")))
        content = menu.property("contentItem")
        self.assert_inside(content, self.window.contentItem())
        self.assertTrue(self.item("quickExcel").property("enabled"))
        self.assertTrue(self.item("quickPowerBI").property("enabled"))
        self.assertIn("período completo", self.item("quickExcel").property("text"))
        self.assertIn("período completo", self.item("quickPowerBI").property("text"))
        QTest.keyClick(self.window, Qt.Key.Key_Escape)
        self.assertTrue(pump(lambda: not menu.property("visible")))

    def test_page_and_topbar_export_anchors_stay_inside_compact_and_wide_window(self):
        self.load()
        self.bundle.preferences.setPreference("reducedMotion", True)
        for width, height in ((500, 400), (1366, 768), (1920, 1080)):
            with self.subTest(viewport=(width, height)):
                self.window.resize(width, height)
                self.settle()
                self.assert_export_popup(self.item("importPageExport"))
                self.assert_export_popup(self.item("quickExportButton"))
        # Existing native callers must retain the original no-argument slot.
        self.assertTrue(QMetaObject.invokeMethod(self.item("importsWorkspace"), "openExportMenu"))
        self.assertTrue(pump(lambda: self.item("quickExportMenu").property("opened")))
        QTest.keyClick(self.window, Qt.Key.Key_Escape)
        self.assertTrue(pump(lambda: not self.item("quickExportMenu").property("visible")))
        self.assertEqual(self.bundle.messages, [])

    def test_local_export_respects_period_draft_and_municipal_pdf_gate(self):
        self.load()
        page_export = self.item("importPageExport")
        self.assertTrue(page_export.property("enabled"))
        start = self.item("startPeriod")
        start.setProperty("currentIndex", start.property("currentIndex") - 1)
        APP.processEvents()
        self.assertTrue(self.item("importsWorkspace").property("draftPeriod"))
        self.assertFalse(page_export.property("enabled"))
        self.assertFalse(self.item("quickExportButton").property("enabled"))
        self.controller.queryPeriod("2026-08", "2026-09")
        settled(self.controller)
        self.assertFalse(self.item("importsWorkspace").property("draftPeriod"))
        self.assertTrue(page_export.property("enabled"))
        self.controller.setDataset("municipal")
        settled(self.controller)
        self.assertTrue(page_export.property("enabled"))
        self.assert_export_popup(page_export)
        self.assertFalse(self.item("quickPDF").property("enabled"))
        self.assertIn("Dados gerais", self.item("quickPDF").property("text"))
        self.assertEqual(self.bundle.messages, [])

    def test_metric_labels_values_and_details_fit_inside_their_cards(self):
        self.load()
        self.bundle.preferences.setPreference("reducedMotion", True)
        workspace = self.item("importsWorkspace")
        for width, height in ((500, 400), (1366, 768), (1920, 1080)):
            self.window.resize(width, height)
            for section, prefix in (("summary", "metricCard"), ("buying", "buyingMetric")):
                with self.subTest(viewport=(width, height), section=section):
                    workspace.setProperty("activeSection", section)
                    self.settle()
                    for index in range(4):
                        card = self.item(prefix + str(index))
                        metric = card.property("displayMetric").toVariant()
                        pending = list(card.childItems())
                        texts = []
                        while pending:
                            child = pending.pop()
                            pending.extend(child.childItems())
                            if child.property("text") in (
                                metric["label"], metric["value"], metric["detail"]
                            ) and child.property("text"):
                                texts.append(child)
                        self.assertEqual(len(texts), 3)
                        for text in texts:
                            self.assert_inside(text, card)
                            point = text.mapToItem(card, QPointF())
                            self.assertGreaterEqual(point.x(), 12)
                            self.assertGreaterEqual(point.y(), 12)
                            self.assertLessEqual(point.y() + text.height(), card.height() - 12)
                        value = self.item(prefix + str(index) + "Value")
                        detail = next(text for text in texts if text.property("text") == metric["detail"])
                        self.assertGreaterEqual(
                            detail.mapToItem(card, QPointF()).y(),
                            value.mapToItem(card, QPointF()).y() + value.height() + 4,
                        )
        self.assertEqual(self.bundle.messages, [])

    def test_period_summary_keeps_the_accepted_dates_and_keyboard_editing(self):
        self.load()
        self.bundle.preferences.setPreference("reducedMotion", True)
        for kind in ("general", "municipal"):
            self.controller.setDataset(kind)
            settled(self.controller)
            self.settle()
            self.assertEqual(
                self.item("importAppliedPeriod").property("text"),
                self.controller.presentation["periodLabel"],
            )
            edit = self.item("editImportPeriod")
            edit.forceActiveFocus(Qt.FocusReason.TabFocusReason)
            QTest.keyClick(self.window, Qt.Key.Key_Space)
            self.assertTrue(pump(lambda: self.item("startPeriod").isVisible()))
            self.assertTrue(self.item("endPeriod").isVisible())
            QTest.keyClick(self.window, Qt.Key.Key_Space)
            self.assertTrue(pump(lambda: not self.item("startPeriod").isVisible()))
        self.assertEqual(self.bundle.messages, [])
