"""Independent reference facts detect import and analytical regressions."""

from dataclasses import replace
from datetime import date
from threading import Event
import unittest
from unittest.mock import patch

from liarte_core.inventory import SCALE, Balance, Closing, Product, Sale
from liarte_core.inventory_reconciliation import InventoryReference, reconcile_inventory
from liarte_core.inventory_source import inventory_from_records
from liarte_core.query import Cancelled


def sample(year=2032, code="SYN-A"):
    return inventory_from_records(
        as_of=date(year, 4, 15),
        source_name="synthetic.pbix",
        source_hash="b" * 64,
        products=(
            Product(code, "Produto A", "Grupo", "MP", "KG"),
            Product("SYN-B", "Produto B", "Grupo", "MP", "L"),
            Product("SYN-C", "Produto C", "Grupo", "PA", "UN"),
        ),
        balances=(
            Balance(code, "F1", "A1", "KG", 10 * SCALE + 1, 2**54 + 3),
            Balance(code, "F1", "A2", "KG", 5 * SCALE, 601),
            Balance("SYN-B", "F2", "A1", "L", -2 * SCALE, -101),
            Balance("SYN-C", "F1", "A1", "UN", 0, 0),
        ),
        closings=(
            Closing(code, "F1", "A1", "KG", f"{year}-02", 4 * SCALE, 4, 1.5, 20),
            Closing(code, "F1", "A2", "KG", f"{year}-02", 2 * SCALE, 3, 0, 0),
            Closing(code, "F1", "A1", "KG", f"{year}-03", 0, 0, None, None),
            Closing("SYN-B", "F2", "A1", "L", f"{year}-03", -4 * SCALE, -501, -1, -20),
            Closing("SYN-C", "F1", "A1", "UN", f"{year}-03", 10 * SCALE, 1000, 2, 15),
        ),
        sales=(
            Sale(code, "F1", "KG", date(year, 2, 10), 2 * SCALE, 200, True),
            Sale(code, "F1", "KG", date(year, 2, 15), 0, 0, True),
            Sale("SYN-B", "F2", "L", date(year, 3, 3), -SCALE, -2, False),
            Sale(code, "F1", "KG", date(year, 3, 10), SCALE, 110, True),
            Sale("SYN-C", "F1", "UN", date(year, 4, 3), 0, 0, True),
        ),
    )


def reference(data):
    return InventoryReference(
        data.as_of,
        data.source_name,
        data.source_hash,
        data.balances,
        data.closings,
        data.sales,
        {"synthetic": {"rows": 5, "accepted": 5, "deleted": 0, "output": 5}},
    )


class InventoryReconciliationTests(unittest.TestCase):
    def test_equal_reference_preserves_units_exact_totals_unknowns_and_counts(self):
        data = sample()
        report = reconcile_inventory(reference(data), data)
        self.assertEqual(report["status"], "equal")
        self.assertTrue(report["comparable"])
        self.assertEqual(report["differences"], ())
        self.assertGreater(report["checks"]["unknown"], 0)
        self.assertEqual(
            report["checks"]["total"],
            sum(
                report["checks"][field]
                for field in ("passed", "different", "missing", "extra", "unknown")
            ),
        )
        cost = next(
            row
            for row in report["totals"]
            if row["section"] == "current_indicators" and row["metric"] == "cost"
        )
        self.assertEqual(cost["sourceValue"], 2**54 + 503)
        self.assertEqual(cost["appValue"], 2**54 + 503)
        self.assertEqual(cost["difference"], 0)
        self.assertEqual(cost["valueUnit"], "R$")
        current_units = {
            row["unit"]
            for row in report["totals"]
            if row["section"] == "current_indicators" and row["metric"] == "quantity"
        }
        self.assertEqual(current_units, {"KG", "L", "UN"})
        april = next(
            row
            for row in report["totals"]
            if row["section"] == "monthly_totals"
            and row["period"] == "2032-04"
            and row["metric"] == "stockCost"
        )
        self.assertIsNone(april["sourceValue"])
        self.assertIsNone(april["appValue"])
        self.assertEqual(april["status"], "unknown")

    def test_per_position_offsets_are_detected_even_when_the_global_total_matches(self):
        data = sample()
        changed = replace(
            data,
            balances=(
                replace(data.balances[0], cost=data.balances[0].cost + 1),
                replace(data.balances[1], cost=600),
                *data.balances[2:],
            ),
        )
        report = reconcile_inventory(reference(data), changed)
        self.assertEqual(report["status"], "different")
        positions = [row for row in report["differences"] if row["section"] == "balances"]
        self.assertEqual({row["warehouse"] for row in positions}, {"A1", "A2"})
        self.assertEqual({row["difference"] for row in positions}, {-1, 1})
        cost = next(
            row
            for row in report["totals"]
            if row["section"] == "current_indicators" and row["metric"] == "cost"
        )
        self.assertEqual(cost["status"], "passed")

    def test_zero_record_missing_is_not_an_equal_or_unknown_value(self):
        data = sample()
        changed = replace(data, balances=data.balances[:-1])
        report = reconcile_inventory(reference(data), changed)
        self.assertEqual(report["status"], "different")
        missing = [row for row in report["differences"] if row["section"] == "balances"]
        self.assertTrue(missing)
        self.assertTrue(
            all(
                row["status"] == "missing"
                and row["sourceValue"] == 0
                and row["sourcePresent"]
                and not row["appPresent"]
                for row in missing
            )
        )
        self.assertTrue(all(row["difference"] is None for row in missing))

    def test_reassigned_warehouse_retains_missing_and_extra_positions(self):
        data = sample()
        changed = replace(
            data, balances=(replace(data.balances[0], warehouse="OTHER"), *data.balances[1:])
        )
        report = reconcile_inventory(reference(data), changed)
        raw = [row for row in report["differences"] if row["section"] == "balances"]
        self.assertEqual({row["status"] for row in raw}, {"missing", "extra"})
        self.assertEqual({row["warehouse"] for row in raw}, {"A1", "OTHER"})

    def test_missing_ratio_and_zero_ratio_are_different_availability(self):
        data = sample()
        changed = replace(
            data,
            closings=(
                *data.closings[:2],
                replace(data.closings[2], turnover=0),
                *data.closings[3:],
            ),
        )
        report = reconcile_inventory(reference(data), changed)
        found = [
            row
            for row in report["differences"]
            if row["section"] == "closings" and row["metric"] == "turnover"
        ]
        self.assertEqual(len(found), 1)
        self.assertIsNone(found[0]["sourceValue"])
        self.assertEqual(found[0]["appValue"], 0)
        self.assertEqual(found[0]["status"], "different")

    def test_legacy_positive_exit_unknown_is_not_coerced_to_false_or_true(self):
        data = sample()
        for flag in (True, False):
            source = replace(
                data, sales=(replace(data.sales[0], had_positive=flag), *data.sales[1:])
            )
            actual = replace(
                data, sales=(replace(data.sales[0], had_positive=None), *data.sales[1:])
            )
            report = reconcile_inventory(reference(source), actual)
            row = next(
                row
                for row in report["differences"]
                if row["section"] == "sales" and row["metric"] == "had_positive"
            )
            self.assertEqual(row["sourceValue"], flag)
            self.assertIsNone(row["appValue"])
            self.assertEqual(row["status"], "different")

    def test_daily_deletion_and_retroactive_correction_are_detected(self):
        data = sample()
        for changes in (
            data.sales[1:],
            (replace(data.sales[0], quantity=2 * SCALE + 1), *data.sales[1:]),
        ):
            with self.subTest(changes=changes):
                report = reconcile_inventory(reference(data), replace(data, sales=changes))
                self.assertEqual(report["status"], "different")
                self.assertTrue(any(row["section"] == "sales" for row in report["differences"]))
                self.assertTrue(
                    any(row["section"] == "monthly_sales" for row in report["differences"])
                )

    def test_monthly_net_sales_are_not_multiplied_by_the_number_of_warehouses(self):
        data = sample()
        report = reconcile_inventory(reference(data), data)
        row = next(
            row
            for row in report["totals"]
            if row["section"] == "monthly_totals"
            and row["period"] == "2032-02"
            and row["unit"] == "KG"
            and row["metric"] == "salesQuantity"
        )
        self.assertEqual(row["sourceValue"], 2 * SCALE)
        self.assertEqual(row["appValue"], 2 * SCALE)
        self.assertEqual(row["difference"], 0)

    def test_current_analytical_bug_is_detected_when_imported_facts_match(self):
        from liarte_core import inventory_reconciliation as domain

        data = sample()
        real = domain.analyze_inventory

        def broken(*args, **kwargs):
            result = real(*args, **kwargs)
            return replace(result, total_cost=result.total_cost + 1)

        with patch.object(domain, "analyze_inventory", side_effect=broken):
            report = reconcile_inventory(reference(data), data)
        self.assertEqual(report["checks"]["different"], 1)
        self.assertEqual(report["differences"][0]["section"], "current_indicators")
        self.assertEqual(report["differences"][0]["difference"], 1)

    def test_monthly_analytical_bugs_are_detected_independently_from_source_facts(self):
        from liarte_core import inventory_reconciliation as domain

        data = sample()
        real = domain.analyze_monthly_inventory

        def broken(*args, **kwargs):
            result = real(*args, **kwargs)
            first = dict(result[0], stockCost=result[0]["stockCost"] + 1)
            first["saleRows"] = [
                dict(row, quantity=row["quantity"] + 1) for row in first["saleRows"]
            ]
            return (first, *result[1:])

        with patch.object(domain, "analyze_monthly_inventory", side_effect=broken):
            report = reconcile_inventory(reference(data), data)
        self.assertEqual(report["status"], "different")
        self.assertEqual(
            {row["section"] for row in report["differences"]}, {"monthly_totals", "monthly_sales"}
        )
        self.assertTrue(all(row["difference"] == 1 for row in report["differences"]))

    def test_date_and_revision_mismatches_are_not_approved_or_compared(self):
        data = sample()
        for changed in (
            replace(data, source_hash="a" * 64),
            replace(data, as_of=date(2032, 4, 16)),
        ):
            with self.subTest(changed=changed.source_hash):
                with patch(
                    "liarte_core.inventory_reconciliation.analyze_inventory",
                    side_effect=AssertionError("not comparable"),
                ):
                    report = reconcile_inventory(reference(data), changed)
                self.assertEqual(report["status"], "not_comparable")
                self.assertFalse(report["comparable"])
                self.assertEqual(report["checks"]["total"], 0)
                self.assertEqual(report["differences"], ())
                self.assertEqual(report["totals"], ())

    def test_new_dates_identifiers_and_row_order_do_not_require_rule_changes(self):
        for year, code in ((2028, "NEW-CODE"), (2034, "ANOTHER-CODE")):
            data = sample(year, code)
            expected = reference(data)
            reordered = replace(
                data,
                balances=tuple(reversed(data.balances)),
                closings=tuple(reversed(data.closings)),
                sales=tuple(reversed(data.sales)),
            )
            report = reconcile_inventory(expected, reordered)
            self.assertEqual(report["status"], "equal")
            self.assertEqual(report["context"]["start"], f"{year}-02")
            self.assertEqual(report["context"]["end"], f"{year}-04")

    def test_reference_and_actual_duplicate_keys_or_invalid_values_are_rejected(self):
        data = sample()
        expected = reference(data)
        variants = (
            replace(expected, balances=(*expected.balances, expected.balances[0])),
            replace(expected, sales=(*expected.sales, expected.sales[0])),
            replace(expected, closings=(*expected.closings, expected.closings[0])),
            replace(expected, balances=(replace(expected.balances[0], quantity=1.0),)),
            replace(expected, closings=(replace(expected.closings[0], turnover=float("nan")),)),
            replace(expected, sales=(replace(expected.sales[0], had_positive=1),)),
        )
        for invalid in variants:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                reconcile_inventory(invalid, data)
        with self.assertRaises(ValueError):
            reconcile_inventory(
                expected, replace(data, balances=(*data.balances, data.balances[0]))
            )

    def test_duplicate_application_output_is_rejected_instead_of_silently_overwritten(self):
        from liarte_core import inventory_reconciliation as domain

        data = sample()
        real = domain.analyze_monthly_inventory

        def broken(*args, **kwargs):
            months = real(*args, **kwargs)
            first = dict(months[0], saleRows=[*months[0]["saleRows"], months[0]["saleRows"][0]])
            return (first, *months[1:])

        with patch.object(domain, "analyze_monthly_inventory", side_effect=broken):
            with self.assertRaisesRegex(ValueError, "duplicadas"):
                reconcile_inventory(reference(data), data)

    def test_cancelled_processing_never_returns_an_approved_report(self):
        data = sample()
        cancel = Event()
        cancel.set()
        with self.assertRaises(Cancelled):
            reconcile_inventory(reference(data), data, cancel=cancel)
        cancel.clear()
        from liarte_core import inventory_reconciliation as domain

        real = domain._Collector.check

        def stop(collector, *args, **kwargs):
            result = real(collector, *args, **kwargs)
            cancel.set()
            return result

        with patch.object(domain._Collector, "check", new=stop):
            with self.assertRaises(Cancelled):
                reconcile_inventory(reference(data), data, cancel=cancel)

    def test_success_keeps_only_compact_totals_and_no_per_position_match_rows(self):
        data = sample()
        many = replace(
            data,
            balances=tuple(Balance("SYN-A", "F1", str(i), "KG", 1, 1) for i in range(1000)),
            closings=(),
            sales=(),
        )
        report = reconcile_inventory(reference(many), many)
        self.assertEqual(report["status"], "equal")
        self.assertGreater(report["checks"]["total"], 4000)
        self.assertLessEqual(len(report["totals"]), 8)
        self.assertEqual(report["differences"], ())

    def test_history_over_twenty_years_is_covered_in_explicit_analysis_batches(self):
        data = sample()
        extended = replace(
            data, sales=(replace(data.sales[0], day=date(2000, 1, 10)), *data.sales[1:])
        )
        report = reconcile_inventory(reference(extended), extended)
        self.assertEqual(report["status"], "equal")
        self.assertEqual(report["context"]["start"], "2000-01")
        self.assertEqual(report["context"]["monthCount"], 388)
        self.assertEqual(report["sections"]["monthly_totals"]["sourceRows"], 388)
