"""Product investigations remain usable through actual Qt controls and charts."""

import unittest

from PySide6.QtCore import (
    Property, QCoreApplication, QEvent, QObject, QPointF, Qt, QUrl, Signal, Slot,
)
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtTest import QSignalSpy, QTest

from liarte_desktop.app import PACKAGE
from liarte_core.inventory_io import write_snapshot
from tests import test_inventory
from tests import test_inventory_alerts_qml as alert_tests
from tests.test_inventory_compare_qml import comparison_sample
from tests.test_qt import APP, click, pump


def variant(value):
    return value.toVariant() if hasattr(value, "toVariant") else value


class PerformanceFixture(QObject):
    """Small deterministic presentation; business calculations have core tests."""

    changed = Signal()

    def __init__(self):
        super().__init__()
        self.calls = []
        self.refreshes = 0
        self._state = {
            "available": True, "busy": False, "current": False, "error": "",
            "units": [{"value": "KG", "label": "KG"}, {"value": "L", "label": "L"}],
            "unit": "KG",
            "windows": [{"value": n, "label": str(n) + " meses"} for n in (1, 3, 6)],
            "window": 3, "sort": "most", "query": "", "page": 1,
            "pages": 2, "count": 12,
        }
        self._summary = {
            "scope": "Todas as filiais · sem alocação de vendas por armazém",
            "periodLabel": "Jul/2026 a Set/2026",
            "comparisonLabel": "Abr/2026 a Jun/2026 versus Jul/2026 a Set/2026",
            "notice": "Quantidades líquidas; meses parciais fora da comparação.",
            "rows": [],
        }
        self._detail = {}
        self._all_rows = [
            {
                "code": f"P{index:02d}",
                "name": "Resina para investigação de desempenho com nome longo " + str(index),
                "unit": "KG", "sold": str(200 - index) + ",000 KG",
                "evolution": "−20,0% · entre janelas completas",
                "turnover": "0,40 x/mês · mediana de 2 posições",
                "status": "Queda no volume líquido",
                "stock": "120,000 KG no fechamento",
            }
            for index in range(12)
        ]
        self._publish_page()

    @Property("QVariantMap", notify=changed)
    def state(self):
        return self._state

    @Property("QVariantMap", notify=changed)
    def summary(self):
        return self._summary

    @Property("QVariantMap", notify=changed)
    def detail(self):
        return self._detail

    def _publish_page(self):
        rows = [
            dict(row, unit=self._state["unit"])
            for row in self._all_rows
            if self._state["query"].casefold() in (row["code"] + " " + row["name"]).casefold()
        ]
        self._state["count"] = len(rows)
        self._state["pages"] = max(1, (len(rows) + 9) // 10)
        self._state["page"] = min(self._state["page"], self._state["pages"])
        start = (self._state["page"] - 1) * 10
        self._summary["rows"] = rows[start:start + 10]

    @Slot()
    def refresh(self):
        self.refreshes += 1
        self._state.update(current=True, busy=False, error="")
        self.changed.emit()

    @Slot(str, int, str, str)
    def configure(self, unit, window, sort, query):
        self.calls.append(("configure", unit, window, sort, query))
        self._state.update(
            unit=unit, window=window, sort=sort, query=query, page=1,
            current=True, busy=False, error="",
        )
        self._publish_page()
        self.changed.emit()

    @Slot(int)
    def setPage(self, page):
        self.calls.append(("page", page))
        self._state["page"] = page
        self._publish_page()
        self.changed.emit()

    @Slot(str, str)
    def investigate(self, code, unit):
        self.calls.append(("investigate", code, unit))
        row = next(row for row in self._all_rows if row["code"] == code)

        def series(title, symbol, values, note):
            return {
                "title": title, "unit": symbol,
                "points": [
                    {
                        "period": f"2026-{index + 7:02d}",
                        "label": ("Jul/2026", "Ago/2026", "Set/2026")[index],
                        "value": value,
                        "display": "Sem fechamento" if value is None else str(value) + " " + symbol,
                    }
                    for index, value in enumerate(values)
                ],
                "note": note,
            }

        self._detail = {
            "code": code, "name": row["name"], "unit": unit,
            "scope": "Produto e unidade selecionados · todas as filiais",
            "metrics": [
                {"label": "Vendas líquidas", "value": "180,000 " + unit, "detail": "Jul/2026 a Set/2026"},
                {"label": "Evolução", "value": "−20,0%", "detail": "Janelas completas de 3 meses"},
                {"label": "Cobertura estimada", "value": "61,3 dias", "detail": "Ao ritmo de vendas registrado; não é idade do lote"},
                {"label": "Giro da fonte · mediana", "value": "0,40 x/mês", "detail": "2 posições elegíveis · Set/2026"},
            ],
            "seriesKinds": [
                {"value": "sales", "label": "Vendas líquidas"},
                {"value": "quantity", "label": "Quantidade no fechamento"},
                {"value": "turnover", "label": "Giro da fonte"},
            ],
            "series": {
                "sales": series("Vendas líquidas mensais", unit, [100, 80, 0], "Zero líquido não comprova ausência de saída positiva."),
                "quantity": series("Quantidade no fechamento", unit, [100, None, 120], "Ausência de fechamento permanece desconhecida."),
                "turnover": series("Giro da fonte · mediana", "x/mês", [0.5, 0.4, 0.4], "Mediana por posição; não é giro consolidado."),
            },
            "evidence": ["Vendas líquidas caíram 20,0% entre as duas janelas completas."],
            "hypotheses": ["Verifique se houve mudança na demanda ou no planejamento de reposição."],
            "limitations": ["A base não comprova idade do lote, ruptura nem causa comercial da variação."],
        }
        self.changed.emit()

    @Slot()
    def closeDetail(self):
        self._detail = {}
        self.changed.emit()


class InventoryPerformanceQmlTests(unittest.TestCase):
    def setUp(self):
        self.fixture = PerformanceFixture()
        self.engine = QQmlApplicationEngine()
        self.messages = []
        self.engine.warnings.connect(lambda warnings: self.messages.extend(str(w) for w in warnings))
        self.engine.rootContext().setContextProperty("performanceFixture", self.fixture)
        self.engine.loadData(
            b'''import QtQuick
import QtQuick.Controls
import "components" as C
ApplicationWindow {
    visible: true
    width: 1380
    height: 900
    property string focusedProduct: ""
    Component.onCompleted: C.Theme.reducedMotion = true
    C.ActionButton {
        objectName: "stockPerformanceOpen"
        x: 20; y: 20
        text: "Desempenho dos produtos"
        onClicked: performanceDialog.open()
    }
    C.StockPerformance {
        id: performanceDialog
        performance: performanceFixture
        controlsEnabled: true
        onProductFocusRequested: code => focusedProduct = code
    }
}
''',
            QUrl.fromLocalFile(str(PACKAGE / "qml" / "performance-test.qml")),
        )
        self.assertTrue(self.engine.rootObjects(), self.messages)
        self.window = self.engine.rootObjects()[0]
        self.window.requestActivate()
        self.assertTrue(pump(lambda: self.window.isVisible()))

    def tearDown(self):
        if hasattr(self, "window"):
            self.window.close()
        self.engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        APP.processEvents()

    def item(self, name):
        def visual(item):
            if item.objectName() == name:
                return item
            for child in item.childItems():
                result = visual(child)
                if result is not None:
                    return result
            return None

        item = self.window.findChild(QObject, name)
        if item is None:
            item = visual(self.window.contentItem())
        self.assertIsNotNone(item, name)
        return item

    def open(self):
        button = self.item("stockPerformanceOpen")
        clicks = QSignalSpy(button.clicked)
        click(self.window, button)
        self.assertEqual(clicks.count(), 1)
        dialog = self.item("stockPerformanceDialog")
        self.assertTrue(pump(lambda: dialog.property("opened")))
        self.assertTrue(pump(lambda: self.fixture.state["current"]))
        self.assertFalse(self.window.grabWindow().isNull())
        return dialog

    def geometry(self, item):
        viewport = self.item("stockPerformanceDialog").property("bodyViewport")
        point = item.mapToItem(viewport, QPointF())
        return {
            "control": tuple(round(value, 3) for value in (point.x(), point.y(), item.width(), item.height())),
            "viewport": (viewport.width(), viewport.height()),
            "visible": item.isVisible(), "enabled": item.isEnabled(),
            "moving": viewport.property("moving"),
        }

    def reveal(self, item):
        viewport = self.item("stockPerformanceDialog").property("bodyViewport")
        point = item.mapToItem(viewport, QPointF())
        maximum = max(0, viewport.property("contentHeight") - viewport.height())
        target = viewport.property("contentY") + point.y() - 15
        viewport.setProperty("contentY", max(0, min(maximum, target)))
        self.window.update()
        APP.processEvents()

    def ready(self, control):
        previous = None

        def rendered():
            nonlocal previous
            self.reveal(control)
            frame = self.window.grabWindow()
            geometry = self.geometry(control)
            stable = previous == geometry
            previous = geometry
            x, y, width, height = geometry["control"]
            viewport_width, viewport_height = geometry["viewport"]
            return (
                stable and not frame.isNull() and geometry["visible"] and geometry["enabled"]
                and not geometry["moving"] and width > 0 and height > 0
                and x >= -1 and y >= -1
                and x + width <= viewport_width + 1 and y + height <= viewport_height + 1
            )

        self.assertTrue(pump(rendered), self.geometry(control))

    def click_dialog(self, control):
        self.ready(control)
        geometry = self.geometry(control)
        clicks = QSignalSpy(control.clicked)
        click(self.window, control)
        self.assertEqual(clicks.count(), 1, geometry)

    def select_combo(self, name, value):
        control = self.item(name)
        options = variant(control.property("model"))
        index = next(i for i, item in enumerate(options) if item["value"] == value)
        self.ready(control)
        if variant(control.property("currentValue")) == value:
            return
        activated = QSignalSpy(control.activated)
        control.forceActiveFocus(Qt.FocusReason.TabFocusReason)
        QTest.keyClick(self.window, Qt.Key.Key_Home)
        for _ in range(index):
            QTest.keyClick(self.window, Qt.Key.Key_Down)
        self.assertTrue(pump(lambda: variant(control.property("currentValue")) == value))
        self.assertGreater(activated.count(), 0)

    def type_search(self, text):
        control = self.item("stockPerformanceSearch")
        self.ready(control)
        control.forceActiveFocus(Qt.FocusReason.TabFocusReason)
        QTest.keyClick(self.window, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        for character in text:
            QTest.keyClick(self.window, Qt.Key(ord(character)))
        self.assertEqual(control.property("text").casefold(), text.casefold())

    def test_open_refreshes_once_and_drafts_require_explicit_apply(self):
        dialog = self.open()
        self.assertEqual(self.fixture.refreshes, 1)
        self.select_combo("stockPerformanceUnit", "L")
        self.select_combo("stockPerformanceWindow", 1)
        self.select_combo("stockPerformanceSort", "decline")
        self.type_search("RESINA")
        query = self.item("stockPerformanceSearch").property("text")
        self.assertEqual(self.fixture.calls, [])
        self.assertEqual(self.fixture.state["unit"], "KG")
        self.click_dialog(self.item("stockPerformanceApply"))
        self.assertEqual(self.fixture.calls, [("configure", "L", 1, "decline", query)])
        QTest.keyClick(self.window, Qt.Key.Key_Escape)
        self.assertTrue(pump(lambda: not dialog.property("visible")))
        self.open()
        self.assertEqual(self.fixture.refreshes, 1)
        self.assertEqual(self.item("stockPerformanceSearch").property("text"), query)
        self.assertEqual(self.messages, [])

    def test_pages_and_back_preserve_list_while_investigation_does_not_filter_product(self):
        self.open()
        self.assertEqual(len(self.fixture.summary["rows"]), 10)
        self.click_dialog(self.item("stockPerformanceNext"))
        self.assertEqual(self.fixture.state["page"], 2)
        self.assertEqual(len(self.fixture.summary["rows"]), 2)
        self.assertFalse(self.item("stockPerformanceNext").isEnabled())
        self.click_dialog(self.item("stockPerformanceRow0"))
        self.assertEqual(self.fixture.detail["code"], "P10")
        self.assertEqual(self.window.property("focusedProduct"), "")
        self.assertTrue(self.item("stockPerformanceEvidence").isVisible())
        self.assertTrue(self.item("stockPerformanceHypotheses").isVisible())
        self.click_dialog(self.item("stockPerformanceBack"))
        self.assertEqual(self.fixture.detail, {})
        self.assertEqual(self.fixture.state["page"], 2)
        self.assertEqual(self.fixture.summary["rows"][0]["code"], "P10")
        self.click_dialog(self.item("stockPerformancePrevious"))
        self.assertEqual(self.fixture.state["page"], 1)
        self.assertFalse(self.item("stockPerformancePrevious").isEnabled())
        self.assertEqual(self.messages, [])

    def test_chart_switches_single_series_keeps_gaps_and_accepts_keyboard_month_selection(self):
        self.open()
        self.click_dialog(self.item("stockPerformanceRow0"))
        chart = self.item("stockPerformanceChart")
        self.assertEqual(chart.property("unit"), "KG")
        self.assertEqual([point["value"] for point in variant(chart.property("points"))], [100, 80, 0])
        self.assertFalse(chart.property("movingAverage"))
        self.select_combo("stockPerformanceMeasure", "quantity")
        self.assertEqual([point["value"] for point in variant(chart.property("points"))], [100, None, 120])
        self.ready(chart)
        chart.forceActiveFocus(Qt.FocusReason.TabFocusReason)
        QTest.keyClick(self.window, Qt.Key.Key_Home)
        QTest.keyClick(self.window, Qt.Key.Key_Right)
        self.assertEqual(chart.property("selectedIndex"), 1)
        self.assertIn("Sem fechamento", chart.property("readout"))
        self.select_combo("stockPerformanceMeasure", "turnover")
        self.assertEqual(chart.property("unit"), "x/mês")
        self.assertEqual([point["value"] for point in variant(chart.property("points"))], [0.5, 0.4, 0.4])
        self.assertEqual(self.messages, [])

    def test_filter_product_is_an_explicit_action_after_investigation(self):
        dialog = self.open()
        self.click_dialog(self.item("stockPerformanceRow0"))
        self.assertEqual(self.window.property("focusedProduct"), "")
        self.click_dialog(self.item("stockPerformanceFilter"))
        self.assertEqual(self.window.property("focusedProduct"), "P00")
        self.assertTrue(pump(lambda: not dialog.property("visible")))
        self.assertEqual(self.messages, [])

    def test_stale_results_disable_rows_and_navigation_until_refreshed(self):
        self.open()
        self.fixture._state.update(current=False, busy=True)
        self.fixture.changed.emit()
        self.assertTrue(pump(lambda: not self.item("stockPerformanceRow0").isEnabled()))
        for name in ("stockPerformanceApply", "stockPerformanceNext", "stockPerformancePrevious"):
            self.assertFalse(self.item(name).isEnabled(), name)
        self.assertEqual(self.fixture.calls, [])
        self.fixture._state.update(current=True, busy=False)
        self.fixture.changed.emit()
        self.assertTrue(pump(lambda: self.item("stockPerformanceRow0").isEnabled()))
        self.assertTrue(self.item("stockPerformanceApply").isEnabled())
        self.assertEqual(self.messages, [])

    def test_wide_controls_fit_and_focus_reveals_controls_at_three_window_sizes(self):
        dialog = self.open()
        for name in (
            "stockPerformanceUnit", "stockPerformanceWindow", "stockPerformanceSort",
            "stockPerformanceSearch", "stockPerformanceApply",
            "stockPerformanceUnitLabel", "stockPerformanceWindowLabel",
            "stockPerformanceSortLabel", "stockPerformanceSearchLabel",
        ):
            control = self.item(name)
            font = control.property("font")
            font.setStretch(200)
            control.setProperty("font", font)
        for width, height in ((1380, 900), (900, 700), (500, 400)):
            with self.subTest(width=width):
                self.window.resize(width, height)
                self.assertTrue(pump(lambda: abs(self.window.contentItem().width() - width) < 1))
                self.assertFalse(self.window.grabWindow().isNull())
                viewport = dialog.property("bodyViewport")
                for name in (
                    "stockPerformanceUnit", "stockPerformanceWindow", "stockPerformanceSort",
                    "stockPerformanceSearch", "stockPerformanceApply", "stockPerformanceRows",
                ):
                    control = self.item(name)
                    point = control.mapToItem(viewport, QPointF())
                    self.assertGreaterEqual(point.x(), -1, name)
                    self.assertLessEqual(point.x() + control.width(), viewport.width() + 1, name)
                for name in (
                    "stockPerformanceUnit", "stockPerformanceWindow", "stockPerformanceSort",
                    "stockPerformanceSearch", "stockPerformanceApply",
                ):
                    control = self.item(name)
                    control.forceActiveFocus(Qt.FocusReason.TabFocusReason)
                    self.assertTrue(pump(control.hasActiveFocus), name)
                    self.assertTrue(pump(lambda: (
                        self.geometry(control)["control"][1] >= -1
                        and self.geometry(control)["control"][1] + control.height() <= viewport.height() + 1
                    )), self.geometry(control))
        self.assertEqual(self.messages, [])

    def test_compact_investigation_keeps_chart_and_month_readout_visible_during_keyboard_use(self):
        self.window.resize(500, 400)
        self.assertTrue(pump(lambda: abs(self.window.contentItem().width() - 500) < 1))
        self.open()
        self.click_dialog(self.item("stockPerformanceRow0"))
        chart = self.item("stockPerformanceChart")
        readout = self.item("stockPerformanceReadout")
        font = readout.property("font")
        font.setStretch(200)
        readout.setProperty("font", font)
        previous = None

        def rendered_detail_is_stable():
            nonlocal previous
            frame = self.window.grabWindow()
            geometry = (self.geometry(chart), self.geometry(readout))
            stable = previous == geometry
            previous = geometry
            return stable and not frame.isNull()

        self.assertTrue(pump(rendered_detail_is_stable))
        chart.forceActiveFocus(Qt.FocusReason.TabFocusReason)
        QTest.keyClick(self.window, Qt.Key.Key_Home)
        QTest.keyClick(self.window, Qt.Key.Key_Right)
        self.assertTrue(pump(chart.hasActiveFocus))
        self.assertIn("Ago/2026", readout.property("text"))
        for control in (chart, readout):
            self.assertTrue(pump(lambda: (
                self.geometry(control)["control"][0] >= -1
                and self.geometry(control)["control"][1] >= -1
                and self.geometry(control)["control"][0] + control.width() <= self.geometry(control)["viewport"][0] + 1
                and self.geometry(control)["control"][1] + control.height() <= self.geometry(control)["viewport"][1] + 1
            )), self.geometry(control))
        back = self.item("stockPerformanceBack")
        back.forceActiveFocus(Qt.FocusReason.TabFocusReason)
        self.assertTrue(pump(lambda: (
            self.geometry(back)["control"][1] >= -1
            and self.geometry(back)["control"][1] + back.height() <= self.geometry(back)["viewport"][1] + 1
        )), self.geometry(back))
        self.assertEqual(self.messages, [])


class InventoryPerformanceWorkspaceTests(unittest.TestCase):
    """The new entry uses the accepted inventory cache without changing its recut."""

    tearDown = test_inventory.InventoryUiTests.tearDown
    load = test_inventory.InventoryUiTests.load
    idle = test_inventory.InventoryUiTests.idle
    item = alert_tests.InventoryAlertQmlTests.item
    click_workspace = alert_tests.InventoryAlertQmlTests.click_workspace
    workspace_geometry = alert_tests.InventoryAlertQmlTests.workspace_geometry

    def setUp(self):
        test_inventory.InventoryUiTests.setUp(self)
        self.bundle.preferences.setPreference("reducedMotion", True)
        write_snapshot(comparison_sample(), self.base)

    def test_workspace_entry_investigates_historical_products_without_changing_global_filters(self):
        self.load()
        before = (self.c.state["selection"], self.c.table.rows, self.c.monthly["period"])
        self.click_workspace(self.item("stockPerformanceOpen"))
        dialog = self.item("stockPerformanceDialog")
        self.assertTrue(pump(lambda: dialog.property("opened")))
        performance = self.c.performance
        self.assertTrue(pump(lambda: performance.state["current"] and not performance.state["busy"], 15), performance.state)
        performance.configure("KG", 1, "most", "")
        self.assertTrue(pump(lambda: performance.state["current"] and not performance.state["busy"], 15), performance.state)
        rows = performance.summary["rows"]
        self.assertLessEqual(len(rows), 10)
        self.assertEqual(rows[0]["code"], "D")
        self.assertFalse(any(row.balance.product == "D" for row in self.c.table.rows))
        # The list row is clicked through the popup viewport, not invoked as a
        # controller shortcut. The product has sales but no current position.
        InventoryPerformanceQmlTests.click_dialog(self, self.item("stockPerformanceRow0"))
        self.assertTrue(pump(lambda: performance.detail.get("code") == "D", 15), performance.state)
        self.assertEqual((self.c.state["selection"], self.c.table.rows, self.c.monthly["period"]), before)
        self.assertTrue(self.item("inventoryWorkspace").property("modalOpen"))
        QTest.keyClick(self.window, Qt.Key.Key_Escape)
        self.assertTrue(pump(lambda: not dialog.property("visible")))
        self.assertTrue(pump(lambda: not self.item("inventoryWorkspace").property("modalOpen")))
        self.assertEqual(self.bundle.messages, [])

    geometry = InventoryPerformanceQmlTests.geometry
    ready = InventoryPerformanceQmlTests.ready

    def reveal(self, control):
        dialog = self.item("stockPerformanceDialog")
        if dialog.property("visible"):
            InventoryPerformanceQmlTests.reveal(self, control)
        else:
            alert_tests.InventoryAlertQmlTests.reveal(self, control)
