"""Accepted stock records are independent of the extraction adapter."""

from dataclasses import fields, replace
from datetime import date
from decimal import Decimal
from pathlib import Path
from threading import Event
import gzip
import hashlib
import json
import tempfile
import unittest
from unittest.mock import patch
import zipfile

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
from liarte_core.inventory_io import read_pbix, read_snapshot, write_snapshot
from liarte_core.inventory_monthly import analyze_monthly_inventory
from liarte_core.inventory_source import inventory_from_records
from liarte_core.query import Cancelled


def records(year=2032, code="SKU-A"):
    return dict(
        as_of=date(year, 4, 15),
        source_name="Extração normalizada sintética",
        products=(
            Product(code, "Produto sintético A", "Grupo A", "MP", "KG"),
            Product("SKU-B", "Produto sintético B", "Grupo B", "PA", "L"),
        ),
        balances=(
            Balance(code, "F1", "A1", "KG", 4 * SCALE + 1, 2**54 + 3),
            Balance("SKU-B", "F1", "A1", "L", -SCALE, -301),
        ),
        closings=(
            Closing(code, "F1", "A1", "KG", f"{year}-02", 2 * SCALE, 902, 2.0, 15.0),
            Closing(code, "F1", "A1", "KG", f"{year}-03", 3 * SCALE, 1301, None, None),
        ),
        sales=(
            Sale(code, "F1", "KG", date(year, 2, 10), 3 * SCALE, 1200, True),
            Sale(code, "F1", "KG", date(year, 3, 12), 0, -1, True),
            Sale("SKU-B", "F1", "L", date(year, 3, 15), -SCALE, -201, False),
        ),
        branches=(("F1", "Filial sintética"),),
        warehouses=(("A1", "Armazém sintético"),),
    )


def facts(data):
    return {
        field.name: getattr(data, field.name)
        for field in fields(InventoryData)
        if field.name not in ("source_name", "source_hash")
    }


class InventorySourceContractTests(unittest.TestCase):
    def test_normalized_acceptance_preserves_exact_values_signals_and_units(self):
        data = inventory_from_records(**records())
        self.assertEqual(data.balances[0].quantity, 4 * SCALE + 1)
        self.assertEqual(data.balances[0].cost, 2**54 + 3)
        self.assertEqual(data.balances[1].quantity, -SCALE)
        self.assertEqual(data.sales[1].quantity, 0)
        self.assertEqual(data.sales[1].cost, -1)
        self.assertTrue(data.sales[1].had_positive)
        self.assertIsNone(data.closings[1].turnover)
        self.assertEqual({row.unit for row in data.balances}, {"KG", "L"})

    def test_source_revision_is_preserved_and_explicit_invalid_revisions_rejected(self):
        known = "b" * 64
        self.assertEqual(inventory_from_records(**records(), source_hash=known).source_hash, known)
        for value in (None, "", "A" * 64, "x" * 64, False):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "Identificação"):
                inventory_from_records(**records(), source_hash=value)

    def test_content_revision_ignores_source_name_and_row_order_without_reordering_facts(self):
        values = records()
        first = inventory_from_records(**values)
        reordered = dict(values, source_name="Outra origem sintética")
        for name in ("products", "balances", "closings", "sales"):
            reordered[name] = list(reversed(reordered[name]))
        second = inventory_from_records(**reordered)
        self.assertEqual(first.source_hash, second.source_hash)
        self.assertEqual(second.products, tuple(reordered["products"]))
        self.assertNotEqual(first.products, second.products)
        self.assertRegex(first.source_hash, r"^[0-9a-f]{64}$")

    def test_content_revision_tracks_changes_insertions_and_deletions(self):
        values = records()
        before = inventory_from_records(**values).source_hash
        modifications = (
            dict(as_of=date(2032, 4, 16)),
            dict(
                balances=(replace(values["balances"][0], cost=2**54 + 4), *values["balances"][1:])
            ),
            dict(sales=(replace(values["sales"][0], quantity=3 * SCALE + 1), *values["sales"][1:])),
            dict(sales=values["sales"][1:]),
            dict(
                sales=(*values["sales"], Sale("SKU-A", "F1", "KG", date(2032, 3, 16), 1, 1, True))
            ),
            dict(sales=(replace(values["sales"][0], had_positive=None), *values["sales"][1:])),
            dict(closings=(replace(values["closings"][0], turnover=None), values["closings"][1])),
            dict(branches=(("F1", "Novo nome sintético"),)),
            dict(notes=("Anotação sintética da revisão",)),
        )
        for change in modifications:
            with self.subTest(change=change):
                self.assertNotEqual(
                    inventory_from_records(**dict(values, **change)).source_hash, before
                )

    def test_equal_ratio_representations_have_the_same_content_revision(self):
        values = records()
        first = inventory_from_records(**values)
        second = inventory_from_records(
            **dict(
                values,
                closings=(
                    replace(values["closings"][0], turnover=2, days=15),
                    values["closings"][1],
                ),
            )
        )
        self.assertEqual(first.source_hash, second.source_hash)

    def test_collections_and_location_pairs_are_detached_from_mutable_inputs(self):
        values = records()
        products = list(values["products"])
        branches = [["F1", "Filial sintética"]]
        data = inventory_from_records(**dict(values, products=products, branches=branches))
        products.clear()
        branches[0][1] = "Alterado depois da aceitação"
        self.assertEqual(len(data.products), 2)
        self.assertEqual(data.branches, (("F1", "Filial sintética"),))

    def test_invalid_records_limits_dates_and_duplicate_keys_are_not_accepted(self):
        values = records()
        changes = (
            dict(products=(dict(code="SKU-A"),)),
            dict(balances=(*values["balances"], values["balances"][0])),
            dict(sales=(replace(values["sales"][0], day=date(2033, 1, 1)),)),
            dict(balances=(replace(values["balances"][0], quantity=1.25),)),
            dict(branches=(("F1",),)),
        )
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):
                inventory_from_records(**dict(values, **change))
        with patch.dict("liarte_core.inventory_io.RECORD_LIMITS", {"sales": 1}):
            with self.assertRaisesRegex(ValueError, "limite de registros"):
                inventory_from_records(**values)

    def test_cancellation_prevents_acceptance_and_content_revision_publication(self):
        cancel = Event()
        cancel.set()
        with self.assertRaises(Cancelled):
            inventory_from_records(**records(), cancel=cancel)
        cancel.clear()
        from liarte_core import inventory_source

        original = inventory_source._content_revision

        def stopped(data, token):
            token.set()
            return original(data, token)

        with patch.object(inventory_source, "_content_revision", side_effect=stopped):
            with self.assertRaises(Cancelled):
                inventory_from_records(**records(), cancel=cancel)

    def test_new_dates_and_product_identifiers_drive_the_same_existing_calculations(self):
        for year, code in ((2028, "NOVO-019"), (2034, "OUTRO-937")):
            with self.subTest(year=year, code=code):
                data = inventory_from_records(**records(year, code))
                selected = StockSelection(f"{year}-02", f"{year}-03")
                result = analyze_inventory(data, selected)
                row = next(row for row in result.rows if row.balance.product == code)
                self.assertEqual(row.balance.quantity, 4 * SCALE + 1)
                monthly = analyze_monthly_inventory(data, selected)
                self.assertEqual(
                    [month["period"] for month in monthly], [f"{year}-02", f"{year}-03"]
                )
                self.assertEqual(monthly[-1]["salesQuantity"]["KG"], 0)

    def test_snapshot_roundtrip_preserves_the_normalized_contract_and_revision(self):
        data = inventory_from_records(**records())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.liarte"
            write_snapshot(data, path)
            self.assertEqual(read_snapshot(path), data)

    def test_snapshot_invalid_hash_does_not_request_a_new_content_revision(self):
        data = inventory_from_records(**records())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.liarte"
            write_snapshot(data, path)
            encoded = json.loads(gzip.decompress(path.read_bytes()))
            encoded["source_hash"] = None
            path.write_bytes(gzip.compress(json.dumps(encoded).encode("utf-8")))
            with self.assertRaisesRegex(ValueError, "Identificação"):
                read_snapshot(path)

    def test_pbix_and_normalized_adapter_inputs_produce_the_same_facts_and_numbers(self):
        import pandas as pd

        values = records()
        base = inventory_from_records(**values)
        tables = {
            "Dim_Atualizacao": [["2032-04-15"]],
            "Dim_Produtos": [[p.code, p.name, p.group, p.kind, p.unit, ""] for p in base.products],
            "Dim_Filiais": [[*row, ""] for row in base.branches],
            "Dim_Armazem": [[*row, ""] for row in base.warehouses],
            "Fato_EstoqueAtual": [
                [
                    r.product,
                    r.branch,
                    r.warehouse,
                    r.unit,
                    Decimal(r.quantity) / SCALE,
                    Decimal(r.cost) / 100,
                    "",
                ]
                for r in base.balances
            ],
            "Fact_Estoque": [
                [
                    r.product,
                    r.branch,
                    r.warehouse,
                    r.unit,
                    pd.Timestamp(r.period + "-28"),
                    Decimal(r.quantity) / SCALE,
                    Decimal(r.cost) / 100,
                    r.turnover,
                    r.days,
                    "",
                ]
                for r in base.closings
            ],
            "Fato_DocumentoSaida": [
                [
                    r.product,
                    r.branch,
                    r.unit,
                    pd.Timestamp(r.day),
                    Decimal(r.quantity) / SCALE,
                    Decimal(r.cost) / 100,
                    "",
                ]
                for r in base.sales
            ],
        }
        # The zero-net day still contains a positive movement in the source.
        tables["Fato_DocumentoSaida"][1:2] = [
            ["SKU-A", "F1", "KG", pd.Timestamp("2032-03-12"), Decimal("1"), Decimal("1"), ""],
            ["SKU-A", "F1", "KG", pd.Timestamp("2032-03-12"), Decimal("-1"), Decimal("-1.01"), ""],
        ]

        class Model:
            def __init__(self, _):
                self.tables = tuple(tables)

            def __enter__(self):
                return self

            def __exit__(self, *_):
                pass

            def get_table(self, name, columns):
                return pd.DataFrame(tables[name], columns=columns)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.pbix"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("DataModel", b"synthetic data contract")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            with patch("pbixray.PBIXRay", Model):
                extracted = read_pbix(path)
            self.assertEqual(extracted.source_hash, digest)
            self.assertNotEqual(base.source_hash, digest)
            self.assertEqual(facts(extracted), facts(base))
            selected = StockSelection("2032-02", "2032-03")
            self.assertEqual(
                analyze_inventory(extracted, selected), analyze_inventory(base, selected)
            )
            self.assertEqual(
                analyze_monthly_inventory(extracted, selected),
                analyze_monthly_inventory(base, selected),
            )
            with (
                patch("pbixray.PBIXRay", Model),
                patch("liarte_core.inventory_io._hash", side_effect=("a" * 64, "b" * 64)),
                self.assertRaisesRegex(ValueError, "alterado durante a leitura"),
            ):
                read_pbix(path)
