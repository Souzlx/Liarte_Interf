"""Installer input integrity and reuse of a native portable build."""

from __future__ import annotations

from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools import build_installer


def fake_pe(path):
    """Synthetic header used only to test publication; never executed."""
    payload = bytearray(1_000_010)
    payload[:2] = b"MZ"
    struct.pack_into("<I", payload, 60, 128)
    payload[128:132] = b"PE\0\0"
    struct.pack_into("<H", payload, 132, 0x14C)
    struct.pack_into("<H", payload, 134, 3)
    struct.pack_into("<H", payload, 152, 0x10B)
    path.write_bytes(payload)


class InstallerPackageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.bundle = self.root / "portable bundle"
        self.bundle.mkdir()
        (self.bundle / "LIARTE_Desktop.exe").write_bytes(b"synthetic; never executed")
        (self.bundle / "_internal").mkdir()
        (self.bundle / "_internal/resource.txt").write_text("resource", encoding="utf-8")
        self.version = "5.3.1-rc.1"
        self.smoke = {
            "version": self.version,
            "status": "ok",
            "platform": "win32",
            "frozen": True,
            "qml_warnings": [],
        }
        self.manifest = self.bundle / "CHECKSUMS_SHA256.txt"
        self.write_manifest()

    def write_manifest(self):
        (self.bundle / "AUTOTESTE.json").write_text(json.dumps(self.smoke), encoding="utf-8")
        self.manifest.write_text(
            "".join(
                hashlib.sha256(path.read_bytes()).hexdigest()
                + "  "
                + path.relative_to(self.bundle).as_posix()
                + "\n"
                for path in sorted(self.bundle.rglob("*"))
                if path.is_file() and path != self.manifest
            ),
            encoding="utf-8",
        )

    def compile(self, *, run=None, destination=None):
        with patch.object(build_installer.subprocess, "run", side_effect=run) as invoke:
            result = build_installer.compile_installer(
                self.bundle,
                destination or self.root / "installer output",
                compiler=self.root / "ISCC.exe",
                version=self.version,
                root=self.root,
            )
        return result, invoke

    @staticmethod
    def successful_compiler(command, **kwargs):
        staging = Path(next(value[2:] for value in command if value.startswith("/O")))
        stem = next(value[2:] for value in command if value.startswith("/F"))
        fake_pe(staging / (stem + ".exe"))
        return subprocess.CompletedProcess(command, 0)

    def test_good_bundle_accepts_the_exact_native_preview(self):
        self.assertEqual(
            build_installer.validate_portable_bundle(self.bundle, self.version),
            self.bundle.resolve(),
        )

    def test_modified_bundle_is_rejected_before_compiler_or_output_creation(self):
        (self.bundle / "_internal/resource.txt").write_text("modified", encoding="utf-8")
        with patch.object(build_installer.subprocess, "run") as invoke:
            with self.assertRaisesRegex(RuntimeError, "Checksum divergente"):
                build_installer.compile_installer(
                    self.bundle,
                    self.root / "output",
                    compiler=self.root / "ISCC.exe",
                    version=self.version,
                )
        invoke.assert_not_called()
        self.assertFalse((self.root / "output").exists())

    def test_missing_and_unlisted_files_are_rejected(self):
        (self.bundle / "_internal/resource.txt").unlink()
        with self.assertRaisesRegex(RuntimeError, "ausentes ou não listados"):
            build_installer.validate_portable_bundle(self.bundle, self.version)
        self.write_manifest()
        (self.bundle / "unexpected.txt").write_text("unlisted", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "ausentes ou não listados"):
            build_installer.validate_portable_bundle(self.bundle, self.version)

    def test_incomplete_foreign_or_non_native_smoke_is_rejected(self):
        original = self.smoke.copy()
        for change in (
            {"version": "5.3.0"},
            {"platform": "linux"},
            {"frozen": False},
            {"frozen": 1},
            {"status": "failed"},
            {"qml_warnings": ["warning"]},
            {"qml_warnings": None},
        ):
            with self.subTest(change=change):
                self.smoke = {**original, **change}
                self.write_manifest()
                with self.assertRaisesRegex(RuntimeError, "validação nativa"):
                    build_installer.validate_portable_bundle(self.bundle, self.version)

    def test_invalid_manifest_paths_or_duplicate_entries_are_rejected(self):
        original = self.manifest.read_text(encoding="utf-8")
        for extra in (
            "0" * 64 + "  ../outside.txt\n",
            "0" * 64 + "  /outside.txt\n",
            "0" * 64 + "  _internal\\resource.txt\n",
            original.splitlines()[0] + "\n",
        ):
            with self.subTest(extra=extra):
                self.manifest.write_text(original + extra, encoding="utf-8")
                with self.assertRaisesRegex(RuntimeError, "manifesto.*inválido"):
                    build_installer.validate_portable_bundle(self.bundle, self.version)

    def test_installed_validation_only_permits_specific_root_uninstaller_files(self):
        for name in ("unins000.exe", "unins000.dat", "unins000.msg"):
            (self.bundle / name).write_bytes(b"synthetic uninstaller file")
        with self.assertRaisesRegex(RuntimeError, "ausentes ou não listados"):
            build_installer.validate_portable_bundle(self.bundle, self.version)
        self.assertEqual(
            build_installer.validate_portable_bundle(
                self.bundle, self.version, allow_installer_files=True
            ),
            self.bundle.resolve(),
        )
        for name in ("unins000.exe.bak", "_internal/unins000.exe"):
            with self.subTest(name=name):
                extra = self.bundle / name
                extra.write_bytes(b"unexpected")
                with self.assertRaisesRegex(RuntimeError, "ausentes ou não listados"):
                    build_installer.validate_portable_bundle(
                        self.bundle, self.version, allow_installer_files=True
                    )
                extra.unlink()
        (self.bundle / "_internal/resource.txt").write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "Checksum divergente"):
            build_installer.validate_portable_bundle(
                self.bundle, self.version, allow_installer_files=True
            )

    def test_compiler_gets_verified_external_bundle_and_staged_output(self):
        result, invoke = self.compile(run=self.successful_compiler)
        self.assertEqual(result.name, "LIARTE_Desktop_5.3.1-rc.1_Setup.exe")
        self.assertEqual(result.parent, (self.root / "installer output").resolve())
        self.assertGreater(result.stat().st_size, 1_000_000)
        command = invoke.call_args.args[0]
        collected = Path(next(value[12:] for value in command if value.startswith("/DBundleDir=")))
        self.assertEqual(collected.name, "portable")
        self.assertTrue(collected.parent.name.startswith(".setup-"))
        self.assertEqual(collected.parent.parent, result.parent)
        self.assertNotEqual(collected, self.bundle.resolve())
        self.assertIn("/DAppVersion=" + self.version, command)
        self.assertEqual(list(result.parent.glob(".setup-*")), [])

    def test_compiler_failure_preserves_existing_setup(self):
        destination = self.root / "output"
        destination.mkdir()
        previous = destination / build_installer.installer_name(self.version)
        previous.write_bytes(b"last known good setup")
        with self.assertRaises(subprocess.CalledProcessError):
            self.compile(
                run=subprocess.CalledProcessError(1, ["ISCC.exe"]), destination=destination
            )
        self.assertEqual(previous.read_bytes(), b"last known good setup")
        self.assertEqual(list(destination.glob(".setup-*")), [])

    def test_compile_uses_a_snapshot_when_the_caller_changes_original_bundle(self):
        observed = []

        def change_original(command, **kwargs):
            (self.bundle / "_internal/resource.txt").write_text("new build", encoding="utf-8")
            copied = Path(next(value[12:] for value in command if value.startswith("/DBundleDir=")))
            observed.append((copied / "_internal/resource.txt").read_text(encoding="utf-8"))
            return self.successful_compiler(command, **kwargs)

        result, _ = self.compile(run=change_original)
        self.assertEqual(observed, ["resource"])
        self.assertTrue(result.is_file())

    def test_output_inside_bundle_is_rejected(self):
        with patch.object(build_installer.subprocess, "run") as invoke:
            with self.assertRaisesRegex(RuntimeError, "fora da pasta portátil"):
                self.compile(destination=self.bundle / "installers")
        invoke.assert_not_called()

    def test_cli_reuses_bundle_without_rebuilding_portable(self):
        output = self.root / "output"
        with (
            patch.object(build_installer.sys, "platform", "win32"),
            patch.object(build_installer, "release_version", return_value=self.version),
            patch.object(
                build_installer, "installer_compiler", return_value=self.root / "ISCC.exe"
            ),
            patch.object(
                build_installer.subprocess, "run", side_effect=self.successful_compiler
            ) as invoke,
            redirect_stdout(io.StringIO()),
        ):
            build_installer.main(["--bundle", str(self.bundle), "--output", str(output)])
        self.assertEqual(invoke.call_count, 1)
        self.assertEqual(invoke.call_args.args[0][0], str(self.root / "ISCC.exe"))
        self.assertTrue((output / build_installer.installer_name(self.version)).is_file())
