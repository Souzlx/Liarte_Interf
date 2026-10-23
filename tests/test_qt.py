from __future__ import annotations

import tempfile
import time
from threading import Event
from pathlib import Path
import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QPoint, QPointF, QSettings, QTimer, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QAbstractItemModelTester, QTest

from liarte_core.demo import Cancelled, DemoProvider
from liarte_core.domain import Period, Selection
from liarte_desktop.app import PACKAGE, create_bundle
from liarte_desktop.branding import BrandProvider
from liarte_desktop.controller import DesktopController, QueryWorker
from liarte_desktop.table_model import ImportTableModel
from tests.test_core import record

QQuickStyle.setStyle("Basic")
APP = QGuiApplication.instance() or QGuiApplication([])
APP.setQuitOnLastWindowClosed(False)


def pump(predicate=lambda: False, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        APP.processEvents()
        # Match exec()'s deferred cleanup while tests manually drive Qt. Without
        # this, old TableView delegates can remain painted after a model reset.
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        if predicate():
            return True
        time.sleep(0.005)
    return False


def settled(controller, timeout=10):
    if not pump(
        lambda: not controller.state["busy"] and not controller._debounce.isActive(), timeout
    ):
        raise AssertionError("A tarefa Qt excedeu o prazo do teste.")
    APP.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def click(window, item):
    position = item.mapToScene(QPointF(item.width() / 2, item.height() / 2))
    QTest.mouseClick(
        window,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        QPoint(round(position.x()), round(position.y())),
    )
    APP.processEvents()


class QtTests(unittest.TestCase):
    def setUp(self):
        self.bundle = create_bundle(initial_module="imports", size=2000)
        self.controller = self.bundle.controller
        self.window = self.bundle.engine.rootObjects()[0]
        APP.processEvents()

    def tearDown(self):
        self.controller.shutdown()
        self.window.close()
        APP.processEvents()
        self.bundle.engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        APP.processEvents()

    def item(self, name):
        value = self.window.findChild(QObject, name)
        self.assertIsNotNone(value, name)
        return value

    def load(self):
        self.controller.queryPeriod("2026-04", "2026-09")
        settled(self.controller)
        self.assertTrue(self.controller.state["loaded"])

    def test_qml_loads_without_warnings_and_without_query(self):
        self.assertEqual(self.bundle.messages, [])
        self.assertFalse(self.controller.state["loaded"])
        self.assertFalse(self.controller.state["busy"])
        self.assertEqual(self.controller.table.rowCount(), 0)

    def test_query_button_runs_native_worker(self):
        click(self.window, self.item("queryButton"))
        settled(self.controller)
        self.assertTrue(self.controller.state["loaded"])
        self.assertEqual(self.controller.table.rowCount(), 50)
        self.assertEqual(self.bundle.messages, [])

    def test_invalid_period_preserves_previous_results(self):
        self.load()
        before = self.controller.table.rows
        self.controller.queryPeriod("2026-09", "2026-01")
        self.assertTrue(self.controller.state["error"])
        self.assertEqual(before, self.controller.table.rows)

    def test_latest_filter_wins_after_rapid_changes(self):
        self.load()
        self.controller.setFilter("country", "China")
        self.controller.setFilter("country", "Holanda")
        settled(self.controller)
        self.assertTrue(all(v.country == "Holanda" for v in self.controller.table.rows))

    def test_page_and_sort_and_size(self):
        self.load()
        self.controller.sortByColumn(6)
        settled(self.controller)
        rows = self.controller.table.rows
        self.assertEqual(
            [r.fob_cents for r in rows], sorted((r.fob_cents for r in rows), reverse=True)
        )
        self.controller.setPage(2)
        settled(self.controller)
        self.assertEqual(self.controller.state["page"], 2)
        self.assertNotEqual(rows, self.controller.table.rows)
        self.controller.setPageSize(25)
        settled(self.controller)
        self.assertEqual(self.controller.table.rowCount(), 25)
        self.assertEqual(self.controller.state["page"], 1)

    def test_search_changes_only_table(self):
        self.load()
        metrics = self.controller.state["metrics"]
        self.controller.setFilter("search", "impossível inexistente")
        settled(self.controller)
        self.assertEqual(self.controller.state["metrics"], metrics)
        self.assertEqual(self.controller.table.rowCount(), 0)
        self.assertEqual(self.bundle.messages, [])

    def test_country_share_rounds_decimal_half_up(self):
        provider = DemoProvider(2)
        provider._rows = (
            record(0, fob_cents=1235, freight_cents=0, insurance_cents=0),
            record(1, country="Holanda", fob_cents=8765, freight_cents=0, insurance_cents=0),
        )
        self.controller._provider = provider
        self.load()
        shares = {v["label"]: v["share"] for v in self.controller.state["countries"]}
        self.assertEqual(shares["China"], "12,4%")

    def test_selection_details_and_clipboard(self):
        self.load()
        self.controller.selectRow(0)
        self.controller.copySelected()
        self.assertIn("CIF (US$)", self.controller.state["selectedText"])
        self.assertIn("DADOS DEMONSTRATIVOS", QGuiApplication.clipboard().text())
        self.assertIn(self.controller.table.rows[0].ncm, QGuiApplication.clipboard().text())

    def test_table_model_contract(self):
        model = ImportTableModel()
        tester = QAbstractItemModelTester(
            model, QAbstractItemModelTester.FailureReportingMode.Warning
        )
        model.replace((record(),))
        self.assertEqual(model.rowCount(), 1)
        self.assertEqual(model.columnCount(), 12)
        self.assertEqual(model.data(model.index(0, 2)), "29161220")
        self.assertIsNone(model.data(model.index(3, 2)))
        self.assertIsNotNone(tester)

    def test_theme_button_and_native_brand(self):
        click(self.window, self.item("themeButton"))
        self.assertTrue(self.controller.state["dark"])
        APP.processEvents()
        self.assertEqual(self.bundle.messages, [])
        brand = BrandProvider(PACKAGE / "assets/liarte-logo-transparente.png")
        x = int(brand.original.width() * 0.33)
        y = int(brand.original.height() * 0.3)
        self.assertTrue(
            all(
                abs(a - b) <= 1
                for a, b in zip(
                    brand.original.pixelColor(x, y).getRgb(), brand.dark.pixelColor(x, y).getRgb()
                )
            )
        )
        x = int(brand.original.width() * 0.04)
        self.assertGreater(brand.dark.pixelColor(x, y).red(), 240)

    def test_native_popups_open_and_restore(self):
        for name, dialog in [("settingsButton", "settingsDialog"), ("projectNav", "projectDialog")]:
            click(self.window, self.item(name))
            self.assertTrue(pump(lambda: self.item(dialog).property("opened")))
            QTest.keyClick(self.window, Qt.Key.Key_Escape)
            self.assertTrue(pump(lambda: not self.item(dialog).property("visible")))
        self.assertEqual(self.bundle.messages, [])

    def test_portuguese_month_dropdown(self):
        item = self.item("startPeriod")
        self.assertEqual(item.property("displayText"), "Abril de 2026")
        click(self.window, item)
        APP.processEvents()
        self.assertEqual(self.bundle.messages, [])
        QTest.keyClick(self.window, Qt.Key.Key_Home)
        QTest.keyClick(self.window, Qt.Key.Key_Return)
        APP.processEvents()
        self.assertEqual(item.property("displayText"), "Janeiro de 2025")

    def test_responsive_window_and_dialogs(self):
        for width, height in [(1380, 900), (1100, 800), (900, 700), (760, 580), (620, 480)]:
            self.window.resize(width, height)
            APP.processEvents()
            for name in ("startPeriod", "endPeriod", "queryButton", "settingsButton"):
                item = self.item(name)
                p = item.mapToScene(QPointF(0, 0))
                self.assertGreaterEqual(p.x(), -1, name)
                self.assertLessEqual(p.x() + item.width(), width + 1, name)
                self.assertGreater(item.width(), 30, name)
        self.assertEqual(self.bundle.messages, [])

    def test_settings_are_separate_and_survive_new_controller(self):
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / "desktop-f1.ini")
            settings = QSettings(path, QSettings.Format.IniFormat)
            a = DesktopController(DemoProvider(5), settings)
            a.setPreference("dark", True)
            a.setPreference("compact", True)
            settings.sync()
            b = DesktopController(DemoProvider(5), QSettings(path, QSettings.Format.IniFormat))
            self.assertTrue(b.state["dark"])
            self.assertTrue(b.state["compact"])

    def test_clear_filters_resets_search_and_scope(self):
        self.load()
        before = self.controller.state["scopeCount"]
        self.controller.setFilter("country", "China")
        self.controller.setFilter("search", "abc")
        settled(self.controller)
        self.controller.clearFilters()
        settled(self.controller)
        self.assertEqual(self.controller.state["scopeCount"], before)
        self.assertEqual(self.controller.state["search"], "")

    def test_keyboard_selects_row_and_opens_details(self):
        self.load()
        scroll = self.item("contentScroll")
        scroll.setProperty("contentY", scroll.property("contentHeight") - scroll.property("height"))
        table = self.item("recordsTable")
        table.forceActiveFocus()
        QTest.keyClick(self.window, Qt.Key.Key_Down)
        APP.processEvents()
        self.assertEqual(self.controller.state["selection"], 0)
        QTest.keyClick(self.window, Qt.Key.Key_Return)
        self.assertTrue(pump(lambda: self.item("detailDialog").property("opened")))
        self.assertEqual(self.bundle.messages, [])

    def test_close_while_busy_requires_confirmation(self):
        class Blocking:
            def query(self, selection, cancel, progress):
                while not cancel.wait(0.01):
                    pass
                raise Cancelled()

        self.controller._provider = Blocking()
        self.controller.queryPeriod("2026-04", "2026-09")
        self.window.close()
        APP.processEvents()
        self.assertTrue(self.window.isVisible())
        self.assertTrue(pump(lambda: self.item("closeDialog").property("opened")))
        click(self.window, self.item("confirmClose"))
        settled(self.controller)
        self.assertFalse(self.window.isVisible())

    def test_worker_error_is_visible_and_previous_results_stay(self):
        self.load()
        before = self.controller.table.rows

        class Broken:
            def query(self, *args):
                raise OSError("Falha controlada")

        self.controller._provider = Broken()
        with self.assertLogs("liarte.desktop", level="ERROR"):
            self.controller.queryPeriod("2026-04", "2026-09")
            settled(self.controller)
        self.assertTrue(self.controller.state["error"])
        self.assertEqual(before, self.controller.table.rows)

    def test_cancellation_has_no_partial_result(self):
        self.controller._provider = DemoProvider(100_000)
        self.controller.queryPeriod("2025-01", "2026-09")
        self.controller.cancel()
        settled(self.controller)
        self.assertFalse(self.controller.state["loaded"])
        self.assertEqual(self.controller.table.rowCount(), 0)

    def test_control_f_reveals_search_below_fold(self):
        self.load()
        QTest.keyClick(self.window, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
        APP.processEvents()
        self.assertTrue(self.item("searchBox").hasActiveFocus())
        self.assertGreater(self.item("contentScroll").property("contentY"), 0)
        self.assertEqual(self.bundle.messages, [])

    def test_keyboard_keeps_selected_row_visible(self):
        self.load()
        scroll = self.item("contentScroll")
        scroll.setProperty("contentY", scroll.property("contentHeight") - scroll.height())
        table = self.item("recordsTable")
        self.assertTrue(pump(lambda: table.property("contentHeight") > table.height()))
        table.forceActiveFocus()
        for _ in range(20):
            QTest.keyClick(self.window, Qt.Key.Key_Down)
        self.assertEqual(self.controller.state["selection"], 19)
        self.assertTrue(pump(lambda: table.property("contentY") > 0))
        self.assertLessEqual(table.property("topRow"), 19)
        self.assertGreaterEqual(table.property("bottomRow"), 19)
        self.assertEqual(self.bundle.messages, [])

    def test_compact_mode_relayouts_without_qml_warnings(self):
        self.load()
        self.controller.setPreference("compact", True)
        APP.processEvents()
        self.assertTrue(self.item("recordsTable").property("compactMode"))
        self.assertEqual(self.bundle.messages, [])

    def test_new_request_replaces_running_request(self):
        self.controller._provider = DemoProvider(20_000)
        self.controller.queryPeriod("2025-01", "2026-09")
        self.controller.queryPeriod("2026-09", "2026-09")
        settled(self.controller, 15)
        self.assertTrue(self.controller.state["loaded"])
        self.assertTrue(all(r.period == "2026-09" for r in self.controller.table.rows))

    def test_model_rejects_update_from_background_thread(self):
        import threading

        failures = []

        def invalid_update():
            try:
                self.controller.table.replace((record(),))
            except RuntimeError as exc:
                failures.append(str(exc))

        thread = threading.Thread(target=invalid_update)
        thread.start()
        thread.join()
        self.assertEqual(len(failures), 1)
        self.assertEqual(self.controller.table.rowCount(), 0)

    def test_month_ticks_align_with_actual_first_and_last_points(self):
        self.controller.queryPeriod("2025-01", "2026-09")
        settled(self.controller)
        chart = self.item("monthlyChart")
        ticks = {item.objectName(): item for item in chart.childItems()}
        first, last = ticks["monthTick0"], ticks["monthTick20"]
        left = chart.property("plotLeft")
        self.assertAlmostEqual(first.x() + first.width() / 2, left, delta=0.1)
        self.assertAlmostEqual(last.x() + last.width() / 2, left + chart.property("plotWidth"), delta=0.1)
        self.assertEqual(self.bundle.messages, [])

    def test_burst_progress_is_coalesced_without_losing_completion(self):
        class BurstyProvider:
            def query(self, selection, cancel, progress):
                for i in range(2000):
                    progress(i // 20, "Mesma etapa")
                progress(100, "Mesma etapa")
                return DemoProvider(1).query(selection, cancel, lambda *args: None)

        worker = QueryWorker(BurstyProvider(), Selection(Period("2026-01", "2026-09")), Event())
        progress, results = [], []
        worker.progress.connect(lambda percent, stage: progress.append(percent))
        worker.succeeded.connect(results.append)
        with (
            patch("liarte_desktop.controller.time.monotonic", return_value=123),
            patch.object(worker.cancel, "wait", return_value=False),
        ):
            worker.run()
        self.assertEqual(progress, [0, 100])
        self.assertEqual(len(results), 1)


class VolumeTests(unittest.TestCase):
    def test_100k_records_stay_paginated_and_ui_keeps_processing(self):
        bundle = create_bundle(initial_module="imports", size=100_000)
        controller = bundle.controller
        window = bundle.engine.rootObjects()[0]
        APP.processEvents()
        ticks = []
        timer = QTimer()
        timer.setInterval(20)
        timer.timeout.connect(lambda: ticks.append(time.perf_counter()))
        timer.start()
        start = time.perf_counter()
        try:
            controller.queryPeriod("2025-01", "2026-09")
            settled(controller, 30)
            elapsed = time.perf_counter() - start
            self.assertEqual(controller.state["scopeCount"], "100.000")
            self.assertEqual(controller.table.rowCount(), 50)
            self.assertEqual(controller.state["tableCount"], "100.000")
            self.assertEqual(bundle.messages, [])
            self.assertGreater(len(ticks), 2)
            self.assertLess(elapsed, 30)
            controller.setFilter("country", "China")
            settled(controller, 15)
            self.assertTrue(all(r.country == "China" for r in controller.table.rows))
            print(
                f"VOLUME: 100000 registros, primeira consulta {elapsed:.3f}s, {len(ticks)} eventos Qt."
            )
        finally:
            timer.stop()
            controller.shutdown()
            window.close()
            bundle.engine.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
