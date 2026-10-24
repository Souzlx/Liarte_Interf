"""Regressões N1/N2: processos nativos e respostas locais, sem API pública."""

from __future__ import annotations

import io
import json
import multiprocessing as mp
from pathlib import Path
import tempfile
from threading import Event
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

from liarte_core.comex import ComexError, ComexProvider
from liarte_core.comex_api import ApiClient, ApiPause, PATHS
from liarte_core.domain import Period
from liarte_core.query import Cancelled, checkpoint
from liarte_engine import comexstat_importacoes as contract


class Response(io.BytesIO):
    def __init__(self, document, status=200):
        raw = json.dumps(document).encode("utf-8")
        super().__init__(raw)
        self.status = status
        self.headers = {"Content-Length": str(len(raw)), "Content-Type": "application/json"}


def _pause_race_writer(path, seconds, rendezvous, short_read, long_written):
    """Force an old read by the short writer before the long writer publishes.

    The barrier is outside the short transaction, so a correct lock can
    serialize publication without deadlocking the test. The short writer must
    read again after acquiring that lock, preserving both deadline and status.
    """
    import liarte_core.comex_api as api

    original_write = api.atomic_json
    pause = ApiPause(path, clock=lambda: 1000)
    original_remaining = pause.remaining
    first_read = True

    def remaining():
        nonlocal first_read
        value = original_remaining()
        if seconds == 10 and first_read:
            first_read = False
            short_read.set()
        return value

    def publish(target, value):
        if seconds == 1800:
            rendezvous.wait(timeout=10)
            if not short_read.wait(timeout=10):
                raise RuntimeError("short writer did not read the old pause")
        elif not long_written.wait(timeout=10):
            raise RuntimeError("long writer did not publish")
        original_write(target, value)
        if seconds == 1800:
            long_written.set()

    if seconds == 10:
        rendezvous.wait(timeout=10)
    with patch.object(api, "atomic_json", publish), patch.object(pause, "remaining", remaining):
        pause.defer(seconds, 503 if seconds == 1800 else 429)


def _post_worker(path, started, entered, release, active, peak, counter_lock, result):
    client = ApiClient(coordinator_path=path)

    def receive(*args, **kwargs):
        with counter_lock:
            active.value += 1
            peak.value = max(peak.value, active.value)
        try:
            entered.set()
            if not release.wait(timeout=10):
                raise RuntimeError("test did not release the POST")
            return Response({"data": {"list": []}})
        finally:
            with counter_lock:
                active.value -= 1

    client._network_opener = receive
    started.set()
    result.put(client.request_json("POST", "/general?language=pt", {}))


def _hold_process_lock(path, acquired, release, *, state=False):
    import liarte_core.comex_api as api

    pause = ApiPause(path)
    if state:
        lock = api._process_lock(pause.state_lock_path)
    else:
        lock = ApiClient(pause_state=pause)._serial()
    with lock:
        acquired.set()
        if not release.wait(timeout=15):
            raise RuntimeError("test did not release the lock")


def _cancel_blocked_process(path, cancel, waiting, result, *, state=False):
    def check():
        checkpoint(cancel)

    client = ApiClient(
        coordinator_path=path,
        cancel_check=check,
        cancel_wait=cancel.wait,
        progress_callback=lambda fraction, message: waiting.set(),
    )
    client._network_opener = lambda *a, **k: result.put("unexpected network")
    try:
        if state:
            # Signal only once the real OS lock has rejected this process.
            import liarte_core.comex_api as api

            original = api._try_file_lock

            def acquire(handle):
                acquired = original(handle)
                if not acquired:
                    waiting.set()
                return acquired

            with patch.object(api, "_try_file_lock", acquire):
                client.pause.defer(1800, 429, cancel_check=check, cancel_wait=cancel.wait)
        else:
            client.request_json("POST", "/general?language=pt", {})
    except Cancelled:
        result.put("cancelled")


class ProcessPauseTests(unittest.TestCase):
    """Uses spawn on every platform, including the Windows msvcrt CI matrix."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "acesso_api.json"
        self.context = mp.get_context("spawn")

    def start(self, function, *args, **kwargs):
        process = self.context.Process(target=function, args=args, kwargs=kwargs)
        process.start()

        def cleanup():
            if process.is_alive():
                process.terminate()
            process.join(timeout=5)
            process.close()

        self.addCleanup(cleanup)
        return process

    def joined(self, process, timeout=10):
        process.join(timeout=timeout)
        self.assertFalse(process.is_alive(), "child process did not finish")
        self.assertEqual(process.exitcode, 0)

    def test_short_last_writer_cannot_shorten_1800_second_pause_or_replace_its_status(self):
        rendezvous = self.context.Barrier(2)
        short_read, long_written = self.context.Event(), self.context.Event()
        writers = [
            self.start(_pause_race_writer, self.path, seconds, rendezvous, short_read, long_written)
            for seconds in (1800, 10)
        ]
        for process in writers:
            self.joined(process)
        following = ApiPause(self.path, clock=lambda: 1000)
        self.assertEqual(following.remaining(), 1800)
        self.assertEqual(following.status, 503)
        persisted = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(persisted, {"until": 2800, "status": 503})

    def test_independent_processes_serialize_posts_without_preventive_interval(self):
        release = self.context.Event()
        active, peak = self.context.Value("i", 0), self.context.Value("i", 0)
        mutex, result = self.context.Lock(), self.context.Queue()
        first_started, second_started = self.context.Event(), self.context.Event()
        first_entered, second_entered = self.context.Event(), self.context.Event()
        first = self.start(
            _post_worker,
            self.path,
            first_started,
            first_entered,
            release,
            active,
            peak,
            mutex,
            result,
        )
        self.assertTrue(first_entered.wait(timeout=10))
        second = self.start(
            _post_worker,
            self.path,
            second_started,
            second_entered,
            release,
            active,
            peak,
            mutex,
            result,
        )
        self.assertTrue(second_started.wait(timeout=10))
        self.assertFalse(second_entered.wait(timeout=0.2))
        release.set()
        self.joined(first)
        self.joined(second)
        self.assertEqual(peak.value, 1)
        self.assertEqual([result.get(timeout=2) for _ in range(2)], [{"data": {"list": []}}] * 2)
        self.assertFalse(self.path.exists(), "successful POSTs must not persist a pause")

    def test_process_exit_releases_native_lock_without_a_stale_lease(self):
        acquired, release = self.context.Event(), self.context.Event()
        holder = self.start(_hold_process_lock, self.path, acquired, release)
        self.assertTrue(acquired.wait(timeout=10))
        holder.terminate()
        holder.join(timeout=5)
        self.assertFalse(holder.is_alive())
        client = ApiClient(coordinator_path=self.path)
        client._network_opener = lambda *a, **k: Response({"data": {}})
        self.assertEqual(client.request_json("POST", "/general?language=pt", {}), {"data": {}})

    def test_cancellation_interrupts_both_native_lock_waits_without_releasing_holder(self):
        for state in (False, True):
            with self.subTest(state_lock=state):
                acquired, release = self.context.Event(), self.context.Event()
                cancel, waiting = self.context.Event(), self.context.Event()
                result = self.context.Queue()
                holder = self.start(_hold_process_lock, self.path, acquired, release, state=state)
                self.assertTrue(acquired.wait(timeout=10))
                blocked = self.start(
                    _cancel_blocked_process, self.path, cancel, waiting, result, state=state
                )
                self.assertTrue(waiting.wait(timeout=10))
                cancel.set()
                self.joined(blocked, timeout=2)
                self.assertEqual(result.get(timeout=2), "cancelled")
                self.assertTrue(holder.is_alive())
                release.set()
                self.joined(holder)

    def test_shorter_refusal_keeps_larger_deadline_and_status_in_each_instance(self):
        first = ApiPause(self.path, clock=lambda: 1000)
        second = ApiPause(self.path, clock=lambda: 1000)
        first.defer(1800, 503)
        second.defer(10, 429)
        self.assertEqual(second.remaining(), 1800)
        self.assertEqual(second.status, 503)
        self.assertEqual(first.remaining(), 1800)
        self.assertEqual(first.status, 503)


class EndpointStatusTests(unittest.TestCase):
    def test_only_http_200_is_supported_by_each_official_endpoint(self):
        for method, path in sorted(PATHS):
            for status in (201, 204, 205, 206):
                with self.subTest(endpoint=path, status=status):
                    diagnostic = []
                    client = ApiClient(failure_callback=diagnostic.append)
                    client._network_opener = lambda *a, **k: Response({"data": {}}, status)
                    with self.assertRaisesRegex(contract.ComexStatError, f"HTTP {status}"):
                        client.request_json(method, path, {} if method == "POST" else None)
                    self.assertEqual(client.network_requests, 1)
                    self.assertEqual(diagnostic[0]["endpoint"], path)
                    self.assertEqual(diagnostic[0]["observed_http_status"], status)
                    self.assertEqual(diagnostic[0]["http_status"], status)
                    self.assertEqual(client.pause.remaining(), 0)

    def test_partial_general_or_municipal_response_preserves_complete_snapshot_and_diagnostic(self):
        fixture = json.loads(
            (Path(__file__).parent / "fixtures/comex_2026-09.json").read_text(encoding="utf-8")
        )
        period = Period("2026-09", "2026-09")
        for partial_endpoint in ("/general", "/cities"):
            with (
                self.subTest(endpoint=partial_endpoint),
                tempfile.TemporaryDirectory() as directory,
            ):
                partial = False
                calls = []

                def receive(request, **kwargs):
                    path = urlsplit(request.full_url).path
                    calls.append(path)
                    rows = fixture["municipal" if path == "/cities" else "general"]
                    unsupported = partial and path == partial_endpoint
                    return Response(
                        {"success": True, "data": {"list": rows[:1] if unsupported else rows}},
                        206 if unsupported else 200,
                    )

                with patch.object(ApiClient, "_open", side_effect=receive):
                    provider = ComexProvider(Path(directory), codes=("29161220",))
                    self.addCleanup(provider.close)
                    complete = provider.load(period, Event(), lambda *a: None)
                    self.assertEqual((len(complete.general), len(complete.municipal)), (18, 216))
                    self.assertTrue(complete.response_validated)
                    partial = True
                    provider.revalidate_next()
                    with self.assertRaisesRegex(ComexError, "HTTP 206"):
                        provider.load(period, Event(), lambda *a: None)
                    self.assertIs(provider.snapshot, complete)
                    expected = (
                        ["/general"] if partial_endpoint == "/general" else ["/general", "/cities"]
                    )
                    self.assertEqual(calls[2:], expected)
                    event = json.loads(
                        (Path(directory) / "ultima_falha_comex.json").read_text(encoding="utf-8")
                    )
                    self.assertEqual(event["observed_http_status"], 206)
                    self.assertEqual(event["http_status"], 206)
                    self.assertTrue(event["endpoint"].startswith(partial_endpoint + "?"))


if __name__ == "__main__":
    unittest.main()
