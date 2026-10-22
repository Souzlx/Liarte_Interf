from __future__ import annotations

from contextlib import ExitStack
import json
import os
from pathlib import Path
import queue
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from liarte_desktop import qt_runtime
from tools import assistente


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.package = self.root / "PySide6"
        self.shiboken = self.root / "shiboken6"
        self.plugin = (
            self.package / "qml/QtQuick/Controls/Basic/qtquickcontrols2basicstyleplugin.dll"
        )
        self.plugin.parent.mkdir(parents=True)
        self.shiboken.mkdir()
        (self.package / "plugins").mkdir()
        self.plugin.write_bytes(b"test fixture; not a DLL")
        for name in ("Qt6Core.dll", "Qt6QuickControls2Basic.dll", "Qt6QuickLayouts.dll"):
            (self.package / name).write_bytes(b"test fixture; not a DLL")

    def tearDown(self):
        self.directory.cleanup()

    def windows(self):
        context = ExitStack()
        context.enter_context(patch.object(qt_runtime.sys, "platform", "win32"))
        context.enter_context(patch.object(qt_runtime, "_CONFIGURED", False))
        context.enter_context(patch.object(qt_runtime, "_DIRECTORIES", []))
        context.enter_context(patch.object(qt_runtime, "_LIBRARIES", []))
        context.enter_context(patch.dict(os.environ))
        context.enter_context(
            patch.object(
                qt_runtime,
                "package_directory",
                side_effect=lambda n: self.package if n == "PySide6" else self.shiboken,
            )
        )
        add = context.enter_context(
            patch.object(os, "add_dll_directory", create=True, side_effect=lambda _: Mock())
        )
        load = context.enter_context(patch.object(qt_runtime.ctypes, "WinDLL", create=True))
        return context, add, load

    def test_non_windows_does_not_change_loader_or_environment(self):
        with (
            patch.object(qt_runtime.sys, "platform", "linux"),
            patch.object(qt_runtime, "package_directory") as locate,
        ):
            qt_runtime.configure_windows_qt()
            locate.assert_not_called()

    def test_windows_keeps_directory_handles_and_loads_absolute_plugins(self):
        context, add, load = self.windows()
        with context:
            qt_runtime.configure_windows_qt()
            self.assertEqual(add.call_count, 2)
            self.assertEqual(len(qt_runtime._DIRECTORIES), 2)
            self.assertEqual(load.call_count, 3)
            self.assertTrue(qt_runtime._CONFIGURED)
            for call in load.call_args_list:
                self.assertTrue(Path(call.args[0]).is_absolute())
                self.assertEqual(call.kwargs["winmode"], 0x1100)
            self.assertEqual(os.environ["QML_IMPORT_PATH"], str(self.package / "qml"))
            self.assertEqual(os.environ["QT_PLUGIN_PATH"], str(self.package / "plugins"))

    def test_registration_is_idempotent(self):
        context, add, load = self.windows()
        with context:
            qt_runtime.configure_windows_qt()
            qt_runtime.configure_windows_qt()
            self.assertEqual(add.call_count, 2)
            self.assertEqual(load.call_count, 3)

    def test_missing_plugin_is_reported_before_loading_any_dll(self):
        context, add, load = self.windows()
        self.plugin.unlink()
        with context, self.assertRaisesRegex(RuntimeError, "Arquivo do Qt ausente"):
            qt_runtime.configure_windows_qt()
        add.assert_not_called()
        load.assert_not_called()

    def test_load_failure_keeps_code_and_closes_directory_handles(self):
        context, add, load = self.windows()
        handles = [Mock(), Mock()]
        error = OSError("dependência ausente")
        error.winerror = 126
        with context:
            add.side_effect = handles
            load.side_effect = error
            with self.assertRaisesRegex(RuntimeError, "erro 126"):
                qt_runtime.configure_windows_qt()
            self.assertFalse(qt_runtime._CONFIGURED)
            self.assertEqual(qt_runtime._DIRECTORIES, [])
            for handle in handles:
                handle.close.assert_called_once()

    def test_frozen_bundle_can_hold_qt_dlls_at_its_internal_root(self):
        frozen = self.root / "_internal"
        frozen.mkdir()
        for name in ("Qt6Core.dll", "Qt6QuickControls2Basic.dll", "Qt6QuickLayouts.dll"):
            (self.package / name).rename(frozen / name)
        context, _, load = self.windows()
        with context, patch.object(qt_runtime.sys, "_MEIPASS", str(frozen), create=True):
            qt_runtime.configure_windows_qt()
            self.assertEqual(Path(load.call_args_list[0].args[0]).parent, frozen)

    def test_dependency_repair_uses_only_its_own_interpreter(self):
        log = self.root / "bootstrap.log"
        interpreter = self.root / "env/Scripts/python.exe"
        with patch.object(
            assistente.subprocess, "run", return_value=SimpleNamespace(returncode=0)
        ) as run:
            assistente.install_dependencies(interpreter, "run", log, repair=True)
        args = run.call_args.args[0]
        self.assertEqual(args[0], str(interpreter))
        self.assertIn("--force-reinstall", args)
        self.assertIn("--no-cache-dir", args)
        self.assertNotIn("--user", args)

    def check_probe(self, document=None, returncode=0):
        def run(command, **kwargs):
            if document is not None:
                Path(command[-1]).write_text(json.dumps(document), encoding="utf-8")
            self.assertEqual(kwargs["env"]["LIARTE_STARTUP_PROBE"], "1")
            self.assertEqual(kwargs["env"]["QT_QPA_PLATFORM"], "offscreen")
            return SimpleNamespace(returncode=returncode)

        with patch.object(assistente.subprocess, "run", side_effect=run):
            return assistente.check_interface(
                Path("isolated/python.exe"), self.root / "bootstrap.log"
            )

    def test_probe_requires_success_and_both_themes(self):
        self.assertTrue(
            self.check_probe(
                {"status": "ok", "qml_warnings": [], "themes_checked": ["light", "dark"]}
            )
        )
        self.assertFalse(
            self.check_probe({"status": "ok", "qml_warnings": [], "themes_checked": ["light"]})
        )

    def test_probe_does_not_accept_a_stale_success_report(self):
        report = self.root / "validacao-qt.json"
        report.write_text('{"status":"ok"}')
        self.assertFalse(self.check_probe(None, returncode=1))
        self.assertEqual(json.loads(report.read_text())["status"], "failed")

    def test_probe_rejects_qml_warnings(self):
        self.assertFalse(
            self.check_probe(
                {"status": "ok", "qml_warnings": ["error"], "themes_checked": ["light", "dark"]}
            )
        )

    def test_probe_timeout_fails_without_opening_the_application(self):
        with patch.object(
            assistente.subprocess, "run", side_effect=subprocess.TimeoutExpired("test", 40)
        ):
            self.assertFalse(
                assistente.check_interface(Path("python.exe"), self.root / "bootstrap.log")
            )
        self.assertEqual(
            json.loads((self.root / "validacao-qt.json").read_text())["reason"], "timeout"
        )

    def prepare(self, checks, *, repair=False):
        for name in ("requirements.txt", "requirements-build.txt", "iniciar.py"):
            (self.root / name).write_text("", encoding="utf-8")
        environment = self.root / "venv"
        interpreter = environment / (
            "Scripts/python.exe" if assistente.sys.platform == "win32" else "bin/python"
        )
        interpreter.parent.mkdir(parents=True)
        interpreter.touch()
        events = queue.Queue()
        with (
            patch.object(assistente, "ROOT", self.root),
            patch.object(assistente, "ENVIRONMENT", environment),
            patch.object(assistente, "ensure_environment", return_value=(interpreter, False)),
            patch.object(assistente, "install_dependencies") as install,
            patch.object(assistente, "check_interface", side_effect=checks) as check,
            patch.object(assistente, "requirements_satisfied", return_value=False),
            patch.object(assistente, "launch_verified") as launch,
        ):
            assistente.prepare("run", events, repair=repair)
        return install, check, launch, list(events.queue)

    def test_prepare_retries_once_and_launches_only_after_success(self):
        install, check, launch, events = self.prepare([False, True])
        self.assertEqual([call.kwargs["repair"] for call in install.call_args_list], [False, True])
        self.assertEqual(check.call_count, 2)
        launch.assert_called_once()
        self.assertEqual(events[-1][0], "launched")

    def test_prepare_stops_after_failed_repair(self):
        install, check, launch, events = self.prepare([False, False])
        self.assertEqual(install.call_count, 2)
        self.assertEqual(check.call_count, 2)
        launch.assert_not_called()
        self.assertEqual(events[-1][0], "error")

    def test_explicit_repair_does_not_reinstall_twice(self):
        install, check, launch, events = self.prepare([False], repair=True)
        self.assertEqual(install.call_count, 1)
        self.assertEqual(check.call_count, 1)
        launch.assert_not_called()
        self.assertEqual(events[-1][0], "error")
