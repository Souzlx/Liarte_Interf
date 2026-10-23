"""Cliente novo em uso real pelo desktop; testes isolados da rede pública."""

from __future__ import annotations

from decimal import Decimal
import gzip
import io
import json
from pathlib import Path
import ssl
import tempfile
from threading import Event
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
import time
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from liarte_core.comex import ComexError, ComexProvider
from liarte_core.comex_api import ApiClient, ApiPause, ApiRedirects, retry_delay
from liarte_core.domain import Period, Selection
from liarte_core.query import Cancelled, checkpoint
from liarte_engine import comexstat_importacoes as legacy
from tests.test_comex import Transport, RealQtTests, FIXTURE
from tests.test_comex_access import Clock


class BytesResponse(io.BytesIO):
    def __init__(self, data, *, headers=None, status=200):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data)), **(headers or {})}
        self.status = status


def limited(seconds="10"):
    return HTTPError(
        "https://api-comexstat.mdic.gov.br/general",
        429,
        "controlled",
        {} if seconds is None else {"Retry-After": seconds},
        io.BytesIO(b'{"error":{"code":429,"message":"Tente novamente em 10 segundos."}}'),
    )


class NativeApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.transport = Transport()
        self.patch = patch.object(ApiClient, "_open", side_effect=self.transport)
        self.patch.start()
        self.provider = ComexProvider(self.directory, codes=("29161220",))
        self.period = Period("2026-09", "2026-09")

    def tearDown(self):
        self.provider.close()
        self.patch.stop()
        self.temp.cleanup()

    def load(self):
        self.provider.revalidate_next()
        return self.provider.load(self.period, Event(), lambda *a: None)

    def test_production_default_uses_new_client_and_two_requests_without_legacy_services(self):
        with patch.object(legacy, "ComexStatClient", side_effect=AssertionError("legacy")):
            snapshot = self.load()
        self.assertTrue(self.provider._native_api)
        self.assertEqual(self.transport.calls, [("POST", "/general"), ("POST", "/cities")])
        self.assertEqual(snapshot.api_requests, 2)
        self.assertTrue(snapshot.response_validated)
        self.assertFalse(snapshot.totals_verified)
        self.assertEqual(len(snapshot.general), 18)
        self.assertEqual(len(snapshot.municipal), 216)
        self.assertEqual(sum(r.cif_cents for r in snapshot.general_records), 234015200)

    def test_corrupt_old_pairing_and_query_databases_do_not_participate(self):
        for name in ("conexao_comex.json", "consultas.sqlite3", "acesso_comex.sqlite3"):
            (self.directory / name).write_bytes(b"old unusable content")
        result = self.load()
        self.assertEqual(result.api_requests, 2)
        self.assertIsNone(self.provider._automatic)
        self.assertFalse((self.directory / "acesso_api.json").exists())

    def test_explicit_new_consultation_refetches_both_bases_and_changed_values(self):
        first = self.load()
        self.transport.general[0]["metricFOB"] = str(
            int(self.transport.general[0]["metricFOB"]) + 1
        )
        self.transport.general[0]["metricCIF"] = str(
            int(self.transport.general[0]["metricCIF"]) + 1
        )
        second = self.load()
        self.assertEqual(len(self.transport.calls), 4)
        self.assertEqual(
            sum(r.cif_cents for r in second.general_records)
            - sum(r.cif_cents for r in first.general_records),
            100,
        )

    def test_second_period_recovers_municipal_rate_limits_without_repeating_general(self):
        first = self.load()
        clock, waits, calls = Clock(), [], []
        self.provider._api_pause.clock = clock
        refused = 0

        def receive(request, **kwargs):
            nonlocal refused
            path = request.full_url.split(".gov.br", 1)[1].split("?", 1)[0]
            window = json.loads(request.data)["period"]
            calls.append((path, window["from"], window["to"]))
            if path == "/cities" and window["from"] == "2026-01" and refused < 2:
                refused += 1
                raise limited(None)
            return self.transport(request, **kwargs)

        def wait(client, seconds):
            client._check()
            waits.append(seconds)
            clock.wait(seconds)

        self.period = Period("2025-10", "2026-09")
        with (
            patch.object(ApiClient, "_open", side_effect=receive),
            patch.object(ApiClient, "_sleep", new=wait),
            patch("liarte_core.comex_api.time.monotonic", new=clock),
        ):
            second = self.load()
        self.assertEqual(calls, [
            ("/general", "2025-10", "2025-12"),
            ("/general", "2026-01", "2026-09"),
            ("/cities", "2025-10", "2025-12"),
            ("/cities", "2026-01", "2026-09"),
            ("/cities", "2026-01", "2026-09"),
            ("/cities", "2026-01", "2026-09"),
        ])
        self.assertEqual(second.api_requests, 6)
        self.assertEqual(second.period, self.period)
        self.assertIs(self.provider.snapshot, second)
        self.assertIsNot(second, first)
        self.assertEqual(len(second.general), 18)
        self.assertEqual(len(second.municipal), 216)
        self.assertAlmostEqual(sum(waits), 31.5)

    def test_exhausted_municipal_rate_limits_preserve_previous_complete_period(self):
        first = self.load()
        clock, calls = Clock(), []
        self.provider._api_pause.clock = clock

        def receive(request, **kwargs):
            path = request.full_url.split(".gov.br", 1)[1].split("?", 1)[0]
            calls.append(path)
            if path == "/cities":
                raise limited(None)
            return self.transport(request, **kwargs)

        self.period = Period("2025-10", "2026-09")
        with (
            patch.object(ApiClient, "_open", side_effect=receive),
            patch.object(ApiClient, "_sleep", new=lambda client, seconds: clock.wait(seconds)),
            patch("liarte_core.comex_api.time.monotonic", new=clock),
            self.assertRaises(ComexError),
        ):
            self.load()
        self.assertEqual(calls, ["/general", "/general", "/cities", "/cities", "/cities", "/cities"])
        self.assertIs(self.provider.snapshot, first)
        self.assertAlmostEqual(self.provider._api_pause.remaining(), 84)

    def test_full_catalog_uses_one_post_per_base_and_calendar_year_without_metadata(self):
        provider = ComexProvider(self.directory)
        with patch.object(provider, "availability", side_effect=AssertionError("metadata")):
            result = provider.load(Period("2024-01", "2026-09"), Event(), lambda *a: None)
        self.assertEqual(result.api_requests, 6)
        self.assertEqual(self.transport.calls, [("POST", "/general")] * 3 + [("POST", "/cities")] * 3)

    def rectangular_period_transport(self):
        """Model independent year/month bounds, including month-wrap emptiness."""
        calls = []
        periods = [("2025", "03"), ("2025", "10"), ("2025", "12"),
                   ("2026", "01"), ("2026", "09"), ("2026", "10")]

        def receive(request, **kwargs):
            path = request.full_url.split(".gov.br", 1)[1].split("?", 1)[0]
            body = json.loads(request.data)
            start, end = body["period"]["from"], body["period"]["to"]
            calls.append((path, start, end))
            source = FIXTURE["municipal" if path == "/cities" else "general"][0]
            rows = [
                dict(source, year=year, monthNumber=month)
                for year, month in periods
                if start[:4] <= year <= end[:4] and start[5:] <= month <= end[5:]
            ]
            return BytesResponse(json.dumps({"success": True, "data": {"list": rows}}).encode())

        return calls, receive

    def test_cross_year_month_wrap_loads_every_month_instead_of_an_empty_period(self):
        calls, receive = self.rectangular_period_transport()
        self.period = Period("2025-10", "2026-09")
        with patch.object(ApiClient, "_open", side_effect=receive):
            snapshot = self.load()
        expected = {"2025-10", "2025-12", "2026-01", "2026-09"}
        for rows in (snapshot.general, snapshot.municipal):
            self.assertEqual({legacy.row_period(row) for row in rows}, expected)
            self.assertEqual(len(rows), 4)
        self.assertEqual(snapshot.api_requests, 4)
        self.assertEqual(calls, [
            ("/general", "2025-10", "2025-12"),
            ("/general", "2026-01", "2026-09"),
            ("/cities", "2025-10", "2025-12"),
            ("/cities", "2026-01", "2026-09"),
        ])

    def test_cross_year_nonwrapping_month_bounds_do_not_silently_omit_months(self):
        calls, receive = self.rectangular_period_transport()
        self.period = Period("2025-03", "2026-09")
        with patch.object(ApiClient, "_open", side_effect=receive):
            snapshot = self.load()
        expected = {"2025-03", "2025-10", "2025-12", "2026-01", "2026-09"}
        for rows in (snapshot.general, snapshot.municipal):
            self.assertEqual({legacy.row_period(row) for row in rows}, expected)
            self.assertEqual(len(rows), 5)
        self.assertEqual(calls[0], ("/general", "2025-03", "2025-12"))
        self.assertEqual(calls[-1], ("/cities", "2026-01", "2026-09"))

    def test_second_calendar_year_failure_does_not_publish_the_first_year(self):
        first = self.load()
        calls, receive = self.rectangular_period_transport()

        def fail_second_year(request, **kwargs):
            period = json.loads(request.data)["period"]
            if period["from"] == "2026-01":
                raise legacy.ComexStatError("Falha da fonte no segundo ano")
            return receive(request, **kwargs)

        self.period = Period("2025-10", "2026-09")
        with (
            patch.object(ApiClient, "_open", side_effect=fail_second_year),
            self.assertRaisesRegex(ComexError, "segundo ano"),
        ):
            self.load()
        self.assertEqual(calls, [("/general", "2025-10", "2025-12")])
        self.assertIs(self.provider.snapshot, first)
        self.assertEqual(self.provider.snapshot.period, Period("2026-09", "2026-09"))

    def test_each_calendar_year_response_is_validated_against_its_own_bounds(self):
        client = ApiClient(max_attempts=1)
        payload = {"data": {"list": [FIXTURE["general"][0]]}}
        client._network_opener = lambda *args, **kwargs: BytesResponse(json.dumps(payload).encode())
        with self.assertRaisesRegex(legacy.ComexStatError, "período"):
            client.query_imports(("29161220",), "2025-10", "2026-09")
        self.assertEqual(client.network_requests, 1)

    def test_filters_switches_and_exports_never_recontact_the_api(self):
        from liarte_core.exports import ExportRequest, export_document

        snap = self.load()
        for kind in ("general", "municipal", "general"):
            self.provider.query(Selection(self.period, kind=kind), Event(), lambda *a: None)
        selection = Selection(self.period, country="China")
        self.provider.query(selection, Event(), lambda *a: None)
        for kind, suffix in (("excel", ".xlsx"), ("pdf", ".pdf"), ("powerbi", ".zip")):
            request = ExportRequest(kind, self.directory / (kind + suffix), snap, selection)
            export_document(request, Event(), lambda *a: None, self.directory / "audit")
            self.assertTrue(request.destination.is_file())
        self.assertEqual(len(self.transport.calls), 2)

    def test_municipal_failure_preserves_last_complete_snapshot_without_empty_replacement(self):
        first = self.load()
        self.transport.fail_municipal = True
        with self.assertRaises(ComexError):
            self.load()
        self.assertIs(self.provider.snapshot, first)

    def test_non_text_general_labels_never_replace_the_last_valid_snapshot(self):
        first = self.load()
        for field in ("ncm", "state", "urf", "country"):
            row = self.transport.general[0]
            original = row[field]
            for value in ({"name": "China"}, ["China"], True, 105):
                with self.subTest(field=field, value=value):
                    row[field] = value
                    with self.assertRaisesRegex(ComexError, field):
                        self.load()
                    self.assertIs(self.provider.snapshot, first)
            row[field] = original

    def test_non_text_municipal_labels_never_replace_the_last_valid_snapshot(self):
        first = self.load()
        for field in ("noMunMinsgUf", "state", "heading", "country"):
            row = self.transport.municipal[0]
            original = row[field]
            for value in ({"name": "China"}, ["China"], False, 105):
                with self.subTest(field=field, value=value):
                    row[field] = value
                    with self.assertRaisesRegex(ComexError, field):
                        self.load()
                    self.assertIs(self.provider.snapshot, first)
            row[field] = original

    def test_malformed_numeric_strings_never_replace_the_last_valid_snapshot(self):
        first = self.load()
        for kind, fields in (
            ("general", legacy.DEFAULT_METRICS),
            ("municipal", legacy.MUNICIPAL_METRICS),
        ):
            row = getattr(self.transport, kind)[0]
            for field in fields:
                original = row[field]
                for value in ("1_000", "1__2", "١٢"):
                    with self.subTest(kind=kind, field=field, value=value):
                        row[field] = value
                        with self.assertRaisesRegex(ComexError, field):
                            self.load()
                        self.assertIs(self.provider.snapshot, first)
                row[field] = original

    def test_supported_official_numeric_forms_keep_exact_units(self):
        for value in (1234, 1234.0, Decimal("1234.00"), "1.234e3", "+1234.00", "001234.00"):
            with self.subTest(value=value):
                self.assertEqual(legacy.validate_metric(value, "metricFOB", "teste"), 123400)
                self.assertEqual(legacy.validate_metric(value, "metricKG", "teste"), 1234)
        self.assertEqual(legacy.validate_metric("1e-2", "metricFOB", "teste"), 1)

    def test_invalid_cif_and_conflicting_duplicates_are_rejected_by_new_client(self):
        first = self.load()
        self.transport.general[0]["metricCIF"] = "0.01"
        with self.assertRaises(ComexError):
            self.load()
        self.assertIs(self.provider.snapshot, first)
        self.transport.general = [dict(r) for r in FIXTURE["general"]]
        row = dict(self.transport.general[0])
        row["metricFOB"] = str(int(row["metricFOB"]) + 1)
        row["metricCIF"] = str(int(row["metricCIF"]) + 1)
        self.transport.general.append(row)
        with self.assertRaisesRegex(ComexError, "duplicados"):
            self.load()
        self.assertIs(self.provider.snapshot, first)

    def test_identical_duplicates_count_once_and_unknown_code_is_rejected(self):
        self.transport.general.append(dict(self.transport.general[0]))
        self.assertEqual(len(self.load().general), 18)
        client = ApiClient(max_attempts=1)
        data = {"data": {"list": [dict(FIXTURE["general"][0], coNcm="29161230")]}}
        client._network_opener = lambda *a, **k: BytesResponse(json.dumps(data).encode())
        with self.assertRaises(legacy.ComexStatError):
            client.query_imports(("29161220",), "2026-09", "2026-09")

    def test_manually_checking_source_is_separate_and_metadata_is_not_inferred(self):
        snapshot = self.load()
        self.assertEqual(snapshot.availability.latest, "")
        result = self.provider.availability(Event(), force=True)
        self.assertEqual(result.latest, "2026-09")
        self.assertEqual(
            self.transport.calls[-2:],
            [("GET", "/general/dates/updated"), ("GET", "/cities/dates/updated")],
        )

    def test_migration_preserves_only_an_actual_api_pause_and_not_the_old_fixed_interval(self):
        from liarte_engine.comex_access import RequestCoordinator

        path = self.directory / "acesso_comex.sqlite3"
        gate = RequestCoordinator(path)
        with gate.acquire(65, 120, check=lambda: None, wait=lambda *a: None):
            pass
        provider = ComexProvider(self.directory)
        self.assertEqual(provider.access_status()["pause_seconds"], 0)
        gate.defer(180)
        following = ComexProvider(self.directory)
        self.assertGreaterEqual(following.access_status()["pause_seconds"], 179)
        self.assertTrue((self.directory / "acesso_api.json").is_file())


class ApiProtocolTests(unittest.TestCase):
    def client(self, *, attempts=2, rate_attempts=None, path=None):
        self.clock = Clock()
        self.messages = []
        client = ApiClient(
            max_attempts=attempts,
            rate_limit_attempts=rate_attempts,
            pause_state=ApiPause(path, clock=self.clock),
            progress_callback=lambda p, m: self.messages.append(m),
        )
        self.waits = []

        def wait(seconds):
            client._check()
            self.waits.append(seconds)
            self.clock.wait(seconds)

        client._sleep = wait
        return client

    def request(self, client):
        return client.request_json("POST", "/general?language=pt", {})

    def test_a_429_waits_the_informed_ten_seconds_and_recovers_without_fixed_sixty_seconds(self):
        client = self.client()
        responses = [limited(None), BytesResponse(b'{"data":{"list":[]}}')]

        def open_response(*a, **k):
            response = responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return response

        client._network_opener = open_response
        result = self.request(client)
        self.assertEqual(result, {"data": {"list": []}})
        self.assertEqual(client.network_requests, 2)
        self.assertAlmostEqual(sum(self.waits), 10.5)
        self.assertTrue(any("nova tentativa" in m for m in self.messages))

    def test_repeated_429_stops_after_two_requests_and_keeps_real_pause(self):
        client = self.client()
        client._network_opener = lambda *a, **k: (_ for _ in ()).throw(limited(None))
        with self.assertRaises(legacy.ComexRateLimitError):
            self.request(client)
        self.assertEqual(client.network_requests, 2)
        self.assertAlmostEqual(sum(self.waits), 10.5)
        self.assertAlmostEqual(client.pause.remaining(), 10.5)

    def test_extended_rate_limit_policy_recovers_after_two_short_refusals(self):
        client = self.client(rate_attempts=4)
        calls = []

        def receive(*args, **kwargs):
            calls.append(self.clock())
            if len(calls) <= 2:
                raise limited(None)
            return BytesResponse(b'{"data":{"list":[]}}')

        client._network_opener = receive
        with patch("liarte_core.comex_api.time.monotonic", new=self.clock):
            self.assertEqual(self.request(client), {"data": {"list": []}})
        self.assertEqual(calls, [1000, 1010.5, 1031.5])
        self.assertEqual(client.network_requests, 3)
        self.assertAlmostEqual(sum(self.waits), 31.5)

    def test_repeated_rate_limits_stop_at_four_requests_and_persist_extended_pause(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "pause.json"
            client = self.client(rate_attempts=4, path=path)
            client._network_opener = lambda *a, **k: (_ for _ in ()).throw(limited(None))
            with (
                patch("liarte_core.comex_api.time.monotonic", new=self.clock),
                self.assertRaises(legacy.ComexRateLimitError),
            ):
                self.request(client)
            self.assertEqual(client.network_requests, 4)
            self.assertAlmostEqual(sum(self.waits), 73.5)
            self.assertAlmostEqual(client.pause.remaining(), 84)
            self.assertAlmostEqual(ApiPause(path, clock=self.clock).remaining(), 84)

    def test_rate_limit_wait_budget_prevents_a_retry_beyond_ninety_seconds(self):
        client = self.client(rate_attempts=4)
        client._network_opener = lambda *a, **k: (_ for _ in ()).throw(limited("30"))
        with (
            patch("liarte_core.comex_api.time.monotonic", new=self.clock),
            self.assertRaises(legacy.ComexRateLimitError),
        ):
            self.request(client)
        self.assertEqual(client.network_requests, 2)
        self.assertAlmostEqual(sum(self.waits), 30.5)
        self.assertAlmostEqual(client.pause.remaining(), 61)

    def test_cancellation_during_the_second_rate_limit_wait_prevents_a_third_request(self):
        cancel = Event()
        client = self.client(rate_attempts=4)
        client.cancel_check = lambda: checkpoint(cancel)
        client.progress_callback = (
            lambda p, message: cancel.set()
            if client.network_requests == 2 and "Aguardando" in message else None
        )
        client._network_opener = lambda *a, **k: (_ for _ in ()).throw(limited(None))
        with (
            patch("liarte_core.comex_api.time.monotonic", new=self.clock),
            self.assertRaises(Cancelled),
        ):
            self.request(client)
        self.assertEqual(client.network_requests, 2)
        self.assertAlmostEqual(sum(self.waits), 10.5)
        self.assertAlmostEqual(client.pause.remaining(), 21)

    def test_extended_rate_limit_policy_keeps_connection_and_server_errors_at_two_requests(self):
        for status in (None, 503):
            with self.subTest(status=status):
                client = self.client(rate_attempts=4)

                def receive(*args, **kwargs):
                    if status is None:
                        raise URLError("connection reset")
                    return BytesResponse(b"busy", status=status, headers={"Retry-After": "1"})

                client._network_opener = receive
                with (
                    patch("liarte_core.comex_api.time.monotonic", new=self.clock),
                    self.assertRaises(legacy.ComexStatError),
                ):
                    self.request(client)
                self.assertEqual(client.network_requests, 2)
                self.assertAlmostEqual(sum(self.waits), 2 if status is None else 1.5)

    def test_connection_retry_limit_still_applies_when_a_rate_limit_intervenes(self):
        client = self.client(rate_attempts=4)
        responses = [URLError("connection reset"), limited(None), URLError("still offline")]

        def receive(*args, **kwargs):
            if not responses:
                self.fail("The two failed connections must stop recovery")
            raise responses.pop(0)

        client._network_opener = receive
        with (
            patch("liarte_core.comex_api.time.monotonic", new=self.clock),
            self.assertRaises(legacy.ComexStatError),
        ):
            self.request(client)
        self.assertEqual(client.network_requests, 3)
        self.assertAlmostEqual(sum(self.waits), 12.5)

    def test_long_retry_after_is_preserved_without_waiting_minutes_or_repeating(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "pause.json"
            client = self.client(path=path, rate_attempts=4)
            client._network_opener = lambda *a, **k: (_ for _ in ()).throw(limited("1800"))
            with self.assertRaises(legacy.ComexRateLimitError):
                self.request(client)
            self.assertEqual(client.network_requests, 1)
            self.assertEqual(self.waits, [])
            following = ApiPause(path, clock=self.clock)
            self.assertAlmostEqual(following.remaining(), 1800.5)
            self.clock.wait(1801)
            self.assertEqual(following.remaining(), 0)

    def test_retry_after_dates_and_invalid_headers_follow_http_semantics(self):
        self.assertEqual(retry_delay({"Retry-After": "1800"}, "10 segundos"), 1800.5)
        self.assertEqual(
            retry_delay(
                {
                    "Retry-After": "Wed, 21 Oct 2026 19:00:00 GMT",
                    "Date": "Wed, 21 Oct 2026 18:00:00 GMT",
                },
                "",
            ),
            3600.5,
        )
        for value in ("NaN", "Infinity", "-1", "bad"):
            self.assertEqual(retry_delay({"Retry-After": value}, "Tente em 10 segundos"), 10.5)
        self.assertEqual(retry_delay({}, ""), 30)

    def test_200_with_error_code_429_is_not_accepted_as_success(self):
        client = self.client(attempts=1)
        events = []
        client.failure_callback = events.append
        client._network_opener = lambda *a, **k: BytesResponse(
            b'{"success":false,"error":{"code":429,"message":"10 segundos"}}'
        )
        with self.assertRaises(legacy.ComexRateLimitError):
            self.request(client)
        self.assertEqual(events[0]["observed_http_status"], 200)
        self.assertEqual(events[0]["http_status"], 429)
        self.assertAlmostEqual(client.pause.remaining(), 10.5)

    def test_long_pause_keeps_the_observed_200_status_of_a_json_rate_limit(self):
        client = self.client()
        client._network_opener = lambda *a, **k: BytesResponse(
            b'{"success":false,"error":{"code":429,"message":"wait"}}',
            headers={"Retry-After": "1800"},
        )
        with self.assertRaises(legacy.ComexRateLimitError) as caught:
            self.request(client)
        self.assertEqual(caught.exception.observed_http_status, 200)
        self.assertEqual(client.network_requests, 1)

    def test_compressed_rate_limit_message_retains_the_source_wait(self):
        client = self.client(attempts=1)
        raw = gzip.compress(b'{"error":{"code":429,"message":"10 segundos"}}')
        client._network_opener = lambda *a, **k: BytesResponse(
            raw, status=429, headers={"Content-Encoding": "gzip"}
        )
        with self.assertRaises(legacy.ComexRateLimitError):
            self.request(client)
        self.assertAlmostEqual(client.pause.remaining(), 10.5)

    def test_cancellation_during_source_pause_prevents_the_retry(self):
        cancel = Event()
        client = self.client()
        client.cancel_check = lambda: checkpoint(cancel)
        client.progress_callback = lambda p, m: cancel.set() if "Aguardando" in m else None
        client._network_opener = lambda *a, **k: (_ for _ in ()).throw(limited(None))
        with self.assertRaises(Cancelled):
            self.request(client)
        self.assertEqual(client.network_requests, 1)

    def test_certificate_failure_is_never_retried_or_treated_as_rate_limit(self):
        client = self.client(rate_attempts=4)
        error = URLError(ssl.SSLCertVerificationError(1, "unknown issuer"))
        client._network_opener = lambda *a, **k: (_ for _ in ()).throw(error)
        with self.assertRaisesRegex(legacy.ComexStatError, "certificado"):
            self.request(client)
        self.assertEqual(client.network_requests, 1)
        self.assertEqual(client.pause.remaining(), 0)

    def test_a_transient_connection_failure_can_recover_once(self):
        client = self.client()
        with patch.object(
            client,
            "_open",
            side_effect=[URLError("connection reset"), BytesResponse(b'{"data":{}}')],
        ):
            self.assertEqual(self.request(client), {"data": {}})
        self.assertEqual(client.network_requests, 2)
        self.assertEqual(sum(self.waits), 2)

    def test_server_unavailable_can_recover_once_but_403_is_final(self):
        client = self.client()
        with patch.object(
            client,
            "_open",
            side_effect=[
                BytesResponse(b"busy", status=503, headers={"Retry-After": "1"}),
                BytesResponse(b'{"data":{}}'),
            ],
        ):
            self.request(client)
        self.assertEqual(client.network_requests, 2)
        self.assertAlmostEqual(sum(self.waits), 1.5)
        client = self.client()
        client._network_opener = lambda *a, **k: BytesResponse(b"forbidden", status=403)
        with self.assertRaisesRegex(legacy.ComexStatError, "403"):
            self.request(client)
        self.assertEqual(client.network_requests, 1)

    def test_gzip_response_is_decompressed_and_checked_against_wire_content_length(self):
        client = self.client(attempts=1)
        data = gzip.compress(b'{"data":{"list":[]}}')
        client._network_opener = lambda *a, **k: BytesResponse(
            data, headers={"Content-Encoding": "gzip"}
        )
        self.assertEqual(self.request(client), {"data": {"list": []}})

    def test_truncated_corrupt_gzip_or_additional_compressed_stream_is_rejected(self):
        valid = gzip.compress(b'{"data":{}}')
        for payload in (valid[:-4], b"not-gzip", valid + valid):
            client = self.client(attempts=1)
            client._network_opener = lambda *a, **k: BytesResponse(
                payload, headers={"Content-Encoding": "gzip"}
            )
            with self.subTest(payload=payload), self.assertRaises(legacy.ComexStatError):
                self.request(client)

    def test_decompression_limit_cannot_be_bypassed_with_a_small_compressed_response(self):
        client = self.client(attempts=1)
        data = gzip.compress(json.dumps({"data": "x" * 10000}).encode())
        client._network_opener = lambda *a, **k: BytesResponse(
            data, headers={"Content-Encoding": "gzip"}
        )
        with (
            patch("liarte_core.comex_api.MAX_BYTES", 4096),
            self.assertRaises(legacy.ComexStatError),
        ):
            self.request(client)

    def test_invalid_json_numbers_duplicate_keys_html_and_partial_body_are_not_data(self):
        for data in (
            b'{"value":NaN}',
            b'{"value":Infinity}',
            b'{"data":{},"data":[]}',
            b"<html>error</html>",
            b"[]",
        ):
            client = self.client(attempts=1)
            client._network_opener = lambda *a, **k: BytesResponse(data)
            with self.subTest(data=data), self.assertRaises(legacy.ComexStatError):
                self.request(client)
        client = self.client(attempts=1)
        client._network_opener = lambda *a, **k: BytesResponse(
            b'{"data":{}}', headers={"Content-Length": "100"}
        )
        with self.assertRaisesRegex(legacy.ComexStatError, "interrompeu"):
            self.request(client)

    def test_json_decimal_numbers_do_not_pass_through_float_rounding(self):
        client = self.client(attempts=1)
        client._network_opener = lambda *a, **k: BytesResponse(b'{"value":9007199254740992.01}')
        self.assertEqual(self.request(client)["value"], Decimal("9007199254740992.01"))

    def test_unknown_endpoint_and_redirection_never_resend_the_payload(self):
        client = self.client()
        with self.assertRaises(ValueError):
            client.request_json("POST", "https://example.com", {})
        self.assertEqual(client.network_requests, 0)
        with self.assertRaises(legacy.ComexStatError):
            ApiRedirects().redirect_request(None, None, 302, "", {}, "https://example.com")

    def test_pause_write_failure_still_preserves_the_pause_in_memory(self):
        with tempfile.TemporaryDirectory() as temporary:
            client = self.client(path=Path(temporary) / "pause.json")
            with patch("liarte_core.comex_api.atomic_json", side_effect=OSError("disk full")):
                client.pause.defer(180, 429)
            self.assertEqual(client.pause.remaining(), 180)

    def test_constructor_rejects_legacy_modes_or_unbounded_retry_counts(self):
        for options in (
            {"use_cache": True},
            {"gateway": object()},
            {"min_interval": 65},
            {"max_attempts": 100},
            {"rate_limit_attempts": 100},
            {"rate_limit_attempts": 0},
            {"rate_limit_attempts": True},
            {"verify_official_totals": True},
            {"window_months": 12},
        ):
            with self.subTest(options=options), self.assertRaises(ValueError):
                ApiClient(**options)

    def test_ten_clients_in_one_installation_serialize_only_the_network_work(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "pause.json"
            lock = Lock()
            active, peak = 0, 0

            def open_response(*args, **kwargs):
                nonlocal active, peak
                with lock:
                    active += 1
                    peak = max(peak, active)
                time.sleep(0.005)
                with lock:
                    active -= 1
                return BytesResponse(b'{"data":{}}')

            def task(index):
                client = ApiClient(coordinator_path=path)
                client._network_opener = open_response
                return self.request(client)

            with ThreadPoolExecutor(max_workers=10) as pool:
                results = list(pool.map(task, range(10)))
            self.assertEqual(peak, 1)
            self.assertEqual(results, [{"data": {}}] * 10)

    def test_another_client_respects_a_persisted_retry_after_before_any_network_access(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "pause.json"
            first = self.client(path=path)
            first.pause.defer(1800, 429)
            second = ApiClient(coordinator_path=path)
            second.pause.clock = self.clock
            second._network_opener = lambda *args, **kwargs: self.fail("unexpected request")
            with self.assertRaises(legacy.ComexRateLimitError):
                self.request(second)
            self.assertEqual(second.network_requests, 0)


class NativeApiQtTests(unittest.TestCase):
    tearDown = RealQtTests.tearDown
    item = RealQtTests.item
    load = RealQtTests.load

    def setUp(self):
        from liarte_desktop.app import create_bundle
        from tests.test_qt import APP

        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.transport = Transport()
        self.patch = patch.object(ApiClient, "_open", side_effect=self.transport)
        self.patch.start()
        self.provider = ComexProvider(self.directory, codes=("29161220",))
        self.bundle = create_bundle(initial_module="imports", provider=self.provider)
        self.controller = self.bundle.controller
        self.window = self.bundle.engine.rootObjects()[0]
        APP.processEvents()

    def controlled_pause(self):
        clock, release = Clock(), Event()
        self.provider._api_pause.clock = clock

        def wait(client, seconds):
            while not release.wait(0.01):
                client._check()
            client._check()
            clock.wait(seconds)
            client._check()

        return clock, release, patch.object(ApiClient, "_sleep", wait)

    def test_real_desktop_uses_new_client_and_keeps_navigation_local(self):
        from tests.test_qt import settled

        self.load()
        self.assertTrue(self.provider._native_api)
        self.assertEqual(self.provider.snapshot.api_requests, 2)
        self.controller.setDataset("municipal")
        settled(self.controller)
        self.controller.setFilter("country", "China")
        settled(self.controller)
        self.controller.setDataset("general")
        settled(self.controller)
        self.assertEqual(len(self.transport.calls), 2)
        self.assertEqual(self.bundle.messages, [])
        self.assertEqual(self.controller.state["error"], "")

    def test_real_429_wait_is_visible_and_can_be_cancelled_without_a_second_call(self):
        from tests.test_qt import pump, settled

        calls = []

        def deny(*args, **kwargs):
            calls.append(1)
            raise limited("1")

        with patch.object(ApiClient, "_open", side_effect=deny):
            self.controller.queryPeriod("2026-09", "2026-09")
            self.assertTrue(
                pump(lambda: "Aguardando o Comex Stat" in self.controller.state["stage"])
            )
            self.assertTrue(self.controller.state["busy"])
            self.assertTrue(self.item("queryProgress").property("visible"))
            self.assertTrue(self.item("cancelButton").property("enabled"))
            self.controller.cancel()
            settled(self.controller)
        self.assertEqual(len(calls), 1)
        self.assertFalse(self.controller.state["error"])
        self.assertEqual(self.bundle.messages, [])

    def test_second_period_query_recovers_repeated_municipal_limits_without_replaying_general(self):
        from urllib.parse import urlsplit
        from tests.test_qt import pump, settled

        self.load()
        previous, rows = self.provider.snapshot, self.controller.table.rows
        total = sum(row.cif_cents for row in previous.general_records)
        self.transport.general[0]["metricFOB"] = str(Decimal(self.transport.general[0]["metricFOB"]) + 1)
        self.transport.general[0]["metricCIF"] = str(Decimal(self.transport.general[0]["metricCIF"]) + 1)
        _, release, sleeping = self.controlled_pause()
        wire = []

        def receive(request, **kwargs):
            path = urlsplit(request.full_url).path
            wire.append(path)
            if path == "/cities" and wire.count("/cities") <= 2:
                raise limited("1")
            return self.transport(request, **kwargs)

        with sleeping, patch.object(ApiClient, "_open", side_effect=receive):
            try:
                self.controller.queryPeriod("2025-10", "2026-09")
                self.assertTrue(pump(lambda: "Aguardando o Comex Stat" in self.controller.state["stage"]))
                self.assertTrue(self.controller.state["busy"])
                self.assertTrue(self.controller.state["loaded"])
                self.assertFalse(self.controller.state["error"])
                self.assertEqual(self.controller.table.rows, rows)
                self.assertIs(self.provider.snapshot, previous)
                self.assertEqual(self.controller.state["appliedStart"], "2026-09")
                self.assertTrue(self.item("queryProgress").property("visible"))
                self.assertFalse(self.item("queryButton").property("enabled"))
                release.set()
                settled(self.controller)
            finally:
                release.set()
        self.assertEqual(
            wire,
            ["/general", "/general", "/cities", "/cities", "/cities", "/cities"],
        )
        self.assertFalse(self.controller.state["error"])
        self.assertEqual(self.controller.state["appliedStart"], "2025-10")
        self.assertEqual(self.provider.snapshot.period, Period("2025-10", "2026-09"))
        self.assertEqual(sum(row.cif_cents for row in self.provider.snapshot.general_records), total + 100)
        self.assertEqual(self.bundle.messages, [])

    def test_second_query_can_cancel_its_pause_without_losing_the_first_result(self):
        from urllib.parse import urlsplit
        from tests.test_qt import pump, settled

        self.load()
        previous, rows = self.provider.snapshot, self.controller.table.rows
        _, release, sleeping = self.controlled_pause()
        wire = []

        def receive(request, **kwargs):
            path = urlsplit(request.full_url).path
            wire.append(path)
            if path == "/cities":
                raise limited("10")
            return self.transport(request, **kwargs)

        with sleeping, patch.object(ApiClient, "_open", side_effect=receive):
            try:
                self.controller.queryPeriod("2025-10", "2026-09")
                self.assertTrue(pump(lambda: "Aguardando o Comex Stat" in self.controller.state["stage"]))
                self.assertEqual(self.controller.table.rows, rows)
                self.assertTrue(self.item("cancelButton").property("enabled"))
                self.controller.cancel()
                settled(self.controller)
            finally:
                release.set()
        self.assertEqual(wire, ["/general", "/general", "/cities"])
        self.assertIs(self.provider.snapshot, previous)
        self.assertEqual(self.controller.table.rows, rows)
        self.assertTrue(self.controller.state["loaded"])
        self.assertFalse(self.controller.state["error"])
        self.assertEqual(self.controller._selection.period, previous.period)
        self.assertGreater(self.provider.access_status()["pause_seconds"], 0)
        self.assertEqual(self.bundle.messages, [])

    def test_expired_source_pause_reenables_query_without_an_obsolete_seconds_message(self):
        from tests.test_qt import pump, settled

        self.load()
        previous, rows = self.provider.snapshot, self.controller.table.rows
        clock, release, sleeping = self.controlled_pause()
        release.set()
        calls = []

        def deny(*args, **kwargs):
            calls.append(1)
            raise limited("1")

        with sleeping, patch.object(ApiClient, "_open", side_effect=deny):
            self.controller.queryPeriod("2025-10", "2026-09")
            settled(self.controller)
        self.assertEqual(len(calls), 4)
        self.assertIs(self.provider.snapshot, previous)
        self.assertEqual(self.controller.table.rows, rows)
        self.assertGreater(self.controller.state["sourcePauseSeconds"], 0)
        self.assertFalse(self.item("queryButton").property("enabled"))
        self.assertIn("Aguarde", self.item("queryError").property("text"))
        diagnostic = self.controller.state["error"]
        clock.wait(self.provider._api_pause.remaining() + 1)
        self.controller._sync_access_status()
        self.assertTrue(pump(lambda: self.item("queryButton").property("enabled")))
        message = self.item("queryError").property("text")
        self.assertIn("terminou", message)
        self.assertIn("consultar novamente", message)
        self.assertNotIn("Aguarde", message)
        self.assertNotIn("HTTP", message)
        self.assertEqual(self.item("queryError").property("color"), self.item("queryStage").property("color"))
        self.assertEqual(self.controller.state["error"], diagnostic)
        self.assertEqual(len(calls), 4)
        self.assertEqual(self.bundle.messages, [])
