from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest

from tools.build_windows import build_arguments
from tools.qt_qml_policy import allowed_destination

ROOT = Path(__file__).resolve().parent.parent


class DistributionTests(unittest.TestCase):
    def test_qml_collection_keeps_controls_and_excludes_unrelated_modules(self):
        for path in (
            "PySide6/Qt/qml/QtQuick",
            "PySide6/qml/QtQml/Models",
            "PySide6/Qt/qml/QtQuick/Controls/Basic/impl",
            "PySide6\\qml\\QtQuick\\Layouts",
        ):
            self.assertTrue(allowed_destination(path), path)
        for path in (
            "PySide6/Qt/qml/QtQuick/Pdf",
            "PySide6/Qt/qml/QtGraphs",
            "PySide6/Qt/qml/QtQuick3D",
            "PySide6/Qt/qml/QtQuick/Timeline",
            "PySide6/Qt/qml/QtQuick/VirtualKeyboard",
            "elsewhere",
        ):
            self.assertFalse(allowed_destination(path), path)
        self.assertFalse(allowed_destination("PySide6/Qt/qml/QtQuick/Controls/Material"))

    def test_freezer_resources_and_icon_exist(self):
        arguments = build_arguments(Path("output"), Path("work"))
        self.assertIn("--additional-hooks-dir", arguments)
        self.assertIn("--onedir", arguments)
        for position, value in enumerate(arguments):
            if value == "--add-data":
                source = arguments[position + 1].rsplit(";" if sys.platform == "win32" else ":", 1)[
                    0
                ]
                self.assertTrue(Path(source).exists(), source)
        self.assertTrue(Path(arguments[arguments.index("--icon") + 1]).is_file())
        self.assertTrue(any("liarte_core/data" in arg for arg in arguments))

    def test_native_windows_tls_dependency_is_in_source_and_frozen_distribution(self):
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        pins = {
            line.strip()
            for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        }
        self.assertEqual(set(project["project"]["dependencies"]), pins)
        self.assertIn("truststore==0.10.5", pins)
        arguments = build_arguments(Path("output"), Path("work"))
        collected = {
            arguments[index + 1]
            for index, argument in enumerate(arguments)
            if argument == "--collect-all"
        }
        self.assertIn("truststore", collected)

    def test_source_smoke_uses_real_qt_entrypoint(self):
        with tempfile.TemporaryDirectory() as directory:
            result = Path(directory) / "smoke.json"
            env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software")
            process = subprocess.run(
                [sys.executable, str(ROOT / "iniciar.py"), "--smoke-test", str(result)],
                capture_output=True,
                text=True,
                timeout=35,
                env=env,
            )
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
            payload = json.loads(result.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "ok")
            self.assertTrue(payload["synthetic"])
            self.assertEqual(payload["qml_warnings"], [])
            self.assertEqual(payload["rows_in_page"], 50)
            self.assertIn("policy", payload["https_transport"])
