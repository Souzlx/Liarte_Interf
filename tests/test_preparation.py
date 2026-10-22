from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from tools.preparation import (
    PreparationLock,
    child_environment,
    launch_verified,
    requirements_satisfied,
)
from tools.build_windows import publish_bundle


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_child_does_not_inherit_foreign_python_or_qt_paths(self):
        with patch.dict(
            os.environ,
            {
                "PYTHONPATH": "foreign",
                "PYTHONHOME": "foreign",
                "QT_PLUGIN_PATH": "foreign",
                "PATH": "keep",
            },
        ):
            env = child_environment(LIARTE_STARTUP_PROBE="1")
            self.assertNotIn("PYTHONPATH", env)
            self.assertNotIn("PYTHONHOME", env)
            self.assertNotIn("QT_PLUGIN_PATH", env)
            self.assertEqual(env["PATH"], "keep")
            self.assertEqual(os.environ["PYTHONPATH"], "foreign")

    def test_lock_excludes_another_process_and_releases_after_close(self):
        lock = self.root / "prepare.lock"
        script = "from pathlib import Path;from tools.preparation import PreparationLock;import sys;\nwith PreparationLock(Path(sys.argv[1])): pass"
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parent.parent))
        with PreparationLock(lock):
            blocked = subprocess.run(
                [sys.executable, "-c", script, str(lock)], env=env, capture_output=True, timeout=8
            )
        free = subprocess.run(
            [sys.executable, "-c", script, str(lock)], env=env, capture_output=True, timeout=8
        )
        self.assertNotEqual(blocked.returncode, 0)
        self.assertEqual(free.returncode, 0, free.stderr)

    def test_failed_preparation_does_not_leave_a_stale_lock(self):
        path = self.root / "prepare.lock"
        with self.assertRaises(ValueError):
            with PreparationLock(path):
                raise ValueError("test")
        with PreparationLock(path):
            pass

    def test_startup_requires_a_ready_signal(self):
        process = Mock()
        process.poll.return_value = None

        def popen(command, **kwargs):
            Path(command[-1]).write_text(json.dumps({"status": "ready", "version": "test"}))
            return process

        with patch("tools.preparation.subprocess.Popen", side_effect=popen):
            result = launch_verified(["python", "iniciar.py"], self.root, self.root / "log.txt")
        self.assertIs(result, process)
        process.terminate.assert_not_called()

    def test_startup_failure_does_not_report_success_or_leave_a_process(self):
        process = Mock()
        process.poll.return_value = None

        def popen(command, **kwargs):
            Path(command[-1]).write_text('{"status":"failed"}')
            return process

        with (
            patch("tools.preparation.subprocess.Popen", side_effect=popen),
            self.assertRaises(RuntimeError),
        ):
            launch_verified(["python", "iniciar.py"], self.root, self.root / "log.txt")
        process.terminate.assert_called_once()

    def test_early_process_exit_does_not_report_success(self):
        process = Mock()
        process.poll.return_value = 1
        with (
            patch("tools.preparation.subprocess.Popen", return_value=process),
            self.assertRaises(RuntimeError),
        ):
            launch_verified(["python", "iniciar.py"], self.root, self.root / "log.txt")

    def test_startup_captures_child_output_without_a_console(self):
        logfile = self.root / "logs/startup.log"
        script = (
            "import sys,json,time; from pathlib import Path; "
            "print('diagnóstico de abertura',flush=True); "
            "print('native warning',file=sys.stderr,flush=True); "
            "Path(sys.argv[-1]).write_text(json.dumps({'status':'ready'})); "
            "time.sleep(5)"
        )
        process = launch_verified([sys.executable, "-c", script], self.root, logfile)
        try:
            diagnostic = logfile.read_text(encoding="utf-8")
            self.assertIn("diagnóstico de abertura", diagnostic)
            self.assertIn("native warning", diagnostic)
        finally:
            process.terminate()
            process.wait(timeout=5)

    def test_startup_timeout_terminates_only_its_own_process(self):
        process = Mock()
        process.poll.return_value = None
        with (
            patch("tools.preparation.subprocess.Popen", return_value=process),
            self.assertRaises(RuntimeError),
        ):
            launch_verified(["python", "iniciar.py"], self.root, self.root / "log.txt", timeout=0)
        process.terminate.assert_called_once()

    def test_matching_versions_skip_installation_probe(self):
        (self.root / "requirements.txt").write_text(
            "PySide6-Essentials==6.10.3\nshiboken6==6.10.3\n"
        )
        result = SimpleNamespace(
            returncode=0, stdout=json.dumps({"PySide6-Essentials": "6.10.3", "shiboken6": "6.10.3"})
        )
        with patch("tools.preparation.subprocess.run", return_value=result):
            self.assertTrue(requirements_satisfied(Path("env/python"), self.root, "run"))
            result.stdout = "{}"
            self.assertFalse(requirements_satisfied(Path("env/python"), self.root, "run"))

    def test_publish_rolls_back_previous_bundle_when_move_fails(self):
        destination = self.root / "dist/LIARTE_Desktop_F1"
        destination.mkdir(parents=True)
        (destination / "old.exe").write_text("old")
        source = self.root / "new"
        source.mkdir()
        with (
            patch("tools.build_windows.shutil.move", side_effect=OSError("disk full")),
            self.assertRaises(OSError),
        ):
            publish_bundle(source, destination)
        self.assertEqual((destination / "old.exe").read_text(), "old")

    def test_publish_keeps_previous_bundle_backup(self):
        destination = self.root / "dist/LIARTE_Desktop_F1"
        destination.mkdir(parents=True)
        (destination / "old.exe").write_text("old")
        source = self.root / "new"
        source.mkdir()
        (source / "new.exe").write_text("new")
        backup = publish_bundle(source, destination)
        self.assertEqual((backup / "old.exe").read_text(), "old")
        self.assertEqual((destination / "new.exe").read_text(), "new")

    def test_publish_preserves_partial_copy_and_restores_old_path(self):
        destination = self.root / "dist/LIARTE_Desktop_F1"
        destination.mkdir(parents=True)
        (destination / "old.exe").write_text("old")
        source = self.root / "new"
        source.mkdir()

        def fail(_, target):
            path = Path(target)
            path.mkdir()
            (path / "partial").write_text("partial")
            raise OSError("disk full")

        with patch("tools.build_windows.shutil.move", side_effect=fail), self.assertRaises(OSError):
            publish_bundle(source, destination)
        self.assertEqual((destination / "old.exe").read_text(), "old")
        self.assertEqual(len(list(destination.parent.glob("LIARTE_Desktop_F1_incompleto_*"))), 1)
