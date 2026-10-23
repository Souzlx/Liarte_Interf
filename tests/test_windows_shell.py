"""Políticas de atalho Windows testadas com APIs simuladas; execução nativa é outro gate."""

from pathlib import Path
import base64
import json
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from liarte_desktop.windows_shell import ensure_shortcuts, shortcut_script, ps_literal


class WindowsShellTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.exe = self.root / "LIARTE_Desktop.exe"
        self.exe.write_bytes(b"fixture")
        self.desktop = self.root / "OneDrive/Área de Trabalho"
        self.programs = self.root / "Menu Iniciar/Programas"
        self.paths = (
            self.desktop / "LIARTE Desktop.lnk",
            self.programs / "LIARTE Desktop/Análise de importações.lnk",
        )
        self.directory = self.root / "dados"

    def tearDown(self):
        self.temp.cleanup()

    def run_shortcuts(self):
        def save(command, **kwargs):
            self.assertEqual(command[-2], "-EncodedCommand")
            script = base64.b64decode(command[-1]).decode("utf-16le")
            self.assertIn(str(self.desktop), script)
            for path in self.paths:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("shortcut fixture")
            return SimpleNamespace(returncode=0)

        with (
            patch("liarte_desktop.windows_shell.identify_shortcuts") as identify,
            patch("liarte_desktop.windows_shell.sys.platform", "win32"),
            patch(
                "liarte_desktop.windows_shell.known_folder",
                side_effect=lambda name: self.desktop if name == "desktop" else self.programs,
            ),
            patch("liarte_desktop.windows_shell.subprocess.run", side_effect=save) as run,
        ):
            self.assertTrue(ensure_shortcuts(self.exe, self.directory))
            self.assertEqual(identify.call_count, run.call_count)
            return run.call_count

    def test_create_and_skip_repeated_startup(self):
        self.assertEqual(self.run_shortcuts(), 1)
        self.assertEqual(self.run_shortcuts(), 0)

    def test_deleted_shortcut_is_recreated(self):
        self.run_shortcuts()
        self.paths[0].unlink()
        self.assertEqual(self.run_shortcuts(), 1)
        self.assertTrue(self.paths[0].is_file())

    def test_corrupted_marker_does_not_prevent_recreation(self):
        self.directory.mkdir()
        (self.directory / "atalhos.json").write_text("[]")
        self.assertEqual(self.run_shortcuts(), 1)

    def test_moved_application_updates_only_its_owned_destinations(self):
        self.run_shortcuts()
        self.exe = self.root / "Nova pasta/LIARTE_Desktop.exe"
        self.exe.parent.mkdir()
        self.exe.write_bytes(b"fixture2")
        self.assertEqual(self.run_shortcuts(), 1)
        self.assertEqual(
            json.loads((self.directory / "atalhos.json").read_text(encoding="utf-8"))["target"], str(self.exe)
        )

    def test_powershell_literals_do_not_expand_paths(self):
        path = "C:\\João D'Ávila & $(calc)\\LIARTE.exe"
        self.assertEqual(ps_literal(path), "'C:\\João D''Ávila & $(calc)\\LIARTE.exe'")
        self.assertIn("-ne $old", shortcut_script(path, ["shortcut"]))

    def test_shortcut_success_requires_files_to_exist(self):
        with (
            patch("liarte_desktop.windows_shell.sys.platform", "win32"),
            patch("liarte_desktop.windows_shell.known_folder", return_value=self.desktop),
            patch(
                "liarte_desktop.windows_shell.subprocess.run",
                return_value=SimpleNamespace(returncode=0),
            ),
            self.assertLogs("liarte.desktop", level="WARNING"),
        ):
            self.assertFalse(ensure_shortcuts(self.exe, self.directory))

    def test_legacy_marker_gets_appid_migration_once(self):
        self.run_shortcuts()
        marker = self.directory / "atalhos.json"
        old = json.loads(marker.read_text(encoding="utf-8"))
        old.pop("schema")
        old.pop("app_id")
        marker.write_text(json.dumps(old))
        self.assertEqual(self.run_shortcuts(), 1)
        self.assertEqual(self.run_shortcuts(), 0)

    def test_appid_failure_does_not_record_success(self):
        for path in self.paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture")
        with (
            patch("liarte_desktop.windows_shell.sys.platform", "win32"),
            patch(
                "liarte_desktop.windows_shell.known_folder",
                side_effect=lambda n: self.desktop if n == "desktop" else self.programs,
            ),
            patch(
                "liarte_desktop.windows_shell.subprocess.run",
                return_value=SimpleNamespace(returncode=0),
            ),
            patch(
                "liarte_desktop.windows_shell.identify_shortcuts",
                side_effect=OSError("access denied"),
            ),
            self.assertLogs("liarte.desktop", level="WARNING"),
        ):
            self.assertFalse(ensure_shortcuts(self.exe, self.directory))
        self.assertFalse((self.directory / "atalhos.json").exists())
