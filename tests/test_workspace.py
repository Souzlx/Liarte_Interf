"""Regras de leitura e navegação; dados e ordenação continuam no motor original."""

from decimal import Decimal
from fractions import Fraction
from threading import Event
import unittest

from PySide6.QtCore import QMetaObject, QObject, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QAbstractItemModelTester

from liarte_core.domain import Period, Selection
from liarte_core.query import DatasetQuery
from liarte_desktop.analytics import present
from liarte_desktop.table_model import HEADERS, ImportTableModel, cells, port_label
from tests import test_comex, test_interface
from tests.test_core import record
from tests.test_qt import APP, pump, settled


class WorkspaceDataTests(unittest.TestCase):
    def analysis(self, rows, start="2026-01", end="2026-04"):
        return (
            DatasetQuery(rows)
            .query(Selection(Period(start, end)), Event(), lambda *_: None)
            .procurement
        )

    def test_monthly_variation_uses_previous_calendar_month_and_handles_zero(self):
        rows = tuple(
            record(
                i, period=f"2026-{i + 1:02d}", fob_cents=value, freight_cents=0, insurance_cents=0
            )
            for i, value in enumerate((10000, 8000, 0, 20000))
        )
        data = self.analysis(rows)
        before = (data.total, data.months)
        series = present(data)["series"]["valueChange"]
        self.assertEqual([p["value"] for p in series["points"]], [None, -20, -100, None])
        self.assertEqual(series["points"][1]["display"], "-20,0%")
        self.assertEqual(series["points"][3]["display"], "Sem base comparável")
        self.assertEqual(series["tableUnit"], "%")
        self.assertEqual((data.total, data.months), before)

    def test_variation_is_not_computed_from_rounded_millions(self):
        data = self.analysis(
            tuple(
                record(
                    i, period=f"2026-0{i + 1}", fob_cents=value, freight_cents=0, insurance_cents=0
                )
                for i, value in enumerate((100, 101))
            ),
            end="2026-02",
        )
        self.assertEqual(present(data)["series"]["valueChange"]["points"][1]["value"], 1)

    def test_mix_and_missing_weight_are_explicit_without_changing_published_totals(self):
        data = self.analysis(
            (
                record(
                    0, period="2026-01", fob_cents=10000, kg=100, freight_cents=0, insurance_cents=0
                ),
                record(
                    1,
                    period="2026-01",
                    ncm="29161230",
                    product="Acrilato de butila",
                    fob_cents=20000,
                    kg=0,
                    freight_cents=0,
                    insurance_cents=0,
                ),
            )
        )
        view = present(data)
        self.assertTrue(view["isMix"])
        self.assertEqual(view["codeCount"], 2)
        self.assertEqual(view["cards"][0]["label"], "Último mês · CIF/kg")
        self.assertEqual(view["cards"][0]["issue"], "")
        self.assertIn("0 kg na fonte", view["weightWarning"])
        self.assertEqual(data.total.value_cents, 30000)
        self.assertEqual(data.total.unit_price, Decimal(3))

    def test_single_product_keeps_commercial_reference_and_no_mix_warning(self):
        view = present(self.analysis((record(period="2026-01"),)))
        self.assertFalse(view["isMix"])
        self.assertTrue(view["comparable"])
        self.assertEqual(view["weightWarning"], "")
        self.assertEqual(view["cards"][0]["label"], "Último mês · CIF/kg")

    def test_port_label_preserves_code_and_handles_names_that_contain_hyphens(self):
        self.assertEqual(port_label("0817800 - PORTO DE SANTOS"), "PORTO DE SANTOS · 0817800")
        self.assertEqual(port_label("0927800 - ITAJAÍ - SC"), "ITAJAÍ - SC · 0927800")
        self.assertEqual(port_label("ALF - FORTALEZA"), "ALF - FORTALEZA")
        self.assertEqual(port_label("Porto de Santos"), "Porto de Santos")

    def test_profile_is_only_a_projection_and_original_copy_retains_every_column(self):
        model = ImportTableModel()
        tester = QAbstractItemModelTester(
            model, QAbstractItemModelTester.FailureReportingMode.Warning
        )
        row = record(port="0817800 - PORTO DE SANTOS")
        original = cells(row)
        model.replace((row,))
        model.setProfile("buying")
        self.assertEqual(model.columnCount(), 8)
        for column, spec in enumerate(model.viewColumns):
            self.assertEqual(model.headerData(column, Qt.Horizontal), HEADERS[spec["source"]])
            self.assertEqual(
                model.data(model.index(0, column), Qt.ToolTipRole), original[spec["source"]]
            )
        self.assertEqual(model.data(model.index(0, 5)), original[11])
        self.assertEqual(model.data(model.index(0, 0)), "04/2026")
        self.assertEqual(model.data(model.index(0, 6)), "PORTO DE SANTOS · 0817800")
        model.setProfile("full")
        self.assertEqual(model.columnCount(), 12)
        self.assertEqual(model.data(model.index(0, 2)), row.ncm)
        self.assertEqual(model.rows, (row,))
        self.assertEqual(cells(row), original)
        self.assertIsNotNone(tester)


class WorkspaceUiTests(unittest.TestCase):
    setUp = test_comex.RealQtTests.setUp
    tearDown = test_comex.RealQtTests.tearDown
    load = test_comex.RealQtTests.load
    item = test_interface.InterfaceTests.item

    def test_price_header_sorts_by_exact_price_not_by_visual_column_index(self):
        self.load()
        test_comex.click(self.window, self.item("jump_records"))
        table = self.item("recordsTable")
        self.assertTrue(pump(lambda: table.isVisible() and table.width() > 0))
        widths = self.controller.table.viewColumns
        table.setProperty("contentX", max(0, sum(item["width"] + 1 for item in widths[:5]) - table.width() / 2))
        self.assertFalse(self.window.grabWindow().isNull())
        self.assertEqual(self.controller.table.viewColumns[5]["source"], 11)
        test_comex.click(self.window, self.item("tableHeader5"))
        settled(self.controller)
        self.assertEqual(self.controller.state["sortColumn"], 11)
        prices = [Fraction(r.cif_cents, r.kg) for r in self.controller.table.rows if r.kg]
        self.assertEqual(prices, sorted(prices, reverse=True))
        self.assertEqual(self.bundle.messages, [])

    def test_column_profile_preserves_selection_and_does_not_query_or_filter_data(self):
        self.load()
        self.controller.selectRow(0)
        state = self.controller.state
        rows = self.controller.table.rows
        analysis = self.controller.analysis
        calls = len(self.transport.calls)
        choices = self.item("tableProfile")
        for index, count in ((1, 12), (0, 8), (1, 12)):
            choices.setProperty("currentIndex", index)
            APP.processEvents()
            self.assertEqual(self.controller.table.columnCount(), count)
            self.assertEqual(self.controller.table.rows, rows)
            self.assertEqual(self.controller.state, state)
            self.assertEqual(self.controller.analysis, analysis)
        self.controller.copySelected()
        copied = QGuiApplication.clipboard().text()
        self.assertIn("Seguro (US$)", copied)
        self.assertIn(rows[0].ncm, copied)
        self.assertEqual(len(self.transport.calls), calls)
        self.assertEqual(self.bundle.messages, [])

    def test_municipal_profile_keeps_fob_basis_and_price_mapping_after_switch(self):
        self.load()
        self.controller.setDataset("municipal")
        settled(self.controller)
        model = self.controller.table
        self.assertEqual(model.columnCount(), 8)
        self.assertEqual(model.viewColumns[6]["source"], 8)
        self.assertEqual(model.headerData(6, Qt.Horizontal), "US$/kg FOB")
        self.assertEqual(model.data(model.index(0, 6)), cells(model.rows[0])[8])
        self.item("tableProfile").setProperty("currentIndex", 1)
        APP.processEvents()
        self.assertEqual(model.columnCount(), 9)
        self.assertEqual(model.headerData(4, Qt.Horizontal), "Descrição SH4")
        self.controller.setDataset("general")
        settled(self.controller)
        self.assertEqual(model.columnCount(), 12)
        self.assertEqual(self.bundle.messages, [])

    def test_collapsing_filters_keeps_active_criteria_and_product_action_reopens_them(self):
        self.load()
        self.controller.setFilters("country", ["China"])
        settled(self.controller)
        before = self.controller.analysis
        collapsed_height = self.item("filterPanel").height()
        test_comex.click(self.window, self.item("toggleFilters"))
        self.assertTrue(pump(lambda: self.item("productFilter").isVisible()))
        previous = None

        def expanded_layout_is_stable():
            nonlocal previous
            image = self.window.grabWindow()
            height = self.item("filterPanel").height()
            stable = height == previous
            previous = height
            return stable and height > collapsed_height and not image.isNull()

        self.assertTrue(pump(expanded_layout_is_stable))
        height = self.item("filterPanel").height()
        test_comex.click(self.window, self.item("toggleFilters"))
        APP.processEvents()
        self.assertFalse(self.item("productFilter").isVisible())
        self.assertTrue(self.item("activeFilter_country").isVisible())
        self.assertTrue(pump(lambda: self.item("filterPanel").height() < height))
        self.assertEqual(self.controller.state["countryValues"], ["China"])
        self.assertEqual(self.controller.analysis, before)
        QMetaObject.invokeMethod(self.window, "chooseProduct")
        popup = self.item("productFilterPopup")
        self.assertTrue(pump(lambda: popup.property("opened")))
        self.assertTrue(self.item("productFilter").isVisible())
        QMetaObject.invokeMethod(popup, "close")
        self.assertEqual(self.bundle.messages, [])

    def test_methodology_is_optional_and_weight_issue_is_local_to_the_metric(self):
        self.transport.general[0]["metricKG"] = "0"
        self.load()
        self.assertTrue(self.controller.analysis["procurement"]["weightWarning"])
        self.assertIsNone(self.window.findChild(QObject, "buyingPriceContext"))
        self.assertIsNone(self.window.findChild(QObject, "summaryPriceContext"))
        self.assertTrue(self.item("metricCard2").property("issue"))
        self.assertTrue(self.item("buyingMetric0").property("issue"))
        test_comex.click(self.window, self.item("toggleMethodology"))
        self.assertTrue(self.window.property("methodologyExpanded"))
        test_comex.click(self.window, self.item("toggleMethodology"))
        self.assertFalse(self.window.property("methodologyExpanded"))
        self.assertEqual(self.bundle.messages, [])

    def test_variation_chart_supports_declines_and_copy_uses_percent_units(self):
        self.load()
        choice = self.item("trendMetric")
        choice.setProperty("currentIndex", choice.property("count") - 1)
        APP.processEvents()
        self.assertEqual(choice.property("currentValue"), "valueChange")
        chart = self.item("monthlyChart")
        self.assertTrue(chart.property("allowNegative"))
        chart.setProperty(
            "points",
            [
                {"period": "2026-07", "label": "Julho", "value": None},
                {"period": "2026-08", "label": "Agosto", "value": -20},
                {"period": "2026-09", "label": "Setembro", "value": 10},
            ],
        )
        APP.processEvents()
        self.assertLess(chart.property("minimum"), -20)
        self.assertGreater(chart.property("maximum"), 10)
        self.assertFalse(chart.property("croppedAxis"))
        self.assertTrue(self.controller.copyTrendData("valueChange"))
        self.assertIn("Variação do valor CIF (%)", QGuiApplication.clipboard().text())
        self.assertTrue(
            all(
                len(line.split("\t")) == 2
                for line in QGuiApplication.clipboard().text().splitlines()
            )
        )
        self.assertEqual(self.bundle.messages, [])

    def test_export_status_is_short_and_pdf_remains_silent(self):
        self.controller._export_succeeded({"path": "a.xlsx", "name": "a.xlsx", "format": "excel"})
        self.assertEqual(self.controller.state["exportMessage"], "")
        self.controller._export_succeeded({"path": "b.zip", "name": "b.zip", "format": "powerbi"})
        self.assertEqual(self.controller.state["exportMessage"], "")
        self.controller._export_succeeded({"path": "c.pdf", "name": "c.pdf", "format": "pdf"})
        self.assertEqual(self.controller.state["exportMessage"], "")
