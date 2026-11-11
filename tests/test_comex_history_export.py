"""Exportações preservam a revisão local aceita apesar de novas sincronizações."""

from dataclasses import replace
from decimal import Decimal
import json
from pathlib import Path
from threading import Event
import tempfile
import unittest
from unittest.mock import patch

from openpyxl import load_workbook

from liarte_core.comex_api import ApiClient
from liarte_core.comex_historical import HistoricalComexProvider
from liarte_core.domain import Period, Selection
from liarte_core.exports import ExportRequest, export_document
from tests.test_comex import Transport


class HistoricalComexExportTests(unittest.TestCase):
    def test_saved_request_keeps_its_accepted_rows_and_provenance_after_a_new_publication(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            transport = Transport()
            provider = HistoricalComexProvider(
                directory / "data", codes=("29161220",),
                sync_options={"first_month": "2026-09", "check_interval": 0},
            )
            try:
                period = Period("2026-09", "2026-09")
                with patch.object(ApiClient, "_open", side_effect=transport):
                    provider.synchronize(Event(), lambda *_: None)
                    first = provider.load(period, Event(), lambda *_: None)
                    request = ExportRequest(
                        "excel", directory / "accepted.xlsx", first, Selection(period=period),
                    )
                    original_value = sum(row.cif_cents for row in first.general_records)
                    transport.updated = "2026-10-07"
                    transport.general[0]["metricFOB"] = str(int(transport.general[0]["metricFOB"]) + 17)
                    transport.general[0]["metricCIF"] = str(int(transport.general[0]["metricCIF"]) + 17)
                    provider.synchronize(Event(), lambda *_: None, force=True)
                    second = provider.load(period, Event(), lambda *_: None)
                self.assertNotEqual(first.local_revision, second.local_revision)
                self.assertEqual(sum(row.cif_cents for row in second.general_records), original_value + 1700)

                # Export neither consults the API nor reloads the new manifest.
                with patch.object(ApiClient, "_open", side_effect=AssertionError("network during export")):
                    saved = export_document(request, Event(), lambda *_: None, directory / "audit")
                audit = json.loads((directory / "audit" / (saved["sha256"] + ".json")).read_text())
                self.assertTrue(audit["local_history"])
                self.assertEqual(audit["local_revision"], first.local_revision)
                self.assertEqual(audit["source_publication"], dict(first.source_publication))
                self.assertNotEqual(audit["source_publication"], dict(second.source_publication))
                book = load_workbook(request.destination, read_only=True, data_only=True)
                try:
                    rows = list(book["Base geral"].values)
                    cif = list(rows[0]).index("CIF")
                    self.assertEqual(sum(int(Decimal(str(row[cif])) * 100) for row in rows[1:]), original_value)
                finally:
                    book.close()

                # A subsequent request intentionally identifies the new base.
                next_request = replace(request, destination=directory / "current.xlsx", snapshot=second)
                current = export_document(next_request, Event(), lambda *_: None, directory / "audit")
                next_audit = json.loads((directory / "audit" / (current["sha256"] + ".json")).read_text())
                self.assertEqual(next_audit["local_revision"], second.local_revision)
            finally:
                provider.close()
