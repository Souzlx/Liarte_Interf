"""Reconciliation files preserve precision, presence and complete differences."""

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import patch
import zipfile

from openpyxl import load_workbook

from liarte_core.inventory_reconciliation_export import export_inventory_reconciliation
from liarte_core.query import Cancelled


def difference(**values):
    result = {
        "section": "balances",
        "product": "=SUM(A1:A2)",
        "branch": "@Filial",
        "warehouse": "A1",
        "unit": "KG",
        "day": "",
        "period": "2032-03",
        "metric": "quantity",
        "scale": 1_000_000,
        "valueUnit": "KG",
        "sourceValue": 10**22 + 1,
        "appValue": 10**22,
        "difference": -1,
        "sourcePresent": True,
        "appPresent": True,
        "status": "different",
    }
    result.update(values)
    return result


def report():
    return {
        "format": "liarte.inventory.reconciliation/1",
        "source": {
            "sourceName": "=Fonte sintética.pbix",
            "sourceHash": "a" * 64,
            "asOf": "2032-04-15",
        },
        "app": {
            "sourceName": "base sintética.liarte",
            "sourceHash": "a" * 64,
            "asOf": "2032-04-15",
        },
        "context": {"scope": "all", "start": "2032-02", "end": "2032-04"},
        "comparable": True,
        "status": "different",
        "checks": {
            "total": 12,
            "passed": 7,
            "different": 4,
            "missing": 1,
            "extra": 0,
            "unknown": 0,
        },
        "sections": {
            "balances": {
                "total": 5,
                "passed": 0,
                "different": 4,
                "missing": 1,
                "extra": 0,
                "unknown": 0,
            }
        },
        "totals": (
            difference(
                section="current_totals",
                product="",
                metric="quantity",
                sourceValue=8_000_000,
                appValue=8_000_000,
                difference=0,
                status="equal",
            ),
            difference(
                section="current_totals",
                product="",
                metric="cost",
                valueUnit="R$",
                scale=100,
                sourceValue=10**22 + 1,
                appValue=10**22,
                difference=-1,
            ),
            difference(
                section="monthly_totals",
                product="",
                unit="L",
                metric="quantity",
                sourceValue=None,
                appValue=None,
                difference=None,
                status="unknown",
            ),
        ),
        "differences": (
            difference(),
            difference(
                product="ZERO",
                metric="cost",
                unit="R$",
                valueUnit="R$",
                scale=100,
                sourceValue=0,
                appValue=None,
                difference=None,
                appPresent=False,
                status="missing",
            ),
            difference(
                product="AUSENTE",
                metric="turnover",
                unit="x/mês",
                valueUnit="x/mês",
                scale=1,
                sourceValue=None,
                appValue=0,
                difference=None,
            ),
            difference(
                product="POSITIVA",
                metric="had_positive",
                unit="",
                valueUnit="bool",
                scale=1,
                sourceValue=True,
                appValue=False,
                difference=None,
            ),
            difference(
                product="GIRO",
                metric="turnover",
                unit="x/mês",
                valueUnit="x/mês",
                scale=1,
                sourceValue=1.25,
                appValue=1.5,
                difference=0.25,
            ),
        ),
    }


class InventoryReconciliationExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)

    def read_book(self, path):
        book = load_workbook(path)
        self.addCleanup(book.close)
        return book

    @staticmethod
    def rows(sheet):
        values = list(sheet.values)
        return [dict(zip(values[0], row, strict=True)) for row in values[1:]]

    def test_json_retains_exact_scaled_integers_presence_nulls_and_source_metadata(self):
        before = report()
        original = deepcopy(before)
        path = self.directory / "numeric.json"
        self.assertEqual(export_inventory_reconciliation(before, path), path)
        restored = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(restored["differences"][0]["sourceValue"], 10**22 + 1)
        self.assertEqual(restored["differences"][0]["scale"], 1_000_000)
        self.assertEqual(restored["differences"][0]["difference"], -1)
        self.assertIsNone(restored["differences"][1]["appValue"])
        self.assertEqual(restored["differences"][1]["sourceValue"], 0)
        self.assertIs(restored["differences"][1]["appPresent"], False)
        self.assertIs(restored["differences"][3]["sourceValue"], True)
        self.assertEqual(restored["source"], before["source"])
        self.assertEqual(restored["context"], before["context"])
        self.assertEqual(restored["totals"][1]["sourceValue"], 10**22 + 1)
        self.assertEqual(before, original)

    def test_excel_numeric_rows_keep_exact_text_unknown_zero_flags_and_fractional_ratios(self):
        path = self.directory / "numeric.xlsx"
        export_inventory_reconciliation(report(), path)
        book = self.read_book(path)
        self.assertIn("Resumo", book.sheetnames)
        self.assertIn("Metodologia", book.sheetnames)
        self.assertIn("Totais", book.sheetnames)
        rows = {row["Produto"]: row for row in self.rows(book["Diferenças"])}
        large = rows["=SUM(A1:A2)"]
        self.assertEqual(large["Valor fonte"], "10000000000000000.000001")
        self.assertEqual(large["Diferença"], -0.000001)
        self.assertEqual(large["Escala"], 1_000_000)
        self.assertEqual(rows["ZERO"]["Valor fonte"], 0)
        self.assertIsNone(rows["ZERO"]["Valor aplicativo"])
        self.assertIsNone(rows["ZERO"]["Diferença"])
        self.assertIsNone(rows["AUSENTE"]["Valor fonte"])
        self.assertEqual(rows["AUSENTE"]["Valor aplicativo"], 0)
        self.assertIs(rows["POSITIVA"]["Valor fonte"], True)
        self.assertIs(rows["POSITIVA"]["Valor aplicativo"], False)
        self.assertEqual(rows["GIRO"]["Valor fonte"], 1.25)
        self.assertEqual(rows["GIRO"]["Valor aplicativo"], 1.5)
        self.assertEqual(rows["GIRO"]["Diferença"], 0.25)
        for sheet in book:
            for row in sheet:
                self.assertTrue(all(cell.data_type != "f" for cell in row))
        exact_cells = [
            cell
            for row in book["Diferenças"]
            for cell in row
            if cell.value == "10000000000000000.000001"
        ]
        self.assertEqual(len(exact_cells), 1)
        self.assertTrue(exact_cells[0].comment)
        totals = self.rows(book["Totais"])
        self.assertEqual(totals[0]["Valor fonte"], 8)
        self.assertEqual(totals[0]["Valor aplicativo"], 8)
        self.assertEqual(totals[0]["Diferença"], 0)
        self.assertEqual(totals[1]["Unidade do valor"], "R$")
        self.assertEqual(totals[1]["Valor fonte"], "100000000000000000000.01")
        self.assertIsNone(totals[2]["Valor fonte"])
        self.assertIsNone(totals[2]["Valor aplicativo"])

    def test_excel_keeps_revisions_reference_and_methodology_without_claiming_dax_execution(self):
        path = self.directory / "context.xlsx"
        export_inventory_reconciliation(report(), path)
        book = self.read_book(path)
        rendered = "\n".join(
            str(cell.value)
            for sheet in book
            for row in sheet
            for cell in row
            if cell.value is not None
        )
        for value in ("a" * 64, "2032-04-15", "2032-02", "2032-04"):
            self.assertIn(value, rendered)
        method = "\n".join(
            str(cell.value) for row in book["Metodologia"] for cell in row if cell.value is not None
        )
        self.assertIn("DAX", method)
        self.assertIn("SQL", method)
        self.assertNotIn("Hipótese a verificar", rendered)
        self.assertNotIn("Próximo passo:", rendered)

    def test_every_difference_survives_sheet_splitting_before_excel_row_limit(self):
        values = report()
        with patch("liarte_core.inventory_reconciliation_export._MAX_ROWS", 3):
            path = self.directory / "split.xlsx"
            export_inventory_reconciliation(values, path)
        book = self.read_book(path)
        tables = [sheet for sheet in book if sheet.title.startswith("Diferenças")]
        self.assertEqual(len(tables), 3)
        self.assertEqual(sum(sheet.max_row - 1 for sheet in tables), 5)
        self.assertTrue(all(sheet.max_row <= 3 for sheet in tables))
        self.assertEqual(
            {row["Produto"] for sheet in tables for row in self.rows(sheet)},
            {row["product"] for row in values["differences"]},
        )
        total_tables = [sheet for sheet in book if sheet.title.startswith("Totais")]
        self.assertEqual(len(total_tables), 2)
        self.assertEqual(sum(sheet.max_row - 1 for sheet in total_tables), 3)

    def test_empty_differences_still_export_valid_summary_and_headers(self):
        values = report()
        values.update(
            status="equal",
            differences=(),
            checks={
                "total": 12,
                "passed": 12,
                "different": 0,
                "missing": 0,
                "extra": 0,
                "unknown": 0,
            },
        )
        path = self.directory / "empty.xlsx"
        export_inventory_reconciliation(values, path)
        book = self.read_book(path)
        self.assertEqual(book["Diferenças"].max_row, 1)
        self.assertEqual(book["Diferenças"].cell(1, 2).value, "Produto")

    def test_cancelled_export_preserves_previous_json_or_workbook_without_temporary_files(self):
        token = Event()
        token.set()
        for suffix in (".json", ".xlsx"):
            with self.subTest(suffix=suffix):
                path = self.directory / ("previous" + suffix)
                path.write_bytes(b"previous valid artifact")
                before = set(self.directory.iterdir())
                with self.assertRaises(Cancelled):
                    export_inventory_reconciliation(report(), path, cancel=token)
                self.assertEqual(path.read_bytes(), b"previous valid artifact")
                self.assertEqual(set(self.directory.iterdir()), before)

    def test_publication_failure_keeps_previous_file_and_cleans_staging_files(self):
        for suffix in (".json", ".xlsx"):
            with self.subTest(suffix=suffix):
                path = self.directory / ("previous" + suffix)
                path.write_bytes(b"previous valid artifact")
                before = set(self.directory.iterdir())
                with patch(
                    "liarte_core.inventory_reconciliation_export.os.replace",
                    side_effect=OSError("controlled publication failure"),
                ):
                    with self.assertRaises(OSError):
                        export_inventory_reconciliation(report(), path)
                self.assertEqual(path.read_bytes(), b"previous valid artifact")
                self.assertEqual(set(self.directory.iterdir()), before)

    def test_source_guard_runs_on_complete_staging_and_failure_preserves_previous_report(self):
        for suffix in (".json", ".xlsx"):
            with self.subTest(suffix=suffix):
                path = self.directory / ("guarded" + suffix)
                path.write_bytes(b"previous valid artifact")
                before = set(self.directory.iterdir())
                calls = []

                def source_changed():
                    calls.append(True)
                    staging = set(self.directory.iterdir()) - before
                    self.assertEqual(len(staging), 1)
                    staged = staging.pop()
                    self.assertEqual(path.read_bytes(), b"previous valid artifact")
                    if suffix == ".json":
                        data = json.loads(staged.read_text(encoding="utf-8"))
                        self.assertEqual(data["differences"][0]["sourceValue"], 10**22 + 1)
                    else:
                        self.assertTrue(zipfile.is_zipfile(staged))
                        workbook = load_workbook(staged, read_only=True)
                        try:
                            self.assertIn("Diferenças", workbook.sheetnames)
                        finally:
                            workbook.close()
                    raise ValueError("Source revision changed during report generation")

                with self.assertRaisesRegex(ValueError, "Source revision"):
                    export_inventory_reconciliation(report(), path, before_publish=source_changed)
                self.assertEqual(calls, [True])
                self.assertEqual(path.read_bytes(), b"previous valid artifact")
                self.assertEqual(set(self.directory.iterdir()), before)

    def test_ratio_beyond_excel_precision_remains_exact_text_with_a_comment(self):
        values = report()
        values["differences"] = (
            difference(
                product="GIRO-EXATO",
                metric="turnover",
                valueUnit="x/mês",
                scale=1,
                sourceValue=1.2345678901234567,
                appValue=1.25,
                difference=-0.0154321098765433,
            ),
        )
        path = self.directory / "exact-ratio.xlsx"
        export_inventory_reconciliation(values, path)
        book = self.read_book(path)
        sheet = book["Diferenças"]
        rows = self.rows(sheet)
        self.assertEqual(rows[0]["Valor fonte"], "1.2345678901234567")
        self.assertEqual(rows[0]["Valor aplicativo"], 1.25)
        headers = [cell.value for cell in sheet[1]]
        source = sheet.cell(2, headers.index("Valor fonte") + 1)
        self.assertEqual(source.data_type, "s")
        self.assertTrue(source.comment)

    def test_nonfinite_json_or_unsupported_extension_never_replace_previous_output(self):
        values = report()
        values["differences"] = (difference(sourceValue=float("nan")),)
        path = self.directory / "previous.json"
        path.write_bytes(b"previous valid artifact")
        with self.assertRaises(ValueError):
            export_inventory_reconciliation(values, path)
        self.assertEqual(path.read_bytes(), b"previous valid artifact")
        invalid = self.directory / "report.csv"
        with self.assertRaises(ValueError):
            export_inventory_reconciliation(report(), invalid)
        self.assertFalse(invalid.exists())
