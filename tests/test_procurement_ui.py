"""Uso dos gráficos com a mesma janela Qt e respostas oficiais capturadas."""

import unittest
from unittest.mock import patch
from liarte_desktop import controller as controller_module
from tests import test_interface, test_comex
from tests.test_qt import APP, settled


class ProcurementUiTests(unittest.TestCase):
    setUp = test_comex.RealQtTests.setUp
    tearDown = test_comex.RealQtTests.tearDown
    item = test_interface.InterfaceTests.item

    def load(self):
        test_comex.RealQtTests.load(self)
        test_comex.click(self.window, self.item("jump_buying"))

    def test_all_metric_choices_are_local_and_preserve_documents_and_filters(self):
        self.load()
        test_comex.click(self.window, self.item("jump_summary"))
        calls = len(self.transport.calls)
        original = self.controller.analysis
        selection = self.controller._selection
        choices = self.item("trendMetric")
        self.assertTrue(choices.isVisible())
        for key in ("value", "price", "fob", "freight", "weight"):
            for index in range(choices.property("count")):
                choices.setProperty("currentIndex", index)
                if choices.property("currentValue") == key:
                    break
            APP.processEvents()
            self.assertEqual(choices.property("currentValue"), key)
            self.assertEqual(
                self.item("monthlyChart").property("unit"),
                original["procurement"]["series"][key]["unit"],
            )
            self.assertTrue(self.controller.state["canExport"])
        self.assertEqual(len(self.transport.calls), calls)
        self.assertEqual(self.controller._selection, selection)
        self.assertEqual(self.controller.analysis, original)
        self.assertEqual(self.bundle.messages, [])

    def test_origin_click_uses_existing_country_filter(self):
        self.load()
        chart = self.item("priceComparison")
        view = self.controller.analysis["procurement"]
        self.assertTrue(view["comparable"])
        self.assertTrue(chart.isVisible())
        first = view["origins"][0]["name"]
        test_comex.click(self.window, self.item("priceOrigin0"))
        settled(self.controller)
        self.assertEqual(self.controller.state["countryValues"], [first])
        self.assertTrue(all(r.country == first for r in self.controller.table.rows))
        self.assertEqual(self.bundle.messages, [])

    def test_municipal_chart_choices_remove_freight_and_keep_fob_basis(self):
        self.load()
        test_comex.click(self.window, self.item("jump_summary"))
        choice = self.item("trendMetric")
        choice.setProperty("currentIndex", 3)
        choice.setProperty("selectedMetricKey", "freight")
        APP.processEvents()
        self.controller.setDataset("municipal")
        settled(self.controller)
        self.assertEqual(choice.property("count"), 4)
        self.assertEqual(choice.property("currentValue"), "value")
        view = self.controller.analysis["procurement"]
        self.assertEqual(view["basis"], "FOB")
        self.assertFalse(self.item("exportPdf").isEnabled())
        self.controller.setDataset("general")
        settled(self.controller)
        self.assertEqual(choice.property("currentValue"), "freight")
        self.assertEqual(self.bundle.messages, [])

    def test_table_search_does_not_change_price_reference(self):
        self.load()
        before = self.controller.analysis["procurement"]
        self.controller.setFilter("search", "Santos")
        settled(self.controller)
        self.assertEqual(self.controller.analysis["procurement"], before)
        self.assertEqual(self.bundle.messages, [])

    def test_price_chart_keeps_missing_values_and_low_prices_distinct(self):
        self.load()
        test_comex.click(self.window, self.item("jump_summary"))
        chart = self.item("monthlyChart")
        chart.setProperty(
            "points",
            [
                {"period": "2026-07", "label": "Julho", "value": 0.008, "movingValue": None},
                {"period": "2026-08", "label": "Agosto", "value": None, "movingValue": None},
                {"period": "2026-09", "label": "Setembro", "value": 0.012, "movingValue": 0.01},
            ],
        )
        APP.processEvents()
        self.assertAlmostEqual(chart.property("maximum"), 0.01344)
        chart.setProperty("hoverIndex", 1)
        self.assertIn("Sem valor", chart.property("hoverText"))
        self.controller.setPreference("reducedMotion", True)
        APP.processEvents()
        self.assertFalse(chart.property("animating"))
        self.assertEqual(self.bundle.messages, [])

    def test_unloaded_interface_has_no_unsupported_negotiation_indicators(self):
        self.assertFalse(self.item("comparisonPanel").isVisible())
        self.assertEqual(self.controller.analysis["procurement"]["origins"], [])
        self.assertEqual(self.bundle.messages, [])

    def test_country_comparator_minimum_weight_is_local_to_chart(self):
        self.load()
        before = self.controller.analysis
        calls = len(self.transport.calls)
        choices = self.item("originMinWeight")
        self.assertEqual(choices.property("currentValue"), "1000")
        for index, limit in ((0, 0), (2, 10000), (3, 50000)):
            choices.setProperty("currentIndex", index)
            APP.processEvents()
            actual = self.item("priceComparison").property("rows").toVariant()
            expected = [r for r in before["procurement"]["origins"] if r["kgValue"] >= limit]
            self.assertEqual(actual, expected)
            self.assertEqual(self.controller.analysis, before)
            self.assertTrue(self.controller.state["canExport"])
        self.assertEqual(len(self.transport.calls), calls)
        self.assertEqual(self.bundle.messages, [])

    def test_paging_sorting_and_table_search_reuse_formatted_analysis(self):
        with patch.object(
            controller_module, "present_procurement", wraps=controller_module.present_procurement
        ) as formatting:
            self.load()
            self.controller.setFilter("search", "China")
            settled(self.controller)
            self.controller.setFilter("search", "")
            settled(self.controller)
            self.controller.setPageSize(25)
            settled(self.controller)
            self.assertEqual(formatting.call_count, 1)
            self.controller.setFilters("country", ["China"])
            settled(self.controller)
            self.assertEqual(formatting.call_count, 2)
        self.assertEqual(self.bundle.messages, [])
