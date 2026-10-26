"""Product performance keeps observed facts distinct from stock hypotheses."""

from copy import deepcopy
from dataclasses import replace
from datetime import date
from threading import Event
import unittest

from liarte_core.inventory import SCALE, Closing, Sale, StockSelection
from liarte_core.inventory_monthly import analyze_monthly_inventory
from liarte_core.inventory_performance import (
    analyze_product_performance,
    product_performance_detail,
)
from liarte_core.query import Cancelled
from tests.test_inventory_monthly import monthly_sample


def prepared(data=None, start="2026-01", end="2026-02", **filters):
    selection = StockSelection(start, end, **filters)
    return analyze_monthly_inventory(data or monthly_sample(), selection), selection


def report(data=None, *, window=1, start="2026-01", end="2026-02", **filters):
    months, selection = prepared(data, start, end, **filters)
    return analyze_product_performance(months, selection, window=window)


def rows_by_key(result):
    return {(row["code"], row["unit"]): row for row in result["rows"]}


def extended_sample():
    """Twelve complete sales months, with quantities that allow exact sums."""
    source = monthly_sample()
    periods = tuple(f"2025-{month:02d}" for month in range(7, 13)) + tuple(
        f"2026-{month:02d}" for month in range(1, 7)
    )
    return replace(
        source,
        as_of=date(2026, 7, 15),
        closings=tuple(
            Closing("A", "01", "01", "KG", period, (100 + index) * SCALE, 10000, index, None)
            for index, period in enumerate(periods, 1)
        ),
        sales=tuple(
            Sale("A", "01", "KG", date.fromisoformat(period + "-01"), index * SCALE, 100)
            for index, period in enumerate(periods, 1)
        ),
    )


class InventoryPerformanceTests(unittest.TestCase):
    def test_net_sales_are_counted_once_per_branch_without_warehouse_duplication(self):
        result = report()
        self.assertTrue(result["available"])
        a = rows_by_key(result)["A", "KG"]
        self.assertEqual(
            (a["previous"], a["sold"], a["change"]), (10 * SCALE, 20 * SCALE, 10 * SCALE)
        )
        self.assertEqual(a["percentage"], 100)
        self.assertEqual(a["stockQuantity"], 170 * SCALE)
        self.assertEqual(a["stockCost"], 20500)
        self.assertEqual(a["status"], "up")

    def test_three_month_windows_are_adjacent_and_do_not_silently_shrink(self):
        result = report(extended_sample(), start="2026-01", end="2026-06", window=3)
        self.assertEqual(tuple(result["basePeriods"]), ("2026-01", "2026-02", "2026-03"))
        self.assertEqual(tuple(result["targetPeriods"]), ("2026-04", "2026-05", "2026-06"))
        a = rows_by_key(result)["A", "KG"]
        self.assertEqual(
            (a["previous"], a["sold"], a["change"]), (24 * SCALE, 33 * SCALE, 9 * SCALE)
        )
        self.assertEqual(a["percentage"], 37.5)
        self.assertEqual(a["turnover"], 12)
        self.assertEqual(a["turnoverCount"], 1)

    def test_six_month_windows_use_all_twelve_consecutive_months(self):
        result = report(extended_sample(), start="2025-07", end="2026-06", window=6)
        a = rows_by_key(result)["A", "KG"]
        self.assertTrue(result["available"])
        self.assertEqual(len(result["basePeriods"]), 6)
        self.assertEqual(len(result["targetPeriods"]), 6)
        self.assertEqual(
            (a["previous"], a["sold"], a["change"]), (21 * SCALE, 57 * SCALE, 36 * SCALE)
        )

    def test_insufficient_history_keeps_target_total_but_does_not_fabricate_baseline(self):
        result = report(extended_sample(), start="2026-03", end="2026-06", window=3)
        self.assertFalse(result["available"])
        self.assertTrue(result["reason"])
        a = rows_by_key(result)["A", "KG"]
        self.assertEqual(a["sold"], 33 * SCALE)
        self.assertIsNone(a["previous"])
        self.assertIsNone(a["change"])
        self.assertIsNone(a["percentage"])
        self.assertEqual(a["status"], "insufficient")

    def test_missing_calendar_month_is_not_bridged_by_older_observed_month(self):
        months, selection = prepared(extended_sample(), "2026-01", "2026-06")
        months = tuple(month for month in months if month["period"] != "2026-05")
        result = analyze_product_performance(months, selection, window=1)
        self.assertFalse(result["available"])
        self.assertEqual(result["targetPeriod"], "2026-06")
        a = rows_by_key(result)["A", "KG"]
        self.assertEqual(a["sold"], 12 * SCALE)
        self.assertIsNone(a["previous"])
        self.assertIsNone(a["change"])

    def test_unobserved_target_month_is_not_replaced_by_latest_sales_month(self):
        months, selection = prepared(extended_sample(), "2026-01", "2026-06")
        months = tuple(
            dict(month, salesObserved=False, salesQuantity={"KG": None}, saleRows=[])
            if month["period"] == "2026-06"
            else month
            for month in months
        )
        result = analyze_product_performance(months, selection, window=1)
        self.assertFalse(result["available"])
        self.assertEqual(result["targetPeriod"], "2026-06")
        a = rows_by_key(result)["A", "KG"]
        self.assertIsNone(a["sold"])
        self.assertEqual(a["previous"], 11 * SCALE)
        self.assertIsNone(a["change"])

    def test_partial_final_month_remains_in_detail_but_is_not_used_for_comparison(self):
        months, selection = prepared(end="2026-04")
        result = analyze_product_performance(months, selection, window=1)
        self.assertEqual(result["targetPeriod"], "2026-03")
        a = rows_by_key(result)["A", "KG"]
        self.assertEqual((a["previous"], a["sold"]), (20 * SCALE, 40 * SCALE))
        detail = product_performance_detail(months, selection, "A", "KG", window=1, report=result)
        self.assertEqual(detail["series"][-1]["period"], "2026-04")
        self.assertTrue(detail["series"][-1]["partial"])

    def test_partial_start_of_observation_blocks_baseline_percentage(self):
        source = monthly_sample()
        source = replace(
            source, sales=tuple(sale for sale in source.sales if sale.day >= date(2026, 1, 2))
        )
        result = report(source)
        self.assertFalse(result["available"])
        a = rows_by_key(result)["A", "KG"]
        self.assertIsNone(a["previous"])
        self.assertEqual(a["sold"], 20 * SCALE)
        self.assertIsNone(a["percentage"])

    def test_complete_observed_month_without_transactions_is_zero_not_unknown(self):
        source = monthly_sample()
        source = replace(source, sales=tuple(sale for sale in source.sales if sale.day.month == 1))
        result = report(source)
        a = rows_by_key(result)["A", "KG"]
        self.assertEqual((a["previous"], a["sold"], a["change"]), (10 * SCALE, 0, -10 * SCALE))
        self.assertEqual(a["status"], "no_positive")

    def test_no_sales_source_is_unknown_even_when_stock_is_available(self):
        result = report(replace(monthly_sample(), sales=()))
        self.assertFalse(result["available"])
        a = rows_by_key(result)["A", "KG"]
        self.assertIsNone(a["sold"])
        self.assertIsNone(a["previous"])
        self.assertIsNone(a["coverage"])
        self.assertEqual(a["stockQuantity"], 170 * SCALE)

    def test_same_product_in_two_units_remains_two_distinct_observations(self):
        source = monthly_sample()
        source = replace(
            source,
            sales=source.sales + (Sale("A", "01", "UN", date(2026, 2, 1), 9 * SCALE, 500),),
            closings=source.closings
            + (Closing("A", "01", "01", "UN", "2026-02", 3 * SCALE, 500, 8, None),),
        )
        result = report(source)
        keys = rows_by_key(result)
        self.assertEqual(set(result["units"]), {"KG", "L", "UN"})
        self.assertEqual(keys["A", "KG"]["sold"], 20 * SCALE)
        self.assertEqual(keys["A", "UN"]["sold"], 9 * SCALE)
        self.assertEqual(keys["A", "KG"]["stockQuantity"], 170 * SCALE)
        self.assertEqual(keys["A", "UN"]["stockQuantity"], 3 * SCALE)

    def test_warehouse_filter_keeps_stock_but_disables_sales_and_coverage(self):
        result = report(warehouse="01")
        self.assertFalse(result["available"])
        self.assertIn("armazém", result["reason"].lower())
        a = rows_by_key(result)["A", "KG"]
        self.assertEqual(a["stockQuantity"], 120 * SCALE)
        self.assertEqual(a["turnover"], 2)
        self.assertIsNone(a["sold"])
        self.assertIsNone(a["coverage"])
        self.assertTrue(a["coverageReason"])

    def test_historical_and_sales_only_products_do_not_require_current_balance(self):
        result = report()
        rows = rows_by_key(result)
        c, d = rows["C", "KG"], rows["D", "KG"]
        self.assertEqual((c["previous"], c["sold"]), (SCALE, 0))
        self.assertIsNone(c["stockQuantity"])
        self.assertIsNone(c["stockCost"])
        self.assertEqual((d["previous"], d["sold"]), (0, 200 * SCALE))
        self.assertIsNone(d["stockQuantity"])
        self.assertIsNone(d["coverage"])
        self.assertEqual(d["status"], "resumed")
        self.assertIsNone(d["percentage"])

    def test_observed_zero_stock_is_distinct_from_missing_closure(self):
        source = monthly_sample()
        source = replace(
            source,
            closings=tuple(
                replace(row, quantity=0, cost=0)
                if row.product == "A" and row.period == "2026-02"
                else row
                for row in source.closings
            ),
        )
        rows = rows_by_key(report(source))
        self.assertEqual(rows["A", "KG"]["stockQuantity"], 0)
        self.assertEqual(rows["A", "KG"]["stockCost"], 0)
        self.assertEqual(rows["A", "KG"]["coverage"], 0)
        self.assertIsNone(rows["C", "KG"]["stockQuantity"])
        self.assertIsNone(rows["C", "KG"]["coverage"])

    def test_coverage_uses_target_calendar_days_and_branch_sales_once(self):
        a = rows_by_key(report())["A", "KG"]
        self.assertEqual(a["coverage"], 238)
        a = rows_by_key(report(extended_sample(), start="2026-01", end="2026-06", window=3))[
            "A", "KG"
        ]
        self.assertAlmostEqual(a["coverage"], 112 * 91 / 33)

    def test_sales_from_a_branch_without_matching_stock_disable_coverage(self):
        source = monthly_sample()
        source = replace(
            source, sales=source.sales + (Sale("A", "02", "KG", date(2026, 2, 1), 5 * SCALE, 500),)
        )
        a = rows_by_key(report(source))["A", "KG"]
        self.assertEqual(a["sold"], 25 * SCALE)
        self.assertEqual(a["stockQuantity"], 170 * SCALE)
        self.assertIsNone(a["coverage"])
        self.assertTrue(a["coverageReason"])

    def test_negative_stock_or_nonpositive_net_demand_never_becomes_coverage(self):
        source = monthly_sample()
        negative_stock = replace(
            source,
            closings=tuple(
                replace(row, quantity=-SCALE)
                if row.product == "A" and row.period == "2026-02"
                else row
                for row in source.closings
            ),
        )
        self.assertIsNone(rows_by_key(report(negative_stock))["A", "KG"]["coverage"])
        for quantity in (0, -SCALE):
            with self.subTest(quantity=quantity):
                changed = replace(
                    source,
                    sales=tuple(
                        replace(row, quantity=quantity)
                        if row.product == "A" and row.day.month == 2
                        else row
                        for row in source.sales
                    ),
                )
                self.assertIsNone(rows_by_key(report(changed))["A", "KG"]["coverage"])

    def test_source_turnover_is_one_month_position_median_with_invalids_excluded(self):
        source = monthly_sample()
        extra = (
            Closing("A", "01", "03", "KG", "2026-02", SCALE, 100, 1000, None),
            Closing("A", "01", "04", "KG", "2026-02", 0, 0, 5000, None),
            Closing("A", "01", "05", "KG", "2026-02", -SCALE, -100, 9000, None),
            Closing("A", "01", "06", "KG", "2026-02", SCALE, 100, -1, None),
            Closing("A", "01", "07", "KG", "2026-02", SCALE, 100, float("inf"), None),
            Closing("A", "01", "08", "KG", "2026-02", SCALE, 100, float("nan"), None),
        )
        source = replace(source, closings=source.closings + extra)
        a = rows_by_key(report(source))["A", "KG"]
        self.assertEqual(a["turnover"], 4)
        self.assertEqual(a["turnoverCount"], 3)

    def test_zero_source_turnover_is_valid_but_missing_source_turnover_is_not_zero(self):
        source = monthly_sample()
        source = replace(
            source,
            closings=tuple(
                replace(row, turnover=0) if row.product == "A" and row.period == "2026-02" else row
                for row in source.closings
            ),
        )
        rows = rows_by_key(report(source))
        self.assertEqual(rows["A", "KG"]["turnover"], 0)
        self.assertEqual(rows["A", "KG"]["turnoverCount"], 2)
        self.assertIsNone(rows["B", "L"]["turnover"])
        self.assertEqual(rows["B", "L"]["turnoverCount"], 0)

    def test_negative_sales_in_either_window_are_not_ranked_as_a_demand_drop(self):
        source = monthly_sample()
        for month in (1, 2):
            with self.subTest(month=month):
                changed = replace(
                    source,
                    sales=tuple(
                        replace(sale, quantity=-SCALE)
                        if sale.product == "A" and sale.day.month == month
                        else sale
                        for sale in source.sales
                    ),
                )
                a = rows_by_key(report(changed))["A", "KG"]
                self.assertEqual(a["status"], "negative")
                self.assertIsNone(a["percentage"])

    def test_net_zero_with_positive_event_does_not_prove_no_sales_transactions(self):
        source = monthly_sample()
        source = replace(
            source,
            sales=tuple(
                replace(sale, quantity=0, had_positive=True)
                if sale.product == "A" and sale.day.month == 2
                else sale
                for sale in source.sales
            ),
        )
        months, selection = prepared(source)
        result = analyze_product_performance(months, selection, window=1)
        a = rows_by_key(result)["A", "KG"]
        self.assertEqual(a["sold"], 0)
        detail = product_performance_detail(months, selection, "A", "KG", window=1, report=result)
        self.assertEqual(detail["series"][-1]["sales"], 0)
        facts = " ".join(detail["evidence"]).lower()
        self.assertNotIn("não houve vendas", facts)
        self.assertNotIn("nenhuma venda ocorreu", facts)
        self.assertNotIn("nunca vendeu", facts)

    def test_matching_stock_positions_includes_branch_warehouse_and_unit(self):
        source = monthly_sample()
        source = replace(
            source,
            closings=tuple(
                replace(row, warehouse="03")
                if row.product == "A" and row.period == "2026-02" and row.warehouse == "02"
                else row
                for row in source.closings
            ),
        )
        a = rows_by_key(report(source))["A", "KG"]
        self.assertEqual(a["matchedStockChange"], 20 * SCALE)
        self.assertEqual(a["matchedStockCostChange"], 5000)
        self.assertEqual((a["matchedCount"], a["addedCount"], a["missingCount"]), (1, 1, 1))
        self.assertTrue(a["stockCoverageChanged"])

    def test_detail_keeps_gaps_and_does_not_reconstruct_stock_from_current_balance(self):
        months, selection = prepared(end="2026-03")
        result = analyze_product_performance(months, selection, window=1)
        detail = product_performance_detail(months, selection, "A", "KG", window=1, report=result)
        self.assertEqual(
            [point["period"] for point in detail["series"]], ["2026-01", "2026-02", "2026-03"]
        )
        self.assertEqual(detail["series"][1]["quantity"], 170 * SCALE)
        self.assertIsNone(detail["series"][2]["quantity"])
        self.assertIsNone(detail["series"][2]["turnover"])
        self.assertEqual(detail["series"][2]["sales"], 40 * SCALE)
        self.assertIsNone(detail["series"][2]["matchedStockChange"])
        limits = " ".join(detail["limitations"]).lower()
        self.assertIn("lote", limits)

    def test_detail_unknown_product_does_not_fabricate_monthly_zero_sales(self):
        months, selection = prepared()
        detail = product_performance_detail(months, selection, "DOES-NOT-EXIST", "KG", window=1)
        self.assertIsNone(detail["row"])
        self.assertEqual(detail["series"], ())
        self.assertTrue(detail["reason"])

    def test_derived_cohort_filters_are_respected_without_adding_historical_products(self):
        result = report(balance="positive")
        keys = rows_by_key(result)
        self.assertIn(("A", "KG"), keys)
        self.assertNotIn(("C", "KG"), keys)
        self.assertNotIn(("D", "KG"), keys)

    def test_computation_does_not_mutate_cached_monthly_facts(self):
        months, selection = prepared()
        before = deepcopy(months)
        result = analyze_product_performance(months, selection, window=1)
        product_performance_detail(months, selection, "A", "KG", window=1, report=result)
        self.assertEqual(months, before)

    def test_cancelled_requests_stop_before_publishing_report_or_detail(self):
        months, selection = prepared()
        cancel = Event()
        cancel.set()
        with self.assertRaises(Cancelled):
            analyze_product_performance(months, selection, window=1, cancel=cancel)
        with self.assertRaises(Cancelled):
            product_performance_detail(months, selection, "A", "KG", window=1, cancel=cancel)

    def test_empty_recorte_has_no_fabricated_products_or_sales(self):
        result = report(product="DOES-NOT-EXIST")
        self.assertEqual(result["rows"], ())
        self.assertEqual(result["units"], ())

    def test_detail_rejects_report_from_another_branch_even_with_the_same_dates(self):
        months, selection = prepared()
        result = analyze_product_performance(months, selection, window=1)
        with self.assertRaises(ValueError):
            product_performance_detail(
                months, replace(selection, branch="03"), "A", "KG", window=1, report=result
            )

    def test_peak_evidence_uses_complete_months_and_identifies_tied_months(self):
        source = monthly_sample()
        source = replace(
            source,
            sales=source.sales
            + (
                Sale("A", "01", "KG", date(2026, 1, 2), 30 * SCALE, 3000),
                Sale("A", "01", "KG", date(2026, 4, 5), 999 * SCALE, 99900),
            ),
        )
        months, selection = prepared(source, end="2026-04")
        detail = product_performance_detail(months, selection, "A", "KG", window=1)
        peaks = [fact for fact in detail["evidence"] if "pico observado" in fact]
        self.assertEqual(len(peaks), 1)
        self.assertIn("40,000 KG", peaks[0])
        self.assertIn("01/2026", peaks[0])
        self.assertIn("03/2026", peaks[0])
        self.assertIn("empate", peaks[0])
        self.assertNotIn("04/2026", peaks[0])
        self.assertNotIn("999", peaks[0])

    def test_unsupported_window_is_rejected_instead_of_silently_changed(self):
        months, selection = prepared()
        for window in (0, 2, 12, True, "3"):
            with self.subTest(window=window), self.assertRaises(ValueError):
                analyze_product_performance(months, selection, window=window)


if __name__ == "__main__":
    unittest.main()
