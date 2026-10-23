"""Consultas independentes à API; sem CSV, central ou resultados de disco."""

from __future__ import annotations

import io
import json
import copy
import tempfile
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlsplit

from liarte_core.comex import ComexError, ComexProvider
from liarte_core.domain import Period, Selection
from liarte_core.query import checkpoint
from liarte_engine import comexstat_importacoes as engine
from liarte_engine.comex_access import RequestCoordinator
from tests import test_comex


class DirectApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.directory = self.root / "profile" / "dados"
        self.directory.mkdir(parents=True)
        self.transport = test_comex.Transport()
        self.options = []
        self.wire = []
        self.bodies = []
        self.providers = []
        self.reject = None
        self.transform = None
        self.period = Period("2026-09", "2026-09")

    def tearDown(self):
        for provider in self.providers:
            provider.close()
        self.temp.cleanup()

    def network(self, request, **kwargs):
        parts = urlsplit(request.full_url)
        self.assertEqual(parts.scheme, "https")
        self.assertEqual(parts.hostname, "api-comexstat.mdic.gov.br")
        self.wire.append((request.get_method(), parts.path))
        if request.data:
            self.bodies.append(json.loads(request.data))
        if self.reject is not None:
            self.reject(request)
        response = self.transport(request, **kwargs)
        if self.transform is not None and request.get_method() == "POST":
            document = json.loads(response.getvalue())
            return test_comex.Response(self.transform(parts.path, document))
        return response

    def factory(self, **kwargs):
        self.options.append(dict(kwargs))
        client = engine.ComexStatClient(**kwargs)
        client._network_opener = self.network
        return client

    def provider(self, directory=None):
        provider = ComexProvider(
            directory or self.directory,
            client_factory=self.factory,
            codes=("29161220",),
        )
        self.providers.append(provider)
        return provider

    def load(self, provider):
        provider.revalidate_next()
        return provider.load(self.period, Event(), lambda *a: None)

    def test_old_pairings_local_service_and_invalid_query_cache_are_never_read_or_changed(
        self,
    ):
        pair = self.directory / "conexao_comex.json"
        cache = self.directory / "consultas.sqlite3"
        managed = self.directory.parent / "central-comex" / "central.json"
        managed.parent.mkdir()
        for p in (pair, cache, managed):
            p.write_bytes(b"old data deliberately unreadable")
        with (
            patch(
                "liarte_core.comex.load_connection",
                side_effect=AssertionError("pairing read"),
            ),
            patch(
                "liarte_core.comex_automatic.AutomaticAccess",
                side_effect=AssertionError("server"),
            ),
            patch(
                "liarte_core.comex_open_data.OfficialFiles.fetch",
                side_effect=AssertionError("CSV"),
            ),
        ):
            provider = self.provider()
            result = self.load(provider)
        self.assertTrue(provider.direct_api)
        self.assertIsNone(provider._automatic)
        self.assertFalse(result.totals_verified)
        self.assertTrue(result.response_validated)
        self.assertFalse(result.availability.confirmed)
        self.assertEqual(result.availability.updated, "")
        self.assertEqual(result.source_channels, ("comex-api",))
        self.assertEqual(result.api_requests, 2)
        self.assertEqual(result.cache_hits + result.shared_cache_hits, 0)
        self.assertEqual(len(self.wire), 2)
        self.assertEqual(self.wire, [("POST", "/general"), ("POST", "/cities")])
        for options in self.options:
            self.assertFalse(options["use_cache"])
            self.assertIsNone(options["gateway"])
            self.assertEqual(options["min_interval"], 0)
            self.assertEqual(options["max_attempts"], 1)
            self.assertFalse(options["verify_official_totals"])
            self.assertIsNone(options["window_months"])
        for p in (pair, cache, managed):
            self.assertEqual(p.read_bytes(), b"old data deliberately unreadable")
        self.assertFalse((self.directory / "acesso-automatico").exists())

    def test_explicit_same_period_query_obtains_new_values_from_the_api(self):
        provider = self.provider()
        first = self.load(provider)
        old_total = sum(r.cif_cents for r in first.general_records)
        self.transport.general[0]["metricFOB"] = str(
            int(self.transport.general[0]["metricFOB"]) + 1
        )
        self.transport.general[0]["metricCIF"] = str(
            int(self.transport.general[0]["metricCIF"]) + 1
        )
        second = self.load(provider)
        self.assertIsNot(first, second)
        self.assertEqual(
            sum(r.cif_cents for r in second.general_records), old_total + 100
        )
        self.assertEqual(len(self.wire), 4)
        self.assertEqual(second.api_requests, 2)

    def test_filters_pagination_and_base_switch_use_the_current_snapshot_without_api_calls(
        self,
    ):
        provider = self.provider()
        self.load(provider)
        for selection in (
            Selection(self.period),
            Selection(self.period, country="China"),
            Selection(self.period, kind="municipal", sort_column=6),
            Selection(self.period, page=2, page_size=25),
        ):
            provider.query(selection, Event(), lambda *a: None)
        self.assertEqual(len(self.wire), 2)

    def test_two_installations_fetch_independently_and_do_not_share_responses(self):
        first = self.load(self.provider(self.root / "pc1" / "dados"))
        second = self.load(self.provider(self.root / "pc2" / "dados"))
        self.assertEqual(first.general, second.general)
        self.assertEqual(first.municipal, second.municipal)
        self.assertEqual(len(self.wire), 4)
        self.assertEqual(first.api_requests, 2)
        self.assertEqual(second.api_requests, 2)
        self.assertEqual(first.shared_cache_hits + second.shared_cache_hits, 0)

    def test_a_pause_in_another_local_profile_does_not_prevent_this_installation_from_querying(
        self,
    ):
        other = self.root / "other-pc" / "dados"
        gate = RequestCoordinator(other / "acesso_comex.sqlite3")
        gate.defer(600)
        snapshot = self.load(self.provider())
        self.assertTrue(snapshot.response_validated)
        self.assertGreater(gate.status()["pause_seconds"], 590)
        self.assertEqual(self.providers[0].access_status()["pause_seconds"], 0)

    def test_failed_live_data_preserves_previous_snapshot_without_any_followup_request(
        self,
    ):
        provider = self.provider()
        previous = self.load(provider)
        before = len(self.wire)

        def deny(request):
            raise HTTPError(
                request.full_url, 403, "controlled", {}, io.BytesIO(b"not authorized")
            )

        self.reject = deny
        with self.assertRaises(ComexError):
            self.load(provider)
        self.assertEqual(len(self.wire), before + 1)
        self.assertIs(provider.snapshot, previous)

    def test_429_is_recorded_preserves_the_pause_and_never_falls_back_to_csv_or_partial_data(
        self,
    ):
        provider = self.provider()

        def deny(request):
            if request.get_method() == "POST":
                raise HTTPError(
                    request.full_url,
                    429,
                    "controlled",
                    {"Retry-After": "180"},
                    io.BytesIO(b'{"error":{"code":429,"message":"wait"}}'),
                )

        self.reject = deny
        with patch(
            "liarte_core.comex_open_data.OfficialFiles.fetch",
            side_effect=AssertionError("CSV"),
        ):
            with self.assertRaises(ComexError):
                self.load(provider)
        self.assertIsNone(provider.snapshot)
        self.assertEqual(len(self.wire), 1)
        self.assertGreaterEqual(provider.access_status()["pause_seconds"], 179)
        record = json.loads((self.directory / "ultima_falha_comex.json").read_text(encoding="utf-8"))
        self.assertEqual(record["observed_http_status"], 429)
        self.assertEqual(record["retry_after_header"], "180")
        self.assertEqual(record["endpoint"], "/general?language=pt")

    def test_entire_multi_year_period_is_sent_once_to_each_dataset(self):
        period = Period("2024-01", "2026-09")
        result = self.provider().load(period, Event(), lambda *a: None)
        self.assertEqual(result.api_requests, 2)
        self.assertEqual(len(self.bodies), 2)
        for body in self.bodies:
            self.assertEqual(body["period"], {"from": period.start, "to": period.end})
            self.assertTrue(body["monthDetail"])
            self.assertGreater(len(body["details"]), 1)

    def test_whole_embedded_catalog_is_sent_in_a_single_request_per_base(self):
        provider = ComexProvider(self.directory, client_factory=self.factory)
        self.providers.append(provider)
        self.load(provider)
        self.assertEqual(len(self.wire), 2)
        self.assertEqual(
            set(map(str, self.bodies[0]["filters"][0]["values"])), set(provider.codes)
        )
        self.assertEqual(
            set(self.bodies[1]["filters"][0]["values"]),
            {code[:4] for code in provider.codes},
        )

    def test_bad_local_values_codes_and_duplicates_still_block_publication_without_controls(
        self,
    ):
        for mode in (
            "cif",
            "weight",
            "outside-period",
            "outside-code",
            "duplicate-conflict",
        ):

            def transform(path, document):
                row = document["data"]["list"][0]
                if mode == "cif":
                    row["metricCIF"] = "0.01"
                elif mode == "weight":
                    row["metricKG"] = "NaN"
                elif mode == "outside-period":
                    row["monthNumber"] = "08"
                elif mode == "outside-code":
                    row["coNcm"] = "29161230"
                else:
                    duplicate = copy.deepcopy(row)
                    duplicate["metricFOB"] = str(int(row["metricFOB"]) + 1)
                    duplicate["metricCIF"] = str(int(row["metricCIF"]) + 1)
                    document["data"]["list"].append(duplicate)
                return document

            self.transform = transform
            provider = self.provider(self.root / mode)
            with self.subTest(mode=mode), self.assertRaises(ComexError):
                self.load(provider)
            self.assertIsNone(provider.snapshot)

    def test_identical_duplicates_are_counted_once_without_an_extra_download(self):
        self.transport.general.append(copy.deepcopy(self.transport.general[0]))
        result = self.load(self.provider())
        self.assertEqual(len(result.general), len(test_comex.FIXTURE["general"]))
        self.assertEqual(result.api_requests, 2)

    def test_old_preventive_wait_is_ignored_but_an_actual_api_pause_is_preserved(self):
        gate = RequestCoordinator(self.directory / "acesso_comex.sqlite3")
        with gate.acquire(65, 120, check=lambda: None, wait=lambda *a: None):
            pass
        provider = self.provider()
        with patch.object(
            engine.ComexStatClient, "_wait", side_effect=AssertionError("fixed wait")
        ):
            result = self.load(provider)
        self.assertEqual(result.api_requests, 2)
        gate.defer(180)
        self.assertGreaterEqual(provider.access_status()["pause_seconds"], 179)

    def test_export_audit_distinguishes_response_validation_from_independent_reconciliation(
        self,
    ):
        from liarte_core.exports import ExportRequest, export_document

        provider = self.provider()
        snapshot = self.load(provider)
        destination = self.root / "report.xlsx"
        request = ExportRequest("excel", destination, snapshot, Selection(self.period))
        result = export_document(request, Event(), lambda *a: None, self.root / "audit")
        audit = json.loads(
            (self.root / "audit" / (result["sha256"] + ".json")).read_text(encoding="utf-8")
        )
        self.assertTrue(audit["response_validated"])
        self.assertFalse(audit["totals_verified"])
        self.assertIn("Sem consulta adicional", audit["verification"])
        self.assertEqual(audit["source_updated"], "")


class DirectApiUiTests(unittest.TestCase):
    setUp = test_comex.RealQtTests.setUp
    tearDown = test_comex.RealQtTests.tearDown
    item = test_comex.RealQtTests.item
    load = test_comex.RealQtTests.load

    def test_consult_again_uses_new_api_values_without_central_or_cache_option(self):
        from tests.test_qt import settled

        self.load()
        before = len(self.transport.calls)
        self.assertFalse(self.bundle.services.comex_access.state["available"])
        self.assertFalse(self.item("configureComexAccess").property("visible"))
        with patch("liarte_desktop.comex_connection.QProcess.startDetached") as spawn:
            self.bundle.services.comex_access.openCentral()
            spawn.assert_not_called()
        self.controller.queryPeriod("2026-09", "2026-09")
        settled(self.controller)
        self.assertEqual(len(self.transport.calls), before + 2)
        self.assertEqual(self.provider.snapshot.api_requests, 2)
        self.assertEqual(self.bundle.messages, [])

    def test_opening_imports_never_queries_metadata_or_blocks_the_first_consult(self):
        from liarte_desktop.app import install_availability_refresh
        from tests.test_qt import pump

        self.bundle.platform.openModule("home")
        with patch.object(self.controller, "refreshAvailability") as refresh:
            install_availability_refresh(self.bundle)
            self.bundle.platform.openModule("imports")
            pump(lambda: False, 0.3)
            refresh.assert_not_called()
        self.assertEqual(self.transport.calls, [])
        self.assertFalse(self.controller.state["metadataBusy"])

    def test_metadata_wait_is_visible_responsive_and_cancellable(self):
        from tests.test_qt import pump
        from tests.test_comex import click

        entered = Event()

        def wait_for_cancel(cancel, **kwargs):
            entered.set()
            cancel.wait(5)
            checkpoint(cancel)

        with patch.object(self.provider, "availability", side_effect=wait_for_cancel):
            self.controller.refreshAvailability()
            self.assertTrue(
                pump(lambda: entered.is_set() and self.controller.state["metadataBusy"])
            )
            self.assertTrue(self.item("queryProgress").property("visible"))
            self.assertTrue(self.item("queryProgress").property("indeterminate"))
            self.assertTrue(self.item("cancelButton").property("enabled"))
            click(self.window, self.item("cancelButton"))
            self.assertTrue(pump(lambda: not self.controller.state["metadataBusy"]))
        self.assertFalse(self.controller.state["metadataError"])
        self.assertEqual(self.transport.calls, [])
        self.assertEqual(self.bundle.messages, [])
