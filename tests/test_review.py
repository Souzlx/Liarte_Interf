from __future__ import annotations
from dataclasses import replace
from decimal import Decimal, localcontext
import random
from threading import Event
import unittest
from unittest.mock import Mock
from PySide6.QtCore import QCoreApplication, QEvent, QMetaObject, QSettings, QSize, Qt
from PySide6.QtTest import QSignalSpy, QTest
from liarte_core.demo import Cancelled, DemoProvider, DEMO_PERIOD, PORTS
from liarte_core.domain import Period, Selection, number
from liarte_desktop.branding import BrandProvider
from liarte_desktop.app import PACKAGE
from liarte_desktop.controller import DesktopController
from tests.test_core import record
from tests.test_qt import QtTests, APP, pump, settled


class ReviewCoreTests(unittest.TestCase):
    def setUp(self):
        self.provider = DemoProvider(600)
        self.selection = Selection(DEMO_PERIOD)

    def query(self, **changes):
        return self.provider.query(replace(self.selection, **changes), Event(), lambda *_: None)

    def test_ascii_ncm_dates_and_valid_uf(self):
        for changes in (
            {"ncm": "２９１６１２２０"},
            {"ncm": None},
            {"state": "ZZ"},
            {"state": None},
            {"period": "２０２６-04"},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                record(**changes)

    def test_invalid_filter_types_are_rejected(self):
        for changes in (
            {"period": "2026-01"},
            {"search": None},
            {"country": 4},
            {"port": None},
            {"descending": "yes"},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(self.selection, **changes)

    def test_port_filter_intersects_other_filters(self):
        self.provider._rows = (record(0), record(1, port=PORTS[1]), record(2, country="Holanda"))
        result = self.query(port=PORTS[0], country="China")
        self.assertEqual([r.identifier for r in result.rows], [0])
        self.assertEqual(result.totals.cif_cents, 111000)

    def test_page_and_size_reuse_scope_and_order(self):
        self.query(sort_column=9)
        before = self.provider.cache_info
        self.query(sort_column=9, page=2, page_size=25)
        after = self.provider.cache_info
        self.assertEqual(before["scope_builds"], after["scope_builds"])
        self.assertEqual(before["view_builds"], after["view_builds"])
        self.assertEqual(after["view_hits"], before["view_hits"] + 1)

    def test_search_reuses_index_without_changing_totals(self):
        all_rows = self.query()
        self.query(search="China")
        before = self.provider.cache_info
        result = self.query(search="Santos")
        self.assertEqual(result.totals, all_rows.totals)
        self.assertEqual(self.provider.cache_info["search_builds"], before["search_builds"])

    def test_source_replacement_invalidates_cached_data(self):
        self.query()
        self.provider._rows = (record(91, fob_cents=12345),)
        result = self.query()
        self.assertEqual(result.totals.records, 1)
        self.assertEqual(result.rows[0].identifier, 91)

    def test_memory_caches_are_bounded(self):
        for month in DEMO_PERIOD.months:
            self.query(period=Period(month, month))
        for n in range(12):
            self.query(search=str(n))
        self.assertLessEqual(self.provider.cache_info["scopes"], 4)
        self.assertLessEqual(self.provider.cache_info["views"], 6)

    def test_cancelled_cache_hit_does_not_return_data(self):
        self.query()
        cancel = Event()
        cancel.set()
        with self.assertRaises(Cancelled):
            self.provider.query(self.selection, cancel, lambda *_: None)

    def test_sorting_can_cancel_before_publishing_order(self):
        cancel = Event()

        def progress(_, message):
            if message.startswith("Ordenando"):
                cancel.set()

        with self.assertRaises(Cancelled):
            self.provider.query(self.selection, cancel, progress)
        self.assertEqual(self.provider.cache_info["views"], 0)

    def test_price_order_is_exact_for_very_close_ratios(self):
        big = 10**35
        self.provider._rows = (
            record(0, kg=big, fob_cents=big + 1, freight_cents=0, insurance_cents=0),
            record(1, kg=big, fob_cents=big, freight_cents=0, insurance_cents=0),
        )
        self.assertEqual(self.query(sort_column=11, descending=True).rows[0].identifier, 0)

    def test_text_order_folds_accents_and_case(self):
        self.provider._rows = tuple(
            record(i, product=name)
            for i, name in enumerate(("Polímero", "Óleo", "ácido", "Acrilato"))
        )
        self.assertEqual(
            [r.product for r in self.query(sort_column=1).rows],
            ["ácido", "Acrilato", "Óleo", "Polímero"],
        )

    def test_format_ignores_ambient_decimal_context(self):
        with localcontext() as context:
            context.prec = 5
            self.assertEqual(number(Decimal("123456789.12345"), 3), "123.456.789,123")
        self.assertEqual(number(Decimal("-0.0001"), 3), "0,000")
        for value in ("NaN", "Infinity"):
            with self.assertRaises(ValueError):
                number(Decimal(value))

    def test_500_independent_filter_and_aggregation_scenarios(self):
        self.query()
        source = self.provider._rows
        rng = random.Random(503)
        for i in range(500):
            start, end = sorted(rng.sample(DEMO_PERIOD.months, 2))
            ncm = rng.choice(("", source[i % len(source)].ncm))
            country = rng.choice(("", "China", "Holanda"))
            uf = rng.choice(("", "SP", "RJ"))
            port = rng.choice(("", PORTS[0], PORTS[1]))
            selection = Selection(
                Period(start, end),
                ncm=ncm,
                country=country,
                state=uf,
                port=port,
                sort_column=9,
                descending=bool(i % 2),
                page_size=25,
                page=1 + i % 5,
            )
            result = self.provider.query(selection, Event(), lambda *_: None)
            expected = [
                r
                for r in source
                if start <= r.period <= end
                and (not ncm or r.ncm == ncm)
                and (not country or r.country == country)
                and (not uf or r.state == uf)
                and (not port or r.port == port)
            ]
            self.assertEqual(result.totals.records, len(expected))
            self.assertEqual(
                result.totals.cif_cents,
                sum(r.fob_cents + r.freight_cents + r.insurance_cents for r in expected),
            )
            self.assertEqual(result.totals.kg, sum(r.kg for r in expected))
            self.assertEqual(sum(v for _, v in result.monthly), result.totals.cif_cents)
            self.assertEqual(sum(v for _, v in result.countries), result.totals.cif_cents)
            ordered = sorted(
                expected,
                key=lambda r: (r.fob_cents + r.freight_cents + r.insurance_cents, r.identifier),
                reverse=selection.descending,
            )
            offset = (result.page - 1) * 25
            self.assertEqual(
                [r.identifier for r in result.rows],
                [r.identifier for r in ordered[offset : offset + 25]],
            )


class ReviewQtTests(unittest.TestCase):
    setUp = QtTests.setUp
    tearDown = QtTests.tearDown
    item = QtTests.item
    load = QtTests.load

    def test_port_control_and_filter_are_consistent(self):
        self.load()
        self.controller.setFilter("port", PORTS[1])
        settled(self.controller)
        self.assertTrue(all(r.port == PORTS[1] for r in self.controller.table.rows))
        self.assertEqual(self.item("portFilter").property("currentValue"), PORTS[1])
        self.controller.clearFilters()
        settled(self.controller)
        self.assertEqual(self.item("portFilter").property("currentIndex"), 0)

    def test_cancel_pending_filter_restores_visible_selection(self):
        self.load()
        before = self.controller.table.rows
        self.controller.setFilter("country", "China")
        self.assertTrue(self.controller.state["waiting"])
        self.controller.cancel()
        APP.processEvents()
        self.assertEqual(self.item("countryFilter").property("currentIndex"), 0)
        self.assertFalse(self.controller.state["waiting"])
        self.assertEqual(before, self.controller.table.rows)

    def test_stale_result_during_debounce_does_not_commit(self):
        self.load()
        old = self.controller._result
        self.controller.selectRow(0)
        self.controller.setFilter("country", "China")
        self.controller._succeeded(old)
        self.assertEqual(self.controller.state["selection"], 0)
        self.assertTrue(self.controller.state["waiting"])
        settled(self.controller)

    def test_selection_theme_page_preserve_analysis_notifications(self):
        self.load()
        spy = QSignalSpy(self.controller.analysisChanged)
        self.controller.selectRow(0)
        self.controller.setPreference("dark", True)
        self.controller.setPage(2)
        settled(self.controller)
        self.assertEqual(spy.count(), 0)

    def test_search_changes_only_table_notifications(self):
        self.load()
        spy = QSignalSpy(self.controller.analysisChanged)
        self.controller.setFilter("search", "texto inexistente")
        settled(self.controller)
        self.assertEqual(spy.count(), 0)
        self.assertEqual(self.controller.state["tableRange"], "0 registros")

    def test_dialogs_stay_inside_small_window(self):
        self.window.resize(500, 400)
        self.load()
        self.controller.selectRow(0)
        for name in ("settingsDialog", "projectDialog", "detailDialog"):
            dialog = self.item(name)
            QMetaObject.invokeMethod(dialog, "open")
            self.assertTrue(pump(lambda: dialog.property("opened")))
            self.assertGreaterEqual(dialog.property("y"), 4)
            self.assertLessEqual(dialog.property("y") + dialog.property("height"), 396)
            QMetaObject.invokeMethod(dialog, "close")
            self.assertTrue(pump(lambda: not dialog.property("visible")))
        self.assertEqual(self.bundle.messages, [])

    def test_modal_suppresses_background_shortcuts(self):
        dialog = self.item("settingsDialog")
        QMetaObject.invokeMethod(dialog, "open")
        pump(lambda: dialog.property("opened"))
        QTest.keyClick(self.window, Qt.Key.Key_F5)
        APP.processEvents()
        self.assertFalse(self.controller.state["loaded"])
        self.assertFalse(self.controller.state["busy"])

    def test_draft_period_is_explicit(self):
        self.load()
        before = self.controller.table.rows
        self.item("startPeriod").setProperty("currentIndex", 0)
        APP.processEvents()
        self.assertTrue(self.item("draftPeriodNotice").property("visible"))
        self.assertEqual(before, self.controller.table.rows)

    def test_extended_keyboard_navigation(self):
        self.load()
        self.item("recordsTable").forceActiveFocus()
        QTest.keyClick(self.window, Qt.Key.Key_End)
        self.assertEqual(self.controller.state["selection"], 49)
        QTest.keyClick(self.window, Qt.Key.Key_Home)
        self.assertEqual(self.controller.state["selection"], 0)
        QTest.keyClick(self.window, Qt.Key.Key_PageDown)
        self.assertEqual(self.controller.state["selection"], 8)

    def test_shutdown_is_idempotent_after_deferred_deletes(self):
        self.controller._provider = DemoProvider(20000)
        self.controller.queryPeriod("2025-01", "2026-09")
        self.controller.shutdown()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.controller.shutdown()

    def test_brand_requested_pixel_size_and_bounded_cache(self):
        provider = BrandProvider(PACKAGE / "assets/liarte-logo-transparente.png")
        for width in (150, 180, 210, 250, 300, 400):
            size = QSize()
            image = provider.requestImage("dark", size, QSize(width, 0))
            self.assertLessEqual(image.width(), width)
            self.assertEqual(size.width(), image.width())
        self.assertLessEqual(len(provider._scaled), 4)

    def test_invalid_preference_does_not_prevent_startup(self):
        settings = Mock()
        settings.value.side_effect = ValueError("invalid")
        with self.assertLogs("liarte.desktop", level="WARNING"):
            controller = DesktopController(DemoProvider(1), settings)
        self.assertFalse(controller.state["dark"])
        controller.shutdown()

    def test_preference_save_failure_keeps_session_functional(self):
        settings = Mock()
        settings.value.return_value = False
        settings.status.return_value = QSettings.Status.AccessError
        controller = DesktopController(DemoProvider(1), settings)
        controller.setPreference("dark", True)
        self.assertTrue(controller.state["dark"])
        self.assertTrue(controller.state["settingsNotice"])
        controller.shutdown()

    def test_failed_result_commit_preserves_previous_table(self):
        self.load()
        before = self.controller.table.rows
        malformed = replace(self.controller._result, monthly=(("data inválida", 100),))
        with self.assertLogs("liarte.desktop", level="ERROR"):
            self.controller._succeeded(malformed)
        self.assertEqual(self.controller.table.rows, before)
        self.assertTrue(self.controller.state["error"])

    def test_first_and_last_page_navigation(self):
        self.load()
        self.controller.setPage(self.controller.state["pages"])
        settled(self.controller)
        self.assertFalse(self.item("lastPage").property("enabled"))
        self.assertTrue(self.item("firstPage").property("enabled"))
        self.controller.setPage(1)
        settled(self.controller)
        self.assertFalse(self.item("firstPage").property("enabled"))

    def test_header_actions_keep_their_complete_labels(self):
        for width, height in ((500, 400), (1380, 900)):
            self.window.resize(width, height)
            APP.processEvents()
            for name in ("themeButton", "settingsButton"):
                control = self.item(name)
                caption = control.property("text")
                pending = list(control.childItems())
                labels = []
                while pending:
                    child = pending.pop()
                    pending.extend(child.childItems())
                    if (
                        child.property("text") == caption
                        and child.property("truncated") is not None
                    ):
                        labels.append(child)
                self.assertEqual(len(labels), 1, name)
                if caption:
                    self.assertFalse(labels[0].property("truncated"), (width, name, caption))
                    self.assertLessEqual(labels[0].property("contentWidth"), labels[0].width() + 0.1)

    def test_action_widths_follow_larger_rendered_font_metrics(self):
        from PySide6.QtCore import QPointF
        from PySide6.QtGui import QFont

        self.load()
        self.item("trendMetric").setProperty("currentIndex", 1)
        self.item("quickExportButton").setProperty("visible", True)
        controls = [
            self.item(name)
            for name in (
                "settingsButton", "toggleFilters", "filterExpansion", "clearFilters",
                "priceScale", "openTrendValues", "quickExportButton", "queryButton",
                "cancelButton",
            )
        ]
        preset_names = {"preset3", "preset6", "preset12"}
        presets = [
            child for child in self.item("cancelButton").parentItem().childItems()
            if child.objectName() in preset_names
        ]
        self.assertEqual({child.objectName() for child in presets}, preset_names)
        controls.extend(presets)
        for control in controls:
            font = QFont(control.property("font"))
            font.setPixelSize(font.pixelSize() * 2)
            control.setProperty("font", font)
        for width in (500, 1380):
            self.window.resize(width, 900)
            QTest.qWait(30)
            for control in controls:
                caption = control.property("text")
                if not caption:
                    continue
                pending = list(control.childItems())
                labels = []
                while pending:
                    child = pending.pop()
                    pending.extend(child.childItems())
                    if (
                        child.property("text") == caption
                        and child.property("truncated") is not None
                    ):
                        labels.append(child)
                self.assertEqual(len(labels), 1, caption)
                self.assertFalse(labels[0].property("truncated"), (width, caption))
                left = control.mapToScene(QPointF()).x()
                self.assertGreaterEqual(left, 0, caption)
                self.assertLessEqual(left + control.width(), width, caption)
            for names in (
                ("toggleFilters", "filterExpansion", "clearFilters"),
                ("priceScale", "openTrendValues"),
            ):
                first, last = self.item(names[0]), self.item(names[-1])
                layout = first.parentItem()
                available = layout.parentItem().width()
                needed = sum(self.item(name).implicitWidth() for name in names)
                needed += len(names) * layout.property("columnSpacing")
                same_row = max(first.y(), last.y()) < min(
                    first.y() + first.height(), last.y() + last.height()
                )
                self.assertEqual(same_row, available >= needed, (width, names))
                self.assertAlmostEqual(layout.width(), available, delta=0.1)
        self.assertEqual(self.bundle.messages, [])
