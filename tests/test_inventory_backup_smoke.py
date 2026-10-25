"""Offline frozen-entrypoint checks for the stock backup module."""

import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from liarte_core.inventory import SCALE
from liarte_core.inventory_backup import list_backups, load_backup
from liarte_core.inventory_io import read_snapshot
from liarte_desktop.app import _smoke_inventory_backups


class InventoryBackupSmokeTests(unittest.TestCase):
    def test_round_trip_restores_original_and_keeps_the_replaced_version(self):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary) / "synthetic"
            self.assertTrue(_smoke_inventory_backups(directory))
            cache = directory / "base.liarte"
            self.assertEqual(read_snapshot(cache).balances[0].quantity, SCALE)
            copies = list_backups(cache)
            self.assertEqual(len(copies), 2)
            self.assertEqual(
                {load_backup(cache, copy.id).balances[0].quantity for copy in copies},
                {SCALE, 2 * SCALE},
            )
            self.assertEqual({path.name for path in Path(temporary).iterdir()}, {"synthetic"})

    def test_existing_directory_is_rejected_before_any_file_changes(self):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            protected = directory / "base.liarte"
            protected.write_bytes(b"previous file; never use as scratch")
            with self.assertRaises(FileExistsError):
                _smoke_inventory_backups(directory)
            self.assertEqual(protected.read_bytes(), b"previous file; never use as scratch")
            self.assertEqual(list(directory.iterdir()), [protected])

    def test_missing_backup_is_a_failed_check_and_keeps_the_original(self):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary) / "synthetic"
            with patch("liarte_core.inventory_backup.backup_previous", return_value=None):
                self.assertFalse(_smoke_inventory_backups(directory))
            self.assertEqual(read_snapshot(directory / "base.liarte").balances[0].quantity, SCALE)

    def test_failed_restore_validation_preserves_the_new_current_version(self):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary) / "synthetic"
            with patch(
                "liarte_core.inventory_backup.load_backup", side_effect=ValueError("invalid backup")
            ):
                with self.assertRaisesRegex(ValueError, "invalid backup"):
                    _smoke_inventory_backups(directory)
            self.assertEqual(
                read_snapshot(directory / "base.liarte").balances[0].quantity, 2 * SCALE
            )

    def test_native_entrypoint_reports_and_requires_the_backup_check(self):
        root = Path(__file__).resolve().parents[1]
        # Run the real entrypoint in another Qt process, overriding only the
        # backup outcome and profile logging. The aggregate gate must fail.
        script = (
            "import sys;sys.path.insert(0,sys.argv[1]);"
            "from liarte_desktop import app;"
            "app.configure_log=lambda:None;"
            "app._smoke_inventory_backups=lambda directory:False;"
            "raise SystemExit(app.main(['--smoke-test',sys.argv[2]]))"
        )
        with TemporaryDirectory() as temporary:
            result = Path(temporary) / "smoke.json"
            process = subprocess.run(
                [sys.executable, "-c", script, str(root / "src"), str(result)],
                capture_output=True,
                text=True,
                timeout=35,
                env=dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software"),
            )
            self.assertEqual(process.returncode, 1, process.stdout + process.stderr)
            report = json.loads(result.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["document_resources"]["inventory_backups"], "failed")
