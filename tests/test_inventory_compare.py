"""Explicit month comparisons preserve coverage, units and integer facts."""

from copy import deepcopy
from dataclasses import replace
from datetime import date
from decimal import localcontext
from threading import Event
import unittest

from liarte_core.inventory import SCALE, Closing, Sale, StockSelection
from liarte_core.inventory_compare import compare_inventory_months
from liarte_core.inventory_monthly import analyze_monthly_inventory
from liarte_core.query import Cancelled
from tests.test_inventory_monthly import monthly_sample


def prepared(data=None, start="2026-01", end="2026-02", **filters):
    return analyze_monthly_inventory(
        monthly_sample() if data is None else data,
        StockSelection(start, end, **filters),
    )


def grouped(summary, dimension="products"):
    return {row["key"]: row for row in summary[dimension]}


class InventoryCompareTests(unittest.TestCase):
    def test_money_reconciles_exact_positions_and_retains_coverage_contributors(self):
        result = compare_inventory_months(prepared(), "2026-01", "2026-02")
        stock = result["stock"]
        self.assertEqual((result["baseLabel"], result["targetLabel"]), ("01/2026", "02/2026"))
        self.assertTrue(stock["available"])
        self.assertEqual((stock["before"], stock["after"], stock["change"]), (18000, 23600, 5600))
        self.assertEqual(
            (stock["matchedChange"], stock["addedValue"], stock["missingValue"]), (6000, 600, 1000)
        )
        self.assertEqual(
            (stock["matchedCount"], stock["addedCount"], stock["missingCount"]), (3, 1, 1)
        )
        self.assertEqual(
            stock["change"], stock["matchedChange"] + stock["addedValue"] - stock["missingValue"]
        )
        self.assertAlmostEqual(stock["percentage"], 5600 / 18000 * 100)
        products = grouped(stock)
        self.assertEqual(
            {key: row["change"] for key, row in products.items()},
            {"A": 5500, "B": 500, "C": -1000, "E": 600},
        )
        self.assertEqual((products["C"]["before"], products["C"]["after"]), (1000, None))
        self.assertEqual((products["E"]["before"], products["E"]["after"]), (None, 600))
        self.assertEqual(sum(row["change"] for row in stock["products"]), 5600)
        self.assertEqual(sum(row["change"] for row in stock["branches"]), 5600)
        self.assertIn("não comprovam", stock["coverageNote"].lower())

    def test_quantities_are_separate_and_missing_unit_is_not_zero(self):
        result = compare_inventory_months(prepared(), "2026-01", "2026-02")
        self.assertEqual(result["units"], ("KG", "L", "UN"))
        kg, liters, units = (result["quantityByUnit"][unit] for unit in result["units"])
        self.assertEqual(
            (kg["before"], kg["after"], kg["change"]), (160 * SCALE, 170 * SCALE, 10 * SCALE)
        )
        self.assertEqual(
            (kg["matchedChange"], kg["addedValue"], kg["missingValue"]), (20 * SCALE, 0, 10 * SCALE)
        )
        self.assertEqual(
            (liters["before"], liters["after"], liters["change"]),
            (20 * SCALE, 25 * SCALE, 5 * SCALE),
        )
        self.assertFalse(units["available"])
        self.assertEqual(
            (units["before"], units["after"], units["change"]), (None, 5 * SCALE, None)
        )
        self.assertEqual(units["products"], ())
        self.assertTrue(units["reason"])

    def test_sales_are_counted_once_per_branch_and_unit_with_observed_zero(self):
        result = compare_inventory_months(prepared(), "2026-01", "2026-02")
        kg, liters, units = (result["salesByUnit"][unit] for unit in result["units"])
        self.assertEqual(
            (kg["before"], kg["after"], kg["change"]), (11 * SCALE, 220 * SCALE, 209 * SCALE)
        )
        products = grouped(kg)
        self.assertEqual(
            (products["A"]["before"], products["A"]["after"]), (10 * SCALE, 20 * SCALE)
        )
        self.assertEqual((products["C"]["before"], products["C"]["after"]), (SCALE, 0))
        self.assertEqual((products["D"]["before"], products["D"]["after"]), (0, 200 * SCALE))
        self.assertEqual(
            {row["key"]: row["change"] for row in kg["branches"]},
            {"01": 9 * SCALE, "03": 200 * SCALE},
        )
        self.assertEqual(liters["change"], 3 * SCALE)
        self.assertTrue(units["available"])
        self.assertEqual((units["before"], units["after"], units["change"]), (0, 0, 0))
        self.assertIsNone(units["percentage"])
        self.assertEqual(units["products"], ())
        self.assertEqual(kg["beforeBranches"], ("01",))
        self.assertEqual(kg["afterBranches"], ("01", "03"))

    def test_nonconsecutive_explicit_endpoints_do_not_use_adjacent_change(self):
        data = monthly_sample()
        data = replace(
            data,
            closings=tuple(
                replace(row, period="2026-03") if row.period == "2026-02" else row
                for row in data.closings
            ),
        )
        months = prepared(data, end="2026-03")
        self.assertIsNone(months[1]["stockCost"])
        self.assertIsNone(months[2]["stockChange"])
        result = compare_inventory_months(months, "2026-01", "2026-03")
        self.assertTrue(result["stock"]["available"])
        self.assertEqual(result["stock"]["change"], 5600)
        self.assertEqual(result["salesByUnit"]["KG"]["change"], 29 * SCALE)

    def test_reversed_endpoints_reverse_changes_and_swap_coverage(self):
        result = compare_inventory_months(prepared(), "2026-02", "2026-01")
        stock = result["stock"]
        self.assertEqual((stock["before"], stock["after"], stock["change"]), (23600, 18000, -5600))
        self.assertEqual(
            (stock["matchedChange"], stock["addedValue"], stock["missingValue"]), (-6000, 1000, 600)
        )
        self.assertEqual(grouped(stock)["C"]["change"], 1000)
        self.assertEqual(grouped(stock)["E"]["change"], -600)
        self.assertEqual(result["salesByUnit"]["KG"]["change"], -209 * SCALE)

    def test_same_month_is_zero_only_where_values_are_available(self):
        result = compare_inventory_months(prepared(), "2026-01", "2026-01")
        stock = result["stock"]
        self.assertTrue(stock["available"])
        self.assertEqual((stock["change"], stock["percentage"]), (0, 0))
        self.assertEqual(
            (stock["matchedCount"], stock["addedCount"], stock["missingCount"]), (4, 0, 0)
        )
        self.assertEqual(len(stock["products"]), 3)
        self.assertTrue(all(row["change"] == 0 for row in stock["products"]))
        self.assertIn("mesmo mês", stock["reason"].lower())
        self.assertFalse(result["quantityByUnit"]["UN"]["available"])
        self.assertIsNone(result["quantityByUnit"]["UN"]["change"])
        self.assertTrue(result["salesByUnit"]["UN"]["available"])
        self.assertEqual(result["salesByUnit"]["UN"]["change"], 0)

    def test_missing_stock_month_preserves_endpoints_without_a_fictitious_delta(self):
        result = compare_inventory_months(prepared(end="2026-03"), "2026-02", "2026-03")
        stock = result["stock"]
        self.assertFalse(stock["available"])
        self.assertEqual((stock["before"], stock["after"]), (23600, None))
        for field in ("change", "percentage", "matchedChange", "addedValue", "missingValue"):
            self.assertIsNone(stock[field], field)
        self.assertEqual(stock["products"], ())
        self.assertEqual(stock["branches"], ())
        self.assertTrue(result["salesByUnit"]["KG"]["available"])
        self.assertEqual(result["salesByUnit"]["KG"]["change"], -180 * SCALE)

    def test_known_zero_stock_and_negative_bases_keep_exact_changes_without_percentages(self):
        for value in (0, -5000):
            with self.subTest(base_cost=value):
                data = monthly_sample()
                data = replace(
                    data,
                    closings=tuple(
                        replace(row, cost=value) if row.period == "2026-01" else row
                        for row in data.closings
                    ),
                )
                result = compare_inventory_months(prepared(data), "2026-01", "2026-02")
                stock = result["stock"]
                self.assertTrue(stock["available"])
                self.assertEqual(stock["before"], 4 * value)
                self.assertEqual(stock["change"], 23600 - 4 * value)
                self.assertIsNone(stock["percentage"])
                self.assertEqual(
                    stock["change"],
                    stock["matchedChange"] + stock["addedValue"] - stock["missingValue"],
                )

    def test_partial_stock_does_not_hide_the_observed_endpoints(self):
        data = replace(monthly_sample(), as_of=date(2026, 2, 15))
        result = compare_inventory_months(prepared(data), "2026-01", "2026-02")
        stock = result["stock"]
        self.assertFalse(stock["available"])
        self.assertEqual((stock["before"], stock["after"]), (18000, 23600))
        self.assertIsNone(stock["change"])
        self.assertIn("parcial", stock["reason"])
        self.assertFalse(result["salesByUnit"]["KG"]["available"])

    def test_partial_sales_are_independent_of_complete_stock_closings(self):
        data = monthly_sample()
        data = replace(
            data, sales=tuple(sale for sale in data.sales if sale.day >= date(2026, 1, 2))
        )
        result = compare_inventory_months(prepared(data), "2026-01", "2026-02")
        self.assertTrue(result["stock"]["available"])
        self.assertEqual(result["stock"]["change"], 5600)
        sales = result["salesByUnit"]["KG"]
        self.assertFalse(sales["available"])
        self.assertEqual((sales["before"], sales["after"]), (SCALE, 220 * SCALE))
        self.assertIsNone(sales["change"])
        self.assertEqual(sales["products"], ())
        self.assertIn("parcial", sales["reason"])
        self.assertIsNone(sales["beforeBranches"])
        self.assertIsNone(sales["afterBranches"])

    def test_warehouse_restricts_stock_and_disables_sales_without_allocating_them(self):
        result = compare_inventory_months(prepared(warehouse="01"), "2026-01", "2026-02")
        self.assertEqual(result["stock"]["change"], 5100)
        for sales in result["salesByUnit"].values():
            self.assertFalse(sales["available"])
            self.assertIsNone(sales["before"])
            self.assertIsNone(sales["after"])
            self.assertIsNone(sales["change"])
            self.assertEqual(sales["branches"], ())
            self.assertIn("armazém", sales["reason"])

    def test_no_sales_source_is_unknown_but_no_records_in_an_observed_month_are_zero(self):
        data = replace(monthly_sample(), sales=())
        unknown = compare_inventory_months(prepared(data), "2026-01", "2026-02")
        self.assertTrue(unknown["stock"]["available"])
        self.assertFalse(unknown["salesByUnit"]["KG"]["available"])
        self.assertIsNone(unknown["salesByUnit"]["KG"]["after"])
        self.assertIsNone(unknown["salesByUnit"]["KG"]["afterBranches"])
        data = monthly_sample()
        data = replace(data, sales=tuple(sale for sale in data.sales if sale.day.month == 1))
        zero = compare_inventory_months(prepared(data), "2026-01", "2026-02")
        self.assertTrue(zero["salesByUnit"]["KG"]["available"])
        self.assertEqual(
            (zero["salesByUnit"]["KG"]["after"], zero["salesByUnit"]["KG"]["change"]),
            (0, -11 * SCALE),
        )
        self.assertEqual(grouped(zero["salesByUnit"]["KG"])["A"]["after"], 0)
        self.assertEqual(zero["salesByUnit"]["KG"]["afterBranches"], ())

    def test_derived_filters_reuse_the_selected_current_cohort(self):
        result = compare_inventory_months(prepared(balance="positive"), "2026-01", "2026-02")
        stock = result["stock"]
        self.assertEqual((stock["before"], stock["after"], stock["change"]), (17000, 23600, 6600))
        self.assertEqual(stock["missingCount"], 0)
        self.assertNotIn("C", grouped(stock))
        sales = result["salesByUnit"]["KG"]
        self.assertEqual(
            (sales["before"], sales["after"], sales["change"]), (10 * SCALE, 20 * SCALE, 10 * SCALE)
        )
        self.assertNotIn("D", grouped(sales))

    def test_position_matching_includes_warehouse_even_for_the_same_product(self):
        data = monthly_sample()
        data = replace(
            data,
            closings=tuple(
                replace(row, warehouse=f"{int(row.warehouse) + 2:02d}")
                if row.period == "2026-02" and row.product == "A"
                else row
                for row in data.closings
            ),
        )
        result = compare_inventory_months(prepared(data), "2026-01", "2026-02")
        product = grouped(result["stock"])["A"]
        self.assertEqual(
            (product["before"], product["after"], product["change"]), (15000, 20500, 5500)
        )
        self.assertEqual(
            (product["matchedCount"], product["addedCount"], product["missingCount"]), (0, 2, 2)
        )
        self.assertEqual(
            (product["matchedChange"], product["addedValue"], product["missingValue"]),
            (0, 20500, 15000),
        )

    def test_money_groups_can_combine_units_while_quantity_and_sales_never_do(self):
        data = monthly_sample()
        data = replace(
            data,
            closings=(
                *data.closings,
                Closing("A", "02", "03", "L", "2026-01", 2 * SCALE, 200, None, None),
                Closing("A", "02", "03", "L", "2026-02", 3 * SCALE, 300, None, None),
            ),
            sales=(
                *data.sales,
                Sale("A", "02", "L", date(2026, 1, 1), 2 * SCALE, 200),
                Sale("A", "02", "L", date(2026, 2, 1), 3 * SCALE, 300),
            ),
        )
        result = compare_inventory_months(prepared(data), "2026-01", "2026-02")
        product = grouped(result["stock"])["A"]
        self.assertEqual(
            (product["before"], product["after"], product["change"]), (15200, 20800, 5600)
        )
        self.assertEqual(grouped(result["stock"], "branches")["02"]["change"], 100)
        self.assertEqual(result["quantityByUnit"]["L"]["change"], 6 * SCALE)
        self.assertEqual(result["quantityByUnit"]["KG"]["change"], 10 * SCALE)
        self.assertEqual(result["salesByUnit"]["L"]["change"], 4 * SCALE)
        self.assertEqual(grouped(result["salesByUnit"]["L"])["A"]["change"], SCALE)

    def test_net_returns_preserve_negative_quantities_and_contributions(self):
        data = monthly_sample()
        data = replace(
            data, sales=(*data.sales, Sale("C", "01", "KG", date(2026, 2, 7), -3 * SCALE, -300))
        )
        result = compare_inventory_months(prepared(data), "2026-01", "2026-02")
        product = grouped(result["salesByUnit"]["KG"])["C"]
        self.assertEqual(
            (product["before"], product["after"], product["change"]),
            (SCALE, -3 * SCALE, -4 * SCALE),
        )
        self.assertEqual(product["matchedCount"], 1)
        self.assertEqual(result["salesByUnit"]["KG"]["change"], 206 * SCALE)

    def test_zero_coverage_groups_remain_and_results_do_not_depend_on_row_order_or_mutate_input(
        self,
    ):
        data = monthly_sample()
        jan = {
            (row.product, row.branch, row.warehouse, row.unit): row
            for row in data.closings
            if row.period == "2026-01"
        }
        data = replace(
            data,
            closings=tuple(
                replace(row, cost=0)
                if row.product == "C"
                else replace(row, cost=jan[row.product, row.branch, row.warehouse, row.unit].cost)
                if row.period == "2026-02" and row.product != "E"
                else replace(row, cost=0)
                if row.product == "E"
                else row
                for row in data.closings
            ),
        )
        months = prepared(data)
        original = deepcopy(months)
        result = compare_inventory_months(months, "2026-01", "2026-02")
        self.assertEqual(months, original)
        self.assertEqual(result["stock"]["change"], 0)
        self.assertEqual(
            tuple(row["key"] for row in result["stock"]["products"]), ("A", "B", "C", "E")
        )
        products = grouped(result["stock"])
        self.assertEqual(
            (products["C"]["before"], products["C"]["after"], products["C"]["missingCount"]),
            (0, None, 1),
        )
        self.assertEqual(
            (products["E"]["before"], products["E"]["after"], products["E"]["addedCount"]),
            (None, 0, 1),
        )
        shuffled = tuple(
            dict(
                month,
                stockRows=list(reversed(month["stockRows"])),
                saleRows=list(reversed(month["saleRows"])),
            )
            for month in months
        )
        self.assertEqual(compare_inventory_months(shuffled, "2026-01", "2026-02"), result)

    def test_invalid_periods_and_duplicate_source_keys_are_rejected(self):
        months = prepared()
        for value in (None, "", "2026-13", "2026-1", "２０２６-01", "2025-01"):
            with self.subTest(period=value), self.assertRaises(ValueError):
                compare_inventory_months(months, value, "2026-02")
        with self.assertRaises(ValueError):
            compare_inventory_months((*months, months[0]), "2026-01", "2026-02")
        for field in ("stockRows", "saleRows"):
            changed = deepcopy(months)
            changed[0][field].append(dict(changed[0][field][0]))
            with self.subTest(field=field), self.assertRaises(ValueError):
                compare_inventory_months(changed, "2026-01", "2026-02")

    def test_cancellation_before_and_during_endpoint_iteration_never_publishes(self):
        months = prepared()
        cancel = Event()
        cancel.set()
        with self.assertRaises(Cancelled):
            compare_inventory_months(months, "2026-01", "2026-02", cancel=cancel)
        cancel.clear()
        base = dict(months[0])
        template = base["stockRows"][0]

        class InterruptingRows:
            visited = 0

            def __iter__(self):
                for index in range(2000):
                    self.visited += 1
                    if index == 511:
                        cancel.set()
                    yield dict(template, code=f"C{index:04d}")

        rows = InterruptingRows()
        base["stockRows"] = rows
        with self.assertRaises(Cancelled):
            compare_inventory_months((base, months[1]), "2026-01", "2026-02", cancel=cancel)
        self.assertLess(rows.visited, 2000)

    def test_large_integer_values_remain_exact_under_a_small_decimal_context(self):
        data = monthly_sample()
        data = replace(
            data,
            closings=tuple(
                replace(row, cost=10**22 + index * 7, quantity=10**25 + index * 11)
                for index, row in enumerate(data.closings)
            ),
        )
        months = prepared(data)
        before, after = (
            sum(row.cost for row in data.closings if row.period == period)
            for period in ("2026-01", "2026-02")
        )
        with localcontext() as context:
            context.prec = 2
            result = compare_inventory_months(months, "2026-01", "2026-02")
        stock = result["stock"]
        self.assertEqual(
            (stock["before"], stock["after"], stock["change"]), (before, after, after - before)
        )
        self.assertIs(type(stock["change"]), int)
        self.assertEqual(sum(row["change"] for row in stock["products"]), after - before)
        self.assertEqual(
            stock["change"], stock["matchedChange"] + stock["addedValue"] - stock["missingValue"]
        )
        kg = result["quantityByUnit"]["KG"]
        self.assertIs(type(kg["change"]), int)
        self.assertEqual(kg["change"], kg["matchedChange"] + kg["addedValue"] - kg["missingValue"])
