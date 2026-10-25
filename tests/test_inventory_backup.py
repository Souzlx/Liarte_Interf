"""Real files verify versioned backups and non-destructive recovery failures."""

from contextlib import contextmanager
from dataclasses import replace
import errno
import hashlib
import json
from pathlib import Path
import tempfile
from threading import Event
import unittest
from unittest.mock import patch

from liarte_core import inventory_backup as backup
from liarte_core.inventory_io import read_snapshot, write_snapshot
from liarte_core.query import Cancelled
from tests.test_audit_stock_core import fixture


class InventoryBackupTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.cache = self.root / "stock/base.liarte"
        self.staged = self.root / "stock/.incoming.liarte"
        self.data = fixture()
        write_snapshot(self.data, self.cache)
        self.previous = self.cache.read_bytes()
        self.changed = replace(self.data, source_name="Nova base.pbix", source_hash="b" * 64)
        write_snapshot(self.changed, self.staged)

    def create(self):
        result = backup.backup_previous(self.cache, self.staged)
        self.assertIsNotNone(result)
        return result

    def folders(self):
        directory = self.cache.parent / "backups"
        return list(directory.iterdir()) if directory.exists() else []

    def test_previous_snapshot_and_manifest_are_verified_without_changing_current_base(self):
        info = self.create()
        self.assertEqual(self.cache.read_bytes(), self.previous)
        self.assertEqual(info.path.read_bytes(), self.previous)
        self.assertEqual(info.sha256, hashlib.sha256(self.previous).hexdigest())
        self.assertEqual(info.bytes, len(self.previous))
        self.assertEqual((info.as_of, info.source_name), ("2026-10-24", self.data.source_name))
        self.assertEqual((info.products, info.balances), (1, 1))
        self.assertEqual(backup.list_backups(self.cache), (info,))
        self.assertEqual(backup.load_backup(self.cache, info.id), self.data)
        self.assertEqual(
            {p.name for p in info.path.parent.iterdir()}, {"base.liarte", "manifest.json"}
        )

    def test_identical_incoming_file_does_not_create_a_backup(self):
        self.staged.write_bytes(self.previous)
        self.assertIsNone(backup.backup_previous(self.cache, self.staged))
        self.assertEqual(self.folders(), [])
        self.assertEqual(self.cache.read_bytes(), self.previous)

    def test_missing_previous_base_does_not_create_history_directory(self):
        missing = self.root / "new-profile/base.liarte"
        self.assertIsNone(backup.backup_previous(missing))
        self.assertEqual(backup.list_backups(missing), ())
        self.assertFalse(missing.parent.exists())

    def test_corrupt_previous_base_does_not_block_recovery_or_publish_an_invalid_copy(self):
        self.cache.write_bytes(b"corrupt previous base")
        self.assertIsNone(backup.backup_previous(self.cache, self.staged))
        self.assertEqual(self.folders(), [])
        self.assertEqual(read_snapshot(self.staged), self.changed)

    def test_oversized_previous_base_is_skipped_before_copying(self):
        with patch.object(backup, "MAX_COMPRESSED", len(self.previous) - 1):
            self.assertIsNone(backup.backup_previous(self.cache, self.staged))
        self.assertEqual(self.folders(), [])

    def test_corrupt_previous_cache_does_not_require_access_to_backup_storage(self):
        self.cache.write_bytes(b"corrupt previous base")
        with patch.object(
            backup, "_directory", side_effect=PermissionError("blocked history")
        ) as history:
            self.assertIsNone(backup.backup_previous(self.cache, self.staged))
            history.assert_not_called()
        history_path = self.cache.parent / "backups"
        history_path.write_bytes(b"existing unrelated file")
        self.assertIsNone(backup.backup_previous(self.cache, self.staged))
        self.assertEqual(history_path.read_bytes(), b"existing unrelated file")
        self.assertEqual(self.cache.read_bytes(), b"corrupt previous base")
        self.assertEqual(read_snapshot(self.staged), self.changed)
        self.assertEqual(list(self.cache.parent.glob(".backup-*")), [])

    def test_valid_previous_cache_must_not_be_replaced_when_history_is_blocked(self):
        with patch.object(backup, "_directory", side_effect=PermissionError("blocked history")):
            with self.assertRaises(PermissionError):
                self.create()
        self.assertEqual(self.cache.read_bytes(), self.previous)
        self.assertEqual(list(self.cache.parent.glob(".backup-*")), [])

    def test_disk_full_cannot_replace_the_old_base_or_leave_a_visible_backup(self):
        original_open = Path.open

        def fail(path, mode="r", *args, **kwargs):
            if mode == "xb":
                raise OSError(errno.ENOSPC, "disk full")
            return original_open(path, mode, *args, **kwargs)

        with patch.object(Path, "open", fail), self.assertRaises(OSError) as error:
            self.create()
        self.assertEqual(error.exception.errno, errno.ENOSPC)
        self.assertEqual(self.cache.read_bytes(), self.previous)
        self.assertEqual(self.folders(), [])

    def test_backup_publication_failure_preserves_current_base_and_previous_copies(self):
        existing = self.create()
        with patch.object(backup.os, "replace", side_effect=PermissionError("locked folder")):
            with self.assertRaises(PermissionError):
                self.create()
        self.assertEqual(backup.list_backups(self.cache), (existing,))
        self.assertEqual(self.cache.read_bytes(), self.previous)
        self.assertEqual(len(self.folders()), 1)

    def test_validation_io_error_is_a_backup_failure_not_a_corrupt_base_skip(self):
        failure = OSError(errno.EIO, "read failure")
        invalid = ValueError("snapshot could not be read")
        invalid.__cause__ = failure
        with patch.object(backup, "read_snapshot", side_effect=invalid):
            with self.assertRaises(OSError) as error:
                self.create()
        self.assertEqual(error.exception.errno, errno.EIO)
        self.assertEqual(self.cache.read_bytes(), self.previous)
        self.assertEqual(self.folders(), [])

    def test_cancel_during_copy_keeps_current_base_and_cleans_staging(self):
        cancel = Event()
        original = backup._reader

        class InterruptingReader:
            def __init__(self, source):
                self.source = source

            def read(self, size):
                value = self.source.read(size)
                cancel.set()
                return value

        @contextmanager
        def reader(path, limit):
            with original(path, limit) as source:
                yield InterruptingReader(source) if path == self.cache else source

        with patch.object(backup, "_reader", reader), self.assertRaises(Cancelled):
            backup.backup_previous(self.cache, self.staged, cancel)
        self.assertEqual(self.cache.read_bytes(), self.previous)
        self.assertEqual(self.folders(), [])

    def test_cancel_after_manifest_write_does_not_publish_a_backup(self):
        cancel, calls = Event(), []
        original = backup.os.fsync

        def sync(fd):
            original(fd)
            calls.append(fd)
            if len(calls) == 2:
                cancel.set()

        with patch.object(backup.os, "fsync", side_effect=sync), self.assertRaises(Cancelled):
            backup.backup_previous(self.cache, self.staged, cancel)
        self.assertEqual(self.folders(), [])
        self.assertEqual(self.cache.read_bytes(), self.previous)

    def test_same_clock_does_not_overwrite_a_previous_backup(self):
        from datetime import datetime, timezone

        instant = datetime(2026, 10, 25, tzinfo=timezone.utc)
        with patch.object(backup, "datetime") as clock:
            clock.now.return_value = instant
            first, second = self.create(), self.create()
        self.assertNotEqual(first.id, second.id)
        self.assertEqual(first.path.read_bytes(), second.path.read_bytes())
        self.assertEqual(len(backup.list_backups(self.cache)), 2)

    def test_backup_remains_valid_after_current_base_is_updated(self):
        info = self.create()
        self.staged.replace(self.cache)
        self.assertEqual(read_snapshot(self.cache), self.changed)
        self.assertEqual(backup.load_backup(self.cache, info.id), self.data)
        self.assertEqual(info.path.read_bytes(), self.previous)

    def test_restore_rejects_changed_snapshot_even_when_its_gzip_and_json_are_valid(self):
        info = self.create()
        write_snapshot(self.changed, info.path)
        with self.assertRaisesRegex(ValueError, "integridade"):
            backup.load_backup(self.cache, info.id)
        with self.assertLogs("liarte.desktop", level="WARNING"):
            self.assertEqual(backup.list_backups(self.cache), ())
        self.assertEqual(self.cache.read_bytes(), self.previous)

    def test_listing_skips_one_corrupt_manifest_and_preserves_the_valid_copy(self):
        first, second = self.create(), self.create()
        (first.path.parent / "manifest.json").write_bytes(b"invalid JSON")
        with self.assertLogs("liarte.desktop", level="WARNING"):
            self.assertEqual(backup.list_backups(self.cache), (second,))
        self.assertTrue(first.path.exists())

    def test_manifest_claims_must_match_snapshot_metadata(self):
        info = self.create()
        path = info.path.parent / "manifest.json"
        manifest = json.loads(path.read_bytes())
        manifest["products"] += 1
        path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "diverge"):
            backup.load_backup(self.cache, info.id)

    def test_recursive_or_oversized_manifest_is_rejected_before_restore(self):
        info = self.create()
        path = info.path.parent / "manifest.json"
        for value in (b"[" * 1500 + b"0" + b"]" * 1500, b" " * (backup.MAX_MANIFEST_BYTES + 1)):
            with self.subTest(bytes=len(value)):
                path.write_bytes(value)
                with self.assertRaises(ValueError):
                    backup.load_backup(self.cache, info.id)
                with self.assertLogs("liarte.desktop", level="WARNING"):
                    self.assertEqual(backup.list_backups(self.cache), ())

    def test_restore_accepts_only_managed_opaque_identifiers(self):
        for identifier in ("../base", "/tmp", "", "base.liarte", None, "a/../../b"):
            with self.subTest(identifier=identifier), self.assertRaises(ValueError):
                backup.load_backup(self.cache, identifier)
        self.assertEqual(self.cache.read_bytes(), self.previous)

    def test_retention_keeps_ten_valid_versions_and_never_touches_current_base(self):
        versions = [self.create() for _ in range(12)]
        backup.prune_backups(self.cache)
        retained = backup.list_backups(self.cache)
        self.assertEqual(len(retained), 10)
        self.assertEqual({v.id for v in retained}, {v.id for v in versions[-10:]})
        self.assertEqual(self.cache.read_bytes(), self.previous)

    def test_explicitly_preserved_backup_survives_clock_rollback(self):
        versions = [self.create() for _ in range(4)]
        backup.prune_backups(self.cache, keep=2, preserve_ids=(versions[0].id,))
        self.assertEqual(
            {v.id for v in backup.list_backups(self.cache)}, {versions[0].id, versions[-1].id}
        )

    def test_pruning_does_not_delete_corrupt_or_unrecognized_directories(self):
        first, second, third = self.create(), self.create(), self.create()
        marker = first.path.parent / "personal.txt"
        marker.write_text("never delete this", encoding="utf-8")
        unrelated = self.cache.parent / "backups/my-old-base"
        unrelated.mkdir()
        (unrelated / "note.txt").write_text("user file", encoding="utf-8")
        with self.assertLogs("liarte.desktop", level="WARNING"):
            backup.prune_backups(self.cache, keep=1)
        self.assertEqual(marker.read_text(encoding="utf-8"), "never delete this")
        self.assertTrue(unrelated.exists())
        self.assertFalse(second.path.exists())
        self.assertTrue(third.path.exists())

    def test_retention_failure_keeps_current_base_and_remaining_backups(self):
        first, second = self.create(), self.create()
        with patch.object(backup.shutil, "rmtree", side_effect=PermissionError("locked backup")):
            with self.assertRaises(PermissionError):
                backup.prune_backups(self.cache, keep=1)
        self.assertEqual(self.cache.read_bytes(), self.previous)
        self.assertEqual({v.id for v in backup.list_backups(self.cache)}, {first.id, second.id})

    def test_invalid_retention_request_cannot_remove_any_copy(self):
        info = self.create()
        for count in (0, 11, -1, True):
            with self.subTest(keep=count), self.assertRaises(ValueError):
                backup.prune_backups(self.cache, keep=count)
        self.assertEqual(backup.list_backups(self.cache), (info,))

    def test_history_symlink_cannot_redirect_backup_or_restore(self):
        outside = self.root / "external"
        outside.mkdir()
        link = self.cache.parent / "backups"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("A conta Windows não permite criar symlinks para este ensaio.")
        with self.assertRaisesRegex(ValueError, "links simbólicos"):
            self.create()
        self.assertEqual(list(outside.iterdir()), [])
        self.assertEqual(self.cache.read_bytes(), self.previous)
