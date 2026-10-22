"""Regressões da RC5: publicação, preparação, logo e interrupção de movimento."""

from __future__ import annotations

import ctypes
import ast
import hashlib
import json
from pathlib import Path
import queue
import struct
import subprocess
import tempfile
import tomllib
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from pypdf import PdfReader
from PySide6.QtCore import QMetaObject, QUrl, Qt
from PySide6.QtQml import QQmlComponent
from PySide6.QtTest import QTest
from liarte_desktop import __version__
from liarte_desktop import installation_guard as guard
from liarte_desktop.identity import APPLICATION_MUTEX
from liarte_engine import pdf_importacoes as pdf
from tools import assistente, build_installer, preparation
from tests import test_comex, test_interface
from tests.test_qt import APP, pump

ROOT = Path(__file__).resolve().parents[1]


def variant(value):
    return value.toVariant() if hasattr(value, "toVariant") else value


def synthetic_pe(path):
    payload = bytearray(1_000_010)
    payload[:2] = b"MZ"
    struct.pack_into("<I", payload, 60, 128)
    payload[128:132] = b"PE\0\0"
    struct.pack_into("<H", payload, 132, 0x14C)
    struct.pack_into("<H", payload, 134, 3)
    struct.pack_into("<H", payload, 152, 0x10B)
    path.write_bytes(payload)


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "src/liarte_desktop").mkdir(parents=True)
        (self.root / "src/liarte_desktop/__init__.py").write_text(
            f'__version__ = "{__version__}"\n', encoding="utf-8"
        )
        for name in ("requirements.txt", "requirements-build.txt", "iniciar.py"):
            (self.root / name).write_text("", encoding="utf-8")
        self.interpreter = self.root / "env/bin/python"
        self.interpreter.parent.mkdir(parents=True)
        self.interpreter.touch()
        self.stamp = self.root / "logs/ambiente-verificado.json"

    def tearDown(self):
        self.temp.cleanup()

    def test_version_comes_from_application_literal_without_running_it(self):
        self.assertEqual(build_installer.release_version(self.root), __version__)
        path = self.root / "src/liarte_desktop/__init__.py"
        path.write_text('__version__ = "7.1.2-rc.12"\nraise Exception("must not run")\n')
        self.assertEqual(build_installer.release_version(self.root), "7.1.2-rc.12")
        self.assertEqual(
            build_installer.installer_name("7.1.2-rc.12"), "LIARTE_Desktop_7.1.2-rc.12_Setup.exe"
        )
        with self.assertRaises(ValueError):
            build_installer.installer_name("../other")

    def test_release_metadata_agrees_in_project_pe_and_installer(self):
        project = tomllib.loads((ROOT / "pyproject.toml").read_text())
        self.assertEqual(project["project"]["version"], __version__.replace("-rc.", "rc"))
        script = (ROOT / "INSTALADOR_LIARTE.iss").read_text(encoding="utf-8-sig")
        self.assertIn(f'#define AppVersion "{__version__}"', script)
        tree = ast.parse((ROOT / "versao_windows.txt").read_text())
        numeric = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id == "StringStruct" and ast.literal_eval(node.args[0]) in (
                "FileVersion",
                "ProductVersion",
            ):
                self.assertEqual(ast.literal_eval(node.args[1]), __version__)
            if node.func.id == "FixedFileInfo":
                numeric = [
                    ast.literal_eval(kw.value)
                    for kw in node.keywords
                    if kw.arg in ("filevers", "prodvers")
                ]
        self.assertEqual(len(numeric), 2)
        self.assertEqual(numeric[0], numeric[1])
        self.assertIn("VersionInfoVersion=" + ".".join(map(str, numeric[0])), script)

    def test_invalid_configured_compiler_does_not_fall_back_to_another_tool(self):
        with (
            patch.dict(build_installer.os.environ, {"LIARTE_ISCC": str(self.root / "missing.exe")}),
            patch.object(build_installer.shutil, "which") as lookup,
        ):
            with self.assertRaisesRegex(RuntimeError, "LIARTE_ISCC"):
                build_installer.installer_compiler()
            lookup.assert_not_called()

    def test_dos_signature_alone_is_not_a_valid_installer(self):
        path = self.root / "setup.exe"
        path.write_bytes(b"MZ" + bytes(1_000_000))
        with self.assertRaises(RuntimeError):
            build_installer.validate_installer(path)
        synthetic_pe(path)
        self.assertEqual(
            build_installer.validate_installer(path), hashlib.sha256(path.read_bytes()).hexdigest()
        )

    def _compile(self, *, produce=True, fail=False, smoke_version=None):
        output = self.root / "instalador" / build_installer.installer_name(__version__)
        output.parent.mkdir(exist_ok=True)
        output.write_bytes(b"previous installer")
        calls = []

        def run(command, **kwargs):
            calls.append(command)
            if len(calls) == 1:
                smoke = self.root / "dist/LIARTE_Desktop/AUTOTESTE.json"
                smoke.parent.mkdir(parents=True)
                smoke.write_text(
                    json.dumps(
                        {
                            "status": "ok",
                            "version": smoke_version or __version__,
                            "qml_warnings": [],
                        }
                    )
                )
            else:
                if fail:
                    raise subprocess.CalledProcessError(1, command)
                if produce:
                    directory = Path(next(value[2:] for value in command if value.startswith("/O")))
                    name = next(value[2:] for value in command if value.startswith("/F"))
                    synthetic_pe(directory / (name + ".exe"))
            return SimpleNamespace(returncode=0)

        with (
            patch.object(build_installer, "ROOT", self.root),
            patch.object(build_installer.sys, "platform", "win32"),
            patch.object(
                build_installer, "installer_compiler", return_value=self.root / "ISCC.exe"
            ),
            patch.object(build_installer.subprocess, "run", side_effect=run),
        ):
            build_installer.main()
        return output, calls

    def test_installer_is_published_for_current_version_from_fresh_staging(self):
        result, calls = self._compile()
        self.assertGreater(result.stat().st_size, 1_000_000)
        self.assertIn(f"/DAppVersion={__version__}", calls[1])
        self.assertFalse(list(result.parent.glob(".setup-*")))

    def test_old_success_file_cannot_mask_a_compiler_that_produced_nothing(self):
        with self.assertRaises(RuntimeError):
            self._compile(produce=False)
        result = self.root / "instalador" / build_installer.installer_name(__version__)
        self.assertEqual(result.read_bytes(), b"previous installer")

    def test_compiler_failure_preserves_previous_installer(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self._compile(fail=True)
        result = self.root / "instalador" / build_installer.installer_name(__version__)
        self.assertEqual(result.read_bytes(), b"previous installer")

    def test_other_version_smoke_does_not_authorize_publication(self):
        with self.assertRaises(RuntimeError):
            self._compile(smoke_version="old")
        result = self.root / "instalador" / build_installer.installer_name(__version__)
        self.assertEqual(result.read_bytes(), b"previous installer")

    def test_fingerprint_changes_with_code_resources_runtime_and_requirements(self):
        def fingerprint():
            return preparation.probe_fingerprint(self.interpreter, self.root)

        previous = fingerprint()
        for name, data in (
            ("src/test.qml", "Item{}"),
            ("src/logo.png", "changed logo"),
            ("requirements.txt", "changed pins"),
            ("iniciar.py", "changed entry"),
            ("env/bin/python", "changed runtime"),
        ):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(data)
            current = fingerprint()
            self.assertNotEqual(current, previous, name)
            previous = current

    def test_verification_stamp_is_bounded_and_rejects_invalid_data(self):
        preparation.save_probe(self.stamp, "current")
        report = json.loads(self.stamp.read_text())
        now = report["verified_at"]
        self.assertTrue(preparation.probe_is_current(self.stamp, "current", now=now + 1))
        self.assertFalse(preparation.probe_is_current(self.stamp, "changed", now=now + 1))
        self.assertFalse(
            preparation.probe_is_current(self.stamp, "current", now=now + preparation.PROBE_MAX_AGE)
        )
        self.assertFalse(preparation.probe_is_current(self.stamp, "current", now=now - 1))
        for invalid in ("null", "[]", '{"verified_at":true}', '{"verified_at":"today"}', "{"):
            self.stamp.write_text(invalid)
            self.assertFalse(preparation.probe_is_current(self.stamp, "current"))

    def invoke(self, *, mode="run", repair=False, launch_error=None):
        # Runtime path follows the host platform; Windows ctypes is checked separately.
        interpreter = (
            self.root
            / "env"
            / ("Scripts/python.exe" if assistente.sys.platform == "win32" else "bin/python")
        )
        interpreter.parent.mkdir(parents=True, exist_ok=True)
        interpreter.touch(exist_ok=True)
        events = queue.Queue()
        with (
            patch.object(assistente, "ROOT", self.root),
            patch.object(assistente, "ENVIRONMENT", self.root / "env"),
            patch.object(assistente, "ensure_environment", return_value=(interpreter, False)),
            patch.object(assistente, "requirements_satisfied", return_value=True) as requirements,
            patch.object(assistente, "install_dependencies") as install,
            patch.object(assistente, "check_interface", return_value=True) as check,
            patch.object(assistente, "launch_verified", side_effect=launch_error) as launch,
            patch.object(assistente.subprocess, "run", return_value=SimpleNamespace(returncode=0)),
        ):
            assistente.prepare(mode, events, repair=repair)
        return requirements, install, check, launch, list(events.queue)

    def test_repeated_opening_reuses_probe_but_still_checks_pins_and_ready_signal(self):
        first = self.invoke()
        self.assertEqual(first[2].call_count, 1)
        # Do not change runtime mtime between identical openings.
        with patch.object(Path, "touch"):
            second = self.invoke()
        self.assertEqual(second[0].call_count, 1)
        self.assertEqual(second[1].call_count, 0)
        self.assertEqual(second[2].call_count, 0)
        self.assertEqual(second[3].call_count, 1)
        self.assertEqual(second[4][-1][0], "launched")

    def test_failed_ready_handshake_invalidates_verification(self):
        self.invoke()
        with patch.object(Path, "touch"):
            result = self.invoke(launch_error=RuntimeError("did not open"))
        self.assertEqual(result[2].call_count, 0)
        self.assertEqual(result[4][-1][0], "error")
        self.assertFalse(self.stamp.exists())
        self.assertEqual(self.invoke()[2].call_count, 1)

    def test_repair_and_build_always_repeat_the_full_probe(self):
        self.invoke()
        with patch.object(Path, "touch"):
            repair = self.invoke(repair=True)
        self.assertEqual(repair[1].call_count, 1)
        self.assertEqual(repair[2].call_count, 1)
        with patch.object(Path, "touch"):
            build = self.invoke(mode="build")
        self.assertEqual(build[2].call_count, 1)
        self.assertEqual(build[4][-1][0], "success")
        self.assertTrue(any(kind == "output" for kind, _ in build[4]))

    def test_missing_inno_is_reported_before_creating_or_installing_environment(self):
        events = queue.Queue()
        with (
            patch.object(assistente, "ROOT", self.root),
            patch.object(
                build_installer, "installer_compiler", side_effect=RuntimeError("Inno missing")
            ),
            patch.object(assistente, "ensure_environment") as environment,
            patch.object(assistente, "install_dependencies") as install,
        ):
            assistente.prepare("installer", events)
        environment.assert_not_called()
        install.assert_not_called()
        self.assertEqual(list(events.queue)[-1], ("error", "Inno missing"))

    def test_windows_guard_uses_pointer_width_and_keeps_reference(self):
        create = Mock(return_value=0x123456789ABCDEF)
        with (
            patch.object(guard, "_HANDLE", None),
            patch.object(guard.sys, "platform", "win32"),
            patch.object(
                guard.ctypes,
                "WinDLL",
                create=True,
                return_value=SimpleNamespace(CreateMutexW=create),
            ),
        ):
            self.assertTrue(guard.hold_installation_mutex())
            self.assertTrue(guard.hold_installation_mutex())
            self.assertEqual(guard._HANDLE, 0x123456789ABCDEF)
        create.assert_called_once_with(None, 0, APPLICATION_MUTEX)
        self.assertEqual(create.restype, ctypes.c_void_p)
        self.assertEqual(create.argtypes, (ctypes.c_void_p, ctypes.c_int32, ctypes.c_wchar_p))

    def test_guard_failure_is_logged_without_preventing_app_start(self):
        with (
            patch.object(guard, "_HANDLE", None),
            patch.object(guard.sys, "platform", "win32"),
            patch.object(guard.ctypes, "WinDLL", create=True, side_effect=OSError("failed")),
            self.assertLogs("liarte.desktop", "ERROR"),
        ):
            self.assertFalse(guard.hold_installation_mutex())
        with (
            patch.object(guard.sys, "platform", "linux"),
            patch.object(guard.ctypes, "WinDLL", create=True) as load,
        ):
            self.assertFalse(guard.hold_installation_mutex())
            load.assert_not_called()

    def test_setup_preserves_identity_and_uses_short_explicit_wizard(self):
        script = (ROOT / "INSTALADOR_LIARTE.iss").read_text(encoding="utf-8-sig")
        for line in (
            "AppMutex=" + APPLICATION_MUTEX,
            "SetupMutex=Local\\LIARTE.Desktop.Setup",
            "DisableWelcomePage=no",
            "DisableDirPage=yes",
            "DisableReadyPage=yes",
            "UsePreviousAppDir=yes",
            "CloseApplications=yes",
            "SetupLogging=yes",
            "PrivilegesRequired=lowest",
        ):
            self.assertIn(line, script)
        self.assertIn("67BEFD46-16AD-4EB1-B183-FB8D2A8CA4A2", script)
        self.assertIn("MB_DEFBUTTON2", script)
        self.assertIn("msgButtonInstall", script)


class BrandedPdfTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "report.pdf"
        self.rows = [
            {
                "coNcm": "29161220",
                "ncm": "Ésteres de etila do ácido acrílico",
                "state": "São Paulo",
                "country": "China",
                "urf": f"PORTO TESTE {i:03d}",
                "metricKG": str(2000 + i),
                "metricCIF": str(11000 + i),
            }
            for i in range(160)
        ]

    def tearDown(self):
        self.temp.cleanup()

    def create(self):
        return pdf.create_import_pdf(self.path, [], self.rows, "2026-07", "2026-09")

    def test_logo_is_embedded_with_fixed_proportions_in_reserved_header_every_page(self):
        report = self.create()
        self.assertTrue(report["logo"])
        pages = PdfReader(self.path).pages
        self.assertEqual(len(pages), 4)
        for page in pages:
            draws = []

            def visit(operator, operands, cm, tm):
                if operator == b"Do":
                    draws.append(cm)

            page.extract_text(visitor_operand_before=visit)
            self.assertEqual(len(draws), 1)
            matrix = draws[0]
            self.assertAlmostEqual(matrix[0], 24 * 72 / 25.4, places=4)
            self.assertAlmostEqual(matrix[4], 14 * 72 / 25.4, places=4)
            self.assertAlmostEqual(
                matrix[5], float(page.mediabox.height) - 14.5 * 72 / 25.4, places=4
            )
            self.assertAlmostEqual(matrix[0] / matrix[3], 2167 / 725, places=4)
            self.assertGreater(matrix[5], float(page.mediabox.height) - 19 * 72 / 25.4)
            self.assertIn("Importações filtradas", page.extract_text())
            self.assertIn("Página", page.extract_text())
            images = page["/Resources"]["/XObject"]
            image = next(
                item.get_object()
                for item in images.values()
                if item.get_object().get("/Subtype") == "/Image"
            )
            self.assertEqual((image["/Width"], image["/Height"]), (2167, 725))
            self.assertIn("/SMask", image)

    def test_table_coordinates_text_and_page_count_match_rc4_baseline(self):
        self.create()
        baseline = json.loads((ROOT / "tests/fixtures/pdf_layout_rc4.json").read_text())
        result = []
        for page in PdfReader(self.path).pages:
            fragments = []

            def visit(text, cm, tm, font, size):
                x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
                y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
                if text.strip() and y < float(page.mediabox.height) - 23 * 72 / 25.4:
                    fragments.append([text, round(x, 5), round(y, 5), round(size, 5)])

            page.extract_text(visitor_text=visit)
            result.append(fragments)
        self.assertEqual(result, baseline["body_and_footer"])
        self.assertEqual(len(result), baseline["pages"])

    def test_missing_or_corrupt_brand_does_not_replace_existing_pdf(self):
        self.path.write_bytes(b"old report")
        for data in (None, b"invalid png"):
            broken = self.path.parent / "brand.png"
            if data:
                broken.write_bytes(data)
            with (
                patch.object(pdf, "PDF_LOGO_PATH", broken),
                self.assertRaisesRegex(pdf.PdfGenerationError, "logo"),
            ):
                self.create()
            self.assertEqual(self.path.read_bytes(), b"old report")
            self.assertFalse(list(self.path.parent.glob(".report-*")))

    def test_long_filter_caption_stays_inside_header_and_does_not_move_table(self):
        report = pdf.create_import_pdf(
            self.path,
            [],
            self.rows,
            "2026-07",
            "2026-09",
            {"country": ["País" * 100], "ncm": ["29161220"]},
        )
        self.assertEqual(report["pages"], 4)
        for page in PdfReader(self.path).pages:
            self.assertIn("Filtros:", page.extract_text())
            self.assertIn("Descrição NCM", page.extract_text())


class MotionRefinementTests(unittest.TestCase):
    setUp = test_comex.RealQtTests.setUp
    tearDown = test_comex.RealQtTests.tearDown
    load = test_comex.RealQtTests.load
    item = test_interface.InterfaceTests.item
    animate = test_interface.InterfaceTests._animate_chart

    def test_hiding_window_finishes_chart_animation_without_replaying_on_restore(self):
        chart = self.animate()
        points = variant(chart.property("points"))
        self.window.hide()
        APP.processEvents()
        self.assertFalse(chart.property("animating"))
        self.assertEqual(chart.property("reveal"), 1)
        self.window.show()
        QTest.qWait(50)
        self.assertFalse(chart.property("animating"))
        self.assertEqual(variant(chart.property("points")), points)
        self.assertEqual(self.bundle.messages, [])

    def test_minimizing_window_finishes_reveal(self):
        chart = self.animate()
        self.window.showMinimized()
        APP.processEvents()
        self.assertFalse(chart.property("animating"))
        self.assertEqual(chart.property("reveal"), 1)
        self.window.showNormal()
        APP.processEvents()
        self.assertFalse(chart.property("animating"))
        self.assertEqual(self.bundle.messages, [])

    def test_fast_series_updates_settle_to_last_series_and_remain_bounded(self):
        self.load()
        chart = self.item("monthlyChart")
        self.controller.setPreference("reducedMotion", False)
        before = chart.property("curvePaintCount")
        for index in range(12):
            chart.setProperty(
                "points",
                [
                    {"period": "2026-08", "label": "Agosto", "value": index + 1},
                    {"period": "2026-09", "label": "Setembro", "value": index + 2},
                ],
            )
            APP.processEvents()
        self.assertTrue(pump(lambda: not chart.property("animating"), 1))
        self.assertEqual(chart.property("reveal"), 1)
        self.assertEqual(variant(chart.property("points"))[-1]["value"], 13)
        self.assertLessEqual(chart.property("curvePaintCount") - before, 14)
        self.assertEqual(self.bundle.messages, [])

    def test_navigation_settles_when_window_is_hidden(self):
        self.load()
        self.controller.setPreference("reducedMotion", False)
        self.window.navigate("records")
        animation = self.item("navigationAnimation")
        self.window.hide()
        APP.processEvents()
        self.assertFalse(animation.property("running"))
        self.window.show()
        APP.processEvents()
        self.assertEqual(self.bundle.messages, [])

    def test_dropdown_rapid_open_close_remains_operable(self):
        popup = self.item("startPeriodPopup")
        for _ in range(4):
            QMetaObject.invokeMethod(popup, "open")
            QTest.qWait(25)
            QMetaObject.invokeMethod(popup, "close")
            QTest.qWait(25)
        QMetaObject.invokeMethod(popup, "open")
        self.assertTrue(pump(lambda: popup.property("opened")))
        self.assertAlmostEqual(popup.property("opacity"), 1)
        QMetaObject.invokeMethod(popup, "close")
        self.assertTrue(pump(lambda: not popup.property("visible")))
        self.assertEqual(self.bundle.messages, [])

    def test_filter_accepts_typing_during_opening_without_resetting_text(self):
        self.load()
        popup = self.item("countryFilterPopup")
        search = self.item("countryFilterSearch")
        QMetaObject.invokeMethod(popup, "open")
        self.assertTrue(pump(lambda: search.hasActiveFocus(), 0.08))
        for key in (Qt.Key_C, Qt.Key_H, Qt.Key_I, Qt.Key_N, Qt.Key_A):
            QTest.keyClick(self.window, key)
        self.assertEqual(search.property("text").casefold(), "china")
        self.assertTrue(pump(lambda: popup.property("opened")))
        self.assertEqual(search.property("text").casefold(), "china")
        self.assertEqual(self.controller.state["countryValues"], [])
        QMetaObject.invokeMethod(popup, "close")
        self.assertTrue(pump(lambda: not popup.property("visible")))
        self.assertEqual(self.bundle.messages, [])

    def progress_control(self):
        component = QQmlComponent(
            self.bundle.engine,
            QUrl.fromLocalFile(str(ROOT / "src/liarte_desktop/qml/components/TaskProgress.qml")),
        )
        control = component.create()
        self.assertIsNotNone(control, [str(error) for error in component.errors()])
        self._progress_component = component
        control.setParent(self.window)
        control.setParentItem(self.window.contentItem())
        control.setWidth(300)
        control.setHeight(6)
        control.setProperty("to", 100)
        return control

    def test_progress_smoothing_never_changes_the_reported_percentage(self):
        control = self.progress_control()
        self.controller.setPreference("reducedMotion", False)
        try:
            for value in (5, 74, 92, 21, 100):
                control.setProperty("value", value)
                self.assertEqual(control.property("value"), value)
                APP.processEvents()
                self.assertGreaterEqual(control.property("renderedPosition"), 0)
                self.assertLessEqual(control.property("renderedPosition"), 1)
            self.assertTrue(pump(lambda: abs(control.property("renderedPosition") - 1) < 0.0001, 1))
            self.controller.setPreference("reducedMotion", True)
            control.setProperty("value", 42)
            APP.processEvents()
            self.assertAlmostEqual(control.property("renderedPosition"), 0.42)
            self.assertEqual(self.bundle.messages, [])
        finally:
            control.deleteLater()

    def test_indeterminate_progress_stops_when_hidden_or_motion_reduced(self):
        control = self.progress_control()
        self.controller.setPreference("reducedMotion", False)
        try:
            control.setProperty("indeterminate", True)
            self.assertTrue(pump(lambda: control.property("indeterminateAnimating")))
            control.setVisible(False)
            APP.processEvents()
            self.assertFalse(control.property("indeterminateAnimating"))
            control.setVisible(True)
            self.assertTrue(pump(lambda: control.property("indeterminateAnimating")))
            self.controller.setPreference("reducedMotion", True)
            APP.processEvents()
            self.assertFalse(control.property("indeterminateAnimating"))
            self.controller.setPreference("reducedMotion", False)
            self.assertTrue(pump(lambda: control.property("indeterminateAnimating")))
            self.window.hide()
            APP.processEvents()
            self.assertFalse(control.property("indeterminateAnimating"))
            self.window.show()
            self.assertEqual(self.bundle.messages, [])
        finally:
            control.deleteLater()
