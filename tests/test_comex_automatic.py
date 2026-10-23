"""Acesso local sem configuração e recusa da fonte, sem rede pública nos testes."""

from __future__ import annotations

import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event, Lock
from urllib.error import HTTPError
from unittest.mock import patch

from liarte_core.comex import ComexProvider
from liarte_core.comex_automatic import AutomaticAccess, process_alive
from liarte_core.comex_central import CentralBroker
from liarte_core.domain import Period
from liarte_core.query import Cancelled
from liarte_engine import comexstat_importacoes as engine
from liarte_engine.comex_access import RequestCoordinator
from liarte_engine.comex_gateway_client import (
    GatewayConnection,
    GatewayError,
    save_connection,
)
from liarte_engine.liarte_dados import atomic_json
from tests.test_comex import Transport
from tests.test_comex_access import FIXTURE, TOKEN, submission


def quick_wait(seconds):
    time.sleep(min(seconds, 0.02))


class AutomaticAccessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.transport = Transport()
        self.managers = []
        self.brokers = []
        self.lock = Lock()
        self.source_error = None

    def tearDown(self):
        for manager in self.managers:
            manager.close()
        self.temp.cleanup()

    def origin_factory(self, **kwargs):
        kwargs.update(min_interval=0.005, max_attempts=1)
        client = engine.ComexStatClient(**kwargs)

        def origin(request, **options):
            if self.source_error is not None:
                status, delay = self.source_error
                raise HTTPError(
                    request.full_url,
                    status,
                    "controlled",
                    {"Retry-After": str(delay)},
                    io.BytesIO(b'{"message":"limite controlado da fonte"}'),
                )
            time.sleep(0.03)
            return self.transport(request, **options)

        client._network_opener = origin
        return client

    def broker_factory(self, path, **kwargs):
        broker = CentralBroker(path, client_factory=self.origin_factory, **kwargs)
        with self.lock:
            self.brokers.append(broker)
        return broker

    def manager(self):
        manager = AutomaticAccess(self.directory, broker_factory=self.broker_factory)
        self.managers.append(manager)
        return manager

    def request(self, manager, value=None, *, check=lambda: None, wait=quick_wait):
        value = value or submission()
        return manager.request_json(
            value["method"],
            value["path"],
            value["body"],
            revision=value["revision"],
            refresh=value["refresh"],
            check=check,
            wait=wait,
            notify=lambda *args: None,
        )

    def test_provider_defaults_to_direct_api_without_server_or_network_at_start(self):
        provider = ComexProvider(self.directory)
        self.assertTrue(provider.direct_api)
        self.assertIsNone(provider._automatic)
        self.assertFalse(self.directory.joinpath("acesso-automatico").exists())
        self.assertIsNone(provider.snapshot)
        provider.close()

    def test_ten_instances_elect_one_broker_and_use_one_exact_source_response(self):
        managers = [self.manager() for _ in range(10)]
        with ThreadPoolExecutor(max_workers=10) as pool:
            replies = list(pool.map(self.request, managers))
        self.assertEqual(len(self.brokers), 1)
        self.assertEqual(len(self.transport.calls), 1)
        self.assertEqual(sum(m.server is not None for m in managers), 1)
        self.assertTrue(all(reply[0] == replies[0][0] for reply in replies))
        self.assertEqual(sum(reply[1] for reply in replies), 9)
        self.assertFalse((self.directory / "conexao_comex.json").exists())
        if os.name != "nt":
            self.assertEqual(managers[0].registry.stat().st_mode & 0o077, 0)

    def test_other_process_reuses_automatic_registration_without_creating_another_broker(self):
        manager = self.manager()
        connection = manager.resolve(check=lambda: None, wait=quick_wait)
        script = """
from pathlib import Path
import sys,time
from liarte_core.comex_automatic import AutomaticAccess
m=AutomaticAccess(Path(sys.argv[1]))
c=m.resolve(check=lambda:None, wait=time.sleep)
assert m.server is None
print(c.url)
m.close()
"""
        result = subprocess.run(
            [sys.executable, "-c", script, str(self.directory)],
            env=dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src")),
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), connection.url)
        self.assertTrue(manager.registry.is_file())
        self.assertEqual(self.transport.calls, [])

    def test_closing_host_hands_over_automatically_and_keeps_valid_shared_cache(self):
        host, follower = self.manager(), self.manager()
        first = self.request(host)
        self.assertIsNone(follower.server)
        host.close()
        second = self.request(follower)
        self.assertIsNotNone(follower.server)
        self.assertEqual(first[0], second[0])
        self.assertTrue(second[1])
        self.assertEqual(len(self.transport.calls), 1)
        host.close()  # Um dono antigo não remove o registro do novo.
        self.assertTrue(follower.registry.is_file())

    def test_stopped_owned_server_is_recreated_without_manual_configuration(self):
        manager = self.manager()
        self.request(manager)
        previous = manager.server
        previous.close()
        self.request(manager)
        self.assertIsNot(manager.server, previous)
        self.assertEqual(len(self.transport.calls), 1)

    def test_stale_registration_is_recovered_but_a_live_owner_is_not_duplicated(self):
        manager = self.manager()
        with socket.socket() as reserved:
            reserved.bind(("127.0.0.1", 0))
            port = reserved.getsockname()[1]
            connection = GatewayConnection(True, f"http://127.0.0.1:{port}", TOKEN)
            save_connection(manager.registry, connection)
            value = json.loads(manager.registry.read_text(encoding="utf-8"))
            value["pid"] = os.getpid()
            atomic_json(manager.registry, value)
            with self.assertRaises(GatewayError):
                manager.resolve(check=lambda: None, wait=quick_wait)
            self.assertEqual(self.brokers, [])
            value["pid"] = 999999999
            atomic_json(manager.registry, value)
            manager.resolve(check=lambda: None, wait=quick_wait)
        self.assertEqual(len(self.brokers), 1)
        self.assertEqual(self.transport.calls, [])

    def test_automatic_registry_can_never_redirect_to_a_network_host(self):
        manager = self.manager()
        save_connection(
            manager.registry, GatewayConnection(True, "http://untrusted.example:8767", TOKEN)
        )
        with patch("liarte_core.comex_automatic.central_http") as network:
            with self.assertRaises(GatewayError):
                manager.resolve(check=lambda: None, wait=quick_wait)
            network.assert_not_called()
        self.assertEqual(self.brokers, [])

    def test_cancel_before_preparation_creates_no_service_or_origin_request(self):
        manager = self.manager()

        def cancel():
            raise Cancelled()

        with self.assertRaises(Cancelled):
            self.request(manager, check=cancel)
        self.assertEqual(self.brokers, [])
        self.assertFalse(manager.registry.exists())

    def test_remote_configuration_has_priority_and_no_local_fallback(self):
        configured = GatewayConnection(True, "http://127.0.0.1:8767", TOKEN)
        save_connection(self.directory / "conexao_comex.json", configured)
        provider = ComexProvider(self.directory, automatic_access=True)
        try:
            client = provider._client(Event())
            self.assertEqual(client.gateway, configured)
            self.assertIsNone(provider._automatic.server)
            client.close()
        finally:
            provider.close()

    def managed_configuration(self, *, host="127.0.0.1", changes=None):
        self.directory = self.directory / "dados"
        self.directory.mkdir()
        with socket.socket() as reserved:
            reserved.bind(("127.0.0.1", 0))
            port = reserved.getsockname()[1]
        connection = GatewayConnection(True, f"http://127.0.0.1:{port}", TOKEN)
        path = self.directory.parent / "central-comex" / "central.json"
        save_connection(path, connection)
        value = json.loads(path.read_text(encoding="utf-8"))
        value.update(host=host, port=port, interval=0.005)
        value.update(changes or {})
        atomic_json(path, value)
        return connection, path

    def test_owned_central_is_resumed_without_a_second_window_and_keeps_address_key_and_cache(self):
        connection, config = self.managed_configuration()
        original = config.read_bytes()
        first = self.manager()
        first.start_managed()
        first._warmup.join(timeout=5)
        self.assertIsNotNone(first.server)
        self.assertEqual(first.resolve(check=lambda: None, wait=quick_wait), connection)
        self.assertEqual(self.brokers[0].directory, config.parent / "dados")
        self.assertEqual(self.transport.calls, [])
        response = self.request(first)
        first.close()
        second = self.manager()
        repeated = self.request(second)
        self.assertEqual(response[0], repeated[0])
        self.assertTrue(repeated[1])
        self.assertEqual(len(self.transport.calls), 1)
        self.assertEqual(config.read_bytes(), original)
        self.assertEqual(second.connection.token, connection.token)

    def test_ten_remote_profiles_use_owned_background_service_without_starting_other_brokers(self):
        connection, _ = self.managed_configuration(host="0.0.0.0")
        host = self.manager()
        providers = []
        with patch("liarte_core.comex_automatic.AutomaticAccess", return_value=host):
            owner = ComexProvider(self.directory, automatic_access=True)
        providers.append(owner)
        try:
            host._warmup.join(timeout=5)
            self.assertIsNotNone(host.server)
            for index in range(10):
                directory = self.directory.parent / f"client-{index}" / "dados"
                save_connection(directory / "conexao_comex.json", connection)
                providers.append(ComexProvider(directory, automatic_access=True))

            def run(provider):
                client = provider._client(Event())
                try:
                    self.assertEqual(client.gateway, connection)
                    value = submission()
                    return client.request_json(value["method"], value["path"], value["body"])
                finally:
                    client.close()

            with ThreadPoolExecutor(max_workers=10) as pool:
                results = list(pool.map(run, providers[1:]))
            self.assertTrue(all(r == results[0] for r in results))
            self.assertEqual(len(self.transport.calls), 1)
            self.assertEqual(len(self.brokers), 1)
            self.assertTrue(all(p._automatic.server is None for p in providers[1:]))
        finally:
            for provider in providers:
                provider.close()

    def test_matching_local_connection_is_managed_but_another_company_server_is_not_replaced(self):
        connection, _ = self.managed_configuration()
        manager = self.manager()
        self.assertIs(manager.gateway(connection), manager)
        other = GatewayConnection(True, "http://192.168.0.25:8767", TOKEN)
        self.assertIs(manager.gateway(other), other)
        wrong_key = GatewayConnection(True, connection.url, "A" * 32)
        self.assertIs(manager.gateway(wrong_key), wrong_key)
        self.assertEqual(self.transport.calls, [])
        self.assertEqual(self.brokers, [])

    def test_owned_configuration_can_only_bind_previously_authorized_private_addresses(self):
        from liarte_core.comex_managed import read_managed

        _, config = self.managed_configuration()
        original = json.loads(config.read_text(encoding="utf-8"))
        for changes in (
            {"host": "8.8.8.8"},
            {"host": "224.0.0.1"},
            {"host": "::1"},
            {"port": True},
            {"interval": "65"},
            {"interval": float("nan")},
            {"url": "https://example.invalid:8767"},
            {"url": "http://127.0.0.1:8767/not-a-local-service"},
        ):
            with self.subTest(changes=changes):
                # Simula arquivo externo malformado, inclusive NaN não padrão.
                config.write_text(json.dumps({**original, **changes}), encoding="utf-8")
                with self.assertRaises((GatewayError, ValueError)):
                    read_managed(self.directory)
        self.assertEqual(self.brokers, [])

    def test_disabled_owned_configuration_does_not_open_any_lan_listener(self):
        _, _ = self.managed_configuration(changes={"enabled": False})
        manager = self.manager()
        manager.start_managed()
        self.assertIsNone(manager._warmup)
        manager.resolve(check=lambda: None, wait=quick_wait)
        self.assertIsNotNone(manager.server)
        self.assertEqual(manager.server.server.effective_host, "127.0.0.1")
        self.assertNotEqual(manager.server.port, 0)

    def test_existing_manual_service_is_reused_but_never_closed_by_the_automatic_client(self):
        from liarte_core.comex_central import CentralServer

        connection, config = self.managed_configuration()
        broker = self.broker_factory(
            config.parent / "dados", access_path=self.directory / "acesso_comex.sqlite3"
        )
        server = CentralServer(
            broker, TOKEN, host="127.0.0.1", port=int(connection.url.rsplit(":", 1)[1])
        )
        server.start()
        try:
            manager = self.manager()
            self.assertEqual(manager.resolve(check=lambda: None, wait=quick_wait), connection)
            self.assertIsNone(manager.server)
            self.request(manager)
            manager.close()
            self.assertTrue(server.thread.is_alive())
            self.assertEqual(len(self.brokers), 1)
        finally:
            server.close()

    def test_full_general_and_municipal_pipeline_works_without_any_connection_file(self):
        code = FIXTURE["general"][0]["coNcm"]
        providers = [
            ComexProvider(self.directory, codes=(code,), automatic_access=True) for _ in range(2)
        ]
        try:
            for provider in providers:
                provider._automatic.broker_factory = self.broker_factory
            first = providers[0].load(Period("2026-09", "2026-09"), Event(), lambda *args: None)
            second = providers[1].load(Period("2026-09", "2026-09"), Event(), lambda *args: None)
            self.assertEqual(first.general, second.general)
            self.assertEqual(first.municipal, second.municipal)
            self.assertTrue(first.totals_verified and second.totals_verified)
            self.assertEqual(len(self.transport.calls), 6)
            self.assertEqual(len(self.brokers), 1)
            self.assertEqual(second.api_requests, 0)
            self.assertFalse((self.directory / "conexao_comex.json").exists())
        finally:
            for provider in providers:
                provider.close()

    def test_real_429_is_preserved_with_pause_and_exact_bounded_diagnostic(self):
        self.source_error = (429, 180)
        manager = self.manager()
        with self.assertRaises(engine.ComexRateLimitError) as failure:
            self.request(manager)
        self.assertGreaterEqual(failure.exception.retry_after, 179)
        state = RequestCoordinator.peek(self.directory / "acesso_comex.sqlite3")
        self.assertGreaterEqual(state["pause_seconds"], 179)
        evidence = json.loads(
            (self.brokers[0].directory / "ultima_falha_comex.json").read_text(encoding="utf-8")
        )
        self.assertEqual(evidence["http_status"], 429)
        self.assertEqual(evidence["endpoint"], "/general?language=pt")
        self.assertIn("limite controlado da fonte", evidence["response_excerpt"])
        manager.close()
        self.assertGreaterEqual(
            RequestCoordinator.peek(self.directory / "acesso_comex.sqlite3")["pause_seconds"], 178
        )

    def test_other_errors_are_not_misclassified_as_a_rate_limit(self):
        self.source_error = (403, 0)
        with self.assertRaises(engine.ComexStatError) as failure:
            self.request(self.manager())
        self.assertNotIsInstance(failure.exception, engine.ComexRateLimitError)
        self.assertIn("HTTP 403", str(failure.exception))
        evidence = json.loads(
            (self.brokers[0].directory / "ultima_falha_comex.json").read_text(encoding="utf-8")
        )
        self.assertEqual(evidence["http_status"], 403)
        self.assertEqual(
            RequestCoordinator.peek(self.directory / "acesso_comex.sqlite3")["pause_seconds"], 0
        )

    def test_pause_read_never_creates_missing_database_and_has_no_persistent_connection(self):
        path = self.directory / "missing" / "gate.sqlite3"
        self.assertEqual(RequestCoordinator.peek(path), {"pause_seconds": 0})
        self.assertFalse(path.exists())
        gate = RequestCoordinator(path)
        gate.defer(30)
        for _ in range(30):
            self.assertGreaterEqual(RequestCoordinator.peek(path)["pause_seconds"], 29)

    def test_pid_checks_recognize_current_and_missing_owner(self):
        self.assertTrue(process_alive(os.getpid()))
        self.assertFalse(process_alive(999999999))
        for pid in (None, -1, 0, True, "invalid"):
            self.assertFalse(process_alive(pid))

    def test_generic_ten_second_body_does_not_cause_rapid_consecutive_retries(self):
        body = '{"error":{"code":429,"message":"Tente novamente em 10 segundos."}}'
        self.assertEqual(engine.ComexStatClient._retry_seconds({}, body, 1), 60)
        self.assertEqual(engine.ComexStatClient._retry_seconds({}, body, 2), 120)
        self.assertEqual(engine.ComexStatClient._retry_seconds({}, body, 3), 240)
        self.assertEqual(
            engine.ComexStatClient._retry_seconds({"Retry-After": "1800"}, body, 1), 1800.5
        )
        self.assertEqual(
            engine.ComexStatClient._retry_seconds({}, "Aguarde 3600 segundos.", 1), 3600.5
        )

    def test_json_limit_keeps_the_actual_http_status_separate_from_api_error_code(self):
        from tests.test_comex import Response

        evidence = []
        client = engine.ComexStatClient(
            max_attempts=1, min_interval=0, failure_callback=evidence.append
        )
        client._network_opener = lambda *args, **kwargs: Response(
            {
                "success": False,
                "error": {"code": 429, "message": "Aguarde 10 segundos."},
            }
        )
        with self.assertRaises(engine.ComexRateLimitError) as error:
            client.request_json("POST", "/general?language=pt", {})
        self.assertEqual(error.exception.observed_http_status, 200)
        self.assertEqual(evidence[0]["observed_http_status"], 200)
        self.assertEqual(evidence[0]["http_status"], 429)
        self.assertIn("código 429 da API", str(error.exception))


class AutomaticAccessUiTests(unittest.TestCase):
    def test_pause_countdown_blocks_repeated_source_queries_and_expires_locally(self):
        from PySide6.QtCore import QObject
        from liarte_desktop.app import create_bundle
        from tests.test_comex import factory
        from tests.test_qt import pump

        with tempfile.TemporaryDirectory() as directory:
            provider = ComexProvider(Path(directory), client_factory=factory)
            bundle = create_bundle(provider=provider, initial_module="imports")
            window = bundle.engine.rootObjects()[0]
            try:
                gate = RequestCoordinator(provider.directory / "acesso_comex.sqlite3")
                gate.defer(2)
                bundle.controller._sync_access_status()
                pump(lambda: False, 0.05)
                button = window.findChild(QObject, "queryButton")
                self.assertFalse(button.property("enabled"))
                self.assertGreater(bundle.controller.state["sourcePauseSeconds"], 0)
                with patch.object(provider, "query") as source:
                    bundle.controller.queryPeriod("2026-09", "2026-09")
                    source.assert_not_called()
                self.assertTrue(pump(lambda: bundle.controller.state["sourcePauseSeconds"] == 0, 4))
                self.assertTrue(button.property("enabled"))
                self.assertEqual(bundle.messages, [])
            finally:
                bundle.controller.shutdown()
                bundle.services.comex_access.shutdown()
                bundle.inventory.shutdown()
                window.close()
                bundle.engine.deleteLater()
                pump(lambda: False, 0.05)
