"""Charts offer explicit drilldown and complete metric context by keyboard."""

from pathlib import Path
import unittest

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QPointF, Qt, QUrl
from PySide6.QtGui import QFont
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtTest import QSignalSpy, QTest

from tests.test_qt import APP, click, pump

COMPONENTS = Path(__file__).resolve().parents[1] / "src/liarte_desktop/qml/components"


class UXChartInteractionTests(unittest.TestCase):
    def setUp(self):
        self.engine = QQmlApplicationEngine()
        self.messages = []
        self.engine.warnings.connect(lambda warnings: self.messages.extend(str(w) for w in warnings))
        self.engine.loadData(b'''import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "." as Ui
ApplicationWindow {
    visible: true
    width: 500
    height: 700
    property string subjectKind: "origin"
    readonly property bool metricTooltipVisible: metric.ToolTip.toolTip ? metric.ToolTip.toolTip.visible : false
    readonly property string metricTooltipText: metric.ToolTip.text
    readonly property real metricBorderWidth: metric.border.width
    Component.onCompleted: Ui.Theme.reducedMotion = true
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 12
        Button { objectName: "before"; text: "Antes" }
        Ui.OriginChart {
            objectName: "origins"
            visible: subjectKind === "origin"
            Layout.fillWidth: true
            Layout.preferredHeight: 430
        }
        Ui.MetricCard {
            id: metric
            objectName: "metric"
            visible: subjectKind === "metric"
            Layout.fillWidth: true
        }
        Button { objectName: "after"; text: "Depois" }
        Item { Layout.fillHeight: true }
    }
}''', QUrl.fromLocalFile(str(COMPONENTS / "ChartInteractionTest.qml")))
        self.assertTrue(self.engine.rootObjects(), self.messages)
        self.window = self.engine.rootObjects()[0]
        self.window.requestActivate()
        self.assertTrue(pump(lambda: not self.window.grabWindow().isNull()))

    def tearDown(self):
        if hasattr(self, "window"):
            self.window.close()
        self.engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        APP.processEvents()

    def item(self, name):
        def find(item):
            if item.objectName() == name:
                return item
            for child in item.childItems():
                found = find(child)
                if found is not None:
                    return found
            return None

        value = self.window.findChild(QObject, name) or find(self.window.contentItem())
        self.assertIsNotNone(value, name)
        return value

    def origins(self, *, interactive=True):
        chart = self.item("origins")
        chart.setProperty("interactive", interactive)
        chart.setProperty("rows", [
            {"label": "Origem " + str(index), "value": index, "share": f"{index / 28 * 100:.1f}%"}
            for index in range(7, 0, -1)
        ])
        row = self.item("originRow0")
        previous = None

        def rendered_row_is_stable():
            nonlocal previous
            frame = self.window.grabWindow()
            point = row.mapToScene(QPointF())
            geometry = (point.x(), point.y(), row.width(), row.height())
            stable = previous == geometry
            previous = geometry
            return stable and row.width() > 0 and not frame.isNull()

        self.assertTrue(pump(rendered_row_is_stable))
        return chart

    def test_origin_bars_use_all_countries_even_when_only_six_are_displayed(self):
        chart = self.origins()
        self.assertEqual(chart.property("total"), 28)
        self.assertEqual(self.item("originRow0").property("ratio"), 0.25)
        self.assertEqual(self.item("originRow5").property("ratio"), 2 / 28)
        self.assertIsNone(self.window.findChild(QObject, "originRow6"))
        self.assertEqual(self.messages, [])

    def test_origins_filter_only_after_click_or_explicit_keyboard_activation(self):
        chart = self.origins()
        row = self.item("originRow0")
        spy = QSignalSpy(chart.originSelected)
        point = row.mapToScene(QPointF(row.width() / 2, row.height() / 2))
        QTest.mouseMove(self.window, point.toPoint())
        APP.processEvents()
        self.assertEqual(spy.count(), 0)
        click(self.window, row)
        self.assertEqual(spy.count(), 1)
        self.assertEqual(spy.at(0), ["Origem 7"])
        row.forceActiveFocus(Qt.FocusReason.TabFocusReason)
        for index, key in enumerate((Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space), 2):
            QTest.keyClick(self.window, key)
            self.assertEqual(spy.count(), index)
            self.assertEqual(spy.at(index - 1), ["Origem 7"])
        self.assertEqual(self.messages, [])

    def test_noninteractive_origins_do_not_filter_or_enter_the_tab_order(self):
        chart = self.origins(interactive=False)
        row = self.item("originRow0")
        spy = QSignalSpy(chart.originSelected)
        click(self.window, row)
        row.forceActiveFocus(Qt.FocusReason.OtherFocusReason)
        for key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            QTest.keyClick(self.window, key)
        self.assertEqual(spy.count(), 0)
        self.assertEqual(row.property("focusPolicy"), Qt.FocusPolicy.NoFocus)
        before = self.item("before")
        before.forceActiveFocus(Qt.FocusReason.TabFocusReason)
        QTest.keyClick(self.window, Qt.Key.Key_Tab)
        self.assertTrue(pump(self.item("after").hasActiveFocus))
        self.assertEqual(self.messages, [])

    def test_compact_origin_labels_preserve_exact_amounts_and_shares_with_wide_fonts(self):
        chart = self.origins()
        country = "Origem com descrição longa que permanece disponível ao investigar"
        chart.setProperty("rows", [{"label": country, "value": 0.0000014, "share": "100,0%"}])
        label, share, amount = (self.item(name) for name in ("originLabel0", "originShare0", "originAmount0"))
        for width in (280, 500, 900):
            self.window.resize(width, 700)
            for item in (label, share, amount):
                font = QFont(item.property("font"))
                font.setStretch(150)
                item.setProperty("font", font)
            self.assertTrue(pump(lambda: abs(chart.width() - (width - 24)) < 1))
            self.window.grabWindow()
            self.assertEqual(label.property("text"), country)
            self.assertEqual(amount.property("text"), "US$ 1,40")
            self.assertLessEqual(label.x() + label.width(), share.x() + 1)
            for item in (share, amount):
                self.assertFalse(item.property("truncated"))
        self.assertEqual(self.messages, [])

    def test_origin_accessible_amount_retains_exact_source_text_beyond_float_precision(self):
        chart = self.origins()
        exact = "US$ 123.456.789.012.345.678,91"
        chart.setProperty("rows", [{
            "label": "Origem exata", "value": 123456789012.34567,
            "share": "100,0%", "full": exact,
        }])
        self.assertTrue(pump(lambda: self.item("originRow0").property("exactAmount") == exact))
        self.assertEqual(self.item("originRow0").property("exactAmount"), exact)
        self.assertEqual(self.messages, [])

    def metric(self):
        self.window.setProperty("subjectKind", "metric")
        card = self.item("metric")
        card.setProperty("metric", {
            "label": "Capital observado no estoque selecionado",
            "value": "R$ 123.456.789.012.345,67",
            "detail": "Quantidade por unidade e por filial; consulte os períodos completos.",
            "full": "O valor exato e a definição devem continuar disponíveis sem depender do cursor.",
            "issue": "Uma posição sem fechamento permanece desconhecida.",
        })
        self.assertTrue(pump(card.isVisible))
        return card

    def test_metric_keyboard_focus_exposes_complete_value_definition_and_issue(self):
        card = self.metric()
        self.window.resize(280, 700)
        before = self.item("before")
        before.forceActiveFocus(Qt.FocusReason.TabFocusReason)
        QTest.keyClick(self.window, Qt.Key.Key_Tab)
        self.assertTrue(pump(card.hasActiveFocus))
        self.assertTrue(pump(lambda: self.window.property("metricTooltipVisible")))
        text = self.window.property("metricTooltipText")
        for expected in (
            "Capital observado no estoque selecionado", "R$ 123.456.789.012.345,67",
            "Quantidade por unidade e por filial", "sem depender do cursor",
            "Uma posição sem fechamento permanece desconhecida",
        ):
            self.assertIn(expected, text)
            self.assertIn(expected, card.property("completeText"))
        self.assertEqual(self.window.property("metricBorderWidth"), 2)
        self.assertEqual(self.messages, [])

    def test_metric_context_closes_when_focus_moves_or_the_card_becomes_hidden(self):
        card = self.metric()
        card.forceActiveFocus(Qt.FocusReason.TabFocusReason)
        self.assertTrue(pump(lambda: self.window.property("metricTooltipVisible")))
        self.item("after").forceActiveFocus(Qt.FocusReason.TabFocusReason)
        self.assertTrue(pump(lambda: not self.window.property("metricTooltipVisible")))
        card.forceActiveFocus(Qt.FocusReason.TabFocusReason)
        self.assertTrue(pump(lambda: self.window.property("metricTooltipVisible")))
        card.setVisible(False)
        self.assertTrue(pump(lambda: not self.window.property("metricTooltipVisible")))
        self.assertEqual(self.messages, [])
