"""Publication failures must preserve the last verified release."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests import test_release
from tools import preparation, prepare_release


class BuildAuditTests(unittest.TestCase):
    setUp = test_release.ReleaseTests.setUp
    write_smoke_and_manifest = test_release.ReleaseTests.write_smoke_and_manifest

    def test_checksum_failure_restores_both_previous_release_files(self):
        result = prepare_release.prepare_release(self.bundle, self.output)
        archive, checksum = Path(result["archive"]), Path(result["checksum"])
        previous = {path: path.read_bytes() for path in (archive, checksum)}
        (self.bundle / "_internal/resource.txt").write_text("new bytes", encoding="utf-8")
        self.write_smoke_and_manifest()
        real_replace = os.replace

        def replace(source, target):
            if Path(target) == checksum:
                raise PermissionError("checksum is locked")
            return real_replace(source, target)

        with patch.object(prepare_release.os, "replace", side_effect=replace):
            with self.assertRaises(PermissionError):
                prepare_release.prepare_release(self.bundle, self.output)
        self.assertEqual({path: path.read_bytes() for path in previous}, previous)
        self.assertEqual(list(self.output.glob(".release-*")), [])

    def test_first_publication_failure_does_not_leave_an_unverified_archive(self):
        real_replace = os.replace

        def replace(source, target):
            if Path(target).name == "SHA256SUMS.txt":
                raise OSError("checksum disk failure")
            return real_replace(source, target)

        with patch.object(prepare_release.os, "replace", side_effect=replace):
            with self.assertRaises(OSError):
                prepare_release.prepare_release(self.bundle, self.output)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_failed_rollback_keeps_recovery_files_after_staging_cleanup(self):
        result = prepare_release.prepare_release(self.bundle, self.output)
        archive, checksum = Path(result["archive"]), Path(result["checksum"])
        previous = {path.name: path.read_bytes() for path in (archive, checksum)}
        (self.bundle / "_internal/resource.txt").write_text("new bytes", encoding="utf-8")
        self.write_smoke_and_manifest()
        real_replace = os.replace

        def replace(source, target):
            if Path(target) == checksum or Path(source).parent.name.startswith(
                ".release-recovery-"
            ):
                raise PermissionError("publication and rollback blocked")
            return real_replace(source, target)

        with patch.object(prepare_release.os, "replace", side_effect=replace):
            with self.assertRaisesRegex(RuntimeError, "preservadas em") as error:
                prepare_release.prepare_release(self.bundle, self.output)
        backups = list(self.output.glob(".release-recovery-*"))
        self.assertEqual(len(backups), 1)
        self.assertIn(str(backups[0]), str(error.exception))
        self.assertEqual({path.name: path.read_bytes() for path in backups[0].iterdir()}, previous)
        self.assertEqual(checksum.read_bytes(), previous[checksum.name])

    def test_first_replace_failure_keeps_previous_pair(self):
        result = prepare_release.prepare_release(self.bundle, self.output)
        previous = {
            Path(result[key]): Path(result[key]).read_bytes() for key in ("archive", "checksum")
        }
        with patch.object(prepare_release.os, "replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                prepare_release.prepare_release(self.bundle, self.output)
        self.assertEqual({path: path.read_bytes() for path in previous}, previous)
        self.assertEqual(list(self.output.glob(".release-*")), [])

    def test_backup_cleanup_error_does_not_mask_successful_publication(self):
        self.output.mkdir()
        staged = (self.root / "new.zip", self.root / "new.sha256")
        targets = (self.output / "release.zip", self.output / "SHA256SUMS.txt")
        for path in staged:
            path.write_bytes(b"new")
        for path in targets:
            path.write_bytes(b"previous")
        with patch.object(prepare_release.shutil, "rmtree", side_effect=PermissionError("locked")):
            with self.assertLogs("tools.prepare_release", level="WARNING") as diagnostic:
                prepare_release._publish_release_files(staged, targets)
        self.assertEqual([path.read_bytes() for path in targets], [b"new", b"new"])
        recovery = next(self.output.glob(".release-recovery-*"))
        self.assertIn(str(recovery), diagnostic.output[0])
        self.assertEqual(
            [path.read_bytes() for path in recovery.iterdir()], [b"previous", b"previous"]
        )

    def test_qmldir_changes_invalidate_the_verified_preparation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ("requirements.txt", "requirements-build.txt", "iniciar.py", "python"):
                (root / name).write_text("synthetic", encoding="utf-8")
            module = root / "src/liarte_desktop/qml/components/qmldir"
            module.parent.mkdir(parents=True)
            module.write_text("AppCard 1.0 AppCard.qml\n", encoding="utf-8")
            before = preparation.probe_fingerprint(root / "python", root)
            module.write_text("AppCard 1.0 Changed.qml\n", encoding="utf-8")
            self.assertNotEqual(preparation.probe_fingerprint(root / "python", root), before)
