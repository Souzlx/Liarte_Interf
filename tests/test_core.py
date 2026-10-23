from __future__ import annotations

import ast
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from threading import Event
import unittest

from liarte_core import demo, domain
from liarte_core.demo import Cancelled, DemoProvider, catalog
from liarte_core.domain import (
    ImportRecord,
    Period,
    Selection,
    compact_money,
    money,
    number,
    period_label,
)


def record(i=0, **changes):
    values = dict(
        identifier=i,
        period="2026-04",
        ncm="29161220",
        product="Acrilato de etila",
        state="SP",
        country="China",
        port="Porto de Santos",
        fob_cents=100_000,
        freight_cents=10_000,
        insurance_cents=1000,
        kg=1000,
    )
    values.update(changes)
    return ImportRecord(**values)


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.provider = DemoProvider(3)
        self.provider._rows = (
            record(0),
            record(1, fob_cents=300_000, kg=3000),
            record(2, period="2026-05", country="Estados Unidos", state="RJ", fob_cents=500_000),
        )
        self.selection = Selection(Period("2026-04", "2026-05"))

    def query(self, **changes):
        return self.provider.query(replace(self.selection, **changes), Event(), lambda *_: None)

    def test_period_round_trip_across_year(self):
        self.assertEqual(Period("2025-12", "2026-02").months, ("2025-12", "2026-01", "2026-02"))

    def test_invalid_periods_and_reversed_range(self):
        for value in ("2026-00", "2026-13", "26-01", "2026-1", "2026-01x", "1996-12", "", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                domain.period_index(value)
        with self.assertRaises(ValueError):
            Period("2026-02", "2026-01")

    def test_month_label_is_portuguese(self):
        self.assertEqual(period_label("2026-01"), "Janeiro de 2026")

    def test_catalog_matches_baseline_unique_ncms(self):
        items = catalog()
        self.assertEqual(len(items), 35)
        self.assertEqual(sum(len(x["products"]) for x in items), 54)
        self.assertTrue(all(len(x["ncm"]) == 8 and x["name"] for x in items))

    def test_cif_is_exact_sum(self):
        r = record(fob_cents=12345, freight_cents=678, insurance_cents=90)
        self.assertEqual(r.cif_cents, 13113)
        self.assertEqual(r.unit_price, Decimal("0.13113"))

    def test_zero_weight_has_no_unit_price(self):
        self.assertIsNone(record(kg=0).unit_price)

    def test_invalid_record_is_rejected(self):
        for values in (
            {"ncm": "123"},
            {"state": "São Paulo"},
            {"kg": -1},
            {"kg": True},
            {"fob_cents": 12.4},
            {"product": ""},
        ):
            with self.subTest(values=values), self.assertRaises(ValueError):
                record(**values)

    def test_financial_format_is_numeric_and_localized(self):
        self.assertEqual(money(123456789), "US$ 1.234.567,89")
        self.assertEqual(number(Decimal("1.2345"), 3), "1,235")
        self.assertEqual(number(None, 3), "—")
        self.assertEqual(number(1234567), "1.234.567")

    def test_compact_money_keeps_currency(self):
        self.assertEqual(compact_money(123_000_000), "US$ 1,2 mi")
        self.assertEqual(compact_money(150), "US$ 1,50")

    def test_aggregation_uses_weighted_price(self):
        result = self.query()
        self.assertEqual(result.totals.cif_cents, 933000)
        self.assertEqual(result.totals.kg, 5000)
        self.assertEqual(result.totals.price, Decimal("1.866"))
        self.assertEqual(result.totals.ncms, 1)

    def test_period_filter_is_inclusive(self):
        result = self.query(period=Period("2026-04", "2026-04"))
        self.assertEqual(result.totals.records, 2)

    def test_combined_filters(self):
        self.assertEqual(self.query(ncm="29161220", country="China", state="SP").totals.records, 2)
        self.assertEqual(self.query(country="China", state="RJ").totals.records, 0)

    def test_search_does_not_change_metrics_or_charts(self):
        all_rows = self.query()
        searched = self.query(search="estados unidos")
        self.assertEqual(searched.table_count, 1)
        self.assertEqual(searched.totals, all_rows.totals)
        self.assertEqual(searched.monthly, all_rows.monthly)
        self.assertEqual(searched.countries, all_rows.countries)

    def test_search_is_accent_insensitive(self):
        self.assertEqual(self.query(search="ACRILATO ETILA").table_count, 3)
        self.assertEqual(self.query(search="SAO PAULO").table_count, 0)

    def test_sort_is_numeric_before_paging(self):
        self.provider._rows = tuple(record(i, fob_cents=(100 - i) * 1000) for i in range(100))
        result = self.query(sort_column=6, descending=False, page_size=25, page=2)
        self.assertEqual([r.fob_cents for r in result.rows], list(range(26000, 51000, 1000)))

    def test_page_is_clamped_to_last(self):
        result = self.query(page=999)
        self.assertEqual(result.page, 1)
        self.assertEqual(result.pages, 1)

    def test_missing_price_sorts_last_both_directions(self):
        self.provider._rows = (record(0, kg=0), record(1))
        for descending in (False, True):
            self.assertEqual(self.query(sort_column=11, descending=descending).rows[-1].kg, 0)

    def test_invalid_selection_is_rejected(self):
        for change in (
            {"page": True},
            {"page_size": 1000},
            {"sort_column": 12},
            {"search": "a" * 251},
            {"state": "xx"},
            {"ncm": "1"},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                replace(self.selection, **change)

    def test_filters_must_belong_to_demo(self):
        for change in (
            {"country": "País inexistente"},
            {"state": "ZZ"},
            {"ncm": "00000000"},
            {"period": Period("2024-01", "2024-01")},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.query(**change)

    def test_cancel_does_not_publish_partial_dataset(self):
        source = DemoProvider(5000)
        cancel = Event()

        def progress(*_):
            cancel.set()

        with self.assertRaises(Cancelled):
            source.query(self.selection, cancel, progress)
        self.assertIsNone(source._rows)

    def test_zero_results_is_valid(self):
        result = self.query(search="não existe")
        self.assertEqual(
            (result.table_count, result.pages, result.page, result.rows), (0, 1, 1, ())
        )

    def test_synthetic_provider_is_deterministic(self):
        a = DemoProvider(200).query(self.selection, Event(), lambda *_: None)
        b = DemoProvider(200).query(self.selection, Event(), lambda *_: None)
        self.assertEqual(a, b)

    def test_chart_months_reconcile(self):
        result = self.query()
        self.assertEqual(sum(v for _, v in result.monthly), result.totals.cif_cents)
        self.assertEqual(sum(v for _, v in result.countries), result.totals.cif_cents)

    def test_core_has_no_ui_or_network_dependencies(self):
        for module in (demo, domain):
            tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    self.assertFalse(
                        (node.module or "").startswith(("PySide6", "fastapi", "urllib", "requests"))
                    )
                if isinstance(node, ast.Import):
                    self.assertTrue(
                        all(
                            not v.name.startswith(("PySide6", "fastapi", "urllib", "requests"))
                            for v in node.names
                        )
                    )
