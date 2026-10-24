"""Regressões sintéticas dos contratos de estoque auditados em outubro/2026."""

import gzip
import json
import math
import statistics
import tempfile
import unittest
import zipfile
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from threading import Event
from unittest.mock import patch

from liarte_core import inventory, inventory_io, inventory_monthly
from liarte_core.inventory import (
    SCALE,
    Balance,
    Closing,
    InventoryData,
    Product,
    Sale,
    StockSelection,
    analyze_inventory,
    closing_summary,
)
from liarte_core.inventory_io import read_pbix, read_snapshot, validate_data, write_snapshot
from liarte_core.inventory_monthly import analyze_monthly_inventory
from liarte_core.query import Cancelled


def fixture():
    return InventoryData(
        date(2026, 10, 24),
        "Base sintética.pbix",
        "a" * 64,
        (Product("A", "Ácido", "Químicos", "MP", "UN"),),
        (Balance("A", "01", "01", "UN", SCALE, 100),),
        (Closing("A", "01", "01", "UN", "2026-09", SCALE, 100, 1.0, 30.0),),
        (Sale("A", "01", "UN", date(2026, 1, 1), SCALE, 100),),
        (("01", "Filial"),),
        (("01", "Principal"),),
    )


def many_products(size):
    return replace(
        fixture(),
        as_of=date(2026, 1, 31),
        products=tuple(
            Product(str(i), "Produto " + str(i), "Grupo", "MP", "UN") for i in range(size)
        ),
        balances=tuple(Balance(str(i), "01", "01", "UN", SCALE, 100) for i in range(size)),
        closings=tuple(
            Closing(str(i), "01", "01", "UN", "2026-01", SCALE, 100, 1.0, 30.0) for i in range(size)
        ),
        sales=tuple(Sale(str(i), "01", "UN", date(2006, 1, 1), SCALE, 100) for i in range(size)),
    )


class AuditStockCoreTests(unittest.TestCase):
    def test_sparse_statistics_include_241_complete_months_and_sample_std(self):
        data = validate_data(many_products(3))
        row = analyze_inventory(data, StockSelection("2006-01", "2026-01")).rows[0]
        self.assertEqual(row.full_months, 241)
        self.assertAlmostEqual(row.monthly_mean, 1 / 241)
        self.assertAlmostEqual(row.monthly_std, 1 / math.sqrt(241))
        self.assertAlmostEqual(row.cv, math.sqrt(241))

    def test_sparse_statistics_preserve_fractional_negative_and_nearly_equal_demand(self):
        selection = StockSelection("2026-01", "2026-03")
        for quantities in (
            (125_001, 0, 375_003),
            (SCALE, -SCALE, 3 * SCALE),
            (10**22, 10**22 + 1, 10**22 + 2),
        ):
            data = replace(
                fixture(),
                sales=tuple(
                    Sale("A", "01", "UN", date(2026, month, 1), qty, 0)
                    for month, qty in enumerate(quantities, 1)
                ),
            )
            row = analyze_inventory(validate_data(data), selection).rows[0]
            self.assertEqual(row.full_months, 3)
            self.assertAlmostEqual(row.monthly_mean, sum(quantities) / 3 / SCALE)
            # Exact scaled integers retain the 1-millionth deviation even when
            # converting each large observation to float would erase it.
            self.assertAlmostEqual(row.monthly_std, statistics.stdev(quantities) / SCALE)
            if min(quantities) < 0:
                self.assertIsNone(row.cv)
            else:
                self.assertAlmostEqual(row.cv, row.monthly_std / row.monthly_mean)

    def test_cancel_interrupts_statistics_of_large_valid_data_in_a_bounded_batch(self):
        data = validate_data(many_products(5_000))
        cancel = Event()
        sqrt = math.sqrt
        calls = 0

        def interrupt(value):
            nonlocal calls
            calls += 1
            if calls == 600:
                cancel.set()
            return sqrt(value)

        with (
            patch.object(inventory.math, "sqrt", side_effect=interrupt),
            self.assertRaises(Cancelled),
        ):
            analyze_inventory(data, StockSelection("2006-01", "2026-01"), cancel=cancel)
        self.assertGreaterEqual(calls, 600)
        self.assertLessEqual(calls, 1_024)

    def test_cancel_interrupts_monthly_formatting_without_returning_partial_results(self):
        data = validate_data(many_products(5_000))
        cancel = Event()
        quantity = inventory_monthly._quantity
        calls = 0

        def interrupt(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 600:
                cancel.set()
            return quantity(*args, **kwargs)

        with (
            patch.object(inventory_monthly, "_quantity", side_effect=interrupt),
            self.assertRaises(Cancelled),
        ):
            analyze_monthly_inventory(
                data, StockSelection("2026-01", "2026-01"), None, cancel=cancel
            )
        self.assertGreaterEqual(calls, 600)
        self.assertLessEqual(calls, 1_024)

    def test_cancelled_analyses_stop_at_entry(self):
        cancel = Event()
        cancel.set()
        selected = StockSelection("2026-09", "2026-10")
        for analyze in (analyze_inventory, analyze_monthly_inventory):
            with self.subTest(analyze=analyze.__name__), self.assertRaises(Cancelled):
                analyze(fixture(), selected, cancel=cancel)

    def test_monthly_facts_remain_complete_and_share_low_turnover_records(self):
        data = many_products(1_100)
        (month,) = analyze_monthly_inventory(data, StockSelection("2026-01", "2026-01"))
        self.assertEqual(len(month["stockRows"]), 1_100)
        self.assertEqual(len(month["lowTurnover"]), 1_100)
        facts = {(row["code"], row["warehouse"]): row for row in month["stockRows"]}
        for row in month["lowTurnover"]:
            self.assertIs(row, facts[row["code"], row["warehouse"]])
        self.assertEqual(sum(row["quantity"] for row in month["stockRows"]), 1_100 * SCALE)

    def test_partial_closing_is_labelled_and_never_compared_with_a_complete_month(self):
        data = replace(
            fixture(),
            closings=fixture().closings
            + (Closing("A", "01", "01", "UN", "2026-10", 2 * SCALE, 200, 1.0, 30.0),),
        )
        result = analyze_inventory(data, StockSelection("2026-09", "2026-10"))
        self.assertTrue(result.trend[-1]["partial"])
        self.assertEqual(result.history_summary["period"], "Fechamento parcial · 10/2026")
        self.assertIsNone(result.history_summary["changeValue"])
        self.assertEqual(result.history_summary["change"], "")
        points = [dict(raw=100, label="09/2026", partial=True), dict(raw=200, label="10/2026")]
        self.assertIsNone(closing_summary(points)["changeValue"])
        self.assertIsNone(
            analyze_monthly_inventory(data, StockSelection("2026-09", "2026-10"))[-1]["stockChange"]
        )

    def test_empty_sales_source_is_unavailable_in_every_month(self):
        data = replace(fixture(), sales=())
        result = analyze_inventory(data, StockSelection("2026-09", "2026-11"))
        self.assertTrue(all(row["quantity"] is None for row in result.sales_months))
        self.assertIsNone(result.rows[0].monthly_mean)
        self.assertIsNone(result.rows[0].coverage)
        months = analyze_monthly_inventory(data, StockSelection("2026-09", "2026-11"))
        self.assertTrue(all(not month["salesObserved"] for month in months))

    def test_scope_contains_only_locations_in_the_selected_closing_interval(self):
        data = replace(
            fixture(), closings=(replace(fixture().closings[0], period="2026-01", warehouse="OLD"),)
        )
        result = analyze_inventory(data, StockSelection("2026-09", "2026-10"))
        self.assertEqual(result.historical_scope, "Sem fechamentos no recorte")
        self.assertTrue(all(point["raw"] is None for point in result.trend))
        data = replace(data, closings=data.closings + fixture().closings)
        scope = analyze_inventory(data, StockSelection("2026-09", "2026-10")).historical_scope
        self.assertIn("arm. 01", scope)
        self.assertNotIn("OLD", scope)

    def test_snapshot_corruption_has_only_domain_errors_and_keeps_good_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "base.liarte"
            write_snapshot(fixture(), path)
            payload = json.loads(gzip.decompress(path.read_bytes()))
            for sale in ([], ["A", "01", "UN"], "invalid", ["A"] * 8):
                corrupt = dict(payload, sales=[sale])
                path.write_bytes(gzip.compress(json.dumps(corrupt).encode()))
                with self.subTest(sale=sale), self.assertRaisesRegex(ValueError, "sales"):
                    read_snapshot(path)
            corrupt = dict(payload, closings=[list(payload["closings"][0])])
            corrupt["closings"][0][7] = 10**400
            path.write_bytes(gzip.compress(json.dumps(corrupt).encode()))
            with self.assertRaisesRegex(ValueError, "Indicador"):
                read_snapshot(path)
            path.write_bytes(b"\x1f\x8b\x08\x00" + b"\x00" * 6 + b"\x07")
            with self.assertRaisesRegex(ValueError, "Não foi possível ler"):
                read_snapshot(path)

    def test_overly_nested_snapshot_is_a_domain_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "base.liarte"
            path.write_bytes(gzip.compress(b"[" * 2_000 + b"0" + b"]" * 2_000))
            with self.assertRaises(ValueError):
                read_snapshot(path)

    def test_invalid_notes_dimensions_and_datetime_never_replace_cache(self):
        from datetime import datetime

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "base.liarte"
            base = fixture()
            write_snapshot(base, path)
            before = path.read_bytes()
            for data in (
                replace(base, notes="Mensagem em vez de coleção"),
                replace(base, branches=("01",)),
                replace(base, warehouses=(([], "Nome"),)),
                replace(base, as_of=datetime(2026, 10, 24)),
                replace(base, source_hash=None),
                replace(base, sales=(replace(base.sales[0], day=datetime(2026, 1, 1)),)),
            ):
                with self.subTest(data=data), self.assertRaises(ValueError):
                    write_snapshot(data, path)
                self.assertEqual(path.read_bytes(), before)

    def test_record_limits_are_shared_at_and_above_each_boundary(self):
        base = fixture()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "base.liarte"
            for name in inventory_io.RECORD_LIMITS:

                def data_with(count):
                    if name == "products":
                        values = tuple(
                            replace(base.products[0], code="A" if i == 0 else str(i))
                            for i in range(count)
                        )
                    elif name == "balances":
                        values = tuple(
                            replace(base.balances[0], warehouse=str(i)) for i in range(count)
                        )
                    elif name == "closings":
                        values = tuple(
                            replace(base.closings[0], warehouse=str(i)) for i in range(count)
                        )
                    else:
                        values = tuple(
                            replace(base.sales[0], day=date(2026, 1, 1) + timedelta(days=i))
                            for i in range(count)
                        )
                    return replace(base, **{name: values})

                with self.subTest(name=name), patch.dict(inventory_io.RECORD_LIMITS, {name: 2}):
                    boundary = data_with(2)
                    self.assertIs(validate_data(boundary), boundary)
                    write_snapshot(boundary, path)
                    self.assertEqual(read_snapshot(path), boundary)
                    before = path.read_bytes()
                    with self.assertRaisesRegex(ValueError, "limite de registros"):
                        validate_data(data_with(3))
                    with self.assertRaisesRegex(ValueError, "limite de registros"):
                        write_snapshot(data_with(3), path)
                    self.assertEqual(path.read_bytes(), before)
                    payload = json.loads(gzip.decompress(before))
                    payload[name].append(payload[name][-1])
                    path.write_bytes(gzip.compress(json.dumps(payload).encode()))
                    with self.assertRaisesRegex(ValueError, "limite de registros"):
                        read_snapshot(path)
            self.assertFalse(list(path.parent.glob(".estoque-*")))

    def test_real_product_count_limit_is_enforced_before_serialization(self):
        product = fixture().products[0]
        data = replace(fixture(), products=(product,) * 100_001)
        with self.assertRaisesRegex(ValueError, "limite de registros"):
            validate_data(data)

    def test_exact_utf8_json_byte_boundary_roundtrips_and_overflow_preserves_cache(self):
        data = fixture()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "base.liarte"
            write_snapshot(data, path)
            before = path.read_bytes()
            size = len(gzip.decompress(before))
            with patch.object(inventory_io, "MAX_JSON", size):
                self.assertIs(validate_data(data), data)
                write_snapshot(data, path)
                self.assertEqual(read_snapshot(path), data)
            with patch.object(inventory_io, "MAX_JSON", size - 1):
                with self.assertRaisesRegex(ValueError, "expandida"):
                    validate_data(data)
                with self.assertRaisesRegex(ValueError, "expandida"):
                    write_snapshot(data, path)
                with self.assertRaisesRegex(ValueError, "expandida"):
                    read_snapshot(path)
            self.assertEqual(path.read_bytes(), before)
            self.assertFalse(list(path.parent.glob(".estoque-*")))

    def test_snapshot_cancel_during_encoding_preserves_the_previous_cache(self):
        data = many_products(1_100)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "base.liarte"
            write_snapshot(fixture(), path)
            before = path.read_bytes()
            encoded = inventory_io._encoded_snapshot
            cancel = Event()
            passes = 0

            def interrupt(*args):
                nonlocal passes
                passes += 1
                for index, chunk in enumerate(encoded(*args)):
                    if passes == 2 and index == 600:
                        cancel.set()
                    yield chunk

            with (
                patch.object(inventory_io, "_encoded_snapshot", side_effect=interrupt),
                self.assertRaises(Cancelled),
            ):
                write_snapshot(data, path, cancel)
            self.assertEqual(path.read_bytes(), before)
            self.assertFalse(list(path.parent.glob(".estoque-*")))

    def test_xml_invalid_text_is_rejected_in_all_shared_fields_before_cache_replace(self):
        base = fixture()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "base.liarte"
            write_snapshot(base, path)
            before = path.read_bytes()
            for invalid in ("\x00", "\x01", "\x0b", "\ufffe", "\uffff", "\ud800"):
                value = "Nome" + invalid
                cases = (
                    replace(base, source_name=value),
                    replace(base, products=(replace(base.products[0], name=value),)),
                    replace(base, products=(replace(base.products[0], group=value),)),
                    replace(base, balances=(replace(base.balances[0], warehouse=value),)),
                    replace(base, branches=(("01", value),)),
                    replace(base, warehouses=((value, "Principal"),)),
                    replace(base, notes=(value,)),
                )
                for data in cases:
                    with (
                        self.subTest(invalid=repr(invalid), data=data),
                        self.assertRaisesRegex(ValueError, "XML/Excel"),
                    ):
                        write_snapshot(data, path)
                    self.assertEqual(path.read_bytes(), before)
            valid = replace(base, source_name="Nome\tcom\ntexto\rlegal 😀")
            write_snapshot(valid, path)
            self.assertEqual(read_snapshot(path), valid)

    def test_pbix_import_uses_shared_record_and_json_byte_limits(self):
        import pandas as pd

        rows = {
            "Dim_Atualizacao": [["2026-10-24"]],
            "Dim_Produtos": [["A", "Ácido", "Químicos", "MP", "UN", ""]],
            "Dim_Filiais": [["01", "Filial", ""]],
            "Dim_Armazem": [["01", "Principal", ""]],
            "Fato_EstoqueAtual": [["A", "01", "01", "UN", 1, 1, ""]],
            "Fact_Estoque": [["A", "01", "01", "UN", pd.Timestamp("2026-09-30"), 1, 1, 1, 30, ""]],
            "Fato_DocumentoSaida": [["A", "01", "UN", pd.Timestamp("2026-01-01"), 1, 1, ""]],
        }

        class Model:
            def __init__(self, _):
                self.tables = list(rows)

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def get_table(self, name, columns):
                return pd.DataFrame(rows[name], columns=columns)

        with tempfile.TemporaryDirectory() as directory, patch("pbixray.PBIXRay", Model):
            path = Path(directory) / "base.pbix"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("DataModel", b"synthetic model")
            data = read_pbix(path)
            cache = path.with_suffix(".liarte")
            write_snapshot(data, cache)
            self.assertEqual(read_snapshot(cache), data)
            for name in inventory_io.RECORD_LIMITS:
                with self.subTest(name=name), patch.dict(inventory_io.RECORD_LIMITS, {name: 0}):
                    with self.assertRaisesRegex(ValueError, "limite de registros"):
                        read_pbix(path)
            with (
                patch.object(inventory_io, "MAX_JSON", 1),
                self.assertRaisesRegex(ValueError, "expandida"),
            ):
                read_pbix(path)


if __name__ == "__main__":
    unittest.main()
