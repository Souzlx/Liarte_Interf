"""Compatibility and recovery when preparing the app with a different Python."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools import preparation


class PythonRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.environment = self.root / "env"
        self.interpreter = self.environment / (
            "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
        )

    def tearDown(self):
        self.temp.cleanup()

    def old_environment(self):
        self.interpreter.parent.mkdir(parents=True)
        self.interpreter.touch()
        (self.environment / "pyvenv.cfg").write_text("version = 3.13.14\n")
        (self.environment / "old-package.txt").write_text("previous dependency")

    def test_supported_versions_include_314_and_keep_previous_releases(self):
        with patch.object(preparation.sysconfig, "get_config_var", return_value=None):
            for minor in (11, 12, 13, 14):
                with (
                    self.subTest(minor=minor),
                    patch.object(preparation.sys, "version_info", (3, minor, 0)),
                ):
                    preparation.validate_python_runtime()
            for version in ((3, 10, 0), (3, 15, 0), (4, 0, 0)):
                with (
                    self.subTest(version=version),
                    patch.object(preparation.sys, "version_info", version),
                    self.assertRaisesRegex(RuntimeError, "3.14"),
                ):
                    preparation.validate_python_runtime()

    def test_free_threaded_runtime_is_rejected_before_venv_creation(self):
        with (
            patch.object(preparation.sysconfig, "get_config_var", return_value=1),
            patch.object(preparation.venv, "EnvBuilder") as builder,
            self.assertRaisesRegex(RuntimeError, "edição padrão"),
        ):
            preparation.ensure_environment(self.environment)
        builder.assert_not_called()
        self.assertFalse(self.environment.exists())

    def test_windows_rejects_32bit_before_downloading_qt(self):
        with (
            patch.object(preparation.sysconfig, "get_config_var", return_value=None),
            patch.object(preparation.sys, "platform", "win32"),
            patch.object(preparation.struct, "calcsize", return_value=4),
            self.assertRaisesRegex(RuntimeError, "64 bits"),
        ):
            preparation.validate_python_runtime()

    def test_python_and_pythonw_share_the_same_runtime_identity(self):
        expected = preparation.runtime_signature()
        with patch.object(preparation.sys, "executable", str(self.root / "pythonw.exe")):
            self.assertEqual(preparation.runtime_signature(), expected)

    def test_matching_runtime_reuses_environment_without_rebuilding(self):
        self.old_environment()
        response = SimpleNamespace(returncode=0, stdout=json.dumps(preparation.runtime_signature()))
        with (
            patch.object(preparation.subprocess, "run", return_value=response) as run,
            patch.object(preparation.venv, "EnvBuilder") as builder,
        ):
            interpreter, recreated = preparation.ensure_environment(self.environment)
        self.assertEqual(interpreter, self.interpreter)
        self.assertFalse(recreated)
        builder.assert_not_called()
        self.assertIn("-I", run.call_args.args[0])
        self.assertTrue((self.environment / "old-package.txt").is_file())

    def test_runtime_probe_rejects_different_version_bitness_and_base_path(self):
        self.old_environment()
        expected = preparation.runtime_signature()
        for field, value in [
            ("version", [3, 10, 0]),
            ("bits", 32),
            ("base_prefix", str(self.root / "other-python")),
            ("free_threaded", True),
            ("implementation", "pypy"),
        ]:
            response = SimpleNamespace(returncode=0, stdout=json.dumps({**expected, field: value}))
            with (
                self.subTest(field=field),
                patch.object(preparation.subprocess, "run", return_value=response),
            ):
                self.assertFalse(preparation.environment_matches(self.interpreter))

    def test_broken_runtime_probe_does_not_report_a_usable_environment(self):
        self.old_environment()
        for response in [
            SimpleNamespace(returncode=1, stdout=""),
            SimpleNamespace(returncode=0, stdout="not JSON"),
        ]:
            with patch.object(preparation.subprocess, "run", return_value=response):
                self.assertFalse(preparation.environment_matches(self.interpreter))
        with patch.object(
            preparation.subprocess, "run", side_effect=subprocess.TimeoutExpired("python", 12)
        ):
            self.assertFalse(preparation.environment_matches(self.interpreter))

    def test_migration_preserves_previous_environment_reports_and_preferences(self):
        self.old_environment()
        report = self.root / "Relatorios_Comex" / "report.xlsx"
        report.parent.mkdir()
        report.write_bytes(b"previous report")
        preference = self.root / "preferences.json"
        preference.write_text("{}")

        def create(path):
            self.interpreter.parent.mkdir(parents=True)
            self.interpreter.touch()
            (path / "pyvenv.cfg").write_text("new runtime")

        with (
            patch.object(preparation, "environment_matches", side_effect=[False, True]),
            patch.object(preparation.venv, "EnvBuilder") as builder,
        ):
            builder.return_value.create.side_effect = create
            interpreter, recreated = preparation.ensure_environment(self.environment)
        self.assertTrue(recreated)
        self.assertEqual(interpreter, self.interpreter)
        (backup,) = self.root.glob("env.anterior-*")
        self.assertEqual((backup / "old-package.txt").read_text(), "previous dependency")
        self.assertFalse((self.environment / "old-package.txt").exists())
        self.assertEqual(report.read_bytes(), b"previous report")
        self.assertEqual(preference.read_text(), "{}")

    def test_failed_migration_restores_previous_environment(self):
        self.old_environment()

        def fail(path):
            path.mkdir()
            (path / "partial.txt").write_text("partial")
            raise RuntimeError("controlled creation failure")

        with (
            patch.object(preparation, "environment_matches", return_value=False),
            patch.object(preparation.venv, "EnvBuilder") as builder,
            self.assertRaisesRegex(RuntimeError, "controlled"),
        ):
            builder.return_value.create.side_effect = fail
            preparation.ensure_environment(self.environment)
        self.assertEqual((self.environment / "old-package.txt").read_text(), "previous dependency")
        self.assertFalse((self.environment / "partial.txt").exists())
        self.assertEqual(list(self.root.glob("env.anterior-*")), [])

    def test_existing_directory_link_is_not_followed_or_modified(self):
        original = self.root / "original"
        original.mkdir()
        (original / "keep.txt").write_text("keep")
        try:
            self.environment.symlink_to(original, target_is_directory=True)
        except OSError:
            self.skipTest("Directory symlinks need extra Windows privileges")
        with self.assertRaisesRegex(RuntimeError, "link"):
            preparation.ensure_environment(self.environment)
        self.assertEqual((original / "keep.txt").read_text(), "keep")

    def test_real_venv_is_created_verified_and_reused_by_the_current_runtime(self):
        interpreter, created = preparation.ensure_environment(self.environment)
        self.assertTrue(created)
        self.assertTrue(preparation.environment_matches(interpreter))
        (self.environment / "marker.txt").write_text("reuse")
        again, created = preparation.ensure_environment(self.environment)
        self.assertEqual(again, interpreter)
        self.assertFalse(created)
        self.assertEqual((self.environment / "marker.txt").read_text(), "reuse")
