"""Contratos de uso e movimento; respostas oficiais capturadas, sem rede nos testes."""

from __future__ import annotations

import math
from pathlib import Path
import re
import unittest

from PySide6.QtCore import QObject, QPointF, QMetaObject
from PySide6.QtTest import QTest

from tests import test_comex
from tests.test_qt import APP, pump, settled


class InterfaceTests(unittest.TestCase):
    setUp = test_comex.RealQtTests.setUp
    tearDown = test_comex.RealQtTests.tearDown
    load = test_comex.RealQtTests.load

    def item(self, name):
        result = self.window.findChild(QObject, name)
        if result is None:
            # Repeater delegates have a visual parent that can differ from
            # QObject ownership; inspect the same tree that the user sees.
            pending = [self.window.contentItem()]
            while pending:
                child = pending.pop()
                if child.objectName() == name:
                    result = child
                    break
                pending.extend(child.childItems())
        self.assertIsNotNone(result, name)
        return result

    def test_initial_workspace_has_one_clear_action_and_no_empty_graphs(self):
        self.assertTrue(self.item("emptyState").isVisible())
        self.assertFalse(self.item("trendPanel").isVisible())
        self.assertFalse(self.item("originsPanel").isVisible())
        self.assertEqual(self.item("queryButton").property("text"), "Consultar")
        self.assertFalse(self.controller.state["demo"])
        self.assertEqual(self.bundle.messages, [])

    def test_removing_one_chip_preserves_other_dimensions(self):
        self.load()
        first = self.provider.snapshot.general_records[0]
        self.controller.setFilters("country", [first.country])
        self.controller.setFilters("state", [first.state])
        settled(self.controller)
        chip = self.item("activeFilter_country")
        test_comex.click(self.window, chip)
        settled(self.controller)
        self.assertEqual(self.controller.state["countryValues"], [])
        self.assertEqual(self.controller.state["stateValues"], [first.state])
        self.assertTrue(all(r.state == first.state for r in self.controller.table.rows))
        self.assertEqual(self.bundle.messages, [])

    def test_clear_search_preserves_analysis_filters_and_totals(self):
        self.load()
        self.controller.setFilters("country", ["China"])
        settled(self.controller)
        metrics = self.controller.state["metrics"]
        self.controller.setFilter("search", "Santos")
        settled(self.controller)
        test_comex.click(self.window, self.item("clearSearch"))
        settled(self.controller)
        self.assertEqual(self.item("searchBox").property("text"), "")
        self.assertEqual(self.controller.state["countryValues"], ["China"])
        self.assertEqual(self.controller.state["metrics"], metrics)
        self.assertEqual(self.bundle.messages, [])

    def test_monthly_sheets_option_remains_available_in_preferences(self):
        before = self.controller.state["monthlySheets"]
        test_comex.click(self.window, self.item("settingsButton"))
        self.assertTrue(pump(lambda: self.item("settingsDialog").property("opened")))
        test_comex.click(self.window, self.item("monthlySheets"))
        self.assertEqual(self.controller.state["monthlySheets"], not before)
        self.assertEqual(self.bundle.messages, [])

    def test_direct_api_preferences_need_no_cache_toggle_or_central_settings(self):
        test_comex.click(self.window, self.item("settingsButton"))
        self.assertTrue(pump(lambda: self.item("settingsDialog").property("opened")))
        self.assertIsNone(self.window.findChild(QObject, "refreshSource"))
        self.assertFalse(self.item("configureComexAccess").isVisible())
        self.assertEqual(self.bundle.messages, [])

    def test_origin_bars_use_all_origins_as_denominator(self):
        self.load()
        chart = self.item("originChart")
        rows = [
            {"label": str(i), "value": value, "share": str(value) + "%"}
            for i, value in enumerate((40, 20, 10, 10, 8, 7, 5))
        ]
        chart.setProperty("rows", rows)
        APP.processEvents()
        self.assertAlmostEqual(chart.property("total"), 100)
        self.assertAlmostEqual(self.item("originRow0").property("ratio"), 0.4)
        self.assertIsNone(self.window.findChild(QObject, "originRow6"))
        self.assertEqual(self.bundle.messages, [])

    def _animate_chart(self):
        self.load()
        chart = self.item("monthlyChart")
        self.controller.setPreference("reducedMotion", False)
        chart.setProperty(
            "points",
            [
                {"period": "2026-07", "label": "Julho", "value": 10},
                {"period": "2026-08", "label": "Agosto", "value": 35},
                {"period": "2026-09", "label": "Setembro", "value": 20},
            ],
        )
        self.assertTrue(pump(lambda: chart.property("animating"), 0.1))
        return chart

    def test_curve_reveal_does_not_repaint_canvas_each_frame(self):
        chart = self._animate_chart()
        before = chart.property("curvePaintCount")
        self.assertTrue(pump(lambda: not chart.property("animating"), 1))
        paints = chart.property("curvePaintCount") - before
        self.assertLessEqual(paints, 3)
        self.assertAlmostEqual(chart.property("reveal"), 1)
        self.assertEqual(self.bundle.messages, [])

    def test_hover_guide_does_not_repaint_the_curve(self):
        chart = self._animate_chart()
        pump(lambda: not chart.property("animating"), 1)
        QTest.qWait(30)
        before = chart.property("curvePaintCount")
        for i in (0, 1, 2, -1, 1, -1):
            chart.setProperty("hoverIndex", i)
            APP.processEvents()
        self.assertEqual(chart.property("curvePaintCount"), before)
        self.assertEqual(self.bundle.messages, [])

    def test_reduce_motion_stops_a_running_reveal(self):
        chart = self._animate_chart()
        self.controller.setPreference("reducedMotion", True)
        APP.processEvents()
        self.assertFalse(chart.property("animating"))
        self.assertEqual(chart.property("reveal"), 1)
        self.assertEqual(self.bundle.messages, [])

    def test_zero_single_and_long_series_are_finite_and_accessible(self):
        self.load()
        self.controller.setPreference("reducedMotion", True)
        chart = self.item("monthlyChart")
        for count in (0, 1, 12, 120):
            points = [
                {"period": f"{2016 + i // 12:04d}-{1 + i % 12:02d}", "label": str(i), "value": 0}
                for i in range(count)
            ]
            chart.setProperty("points", points)
            QTest.qWait(20)
            self.assertGreater(chart.property("maximum"), 0)
            self.assertTrue(math.isfinite(chart.property("maximum")))
            self.assertFalse(chart.property("animating"))
        self.assertEqual(self.bundle.messages, [])

    def test_active_chips_wrap_inside_a_compact_workspace(self):
        self.load()
        self.window.resize(500, 400)
        self.controller.setFilters("country", ["China", "Estados Unidos"])
        self.controller.setFilters("state", ["SP", "SC"])
        settled(self.controller)
        QTest.qWait(30)
        for name in ("activeFilter_country", "activeFilter_state"):
            chip = self.item(name)
            x = chip.mapToScene(QPointF(0, 0)).x()
            self.assertGreaterEqual(x, 0)
            self.assertLessEqual(x + chip.width(), 500)
        self.assertEqual(self.bundle.messages, [])

    def test_primary_button_captions_are_not_truncated(self):
        self.load()
        for width in (500, 760, 1120, 1380):
            self.window.resize(width, 900)
            QTest.qWait(20)
            for name in ("settingsButton", "clearFilters", "queryButton"):
                control = self.item(name)
                caption = control.property("text")
                for child in control.findChildren(QObject):
                    if (
                        caption
                        and child.property("text") == caption
                        and child.property("truncated") is not None
                    ):
                        self.assertFalse(child.property("truncated"), (width, name, caption))
        self.assertEqual(self.bundle.messages, [])

    def test_workspace_omits_internal_platform_and_cache_descriptions(self):
        self.load()
        texts = []
        for child in self.window.findChildren(QObject):
            if hasattr(child, "isVisible") and child.isVisible():
                value = child.property("text")
                if isinstance(value, str):
                    texts.append(value)
        shown = " ".join(texts).lower()
        for term in (
            "pyside",
            "qml",
            "protheus",
            "sql server",
            "preparado em",
            "cache",
            "módulos futuros",
        ):
            self.assertNotIn(term, shown)
        QMetaObject.invokeMethod(self.item("projectDialog"), "open")
        self.assertTrue(pump(lambda: self.item("projectDialog").property("opened")))
        self.assertEqual(self.bundle.messages, [])

    def test_rate_limit_message_is_readable_and_preserves_technical_diagnostic(self):
        self.load()
        previous = self.controller.table.rows
        raw = 'Consulta oficial não concluída: API retornou HTTP 429: {"error":{"code":429}}'
        self.controller._failed(raw)
        APP.processEvents()
        self.assertEqual(self.controller.state["error"], raw)
        self.assertEqual(self.controller.table.rows, previous)
        shown = self.item("queryError").property("text")
        self.assertIn("limite de consultas", shown)
        self.assertNotIn("HTTP", shown)
        self.assertNotIn("{", shown)
        self.controller._update(
            stage="Comex Stat temporariamente limitado (HTTP 429) · nova tentativa em 11 s"
        )
        APP.processEvents()
        self.assertNotIn("HTTP", self.item("queryStage").property("text"))
        self.assertIn("11 s", self.item("queryStage").property("text"))
        self.assertEqual(self.bundle.messages, [])

    def test_validation_errors_remain_explicit(self):
        self.load()
        self.controller._failed("Consulta oficial não concluída: CIF divergente; lote recusado.")
        APP.processEvents()
        self.assertEqual(self.item("queryError").property("text"), "CIF divergente; lote recusado.")
        self.assertEqual(self.bundle.messages, [])


class PaletteTests(unittest.TestCase):
    def test_text_and_emphasized_card_contrast_in_both_themes(self):
        source = (
            Path(__file__).parents[1] / "src/liarte_desktop/qml/components/Theme.qml"
        ).read_text()

        def luminance(color):
            channels = [int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
            channels = [
                v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in channels
            ]
            return sum(a * b for a, b in zip(channels, (0.2126, 0.7152, 0.0722)))

        def contrast(a, b):
            bright, dark = sorted((luminance(a), luminance(b)), reverse=True)
            return (bright + 0.05) / (dark + 0.05)

        for index in (0, 1):
            colors = {}
            for name, dark, light in re.findall(
                r'property color (\w+): dark \? "(#[0-9a-f]{6})" : "(#[0-9a-f]{6})"', source
            ):
                colors[name] = (dark, light)[index]
            for foreground in ("text", "muted", "danger"):
                for background in ("surface", "canvas"):
                    self.assertGreaterEqual(
                        contrast(colors[foreground], colors[background]),
                        4.5,
                        (index, foreground, background),
                    )
            self.assertGreaterEqual(contrast("#ffffff", colors["hero"]), 4.5)
            self.assertGreaterEqual(contrast("#c4daed", colors["hero"]), 4.5)
            self.assertGreaterEqual(contrast("#ffffff", colors["primary"]), 4.5)
