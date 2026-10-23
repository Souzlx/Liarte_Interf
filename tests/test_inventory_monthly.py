"""Contratos mensais com históricos que diferem do saldo atual."""

from dataclasses import replace
from datetime import date
import unittest

from liarte_core.inventory import (
    SCALE,
    Balance,
    Closing,
    InventoryData,
    Product,
    Sale,
    StockSelection,
    analyze_inventory,
)
from liarte_core.inventory_monthly import analyze_monthly_inventory


def monthly_sample():
    return InventoryData(
        date(2026, 4, 15),
        "Análise mensal sintética.pbix",
        "a" * 64,
        (
            Product("A", "Ácido", "Químicos", "PA", "KG"),
            Product("B", "Solvente", "Químicos", "MP", "L"),
            Product("C", "Produto histórico", "Químicos", "PA", "KG"),
            Product("D", "Produto esgotado", "Químicos", "PA", "KG"),
            Product("E", "Embalagem", "Embalagens", "EM", "UN"),
        ),
        (
            Balance("A", "01", "01", "KG", 80 * SCALE, 8000),
            Balance("A", "01", "02", "KG", 20 * SCALE, 2000),
            Balance("B", "01", "01", "L", 30 * SCALE, 3000),
            Balance("E", "01", "01", "UN", 12 * SCALE, 1200),
        ),
        (
            Closing("A", "01", "01", "KG", "2026-01", 100 * SCALE, 10000, 1, 30),
            Closing("A", "01", "02", "KG", "2026-01", 50 * SCALE, 5000, 3, 10),
            Closing("B", "01", "01", "L", "2026-01", 20 * SCALE, 2000, -2, -15),
            Closing("C", "01", "01", "KG", "2026-01", 10 * SCALE, 1000, 0, None),
            Closing("A", "01", "01", "KG", "2026-02", 120 * SCALE, 15000, 2, 14),
            Closing("A", "01", "02", "KG", "2026-02", 50 * SCALE, 5500, 4, 7),
            Closing("B", "01", "01", "L", "2026-02", 25 * SCALE, 2500, None, None),
            Closing("E", "01", "01", "UN", "2026-02", 5 * SCALE, 600, None, None),
        ),
        (
            Sale("A", "01", "KG", date(2026, 1, 1), 10 * SCALE, 1000),
            Sale("A", "01", "KG", date(2026, 2, 5), 20 * SCALE, 2000),
            Sale("A", "01", "KG", date(2026, 3, 5), 40 * SCALE, 4000),
            Sale("B", "01", "L", date(2026, 1, 1), 4 * SCALE, 400),
            Sale("B", "01", "L", date(2026, 2, 1), 7 * SCALE, 700),
            Sale("C", "01", "KG", date(2026, 1, 2), SCALE, 100),
            Sale("D", "03", "KG", date(2026, 2, 6), 200 * SCALE, 20000),
        ),
    )


def months(data=None, **filters):
    return analyze_monthly_inventory(
        data or monthly_sample(), StockSelection("2026-01", "2026-02", **filters)
    )


class InventoryMonthlyTests(unittest.TestCase):
    def test_historical_and_sold_out_products_do_not_require_a_current_balance(self):
        january, february = months()
        self.assertIn("C", {row["code"] for row in january["stockRows"]})
        self.assertEqual(february["sellersByUnit"]["KG"][0]["code"], "D")
        self.assertEqual(february["sellersByUnit"]["KG"][0]["value"], 200 * SCALE)
        self.assertIn("03", february["salesScope"])
        self.assertNotIn("03", february["scope"])

    def test_sales_are_counted_once_despite_two_stock_warehouses(self):
        january, february = months(product="A")
        self.assertEqual(january["stockQuantity"]["KG"], 150 * SCALE)
        self.assertEqual(january["salesQuantity"]["KG"], 10 * SCALE)
        self.assertEqual(february["salesQuantity"]["KG"], 20 * SCALE)
        self.assertEqual(len(february["saleRows"]), 1)
        self.assertEqual(february["salesChangesByUnit"]["KG"][0]["value"], 10 * SCALE)

    def test_warehouse_sales_are_unavailable_instead_of_assigned_to_that_location(self):
        january, february = months(warehouse="01")
        self.assertIsNone(february["salesQuantity"]["KG"])
        self.assertEqual(february["saleRows"], [])
        self.assertEqual(february["sellersByUnit"]["KG"], [])
        self.assertIsNone(february["salesChange"]["KG"])
        self.assertIn("Retire", february["salesComparison"])
        self.assertEqual(january["stockQuantity"]["KG"], 110 * SCALE)
        a = next(row for row in february["slow"] if row["code"] == "A")
        self.assertEqual(a["lastSale"], "2026-02-05")
        self.assertIn("última venda abaixo é da filial", february["notice"])

    def test_units_remain_separate_in_all_quantity_metrics_and_rankings(self):
        january, february = months()
        self.assertEqual(january["stockQuantity"]["KG"], 160 * SCALE)
        self.assertEqual(january["stockQuantity"]["L"], 20 * SCALE)
        self.assertIsNone(january["stockQuantity"]["UN"])
        self.assertEqual(february["salesQuantity"]["KG"], 220 * SCALE)
        self.assertEqual(february["salesQuantity"]["L"], 7 * SCALE)
        self.assertEqual(february["salesQuantity"]["UN"], 0)
        self.assertEqual({r["code"] for r in february["sellersByUnit"]["L"]}, {"B"})
        self.assertEqual(set(months(unit="L")[0]["salesQuantity"]), {"L"})

    def test_historical_recency_never_reads_a_later_sale_or_uses_source_days_as_age(self):
        january, february = months()
        a = next(row for row in january["slow"] if row["code"] == "A")
        self.assertEqual(a["lastSale"], "2026-01-01")
        self.assertEqual(a["daysSinceSale"], 30)
        a = next(row for row in february["slow"] if row["code"] == "A")
        self.assertEqual(a["lastSale"], "2026-02-05")
        self.assertEqual(a["daysSinceSale"], 23)
        e = next(row for row in february["slow"] if row["code"] == "E")
        self.assertIsNone(e["daysSinceSale"])
        self.assertEqual(e["display"], "Sem venda registrada")
        self.assertIn("não é idade", january["notice"])

    def test_positive_sale_marker_survives_net_returns_for_last_sale(self):
        data = monthly_sample()
        data = replace(
            data,
            sales=data.sales + (Sale("A", "01", "KG", date(2026, 2, 20), -SCALE, -100, True),),
        )
        february = months(data, product="A")[1]
        self.assertEqual(february["salesQuantity"]["KG"], 19 * SCALE)
        self.assertEqual(february["slow"][0]["lastSale"], "2026-02-20")
        self.assertEqual(february["slow"][0]["daysSinceSale"], 8)

    def test_stock_comparison_separates_matched_changes_from_coverage_changes(self):
        january, february = months()
        self.assertEqual(january["stockCost"], 18000)
        self.assertEqual(february["stockCost"], 23600)
        self.assertEqual(february["stockChange"], 5600)
        self.assertEqual(february["matchedStockChange"], 6000)
        self.assertEqual(sum(row["value"] for row in february["changes"]), 6000)
        self.assertEqual(
            {r["code"]: r["value"] for r in february["changes"]}, {"A": 5500, "B": 500}
        )
        self.assertEqual(february["newPositionCount"], 1)
        self.assertEqual(february["missingPositionCount"], 1)
        self.assertEqual(february["newPositionCost"], 600)
        self.assertEqual(february["missingPositionCost"], 1000)
        self.assertEqual(
            february["stockChange"],
            february["matchedStockChange"]
            + february["newPositionCost"]
            - february["missingPositionCost"],
        )
        self.assertNotIn("E", {r["code"] for r in february["changes"]})
        self.assertNotIn("C", {r["code"] for r in february["changes"]})
        self.assertIn("não comprovam", february["comparison"])

    def test_missing_previous_calendar_month_never_becomes_zero_or_is_bridged(self):
        data = monthly_sample()
        march = tuple(replace(c, period="2026-03") for c in data.closings if c.period == "2026-02")
        data = replace(
            data, closings=tuple(c for c in data.closings if c.period != "2026-02") + march
        )
        january, february, march = analyze_monthly_inventory(
            data, StockSelection("2026-01", "2026-03")
        )
        self.assertIsNone(february["stockCost"])
        self.assertIsNone(march["stockChange"])
        self.assertEqual(march["changes"], [])
        self.assertEqual(march["previousLabel"], "02/2026")
        # Sales in a fully observed month may genuinely be zero.
        self.assertEqual(february["salesQuantity"]["UN"], 0)

    def test_partial_and_unobserved_sales_months_are_never_comparable(self):
        data = replace(monthly_sample(), sales=monthly_sample().sales[1:])
        december, january, february, march, april, may = analyze_monthly_inventory(
            data, StockSelection("2025-12", "2026-05")
        )
        self.assertIsNone(december["salesQuantity"]["KG"])
        self.assertFalse(december["salesObserved"])
        # Other source transactions on 01/01 preserve complete global January.
        self.assertFalse(january["partial"])
        self.assertIsNotNone(february["salesChange"]["KG"])
        self.assertTrue(april["partial"])
        self.assertIsNone(april["salesChange"]["KG"])
        self.assertIn("parcial", april["salesComparison"])
        self.assertIsNone(may["salesQuantity"]["KG"])
        self.assertEqual(may["saleRows"], [])

    def test_first_observation_in_middle_of_month_disables_comparison(self):
        data = monthly_sample()
        data = replace(data, sales=tuple(s for s in data.sales if s.day >= date(2026, 1, 2)))
        january, february = months(data)
        self.assertTrue(january["partial"])
        self.assertFalse(february["partial"])
        self.assertIsNone(february["salesChange"]["KG"])
        self.assertEqual(february["salesChangesByUnit"]["KG"], [])

    def test_giro_is_source_median_of_positive_positions_not_sum_or_current_balance(self):
        january, february = months()
        self.assertEqual(january["turnover"], 1)
        self.assertEqual(january["turnoverCount"], 3)
        self.assertEqual(january["turnoverInvalidCount"], 1)
        self.assertEqual(february["turnover"], 3)
        self.assertEqual(february["turnoverCount"], 2)
        self.assertEqual(january["productCount"], 3)

    def test_derived_filters_explicitly_use_current_cohort_and_allow_precomputed_analysis(self):
        data = monthly_sample()
        selected = StockSelection("2026-01", "2026-02", balance="positive")
        analysis = analyze_inventory(data, selected)
        january, february = analyze_monthly_inventory(data, selected, analysis)
        self.assertNotIn("C", {r["code"] for r in january["stockRows"]})
        self.assertNotIn("D", {r["code"] for r in february["saleRows"]})
        self.assertIn("situação atual", february["notice"])
        self.assertEqual(february["salesQuantity"]["KG"], 20 * SCALE)

    def test_primary_filters_include_historical_units_and_sales_only_branches(self):
        january, february = months(branch="03")
        self.assertIsNone(january["stockCost"])
        self.assertEqual(february["salesQuantity"]["KG"], 200 * SCALE)
        self.assertEqual({r["code"] for r in february["saleRows"]}, {"D"})
        january, february = months(search="acido", kind="PA", group="Químicos")
        self.assertEqual({r["code"] for r in january["stockRows"]}, {"A"})
        self.assertEqual(february["salesQuantity"]["KG"], 20 * SCALE)

    def test_negative_contributors_and_net_sales_returns_keep_their_sign(self):
        data = monthly_sample()
        data = replace(
            data,
            closings=tuple(
                replace(c, cost=2000) if c.period == "2026-02" and c.product == "A" else c
                for c in data.closings
            ),
            sales=data.sales + (Sale("C", "01", "KG", date(2026, 2, 7), -3 * SCALE, -300),),
        )
        february = months(data)[1]
        stock_a = next(row for row in february["changes"] if row["code"] == "A")
        sales_c = next(row for row in february["salesChangesByUnit"]["KG"] if row["code"] == "C")
        self.assertEqual(stock_a["value"], -11000)
        self.assertIn("−R$", stock_a["display"])
        self.assertEqual(sales_c["value"], -4 * SCALE)
        self.assertIn("-4,000 KG", sales_c["display"])
        self.assertNotIn("C", {row["code"] for row in february["sellersByUnit"]["KG"]})

    def test_empty_sales_source_is_missing_instead_of_fictitious_zero_demand(self):
        january, february = months(replace(monthly_sample(), sales=()))
        self.assertIsNone(january["salesQuantity"]["KG"])
        self.assertFalse(february["salesObserved"])
        self.assertTrue(all(row["daysSinceSale"] is None for row in february["slow"]))

    def test_stock_rows_preserve_source_indicators_and_branch_last_sale_for_export(self):
        january, february = months()
        b = next(row for row in january["stockRows"] if row["code"] == "B")
        self.assertEqual(b["turnover"], -2)
        self.assertEqual(b["days"], -15)
        self.assertEqual(b["lastSale"], "2026-01-01")
        self.assertEqual(b["daysSinceSale"], 30)
        self.assertEqual(b["lastSaleScope"], "filial")
        self.assertEqual(len(february["stockRows"]), 4)

    def test_partial_stock_closing_is_identified_and_not_compared_to_full_month(self):
        data = replace(monthly_sample(), as_of=date(2026, 2, 15))
        january, february = months(data)
        self.assertFalse(january["stockPartial"])
        self.assertTrue(february["stockPartial"])
        self.assertIsNotNone(february["stockCost"])
        self.assertIsNone(february["stockChange"])
        self.assertEqual(february["changes"], [])
        self.assertIn("fechamento deste mês é parcial", february["notice"])

    def test_stock_contributors_require_same_position_not_merely_same_product(self):
        data = monthly_sample()
        data = replace(
            data,
            closings=tuple(
                replace(c, warehouse="03") if c.period == "2026-02" and c.product == "A" else c
                for c in data.closings
                if c.product != "A" or c.warehouse == "01"
            ),
        )
        february = months(data)[1]
        self.assertNotIn("A", {row["code"] for row in february["changes"]})
        self.assertEqual(february["matchedStockChange"], 500)
        self.assertEqual(february["newPositionCount"], 2)
        self.assertEqual(february["missingPositionCount"], 2)

    def test_nonpositive_stock_positions_do_not_enter_turnover_median(self):
        data = monthly_sample()
        data = replace(
            data,
            closings=data.closings
            + (
                Closing("E", "01", "02", "UN", "2026-01", 0, 0, 1000, 0),
                Closing("D", "01", "01", "KG", "2026-01", -SCALE, -100, -200, -1),
            ),
        )
        january = months(data)[0]
        self.assertEqual(january["turnover"], 1)
        self.assertEqual(january["turnoverCount"], 3)
        self.assertEqual(january["turnoverInvalidCount"], 1)
        self.assertNotIn("D", {row["code"] for row in january["slow"]})

    def test_unknown_product_count_is_distinct_from_observed_zero_positive_products(self):
        data = monthly_sample()
        data = replace(
            data,
            closings=(Closing("A", "01", "01", "KG", "2026-01", 0, 0, 0, None),),
        )
        january, february = months(data)
        self.assertEqual(january["productCount"], 0)
        self.assertEqual(january["stockCost"], 0)
        self.assertIsNone(february["productCount"])
        self.assertIsNone(february["stockCost"])

    def test_low_turnover_ranks_source_positions_and_preserves_unit_and_location(self):
        data = monthly_sample()
        data = replace(
            data,
            closings=data.closings
            + (
                Closing("E", "01", "03", "UN", "2026-01", SCALE, 2000, 1, 30),
                Closing("D", "01", "01", "KG", "2026-01", 0, 0, 0, 0),
            ),
        )
        ranking = months(data)[0]["lowTurnover"]
        self.assertEqual(
            [(r["code"], r["value"]) for r in ranking], [("C", 0), ("A", 1), ("E", 1), ("A", 3)]
        )
        self.assertEqual(ranking[0]["display"], "0,00 x/mês")
        self.assertTrue(all("Giro da fonte" in row["detail"] for row in ranking))
        self.assertEqual(ranking[2]["warehouse"], "03")
        self.assertEqual(ranking[2]["unit"], "UN")
        self.assertEqual({row["unit"] for row in months(data, unit="KG")[0]["lowTurnover"]}, {"KG"})


if __name__ == "__main__":
    unittest.main()
