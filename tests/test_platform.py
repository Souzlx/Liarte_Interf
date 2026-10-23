"""Regressões do núcleo central e da sessão mantida entre os módulos."""

from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import tempfile
from threading import Event
import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import QCoreApplication, QEvent, QMetaObject, QObject, QSettings, Qt
from PySide6.QtTest import QSignalSpy, QTest

from liarte_core.comex import ComexProvider
from liarte_core.demo import DemoProvider
from liarte_core.modules import Module, ModuleRegistry, default_registry
from liarte_desktop.app import create_bundle
from liarte_desktop.controller import DesktopController
from liarte_desktop.platform import PlatformController
from liarte_desktop.preferences import ApplicationPreferences
from tests import test_comex
from tests.test_qt import APP, click, pump, settled


class PlatformTests(unittest.TestCase):
    def test_only_available_registered_modules_can_open(self):
        registry = default_registry()
        self.assertTrue(registry.can_open("imports"))
        self.assertTrue(registry.can_open("inventory"))
        for name in ("credit", "unknown", "../imports", ""):
            self.assertFalse(registry.can_open(name))
        self.assertIsNone(registry.get("unknown"))

    def test_registry_rejects_duplicates_reserved_keys_and_incomplete_names(self):
        module = Module("imports", "Importações", "Descrição", "chart", True)
        with self.assertRaises(ValueError):
            ModuleRegistry((module, module))
        for entry in (
            replace(module, key="home"),
            replace(module, key="Imports"),
            replace(module, key="../imports"),
            replace(module, title="  "),
            replace(module, description=""),
            replace(module, available=1),
        ):
            with self.subTest(entry=entry), self.assertRaises(ValueError):
                ModuleRegistry((entry,))

    def test_registry_definition_cannot_be_mutated_by_a_consumer(self):
        module = default_registry().modules[0]
        with self.assertRaises(FrozenInstanceError):
            module.available = False
        platform = PlatformController(default_registry(), ApplicationPreferences())
        exported = platform.modules
        exported[0]["available"] = False
        self.assertTrue(platform.openModule("imports"))

    def test_available_module_without_a_mounted_page_cannot_open_the_wrong_workspace(self):
        registry = ModuleRegistry((Module("other", "Outro", "Outro módulo", "box", True),))
        with self.assertRaises(ValueError):
            PlatformController(registry, ApplicationPreferences())

    def test_existing_preferences_and_unrelated_keys_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = QSettings(str(Path(directory) / "prefs.ini"), QSettings.Format.IniFormat)
            settings.setValue("dark", True)
            settings.setValue("compact", True)
            settings.setValue("monthlySheets", False)
            settings.setValue("reports/path", "relatorios-preservados")
            preferences = ApplicationPreferences(settings)
            self.assertTrue(preferences.value("dark"))
            self.assertTrue(preferences.value("compact"))
            self.assertFalse(preferences.value("monthlySheets"))
            platform = PlatformController(default_registry(), preferences)
            platform.openModule("imports")
            platform.setStartupPage("last")
            self.assertEqual(settings.value("reports/path"), "relatorios-preservados")
            restored = PlatformController(default_registry(), ApplicationPreferences(settings))
            self.assertEqual(restored.activeModule, "imports")
            self.assertEqual(restored.startupPage, "last")

    def test_disabled_or_corrupt_saved_page_falls_back_to_home(self):
        for startup, last in (
            ("credit", "imports"),
            ("last", "credit"),
            ("last", "../other"),
            ("missing", "imports"),
        ):
            with self.subTest(startup=startup, last=last):
                preferences = ApplicationPreferences()
                preferences.remember_page("platform/startupPage", startup)
                preferences.remember_page("platform/lastPage", last)
                platform = PlatformController(default_registry(), preferences)
                self.assertEqual(platform.activeModule, "home")
                self.assertFalse(platform.openModule("credit"))
                self.assertEqual(platform.activeModule, "home")

    def test_opening_current_page_is_idempotent_and_does_not_emit_again(self):
        platform = PlatformController(default_registry(), ApplicationPreferences())
        changed = QSignalSpy(platform.navigationChanged)
        self.assertTrue(platform.openModule("home"))
        self.assertTrue(platform.openModule("imports"))
        self.assertTrue(platform.openModule("imports"))
        self.assertFalse(platform.openModule("credit"))
        self.assertEqual(changed.count(), 1)

    def test_startup_choices_only_include_usable_routes_and_track_current_page(self):
        preferences = ApplicationPreferences()
        platform = PlatformController(default_registry(), preferences, initial_module="imports")
        self.assertEqual(
            {row["value"] for row in platform.startupOptions},
            {"home", "imports", "inventory", "last"},
        )
        platform.setStartupPage("credit")
        self.assertEqual(platform.startupPage, "home")
        platform.setStartupPage("last")
        restored = PlatformController(default_registry(), preferences)
        self.assertEqual(restored.activeModule, "imports")
        restored.openModule("home")
        self.assertEqual(PlatformController(default_registry(), preferences).activeModule, "home")

    def test_preferences_are_shared_without_query_or_analysis_updates(self):
        preferences = ApplicationPreferences()
        controller = DesktopController(DemoProvider(5), preferences=preferences)
        analysis = QSignalSpy(controller.analysisChanged)
        with patch.object(controller._provider, "query") as query:
            preferences.setPreference("dark", True)
            preferences.setPreference("compact", True)
            controller.setPreference("reducedMotion", True)
            controller.setExportOption("monthlySheets", False)
            self.assertTrue(controller.state["dark"])
            self.assertTrue(controller.state["compact"])
            self.assertTrue(preferences.value("reducedMotion"))
            self.assertFalse(preferences.value("monthlySheets"))
            query.assert_not_called()
            self.assertEqual(analysis.count(), 0)
        controller.shutdown()

    def test_failed_preferences_write_keeps_navigation_and_session_operable(self):
        settings = Mock()
        settings.value.side_effect = lambda key, default=None, **kwargs: default
        settings.status.return_value = QSettings.Status.AccessError
        preferences = ApplicationPreferences(settings)
        platform = PlatformController(default_registry(), preferences)
        preferences.setPreference("dark", True)
        self.assertTrue(preferences.value("dark"))
        self.assertTrue(preferences.notice)
        self.assertTrue(platform.openModule("imports"))
        self.assertTrue(platform.openModule("home"))
        settings.status.return_value = QSettings.Status.NoError
        preferences.setPreference("dark", False)
        self.assertFalse(preferences.notice)


class PlatformUiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.transport = test_comex.Transport()
        self.patch = patch(
            "liarte_engine.secure_http.urlopen", side_effect=self.transport
        )
        self.patch.start()
        self.provider = ComexProvider(
            self.directory, client_factory=test_comex.factory, codes=["29161220"]
        )
        self.bundle = create_bundle(provider=self.provider)
        self.controller = self.bundle.controller
        self.platform = self.bundle.platform
        self.window = self.bundle.engine.rootObjects()[0]
        APP.processEvents()

    def tearDown(self):
        self.controller.shutdown()
        self.window.close()
        APP.processEvents()
        self.bundle.engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        APP.processEvents()
        self.patch.stop()
        self.temp.cleanup()

    def item(self, name):
        item = self.window.findChild(QObject, name)
        pending = [self.window.contentItem()]
        while item is None and pending:
            child = pending.pop()
            if child.objectName() == name:
                item = child
                break
            pending.extend(child.childItems())
        self.assertIsNotNone(item, name)
        return item

    def load(self):
        self.platform.openModule("imports")
        self.controller.queryPeriod("2026-09", "2026-09")
        settled(self.controller)
        self.assertTrue(self.controller.state["loaded"], self.controller.state["error"])

    def test_home_opens_without_data_query_and_shows_only_real_module_actions(self):
        self.assertEqual(self.platform.activeModule, "home")
        self.assertEqual(self.window.title(), "Liarte")
        self.assertTrue(self.item("homePage").isVisible())
        self.assertFalse(self.item("importsWorkspace").isVisible())
        self.assertFalse(self.item("quickExportButton").isVisible())
        self.assertFalse(self.controller.state["loaded"])
        self.assertEqual(self.transport.calls, [])
        click(self.window, self.item("plannedModule_credit"))
        self.assertEqual(self.platform.activeModule, "home")
        click(self.window, self.item("moduleCard_imports"))
        self.assertEqual(self.platform.activeModule, "imports")
        self.assertEqual(self.window.title(), "Liarte Importações")
        self.assertEqual(self.transport.calls, [])
        self.assertEqual(self.bundle.messages, [])

    def test_module_roundtrip_preserves_models_totals_filters_and_viewport_for_both_bases(self):
        self.load()
        self.bundle.preferences.setPreference("reducedMotion", True)
        workspace = self.item("importsWorkspace")
        table = self.controller.table
        for kind in ("general", "municipal"):
            self.controller.setDataset(kind)
            settled(self.controller)
            self.controller.setFilters("country", ["China"])
            self.controller.setPageSize(25)
            settled(self.controller)
            self.controller.setPage(min(2, self.controller.state["pages"]))
            settled(self.controller)
            scroll = self.item("contentScroll")
            scroll.setProperty(
                "contentY", min(480, max(0, scroll.property("contentHeight") - scroll.height()))
            )
            APP.processEvents()
            before_y = scroll.property("contentY")
            before = (
                self.controller._result,
                self.controller.state["countryValues"],
                self.controller.state["page"],
                tuple(table.rows),
            )
            calls = list(self.transport.calls)
            resets = QSignalSpy(table.modelReset)
            analysis = QSignalSpy(self.controller.analysisChanged)
            click(self.window, self.item("homeNav"))
            APP.processEvents()
            click(self.window, self.item("importsNav"))
            self.assertTrue(pump(lambda: self.item("importsWorkspace").isVisible()))
            APP.processEvents()
            self.assertIs(self.item("importsWorkspace"), workspace)
            self.assertIs(self.controller.table, table)
            self.assertIs(self.controller._result, before[0])
            self.assertEqual(
                (
                    self.controller.state["countryValues"],
                    self.controller.state["page"],
                    tuple(table.rows),
                ),
                before[1:],
            )
            self.assertAlmostEqual(scroll.property("contentY"), before_y, delta=1)
            self.assertEqual(resets.count(), 0)
            self.assertEqual(analysis.count(), 0)
            self.assertEqual(self.transport.calls, calls)
        self.assertEqual(self.bundle.messages, [])

    def test_query_shortcut_is_inactive_on_home_and_routes_work_from_keyboard(self):
        QTest.keyClick(self.window, Qt.Key.Key_F5)
        APP.processEvents()
        self.assertFalse(self.controller.state["busy"])
        self.assertEqual(self.transport.calls, [])
        QTest.keyClick(self.window, Qt.Key.Key_2, Qt.KeyboardModifier.ControlModifier)
        self.assertTrue(pump(lambda: self.platform.activeModule == "imports"))
        QTest.keyClick(self.window, Qt.Key.Key_1, Qt.KeyboardModifier.ControlModifier)
        self.assertTrue(pump(lambda: self.platform.activeModule == "home"))
        self.assertEqual(self.transport.calls, [])
        self.assertEqual(self.bundle.messages, [])

    def test_short_window_keeps_help_accessible_and_navigation_scrolls_to_keyboard_focus(self):
        self.load()
        self.window.resize(500, 400)
        APP.processEvents()
        help_button = self.item("projectNav")
        from PySide6.QtCore import QPointF

        position = help_button.mapToScene(QPointF())
        self.assertGreaterEqual(position.y(), 0)
        self.assertLessEqual(position.y() + help_button.height(), 401)
        self.assertGreaterEqual(help_button.height(), 36)
        records = self.item("jump_records")
        records.forceActiveFocus()
        viewport = self.item("moduleNavigation")

        def focus_in_viewport():
            point = records.mapToItem(viewport, QPointF())
            return point.y() >= -1 and point.y() + records.height() <= viewport.height() + 1

        self.assertTrue(pump(focus_in_viewport))
        self.assertEqual(self.bundle.messages, [])

    def test_pending_query_completes_while_home_is_visible_without_restart(self):
        entered, release = Event(), Event()
        original = self.provider.query

        def delayed(*args, **kwargs):
            entered.set()
            if not release.wait(4):
                raise RuntimeError("Teste não liberou a consulta")
            return original(*args, **kwargs)

        try:
            with patch.object(self.provider, "query", side_effect=delayed) as query:
                self.platform.openModule("imports")
                self.controller.queryPeriod("2026-09", "2026-09")
                self.assertTrue(pump(entered.is_set))
                thread = self.controller._thread
                self.platform.openModule("home")
                APP.processEvents()
                self.assertTrue(self.controller.state["busy"])
                self.assertIs(self.controller._thread, thread)
                self.assertTrue(self.item("homeImportContext").isVisible())
                release.set()
                settled(self.controller)
                self.assertTrue(self.controller.state["loaded"])
                self.assertEqual(self.platform.activeModule, "home")
                self.platform.openModule("imports")
                self.assertEqual(query.call_count, 1)
        finally:
            release.set()
        self.assertEqual(self.bundle.messages, [])

    def test_shared_preferences_apply_on_home_and_remain_in_imports(self):
        click(self.window, self.item("settingsButton"))
        dialog = self.item("settingsDialog")
        self.assertTrue(pump(lambda: dialog.property("opened")))
        click(self.window, self.item("darkPreference"))
        self.assertTrue(self.bundle.preferences.value("dark"))
        self.assertTrue(self.controller.state["dark"])
        QMetaObject.invokeMethod(dialog, "close")
        self.assertTrue(pump(lambda: not dialog.property("visible")))
        click(self.window, self.item("importsNav"))
        APP.processEvents()
        self.assertTrue(self.controller.state["dark"])
        self.assertEqual(self.transport.calls, [])
        self.assertEqual(self.bundle.messages, [])

    def test_startup_page_can_be_selected_in_the_shared_preferences(self):
        click(self.window, self.item("settingsButton"))
        self.assertTrue(pump(lambda: self.item("settingsDialog").property("opened")))
        combo = self.item("startupPagePreference")
        click(self.window, combo)
        QTest.keyClick(self.window, Qt.Key.Key_Home)
        QTest.keyClick(self.window, Qt.Key.Key_Down)
        QTest.keyClick(self.window, Qt.Key.Key_Return)
        APP.processEvents()
        self.assertEqual(self.platform.startupPage, "imports")
        restored = PlatformController(default_registry(), self.bundle.preferences)
        self.assertEqual(restored.activeModule, "imports")
        self.assertEqual(self.platform.activeModule, "home")
        self.assertEqual(self.transport.calls, [])
        self.assertEqual(self.bundle.messages, [])

    def test_closing_from_home_still_protects_a_running_import_task(self):
        entered, release = Event(), Event()
        original = self.provider.query

        def delayed(*args, **kwargs):
            entered.set()
            if not release.wait(4):
                raise RuntimeError("Teste não liberou a consulta")
            return original(*args, **kwargs)

        try:
            with patch.object(self.provider, "query", side_effect=delayed):
                self.controller.queryPeriod("2026-09", "2026-09")
                self.assertTrue(pump(entered.is_set))
                self.window.close()
                self.assertTrue(self.window.isVisible())
                dialog = self.item("closeDialog")
                self.assertTrue(pump(lambda: dialog.property("opened")))
                QMetaObject.invokeMethod(dialog, "close")
                release.set()
                settled(self.controller)
                self.assertTrue(self.controller.state["loaded"])
                self.assertTrue(self.window.isVisible())
        finally:
            release.set()
        self.assertEqual(self.bundle.messages, [])

    def test_modal_prevents_page_shortcuts_until_closed(self):
        dialog = self.item("settingsDialog")
        QMetaObject.invokeMethod(dialog, "open")
        self.assertTrue(pump(lambda: dialog.property("opened")))
        QTest.keyClick(self.window, Qt.Key.Key_2, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.platform.activeModule, "home")
        QMetaObject.invokeMethod(dialog, "close")
        self.assertTrue(pump(lambda: not dialog.property("visible")))
        QTest.keyClick(self.window, Qt.Key.Key_2, Qt.KeyboardModifier.ControlModifier)
        self.assertTrue(pump(lambda: self.platform.activeModule == "imports"))
        self.assertEqual(self.bundle.messages, [])

    def test_reduced_motion_finishes_page_transition_and_rapid_routes_settle(self):
        for route in ("imports", "home", "imports", "home", "imports"):
            self.platform.openModule(route)
            APP.processEvents()
        self.bundle.preferences.setPreference("reducedMotion", True)
        APP.processEvents()
        self.assertFalse(self.item("moduleTransition").property("running"))
        self.assertEqual(self.item("moduleStack").property("opacity"), 1)
        self.assertEqual(self.platform.activeModule, "imports")
        self.assertTrue(self.item("importsWorkspace").isVisible())
        self.assertFalse(self.item("homePage").isVisible())
        self.assertEqual(self.transport.calls, [])
        self.assertEqual(self.bundle.messages, [])
