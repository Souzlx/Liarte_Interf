"""Real Qt stock cache updates preserve and restore verified previous bases."""

from dataclasses import replace
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import os
import unittest
from unittest.mock import patch

from PySide6.QtCore import QThread, QUrl

from liarte_core.inventory_backup import list_backups
from liarte_core.inventory_io import read_snapshot, write_snapshot
from liarte_desktop import inventory as desktop
from tests.test_inventory import sample
from tests.test_qt import APP, pump


def updated(data=None, *, source="Base atualizada.pbix", digest="b"):
    data = data or sample()
    return replace(
        data,
        source_name=source,
        source_hash=digest * 64,
        balances=tuple(replace(balance, cost=balance.cost + 100) for balance in data.balances),
    )


class InventoryBackupUiTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.cache = self.directory / "profile/estoque/base.liarte"
        self.original = sample()
        self.new = updated()
        self.source = self.directory / "new.liarte"
        write_snapshot(self.original, self.cache)
        write_snapshot(self.new, self.source)
        self.c = desktop.InventoryController(cache_path=self.cache)
        self.addCleanup(self.c.shutdown)
        self.c.ensureLoaded()
        self.idle()

    def idle(self):
        self.assertTrue(
            pump(lambda: not self.c.state["busy"] and not self.c._debounce.isActive(), 10),
            self.c.state,
        )

    def update(self):
        self.c.openFile(QUrl.fromLocalFile(str(self.source)))
        self.idle()

    def test_update_backs_up_previous_valid_base_and_restore_preserves_replaced_base(self):
        self.assertEqual(self.c.backupState["items"], [])
        self.update()
        self.assertEqual(read_snapshot(self.cache), self.new)
        self.assertEqual(self.c._data, self.new)
        entries = self.c.backupState["items"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["source"], self.original.source_name)
        self.assertEqual(entries[0]["asOf"], "15/04/2026")
        self.assertEqual(entries[0]["products"], 3)
        self.assertNotIn("path", entries[0])
        self.assertNotIn("sha256", entries[0])
        self.c.restoreBackup(entries[0]["id"])
        self.idle()
        self.assertEqual(self.c._data, self.original)
        self.assertEqual(read_snapshot(self.cache), self.original)
        self.assertEqual(self.c.backupState["notice"], "Base anterior restaurada.")
        entries = self.c.backupState["items"]
        self.assertEqual(
            {entry["source"] for entry in entries},
            {self.original.source_name, self.new.source_name},
        )
        self.assertEqual(self.c.state["error"], "")
        fresh = desktop.InventoryController(cache_path=self.cache)
        try:
            fresh.ensureLoaded()
            self.assertTrue(pump(lambda: not fresh.state["busy"]))
            self.assertEqual(fresh._data, self.original)
            self.assertEqual(len(fresh.backupState["items"]), 2)
        finally:
            fresh.shutdown()

    def test_identical_update_does_not_create_a_redundant_backup(self):
        write_snapshot(self.original, self.source)
        self.update()
        self.assertEqual(read_snapshot(self.cache), self.original)
        self.assertEqual(self.c.backupState["items"], [])
        self.assertEqual(list_backups(self.cache), ())

    def test_backup_failure_blocks_update_and_preserves_memory_and_current_cache(self):
        previous = self.cache.read_bytes()
        with patch.object(desktop, "backup_previous", side_effect=OSError("backup disk full")):
            self.update()
        self.assertEqual(self.cache.read_bytes(), previous)
        self.assertEqual(self.c._data, self.original)
        self.assertTrue(self.c.state["error"])
        self.assertEqual(list(self.cache.parent.glob(".base-*.liarte")), [])

    def test_cancel_after_backup_keeps_current_base_and_does_not_prune(self):
        entered, release = Event(), Event()
        original = desktop.backup_previous

        def delayed(*args, **kwargs):
            result = original(*args, **kwargs)
            entered.set()
            if not release.wait(3):
                raise RuntimeError("Test did not release backup worker")
            return result

        previous = self.cache.read_bytes()
        try:
            with (
                patch.object(desktop, "backup_previous", side_effect=delayed),
                patch.object(desktop, "prune_backups") as prune,
            ):
                self.c.openFile(QUrl.fromLocalFile(str(self.source)))
                self.assertTrue(pump(entered.is_set))
                self.c.cancel()
                release.set()
                self.idle()
                prune.assert_not_called()
            self.assertEqual(self.cache.read_bytes(), previous)
            self.assertEqual(self.c._data, self.original)
            self.assertEqual(len(list_backups(self.cache)), 1)
            self.assertEqual(list(self.cache.parent.glob(".base-*.liarte")), [])
        finally:
            release.set()

    def test_corrupt_backup_cannot_replace_loaded_base(self):
        self.update()
        item = self.c.backupState["items"][0]
        backup = list_backups(self.cache)[0]
        backup.path.write_bytes(b"corrupted")
        previous = self.cache.read_bytes()
        self.c.restoreBackup(item["id"])
        self.idle()
        self.assertEqual(self.cache.read_bytes(), previous)
        self.assertEqual(self.c._data, self.new)
        self.assertTrue(self.c.backupState["error"])
        self.assertTrue(self.c.state["error"])

    def test_unknown_identifier_is_rejected_without_reading_a_user_path(self):
        with patch.object(desktop, "load_backup") as load:
            self.c.restoreBackup("../base.liarte")
            load.assert_not_called()
        self.assertTrue(self.c.backupState["error"])
        self.assertEqual(self.c._data, self.original)

    def test_listing_failure_does_not_prevent_loading_the_valid_current_base(self):
        another = desktop.InventoryController(cache_path=self.cache)
        try:
            with patch.object(
                desktop, "list_backups", side_effect=PermissionError("folder locked")
            ):
                another.ensureLoaded()
                self.assertTrue(pump(lambda: not another.state["busy"]))
            self.assertEqual(another._data, self.original)
            self.assertEqual(another.state["error"], "")
            self.assertTrue(another.backupState["error"])
        finally:
            another.shutdown()

    def test_invalid_cache_recovers_bundled_base_even_when_history_storage_is_invalid(self):
        self.cache.write_bytes(b"corrupt cache")
        self.source.with_suffix(".json").write_text(
            json.dumps({"sha256": hashlib.sha256(self.source.read_bytes()).hexdigest()}),
            encoding="utf-8",
        )
        history = self.cache.parent / "backups"
        history.write_bytes(b"a file occupies the history folder")
        another = desktop.InventoryController(cache_path=self.cache, bundled_path=self.source)
        try:
            another.ensureLoaded()
            self.assertTrue(pump(lambda: not another.state["busy"], 10))
            self.assertEqual(another._data.balances, self.new.balances)
            self.assertEqual(read_snapshot(self.cache).balances, self.new.balances)
            self.assertEqual(another.state["error"], "")
            self.assertTrue(another.backupState["error"])
            self.assertIn("recuperada", " ".join(another.state["notes"]))
            self.assertEqual(history.read_bytes(), b"a file occupies the history folder")
        finally:
            another.shutdown()

    def test_retention_failure_warns_after_successful_update_without_rolling_back(self):
        with patch.object(desktop, "prune_backups", side_effect=OSError("old backup locked")):
            self.update()
        self.assertEqual(self.c._data, self.new)
        self.assertEqual(read_snapshot(self.cache), self.new)
        self.assertEqual(self.c.state["error"], "")
        self.assertTrue(self.c.backupState["error"])
        self.assertEqual(len(self.c.backupState["items"]), 1)

    def test_backup_copy_listing_and_retention_run_on_worker_threads(self):
        threads = {name: [] for name in ("backup_previous", "list_backups", "prune_backups")}

        def observed(name, original):
            def invoke(*args, **kwargs):
                threads[name].append(QThread.currentThread() == APP.thread())
                if name == "prune_backups":
                    self.assertEqual(read_snapshot(self.cache), self.new)
                return original(*args, **kwargs)

            return invoke

        with (
            patch.object(
                desktop,
                "backup_previous",
                side_effect=observed("backup_previous", desktop.backup_previous),
            ),
            patch.object(
                desktop, "list_backups", side_effect=observed("list_backups", desktop.list_backups)
            ),
            patch.object(
                desktop,
                "prune_backups",
                side_effect=observed("prune_backups", desktop.prune_backups),
            ),
        ):
            self.update()
        for name, values in threads.items():
            self.assertTrue(values, name)
            self.assertFalse(any(values), name)

    def test_publication_failure_never_prunes_or_replaces_the_previous_cache(self):
        original = os.replace

        def replace_file(source, target):
            if Path(target) == self.cache:
                raise PermissionError("cache is locked")
            return original(source, target)

        with (
            patch.object(desktop.os, "replace", side_effect=replace_file),
            patch.object(desktop, "prune_backups") as prune,
        ):
            self.update()
            prune.assert_not_called()
        self.assertEqual(read_snapshot(self.cache), self.original)
        self.assertEqual(self.c._data, self.original)
        self.assertEqual(len(list_backups(self.cache)), 1)
        self.assertTrue(self.c.state["error"])

    def test_other_writer_changing_cache_before_gui_commit_is_preserved(self):
        external = updated(source="Outra operação.pbix", digest="c")
        external_path = self.directory / "external.liarte"
        write_snapshot(external, external_path)
        original = desktop._read_backup_items

        def replace_after_read(*args, **kwargs):
            result = original(*args, **kwargs)
            os.replace(external_path, self.cache)
            return result

        with (
            patch.object(desktop, "_read_backup_items", side_effect=replace_after_read),
            patch.object(desktop, "prune_backups") as prune,
        ):
            self.update()
            prune.assert_not_called()
        self.assertEqual(read_snapshot(self.cache), external)
        self.assertEqual(self.c._data, self.original)
        self.assertIn("outra operação", self.c.state["error"])

    def test_missing_cache_created_by_other_writer_is_not_overwritten(self):
        self.cache.unlink()
        external = updated(source="Base de outro processo.pbix", digest="d")
        external_path = self.directory / "external.liarte"
        write_snapshot(external, external_path)
        original = desktop._read_backup_items

        def create_after_read(*args, **kwargs):
            result = original(*args, **kwargs)
            os.replace(external_path, self.cache)
            return result

        with patch.object(desktop, "_read_backup_items", side_effect=create_after_read):
            self.update()
        self.assertEqual(read_snapshot(self.cache), external)
        self.assertEqual(self.c._data, self.original)
        self.assertIn("outra operação", self.c.state["error"])

    def test_cancelled_listing_does_not_publish_a_stale_list_or_block_new_filters(self):
        entered = Event()

        def delayed(cache, cancel):
            entered.set()
            if not cancel.wait(3):
                raise RuntimeError("Listing did not receive generation cancellation")
            return (({"id": "stale"},), "stale warning")

        with patch.object(desktop, "_read_backup_items", side_effect=delayed):
            self.c.refreshBackups()
            self.assertTrue(pump(entered.is_set))
            self.c.setFilter("unit", "KG")
            self.idle()
        self.assertEqual(self.c.state["selection"]["unit"], "KG")
        self.assertEqual(self.c.state["count"], 2)
        self.assertEqual(self.c.backupState["items"], [])
        self.assertEqual(self.c.backupState["error"], "")
        self.assertTrue(self.c.backupState["canRestore"])

    def test_cancelled_restore_preserves_current_base_and_reenables_backup_actions(self):
        self.update()
        identifier = self.c.backupState["items"][0]["id"]
        previous = self.cache.read_bytes()
        entered = Event()
        original = desktop.load_backup

        def delayed(cache, backup_id, cancel):
            entered.set()
            if not cancel.wait(3):
                raise RuntimeError("Restore did not receive cancellation")
            return original(cache, backup_id, cancel)

        with patch.object(desktop, "load_backup", side_effect=delayed):
            self.c.restoreBackup(identifier)
            self.assertTrue(pump(entered.is_set))
            self.assertEqual(self.c.state["task"], "load")
            self.assertFalse(self.c.backupState["canRestore"])
            self.c.setFilter("unit", "KG")
            self.assertEqual(self.c.state["selection"]["unit"], "")
            self.c.cancel()
            self.idle()
        self.assertEqual(self.cache.read_bytes(), previous)
        self.assertEqual(self.c._data, self.new)
        self.assertTrue(self.c.backupState["canRestore"])
        self.assertEqual(self.c.backupState["notice"], "")

    def test_refreshing_history_preserves_an_existing_filter_analysis_error(self):
        self.c.setFilter("start", "2026-04")
        self.c.setFilter("end", "2026-01")
        self.idle()
        error = self.c.state["error"]
        self.assertTrue(error)
        self.assertFalse(self.c.state["current"])
        self.c.refreshBackups()
        self.idle()
        self.assertEqual(self.c.state["error"], error)
        self.assertEqual(self.c.backupState["error"], "")
