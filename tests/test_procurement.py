"""Referências verificadas por totais conhecidos, não por cópia do algoritmo."""

from dataclasses import replace
from decimal import Decimal, localcontext
from threading import Event
import unittest

from liarte_core.domain import Period, Selection, MunicipalRecord
from liarte_core.query import DatasetQuery, Cancelled
from liarte_core.procurement import ProcurementBuilder, change, ratio
from liarte_desktop.analytics import present
from tests.test_core import record


def fixture():
    return (
        record(
            0, period="2026-01", kg=200, fob_cents=18000, freight_cents=1800, insurance_cents=200
        ),
        record(
            1, period="2026-02", kg=100, fob_cents=27000, freight_cents=2700, insurance_cents=300
        ),
        record(
            2,
            period="2026-03",
            kg=1000,
            country="Estados Unidos",
            fob_cents=180000,
            freight_cents=18000,
            insurance_cents=2000,
        ),
    )


class ProcurementTests(unittest.TestCase):
    def setUp(self):
        self.selection = Selection(Period("2026-01", "2026-03"))
        self.provider = DatasetQuery(fixture())

    def query(self, **changes):
        return self.provider.query(replace(self.selection, **changes), Event(), lambda *_: None)

    def test_known_totals_weighted_reference_and_costs(self):
        data = self.query().procurement
        total = data.total
        self.assertEqual(
            (total.fob_cents, total.freight_cents, total.insurance_cents, total.kg),
            (225000, 22500, 2500, 1300),
        )
        self.assertEqual(total.value_cents, 250000)
        self.assertAlmostEqual(total.unit_price, Decimal(25) / 13, places=26)
        self.assertAlmostEqual(total.freight_per_kg, Decimal(9) / 52, places=26)
        self.assertEqual(total.freight_share, 9)
        self.assertAlmostEqual(data.months[-1].rolling.unit_price, Decimal(25) / 13, places=26)
        self.assertNotEqual(data.months[-1].rolling.unit_price, Decimal(2))
        self.assertIsNone(data.months[0].rolling)
        self.assertIsNone(data.months[1].rolling)
        self.assertTrue(data.months[2].rolling_price_valid)

    def test_unit_series_volume_and_monthly_change(self):
        view = present(self.query().procurement)
        self.assertEqual([p["value"] for p in view["series"]["price"]["points"]], [1, 3, 2])
        self.assertEqual(view["series"]["price"]["change"], "-33,3%")
        self.assertEqual(view["series"]["price"]["periodChange"], "+100,0%")
        self.assertEqual(view["series"]["weight"]["change"], "+900,0%")
        self.assertEqual(view["cards"][1]["value"], "US$ 1,923")
        self.assertAlmostEqual(
            view["series"]["weight"]["points"][-1]["movingValue"], 1300 / 3 / 1000
        )
        self.assertAlmostEqual(
            view["series"]["value"]["points"][-1]["movingValue"], 2500 / 3 / 1_000_000
        )

    def test_country_comparison_uses_weight_and_same_scope(self):
        view = present(self.query().procurement)
        usa, china = view["origins"]
        self.assertEqual(
            (usa["name"], usa["unit"], usa["kg"], usa["share"], usa["difference"]),
            ("Estados Unidos", "2,000", "1.000", "80,0%", "+4,0%"),
        )
        self.assertEqual(
            (china["name"], china["unit"], china["difference"]), ("China", "1,667", "-13,3%")
        )
        self.assertEqual(usa["monthlyChange"], "—")
        self.assertEqual(china["monthlyChange"], "—")
        data = self.query(country_values=("China",)).procurement
        self.assertEqual(data.total.kg, 300)
        self.assertAlmostEqual(data.total.unit_price, Decimal(5) / 3, places=26)
        self.assertEqual(len(data.origins), 1)

    def test_missing_month_is_not_connected_or_used_as_zero_price(self):
        provider = DatasetQuery((fixture()[0], fixture()[2]))
        result = provider.query(self.selection, Event(), lambda *_: None)
        self.assertEqual(result.monthly[1], ("2026-02", 0))
        view = present(result.procurement)
        self.assertIsNone(view["series"]["price"]["points"][1]["value"])
        self.assertIsNone(view["series"]["price"]["points"][2]["movingValue"])
        self.assertFalse(view["series"]["price"]["hasRolling"])
        self.assertEqual(view["series"]["price"]["change"], "—")
        self.assertEqual(view["series"]["value"]["change"], "—")

    def test_no_borrowing_of_months_outside_selected_period(self):
        data = self.query(period=Period("2026-02", "2026-03")).procurement
        self.assertTrue(all(m.rolling is None for m in data.months))
        self.assertEqual(present(data)["cards"][1]["value"], "—")

    def test_zero_weight_records_preserve_published_totals_and_raise_quality_note(self):
        provider = DatasetQuery(
            fixture()
            + (
                record(
                    3, period="2026-02", kg=0, fob_cents=100, freight_cents=0, insurance_cents=0
                ),
            )
        )
        result = provider.query(self.selection, Event(), lambda *_: None)
        data = result.procurement
        self.assertEqual(result.totals.value_cents, 250100)
        self.assertEqual(data.total.value_cents, result.totals.value_cents)
        self.assertEqual(data.total.unit_price, ratio(250100, 130000))
        self.assertEqual(data.months[-1].aggregate.unit_price, 2)
        self.assertEqual(data.months[-1].rolling.unit_price, ratio(250100, 130000))
        view = present(data)
        self.assertTrue(view["weightWarning"])
        self.assertEqual(view["origins"][1]["unweighed"], "US$ 1,00")
        # A wholly zero-weight month has no unit value, not a zero price.
        provider = DatasetQuery((record(4, period="2026-02", kg=0),))
        data = provider.query(self.selection, Event(), lambda *_: None).procurement
        self.assertIsNone(data.total.unit_price)
        self.assertIsNone(data.months[1].aggregate.unit_price)
        self.assertIsNone(present(data)["origins"][0]["price"])

    def test_valueless_zero_weight_does_not_invalidate_real_prices(self):
        provider = DatasetQuery(
            fixture()
            + (record(3, period="2026-02", kg=0, fob_cents=0, freight_cents=0, insurance_cents=0),)
        )
        data = provider.query(self.selection, Event(), lambda *_: None).procurement
        self.assertIsNotNone(data.total.unit_price)

    def test_zero_price_is_observed_but_zero_comparison_base_is_undefined(self):
        self.assertIsNone(change(2, 0))
        self.assertEqual(change(0, 2), -100)
        self.assertIsNone(ratio(10, 0))
        self.assertEqual(ratio(0, 10), 0)
        row = record(0, fob_cents=0, freight_cents=0, insurance_cents=0, kg=100)
        builder = ProcurementBuilder((row.period,))
        builder.add(row)
        self.assertEqual(builder.finish().total.unit_price, 0)

    def test_empty_scope_has_no_fabricated_reference(self):
        view = present(self.query(country_values=("País sem importações",)).procurement)
        self.assertFalse(view["comparable"])
        self.assertEqual(view["origins"], [])
        self.assertIsNone(view["reference"])
        self.assertEqual(view["series"]["price"]["change"], "—")
        self.assertEqual(view["cards"][0]["value"], "—")

    def test_mix_is_explicit_and_origin_comparison_requires_one_code(self):
        provider = DatasetQuery((fixture()[0], replace(fixture()[1], ncm="29161230")))
        data = provider.query(self.selection, Event(), lambda *_: None).procurement
        view = present(data)
        self.assertFalse(view["comparable"])
        self.assertEqual(view["context"], "Média da seleção")
        self.assertIn("mix", view["note"])
        view = present(self.query().procurement)
        self.assertTrue(view["comparable"])
        self.assertIn("NCM", view["context"])

    def test_municipal_is_fob_and_never_fabricates_cif_or_freight(self):
        rows = tuple(
            MunicipalRecord(
                r.identifier,
                r.period,
                "2916",
                "Ácidos e derivados",
                r.state,
                r.country,
                "São Paulo",
                r.fob_cents,
                r.kg,
            )
            for r in fixture()
        )
        data = (
            DatasetQuery(rows)
            .query(replace(self.selection, kind="municipal"), Event(), lambda *_: None)
            .procurement
        )
        self.assertEqual(data.total.value_cents, 225000)
        self.assertIsNone(data.total.freight_cents)
        self.assertIsNone(data.total.freight_per_kg)
        self.assertIsNone(data.total.freight_share)
        view = present(data)
        self.assertEqual(set(view["series"]), {"price", "value", "weight", "valueChange"})
        self.assertEqual(view["basis"], "FOB")
        self.assertIn("SH4", view["note"])
        self.assertNotIn("CIF", str(view))
        self.assertNotIn("Frete no", str(view))

    def test_top3_concentration_uses_all_origins_not_only_visible_eight(self):
        rows = tuple(
            record(
                i,
                country=f"País {i}",
                fob_cents=(10 - i) * 100,
                freight_cents=0,
                insurance_cents=0,
                kg=10 - i,
            )
            for i in range(10)
        )
        data = (
            DatasetQuery(rows)
            .query(Selection(Period("2026-04", "2026-04")), Event(), lambda *_: None)
            .procurement
        )
        self.assertAlmostEqual(data.top3_share, Decimal(2700) / 55, places=26)
        self.assertEqual(len(present(data)["origins"]), 10)  # UI pagination, not data truncation.

    def test_search_sort_and_page_do_not_change_procurement_scope(self):
        result = self.query()
        changed = self.query(
            search="Estados Unidos", descending=True, sort_column=10, page=5, page_size=25
        )
        self.assertIs(result.procurement, changed.procurement)
        self.assertEqual(changed.table_count, 1)
        self.assertEqual(changed.totals.records, 3)
        self.assertEqual(self.provider.cache_info["scope_builds"], 1)

    def test_finalization_remains_cancellable(self):
        builder = ProcurementBuilder(self.selection.period.months)
        for row in fixture():
            builder.add(row)

        def stop():
            raise Cancelled()

        with self.assertRaises(Cancelled):
            builder.finish(stop)

    def test_calculations_do_not_inherit_display_precision(self):
        with localcontext() as context:
            context.prec = 4
            data = self.query().procurement
            self.assertTrue(
                str(data.total.unit_price).startswith("1.9230769230769230769230769230769")
            )
            self.assertTrue(str(change(2, 3)).startswith("-33.3333333333333333333333"))
            self.assertEqual(present(data)["cards"][1]["value"], "US$ 1,923")

    def test_large_values_and_tiny_unit_values_remain_finite(self):
        provider = DatasetQuery(
            (record(0, fob_cents=10**30 + 1, freight_cents=1, insurance_cents=0, kg=10**20),)
        )
        data = provider.query(
            Selection(Period("2026-04", "2026-04")), Event(), lambda *_: None
        ).procurement
        self.assertEqual(data.total.value_cents, 10**30 + 2)
        self.assertIsNotNone(data.total.unit_price)
        self.assertEqual(data.total.unit_price, ratio(10**30 + 2, 10**22))
