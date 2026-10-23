"""Fila real, pausa persistente e HTTP da central. Nenhuma chamada ao Comex público."""

from __future__ import annotations

import copy
import io
import json
import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from threading import Event, Lock
from unittest.mock import patch
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import HTTPError
from uuid import uuid4

from liarte_engine import comexstat_importacoes as engine
from liarte_engine.comex_access import RequestCoordinator
from liarte_engine.comex_gateway_client import (
    GatewayConnection,
    GatewayError,
    PROTOCOL,
    central_http,
    export_connection,
    import_connection,
    load_connection,
    request_shared,
    save_connection,
)
from liarte_core.comex_central import CentralBroker, CentralServer, SharedResponses
from liarte_core.query import Cancelled

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures/comex_2026-09.json").read_text(encoding="utf-8")
)
TOKEN = "teste_" + "A" * 40


def submission(*, refresh=False, revision=None):
    code = FIXTURE["general"][0]["coNcm"]
    return {
        "protocol": PROTOCOL,
        "method": "POST",
        "path": "/general?language=pt",
        "body": {
            "flow": "import",
            "monthDetail": True,
            "period": {"from": "2026-09", "to": "2026-09"},
            "filters": [{"filter": "ncm", "values": [int(code)]}],
            "details": list(engine.DEFAULT_DETAILS),
            "metrics": list(engine.DEFAULT_METRICS),
        },
        "revision": revision,
        "refresh": refresh,
        "request_id": uuid4().hex,
    }


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def wait(self, seconds):
        self.now += seconds


class ComexAccessTests(unittest.TestCase):
    def test_retry_after_is_not_shortened_and_accepts_http_dates_without_date_header(self):
        self.assertEqual(
            engine.ComexStatClient._retry_seconds({"Retry-After": "1800"}, "", 1), 1800.5
        )
        self.assertEqual(
            engine.ComexStatClient._retry_seconds(
                {
                    "Retry-After": "Wed, 21 Oct 2026 19:00:00 GMT",
                    "Date": "Wed, 21 Oct 2026 18:00:00 GMT",
                },
                "",
                1,
            ),
            3600.5,
        )
        target = datetime.now(timezone.utc) + timedelta(seconds=900)
        delay = engine.ComexStatClient._retry_seconds(
            {"Retry-After": format_datetime(target)}, "", 1
        )
        self.assertTrue(899 <= delay <= 901)
        self.assertGreaterEqual(engine.ComexStatClient._retry_seconds({}, "", 1), 60)

    def test_last_429_persists_pause_for_a_new_client_and_cancel_prevents_network(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "access.sqlite3"
            clock = Clock()
            client = engine.ComexStatClient(max_attempts=1, min_interval=0, coordinator_path=path)
            client._coordinator.clock = clock

            def limited(*args, **kwargs):
                raise HTTPError(
                    "https://api-comexstat.mdic.gov.br/general",
                    429,
                    "limit",
                    {"Retry-After": "600"},
                    io.BytesIO(b"limit"),
                )

            client._network_opener = limited
            with self.assertRaisesRegex(engine.ComexStatError, "HTTP 429"):
                client.request_json("POST", "/general", {})
            following = engine.ComexStatClient(
                max_attempts=1, min_interval=0, coordinator_path=path
            )
            following._coordinator.clock = clock
            self.assertGreaterEqual(following._coordinator.status()["pause_seconds"], 600)
            calls = []
            following._network_opener = lambda *args, **kwargs: calls.append(1)

            def cancel(seconds):
                raise Cancelled()

            following._wait = cancel
            with self.assertRaises(Cancelled):
                following.request_json("POST", "/general", {})
            self.assertEqual(calls, [])

    def test_json_rate_limit_also_sets_the_shared_pause(self):
        from tests.test_comex import Response

        with tempfile.TemporaryDirectory() as directory:
            client = engine.ComexStatClient(
                max_attempts=1, min_interval=0, coordinator_path=Path(directory) / "access.sqlite3"
            )
            client._network_opener = lambda *args, **kwargs: Response(
                {"success": False, "code": 429, "error": "rate limited"}
            )
            with self.assertRaises(engine.ComexStatError):
                client.request_json("GET", "/general/dates/updated")
            self.assertGreaterEqual(client._coordinator.status()["pause_seconds"], 59)

    def test_ten_local_clients_are_serial_and_have_spacing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "access.sqlite3"
            # Construct independently, as happens with metadata, periods and different app instances.
            gates = [RequestCoordinator(path) for _ in range(10)]
            times, active, maximum = [], [0], [0]
            lock = Lock()

            def run(gate):
                with gate.acquire(0.015, 2, check=lambda: None, wait=time.sleep):
                    with lock:
                        active[0] += 1
                        maximum[0] = max(maximum[0], active[0])
                        times.append(time.monotonic())
                    time.sleep(0.01)
                    with lock:
                        active[0] -= 1

            with ThreadPoolExecutor(max_workers=10) as pool:
                list(pool.map(run, gates))
            self.assertEqual(maximum[0], 1)
            self.assertEqual(len(times), 10)
            self.assertTrue(all(b - a >= 0.02 for a, b in zip(times, times[1:])))

    def test_abandoned_lease_expires_and_a_stale_owner_cannot_release_the_new_one(self):
        with tempfile.TemporaryDirectory() as directory:
            clock = Clock()
            gate = RequestCoordinator(Path(directory) / "access.sqlite3", clock=clock)
            first = gate.acquire(0, 1, check=lambda: None, wait=clock.wait)
            clock.wait(2)
            second = gate.acquire(0, 2, check=lambda: None, wait=clock.wait)
            first.release()
            with gate.connect() as db:
                self.assertEqual(db.execute("SELECT owner FROM access").fetchone()[0], second.token)
            second.release()

    def test_two_processes_share_a_pause_without_network_storage(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "access.sqlite3"
            gate = RequestCoordinator(path)
            gate.defer(60)
            script = 'from pathlib import Path; from liarte_engine.comex_access import RequestCoordinator; import sys; print(RequestCoordinator(Path(sys.argv[1])).status()["pause_seconds"])'
            result = subprocess.run(
                [sys.executable, "-c", script, str(path)],
                env=dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src")),
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertGreaterEqual(int(result.stdout.strip()), 58)

    def test_configuration_roundtrip_pairing_and_invalid_config_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "connection.json"
            self.assertFalse(load_connection(path).enabled)
            expected = GatewayConnection(True, "http://127.0.0.1:8767", TOKEN)
            save_connection(path, expected)
            self.assertEqual(load_connection(path), expected)
            exported = path.with_suffix(".liarte-conexao")
            export_connection(exported, expected)
            self.assertEqual(import_connection(exported), expected)
            path.write_text("{broken", encoding="utf-8")
            with self.assertRaises(GatewayError):
                load_connection(path)
        for url in (
            "file:///tmp/abc",
            "http://user:pass@host",
            "http://:@host",
            "http://host/?token=x",
            "http://0.0.0.0:8767",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                GatewayConnection(True, url, TOKEN)

    def test_unreadable_connection_never_enables_direct_access(self):
        with patch.object(Path, "stat", side_effect=PermissionError("access denied")):
            with self.assertRaises(GatewayError):
                load_connection(Path("protected-connection.json"))

    def test_shared_response_expiry_and_corruption_are_not_silently_used(self):
        with tempfile.TemporaryDirectory() as directory:
            clock = Clock()
            cache = SharedResponses(Path(directory) / "replies.sqlite3", clock=clock)
            raw = b'{"success":true,"data":{}}'
            cache.put("key", raw, 1)
            self.assertEqual(cache.get("key"), raw)
            clock.wait(2)
            self.assertIsNone(cache.get("key"))
            self.assertEqual(cache.get("key", allow_expired=True), raw)
            with closing(cache.connect()) as db, db:
                db.execute("UPDATE replies SET body=?", (b"bad",))
                db.commit()
            self.assertIsNone(cache.get("key", allow_expired=True))


class ComexCentralTests(unittest.TestCase):
    def setUp(self):
        from tests.test_comex import Transport

        self.temp = tempfile.TemporaryDirectory()
        self.transport = Transport()

        def factory(**kwargs):
            kwargs["min_interval"] = 0.01
            client = engine.ComexStatClient(**kwargs)

            def delayed(*args, **kwargs):
                time.sleep(0.025)
                return self.transport(*args, **kwargs)

            client._network_opener = delayed
            return client

        self.broker = CentralBroker(Path(self.temp.name), interval=0.01, client_factory=factory)
        self.server = CentralServer(self.broker, TOKEN, port=0)
        self.server.start()
        self.connection = GatewayConnection(True, f"http://127.0.0.1:{self.server.port}", TOKEN)

    def tearDown(self):
        self.server.close()
        self.temp.cleanup()

    def wait_ticket(self, ticket):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            status, document, headers = central_http(
                self.connection, "GET", "/v1/jobs/" + ticket, None
            )
            if status != 202:
                return status, document, headers
            time.sleep(0.02)
        self.fail("Consulta não concluiu")

    def request(self, selected):
        return request_shared(
            self.connection,
            selected["method"],
            selected["path"],
            selected["body"],
            revision=selected["revision"],
            refresh=selected["refresh"],
            check=lambda: None,
            wait=lambda s: time.sleep(min(s, 0.02)),
            notify=lambda *args: None,
        )

    def test_ten_computers_same_request_use_one_origin_response(self):
        selected = submission()
        with ThreadPoolExecutor(max_workers=10) as pool:
            results = list(pool.map(lambda _: self.request(selected), range(10)))
        self.assertEqual(len(self.transport.calls), 1)
        documents = [value[0] for value in results]
        self.assertTrue(all(documents[0] == value for value in documents))
        expected = [
            r
            for r in FIXTURE["general"]
            if r["coNcm"] == str(selected["body"]["filters"][0]["values"][0])
        ]
        self.assertEqual(documents[0]["data"]["list"], expected)
        self.assertEqual(sum(shared for _, shared in results), 9)
        self.assertEqual(self.broker.status()["completed"], 1)

    def test_revision_and_control_dimensions_never_share_a_wrong_result(self):
        original = submission(revision={"updated": "2026-10-06"})
        data, _ = self.request(original)
        second = copy.deepcopy(original)
        second["body"]["details"] = ["ncm"]
        control, _ = self.request(second)
        self.assertNotEqual(data, control)
        third = copy.deepcopy(original)
        third["revision"] = {"updated": "2026-10-07"}
        _, shared = self.request(third)
        self.assertFalse(shared)
        self.assertEqual(len(self.transport.calls), 3)

    def test_complete_details_survive_short_failures_with_publication_revision(self):
        selected = submission(revision={"updated": "2026-10-06"})
        original, shared = self.request(selected)
        self.assertFalse(shared)
        self.broker.cache.clock = lambda: time.time() + 600
        repeated, shared = self.request(selected)
        self.assertTrue(shared)
        self.assertEqual(original, repeated)
        self.assertEqual(len(self.transport.calls), 1)

    def test_force_refresh_keeps_old_ticket_immutable_and_submission_idempotent(self):
        original = submission(refresh=True)
        status, ticket, _ = central_http(self.connection, "POST", "/v1/query", original)
        self.assertEqual(status, 202)
        status, first, _ = self.wait_ticket(ticket["ticket"])
        self.assertEqual(status, 200)
        status, again, _ = central_http(self.connection, "POST", "/v1/query", original)
        self.assertEqual(status, 200)
        self.assertEqual(first, again)
        self.assertEqual(len(self.transport.calls), 1)
        selected = submission(refresh=True)
        self.request(selected)
        self.assertEqual(len(self.transport.calls), 2)
        self.assertEqual(self.wait_ticket(ticket["ticket"])[1], first)

    def test_auth_and_ssrf_blocking_never_contact_origin(self):
        invalid = replace(self.connection, token="B" * 40)
        status, _, _ = central_http(invalid, "GET", "/v1/health", None)
        self.assertEqual(status, 401)
        cases = []
        bad = submission()
        bad["path"] = "https://example.com"
        cases.append(bad)
        bad = submission()
        bad["body"]["flow"] = "export"
        cases.append(bad)
        bad = submission()
        bad["body"]["filters"][0]["values"] = [99999999]
        cases.append(bad)
        bad = submission()
        bad["body"]["period"]["from"] = "2025-01"
        cases.append(bad)
        for case in cases:
            status, _, _ = central_http(self.connection, "POST", "/v1/query", case)
            self.assertEqual(status, 422)
        self.assertEqual(self.transport.calls, [])

    def test_invalid_source_is_not_cached_or_published(self):
        self.transport.general[0]["metricCIF"] = "1"
        with self.assertRaises(engine.ComexStatError):
            self.request(submission())
        self.assertEqual(self.broker.status()["completed"], 0)
        self.assertEqual(self.broker.status()["cache_hits"], 0)

    def test_central_unavailable_never_falls_back_to_the_official_api(self):
        self.server.close()
        with self.assertRaises(engine.ComexStatError):
            self.request(submission())
        self.assertEqual(self.transport.calls, [])

    def test_shutdown_closes_keepalive_connections_and_is_idempotent(self):
        from http.client import HTTPConnection

        connection = HTTPConnection("127.0.0.1", self.server.port, timeout=3)
        try:
            connection.request("GET", "/v1/health", headers={"Authorization": "Bearer " + TOKEN})
            reply = connection.getresponse()
            self.assertEqual(reply.status, 200)
            reply.read()
            self.server.close()
            self.server.close()
            self.assertFalse(self.server.thread.is_alive())
            self.assertEqual(self.server._channels, {})
        finally:
            connection.close()

    def test_full_provider_uses_shared_responses_and_keeps_exact_general_and_municipal_totals(self):
        from liarte_core.comex import ComexProvider
        from liarte_core.domain import Period

        code = FIXTURE["general"][0]["coNcm"]
        results = []
        for i in range(2):
            directory = Path(self.temp.name) / f"pc_{i}"
            save_connection(directory / "conexao_comex.json", self.connection)
            provider = ComexProvider(directory, codes=(code,), automatic_access=True)
            result = provider.load(Period("2026-09", "2026-09"), Event(), lambda *a: None)
            results.append(result)
        self.assertEqual(results[0].general, results[1].general)
        self.assertEqual(results[0].municipal, results[1].municipal)
        self.assertTrue(all(s.totals_verified for s in results))
        self.assertGreater(results[1].shared_cache_hits, 0)
        self.assertEqual(results[1].api_requests, 0)
        self.assertEqual(
            len(self.transport.calls), 6
        )  # metadata x2, general/control, municipal/control


class ComexConnectionUiTests(unittest.TestCase):
    def setUp(self):
        from liarte_desktop.app import create_bundle
        from liarte_core.comex import ComexProvider
        from tests.test_comex import factory

        self.temp = tempfile.TemporaryDirectory()
        self.provider = ComexProvider(
            Path(self.temp.name), client_factory=factory, automatic_access=True
        )
        self.bundle = create_bundle(provider=self.provider, initial_module="imports")
        self.window = self.bundle.engine.rootObjects()[0]
        self.connection = self.bundle.services.comex_access

    def tearDown(self):
        from tests.test_qt import pump

        self.bundle.controller.shutdown()
        self.connection.shutdown()
        self.bundle.inventory.shutdown()
        self.window.close()
        self.bundle.engine.deleteLater()
        pump(lambda: False, 0.04)
        self.temp.cleanup()

    def test_native_connection_dialog_keeps_modules_and_filters_unchanged(self):
        from PySide6.QtCore import QObject, QMetaObject
        from tests.test_qt import pump

        previous = self.bundle.controller._selection
        dialog = self.window.findChild(QObject, "comexConnectionDialog")
        self.assertIsNotNone(dialog)
        QMetaObject.invokeMethod(dialog, "open")
        self.assertTrue(pump(lambda: dialog.property("visible")))
        self.assertTrue(self.window.property("globalModalOpen"))
        self.window.resize(500, 400)
        self.assertFalse(self.window.grabWindow().isNull())
        QMetaObject.invokeMethod(dialog, "close")
        self.assertEqual(self.bundle.controller._selection, previous)
        self.assertEqual(self.bundle.messages, [])

    def test_save_and_import_are_persistent_without_deleting_valid_cache(self):
        path = Path(self.temp.name) / "consultas.sqlite3"
        path.write_bytes(b"not touched by connection settings")
        self.assertTrue(self.connection.save("http://127.0.0.1:8767", TOKEN, True))
        current = load_connection(Path(self.temp.name) / "conexao_comex.json")
        self.assertTrue(current.enabled)
        self.assertEqual(path.read_bytes(), b"not touched by connection settings")
        self.assertEqual(self.provider._availability, None)
        self.assertTrue(self.provider._revalidate_next)
        self.assertTrue(self.connection.save("http://127.0.0.1:8767", TOKEN, False))
        self.assertFalse(load_connection(Path(self.temp.name) / "conexao_comex.json").enabled)
        exported = Path(self.temp.name) / "connect.liarte-conexao"
        export_connection(exported, GatewayConnection(True, "http://127.0.0.1:8768", TOKEN))
        from PySide6.QtCore import QUrl

        self.assertTrue(self.connection.importFile(QUrl.fromLocalFile(str(exported))))
        self.assertEqual(self.connection.state["url"], "http://127.0.0.1:8768")

    def test_configuration_cannot_change_during_a_query(self):
        self.bundle.controller._state["busy"] = True
        self.assertFalse(self.connection.save("http://127.0.0.1:8767", TOKEN, True))
        self.assertFalse((Path(self.temp.name) / "conexao_comex.json").exists())
        self.bundle.controller._state["busy"] = False

    def test_source_check_starts_only_on_imports_once_and_never_on_filter_or_module_roundtrip(self):
        from liarte_desktop.app import install_availability_refresh
        from tests.test_qt import pump

        self.bundle.platform.openModule("home")
        with patch.object(self.bundle.controller, "refreshAvailability") as refresh:
            install_availability_refresh(self.bundle)
            pump(lambda: False, 0.25)
            self.bundle.platform.openModule("inventory")
            pump(lambda: False, 0.25)
            refresh.assert_not_called()
            self.bundle.platform.openModule("imports")
            self.assertTrue(pump(lambda: refresh.call_count == 1))
            self.bundle.platform.openModule("home")
            self.bundle.platform.openModule("imports")
            self.bundle.controller.setFilter("search", "ácido")
            pump(lambda: False, 0.3)
            self.assertEqual(refresh.call_count, 1)

    def test_central_gui_starts_checks_health_and_stops_without_console_commands(self):
        import os

        directory = Path(self.temp.name) / "ui"
        directory.mkdir()
        report = directory / "central.json"
        root = Path(__file__).resolve().parents[1]
        process = subprocess.run(
            [
                sys.executable,
                str(root / "iniciar.py"),
                "--central-comex",
                "--central-smoke",
                str(report),
            ],
            env=dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software"),
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        result = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["api_requests"], 0)
