"""Distribution gates refuse unsafe profiles and unverified installer reports."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

from tools import test_installer_windows as installer


class InstallerSmokeContractTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.version = "5.3.1-rc.1"
        self.bundle = self.root / "portable"
        self.bundle.mkdir()
        (self.bundle / "LIARTE_Desktop.exe").write_bytes(b"synthetic; never executed")
        (self.bundle / "resource.txt").write_bytes(b"known resource")
        self.payload = self.smoke(self.version)
        self.write_manifest(self.version)
        self.setup = self.root / installer.installer_name(self.version)
        body = bytearray(1_000_010)
        body[:2] = b"MZ"
        struct.pack_into("<I", body, 60, 128)
        body[128:132] = b"PE\0\0"
        struct.pack_into("<H", body, 132, 0x14C)
        struct.pack_into("<H", body, 134, 3)
        struct.pack_into("<H", body, 152, 0x10B)
        self.setup.write_bytes(body)
        self.report = {
            "status": "ok",
            "version": self.version,
            "setup_sha256": installer.digest(self.setup),
            "tests": dict.fromkeys(installer.LIFECYCLE_CHECKS, True),
            "fresh_installed_smoke": self.payload,
            "upgraded_installed_smoke": self.payload,
        }
        self.smoke_path = self.root / "installer-smoke.json"

    @staticmethod
    def smoke(version):
        return {
            "status": "ok",
            "version": version,
            "platform": "win32",
            "frozen": True,
            "qml_warnings": [],
            "themes_checked": ["light", "dark"],
            "document_resources": dict.fromkeys(
                ("excel", "pdf", "powerbi", "inventory_backups"), "ok"
            ),
        }

    def write_manifest(self, version):
        (self.bundle / "AUTOTESTE.json").write_text(json.dumps(self.smoke(version)))
        manifest = "".join(
            installer.digest(path) + "  " + path.name + "\n"
            for path in sorted(self.bundle.iterdir())
            if path.name != "CHECKSUMS_SHA256.txt"
        )
        (self.bundle / "CHECKSUMS_SHA256.txt").write_text(manifest)

    def publish(self, output, *, channel=None):
        self.smoke_path.write_text(json.dumps(self.report))
        with patch.object(installer, "release_version", return_value=self.version):
            if channel is not None:
                return installer.prepare_installer_assets(
                    self.bundle, self.setup, self.smoke_path, output, channel=channel
                )
            return installer.prepare_preview_assets(
                self.bundle, self.setup, self.smoke_path, output
            )

    def stable(self):
        self.version = "5.3.1"
        self.setup = self.setup.rename(self.root / installer.installer_name(self.version))
        self.payload = self.smoke(self.version)
        self.write_manifest(self.version)
        self.report.update({
            "version": self.version,
            "baseline_version": installer.BASELINE_VERSION,
            "baseline_installed_smoke": self.smoke(installer.BASELINE_VERSION),
            "fresh_installed_smoke": self.payload,
            "upgraded_installed_smoke": self.payload,
            "previous_version": installer.PREVIOUS_VERSION,
            "previous_setup_sha256": "a" * 64,
            "previous_installed_smoke": self.smoke(installer.PREVIOUS_VERSION),
            "previous_upgraded_installed_smoke": self.payload,
        })
        self.report["tests"][installer.PREVIOUS_UPGRADE_CHECK] = True

    def previous_setup(self):
        previous = self.root / installer.installer_name(installer.PREVIOUS_VERSION)
        previous.write_bytes(self.setup.read_bytes())
        checksum = self.root / "previous-SHA256SUMS.txt"
        checksum.write_text(installer.digest(previous) + "  " + previous.name + "\n")
        return previous, checksum

    def archive(self, entries):
        path = self.root / "LIARTE_Desktop_5.3.0_Windows_x64.zip"
        with zipfile.ZipFile(path, "w") as packed:
            for name, value in entries:
                packed.writestr(name, value)
        checksum = self.root / "SHA256SUMS.txt"
        checksum.write_text(installer.digest(path) + "  " + path.name + "\n")
        return path, checksum

    def test_native_profile_changes_require_hosted_disposable_windows_ci(self):
        good = {
            "GITHUB_ACTIONS": "true",
            "RUNNER_OS": "Windows",
            "RUNNER_ENVIRONMENT": "github-hosted",
        }
        installer.require_disposable_ci(True, good, "win32")
        for explicit, environment, platform in (
            (False, good, "win32"),
            (True, {}, "win32"),
            (True, {**good, "RUNNER_ENVIRONMENT": "self-hosted"}, "win32"),
            (True, good, "linux"),
        ):
            with self.subTest(environment=environment, platform=platform):
                with self.assertRaises(RuntimeError):
                    installer.require_disposable_ci(explicit, environment, platform)

    def test_existing_user_data_settings_or_shortcuts_abort_before_install(self):
        profile, program, shortcut = (
            self.root / name for name in ("profile", "program", "existing.lnk")
        )
        installer.require_pristine_profile(
            profile, program, (shortcut,), settings_exist=False, installed=False
        )
        for name in (profile, program, shortcut):
            name.write_bytes(b"must not modify")
            with self.assertRaises(RuntimeError):
                installer.require_pristine_profile(
                    profile, program, (shortcut,), settings_exist=False, installed=False
                )
            self.assertEqual(name.read_bytes(), b"must not modify")
            name.unlink()
        for settings, installed in ((True, False), (False, True)):
            with self.assertRaises(RuntimeError):
                installer.require_pristine_profile(
                    profile, program, (shortcut,), settings_exist=settings, installed=installed
                )

    def test_current_installed_smoke_requires_backup_resource_baseline_remains_supported(self):
        installer.verify_smoke_payload(self.payload, self.version)
        self.payload["document_resources"].pop("inventory_backups")
        with self.assertRaises(RuntimeError):
            installer.verify_smoke_payload(self.payload, self.version)
        old = self.smoke("5.3.0")
        old["document_resources"].pop("inventory_backups")
        installer.verify_smoke_payload(old, "5.3.0")
        with self.assertRaises(RuntimeError):
            installer.verify_smoke_payload(old, self.version)

    def test_single_uninstall_shortcut_accepts_powershell_json_object(self):
        shortcut = self.root / "Desinstalar.lnk"
        shortcut.touch()
        target = self.bundle / "unins000.exe"
        entry = {"path": str(shortcut), "target": str(target), "working": ""}
        result = SimpleNamespace(stdout=json.dumps(entry).encode("utf-8"))
        with (
            patch.dict(installer.os.environ, {"SystemRoot": str(self.root)}),
            patch.object(installer.subprocess, "run", return_value=result) as process,
        ):
            installer.check_shortcuts((shortcut,), target, working_directory=False)
        self.assertEqual(process.call_count, 1)

    def test_two_application_shortcuts_accept_array_and_reject_another_target(self):
        paths = (self.root / "Desktop.lnk", self.root / "Análise de importações.lnk")
        for path in paths:
            path.touch()
        target = self.bundle / "LIARTE_Desktop.exe"
        entries = [
            {"path": str(path), "target": str(target), "working": str(target.parent)}
            for path in paths
        ]
        result = SimpleNamespace(stdout=json.dumps(entries).encode("utf-8"))
        with (
            patch.dict(installer.os.environ, {"SystemRoot": str(self.root)}),
            patch.object(installer.subprocess, "run", return_value=result),
        ):
            installer.check_shortcuts(paths, target)
            entries[1]["target"] = str(self.root / "different-installation.exe")
            result.stdout = json.dumps(entries).encode("utf-8")
            with self.assertRaisesRegex(RuntimeError, "outra instalação"):
                installer.check_shortcuts(paths, target)

    def test_baseline_checksum_is_verified_before_creating_extracted_files(self):
        archive, checksum = self.archive([("LIARTE_Desktop/a", b"original")])
        archive.write_bytes(archive.read_bytes() + b"changed")
        output = self.root / "extract"
        with self.assertRaisesRegex(ValueError, "checksum"):
            installer.extract_baseline(archive, checksum, output)
        self.assertFalse(output.exists())

    def test_baseline_zip_rejects_escape_and_windows_case_collisions(self):
        for entries in (
            [("LIARTE_Desktop/../outside.txt", b"escape")],
            [("LIARTE_Desktop//resource.txt", b"noncanonical")],
            [("LIARTE_Desktop/A", b"first"), ("LIARTE_Desktop/a", b"second")],
        ):
            with self.subTest(entries=entries):
                archive, checksum = self.archive(entries)
                output = self.root / "extract"
                with self.assertRaisesRegex(ValueError, "Caminho"):
                    installer.extract_baseline(archive, checksum, output)
                self.assertFalse(output.exists())
                self.assertFalse((self.root / "outside.txt").exists())

    def test_incomplete_or_changed_installer_does_not_publish_preview_assets(self):
        output = self.root / "published"
        output.mkdir()
        previous = output / "previous.txt"
        previous.write_bytes(b"previous package")
        for field in installer.LIFECYCLE_CHECKS:
            self.report["tests"][field] = False
            with self.assertRaises(ValueError):
                self.publish(output)
            self.report["tests"][field] = True
            self.assertEqual(list(output.iterdir()), [previous])
        self.report["setup_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            self.publish(output)
        self.assertEqual(previous.read_bytes(), b"previous package")

    def test_successful_preview_preserves_bundle_and_checksums_both_delivered_files(self):
        output = self.root / "published"
        result = self.publish(output)
        checksums = dict(
            line.split("  ", 1)[::-1] for line in Path(result["checksum"]).read_text().splitlines()
        )
        self.assertEqual(set(checksums), {Path(result["archive"]).name, self.setup.name})
        for name, expected in checksums.items():
            self.assertEqual(installer.digest(output / name), expected)
        self.assertEqual(Path(result["setup"]).read_bytes(), self.setup.read_bytes())
        with zipfile.ZipFile(result["archive"]) as packed:
            self.assertIsNone(packed.testzip())
            self.assertEqual(packed.read("LIARTE_Desktop/resource.txt"), b"known resource")
        self.assertEqual(result["tag"], "v" + self.version)

    def test_successful_stable_requires_both_upgrade_paths_and_checksums_setup_and_zip(self):
        self.stable()
        output = self.root / "published"
        result = self.publish(output, channel="stable")
        self.assertEqual(result["tag"], "v5.3.1")
        checksums = dict(
            line.split("  ", 1)[::-1] for line in Path(result["checksum"]).read_text().splitlines()
        )
        self.assertEqual(set(checksums), {Path(result["archive"]).name, self.setup.name})
        for name, expected in checksums.items():
            self.assertEqual(installer.digest(output / name), expected)
        with zipfile.ZipFile(result["archive"]) as packed:
            self.assertIsNone(packed.testzip())
            smoke = json.loads(packed.read("LIARTE_Desktop/AUTOTESTE.json"))
            self.assertEqual(smoke["version"], "5.3.1")

    def test_stable_rejects_missing_previous_setup_proof_before_creating_output(self):
        self.stable()
        original = json.loads(json.dumps(self.report))
        output = self.root / "published"
        for field in ("baseline_version", "previous_version", "previous_setup_sha256"):
            with self.subTest(field=field):
                self.report = json.loads(json.dumps(original))
                del self.report[field]
                with self.assertRaisesRegex(ValueError, "atualização validada"):
                    self.publish(output, channel="stable")
                self.assertFalse(output.exists())
        for update in (
            {"baseline_version": "5.2.0"},
            {"previous_version": "5.3.1-rc.1"},
            {"previous_setup_sha256": 1},
            {"previous_setup_sha256": "not-a-digest"},
        ):
            with self.subTest(update=update):
                self.report = json.loads(json.dumps(original))
                self.report.update(update)
                with self.assertRaisesRegex(ValueError, "atualização validada"):
                    self.publish(output, channel="stable")
                self.assertFalse(output.exists())
        self.report = original
        self.report["tests"][installer.PREVIOUS_UPGRADE_CHECK] = False
        with self.assertRaisesRegex(ValueError, "atualização validada"):
            self.publish(output, channel="stable")
        self.assertFalse(output.exists())

    def test_stable_rejects_missing_or_non_native_smoke_for_either_upgrade(self):
        self.stable()
        original = json.loads(json.dumps(self.report))
        output = self.root / "published"
        for field in (
            "baseline_installed_smoke", "previous_installed_smoke",
            "previous_upgraded_installed_smoke",
        ):
            for replacement in (None, {}, {"platform": "linux"}):
                with self.subTest(field=field, replacement=replacement):
                    self.report = json.loads(json.dumps(original))
                    self.report[field] = replacement
                    with self.assertRaisesRegex(RuntimeError, "autoteste nativo"):
                        self.publish(output, channel="stable")
                    self.assertFalse(output.exists())

    def test_stable_and_preview_channels_cannot_publish_each_others_versions(self):
        output = self.root / "published"
        for channel in ("stable", "invalid"):
            with self.subTest(channel=channel):
                with self.assertRaisesRegex(ValueError, "canal de publicação"):
                    self.publish(output, channel=channel)
                self.assertFalse(output.exists())
        self.stable()
        with self.assertRaisesRegex(ValueError, "canal de publicação"):
            self.publish(output)
        self.assertFalse(output.exists())

    def test_previous_setup_requires_matching_published_digest_and_valid_windows_header(self):
        previous, checksum = self.previous_setup()
        self.assertEqual(
            installer.validate_previous_setup(previous, checksum), installer.digest(previous)
        )
        previous.write_bytes(previous.read_bytes() + b"changed")
        with self.assertRaisesRegex(ValueError, "diverge"):
            installer.validate_previous_setup(previous, checksum)
        previous.write_bytes(b"not a Windows Setup" * 100_000)
        checksum.write_text(installer.digest(previous) + "  " + previous.name + "\n")
        with self.assertRaisesRegex(RuntimeError, "cabeçalho Windows"):
            installer.validate_previous_setup(previous, checksum)

    def test_previous_setup_checksum_refuses_missing_duplicate_or_malformed_entries(self):
        previous, checksum = self.previous_setup()
        valid = checksum.read_text()
        for contents in (
            "a" * 64 + "  other.exe\n", valid + valid, "invalid checksum\n",
        ):
            with self.subTest(contents=contents):
                checksum.write_text(contents)
                with self.assertRaises(ValueError):
                    installer.validate_previous_setup(previous, checksum)
        renamed = previous.rename(self.root / "unexpected.exe")
        with self.assertRaisesRegex(ValueError, "Setup publicado"):
            installer.validate_previous_setup(renamed, checksum)

    def test_stable_lifecycle_refuses_missing_previous_setup_before_touching_workspace(self):
        workspace = self.root / "ci-workspace"
        command = [
            "test_installer_windows.py", "--setup", str(self.setup),
            "--baseline-archive", "baseline.zip", "--baseline-checksum", "baseline.txt",
            "--output", str(self.root / "report.json"), "--workspace", str(workspace),
            "--ci-profile",
        ]
        with (
            patch("sys.argv", command),
            patch.object(installer, "release_version", return_value="5.3.1"),
            patch.object(installer, "require_disposable_ci"),
            patch.object(installer, "install") as install,
        ):
            with self.assertRaisesRegex(ValueError, "Setup anterior publicado"):
                installer.main()
        self.assertFalse(workspace.exists())
        install.assert_not_called()

    def test_lifecycle_refuses_unpaired_or_changed_previous_setup_before_any_install(self):
        previous, checksum = self.previous_setup()
        previous.write_bytes(previous.read_bytes() + b"changed after publication")
        workspace = self.root / "ci-workspace"
        command = [
            "test_installer_windows.py", "--setup", str(self.setup),
            "--baseline-archive", "baseline.zip", "--baseline-checksum", "baseline.txt",
            "--output", str(self.root / "report.json"), "--workspace", str(workspace),
            "--ci-profile",
        ]
        for arguments, message in (
            (["--previous-setup", str(previous)], "informados juntos"),
            (["--previous-checksum", str(checksum)], "informados juntos"),
            (["--previous-setup", str(previous), "--previous-checksum", str(checksum)], "diverge"),
        ):
            with self.subTest(arguments=arguments):
                with (
                    patch("sys.argv", command + arguments),
                    patch.object(installer, "release_version", return_value="5.3.1"),
                    patch.object(installer, "require_disposable_ci"),
                    patch.object(installer, "install") as install,
                ):
                    with self.assertRaisesRegex(ValueError, message):
                        installer.main()
                self.assertFalse(workspace.exists())
                install.assert_not_called()

    def test_stable_packaging_io_failure_restores_previous_delivered_files(self):
        self.stable()
        output = self.root / "published"
        result = self.publish(output, channel="stable")
        previous = {Path(result[key]): Path(result[key]).read_bytes()
                    for key in ("archive", "setup", "checksum")}
        replace = installer.os.replace

        def fail_setup_commit(source, destination):
            if Path(destination) == Path(result["setup"]):
                raise OSError("simulated Setup publication failure")
            return replace(source, destination)

        with patch.object(installer.os, "replace", side_effect=fail_setup_commit):
            with self.assertRaisesRegex(OSError, "publication failure"):
                self.publish(output, channel="stable")
        self.assertEqual({path: path.read_bytes() for path in previous}, previous)

    def test_workflow_outputs_use_real_newlines(self):
        workflow = Path(installer.ROOT / ".github/workflows/installer.yml").read_text()
        line = next(line.strip() for line in workflow.splitlines() if "output.write(" in line)
        tree = ast.parse(line)
        value = tree.body[0].value.args[0]
        encoded = eval(
            compile(ast.Expression(value), "workflow-output", "eval"),
            {"key": "tag", "value": "v5.3.1-rc.1"},
        )
        self.assertEqual(encoded, "tag=v5.3.1-rc.1\n")
