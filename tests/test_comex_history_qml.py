"""Real Qt presentation of a synthetic local-history update state."""

from __future__ import annotations

import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QPointF, Property, QUrl, Qt, Signal, Slot
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtTest import QTest

from liarte_desktop.app import PACKAGE, _finish_inventory_shutdown, create_bundle
from tests.test_qt import APP, click, pump, settled
from tests.test_comex_history_ui import SyntheticHistoricalProvider


def drain_deferred_deletes():
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    APP.processEvents()


class SyntheticHistoryOwner(QObject):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.calls = []
        self.values = {
            "enabled": True,
            "busy": False,
            "progress": 0,
            "message": "Base sintética disponível para consulta.",
            "error": "",
            "coverageStart": "2023-01",
            "coverageEnd": "2025-09",
            "completeMonths": 33,
            "complete": True,
            "checkedAt": "2025-10-04T14:35:00+00:00",
            "baseUpdatedAt": "2025-10-03T12:00:00+00:00",
            "pauseSeconds": 0,
            "stopped": False,
        }

    @Property("QVariantMap", notify=changed)
    def state(self):
        return dict(self.values)

    def update(self, **values):
        self.values.update(values)
        self.changed.emit()

    @Slot()
    def check(self):
        self.calls.append("check")

    @Slot()
    def cancel(self):
        self.calls.append("cancel")


class ComexHistoryQmlTests(unittest.TestCase):
    def setUp(self):
        self._disposed = False
        self.owner = SyntheticHistoryOwner()
        self.engine = QQmlEngine()
        self.messages = []
        self.engine.warnings.connect(lambda warnings: self.messages.extend(str(w) for w in warnings))
        self.engine.rootContext().setContextProperty("syntheticHistory", self.owner)
        self.component = QQmlComponent(self.engine)
        self.component.setData('''
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components" as Ui
ApplicationWindow {
    id: host
    width: 900
    height: 600
    visible: true
    function reveal(item) {}
    ColumnLayout {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 12
        Ui.ComexHistoryStatus {
            owner: syntheticHistory
            workspace: host
        }
        Ui.ActionButton {
            objectName: "nextSyntheticControl"
            text: "Outra ação sintética"
        }
    }
}
'''.encode("utf-8"), QUrl.fromLocalFile(str(PACKAGE / "qml/HistoryStatusSynthetic.qml")))
        self.window = self.component.create()
        self.assertIsNotNone(self.window, [e.toString() for e in self.component.errors()])
        APP.processEvents()

    def tearDown(self):
        if self._disposed:
            return
        self._disposed = True
        # Keep the component, engine and context owner alive until the window
        # has actually been destroyed; processEvents alone does not guarantee
        # delivery of DeferredDelete events in a manually driven test loop.
        self.window.close()
        self.window.deleteLater()
        drain_deferred_deletes()
        self.component.deleteLater()
        drain_deferred_deletes()
        self.engine.deleteLater()
        drain_deferred_deletes()
        self.owner.deleteLater()
        drain_deferred_deletes()

    def item(self, name):
        found = self.window.findChild(QObject, name)
        self.assertIsNotNone(found, name)
        return found

    def test_accepted_base_shows_coverage_and_acquisition_reference_without_network_claim(self):
        self.assertEqual(self.item("comexHistoryCoverage").property("text"), "Base local · 01/2023 a 09/2025")
        self.assertIn("Carga completa", self.item("comexHistoryReference").property("text"))
        self.assertIn("última carga:", self.item("comexHistoryReference").property("text"))
        self.assertEqual(self.messages, [])

    def test_partial_coverage_stays_explicit_when_a_received_timestamp_exists(self):
        self.owner.update(complete=False, coverageEnd="2023-12")
        APP.processEvents()
        self.assertIn("Cobertura parcial", self.item("comexHistoryReference").property("text"))
        self.assertIn("última carga:", self.item("comexHistoryReference").property("text"))
        self.assertIn("12/2023", self.item("comexHistoryCoverage").property("text"))

    def test_pause_only_disables_update_and_limits_availability_to_loaded_periods(self):
        self.owner.update(pauseSeconds=129)
        APP.processEvents()
        message = self.item("comexHistoryMessage").property("text")
        self.assertIn("2:09", message)
        self.assertIn("períodos já carregados", message)
        self.assertFalse(self.item("comexHistoryAction").property("enabled"))
        self.assertEqual(self.owner.calls, [])

    def test_empty_first_load_does_not_claim_that_local_consultations_are_available(self):
        self.owner.update(coverageStart="", coverageEnd="", complete=False, baseUpdatedAt="", pauseSeconds=60)
        APP.processEvents()
        self.assertIn("primeira carga pendente", self.item("comexHistoryCoverage").property("text"))
        self.assertIn("primeira carga ainda não foi concluída", self.item("comexHistoryMessage").property("text"))
        self.assertNotIn("continuam disponíveis", self.item("comexHistoryMessage").property("text"))

    def test_action_dispatches_check_and_allows_cancelling_a_waiting_update(self):
        action = self.item("comexHistoryAction")
        click(self.window, action)
        self.assertEqual(self.owner.calls, ["check"])
        self.owner.update(busy=True, pauseSeconds=90, progress=38)
        APP.processEvents()
        self.assertEqual(action.property("text"), "Cancelar atualização")
        self.assertTrue(action.property("enabled"))
        self.assertTrue(self.item("comexHistoryProgress").property("visible"))
        click(self.window, action)
        self.assertEqual(self.owner.calls, ["check", "cancel"])

    def test_compact_layout_wraps_a_long_failure_and_preserves_keyboard_action(self):
        self.window.setWidth(390)
        self.owner.update(error="Fonte sintética indisponível. A versão local aceita foi preservada para os períodos já carregados.")
        self.assertTrue(pump(lambda: self.item("comexHistoryStatus").width() < 400))
        panel = self.item("comexHistoryStatus")
        action = self.item("comexHistoryAction")
        message = self.item("comexHistoryMessage")
        self.assertLessEqual(action.width(), panel.width())
        self.assertGreaterEqual(action.width(), action.property("naturalWidth"))
        self.assertGreater(message.height(), 12)
        self.assertLessEqual(message.y() + message.height(), panel.height())
        action.forceActiveFocus(Qt.FocusReason.TabFocusReason)
        QTest.keyClick(self.window, Qt.Key.Key_Space)
        self.assertEqual(self.owner.calls, ["check"])
        QTest.keyClick(self.window, Qt.Key.Key_Tab)
        self.assertTrue(self.item("nextSyntheticControl").hasActiveFocus())
        QTest.keyClick(self.window, Qt.Key.Key_Tab, Qt.KeyboardModifier.ShiftModifier)
        self.assertTrue(action.hasActiveFocus())
        self.assertEqual(self.messages, [])

    def test_disabled_history_is_hidden_for_direct_or_demonstration_providers(self):
        self.owner.update(enabled=False)
        APP.processEvents()
        self.assertFalse(self.item("comexHistoryStatus").property("visible"))
        self.assertEqual(self.messages, [])

    def test_repeated_teardown_destroys_qml_objects_before_their_context_owner(self):
        for iteration in range(3):
            if iteration:
                self.setUp()
            destroyed = []
            self.window.destroyed.connect(lambda *_: destroyed.append("window"))
            self.component.destroyed.connect(lambda *_: destroyed.append("component"))
            self.engine.destroyed.connect(lambda *_: destroyed.append("engine"))
            self.owner.destroyed.connect(lambda *_: destroyed.append("owner"))
            self.assertEqual(self.messages, [])
            self.tearDown()
            self.assertEqual(destroyed, ["window", "component", "engine", "owner"])


class ComexHistoryWorkspaceQmlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.provider = SyntheticHistoricalProvider(Path(self.temp.name))
        self.provider.pause = 180
        self.bundle = create_bundle(provider=self.provider, initial_module="imports")
        self.controller = self.bundle.controller
        self.window = self.bundle.engine.rootObjects()[0]
        self.controller.setDraftPeriod("start", "2026-09")
        self.controller.setDraftPeriod("end", "2026-09")
        self.controller._sync_access_status()
        APP.processEvents()

    def tearDown(self):
        self.provider.sync_release.set()
        self.bundle.services.comex_access.shutdown()
        self.controller.shutdown()
        _finish_inventory_shutdown(self.bundle.inventory)
        self.window.close()
        self.window.deleteLater()
        drain_deferred_deletes()
        self.bundle.engine.deleteLater()
        drain_deferred_deletes()
        self.bundle.services.deleteLater()
        drain_deferred_deletes()
        self.provider.close()
        self.temp.cleanup()

    def item(self, name):
        found = self.window.findChild(QObject, name)
        self.assertIsNotNone(found, name)
        return found

    def load(self):
        click(self.window, self.item("queryButton"))
        settled(self.controller)
        self.assertTrue(self.controller.state["loaded"], self.controller.state["error"])

    def open_updates(self):
        click(self.window, self.item("settingsButton"))
        self.assertTrue(pump(lambda: self.item("settingsDialog").property("opened")))
        opening_action = self.item("openImportUpdates")
        opening_action.forceActiveFocus(Qt.FocusReason.TabFocusReason)
        APP.processEvents()
        QTest.keyClick(self.window, Qt.Key.Key_Space)
        self.assertTrue(pump(lambda: self.item("importUpdatesDialog").property("opened")))

    def test_manual_update_and_technical_context_are_separate_from_the_dashboard(self):
        self.assertFalse(self.item("comexHistoryStatus").property("visible"))
        self.assertFalse(self.item("comexHistoryAction").property("visible"))
        self.open_updates()
        self.assertTrue(self.item("comexHistoryStatus").property("visible"))
        self.assertTrue(self.item("comexHistoryAction").property("visible"))
        self.assertEqual(self.item("comexHistoryAction").property("text"), "Verificar atualizações")
        self.assertTrue(self.window.property("globalModalOpen"))
        before = self.provider.query_count
        QTest.keyClick(self.window, Qt.Key.Key_F5)
        QTest.keyClick(self.window, Qt.Key.Key_1, Qt.KeyboardModifier.ControlModifier)
        APP.processEvents()
        self.assertEqual(self.provider.query_count, before)
        self.assertEqual(self.bundle.platform.activeModule, "imports")
        QTest.keyClick(self.window, Qt.Key.Key_Escape)
        self.assertTrue(pump(lambda: not self.item("importUpdatesDialog").property("visible")))
        self.assertFalse(self.window.property("globalModalOpen"))
        self.assertEqual(self.bundle.messages, [])

    def test_real_query_button_and_f5_read_locally_while_api_update_is_paused(self):
        self.assertTrue(self.item("queryButton").property("enabled"))
        self.assertFalse(self.item("comexHistoryAction").property("enabled"))
        self.load()
        before = self.provider.query_count
        self.provider.publish()
        self.window.requestActivate()
        QTest.keyClick(self.window, Qt.Key.Key_F5)
        self.assertTrue(pump(lambda: self.provider.query_count > before))
        settled(self.controller)
        self.assertEqual(self.provider.snapshot.local_revision, self.provider.period_revision)
        self.assertEqual(self.provider.pause, 180)
        self.assertEqual(self.provider.sync_count, 0)
        self.assertFalse(self.controller.state["error"])
        self.assertEqual(self.bundle.messages, [])

    def test_running_update_keeps_the_real_local_query_action_available(self):
        self.provider.pause = 0
        self.provider.sync_release.clear()
        self.controller.history.check()
        self.assertTrue(pump(self.provider.sync_started.is_set))
        self.assertTrue(self.item("queryButton").property("enabled"))
        self.assertEqual(self.item("comexHistoryAction").property("text"), "Cancelar atualização")
        self.load()
        self.assertTrue(self.controller.history.running)
        self.assertEqual(self.provider.sync_count, 1)
        self.assertFalse(self.controller.state["error"])
        self.assertEqual(self.bundle.messages, [])

    def test_an_api_pause_does_not_mask_the_unloaded_period_error(self):
        self.provider.available = False
        self.controller.history.refresh()
        click(self.window, self.item("queryButton"))
        settled(self.controller)
        self.assertFalse(self.controller.state["loaded"])
        self.assertTrue(self.item("queryError").property("visible"))
        self.assertIn("não cobre", self.item("queryError").property("text"))
        self.assertIn("primeira carga ainda não foi concluída", self.item("comexHistoryMessage").property("text"))
        self.assertEqual(self.item("importEmptyTitle").property("text"), "Importações indisponíveis")
        self.assertEqual(self.bundle.messages, [])

    def test_a_manual_draft_outside_the_accepted_publication_remains_visible_in_the_combo(self):
        self.controller.setDraftPeriod("start", "2026-08")
        original_status = self.provider.history_status

        def reduced_publication():
            result = original_status()
            result["publication"] = {"latest": "2026-08", "municipal_latest": "2026-08", "updated": "2026-09-07"}
            return result

        with patch.object(self.provider, "history_status", side_effect=reduced_publication):
            self.controller._sync_history_limits()
        APP.processEvents()
        combo = self.item("endPeriod")
        self.assertGreaterEqual(combo.property("currentIndex"), 0)
        self.assertEqual(combo.property("currentValue"), "2026-09")
        self.assertIn("fora da base local", combo.property("currentText"))
        before = self.provider.query_count
        click(self.window, self.item("queryButton"))
        APP.processEvents()
        self.assertEqual(self.provider.query_count, before)
        self.assertIn("intervalo disponível", self.item("queryError").property("text"))
        self.assertEqual(combo.property("currentValue"), "2026-09")
        self.assertEqual(self.bundle.messages, [])

    def test_compact_history_action_is_reached_by_keyboard_and_cancels_only_the_update(self):
        self.load()
        original = self.provider.snapshot
        self.window.setWidth(500)
        self.window.setHeight(400)
        self.provider.pause = 0
        self.provider.sync_release.clear()
        self.controller.history.refresh()
        self.window.requestActivate()
        self.item("settingsButton").forceActiveFocus(Qt.FocusReason.TabFocusReason)
        QTest.keyClick(self.window, Qt.Key.Key_Space)
        self.assertTrue(pump(lambda: self.item("settingsDialog").property("opened")))
        opening_action = self.item("openImportUpdates")
        for _ in range(80):
            if opening_action.hasActiveFocus():
                break
            QTest.keyClick(self.window, Qt.Key.Key_Tab)
            APP.processEvents()
        self.assertTrue(opening_action.hasActiveFocus())
        QTest.keyClick(self.window, Qt.Key.Key_Space)
        dialog = self.item("importUpdatesDialog")
        self.assertTrue(pump(lambda: dialog.property("opened")))
        action = self.item("comexHistoryAction")
        for _ in range(80):
            if action.hasActiveFocus():
                break
            QTest.keyClick(self.window, Qt.Key.Key_Tab)
            APP.processEvents()
        self.assertTrue(action.hasActiveFocus())
        self.assertLessEqual(action.width(), self.item("comexHistoryStatus").width())
        viewport = dialog.property("bodyViewport")
        self.assertTrue(pump(lambda: action.mapToItem(viewport, QPointF(0, 0)).y() >= 0
                             and action.mapToItem(viewport, QPointF(0, action.height())).y() <= viewport.height()))
        QTest.keyClick(self.window, Qt.Key.Key_Space)
        self.assertTrue(pump(self.provider.sync_started.is_set))
        self.assertEqual(action.property("text"), "Cancelar atualização")
        QTest.keyClick(self.window, Qt.Key.Key_Space)
        self.assertTrue(pump(lambda: not self.controller.history.running))
        self.assertIs(self.provider.snapshot, original)
        self.assertTrue(self.controller.state["loaded"])
        self.assertTrue(self.controller.history.state["stopped"])
        self.assertEqual(self.bundle.messages, [])
