"""Previous stock bases remain an explicit, accessible restore choice."""

from dataclasses import replace
from datetime import timedelta
from threading import Event
import unittest
from unittest.mock import patch

from PySide6.QtCore import QPointF, Qt, QUrl
from PySide6.QtTest import QSignalSpy, QTest

from liarte_core.inventory_io import write_snapshot
from liarte_core.query import checkpoint
from tests import test_platform
from tests.test_inventory import sample
from tests.test_qt import APP, click, pump


class InventoryBackupQmlTests(unittest.TestCase):
    item = test_platform.PlatformUiTests.item

    def setUp(self):
        test_platform.PlatformUiTests.setUp(self)
        self.inventory = self.bundle.inventory
        self.cache = self.directory / "cache/base.liarte"
        self.cache.parent.mkdir()
        self.inventory._cache = self.cache
        self.inventory._bundled = None
        self.inventory._restored = True
        self.inventory.backupChanged.emit()
        self.bundle.preferences.setPreference("reducedMotion", True)
        self.loads = 0

    def tearDown(self):
        self.inventory.shutdown()
        test_platform.PlatformUiTests.tearDown(self)

    def idle(self):
        self.assertTrue(
            pump(
                lambda: not self.inventory.state["busy"]
                and not self.inventory._debounce.isActive(),
                15,
            ),
            self.inventory.state,
        )

    def load_stock(self, index=0):
        original = sample()
        data = replace(
            original,
            as_of=original.as_of + timedelta(days=index),
            source_name=f"Base {index}.pbix",
            source_hash=f"{index + 1:064x}",
            balances=tuple(replace(row, cost=row.cost + index * 100) for row in original.balances),
        )
        path = self.directory / f"source-{self.loads}.liarte"
        self.loads += 1
        write_snapshot(data, path)
        self.inventory.openFile(QUrl.fromLocalFile(str(path)))
        self.idle()
        self.assertFalse(self.inventory.state["error"])
        return data

    def open_backups(self):
        self.platform.openModule("inventory")
        self.window.update()
        self.idle()
        self.assertTrue(pump(self.header_ready), self.header_geometry())
        # Wait for a frame at the resized client size, rather than assuming a
        # fixed delay is enough for native window/layout updates on Windows.
        frame = self.window.grabWindow()
        self.assertFalse(frame.isNull(), self.header_geometry())
        self.assertAlmostEqual(
            frame.width() / self.window.devicePixelRatio(), self.window.width(), delta=1
        )
        click(self.window, self.item("stockRestoreButton"))
        dialog = self.item("stockBackupsDialog")
        self.assertTrue(pump(lambda: dialog.property("opened")), self.header_geometry())
        self.idle()
        return dialog

    def header_geometry(self):
        viewport = self.item("stockScroll")
        actions = {}
        for name in (
            "openStockBase",
            "stockExportButton",
            "stockRestoreButton",
            "stockMethodologyButton",
        ):
            item = self.item(name)
            point = item.mapToItem(viewport, QPointF())
            actions[name] = {
                "rect": (point.x(), point.y(), item.width(), item.height()),
                "visible": item.isVisible(),
                "enabled": item.isEnabled(),
                "naturalWidth": item.property("naturalWidth"),
                "font": item.property("font").toString(),
            }
        return {
            "window": (self.window.width(), self.window.height()),
            "content": (self.window.contentItem().width(), self.window.contentItem().height()),
            "viewport": (viewport.width(), viewport.height()),
            "busy": self.inventory.state["busy"],
            "actions": actions,
        }

    def header_ready(self):
        geometry = self.header_geometry()
        width, height = geometry["viewport"]
        if abs(geometry["window"][0] - geometry["content"][0]) > 1:
            return False
        for item in geometry["actions"].values():
            x, y, w, h = item["rect"]
            if not item["visible"] or not item["enabled"] or w <= 0 or h <= 0:
                return False
            if x < -1 or y < -1 or x + w > width + 1 or y + h > height + 1:
                return False
        return True

    def choose_first(self):
        click(self.window, self.item("stockBackupChoice0"))
        self.assertTrue(self.item("reviewStockRestore").isEnabled())
        click(self.window, self.item("reviewStockRestore"))
        self.assertTrue(pump(lambda: self.item("confirmStockRestoreDialog").property("opened")))
        self.assertTrue(pump(lambda: self.item("cancelStockRestore").width() > 0))

    def test_restore_action_explains_missing_history_and_requires_selection(self):
        self.load_stock()
        dialog = self.open_backups()
        self.assertIn("Nenhuma base anterior", self.item("stockBackupsStatus").property("text"))
        self.assertFalse(self.item("reviewStockRestore").isEnabled())
        self.assertTrue(self.item("inventoryWorkspace").property("modalOpen"))
        self.assertEqual(self.bundle.messages, [])
        QTest.keyClick(self.window, Qt.Key.Key_Escape)
        self.assertTrue(pump(lambda: not dialog.property("visible")))

    def test_no_cache_disables_restore_and_navigation_does_not_refresh_history(self):
        self.inventory._cache = None
        self.inventory.backupChanged.emit()
        self.platform.openModule("inventory")
        APP.processEvents()
        self.assertFalse(self.item("stockRestoreButton").isEnabled())
        self.assertEqual(self.inventory.backupState["items"], [])
        changes = QSignalSpy(self.inventory.backupChanged)
        for module in ("home", "imports", "inventory", "home", "inventory"):
            self.platform.openModule(module)
            APP.processEvents()
        self.assertEqual(changes.count(), 0)
        self.assertFalse(self.inventory.state["busy"])
        self.assertEqual(self.bundle.messages, [])

    def test_cancel_confirmation_keeps_current_base_and_restore_is_explicit(self):
        previous, current = self.load_stock(0), self.load_stock(1)
        dialog = self.open_backups()
        before = self.cache.read_bytes()
        self.choose_first()
        self.assertTrue(pump(lambda: self.item("cancelStockRestore").hasActiveFocus()))
        QTest.keyClick(self.window, Qt.Key.Key_Space)
        self.assertTrue(
            pump(lambda: not self.item("confirmStockRestoreDialog").property("visible"))
        )
        self.assertEqual(self.cache.read_bytes(), before)
        self.assertEqual(self.inventory._data.source_name, current.source_name)
        self.assertTrue(dialog.property("visible"))
        self.choose_first()
        click(self.window, self.item("confirmStockRestore"))
        self.idle()
        self.assertEqual(self.inventory._data.source_name, previous.source_name)
        self.assertEqual(self.inventory.state["asOf"], previous.as_of.strftime("%d/%m/%Y"))
        self.assertIn("restaurad", self.item("stockBackupsStatus").property("text").casefold())
        self.assertTrue(dialog.property("visible"))
        self.assertIn(
            current.source_name, [row["source"] for row in self.inventory.backupState["items"]]
        )
        self.assertEqual(self.bundle.messages, [])

    def test_cancel_busy_restore_keeps_current_base_and_exposes_progress(self):
        self.load_stock(0)
        current = self.load_stock(1)
        self.open_backups()
        self.choose_first()
        before = self.cache.read_bytes()
        entered = Event()

        def wait_for_cancel(cache, backup_id, cancel):
            entered.set()
            self.assertTrue(cancel.wait(5), "Restore did not receive cancellation")
            checkpoint(cancel)

        try:
            with patch("liarte_desktop.inventory.load_backup", side_effect=wait_for_cancel):
                click(self.window, self.item("confirmStockRestore"))
                self.assertTrue(pump(entered.is_set))
                self.assertTrue(self.item("stockBackupsProgress").isVisible())
                self.assertTrue(self.item("cancelStockBackupTask").isVisible())
                self.assertFalse(self.item("reviewStockRestore").isEnabled())
                self.assertIn("Restaurando", self.item("stockBackupsStatus").property("text"))
                self.assertTrue(pump(lambda: self.item("cancelStockBackupTask").width() > 0))
                click(self.window, self.item("cancelStockBackupTask"))
                self.idle()
            self.assertEqual(self.cache.read_bytes(), before)
            self.assertEqual(self.inventory._data.source_name, current.source_name)
            self.assertFalse(self.inventory.backupState["error"])
            self.assertEqual(self.bundle.messages, [])
        finally:
            self.inventory.cancel()

    def test_failed_restore_displays_error_and_keeps_loaded_base(self):
        self.load_stock(0)
        current = self.load_stock(1)
        self.open_backups()
        self.choose_first()
        snapshots = list((self.cache.parent / "backups").rglob("*.liarte"))
        self.assertTrue(snapshots)
        for path in snapshots:
            path.write_bytes(b"invalid stock backup")
        before = self.cache.read_bytes()
        click(self.window, self.item("confirmStockRestore"))
        self.idle()
        self.assertTrue(self.inventory.backupState["error"])
        self.assertEqual(
            self.item("stockBackupsStatus").property("text"), self.inventory.backupState["error"]
        )
        self.assertEqual(self.cache.read_bytes(), before)
        self.assertEqual(self.inventory._data.source_name, current.source_name)
        self.assertTrue(self.item("stockBackupsDialog").property("visible"))
        self.assertEqual(self.bundle.messages, [])

    def test_compact_dialog_reveals_keyboard_selection_and_confirmation(self):
        for index in range(4):
            self.load_stock(index)
        self.window.resize(500, 400)
        dialog = self.open_backups()
        choice = self.item("stockBackupChoice0")
        choice.forceActiveFocus()
        pump(timeout=0.08)
        for index in range(3):
            choice = self.item(f"stockBackupChoice{index}")
            self.assertTrue(choice.hasActiveFocus())
            viewport = dialog.property("bodyViewport")
            point = choice.mapToItem(viewport, QPointF())
            self.assertGreaterEqual(point.y(), -1)
            self.assertLessEqual(point.y() + choice.height(), viewport.height() + 1)
            QTest.keyClick(self.window, Qt.Key.Key_Space)
            self.assertTrue(choice.property("checked"))
            QTest.keyClick(self.window, Qt.Key.Key_Tab)
            pump(timeout=0.08)
        review = self.item("reviewStockRestore")
        self.assertTrue(review.hasActiveFocus())
        point = review.mapToItem(dialog.property("bodyViewport"), QPointF())
        self.assertGreaterEqual(point.y(), -1)
        self.assertLessEqual(
            point.y() + review.height(), dialog.property("bodyViewport").height() + 1
        )
        QTest.keyClick(self.window, Qt.Key.Key_Space)
        self.assertTrue(pump(lambda: self.item("confirmStockRestoreDialog").property("opened")))
        self.assertEqual(self.bundle.messages, [])

    def test_compact_header_wraps_wide_font_actions_and_restore_remains_clickable(self):
        self.load_stock()
        for name in ("openStockBase", "stockExportButton"):
            item = self.item(name)
            font = item.property("font")
            font.setStretch(200)
            item.setProperty("font", font)
        self.window.resize(500, 400)
        dialog = self.open_backups()
        self.assertTrue(self.header_ready(), self.header_geometry())
        self.assertEqual(self.item("stockHeaderActions").property("columns"), 2)
        self.assertTrue(dialog.property("visible"))
        self.assertEqual(self.bundle.messages, [])
