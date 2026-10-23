"""Gráficos de estoque: leitura e interação em diferentes larguras reais."""

from pathlib import Path
import unittest

from PySide6.QtCore import QObject, Qt, QUrl
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtTest import QSignalSpy, QTest

from tests.test_qt import APP, pump

ROOT = Path(__file__).resolve().parents[1]


def variant(value):
    return value.toVariant() if hasattr(value, "toVariant") else value


class StockChartResponsiveTests(unittest.TestCase):
    def setUp(self):
        self.engine = QQmlEngine()
        self.messages = []
        self.engine.warnings.connect(lambda warnings: self.messages.extend(w.toString() for w in warnings))
        self.component = QQmlComponent(self.engine)
        self.window = None

    def tearDown(self):
        if self.window is not None:
            self.window.close()
            self.window.deleteLater()
        self.component.deleteLater()
        self.engine.deleteLater()
        pump(lambda: False, 0.03)

    def create(self, name):
        source = f'''import QtQuick
import QtQuick.Controls
import "." as Ui
Window {{
    width: 500; height: 280; visible: true
    Ui.{name} {{ objectName: "subject"; anchors.fill: parent }}
}}'''
        url = QUrl.fromLocalFile(str(ROOT / "src/liarte_desktop/qml/components/ResponsiveTest.qml"))
        self.component.setData(source.encode(), url)
        self.assertEqual(self.component.errors(), [])
        self.window = self.component.create()
        self.assertIsNotNone(self.window)
        self.chart = self.window.findChild(QObject, "subject")
        self.assertIsNotNone(self.chart)
        self.assertTrue(pump(lambda: self.chart.width() > 0))

    def descendants(self, prefix):
        pending, result = [self.chart], []
        while pending:
            item = pending.pop()
            if item.objectName().startswith(prefix):
                result.append(item)
            pending.extend(item.childItems())
        return result

    def test_dense_month_labels_reflow_without_overlap_and_keep_the_last_month(self):
        self.create("StockPlot")
        points = [{"period": f"{2024 + i // 12}-{i % 12 + 1:02}", "label": str(i), "value": i + 1} for i in range(36)]
        self.chart.setProperty("points", points)
        counts = []
        for width in (260, 420, 760):
            self.window.resize(width, 280)
            self.window.requestUpdate()
            pump(lambda: False, 0.06)
            ticks = sorted(self.descendants("subjectCategoryTick"), key=lambda item: item.x())
            self.assertTrue(ticks)
            self.assertTrue(any(tick.objectName().endswith("35") for tick in ticks))
            counts.append(len(ticks))
            for tick in ticks:
                self.assertGreaterEqual(tick.x(), 0)
                self.assertLessEqual(tick.x() + tick.width(), self.chart.width() + 1)
                self.assertLessEqual(tick.y() + tick.height(), self.chart.height() + 1)
            for left, right in zip(ticks, ticks[1:]):
                self.assertLessEqual(left.x() + left.width() + 6, right.x())
        self.assertLess(counts[0], counts[-1])
        self.assertEqual(variant(self.chart.property("points")), points)
        self.assertEqual(self.messages, [])

    def test_negative_axis_values_fit_and_missing_months_remain_missing(self):
        self.create("StockPlot")
        points = [
            {"period": "2026-01", "label": "Jan", "value": -123456789.25},
            {"period": "2026-02", "label": "Fev", "value": None},
            {"period": "2026-03", "label": "Mar", "value": 12.5},
        ]
        self.chart.setProperty("unit", "KG")
        self.chart.setProperty("points", points)
        pump(lambda: False, 0.06)
        for tick in self.descendants("subjectValueTick"):
            self.assertLessEqual(tick.implicitWidth(), tick.width() + 1)
        self.assertEqual(variant(self.chart.property("points")), points)
        self.assertEqual(self.chart.property("selectedIndex"), 2)
        self.chart.setProperty("hoverIndex", 1)
        self.assertIn("Sem dados", self.chart.property("readout"))
        self.assertEqual(self.messages, [])

    def test_keyboard_and_hover_read_exact_values_without_repainting_the_series(self):
        self.create("StockPlot")
        points = [
            {"period": "2026-01", "label": "Jan", "value": 9.25, "display": "R$ 9,25"},
            {"period": "2026-02", "label": "Fev", "value": 10.75, "display": "R$ 10,75"},
            {"period": "2026-03", "label": "Mar", "value": None},
        ]
        self.chart.setProperty("points", points)
        self.assertTrue(pump(lambda: not self.chart.property("animating"), 1))
        self.assertEqual(self.chart.property("selectedIndex"), 1)
        self.assertIn("R$ 10,75", self.chart.property("readout"))
        before = self.chart.property("curvePaintCount")
        self.chart.setProperty("hoverIndex", 0)
        APP.processEvents()
        self.assertIn("R$ 9,25", self.chart.property("readout"))
        self.chart.setProperty("hoverIndex", -1)
        self.chart.forceActiveFocus()
        QTest.keyClick(self.window, Qt.Key.Key_Home)
        self.assertEqual(self.chart.property("selectedIndex"), 0)
        QTest.keyClick(self.window, Qt.Key.Key_End)
        self.assertEqual(self.chart.property("selectedIndex"), 2)
        self.assertIn("Sem dados", self.chart.property("readout"))
        APP.processEvents()
        self.assertEqual(self.chart.property("curvePaintCount"), before)
        self.assertEqual(variant(self.chart.property("points")), points)
        self.assertEqual(self.messages, [])

    def test_ranking_moves_amounts_to_the_second_line_and_retains_product_activation(self):
        self.create("StockBars")
        rows = [
            {"code": "0001", "name": "Produto com descrição comercial extensa", "display": "R$ 1.234.567,89", "value": 123456789, "share": "100,0%"},
            {"code": "0002", "name": "Outro produto", "display": "R$ 12,50", "value": 1250, "share": "0,0%"},
        ]
        self.chart.setProperty("interactive", True)
        self.chart.setProperty("rows", rows)
        spy = QSignalSpy(self.chart.selected)
        for width, compact in ((280, True), (660, False)):
            self.window.resize(width, 280)
            pump(lambda: False, 0.06)
            self.assertEqual(self.chart.property("compact"), compact)
            for index in range(len(rows)):
                name = self.descendants(f"subjectRow{index}Name")[0]
                amount = self.descendants(f"subjectRow{index}" + ("CompactAmount" if compact else "Amount"))[0]
                self.assertGreater(name.width(), 40)
                self.assertTrue(amount.isVisible())
                self.assertFalse(amount.property("truncated"))
                self.assertEqual(amount.property("text"), rows[index]["display"])
        row = self.descendants("subjectRow0")[0]
        row.forceActiveFocus()
        QTest.keyClick(self.window, Qt.Key.Key_Space)
        self.assertEqual(spy.count(), 1)
        self.assertEqual(spy.at(0), ["0001"])
        self.assertEqual(variant(self.chart.property("rows")), rows)
        self.assertEqual(self.messages, [])
