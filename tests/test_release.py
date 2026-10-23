"""Regressões do pacote verificado antes da publicação estável."""

from __future__ import annotations

import hashlib
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from tools import prepare_release


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.bundle = self.root / "portable"
        self.output = self.root / "release"
        self.bundle.mkdir()
        self.smoke = {
            "status": "ok", "version": "5.2.0", "platform": "win32",
            "frozen": True, "qml_warnings": [],
        }
        (self.bundle / "LIARTE_Desktop.exe").write_bytes(b"synthetic executable; never executed")
        internal = self.bundle / "_internal"
        internal.mkdir()
        (internal / "resource.txt").write_text("recurso sintético", encoding="utf-8")
        self.write_smoke_and_manifest()
        self.version = patch.object(prepare_release, "release_version", return_value="5.2.0")
        self.version.start()
        self.addCleanup(self.version.stop)
        self.addCleanup(self.temporary.cleanup)

    def write_smoke_and_manifest(self):
        (self.bundle / "AUTOTESTE.json").write_text(json.dumps(self.smoke), encoding="utf-8")
        entries = []
        for path in sorted(self.bundle.rglob("*")):
            if path.is_file() and path.name != prepare_release.MANIFEST:
                entries.append(hashlib.sha256(path.read_bytes()).hexdigest() + "  "
                               + path.relative_to(self.bundle).as_posix() + "\n")
        (self.bundle / prepare_release.MANIFEST).write_text("".join(entries), encoding="utf-8")

    def reject(self, message):
        with self.assertRaisesRegex(ValueError, message):
            prepare_release.prepare_release(self.bundle, self.output)
        self.assertFalse(self.output.exists())

    def test_verified_bundle_preserves_files_and_has_a_matching_archive_checksum(self):
        result = prepare_release.prepare_release(self.bundle, self.output)
        self.assertEqual((result["tag"], result["title"]), ("v5.2.0", "LIARTE 5.2.0"))
        archive = Path(result["archive"])
        self.assertEqual(archive.name, "LIARTE_Desktop_5.2.0_Windows_x64.zip")
        self.assertEqual(Path(result["checksum"]).read_text(encoding="utf-8"),
                         hashlib.sha256(archive.read_bytes()).hexdigest() + "  " + archive.name + "\n")
        with zipfile.ZipFile(archive) as packed:
            expected = {"LIARTE_Desktop/" + path.relative_to(self.bundle).as_posix()
                        for path in self.bundle.rglob("*") if path.is_file()}
            self.assertEqual(set(packed.namelist()), expected)
            for name in expected:
                self.assertEqual(packed.read(name), (self.bundle / name.split("/", 1)[1]).read_bytes())

    def test_old_version_or_non_native_smoke_cannot_authorize_a_stable_release(self):
        for update in ({"version": "5.2.0-rc.10"}, {"platform": "linux"},
                       {"frozen": False}, {"status": "failed"}, {"qml_warnings": ["warning"]}):
            with self.subTest(update=update):
                original = dict(self.smoke)
                self.smoke.update(update)
                self.write_smoke_and_manifest()
                self.reject("autoteste")
                self.smoke = original

    def test_command_exposes_verified_files_to_the_release_workflow(self):
        github_output = self.root / "github-output.txt"
        stdout = io.StringIO()
        with (
            patch("sys.argv", ["prepare_release.py", "--bundle", str(self.bundle),
                               "--output", str(self.output)]),
            patch.dict(os.environ, {"GITHUB_OUTPUT": str(github_output)}),
            redirect_stdout(stdout),
        ):
            prepare_release.main()
        result = json.loads(stdout.getvalue())
        outputs = dict(line.split("=", 1) for line in
                       github_output.read_text(encoding="utf-8").splitlines())
        self.assertEqual(outputs, result)
        self.assertEqual(outputs["tag"], "v5.2.0")
        self.assertTrue(Path(outputs["archive"]).is_file())
        self.assertTrue(Path(outputs["checksum"]).is_file())

    def test_a_changed_file_is_rejected_before_creating_an_archive(self):
        (self.bundle / "_internal/resource.txt").write_text("alterado", encoding="utf-8")
        self.reject("Checksum divergente")

    def test_missing_or_unlisted_files_are_rejected(self):
        resource = self.bundle / "_internal/resource.txt"
        resource.unlink()
        self.reject("ausentes ou não listados")
        resource.write_text("restaurado", encoding="utf-8")
        self.write_smoke_and_manifest()
        (self.bundle / "extra.txt").write_text("sem checksum", encoding="utf-8")
        self.reject("ausentes ou não listados")

    def test_prerelease_version_is_rejected(self):
        with patch.object(prepare_release, "release_version", return_value="5.2.0-rc.10"):
            self.reject("sem sufixo RC")

    def test_manifest_paths_cannot_escape_the_bundle(self):
        manifest = self.bundle / prepare_release.MANIFEST
        original = manifest.read_text(encoding="utf-8")
        for name in ("../outside.txt", "/outside.txt", "_internal\\resource.txt"):
            with self.subTest(name=name):
                manifest.write_text(original + "0" * 64 + "  " + name + "\n", encoding="utf-8")
                self.reject("manifesto.*inválido")

