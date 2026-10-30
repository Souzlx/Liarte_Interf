"""Review priorities preserve the scope and uncertainty of monthly facts."""

from copy import deepcopy
from dataclasses import replace
from threading import Event
import unittest

from liarte_core.inventory import SCALE
from liarte_core.inventory_performance import analyze_product_performance
from liarte_core.inventory_priorities import analyze_product_priorities
from liarte_core.query import Cancelled
from tests.test_inventory_performance import extended_sample, prepared, report


def row(code="A", unit="KG", **changes):
    result = {
        "code": code, "name": "Produto " + code, "unit": unit,
        "sold": 20 * SCALE, "previous": 10 * SCALE, "change": 10 * SCALE,
        "percentage": 100, "status": "up", "reason": "",
        "stockQuantity": 100 * SCALE, "stockCost": 10000,
        "coverage": 140, "coverageReason": "Ritmo observado nas mesmas filiais.",
        "negativeStockPositionCount": 0,
    }
    result.update(changes)
    return result


def source(*rows, **changes):
    result = {
        "available": True, "window": 1, "units": tuple(sorted({r["unit"] for r in rows})),
        "selectionStart": "2026-01", "selectionEnd": "2026-02",
        "basePeriods": ("2026-01",), "targetPeriods": ("2026-02",),
        "baseLabel": "01/2026", "targetLabel": "02/2026", "targetPeriod": "2026-02",
        "baseDays": 31, "targetDays": 28, "excludedPeriods": (),
        "scope": "Recorte sintético", "notice": "Janelas de meses completos.", "reason": "",
        "rows": tuple(rows),
    }
    result.update(changes)
    return result


def classified(*rows, **options):
    return analyze_product_priorities(source(*rows), **options)


class InventoryPrioritiesTests(unittest.TestCase):
    def test_overlapping_reasons_count_one_product_unit_in_review(self):
        value = row(sold=5 * SCALE, change=-5 * SCALE, status="down", coverage=20)
        result = classified(value)
        self.assertEqual(result["counts"], {
            "review": 1, "coverage": 1, "decline": 1, "idle": 0, "capital": 1,
        })
        item, = result["rows"]
        self.assertEqual(item["categories"], ("coverage", "decline", "capital"))
        self.assertEqual(item["primaryCategory"], "coverage")
        self.assertEqual([r["key"] for r in item["reasons"]], list(item["categories"]))
        self.assertTrue(all(r["fact"] and r["nextStep"] for r in item["reasons"]))

    def test_coverage_threshold_is_strict_and_zero_is_a_known_value(self):
        for coverage, expected in ((0, 1), (29.999, 1), (30, 0), (None, 0), (-1, 0),
                                   (float("inf"), 0), (float("nan"), 0), (True, 0)):
            with self.subTest(coverage=coverage):
                result = classified(row(coverage=coverage))
                self.assertEqual(result["counts"]["coverage"], expected)
        result = classified(row(stockQuantity=0, coverage=0))
        self.assertEqual((result["counts"]["coverage"], result["counts"]["capital"]), (1, 0))

    def test_negative_positions_or_negative_total_cannot_request_coverage_review(self):
        for update in ({"negativeStockPositionCount": 1}, {"stockQuantity": -SCALE},
                       {"stockQuantity": None}, {"sold": None}, {"sold": -SCALE}):
            with self.subTest(update=update):
                self.assertEqual(classified(row(coverage=0, **update))["counts"]["coverage"], 0)
        item, = classified(row(coverage=0, negativeStockPositionCount=1))["rows"]
        self.assertEqual(item["negativeStockPositionCount"], 1)
        self.assertIn("saldo negativo", item["dataNotice"])

    def test_decline_requires_complete_comparison_positive_base_and_remaining_stock(self):
        good = row(sold=0, change=-10 * SCALE, status="no_positive")
        self.assertEqual(classified(good)["counts"]["decline"], 1)
        for update in ({"previous": None}, {"previous": 0}, {"previous": -SCALE},
                       {"sold": -SCALE}, {"change": None}, {"change": 0},
                       {"status": "insufficient"}, {"stockQuantity": 0},
                       {"stockQuantity": None}):
            with self.subTest(update=update):
                value = {**good, **update}
                self.assertEqual(classified(value)["counts"]["decline"], 0)
        incomplete = source(good, available=False, reason="Mês anterior indisponível.")
        result = analyze_product_priorities(incomplete)
        self.assertEqual(result["counts"]["decline"], 0)
        self.assertEqual(result["counts"]["idle"], 1)
        self.assertFalse(result["comparisonAvailable"])
        self.assertEqual(result["reason"], incomplete["reason"])

    def test_zero_net_sales_remains_distinct_from_no_sales_or_old_stock(self):
        value = row(sold=0, change=-10 * SCALE, status="no_positive", positiveMonths=1)
        item, = classified(value)["rows"]
        reason = next(r for r in item["reasons"] if r["key"] == "idle")
        self.assertEqual(reason["title"], "Saldo sem venda líquida")
        self.assertIn("compensadas por devoluções", reason["fact"])
        self.assertIn("não comprova ausência de vendas", reason["nextStep"])
        self.assertEqual(item["positiveMonths"], 1)
        for sold in (None, -SCALE, SCALE):
            with self.subTest(sold=sold):
                self.assertEqual(classified(row(sold=sold))["counts"]["idle"], 0)

    def test_capital_is_a_positive_cost_view_without_an_excess_threshold(self):
        result = classified(row(stockCost=1))
        self.assertEqual(result["counts"]["capital"], 1)
        self.assertEqual(result["counts"]["review"], 0)
        self.assertEqual(result["rows"][0]["primaryTitle"], "Maior capital")
        self.assertIn("não define excesso", result["rows"][0]["reasons"][0]["nextStep"])
        for cost, quantity in ((0, SCALE), (-1, SCALE), (None, SCALE), (100, 0), (100, None)):
            with self.subTest(cost=cost, quantity=quantity):
                self.assertEqual(classified(row(stockCost=cost, stockQuantity=quantity))[
                    "counts"]["capital"], 0)

    def test_sort_uses_exact_costs_and_puts_every_known_cost_before_missing(self):
        huge = 10**24
        values = [row("D", name="A ausente", stockCost=None, sold=0),
                  row("B", stockCost=huge), row("A", stockCost=huge + 1),
                  row("N", name="Z negativo", stockCost=-1, sold=0),
                  row("M", name="A negativo maior", stockCost=-100, sold=0),
                  row("C", stockCost=0, sold=0)]
        result = classified(*values)
        self.assertEqual([r["code"] for r in result["rows"]], ["A", "B", "C", "N", "M", "D"])
        self.assertEqual(result["rows"][0]["stockCost"], huge + 1)

    def test_same_product_in_different_units_is_never_merged(self):
        result = classified(row("A", "KG", sold=0), row("A", "L", sold=0))
        self.assertEqual(len(result["rows"]), 2)
        self.assertEqual(result["counts"]["review"], 2)
        self.assertEqual(result["units"], ("KG", "L"))
        self.assertEqual({r["unit"] for r in result["rows"]}, {"KG", "L"})
        self.assertTrue(all(r["stockQuantity"] == 100 * SCALE for r in result["rows"]))

    def test_ties_are_stable_by_folded_name_then_code_and_unit(self):
        values = [row("Z", name="Ácido"), row("A", name="acido"), row("L", name="Base")]
        result = classified(*values)
        self.assertEqual([r["code"] for r in result["rows"]], ["A", "Z", "L"])
        reverse = classified(*reversed(values))
        self.assertEqual(result["rows"], reverse["rows"])

    def test_input_rows_and_metadata_are_not_mutated(self):
        prepared = source(row(sold=0), selectionKey=("coorte",), excludedPeriods=("2026-03",))
        before = deepcopy(prepared)
        result = analyze_product_priorities(prepared)
        self.assertEqual(prepared, before)
        self.assertIsNot(result["rows"][0], prepared["rows"][0])
        for field in ("selectionKey", "excludedPeriods", "scope", "notice", "targetPeriod"):
            self.assertEqual(result[field], prepared[field])
        self.assertIn("não ao saldo atual", result["referenceNotice"])

    def test_partial_final_month_uses_the_accepted_complete_closing(self):
        prepared = report(end="2026-04")
        result = analyze_product_priorities(prepared)
        self.assertEqual(result["targetPeriod"], "2026-03")
        self.assertEqual(result["excludedPeriods"], ("2026-04",))
        self.assertEqual(result["targetLabel"], prepared["targetLabel"])
        for item in result["rows"]:
            self.assertTrue(all("03/2026" in reason["fact"] for reason in item["reasons"]))

    def test_missing_baseline_keeps_known_recent_capital_and_coverage(self):
        prepared = report(extended_sample(), start="2026-03", end="2026-06", window=3)
        result = analyze_product_priorities(prepared, coverage_days=3650)
        self.assertFalse(result["comparisonAvailable"])
        self.assertEqual(result["counts"]["decline"], 0)
        self.assertEqual(result["counts"]["capital"], 1)
        self.assertEqual(result["counts"]["coverage"], 1)
        self.assertEqual(result["rows"][0]["sold"], 33 * SCALE)
        self.assertEqual(result["rows"][0]["previous"], None)

    def test_missing_recent_month_keeps_the_explicit_reference_without_inventing_priorities(self):
        months, selection = prepared(extended_sample(), "2026-01", "2026-06")
        months = tuple(m for m in months if m["period"] != "2026-06")
        performance = analyze_product_performance(months, selection, window=1)
        result = analyze_product_priorities(performance)
        self.assertEqual(result["targetPeriod"], "2026-06")
        self.assertFalse(result["comparisonAvailable"])
        self.assertEqual(result["counts"], dict.fromkeys(
            ("review", "coverage", "decline", "idle", "capital"), 0
        ))
        self.assertIn("06/2026", result["reason"])

    def test_selected_branch_and_current_cohort_remain_the_accepted_report_scope(self):
        performance = report(branch="01", abc="A")
        result = analyze_product_priorities(performance)
        self.assertEqual(result["selectionKey"], performance["selectionKey"])
        self.assertEqual(result["scope"], performance["scope"])
        self.assertIn("coorte atual", result["scope"])
        self.assertEqual({r["code"] for r in result["rows"]}, {"A", "B"})
        accepted = {(r["code"], r["unit"]): r for r in performance["rows"]}
        for item in result["rows"]:
            original = accepted[item["code"], item["unit"]]
            self.assertEqual(item["stockQuantity"], original["stockQuantity"])
            self.assertEqual(item["stockBranches"], original["stockBranches"])

    def test_unobserved_recent_sales_do_not_become_zero_net_sales(self):
        data = replace(extended_sample(), sales=())
        prepared = report(data, start="2026-01", end="2026-06", window=3)
        result = analyze_product_priorities(prepared)
        self.assertEqual(result["counts"]["idle"], 0)
        self.assertEqual(result["counts"]["coverage"], 0)
        self.assertEqual(result["counts"]["decline"], 0)
        self.assertEqual(result["counts"]["capital"], 1)

    def test_warehouse_filter_keeps_capital_and_disables_sales_priorities(self):
        prepared = report(warehouse="01")
        result = analyze_product_priorities(prepared)
        self.assertGreater(result["counts"]["capital"], 0)
        self.assertEqual(result["counts"]["review"], 0)
        self.assertIn("armazém", result["reason"])

    def test_invalid_policy_duplicate_entities_and_noninteger_facts_are_rejected(self):
        for days in (0, 3651, True, 30.0, "30"):
            with self.subTest(days=days), self.assertRaises(ValueError):
                classified(row(), coverage_days=days)
        with self.assertRaisesRegex(ValueError, "mesmo produto"):
            classified(row(), row())
        for field in ("stockQuantity", "stockCost", "sold", "previous", "change"):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "escala inteira"):
                classified(row(**{field: True}))

    def test_cancellation_prevents_any_partial_report(self):
        cancel = Event()
        cancel.set()
        with self.assertRaises(Cancelled):
            analyze_product_priorities(source(row()), cancel=cancel)

    def test_cancellation_is_checked_during_a_large_classification(self):
        class Cancelling:
            calls = 0

            def is_set(self):
                self.calls += 1
                return self.calls >= 3

        cancel = Cancelling()
        rows = tuple(row(str(index)) for index in range(1025))
        with self.assertRaises(Cancelled):
            analyze_product_priorities(source(*rows), cancel=cancel)
        self.assertEqual(cancel.calls, 3)
