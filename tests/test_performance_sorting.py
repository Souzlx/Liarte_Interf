"""Product-list orders use numeric summaries and keep missing facts distinct."""

from threading import Event
import unittest
from unittest.mock import patch

from PySide6.QtCore import QPointF, Qt

from liarte_desktop import inventory_performance as desktop
from tests import test_inventory_performance_qml as qml
from tests import test_inventory_performance_ui as performance
from tests.test_qt import pump


def row(code, *, unit="KG", **values):
    return {
        "code": code, "name": "Produto " + code, "unit": unit, "sold": 0,
        "previous": 0, "change": 0, "stockQuantity": 0, "stockCost": 0,
        "turnover": None, "coverage": None, **values,
    }


def ordered(rows, field, direction):
    result, _ = desktop._list_rows(
        {"rows": tuple(rows)}, "KG", f"metric:{field}:{direction}", "", Event(),
    )
    return [item["code"] for item in result]


class ProductPerformanceSortingTests(unittest.TestCase):
    setUp = performance.InventoryPerformanceUiTests.setUp
    idle = performance.InventoryPerformanceUiTests.idle
    load = performance.InventoryPerformanceUiTests.load
    configure = performance.InventoryPerformanceUiTests.configure

    def test_turnover_numeric_order_keeps_zero_and_stable_ties_before_unknown_or_invalid(self):
        rows = [
            row("TEN", turnover=10), row("TWO_B", turnover=2),
            row("ZERO", turnover=0), row("TWO_A", turnover=2),
            row("MISSING"), row("INVALID", turnover=-1),
            row("NAN", turnover=float("nan")), row("LITROS", unit="L", turnover=1000),
        ]
        self.assertEqual(ordered(rows, "turnover", "asc"), [
            "ZERO", "TWO_A", "TWO_B", "TEN", "INVALID", "MISSING", "NAN",
        ])
        self.assertEqual(ordered(rows, "turnover", "desc"), [
            "TEN", "TWO_A", "TWO_B", "ZERO", "INVALID", "MISSING", "NAN",
        ])
        self.assertEqual(rows[5]["turnover"], -1)

    def test_capital_and_balance_sort_numbers_and_keep_legitimate_negative_values(self):
        for field in ("stockCost", "stockQuantity"):
            with self.subTest(field=field):
                rows = [row("TEN", **{field: 10}), row("TWO", **{field: 2}),
                        row("ZERO", **{field: 0}), row("NEGATIVE", **{field: -5}),
                        row("UNKNOWN", **{field: None})]
                self.assertEqual(ordered(rows, field, "asc"), ["NEGATIVE", "ZERO", "TWO", "TEN", "UNKNOWN"])
                self.assertEqual(ordered(rows, field, "desc"), ["TEN", "TWO", "ZERO", "NEGATIVE", "UNKNOWN"])

    def test_coverage_unknown_or_ineligible_is_last_in_both_directions(self):
        rows = [row("SHORT", coverage=2), row("LONG", coverage=10),
                row("ZERO", coverage=0), row("ABSENT"), row("INVALID", coverage=-1)]
        self.assertEqual(ordered(rows, "coverage", "asc"), ["ZERO", "SHORT", "LONG", "ABSENT", "INVALID"])
        self.assertEqual(ordered(rows, "coverage", "desc"), ["LONG", "SHORT", "ZERO", "ABSENT", "INVALID"])

    def test_capital_order_preserves_exact_large_integer_differences(self):
        huge = 10 ** 400
        rows = [row("B", stockCost=huge), row("A", stockCost=huge + 1)]
        self.assertEqual(ordered(rows, "stockCost", "asc"), ["B", "A"])
        self.assertEqual(ordered(rows, "stockCost", "desc"), ["A", "B"])

    def test_sorting_all_pages_uses_cache_and_does_not_treat_missing_closing_as_low_giro(self):
        self.load()
        self.configure()
        report = self.c.report
        self.c.setPage(2)
        self.idle()
        with patch.object(desktop, "analyze_product_performance", side_effect=AssertionError("Sort reanalysis")):
            self.configure(sort="metric:turnover:asc")
            self.assertIs(self.c.report, report)
            self.assertEqual(self.c.state["page"], 1)
            self.assertEqual(self.c.state["count"], 26)
            self.assertEqual(self.c.summary["rows"][0]["code"], "P001")
            self.assertEqual(self.c.summary["rows"][0]["sortValue"], "0,10 x/mês")
            self.configure(sort="metric:turnover:desc")
            self.assertEqual(self.c.summary["rows"][0]["code"], "P025")
            self.c.setPage(3)
            self.idle()
            self.assertEqual(self.c.summary["rows"][-1]["code"], "OLD")
            self.assertEqual(self.c.summary["rows"][-1]["sortValue"], "Sem giro elegível")

    def test_pure_order_change_preserves_investigation_identity_without_rebuilding_detail(self):
        self.load()
        self.configure(sort="metric:turnover:asc")
        self.c.investigate("P001", "KG")
        self.idle()
        detail, raw = self.c.detail, self.c._raw_detail
        with (
            patch.object(desktop, "analyze_product_performance", side_effect=AssertionError("Sort reanalysis")),
            patch.object(desktop, "product_performance_detail", side_effect=AssertionError("Detail rebuild")),
        ):
            self.configure(sort="metric:turnover:desc")
        self.assertIs(self.c.detail, detail)
        self.assertIs(self.c._raw_detail, raw)
        self.assertEqual(self.c.detail["code"], "P001")
        self.assertEqual(self.c.summary["rows"][0]["code"], "P025")

    def test_applied_capital_and_coverage_expose_the_ordered_value_instead_of_unrelated_sales(self):
        self.load()
        self.configure(sort="metric:stockCost:desc")
        presented = self.c.summary["rows"][0]
        self.assertEqual(presented["sortLabel"], "Estoque a custo no fechamento")
        self.assertEqual(presented["sortValue"], "R$ 100,00")
        self.assertIn("Maior primeiro", self.c.summary["orderLabel"])
        self.configure(sort="metric:coverage:asc")
        self.assertEqual(self.c.summary["rows"][0]["sortLabel"], "Cobertura estimada")
        self.assertTrue(self.c.summary["rows"][0]["sortValue"].endswith(" dias"))

    def test_product_name_order_is_alphabetical_with_consistent_identity_ties(self):
        rows = [row("A", name="Resina"), row("Z", name="Ácido"), row("M", name="acido")]
        self.assertEqual(ordered(rows, "name", "asc"), ["M", "Z", "A"])
        self.assertEqual(ordered(rows, "name", "desc"), ["A", "M", "Z"])
        legacy, _ = desktop._list_rows({"rows": rows}, "KG", "all", "", Event())
        self.assertEqual([item["code"] for item in legacy], ["A", "M", "Z"])
        summary, _ = desktop._summary({
            "reason": "Histórico insuficiente. Mês parcial excluído.",
            "notice": "Mês parcial excluído. Janelas com 30 dias de calendário.",
        }, (), 1, Event())
        self.assertEqual(summary["reason"], "Histórico insuficiente. Mês parcial excluído.")
        self.assertEqual(summary["notice"], "Janelas com 30 dias de calendário.")


class ProductPerformanceSortingQmlTests(unittest.TestCase):
    setUp = qml.InventoryPerformanceQmlTests.setUp
    tearDown = qml.InventoryPerformanceQmlTests.tearDown
    item = qml.InventoryPerformanceQmlTests.item
    open = qml.InventoryPerformanceQmlTests.open
    geometry = qml.InventoryPerformanceQmlTests.geometry
    reveal = qml.InventoryPerformanceQmlTests.reveal
    ready = qml.InventoryPerformanceQmlTests.ready
    click_dialog = qml.InventoryPerformanceQmlTests.click_dialog
    select_combo = qml.InventoryPerformanceQmlTests.select_combo

    def test_metric_and_direction_are_drafts_until_apply_and_chosen_value_is_visible(self):
        self.open()
        self.select_combo("stockPerformanceSort", "stockCost")
        self.assertEqual(self.fixture.calls, [])
        direction = self.item("stockPerformanceDirection")
        self.assertTrue(direction.isEnabled())
        self.assertEqual(direction.property("text"), "Maior primeiro")
        self.click_dialog(direction)
        self.assertEqual(direction.property("text"), "Menor primeiro")
        self.assertEqual(self.fixture.calls, [])
        self.fixture._all_rows[0].update(
            sortField="stockCost", sortLabel="Estoque a custo no fechamento", sortValue="R$ 1.234,56",
        )
        self.click_dialog(self.item("stockPerformanceApply"))
        self.assertEqual(self.fixture.calls, [("configure", "KG", 3, "metric:stockCost:asc", "")])
        self.assertIn("R$ 1.234,56", self.item("stockPerformanceRow0Value").property("text"))
        self.assertIn("Estoque a custo", self.item("stockPerformanceRow0Value").property("text"))
        self.assertEqual(self.messages, [])

    def test_all_products_choice_applies_name_order_without_relabeling_legacy_code_order(self):
        self.open()
        self.select_combo("stockPerformanceSort", "all")
        direction = self.item("stockPerformanceDirection")
        self.assertTrue(direction.isVisible())
        self.assertEqual(direction.property("text"), "A–Z")
        self.assertEqual(self.fixture.calls, [])
        self.click_dialog(self.item("stockPerformanceApply"))
        self.assertEqual(self.fixture.calls, [("configure", "KG", 3, "metric:name:asc", "")])
        self.fixture.configure("KG", 3, "all", "")
        self.assertFalse(direction.isVisible())
        self.assertFalse(direction.isEnabled())
        self.assertEqual(direction.property("text"), "Código crescente")
        self.fixture._summary.update(
            reason="Mês parcial excluído.", notice="Janelas com 30 dias de calendário.",
        )
        self.fixture.changed.emit()
        reason = self.item("stockPerformanceReason")
        context = self.item("stockPerformanceContext")
        self.assertEqual(reason.property("text"), "Mês parcial excluído.")
        self.assertTrue(reason.isVisible())
        self.assertFalse(context.isVisible())
        toggle = self.item("stockPerformanceContextToggle")
        self.click_dialog(toggle)
        self.assertTrue(context.isVisible())
        self.assertIn(self.fixture.summary["scope"], context.property("text"))
        self.assertIn("Janelas com 30 dias", context.property("text"))
        self.assertTrue(reason.isVisible())
        self.click_dialog(toggle)
        self.assertFalse(context.isVisible())
        self.assertTrue(reason.isVisible())
        self.assertEqual(self.messages, [])

    def test_direction_respects_special_rankings_and_fits_compact_window_with_wide_font(self):
        dialog = self.open()
        self.select_combo("stockPerformanceSort", "decline")
        direction = self.item("stockPerformanceDirection")
        self.assertFalse(direction.isEnabled())
        self.select_combo("stockPerformanceSort", "turnover")
        self.assertTrue(direction.isEnabled())
        font = direction.property("font")
        font.setStretch(200)
        direction.setProperty("font", font)
        for width, height in ((900, 700), (500, 400)):
            with self.subTest(width=width):
                self.window.resize(width, height)
                self.ready(direction)
                direction.forceActiveFocus(Qt.FocusReason.TabFocusReason)
                viewport = dialog.property("bodyViewport")
                self.assertTrue(pump(direction.hasActiveFocus))
                point = direction.mapToItem(viewport, QPointF())
                self.assertGreaterEqual(point.x(), -1)
                self.assertLessEqual(point.x() + direction.width(), viewport.width() + 1)
                self.assertGreaterEqual(point.y(), -1)
                self.assertLessEqual(point.y() + direction.height(), viewport.height() + 1)
        self.assertEqual(self.messages, [])

    def test_return_to_reordered_list_focuses_the_investigated_product_identity(self):
        self.open()
        self.click_dialog(self.item("stockPerformanceRow0"))
        self.assertEqual(self.fixture.detail["code"], "P00")
        rows = self.fixture._all_rows
        rows[0], rows[1] = rows[1], rows[0]
        self.fixture.configure("KG", 3, "metric:name:desc", "")
        self.assertEqual(self.fixture.detail["code"], "P00")
        self.click_dialog(self.item("stockPerformanceBack"))
        self.assertTrue(pump(lambda: self.item("stockPerformanceRow1").hasActiveFocus()))
        self.assertFalse(self.item("stockPerformanceRow0").hasActiveFocus())
        self.assertEqual(self.messages, [])
