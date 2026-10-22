"""Contratos de uso observáveis; não substituem estudo com usuários da LIARTE."""

from dataclasses import replace
from decimal import Decimal
from threading import Event
import copy
import unittest

from PySide6.QtCore import QMetaObject, Qt
from PySide6.QtTest import QTest
from liarte_core.domain import Period, Selection
from liarte_core.query import DatasetQuery
from liarte_desktop.analytics import present
from tests import test_comex, test_interface
from tests.test_core import record
from tests.test_qt import APP, pump, settled


def variant(value):
    return value.toVariant() if hasattr(value, "toVariant") else value


class DescriptiveTests(unittest.TestCase):
    def test_price_order_uses_exact_ratio_before_formatting(self):
        rows = (
            record(
                0,
                country="A arredondado maior",
                fob_cents=10**30 + 1,
                freight_cents=0,
                insurance_cents=0,
                kg=10**15,
            ),
            record(
                1,
                country="Z exato menor",
                fob_cents=10**30,
                freight_cents=0,
                insurance_cents=0,
                kg=10**15,
            ),
        )
        data = (
            DatasetQuery(rows)
            .query(Selection(Period("2026-04", "2026-04")), Event(), lambda *_: None)
            .procurement
        )
        rows = present(data)["origins"]
        ordered = sorted(rows, key=lambda row: row["priceRank"])
        self.assertEqual(ordered[0]["name"], "Z exato menor")
        self.assertEqual(
            rows[0]["price"], rows[1]["price"]
        )  # Geometry cannot distinguish these; the sort can.

    def test_month_coverage_is_weight_coverage_not_number_of_orders(self):
        rows = (
            record(0, period="2026-01"),
            record(1, period="2026-01"),
            record(2, period="2026-03", kg=0),
        )
        data = (
            DatasetQuery(rows)
            .query(Selection(Period("2026-01", "2026-03")), Event(), lambda *_: None)
            .procurement
        )
        self.assertEqual(data.origins[0].priced_months, 1)
        self.assertEqual(present(data)["origins"][0]["months"], "1/3 meses")
        self.assertEqual(present(data)["series"]["price"]["coverage"], "1/3 meses com valor")
        self.assertEqual(data.total.records, 3)
        self.assertEqual(data.product_label, "Acrilato de etila")

    def test_copy_values_use_full_dollars_and_kg_not_scaled_graph_units(self):
        data = (
            DatasetQuery(
                (record(0, kg=12345, fob_cents=123456789, freight_cents=0, insurance_cents=0),)
            )
            .query(Selection(Period("2026-04", "2026-04")), Event(), lambda *_: None)
            .procurement
        )
        series = present(data)["series"]
        self.assertEqual(series["value"]["unit"], "US$ mi")
        self.assertEqual(series["value"]["tableUnit"], "US$")
        self.assertEqual(series["value"]["points"][0]["tableValue"], "1.234.567,89")
        self.assertEqual(series["weight"]["unit"], "mil kg")
        self.assertEqual(series["weight"]["tableUnit"], "kg")
        self.assertEqual(series["weight"]["points"][0]["tableValue"], "12.345")
        self.assertEqual(series["price"]["tableUnit"], "US$/kg")

    def test_moving_weight_copy_preserves_fractional_monthly_mean(self):
        rows = tuple(record(i, period=f"2026-{i + 1:02d}", kg=100) for i in range(3))
        rows = rows[:-1] + (replace(rows[-1], kg=101),)
        data = (
            DatasetQuery(rows)
            .query(Selection(Period("2026-01", "2026-03")), Event(), lambda *_: None)
            .procurement
        )
        self.assertEqual(present(data)["series"]["weight"]["points"][-1]["tableMoving"], "100,33")


class UsabilityTests(unittest.TestCase):
    setUp = test_comex.RealQtTests.setUp
    tearDown = test_comex.RealQtTests.tearDown
    load = test_comex.RealQtTests.load
    item = test_interface.InterfaceTests.item

    def load_quarter(self):
        original = copy.deepcopy(self.transport.general)
        self.transport.general = []
        for month in ("07", "08", "09"):
            for row in original:
                row = copy.deepcopy(row)
                row["monthNumber"] = month
                self.transport.general.append(row)
        self.controller.queryPeriod("2026-07", "2026-09")
        settled(self.controller)
        self.assertTrue(self.controller.state["loaded"])

    def test_presets_fill_draft_without_network_or_losing_result(self):
        self.load()
        before = self.controller.analysis
        calls = len(self.transport.calls)
        test_comex.click(self.window, self.item("preset3"))
        self.assertEqual(self.controller.state["defaultStart"], "2026-07")
        self.assertEqual(self.controller.state["defaultEnd"], "2026-09")
        self.assertEqual(self.controller.state["appliedStart"], "2026-09")
        self.assertTrue(self.item("draftPeriodNotice").isVisible())
        self.assertFalse(self.item("quickExportButton").isEnabled())
        self.assertEqual(self.controller.analysis, before)
        self.assertEqual(len(self.transport.calls), calls)
        self.assertEqual(self.bundle.messages, [])

    def test_presets_clip_at_first_available_month_and_reject_invalid_counts(self):
        self.controller._limits = Period("2026-08", "2026-09")
        self.controller.setPeriodPreset(12)
        self.assertEqual(self.controller.state["defaultStart"], "2026-08")
        self.assertEqual(self.controller.state["defaultEnd"], "2026-09")
        self.controller.setPeriodPreset(99)
        self.assertEqual(self.controller.state["defaultStart"], "2026-08")
        self.assertEqual(self.transport.calls, [])

    def test_navigation_reaches_existing_sections_and_preserves_filters(self):
        self.load()
        self.controller.setFilters("country", ["China"])
        settled(self.controller)
        calls = len(self.transport.calls)
        before = self.controller.analysis
        self.controller.setPreference("reducedMotion", True)
        test_comex.click(self.window, self.item("jump_records"))
        self.assertTrue(pump(lambda: self.window.property("activeSection") == "records"))
        self.assertGreater(self.item("contentScroll").property("contentY"), 500)
        test_comex.click(self.window, self.item("jump_buying"))
        self.assertTrue(pump(lambda: self.window.property("activeSection") == "buying"))
        test_comex.click(self.window, self.item("jump_summary"))
        self.assertTrue(pump(lambda: self.item("contentScroll").property("contentY") < 20))
        self.assertEqual(self.controller.state["countryValues"], ["China"])
        self.assertEqual(self.controller.analysis, before)
        self.assertEqual(len(self.transport.calls), calls)
        self.assertEqual(self.bundle.messages, [])

    def test_animated_navigation_is_bounded_and_can_be_reduced(self):
        self.load()
        self.controller.setPreference("reducedMotion", False)
        test_comex.click(self.window, self.item("jump_records"))
        animation = self.item("navigationAnimation")
        self.assertTrue(pump(lambda: animation.property("running"), 0.1))
        self.assertTrue(pump(lambda: not animation.property("running"), 1))
        scroll = self.item("contentScroll")
        self.assertLessEqual(
            scroll.property("contentY"), scroll.property("contentHeight") - scroll.height() + 0.1
        )
        self.controller.setPreference("reducedMotion", True)
        test_comex.click(self.window, self.item("jump_summary"))
        self.assertFalse(animation.property("running"))
        self.assertLess(scroll.property("contentY"), 20)
        self.assertEqual(self.bundle.messages, [])

    def test_quick_download_uses_same_save_dialog_and_scope(self):
        self.load()
        self.controller.setFilters("country", ["China"])
        settled(self.controller)
        for name, kind in (
            ("quickExcel", "excel"),
            ("quickPowerBI", "powerbi"),
            ("quickPDF", "pdf"),
        ):
            test_comex.click(self.window, self.item("quickExportButton"))
            menu = self.item("quickExportMenu")
            self.assertTrue(pump(lambda: menu.property("opened")))
            action = self.item(name)
            self.assertIn(
                "período completo" if kind != "pdf" else "filtros aplicados",
                action.property("text"),
            )
            test_comex.native_click(self.window, action)
            self.assertTrue(pump(lambda: self.item("exportDialog").property("visible")))
            self.assertEqual(self.item("exportDialog").property("exportKind"), kind)
            QMetaObject.invokeMethod(self.item("exportDialog"), "close")
            self.assertTrue(pump(lambda: not self.item("exportDialog").property("visible")))
        self.assertEqual(self.controller.state["countryValues"], ["China"])
        self.assertEqual(self.bundle.messages, [])

    def test_quick_menu_municipal_pdf_disabled_and_modal_shortcuts_guarded(self):
        self.load()
        self.controller.setDataset("municipal")
        settled(self.controller)
        calls = len(self.transport.calls)
        test_comex.click(self.window, self.item("quickExportButton"))
        self.assertTrue(pump(lambda: self.item("quickExportMenu").property("opened")))
        self.assertFalse(self.item("quickPDF").isEnabled())
        self.assertTrue(self.window.property("modalOpen"))
        QTest.keyClick(self.window, Qt.Key_F5)
        APP.processEvents()
        self.assertEqual(len(self.transport.calls), calls)
        QTest.keyClick(self.window, Qt.Key_Escape)
        self.assertTrue(pump(lambda: not self.item("quickExportMenu").property("visible")))
        self.assertEqual(self.bundle.messages, [])

    def test_chart_can_be_read_by_keyboard_without_hover(self):
        self.load_quarter()
        chart = self.item("monthlyChart")
        test_comex.click(self.window, chart)
        QTest.keyClick(self.window, Qt.Key_Home)
        APP.processEvents()
        self.assertEqual(chart.property("selectedIndex"), 0)
        self.assertIn("Julho", self.item("trendReadout").property("text"))
        QTest.keyClick(self.window, Qt.Key_Right)
        APP.processEvents()
        self.assertEqual(chart.property("selectedIndex"), 1)
        self.assertIn("Agosto", self.item("trendReadout").property("text"))
        QTest.keyClick(self.window, Qt.Key_End)
        APP.processEvents()
        self.assertEqual(chart.property("selectedIndex"), 2)
        self.assertIn("Setembro", self.item("trendReadout").property("text"))
        self.assertEqual(self.bundle.messages, [])

    def test_price_axis_detail_is_explicit_and_never_changes_values(self):
        self.load_quarter()
        calls = len(self.transport.calls)
        before = self.controller.analysis
        self.item("trendMetric").setProperty("currentIndex", 1)
        APP.processEvents()
        test_comex.click(self.window, self.item("priceScale"))
        chart = self.item("monthlyChart")
        self.assertTrue(chart.property("croppedAxis"))
        self.assertGreater(chart.property("minimum"), 0)
        self.assertTrue(self.item("axisScaleNotice").isVisible())
        for point in variant(chart.property("points")):
            if point["value"] is not None:
                self.assertGreaterEqual(point["value"], chart.property("minimum"))
                self.assertLessEqual(point["value"], chart.property("maximum"))
        self.item("trendMetric").setProperty("currentIndex", 0)
        APP.processEvents()
        self.assertEqual(chart.property("minimum"), 0)
        self.assertFalse(self.item("axisScaleNotice").isVisible())
        self.assertEqual(self.controller.analysis, before)
        self.assertEqual(len(self.transport.calls), calls)
        self.assertEqual(self.bundle.messages, [])

    def test_trend_values_dialog_has_full_units_and_copies_exact_totals(self):
        self.load_quarter()
        test_comex.click(self.window, self.item("openTrendValues"))
        dialog = self.item("trendValuesDialog")
        self.assertTrue(pump(lambda: dialog.property("opened")))
        self.assertTrue(self.item("trendDataRow0").isVisible())
        test_comex.click(self.window, self.item("copyTrendValues"))
        lines = APP.clipboard().text().splitlines()
        self.assertIn("Valor CIF (US$)", lines[0])
        self.assertNotIn("US$ mi", lines[0])
        values = [
            Decimal(line.split("\t")[1].replace(".", "").replace(",", ".")) for line in lines[1:]
        ]
        self.assertEqual(sum(values), Decimal(self.controller._result.totals.value_cents) / 100)
        self.assertEqual(len(lines), 4)
        self.assertTrue(dialog.property("copied"))
        self.assertEqual(self.bundle.messages, [])

    def test_trend_dialog_stays_inside_small_window(self):
        self.load_quarter()
        self.window.resize(500, 400)
        pump(timeout=0.12)
        test_comex.click(self.window, self.item("openTrendValues"))
        dialog = self.item("trendValuesDialog")
        self.assertTrue(pump(lambda: dialog.property("opened")))
        self.assertGreaterEqual(dialog.property("y"), 2)
        self.assertLessEqual(dialog.property("y") + dialog.property("height"), 398)
        self.assertLessEqual(dialog.property("width"), 476)
        self.assertEqual(self.bundle.messages, [])

    def test_comparator_sorts_all_origins_before_eight_row_display(self):
        template = self.transport.general[0]
        self.transport.general = []
        prices = [6, 12, 4, 9, 11, 7, 8, 14, 5, 10, 13, 15]
        for i, price in enumerate(prices):
            row = copy.deepcopy(template)
            row.update(
                country=f"País de teste {i:02d}",
                metricKG=str((i + 1) * 1000),
                metricFOB=str(price * (i + 1) * 1000),
                metricFreight="0",
                metricInsurance="0",
                metricCIF=str(price * (i + 1) * 1000),
            )
            self.transport.general.append(row)
        self.load()
        calls = len(self.transport.calls)
        self.assertEqual(len(self.controller.analysis["procurement"]["origins"]), 12)
        self.assertEqual(len(variant(self.item("priceComparison").property("rows"))), 8)
        self.item("originOrder").setProperty("currentIndex", 1)
        APP.processEvents()
        self.assertEqual(
            variant(self.item("priceComparison").property("rows"))[0]["name"], "País de teste 02"
        )
        test_comex.click(self.window, self.item("moreOrigins"))
        self.assertEqual(len(variant(self.item("priceComparison").property("rows"))), 12)
        self.item("originOrder").setProperty("currentIndex", 2)
        APP.processEvents()
        self.assertEqual(
            variant(self.item("priceComparison").property("rows"))[0]["name"], "País de teste 11"
        )
        self.assertEqual(len(variant(self.item("priceComparison").property("rows"))), 8)
        self.assertEqual(len(self.transport.calls), calls)
        self.assertTrue(self.controller.state["canExport"])
        self.assertEqual(self.bundle.messages, [])

    def test_product_name_remains_readable_in_records(self):
        self.load()
        self.assertIn("Acrilato", self.controller.table.data(self.controller.table.index(0, 1)))
        self.assertEqual(self.bundle.messages, [])

    def test_reduce_motion_stops_navigation_in_progress(self):
        self.load()
        self.controller.setPreference("reducedMotion", False)
        test_comex.click(self.window, self.item("jump_records"))
        animation = self.item("navigationAnimation")
        self.assertTrue(pump(lambda: animation.property("running"), 0.1))
        self.controller.setPreference("reducedMotion", True)
        APP.processEvents()
        self.assertFalse(animation.property("running"))
        self.assertEqual(self.bundle.messages, [])

    def test_action_captions_fit_in_supported_window_sizes(self):
        self.load()
        for width, height in ((500, 400), (900, 700), (1380, 900)):
            self.window.resize(width, height)
            pump(timeout=0.1)
            for name in ("quickExportButton", "openTrendValues", "preset3", "preset6", "preset12"):
                control = self.item(name)
                caption = control.property("text")
                if not caption:
                    continue
                pending = list(control.childItems())
                matched = False
                while pending:
                    child = pending.pop()
                    pending.extend(child.childItems())
                    if child.property("text") == caption:
                        self.assertFalse(
                            child.property("truncated"), (width, name, caption, child.width())
                        )
                        matched = True
                self.assertTrue(matched, name)
        self.assertEqual(self.bundle.messages, [])

    def test_graph_scale_remains_consistent_for_very_small_values(self):
        self.load()
        chart = self.item("monthlyChart")
        chart.setProperty("points", [{"period": "2026-09", "label": "Setembro", "value": 1e-14}])
        APP.processEvents()
        self.assertEqual(chart.property("minimum"), 0)
        self.assertAlmostEqual(chart.property("span") / chart.property("maximum"), 1)
        self.assertGreater(chart.property("maximum"), 1e-14)
        self.assertEqual(self.bundle.messages, [])

    def test_chart_accessibility_exposes_current_value_without_reading_whole_series(self):
        from PySide6.QtGui import QAccessible

        self.load_quarter()
        chart = self.item("monthlyChart")
        test_comex.click(self.window, chart)
        QTest.keyClick(self.window, Qt.Key_Home)
        APP.processEvents()
        interface = QAccessible.queryAccessibleInterface(chart)
        self.assertIsNotNone(interface)
        self.assertIn("Julho", interface.text(QAccessible.Text.Name))
        self.assertIn("Home e End", interface.text(QAccessible.Text.Description))
        self.assertNotIn("Setembro", interface.text(QAccessible.Text.Description))
        self.assertEqual(self.bundle.messages, [])

    def test_empty_filter_intersection_offers_recovery_and_preserves_full_exports(self):
        self.load()
        records = self.provider.snapshot.general_records
        combinations = {(r.country, r.state) for r in records}
        pair = next(
            (country, state)
            for country in {r.country for r in records}
            for state in {r.state for r in records}
            if (country, state) not in combinations
        )
        self.controller.setFilters("country", [pair[0]])
        self.controller.setFilters("state", [pair[1]])
        settled(self.controller)
        self.assertTrue(self.controller.analysis["procurement"]["empty"])
        self.assertTrue(self.item("recoverEmptyFilters").isVisible())
        self.assertFalse(self.item("chooseComparisonProduct").isVisible())
        self.assertFalse(self.item("exportPdf").isEnabled())
        self.assertTrue(self.item("exportExcel").isEnabled())
        self.assertTrue(self.item("exportPowerBI").isEnabled())
        test_comex.click(self.window, self.item("recoverEmptyFilters"))
        settled(self.controller)
        self.assertFalse(self.controller.analysis["procurement"]["empty"])
        self.assertEqual(self.controller.state["filterCount"], 0)
        self.assertEqual(self.bundle.messages, [])

    def test_no_search_results_disable_pdf_but_keep_full_excel_and_bi(self):
        self.load()
        before = self.controller.analysis
        self.controller.setFilter("search", "texto-sem-correspondencia-xyz")
        settled(self.controller)
        self.assertEqual(self.controller.state["tableCount"], "0")
        self.assertFalse(self.item("exportPdf").isEnabled())
        self.assertTrue(self.item("exportExcel").isEnabled())
        self.assertTrue(self.item("exportPowerBI").isEnabled())
        self.assertEqual(self.controller.analysis, before)
        test_comex.click(self.window, self.item("quickExportButton"))
        self.assertTrue(pump(lambda: self.item("quickExportMenu").property("opened")))
        self.assertFalse(self.item("quickPDF").isEnabled())
        self.assertIn("sem registros", self.item("quickPDF").property("text"))
        self.assertEqual(self.bundle.messages, [])
