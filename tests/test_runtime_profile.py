"""Development persistence stays separate from the installed LIARTE profile."""

from dataclasses import replace
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QSettings, QUrl

from liarte_core.inventory_backup import list_backups
from liarte_core.inventory_io import read_snapshot, write_snapshot
from liarte_desktop import app as desktop
from liarte_desktop import runtime_profile as runtime
from liarte_desktop.preferences import ApplicationPreferences
from tests.test_inventory import sample
from tests.test_qt import APP, pump

ROOT = Path(__file__).resolve().parents[1]


def fingerprints(root):
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


class RuntimeProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name).resolve()
        self.production = self.directory / "installed-profile"
        self.production.mkdir()
        (self.production / "untouched.txt").write_bytes(b"installed profile")
        self.before = fingerprints(self.production)

    def test_default_profile_preserves_native_settings_and_existing_paths(self):
        with patch.object(
            runtime.QStandardPaths, "writableLocation", return_value=str(self.production)
        ):
            profile = runtime.resolve_profile(None)
        self.assertFalse(profile.development)
        self.assertEqual(profile.root, self.production)
        self.assertEqual(profile.data_dir, self.production / "dados")
        self.assertEqual(profile.inventory_cache, self.production / "estoque/base.liarte")
        self.assertEqual(profile.log_dir, self.production / "logs")
        with patch.object(runtime, "QSettings") as native:
            self.assertIs(runtime.open_settings(profile), native.return_value)
            native.assert_called_once_with()
        self.assertEqual(fingerprints(self.production), self.before)

    def test_development_profile_prepares_only_its_own_empty_directories(self):
        target = self.directory / "development-profile"
        profile = runtime.resolve_profile(target, default_root=self.production)
        profile.prepare()
        self.assertTrue(profile.development)
        self.assertEqual(profile.root, target.resolve())
        for path in (
            profile.data_dir,
            profile.inventory_cache.parent,
            profile.log_dir,
            profile.reports_dir,
            profile.central_dir,
        ):
            self.assertTrue(path.is_relative_to(target))
        self.assertTrue(target.is_dir())
        self.assertFalse(profile.settings_file.exists())
        self.assertFalse(profile.inventory_cache.exists())
        self.assertEqual(fingerprints(self.production), self.before)

    def test_production_equal_parent_and_child_paths_are_rejected_before_writes(self):
        for target in (
            self.production,
            self.production.parent,
            self.production / "nested-development",
        ):
            with self.subTest(target=target), self.assertRaises(ValueError):
                runtime.resolve_profile(target, default_root=self.production)
        self.assertEqual(fingerprints(self.production), self.before)
        self.assertFalse((self.production / "nested-development").exists())

    def test_profile_path_resolves_directory_links_before_comparing_production(self):
        link = self.directory / "production-alias"
        try:
            link.symlink_to(self.production, target_is_directory=True)
        except OSError:
            self.skipTest("Directory symlinks need extra Windows privileges")
        with self.assertRaises(ValueError):
            runtime.resolve_profile(link, default_root=self.production)
        self.assertEqual(fingerprints(self.production), self.before)

    def test_preexisting_nested_links_cannot_send_profile_writes_outside_root(self):
        for index, (name, directory) in enumerate((
            ("logs", True),
            ("central-comex/dados", True),
            ("central-comex/consultas.sqlite3", False),
        )):
            with self.subTest(path=name):
                target = self.directory / f"development-profile-{index}"
                link = target / name
                link.parent.mkdir(parents=True)
                destination = self.production if directory else self.production / "untouched.txt"
                try:
                    link.symlink_to(destination, target_is_directory=directory)
                except OSError:
                    self.skipTest("Symlinks need extra Windows privileges")
                profile = runtime.resolve_profile(target, default_root=self.production)
                with self.assertRaises(ValueError):
                    profile.prepare()
                self.assertEqual(fingerprints(self.production), self.before)

    def test_preferences_persist_in_ini_and_do_not_fall_back_to_native_settings(self):
        profile = runtime.resolve_profile(
            self.directory / "development-profile", default_root=self.production
        )
        profile.prepare()
        settings = runtime.open_settings(profile)
        self.assertEqual(Path(settings.fileName()), profile.settings_file)
        self.assertEqual(settings.format(), QSettings.Format.IniFormat)
        self.assertFalse(settings.fallbacksEnabled())
        preferences = ApplicationPreferences(settings)
        preferences.setPreference("dark", True)
        preferences.remember_page("platform/startupPage", "inventory")
        reopened = runtime.open_settings(profile)
        restored = ApplicationPreferences(reopened)
        self.assertTrue(restored.value("dark"))
        self.assertEqual(restored.text("platform/startupPage", "home"), "inventory")
        self.assertEqual(fingerprints(self.production), self.before)

    def test_no_settings_never_opens_any_settings_backend(self):
        for development in (False, True):
            profile = runtime.RuntimeProfile(self.directory / "profile", development)
            with self.subTest(development=development), patch.object(runtime, "QSettings") as backend:
                self.assertIsNone(runtime.open_settings(profile, no_settings=True))
                backend.assert_not_called()
        self.assertFalse((self.directory / "profile").exists())

    def test_logs_are_written_inside_development_profile(self):
        profile = runtime.resolve_profile(
            self.directory / "development-profile", default_root=self.production
        )
        profile.prepare()
        loggers = [logging.getLogger(name) for name in ("liarte.desktop", "liarte-comex-intelligence")]
        previous = [(logger, list(logger.handlers), logger.level) for logger in loggers]
        try:
            path = desktop.configure_log(profile)
            loggers[0].info("isolated development log")
            for handler in loggers[0].handlers:
                handler.flush()
            self.assertEqual(path, profile.log_dir / "desktop.log")
            self.assertIn("isolated development log", path.read_text(encoding="utf-8"))
            self.assertEqual(fingerprints(self.production), self.before)
        finally:
            originals = {handler for _, handlers, _ in previous for handler in handlers}
            added = {handler for logger in loggers for handler in logger.handlers} - originals
            for logger, handlers, level in previous:
                logger.handlers[:] = handlers
                logger.setLevel(level)
            for handler in added:
                handler.close()

    def test_profile_and_data_directory_cannot_be_combined_before_qt_startup(self):
        with (
            patch.object(desktop, "QGuiApplication") as gui,
            patch("sys.stderr", new_callable=io.StringIO),
            self.assertRaises(SystemExit) as failure,
        ):
            desktop.main([
                "--profile-dir", str(self.directory / "development-profile"),
                "--data-dir", str(self.production / "dados"),
            ])
        self.assertEqual(failure.exception.code, 2)
        gui.assert_not_called()
        self.assertEqual(fingerprints(self.production), self.before)

    def test_main_uses_profile_settings_logs_and_identity_without_installation_side_effects(self):
        profile = self.directory / "development-profile"
        script = r'''
import json
import logging
import os
from pathlib import Path
import sys
from unittest.mock import patch
from PySide6.QtCore import QCoreApplication, QTimer, Qt
from liarte_desktop import app, runtime_profile
from liarte_desktop import windows_shell
from liarte_desktop.identity import APP_USER_MODEL_ID

profile, production = map(Path, sys.argv[1:3])
real_bundle = app.create_bundle
real_settings = runtime_profile.QSettings
observed = {}

def settings(*args, **kwargs):
    if not args or args == ("LIARTE", "LIARTE Desktop F1"):
        raise AssertionError("Installed settings or migration must not be opened")
    return real_settings(*args, **kwargs)

settings.Format = real_settings.Format
settings.Status = real_settings.Status

def create_bundle(**kwargs):
    kwargs["size"] = 5
    bundle = real_bundle(**kwargs)
    bundle.preferences.setPreference("dark", True)
    observed["title"] = bundle.platform.windowTitle
    observed["cache"] = str(bundle.inventory._cache)
    observed["bundled"] = str(bundle.inventory._bundled)
    observed["qml_warnings"] = bundle.messages
    observed["qml_cache"] = os.environ.get("QML_DISK_CACHE_PATH")
    observed["pipeline_overrides"] = [
        os.environ.get(key) for key in ("QSG_RHI_PIPELINE_CACHE_LOAD", "QSG_RHI_PIPELINE_CACHE_SAVE")
    ]
    observed["automatic_pipeline_cache"] = (
        bundle.engine.rootObjects()[0].graphicsConfiguration().isAutomaticPipelineCacheEnabled()
    )
    observed["shader_cache_disabled"] = QCoreApplication.testAttribute(
        Qt.ApplicationAttribute.AA_DisableShaderDiskCache
    )
    logging.getLogger("liarte.desktop").info("profile startup checked")
    QTimer.singleShot(100, QCoreApplication.quit)
    return bundle

with (
    patch.object(app.QStandardPaths, "writableLocation", return_value=str(production)),
    patch.object(runtime_profile, "QSettings", new=settings),
    patch.object(app, "QSettings", new=settings),
    patch.object(app, "create_bundle", side_effect=create_bundle),
    patch.object(app, "hold_installation_mutex", side_effect=AssertionError("Installed mutex")),
    patch.object(windows_shell, "ensure_shortcuts", side_effect=AssertionError("Installed shortcuts")),
    patch.object(app, "set_process_identity") as identity,
    patch.object(sys, "frozen", True, create=True),
):
    code = app.main(["--demo", "--profile-dir", str(profile)])
    call = identity.call_args
    observed["app_id"] = call.args[0] if call.args else call.kwargs.get("app_id")
    assert observed["app_id"] and observed["app_id"] != APP_USER_MODEL_ID, observed
    assert code == 0, code
print(json.dumps(observed))
'''
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(ROOT / "src")
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["QT_QPA_PLATFORM"] = "offscreen"
        environment["QT_QUICK_BACKEND"] = "software"
        for key in ("QSG_RHI_PIPELINE_CACHE_LOAD", "QSG_RHI_PIPELINE_CACHE_SAVE"):
            environment[key] = str(self.production / "external-qt-cache")
        result = subprocess.run(
            [sys.executable, "-c", script, str(profile), str(self.production)],
            cwd=ROOT, env=environment, capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        observed = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertIn("Desenvolvimento", observed["title"])
        self.assertEqual(observed["qml_warnings"], [])
        self.assertTrue(Path(observed["qml_cache"]).is_relative_to(profile))
        self.assertTrue(observed["shader_cache_disabled"])
        self.assertEqual(observed["pipeline_overrides"], [None, None])
        self.assertFalse(observed["automatic_pipeline_cache"])
        self.assertEqual(Path(observed["cache"]), profile / "estoque/base.liarte")
        self.assertEqual(observed["bundled"], "None")
        settings = QSettings(str(profile / "settings.ini"), QSettings.Format.IniFormat)
        self.assertTrue(settings.value("dark", False, type=bool))
        self.assertIn("profile startup checked", (profile / "logs/desktop.log").read_text(encoding="utf-8"))
        self.assertEqual(fingerprints(self.production), self.before)


class RuntimeProfileUiTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.directory = Path(self.temp.name).resolve()
        self.production = self.directory / "installed-profile"
        self.production.mkdir()
        write_snapshot(sample(), self.production / "estoque/base.liarte")
        (self.production / "settings.ini").write_text("[General]\ndark=true\n", encoding="utf-8")
        self.before = fingerprints(self.production)
        self.profile = runtime.resolve_profile(
            self.directory / "development-profile", default_root=self.production
        )
        self.profile.prepare()
        self.bundles = []

    def tearDown(self):
        for bundle in reversed(self.bundles):
            bundle.services.comex_access.shutdown()
            bundle.controller.shutdown()
            desktop._finish_inventory_shutdown(bundle.inventory)
            for window in bundle.engine.rootObjects():
                window.close()
            bundle.engine.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            APP.processEvents()
        self.temp.cleanup()

    def bundle(self, *, demo=True, settings=True, profile=None):
        profile = self.profile if profile is None else profile
        bundle = desktop.create_bundle(
            size=5 if demo else None,
            settings=(
                (runtime.open_settings(profile) if profile.development else QSettings(
                    str(profile.settings_file), QSettings.Format.IniFormat
                )) if settings else None
            ),
            profile=profile,
        )
        self.bundles.append(bundle)
        APP.processEvents()
        self.assertEqual(bundle.messages, [])
        return bundle

    def idle(self, inventory):
        self.assertTrue(pump(
            lambda: not inventory.state["busy"] and not inventory._debounce.isActive(), 10
        ), inventory.state)

    def test_new_non_demo_profile_does_not_load_production_or_integrated_stock(self):
        with patch("liarte_engine.secure_http.urlopen", side_effect=AssertionError("Unexpected network")) as network:
            bundle = self.bundle(demo=False)
            bundle.inventory.ensureLoaded()
            self.idle(bundle.inventory)
            self.assertEqual(bundle.controller._provider.directory, self.profile.data_dir)
            self.assertIsNone(bundle.inventory._data)
            self.assertFalse(self.profile.inventory_cache.exists())
            self.assertFalse(bundle.preferences.value("dark"))
            bundle.platform.openModule("inventory")
            window = bundle.engine.rootObjects()[0]
            self.assertTrue(pump(lambda: window.findChild(QObject, "stockEmptyExplanation") is not None))
            explanation = window.findChild(QObject, "stockEmptyExplanation").property("text")
            self.assertIn("base de teste", explanation)
            self.assertNotIn("abre automaticamente", explanation)
            network.assert_not_called()
        self.assertEqual(fingerprints(self.production), self.before)

    def test_development_title_remains_visible_on_home_and_both_modules(self):
        bundle = self.bundle()
        window = bundle.engine.rootObjects()[0]
        for module in ("home", "imports", "inventory", "home"):
            bundle.platform.openModule(module)
            self.assertTrue(pump(lambda: window.title() == bundle.platform.windowTitle))
            self.assertIn("Desenvolvimento", window.title())
        bundle.preferences.setPreference("dark", True)
        restored = ApplicationPreferences(runtime.open_settings(self.profile))
        self.assertTrue(restored.value("dark"))
        self.assertEqual(fingerprints(self.production), self.before)

    def test_stock_publication_backup_and_restore_stay_inside_development_profile(self):
        bundle = self.bundle()
        original = sample()
        replacement = replace(
            original,
            source_name="Development replacement.pbix",
            source_hash="b" * 64,
            balances=tuple(replace(row, cost=row.cost + 100) for row in original.balances),
        )
        for index, data in enumerate((original, replacement)):
            source = self.directory / f"synthetic-source-{index}.liarte"
            write_snapshot(data, source)
            bundle.inventory.openFile(QUrl.fromLocalFile(str(source)))
            self.idle(bundle.inventory)
            self.assertFalse(bundle.inventory.state["error"])
        self.assertEqual(read_snapshot(self.profile.inventory_cache), replacement)
        copies = list_backups(self.profile.inventory_cache)
        self.assertEqual(len(copies), 1)
        self.assertTrue(copies[0].path.is_relative_to(self.profile.root))
        bundle.inventory.restoreBackup(copies[0].id)
        self.idle(bundle.inventory)
        self.assertEqual(read_snapshot(self.profile.inventory_cache), original)
        self.assertEqual(bundle.inventory._data, original)
        self.assertEqual(len(list_backups(self.profile.inventory_cache)), 2)
        self.assertEqual(fingerprints(self.production), self.before)

    def test_no_settings_keeps_development_imports_in_memory_without_cache_or_backups(self):
        bundle = self.bundle(settings=False)
        source = self.directory / "synthetic-source.liarte"
        write_snapshot(sample(), source)
        bundle.inventory.openFile(QUrl.fromLocalFile(str(source)))
        self.idle(bundle.inventory)
        self.assertEqual(bundle.inventory._data, sample())
        self.assertIsNone(bundle.inventory._cache)
        self.assertFalse(self.profile.inventory_cache.exists())
        self.assertEqual(list_backups(self.profile.inventory_cache), ())
        self.assertFalse(self.profile.settings_file.exists())
        self.assertEqual(fingerprints(self.production), self.before)

    def test_reports_and_diagnostics_use_the_active_development_profile(self):
        bundle = self.bundle()
        reports = Path(QUrl(bundle.controller.reportsFolder).toLocalFile())
        self.assertEqual(reports, self.profile.reports_dir)
        with patch("liarte_desktop.controller.QDesktopServices.openUrl", return_value=True) as opened:
            bundle.controller.openDiagnostics()
        self.assertEqual(Path(opened.call_args.args[0].toLocalFile()), self.profile.log_dir)
        self.assertEqual(fingerprints(self.production), self.before)

    def test_normal_profile_still_loads_existing_stock_with_unchanged_window_title(self):
        profile = runtime.RuntimeProfile(self.production)
        bundle = self.bundle(profile=profile)
        bundle.inventory.ensureLoaded()
        self.idle(bundle.inventory)
        self.assertEqual(bundle.inventory._data, sample())
        self.assertEqual(bundle.engine.rootObjects()[0].title(), "Liarte")
        self.assertNotIn("Desenvolvimento", bundle.platform.windowTitle)


    def test_opening_central_propagates_development_profile_without_changing_default_launch(self):
        normal = runtime.RuntimeProfile(self.directory / "normal-profile")
        for profile in (self.profile, normal):
            bundle = self.bundle(profile=profile)
            with self.subTest(development=profile.development), patch(
                "liarte_desktop.comex_connection.QProcess.startDetached", return_value=(True, 123)
            ) as launch:
                bundle.services.comex_access.openCentral()
            launch.assert_called_once()
            arguments = launch.call_args.args[1]
            self.assertIn("--central-comex", arguments)
            if profile.development:
                self.assertIn("--profile-dir", arguments)
                index = arguments.index("--profile-dir")
                self.assertEqual(Path(arguments[index + 1]), profile.root)
                self.assertTrue(Path(arguments[index + 1]).is_absolute())
            else:
                self.assertNotIn("--profile-dir", arguments)
        self.assertEqual(fingerprints(self.production), self.before)

    def test_central_main_keeps_its_directory_logs_identity_and_cache_in_development_profile(self):
        script = r'''
import json
import os
from pathlib import Path
import sys
from unittest.mock import Mock, patch
from PySide6.QtCore import QCoreApplication, Qt
from liarte_desktop import comex_central_ui as central
from liarte_desktop import installation_guard, windows_identity, runtime_profile
from liarte_desktop.identity import APP_USER_MODEL_ID

profile, production = map(Path, sys.argv[1:3])
window = Mock()
window.windowTitle.return_value = "Central de Consultas"
with (
    patch.object(runtime_profile.QStandardPaths, "writableLocation", return_value=str(production)),
    patch.object(central, "CentralWindow", return_value=window) as window_type,
    patch.object(central.QApplication, "exec", return_value=0),
    patch.object(installation_guard, "hold_installation_mutex", side_effect=AssertionError("Installed mutex")),
    patch.object(windows_identity, "set_process_identity") as identity,
):
    code = central.main(["--central-comex", "--profile-dir", str(profile)])
    assert code == 0, code
    call = identity.call_args
    app_id = call.args[0] if call.args else call.kwargs.get("app_id")
    assert app_id and app_id != APP_USER_MODEL_ID, call
    result = {
        "directory": str(window_type.call_args.args[0]),
        "title": window.setWindowTitle.call_args.args[0],
        "shown": window.show.called,
        "qml_cache": os.environ.get("QML_DISK_CACHE_PATH"),
        "shader_cache_disabled": QCoreApplication.testAttribute(Qt.ApplicationAttribute.AA_DisableShaderDiskCache),
    }
print(json.dumps(result))
'''
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(ROOT / "src")
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["QT_QPA_PLATFORM"] = "offscreen"
        environment["QT_QUICK_BACKEND"] = "software"
        result = subprocess.run(
            [sys.executable, "-c", script, str(self.profile.root), str(self.production)],
            cwd=ROOT, env=environment, capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        observed = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(Path(observed["directory"]), self.profile.central_dir)
        self.assertIn("Desenvolvimento", observed["title"])
        self.assertTrue(observed["shown"])
        self.assertTrue(Path(observed["qml_cache"]).is_relative_to(self.profile.root))
        self.assertTrue(observed["shader_cache_disabled"])
        self.assertTrue((self.profile.central_dir / "central.log").exists())
        self.assertEqual(fingerprints(self.production), self.before)
