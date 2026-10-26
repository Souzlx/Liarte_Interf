"""Synthetic review-list contracts: selected stock, known demand and unknown age."""

from dataclasses import FrozenInstanceError, replace
from datetime import date, timedelta
from threading import Event
import unittest
from unittest.mock import patch

from liarte_core.inventory import (
    SCALE, Balance, InventoryData, Product, Sale, StockSelection, analyze_inventory,
)
from liarte_core.inventory_alerts import AlertPolicy, analyze_stock_alerts
from liarte_core.query import Cancelled


def alert_sample():
    return InventoryData(
        date(2026, 4, 15), "Synthetic alert source", "a" * 64,
        (
            Product("A", "Product A", "Group", "PA", "KG"),
            Product("B", "Product B", "Group", "PA", "UN"),
            Product("C", "Product C", "Group", "PA", "L"),
        ),
        (
            Balance("A", "01", "01", "KG", 20 * SCALE, 2000),
            Balance("A", "01", "02", "KG", 10 * SCALE, 1000),
            Balance("B", "01", "01", "UN", 5 * SCALE, 500),
            Balance("C", "01", "01", "L", -SCALE, -100),
        ),
        (),
        (Sale("A", "01", "KG", date(2026, 1, 1), 10 * SCALE, 1000),),
    )


def review(data=None, selected=None, policy=None):
    data = data if data is not None else alert_sample()
    selected = selected if selected is not None else StockSelection("2026-01", "2026-03")
    analysis = analyze_inventory(data, selected)
    return analyze_stock_alerts(data, selected, analysis, policy or AlertPolicy())


class InventoryAlertTests(unittest.TestCase):
    def test_policy_defaults_bounds_and_strict_integer_validation(self):
        self.assertEqual(AlertPolicy(), AlertPolicy(90, 30))
        self.assertEqual(AlertPolicy(1, 3650).stale_days, 1)
        self.assertEqual(AlertPolicy(3650, 1).coverage_days, 1)
        for field in ("stale_days", "coverage_days"):
            for invalid in (True, False, None, "90", 90.0, -1, 0, 3651):
                with self.subTest(field=field, value=invalid), self.assertRaises(ValueError):
                    AlertPolicy(**{field: invalid})
        with self.assertRaises(FrozenInstanceError):
            AlertPolicy().stale_days = 12
        data, selected = alert_sample(), StockSelection("2026-01", "2026-03")
        with self.assertRaises(ValueError):
            analyze_stock_alerts(data, selected, analyze_inventory(data, selected), None)

    def test_warehouses_are_deduplicated_and_capital_is_clipped_after_summing(self):
        data = alert_sample()
        data = replace(data, balances=(
            data.balances[0], replace(data.balances[1], cost=-2500), *data.balances[2:],
        ))
        result = review(data)
        self.assertEqual(result.scope_count, 3)
        self.assertEqual(len(result.stale), 1)
        item = result.stale[0]
        self.assertEqual((item.code, item.branch, item.unit), ("A", "01", "KG"))
        self.assertEqual(item.quantity, 30 * SCALE)
        self.assertEqual(item.cost, 0)
        self.assertEqual(item.coverage, 270.0)
        self.assertEqual(result.coverage_unavailable_count, 2)

    def test_same_product_in_other_branches_and_units_remains_separate(self):
        data = alert_sample()
        data = replace(data, balances=(
            *data.balances,
            Balance("A", "02", "01", "KG", 2 * SCALE, 200),
            Balance("A", "01", "03", "L", 3 * SCALE, 300),
        ), sales=(
            *data.sales,
            Sale("A", "02", "KG", date(2026, 1, 2), SCALE, 100),
            Sale("A", "01", "L", date(2026, 4, 1), SCALE, 100),
        ))
        result = review(data)
        self.assertEqual(result.scope_count, 5)
        self.assertEqual(
            {(r.code, r.branch, r.unit) for r in result.stale},
            {("A", "01", "KG"), ("A", "02", "KG")},
        )
        self.assertNotIn(("A", "01", "L"), {(r.code, r.branch, r.unit) for r in result.stale})

    def test_recency_strict_boundary_uses_source_date_instead_of_selected_end(self):
        data = alert_sample()
        at_limit = data.as_of - timedelta(days=90)
        data = replace(data, sales=(Sale("A", "01", "KG", at_limit, SCALE, 100),))
        result = review(data)
        self.assertEqual(result.stale, ())
        older = replace(data, sales=(replace(data.sales[0], day=at_limit - timedelta(days=1)),))
        result = review(older)
        self.assertEqual(result.stale[0].days_since_sale, 91)
        self.assertEqual(result.stale[0].last_sale, at_limit - timedelta(days=1))
        self.assertEqual(result.as_of, date(2026, 4, 15))
        self.assertEqual((result.start, result.end), ("2026-01", "2026-03"))
        self.assertEqual(review(older, policy=AlertPolicy(91, 30)).stale, ())

    def test_unknown_sale_age_is_separate_and_only_positive_stock_enters(self):
        data = replace(alert_sample(), sales=(), balances=(
            Balance("A", "01", "01", "KG", 20 * SCALE, 2000),
            Balance("B", "01", "01", "UN", 0, 0),
            Balance("C", "01", "01", "L", -SCALE, -100),
        ))
        result = review(data)
        self.assertEqual(result.stale, ())
        self.assertEqual(result.low_coverage, ())
        self.assertEqual([r.code for r in result.no_sale], ["A"])
        self.assertIsNone(result.no_sale[0].last_sale)
        self.assertIsNone(result.no_sale[0].days_since_sale)
        self.assertIsNone(result.no_sale[0].coverage)
        self.assertEqual(result.coverage_unavailable_count, 3)

    def test_coverage_strict_boundary_includes_zero_stock_with_observed_demand(self):
        data = InventoryData(
            date(2026, 1, 30), "Coverage limits", "b" * 64,
            tuple(Product(c, c, "Group", "PA", "KG") for c in ("A", "B", "C")),
            tuple(Balance(c, "01", "01", "KG", qty * SCALE, qty * 100)
                  for c, qty in (("A", 30), ("B", 29), ("C", 0))),
            (),
            tuple(Sale(c, "01", "KG", date(2026, 1, 1), 30 * SCALE, 3000)
                  for c in ("A", "B", "C")),
        )
        selected = StockSelection("2026-01", "2026-01")
        result = review(data, selected)
        self.assertEqual([r.code for r in result.low_coverage], ["C", "B"])
        self.assertEqual([r.coverage for r in result.low_coverage], [0, 29])
        self.assertEqual(result.coverage_unavailable_count, 0)
        self.assertEqual(review(data, selected, AlertPolicy(90, 29)).low_coverage[0].code, "C")
        self.assertEqual(len(review(data, selected, AlertPolicy(90, 29)).low_coverage), 1)

    def test_warehouse_selection_disables_coverage_but_preserves_branch_sale_recency(self):
        result = review(selected=StockSelection("2026-01", "2026-03", warehouse="01"))
        self.assertFalse(result.coverage_available)
        self.assertEqual(result.low_coverage, ())
        self.assertEqual(result.coverage_unavailable_count, result.scope_count)
        self.assertEqual(result.stale[0].quantity, 20 * SCALE)
        self.assertIsNone(result.stale[0].coverage)
        self.assertEqual(result.stale[0].last_sale, date(2026, 1, 1))

    def test_negative_stock_and_nonpositive_net_demand_cannot_generate_low_coverage(self):
        data = alert_sample()
        data = replace(data, balances=(
            replace(data.balances[0], quantity=-SCALE),
            replace(data.balances[1], quantity=0),
            *data.balances[2:],
        ), sales=(
            *data.sales,
            Sale("B", "01", "UN", date(2026, 1, 1), -SCALE, -100),
        ))
        result = review(data)
        self.assertEqual(result.low_coverage, ())
        self.assertEqual(result.stale, ())
        self.assertEqual([r.code for r in result.no_sale], ["B"])
        self.assertEqual(result.coverage_unavailable_count, 3)

    def test_positive_sale_marker_preserves_recency_after_same_day_returns(self):
        data = alert_sample()
        data = replace(data, sales=(
            *data.sales,
            Sale("A", "01", "KG", date(2026, 4, 1), -20 * SCALE, -2000, True),
        ))
        self.assertEqual(review(data).stale, ())
        data = replace(data, sales=(*data.sales[:-1], replace(data.sales[-1], had_positive=False)))
        self.assertEqual(review(data).stale[0].last_sale, date(2026, 1, 1))

    def test_selected_period_changes_demand_without_rewriting_source_date_recency(self):
        data = replace(alert_sample(), sales=(
            Sale("A", "01", "KG", date(2026, 1, 1), 100 * SCALE, 10000),
        ))
        january = review(data, StockSelection("2026-01", "2026-01"))
        march = review(data, StockSelection("2026-03", "2026-03"))
        self.assertEqual(january.stale[0].days_since_sale, march.stale[0].days_since_sale)
        self.assertEqual(len(january.low_coverage), 1)
        self.assertEqual(march.low_coverage, ())
        self.assertIsNone(march.stale[0].coverage)

    def test_existing_product_branch_unit_and_balance_filters_define_alert_scope(self):
        data = alert_sample()
        result = review(data, StockSelection("2026-01", "2026-03", product="A", unit="KG"))
        self.assertEqual(result.scope_count, 1)
        self.assertEqual([r.code for r in result.stale], ["A"])
        self.assertEqual(result.no_sale, ())
        result = review(data, StockSelection("2026-01", "2026-03", branch="99"))
        self.assertEqual(result.scope_count, 0)
        self.assertEqual((result.stale, result.low_coverage, result.no_sale), ((), (), ()))

    def test_negative_selected_group_cannot_use_positive_whole_branch_coverage(self):
        data = alert_sample()
        data = replace(data, balances=(
            replace(data.balances[0], quantity=-SCALE, cost=-100), data.balances[1],
        ))
        selected = StockSelection("2026-01", "2026-03", balance="negative")
        analysis = analyze_inventory(data, selected)
        self.assertGreater(analysis.rows[0].coverage, 0)
        result = analyze_stock_alerts(data, selected, analysis, AlertPolicy(90, 3650))
        self.assertEqual(result.low_coverage, ())
        self.assertEqual(result.coverage_unavailable_count, 1)

    def test_complete_lists_are_sorted_deterministically_without_visual_truncation(self):
        codes = tuple(f"P{i:03}" for i in range(25))
        data = InventoryData(
            date(2026, 4, 15), "Complete lists", "c" * 64,
            tuple(Product(c, c, "Group", "PA", "KG") for c in reversed(codes)),
            tuple(Balance(c, "01", "01", "KG", SCALE, 100) for c in reversed(codes)),
            (), (),
        )
        result = review(data)
        self.assertEqual(len(result.no_sale), 25)
        self.assertEqual([r.code for r in result.no_sale], list(codes))
        with self.assertRaises(FrozenInstanceError):
            result.no_sale[0].cost = 10

    def test_analysis_is_reused_without_rescanning_source_facts(self):
        data = alert_sample()
        selected = StockSelection("2026-01", "2026-03")
        analysis = analyze_inventory(data, selected)

        class Unreadable:
            def __iter__(self):
                raise AssertionError("Source facts must not be traversed again")

        unreadable = replace(data, products=Unreadable(), balances=Unreadable(), sales=Unreadable())
        result = analyze_stock_alerts(unreadable, selected, analysis)
        self.assertEqual(result.stale[0].code, "A")

    def test_invalid_coverage_values_are_unknown_instead_of_signals(self):
        data = alert_sample()
        selected = StockSelection("2026-01", "2026-03", product="A")
        analysis = analyze_inventory(data, selected)
        for invalid in (float("nan"), float("inf"), -1):
            with self.subTest(value=invalid):
                modified = replace(analysis, rows=tuple(replace(r, coverage=invalid) for r in analysis.rows))
                result = analyze_stock_alerts(data, selected, modified)
                self.assertEqual(result.low_coverage, ())
                self.assertEqual(result.coverage_unavailable_count, 1)
                self.assertIsNone(result.stale[0].coverage)

    def test_cancellation_before_or_during_collection_never_returns_partial_results(self):
        data = alert_sample()
        selected = StockSelection("2026-01", "2026-03")
        analysis = analyze_inventory(data, selected)
        cancelled = Event()
        cancelled.set()
        with self.assertRaises(Cancelled):
            analyze_stock_alerts(data, selected, analysis, cancel=cancelled)
        calls = 0
        is_cancelled = cancelled.is_set

        def cancel_on_third_check():
            nonlocal calls
            calls += 1
            if calls == 3:
                cancelled.set()
            return is_cancelled()

        cancelled.clear()
        with patch.object(cancelled, "is_set", side_effect=cancel_on_third_check):
            with self.assertRaises(Cancelled):
                analyze_stock_alerts(data, selected, analysis, cancel=cancelled)
