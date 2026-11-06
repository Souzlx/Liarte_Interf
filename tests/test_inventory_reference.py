"""Independent PBIX reference keeps source facts, exclusions and exact scales."""

from copy import deepcopy
from datetime import date
from decimal import Decimal, Inexact, Rounded, localcontext
import hashlib
from pathlib import Path
from threading import Event
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile

from liarte_core.inventory_reference import read_pbix_reference
from liarte_core.query import Cancelled


def reference_tables(year=2036, code="REF-71"):
    import pandas as pd

    return {
        "Dim_Atualizacao": [[f"{year}-04-15"]],
        "Fato_EstoqueAtual": [
            [code, "F1", "A1", "KG", Decimal("4.000001"), Decimal("90071992547409.93"), ""],
            ["LEGACY", "F1", "A2", "L", Decimal("-1"), Decimal("-3.01"), False],
            ["DELETED", "F1", "A1", "KG", Decimal("99"), Decimal("999"), "*"],
        ],
        "Fact_Estoque": [
            [code, "F1", "A1", "KG", pd.Timestamp(f"{year}-02-28"), Decimal("2"),
             Decimal("9.02"), 2.0, 15.0, "0"],
            [code, "F1", "A1", "KG", pd.Timestamp(f"{year}-03-31"), Decimal("3"),
             Decimal("13.01"), None, None, 0.0],
            ["DELETED", "F1", "A1", "KG", pd.Timestamp(f"{year}-03-31"), Decimal("3"),
             Decimal("13.01"), None, None, "true"],
        ],
        "Fato_DocumentoSaida": [
            [code, "F1", "KG", pd.Timestamp(f"{year}-03-12"), Decimal("1"),
             Decimal("1.005"), ""],
            [code, "F1", "KG", pd.Timestamp(f"{year}-03-12"), Decimal("-1"),
             Decimal("-1.015"), "false"],
            [code, "F1", "KG", pd.Timestamp(f"{year}-03-13"), Decimal("0.00000049"),
             Decimal("0.0049"), None],
            [code, "F1", "KG", pd.Timestamp(f"{year}-03-13"), Decimal("-0.00000049"),
             Decimal("0.0049"), 0],
            ["LEGACY", "F1", "L", pd.Timestamp(f"{year}-03-15"), Decimal("-1.0000005"),
             Decimal("-2.005"), ""],
            ["DELETED", "F1", "KG", pd.Timestamp(f"{year}-03-12"), Decimal("99"),
             Decimal("999"), 1],
        ],
    }


class InventoryReferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "reference-synthetic.pbix"
        with zipfile.ZipFile(self.path, "w") as archive:
            archive.writestr("DataModel", b"synthetic numeric reference")
        self.tables = reference_tables()

    def model(self, transform=None):
        import pandas as pd

        tables = self.tables

        class Model:
            def __init__(self, _):
                self.tables = tuple(tables)

            def __enter__(self):
                return self

            def __exit__(self, *_):
                pass

            def get_table(self, name, columns):
                result = pd.DataFrame(tables[name], columns=columns)
                return transform(name, result) if transform else result

        return Model

    def read(self, *, transform=None, **kwargs):
        with patch("pbixray.PBIXRay", self.model(transform)):
            return read_pbix_reference(self.path, **kwargs)

    def test_independent_reference_preserves_exact_values_unknowns_and_source_identity(self):
        with (
            patch("liarte_core.inventory_io.read_pbix", side_effect=AssertionError("importer")),
            patch("liarte_core.inventory_source.inventory_from_records", side_effect=AssertionError("normalizer")),
            patch("liarte_core.inventory.scaled", side_effect=AssertionError("production conversion")),
        ):
            result = self.read()
        self.assertEqual(result.as_of, date(2036, 4, 15))
        self.assertEqual(result.source_name, self.path.name)
        self.assertEqual(result.source_hash, hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertEqual(result.balances[0].quantity, 4_000_001)
        self.assertEqual(result.balances[0].cost, 9_007_199_254_740_993)
        self.assertEqual(result.balances[1].quantity, -1_000_000)
        self.assertEqual(result.balances[1].unit, "L")
        self.assertEqual(result.closings[0].turnover, 2.0)
        self.assertEqual(result.closings[0].days, 15.0)
        self.assertIsNone(result.closings[1].turnover)
        self.assertIsNone(result.closings[1].days)

    def test_deleted_rows_are_counted_and_excluded_without_dropping_legacy_facts(self):
        result = self.read()
        self.assertEqual(result.counts["Dim_Atualizacao"],
                         {"rows": 1, "accepted": 1, "deleted": 0, "output": 1})
        self.assertEqual(result.counts["Fato_EstoqueAtual"],
                         {"rows": 3, "accepted": 2, "deleted": 1, "output": 2})
        self.assertEqual(result.counts["Fact_Estoque"],
                         {"rows": 3, "accepted": 2, "deleted": 1, "output": 2})
        self.assertEqual(result.counts["Fato_DocumentoSaida"],
                         {"rows": 6, "accepted": 5, "deleted": 1, "output": 3})
        self.assertIn("LEGACY", {row.product for row in result.balances})
        self.assertIn("LEGACY", {row.product for row in result.sales})
        self.assertNotIn("DELETED", {row.product for row in result.sales})

    def test_per_item_rounding_precedes_daily_aggregation_and_retains_positive_presence(self):
        result = self.read()
        rows = {row.day: row for row in result.sales if row.product == "REF-71"}
        zero_net = rows[date(2036, 3, 12)]
        self.assertEqual((zero_net.quantity, zero_net.cost, zero_net.had_positive), (0, -1, True))
        subscale = rows[date(2036, 3, 13)]
        self.assertEqual((subscale.quantity, subscale.cost, subscale.had_positive), (0, 0, False))
        negative = next(row for row in result.sales if row.product == "LEGACY")
        self.assertEqual((negative.quantity, negative.cost, negative.had_positive),
                         (-1_000_001, -201, False))

    def test_reference_conversion_ignores_small_decimal_precision_and_traps(self):
        with localcontext() as context:
            context.prec = 3
            context.traps[Inexact] = True
            context.traps[Rounded] = True
            result = self.read()
        self.assertEqual(result.balances[0].cost, 9_007_199_254_740_993)
        self.assertEqual(result.balances[0].quantity, 4_000_001)

    def test_daily_bound_applies_to_final_net_quantity_without_order_dependent_rejection(self):
        import pandas as pd

        source = self.tables["Fato_DocumentoSaida"]
        for sign in (1, -1):
            source.extend([
                ["REF-71", "F1", "KG", pd.Timestamp("2036-03-12"),
                 Decimal(sign) * Decimal("1e16"), Decimal(0), ""]
                for _ in range(12)
            ])
        result = self.read()
        aggregate = next(row for row in result.sales if row.day == date(2036, 3, 12))
        self.assertEqual(aggregate.quantity, 0)
        self.assertTrue(aggregate.had_positive)
        del source[-12:]
        with self.assertRaisesRegex(ValueError, "Agregado diário fora do limite"):
            self.read()

    def test_values_above_numeric_limit_are_rejected_even_in_small_decimal_context(self):
        self.tables["Fato_EstoqueAtual"][0][4] = Decimal("10000000000000001")
        with localcontext() as context:
            context.prec = 2
            with self.assertRaisesRegex(ValueError, "fora do limite"):
                self.read()

    def test_new_identifiers_dates_and_row_orders_drive_the_reference(self):
        original = self.read()
        self.tables = reference_tables(2044, "OTHER-903")
        for name in self.tables:
            self.tables[name].reverse()
        shifted = self.read()
        self.assertEqual(shifted.as_of, date(2044, 4, 15))
        self.assertIn("OTHER-903", {row.product for row in shifted.balances})
        self.assertEqual(sorted(row.cost for row in shifted.balances),
                         sorted(row.cost for row in original.balances))
        self.assertEqual({row.period for row in shifted.closings}, {"2044-02", "2044-03"})

    def test_unknown_deletion_flags_are_rejected(self):
        for name in ("Fato_EstoqueAtual", "Fact_Estoque", "Fato_DocumentoSaida"):
            original = deepcopy(self.tables)
            with self.subTest(table=name), self.assertRaisesRegex(ValueError, "Marcador"):
                self.tables[name][0][-1] = "?"
                self.read()
            self.tables = original

    def test_duplicate_current_and_monthly_positions_are_rejected(self):
        for name in ("Fato_EstoqueAtual", "Fact_Estoque"):
            original = deepcopy(self.tables)
            with self.subTest(table=name), self.assertRaisesRegex(ValueError, "duplicada"):
                self.tables[name].append(self.tables[name][0])
                self.read()
            self.tables = original

    def test_dates_and_future_month_or_sale_are_rejected(self):
        import pandas as pd

        for name, column, value in (
            ("Fact_Estoque", 4, pd.NaT),
            ("Fact_Estoque", 4, pd.Timestamp("2036-05-31")),
            ("Fato_DocumentoSaida", 3, pd.NaT),
            ("Fato_DocumentoSaida", 3, pd.Timestamp("2036-04-16")),
            ("Dim_Atualizacao", 0, "not a source date"),
        ):
            original = deepcopy(self.tables)
            with self.subTest(table=name, value=value), self.assertRaises(ValueError):
                self.tables[name][0][column] = value
                self.read()
            self.tables = original

    def test_partial_current_month_closing_keeps_its_period(self):
        import pandas as pd

        self.tables["Fact_Estoque"][1][4] = pd.Timestamp("2036-04-30")
        result = self.read()
        self.assertEqual(result.closings[1].period, "2036-04")

    def test_indicator_zero_and_negative_are_preserved_and_nonfinite_is_rejected(self):
        self.tables["Fact_Estoque"][0][7:9] = [0, -3.5]
        row = self.read().closings[0]
        self.assertEqual((row.turnover, row.days), (0.0, -3.5))
        self.tables["Fact_Estoque"][0][7] = float("inf")
        with self.assertRaisesRegex(ValueError, "Indicador"):
            self.read()

    def _add_import_dimensions(self):
        self.tables.update({
            "Dim_Produtos": [
                ["REF-71", "Produto sintético", "Grupo", "Tipo", "KG", ""],
                ["LEGACY", "Produto histórico sintético", "Grupo", "Tipo", "L", ""],
            ],
            "Dim_Filiais": [["F1", "Filial sintética", ""]],
            "Dim_Armazem": [
                ["A1", "Armazém sintético", ""], ["A2", "Outro armazém sintético", ""],
            ],
        })

    def test_reference_and_importer_reject_boolean_indicators_before_float_conversion(self):
        import numpy as np
        import pandas as pd
        from liarte_core.inventory_io import read_pbix

        self._add_import_dimensions()
        for column in ("GiroEstoqueMensalQtd", "DiasEstoqueQtd"):
            for storage in ("nullable", "numpy_object", "python_object"):
                for flag in (True, False):
                    def transform(name, frame):
                        if name != "Fact_Estoque":
                            return frame
                        result = frame.copy()
                        if storage == "nullable":
                            values = pd.Series([flag, pd.NA, pd.NA], dtype="boolean")
                        elif storage == "numpy_object":
                            values = pd.Series([np.bool_(flag), None, None], dtype=object)
                        else:
                            values = pd.Series([flag, None, None], dtype=object)
                        result[column] = values
                        return result

                    for reader in (read_pbix_reference, read_pbix):
                        with (
                            self.subTest(column=column, storage=storage, flag=flag,
                                         reader=reader.__name__),
                            patch("pbixray.PBIXRay", self.model(transform)),
                            self.assertRaisesRegex(ValueError, "Indicador"),
                        ):
                            reader(self.path)

    def test_reference_and_importer_keep_missing_indicators_as_unknown(self):
        import pandas as pd
        from liarte_core.inventory_io import read_pbix

        self._add_import_dimensions()
        for missing in (None, float("nan"), pd.NA):
            def transform(name, frame):
                if name != "Fact_Estoque":
                    return frame
                result = frame.copy()
                for column in ("GiroEstoqueMensalQtd", "DiasEstoqueQtd"):
                    result[column] = pd.Series([missing] * len(result), dtype=object)
                return result

            for reader in (read_pbix_reference, read_pbix):
                with (
                    self.subTest(missing=missing, reader=reader.__name__),
                    patch("pbixray.PBIXRay", self.model(transform)),
                ):
                    data = reader(self.path)
                self.assertTrue(data.closings)
                self.assertTrue(all(row.turnover is None and row.days is None
                                    for row in data.closings))

    def test_absent_and_duplicate_required_columns_are_rejected(self):
        def missing(name, frame):
            return frame.drop(columns="CustoTotal") if name == "Fato_EstoqueAtual" else frame

        def duplicate(name, frame):
            if name == "Fato_EstoqueAtual":
                frame = frame.copy()
                frame.columns = [*frame.columns[:-2], "Produto", "DELETED"]
            return frame

        for transform in (missing, duplicate):
            with self.subTest(transform=transform), self.assertRaisesRegex(ValueError, "Colunas"):
                self.read(transform=transform)

    def test_missing_numeric_source_table_is_rejected(self):
        del self.tables["Fact_Estoque"]
        with self.assertRaisesRegex(ValueError, "Tabelas"):
            self.read()

    def test_cancellation_is_checked_before_io_and_during_rows(self):
        cancel = Event()
        cancel.set()
        with self.assertRaises(Cancelled), patch("pbixray.PBIXRay") as parser:
            read_pbix_reference(self.path, cancel)
        parser.assert_not_called()
        cancel.clear()

        def stop(name, frame):
            if name == "Fato_EstoqueAtual":
                cancel.set()
            return frame

        with self.assertRaises(Cancelled):
            self.read(transform=stop, cancel=cancel)

    def test_pbix_changed_during_read_is_rejected(self):
        with patch("liarte_core.inventory_reference._digest", side_effect=("a" * 64, "b" * 64)):
            with self.assertRaisesRegex(ValueError, "alterado durante a leitura"):
                self.read()

    def test_empty_or_multiple_update_rows_are_rejected(self):
        for rows in ([], [["2036-04-15"], ["2036-04-16"]]):
            with self.subTest(rows=rows), self.assertRaisesRegex(ValueError, "única data"):
                self.tables["Dim_Atualizacao"] = rows
                self.read()

    def test_limits_are_checked_without_silent_truncation(self):
        for key in ("balances", "closings", "sales"):
            with self.subTest(key=key):
                with patch.dict("liarte_core.inventory_reference.REFERENCE_LIMITS", {key: 1}):
                    with self.assertRaisesRegex(ValueError, "limite"):
                        self.read()

    def test_invalid_or_oversized_pbix_is_rejected_before_parsing(self):
        with patch("liarte_core.inventory_reference.MAX_PBIX_BYTES", 1):
            with self.assertRaisesRegex(ValueError, "limite"), patch("pbixray.PBIXRay") as parser:
                read_pbix_reference(self.path)
            parser.assert_not_called()
        self.path.write_bytes(b"not a model zip")
        with self.assertRaisesRegex(ValueError, "PBIX inválido"):
            read_pbix_reference(self.path)

    def test_missing_or_ambiguous_datamodel_is_rejected(self):
        with zipfile.ZipFile(self.path, "w") as archive:
            archive.writestr("not-a-model", b"synthetic")
        with self.assertRaisesRegex(ValueError, "único DataModel"):
            read_pbix_reference(self.path)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(self.path, "w") as archive:
                archive.writestr("DataModel", b"synthetic one")
                archive.writestr("DataModel", b"synthetic two")
        with self.assertRaisesRegex(ValueError, "único DataModel"):
            read_pbix_reference(self.path)
