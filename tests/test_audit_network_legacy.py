"""Regressões ENG-01..05, sem consultas à API pública."""

from __future__ import annotations

import copy
import io
import json
import sqlite3
import tempfile
import time
import unittest
from decimal import Decimal
from http.client import HTTPException, IncompleteRead
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from uuid import uuid4

from liarte_core.comex_central import CentralBroker
from liarte_core.query import Cancelled
from liarte_engine import comex_access, comex_gateway_client as gateway
from liarte_engine import comexstat_importacoes as engine
from liarte_engine.liarte_dados import IncrementalCache, atomic_json, json_bytes
from liarte_engine.numeric import published_units


FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures/comex_2026-09.json").read_text(encoding="utf-8")
)
CONNECTION = gateway.GatewayConnection(True, "http://central.test:8767", "A" * 40)
EXACT = Decimal("90071992547409.91")


class Response(io.BytesIO):
    status = 200

    def __init__(self, raw, *, failure=None, central=False):
        super().__init__(raw)
        self.failure = failure
        self.headers = {"Content-Length": str(len(raw))}
        if central:
            self.headers["X-Liarte-Protocol"] = gateway.PROTOCOL

    def read1(self, size=-1):
        if self.failure is not None:
            raise self.failure
        return super().read1(size)


class Clock:
    def __init__(self):
        self.now = 1000.0
        self.waits = []

    def __call__(self):
        return self.now

    def wait(self, seconds):
        self.waits.append(seconds)
        self.now += seconds
        return False


def metadata_submission(path="/cities/dates/updated"):
    return dict(
        protocol=gateway.PROTOCOL,
        method="GET",
        path=path,
        body=None,
        revision=None,
        refresh=False,
        request_id=uuid4().hex,
    )


class LegacyWaitAuditTests(unittest.TestCase):
    def test_monotonic_wait_checks_cancellation_without_cancel_wait(self):
        clock = Clock()

        def check():
            if clock.now >= 1000.5:
                raise Cancelled()

        client = engine.ComexStatClient(cancel_check=check)
        with (
            patch.object(engine.time, "monotonic", clock),
            patch.object(engine.time, "sleep", clock.wait),
            self.assertRaises(Cancelled),
        ):
            client._wait(600.5)
        self.assertEqual(clock.waits, [0.25, 0.25])

    def test_monotonic_wait_does_not_shorten_the_requested_delay(self):
        clock = Clock()
        checks = Mock()
        client = engine.ComexStatClient(cancel_check=checks, cancel_wait=clock.wait)
        with patch.object(engine.time, "monotonic", clock):
            client._wait(600.5)
        self.assertEqual(sum(clock.waits), 600.5)
        self.assertLessEqual(max(clock.waits), 0.25)
        self.assertEqual(checks.call_count, len(clock.waits) + 1)

    def test_abandoned_retry_releases_worker_and_keeps_global_retry_after(self):
        waiting, resume = Event(), Event()
        waits, network_calls = [], []

        def factory(**options):
            client = engine.ComexStatClient(**options)

            def opener(*args, **kwargs):
                network_calls.append(1)
                raise HTTPError(
                    "https://official.test/general",
                    429,
                    "limit",
                    {"Retry-After": "600"},
                    io.BytesIO(b"limit"),
                )

            def wait(seconds):
                waits.append(seconds)
                waiting.set()
                if not resume.wait(3):
                    raise AssertionError("O ensaio não liberou a espera controlada.")
                return False

            client._network_opener = opener
            client.cancel_wait = wait
            original = client.request_json

            def request(method, path, body):
                if path == "/cities/dates/updated":
                    return {"success": True, "data": {"year": "2026", "monthNumber": "09"}}
                return original(method, path, body)

            client.request_json = request
            return client

        with tempfile.TemporaryDirectory() as directory:
            broker = CentralBroker(Path(directory), interval=0, client_factory=factory)
            try:
                status, raw, _ = broker.submit(metadata_submission("/general/dates/updated"))
                self.assertEqual(status, 202)
                first = json.loads(raw)["ticket"]
                self.assertTrue(waiting.wait(3))
                with broker.lock:
                    broker.jobs[first].touched = time.time() - 46
                _, raw, _ = broker.submit(metadata_submission())
                second = json.loads(raw)["ticket"]
                resume.set()
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    with broker.lock:
                        if broker.jobs[second].state == "done":
                            break
                    Event().wait(0.01)
                with broker.lock:
                    self.assertEqual(broker.jobs[first].state, "failed")
                    self.assertIn("deixou de ser acompanhada", broker.jobs[first].error)
                    self.assertEqual(broker.jobs[second].state, "done")
                self.assertLessEqual(max(waits), 0.25)
                self.assertGreaterEqual(broker.coordinator.status()["pause_seconds"], 597)
                following = engine.ComexStatClient(
                    min_interval=0, coordinator_path=broker.access_path, max_attempts=1
                )
                following._network_opener = Mock(side_effect=AssertionError("pausa ignorada"))
                with (
                    patch.object(following, "_wait", side_effect=Cancelled),
                    self.assertRaises(Cancelled),
                ):
                    following.request_json("GET", "/general/dates/updated")
                following._network_opener.assert_not_called()
                self.assertEqual(network_calls, [1])
            finally:
                resume.set()
                broker.close()


class LeaseReleaseAuditTests(unittest.TestCase):
    def test_locked_release_is_bounded_and_can_be_retried_after_rollback(self):
        with tempfile.TemporaryDirectory() as directory:
            gate = comex_access.RequestCoordinator(Path(directory) / "access.sqlite3")
            lease = gate.acquire(0, 600, check=lambda: None, wait=time.sleep)
            blocker = sqlite3.connect(gate.path)
            try:
                blocker.execute("BEGIN IMMEDIATE")
                start = time.monotonic()
                with (
                    patch.object(comex_access.time, "sleep") as sleep,
                    self.assertRaises(comex_access.AccessError),
                ):
                    lease.release()
                self.assertLess(time.monotonic() - start, 2)
                self.assertEqual(sleep.call_count, 2)
                self.assertTrue(lease.active)
                blocker.rollback()
                lease.release()
                self.assertFalse(lease.active)
                with gate.connect() as db:
                    self.assertEqual(
                        db.execute("SELECT owner, lease_until FROM access").fetchone(), ("", 0)
                    )
            finally:
                blocker.close()

    def test_short_lock_is_retried_during_context_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            gate = comex_access.RequestCoordinator(Path(directory) / "access.sqlite3")
            lease = gate.acquire(0, 600, check=lambda: None, wait=time.sleep)
            blocker = sqlite3.connect(gate.path)
            try:
                with patch.object(
                    comex_access.time, "sleep", side_effect=lambda _: blocker.rollback()
                ) as sleep:
                    with lease:
                        blocker.execute("BEGIN IMMEDIATE")
                    self.assertEqual(sleep.call_count, 1)
                self.assertFalse(lease.active)
                with gate.connect() as db:
                    self.assertEqual(db.execute("SELECT owner FROM access").fetchone()[0], "")
            finally:
                blocker.close()

    def test_failed_stale_owner_cannot_release_replacement_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            clock = Clock()
            gate = comex_access.RequestCoordinator(Path(directory) / "access.sqlite3", clock=clock)
            old = gate.acquire(0, 1, check=lambda: None, wait=clock.wait)
            with patch.object(
                gate, "connect", side_effect=sqlite3.OperationalError("disk I/O error")
            ) as connect:
                with self.assertRaises(comex_access.AccessError):
                    old.release()
                self.assertEqual(connect.call_count, 1)
            self.assertTrue(old.active)
            clock.now += 2
            new = gate.acquire(0, 600, check=lambda: None, wait=clock.wait)
            old.release()
            with gate.connect() as db:
                self.assertEqual(db.execute("SELECT owner FROM access").fetchone()[0], new.token)
            new.release()


class InterruptedReadAuditTests(unittest.TestCase):
    def test_legacy_open_and_read_failures_retry_then_return_only_complete_response(self):
        for stage in ("open", "read", "error_body"):
            for exception in (IncompleteRead(b'{"bad":true}', 50), HTTPException("protocol")):
                with self.subTest(stage=stage, exception=type(exception).__name__):
                    calls = []

                    def opener(*args, **kwargs):
                        calls.append(1)
                        if len(calls) == 1:
                            if stage == "open":
                                raise exception
                            response = Response(b"", failure=exception)
                            if stage == "error_body":
                                response.read = response.read1
                                raise HTTPError(
                                    "https://official.test/general", 500, "failed", {}, response
                                )
                            return response
                        return Response(b'{"success":true,"data":{"complete":true}}')

                    client = engine.ComexStatClient(min_interval=0, max_attempts=3)
                    client._network_opener = opener
                    with patch.object(client, "_wait"):
                        payload = client.request_json("GET", "/general/dates/updated")
                    self.assertEqual(payload, {"success": True, "data": {"complete": True}})
                    self.assertEqual(len(calls), 2)

    def test_legacy_incomplete_reads_exhaust_the_attempt_budget(self):
        client = engine.ComexStatClient(min_interval=0, max_attempts=3)
        client._network_opener = Mock(
            side_effect=lambda *a, **kw: Response(
                b"", failure=IncompleteRead(b'{"success":true}', 50)
            )
        )
        with (
            patch.object(client, "_wait") as wait,
            self.assertRaisesRegex(engine.ComexStatError, "Não foi possível acessar o Comex Stat"),
        ):
            client.request_json("GET", "/general/dates/updated")
        self.assertEqual(client._network_opener.call_count, 3)
        self.assertEqual(wait.call_count, 2)

    def test_interrupted_rate_limit_body_still_persists_the_official_pause(self):
        with tempfile.TemporaryDirectory() as directory:
            client = engine.ComexStatClient(
                min_interval=0, max_attempts=1, coordinator_path=Path(directory) / "access.sqlite3"
            )
            response = Response(b"", failure=IncompleteRead(b"limited", 50))
            response.read = response.read1
            client._network_opener = Mock(
                side_effect=HTTPError(
                    "https://official.test/general", 429, "limit", {"Retry-After": "600"}, response
                )
            )
            with self.assertRaises(engine.ComexRateLimitError):
                client.request_json("GET", "/general/dates/updated")
            self.assertGreaterEqual(client._coordinator.status()["pause_seconds"], 600)

    def test_central_normalizes_open_and_read_http_errors_with_cause(self):
        for stage in ("open", "read"):
            with self.subTest(stage=stage):
                error = IncompleteRead(b'{"success":true}', 30)
                opener = Mock()
                if stage == "open":
                    opener.open.side_effect = error
                else:
                    opener.open.return_value = Response(b"", failure=error, central=True)
                with (
                    patch.object(gateway, "build_opener", return_value=opener),
                    self.assertRaises(gateway.GatewayError) as caught,
                ):
                    gateway.central_http(CONNECTION, "GET", "/v1/health", None)
                self.assertIs(caught.exception.__cause__, error)

    def test_shared_request_recovers_and_exhausts_exactly_three_incomplete_reads(self):
        for recover in (True, False):
            with self.subTest(recover=recover):
                calls = []

                def open_response(*args, **kwargs):
                    calls.append(1)
                    if not recover or len(calls) == 1:
                        return Response(
                            b"", failure=IncompleteRead(b'{"bad":true}', 20), central=True
                        )
                    return Response(b'{"success":true,"data":{"complete":true}}', central=True)

                opener = SimpleNamespace(open=open_response)
                wait = Mock()
                with patch.object(gateway, "build_opener", return_value=opener):

                    def request():
                        return gateway.request_shared(
                            CONNECTION,
                            "GET",
                            "/general/dates/updated",
                            None,
                            revision=None,
                            refresh=False,
                            check=lambda: None,
                            wait=wait,
                            notify=lambda *args: None,
                        )

                    if recover:
                        self.assertEqual(request()[0]["data"], {"complete": True})
                    else:
                        with self.assertRaisesRegex(engine.ComexStatError, "interrompida"):
                            request()
                self.assertEqual(len(calls), 2 if recover else 3)
                self.assertEqual(wait.call_count, 1 if recover else 2)

    def test_cooperative_cancellation_and_programming_errors_are_not_retried(self):
        with patch.object(gateway, "central_http", side_effect=Cancelled) as http:
            with self.assertRaises(Cancelled):
                gateway.request_shared(
                    CONNECTION,
                    "GET",
                    "/general/dates/updated",
                    None,
                    revision=None,
                    refresh=False,
                    check=lambda: None,
                    wait=lambda _: None,
                    notify=lambda *args: None,
                )
            self.assertEqual(http.call_count, 1)
        with patch.object(gateway, "central_http", side_effect=ValueError("bug")) as http:
            with self.assertRaisesRegex(ValueError, "bug"):
                gateway.request_shared(
                    CONNECTION,
                    "GET",
                    "/general/dates/updated",
                    None,
                    revision=None,
                    refresh=False,
                    check=lambda: None,
                    wait=lambda _: None,
                    notify=lambda *args: None,
                )
            self.assertEqual(http.call_count, 1)


class MunicipalCliAuditTests(unittest.TestCase):
    def test_municipal_failure_aborts_cli_and_preserves_previous_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.xlsx"
            previous = {
                output: b"previous workbook",
                output.with_suffix(".zip"): b"previous BI",
                output.with_suffix(".manifesto.json"): b"previous manifest",
            }
            for path, raw in previous.items():
                path.write_bytes(raw)
            client = Mock(source_revision=None, cache=None)
            client.latest_published_period.return_value = ("2026-09", None)
            client.query_imports.return_value = FIXTURE["general"]
            client.query_municipal_imports.side_effect = engine.ComexStatError(
                "Falha municipal controlada"
            )
            with (
                patch.object(engine, "ComexStatClient", return_value=client),
                patch.object(engine, "create_report") as report,
                patch.object(engine, "create_manifest") as manifest,
                patch("sys.stderr", new_callable=io.StringIO) as stderr,
            ):
                result = engine.main(
                    ["--inicio", "2026-09", "--fim", "2026-09", "--saida", str(output)]
                )
            self.assertEqual(result, 1)
            self.assertIn("Falha municipal controlada", stderr.getvalue())
            client.close.assert_called_once()
            report.assert_not_called()
            manifest.assert_not_called()
            for path, raw in previous.items():
                self.assertEqual(path.read_bytes(), raw)

    def test_municipal_programming_error_is_propagated_before_publication(self):
        client = Mock(source_revision=None, cache=None)
        client.latest_published_period.return_value = ("2026-09", None)
        client.query_imports.return_value = []
        client.query_municipal_imports.side_effect = TypeError("programming error")
        with (
            patch.object(engine, "ComexStatClient", return_value=client),
            patch.object(engine, "create_report") as report,
        ):
            with self.assertRaisesRegex(TypeError, "programming error"):
                engine.run(engine.parse_args(["--inicio", "2026-09", "--sem-power-bi"]))
        report.assert_not_called()
        client.close.assert_called_once()

    def test_empty_municipal_result_and_explicit_skip_remain_valid(self):
        for skip in (False, True):
            with self.subTest(skip=skip):
                client = Mock(source_revision=None, cache=None)
                client.latest_published_period.return_value = ("2026-09", None)
                client.query_imports.return_value = []
                client.query_municipal_imports.return_value = []
                argv = ["--inicio", "2026-09", "--sem-power-bi"] + (
                    ["--sem-municipios"] if skip else []
                )
                with (
                    patch.object(engine, "ComexStatClient", return_value=client),
                    patch.object(engine, "create_report") as report,
                    patch.object(engine, "create_manifest") as manifest,
                ):
                    engine.run(engine.parse_args(argv))
                self.assertEqual(report.call_args.kwargs["municipal_rows"], [])
                self.assertEqual(
                    manifest.call_args.kwargs["municipal_status"], "skipped" if skip else "complete"
                )
                self.assertEqual(client.query_municipal_imports.call_count, 0 if skip else 1)


class ExactJsonAuditTests(unittest.TestCase):
    def test_legacy_json_numbers_and_strings_keep_exact_cents(self):
        raw = b'{"data":{"value":90071992547409.91,"string":"90071992547409.91","ordinary":1.25,"integer":5}}'
        client = engine.ComexStatClient(min_interval=0)
        client._network_opener = lambda *a, **kw: Response(raw)
        data = client.request_json("GET", "/general/dates/updated")["data"]
        self.assertEqual(data["value"], EXACT)
        self.assertEqual(published_units(data["value"], places=2), 9007199254740991)
        self.assertEqual(data["string"], "90071992547409.91")
        self.assertEqual(data["ordinary"], Decimal("1.25"))
        self.assertEqual(data["integer"], 5)

    def test_decimal_numbers_roundtrip_shared_serializer_cache_and_central(self):
        value = {
            "value": EXACT,
            "text": "90071992547409.91",
            "normal": 1.25,
            "integer": 3,
            "flags": [True, None],
        }
        raw = json_bytes(value)
        self.assertIn(b'"value":90071992547409.91', raw)
        self.assertEqual(json.loads(raw, parse_float=Decimal), value)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "exact.json"
            atomic_json(path, value)
            self.assertEqual(json.loads(path.read_bytes(), parse_float=Decimal), value)
            cache = IncrementalCache(Path(directory) / "cache.sqlite3")
            cache._store("general", "contract", {("12345678", "2026-09"): [value]}, time.time())
            cached = cache._load("general", "contract", "2026-09", "2026-09")
            self.assertEqual(cached[("12345678", "2026-09")][0], [value])
            self.assertFalse(cache.stats["unavailable"])
            response = Response(json_bytes({"success": True, "data": value}), central=True)
            with patch.object(
                gateway,
                "build_opener",
                return_value=SimpleNamespace(open=lambda *a, **kw: response),
            ):
                status, payload, _ = gateway.central_http(CONNECTION, "GET", "/v1/jobs/id", None)
            self.assertEqual(status, 200)
            self.assertEqual(payload["data"]["value"], EXACT)

    def test_decimal_protocol_poll_intervals_and_rate_limit_are_accepted(self):
        pending = Response(json_bytes({"ticket": "a" * 32, "poll_after": 1.25}), central=True)
        pending.status = 202
        responses = [
            pending,
            Response(json_bytes({"success": True, "data": {"value": EXACT}}), central=True),
        ]
        wait = Mock()
        with patch.object(
            gateway,
            "build_opener",
            return_value=SimpleNamespace(open=lambda *a, **kw: responses.pop(0)),
        ):
            payload, _ = gateway.request_shared(
                CONNECTION,
                "GET",
                "/general/dates/updated",
                None,
                revision=None,
                refresh=False,
                check=lambda: None,
                wait=wait,
                notify=lambda *args: None,
            )
        self.assertEqual(payload["data"]["value"], EXACT)
        wait.assert_called_once_with(1.25)
        with patch.object(
            gateway,
            "central_http",
            return_value=(429, {"code": "COMEX_RATE_LIMIT", "retry_after": Decimal("600.5")}, {}),
        ):
            with self.assertRaises(engine.ComexRateLimitError) as caught:
                gateway.request_shared(
                    CONNECTION,
                    "GET",
                    "/general/dates/updated",
                    None,
                    revision=None,
                    refresh=False,
                    check=lambda: None,
                    wait=wait,
                    notify=lambda *args: None,
                )
        self.assertEqual(caught.exception.retry_after, 601)

    def test_validated_legacy_queries_reuse_large_decimal_rows_from_cache(self):
        row = copy.deepcopy(FIXTURE["general"][0])
        row.update(
            metricFOB=EXACT,
            metricCIF=EXACT,
            metricFreight=Decimal("0.00"),
            metricInsurance=Decimal("0.00"),
            metricKG=1,
        )
        with tempfile.TemporaryDirectory() as directory:
            options = dict(
                min_interval=0,
                use_cache=True,
                cache_path=Path(directory) / "cache.sqlite3",
                source_revision={"updated": "2026-10-06"},
                verify_official_totals=False,
            )
            first = engine.ComexStatClient(**options)
            first._network_opener = Mock(
                side_effect=lambda *a, **kw: Response(
                    json_bytes({"success": True, "data": {"list": [row]}})
                )
            )
            rows = first.query_imports([row["coNcm"]], "2026-09", "2026-09", 35)
            second = engine.ComexStatClient(**options)
            second._network_opener = Mock(side_effect=AssertionError("cache exato não utilizado"))
            cached = second.query_imports([row["coNcm"]], "2026-09", "2026-09", 35)
            self.assertEqual(rows, cached)
            self.assertEqual(published_units(cached[0]["metricFOB"], places=2), 9007199254740991)
            second._network_opener.assert_not_called()
            self.assertEqual(second.cache.stats["hits"], 1)


if __name__ == "__main__":
    unittest.main()
