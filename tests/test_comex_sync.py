"""Sincronização sintética, retomada em disco e publicação integral do histórico."""

from __future__ import annotations

from contextlib import closing, contextmanager
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import sqlite3
import tempfile
from threading import Event
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlsplit

from liarte_core.comex import ComexError, ComexProvider, integral
from liarte_core.comex_api import ApiClient, ApiPause
from liarte_core.comex_history import HistoryBusy, HistoryError, HistoryStagingError, HistoryStore
from liarte_core.comex_sync import HistorySynchronizer, HistorySyncError
from liarte_core.domain import Period
from liarte_core.query import Cancelled, checkpoint
from liarte_engine import comexstat_importacoes as engine


class EpochClock:
    def __init__(self):
        self.value = datetime(2026, 11, 10, tzinfo=timezone.utc).timestamp()

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


class HistoricalSource:
    """Two independent metadata routes and complete annual catalog responses."""

    def __init__(self, clock):
        self.clock = clock
        self.publication = {
            "latest": "2026-02", "updated": "2026-03-05",
            "municipal_latest": "2026-01", "municipal_updated": "2026-02-04",
        }
        self.attempts = []
        self.accepted = []
        self.clients = []
        self.hook = None
        self.spacing, self.next_allowed = 0, 0
        self.value = 100
        self.empty = set()
        self.state = "SP"

    def touch(self, kind):
        self.attempts.append(kind)
        if self.clock() < self.next_allowed:
            raise engine.ComexRateLimitError(self.next_allowed - self.clock(), str(kind))
        self.next_allowed = self.clock() + self.spacing
        self.accepted.append(kind)
        if self.hook is not None:
            self.hook(kind)

    def factory(self, cancel, progress):
        source = self

        class Client:
            closed = False

            def latest_published_period(self):
                source.touch(("metadata", "general"))
                return source.publication["latest"], source.publication["updated"]

            def request_json(self, method, path):
                if (method, path) != ("GET", "/cities/dates/updated"):
                    raise AssertionError((method, path))
                source.touch(("metadata", "municipal"))
                latest = source.publication["municipal_latest"]
                return {"data": {"year": latest[:4], "monthNumber": latest[5:], "updated": source.publication["municipal_updated"]}}

            def query_imports(self, codes, start, end):
                source.touch(("data", False, start, end))
                return source.rows(False, codes, start)

            def query_municipal_imports(self, codes, start, end):
                source.touch(("data", True, start, end))
                return source.rows(True, codes, start)

            def close(self):
                self.closed = True

        client = Client()
        self.clients.append(client)
        return client

    def rows(self, municipal, codes, start):
        if (municipal, start[:4]) in self.empty:
            return []
        result = []
        for code in sorted({c[:4] if municipal else c for c in codes}):
            row = {
                "year": start[:4], "monthNumber": start[5:],
                "state": self.state, "country": "China",
                "metricFOB": str(self.value), "metricKG": "10",
            }
            if municipal:
                row.update(headingCode=code, heading="Produto sintético", noMunMinsgUf="São Paulo - SP")
            else:
                row.update(
                    coNcm=code, ncm="Produto sintético", urf="0817800 - PORTO DE SANTOS",
                    metricFreight="2", metricInsurance="1", metricCIF=str(self.value + 3),
                )
            result.append(row)
        return result


class ComexSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "history.sqlite3"
        self.clock = EpochClock()
        self.store = HistoryStore(self.path, ("29161220",), clock=self.clock)
        self.source = HistoricalSource(self.clock)
        self.period = Period("2025-11", "2026-01")

    def tearDown(self):
        self.assertTrue(all(client.closed for client in self.source.clients))
        self.temp.cleanup()

    @staticmethod
    def validate(general, municipal, cancel):
        return ComexProvider._convert(None, general, municipal, cancel)

    def syncer(self, **kwargs):
        return HistorySynchronizer(
            self.store, self.source.factory, self.validate,
            first_month="2025-11", clock=self.clock, **kwargs,
        )

    def synchronize(self, *, cancel=None, progress=lambda *_: None, **kwargs):
        return self.syncer().synchronize(cancel or Event(), progress, **kwargs)

    def read(self):
        return self.store.read(self.period, Event())

    def test_complete_history_is_chronological_and_only_published_after_final_metadata(self):
        observations, progress = [], []
        self.source.hook = lambda kind: observations.append((kind, self.store.contains(self.period)))
        result = self.synchronize(progress=lambda value, message: progress.append((value, message)))
        self.assertEqual(self.source.accepted, [
            ("metadata", "general"), ("metadata", "municipal"),
            ("data", False, "2025-11", "2025-12"), ("data", True, "2025-11", "2025-12"),
            ("data", False, "2026-01", "2026-01"), ("data", True, "2026-01", "2026-01"),
            ("metadata", "general"), ("metadata", "municipal"),
        ])
        self.assertFalse(any(available for _, available in observations))
        self.assertEqual(result["status"], "updated")
        self.assertTrue(result["changed"])
        self.assertTrue(self.store.contains(self.period))
        self.assertEqual(self.store.status()["coverage_end"], "2026-01")
        self.assertEqual(self.store.status()["complete_months"], 3)
        self.assertEqual(len(self.read().general), 2)
        empty = self.store.read(Period("2025-12", "2025-12"), Event())
        self.assertEqual((empty.general, empty.municipal), ((), ()))
        self.assertTrue(all(type(value) is int and 0 <= value <= 100 for value, _ in progress))
        self.assertEqual(progress[-1][0], 100)

    def test_coalesced_check_uses_no_client_but_forced_check_does_not_reuse_completed_metadata(self):
        self.synchronize()
        count = len(self.source.attempts)
        clients = len(self.source.clients)
        result = self.synchronize()
        self.assertEqual(result["status"], "throttled")
        self.assertEqual(len(self.source.clients), clients)
        self.assertEqual(len(self.source.attempts), count)
        for _ in range(2):
            result = self.synchronize(force=True)
            self.assertEqual(result["status"], "unchanged")
            self.assertFalse(result["changed"])
        self.assertEqual(self.source.attempts[count:], [("metadata", "general"), ("metadata", "municipal")] * 2)

    def test_completed_state_is_committed_with_the_manifest_without_an_extra_state_write(self):
        original = self.store.record_state

        def record_state(state, error=""):
            if state == "ready":
                raise OSError("simulated storage failure after the accepted commit")
            original(state, error)

        with patch.object(self.store, "record_state", side_effect=record_state):
            result = self.synchronize()
        self.assertEqual(result["status"], "updated")
        self.assertTrue(self.store.contains(self.period))
        self.assertEqual(self.store.status()["sync_state"], "ready")

    def test_short_accepted_history_does_not_throttle_or_skip_backfill_of_a_new_start(self):
        for force in (False, True):
            with self.subTest(force=force):
                self.path = Path(self.temp.name) / f"expanded-{force}.sqlite3"
                self.store = HistoryStore(self.path, ("29161220",), clock=self.clock)
                self.synchronize()
                count = len(self.source.attempts)
                extended = HistorySynchronizer(
                    self.store, self.source.factory, self.validate,
                    first_month="2024-10", clock=self.clock,
                )
                result = extended.synchronize(Event(), lambda *_: None, force=force)
                self.assertEqual(result["status"], "updated")
                self.assertEqual(self.store.status()["coverage_start"], "2024-10")
                self.assertIn(("data", False, "2024-10", "2024-12"), self.source.attempts[count:])

    def test_short_accepted_end_is_rebuilt_until_the_same_publications_common_target(self):
        publication = self.source.publication
        run = self.store.begin_run(publication, "2025-11", "2025-12")
        for municipal in (False, True):
            self.store.write_stage(
                run, municipal, "2025-11", "2025-12",
                self.source.rows(municipal, self.store.codes, "2025-11"),
                received_at=self.syncer()._now(), acquisition_started_at=self.syncer()._now(),
            )
        self.store.record_check(publication)
        self.store.publish_run(run)
        result = self.synchronize()
        self.assertEqual(result["status"], "updated")
        self.assertEqual(self.store.status()["coverage_end"], "2026-01")
        self.assertTrue(self.store.contains(self.period))

    def test_periodic_audit_detects_same_metadata_correction_and_deletion_with_exact_large_values(self):
        self.synchronize()
        previous = self.read()
        self.source.value = 9007199254740993
        self.source.empty.add((False, "2025"))
        self.clock.advance(301)
        self.assertEqual(self.synchronize()["status"], "unchanged")
        self.assertEqual(self.read().general, previous.general)
        self.clock.advance(86400)
        result = self.synchronize()
        self.assertTrue(result["changed"])
        current = self.read()
        self.assertNotEqual(current.local_revision, previous.local_revision)
        self.assertEqual(len(current.general), 1)
        self.assertEqual(integral(current.general[0]["metricFOB"], cents=True), 900719925474099300)
        self.assertEqual(self.store.status()["publication"], self.source.publication)

    def test_explicit_audit_reextracts_even_with_a_recent_unchanged_publication(self):
        self.synchronize()
        count = len(self.source.attempts)
        self.source.value += 1
        result = self.synchronize(audit=True)
        self.assertTrue(result["changed"])
        self.assertEqual(len([kind for kind in self.source.attempts[count:] if kind[0] == "data"]), 4)

    def test_changed_publication_reextracts_closed_years_and_extends_only_common_coverage(self):
        self.synchronize()
        self.source.publication.update(updated="2026-03-06", municipal_latest="2026-02", municipal_updated="2026-03-05")
        self.source.value += 2
        count = len(self.source.attempts)
        result = self.synchronize(force=True)
        self.assertTrue(result["changed"])
        self.assertEqual(self.store.status()["coverage_end"], "2026-02")
        self.assertEqual([kind for kind in self.source.attempts[count:] if kind[0] == "data"], [
            ("data", False, "2025-11", "2025-12"), ("data", True, "2025-11", "2025-12"),
            ("data", False, "2026-01", "2026-02"), ("data", True, "2026-01", "2026-02"),
        ])

    def test_global_source_limit_eventually_finishes_after_restarts_without_replaying_metadata_or_data(self):
        for spacing in (180, 900):
            with self.subTest(spacing=spacing):
                self.path = Path(self.temp.name) / f"global-{spacing}.sqlite3"
                self.source = HistoricalSource(self.clock)
                self.source.spacing = spacing
                attempts = 0
                while attempts < 20:
                    # Fresh store/client/synchronizer instances prove that all
                    # checkpoints are durable, not an in-memory retry trick.
                    self.store = HistoryStore(self.path, ("29161220",), clock=self.clock)
                    attempts += 1
                    try:
                        result = self.synchronize()
                        break
                    except engine.ComexRateLimitError:
                        self.assertFalse(self.store.contains(self.period))
                        self.clock.advance(spacing + 1)
                else:
                    self.fail("A retomada repetiu etapas aceitas e não concluiu.")
                self.assertTrue(result["changed"])
                self.assertEqual(len(self.source.accepted), 8)
                self.assertEqual(len(self.source.attempts), 15)
                self.assertEqual(self.source.accepted.count(("metadata", "general")), 2)
                self.assertEqual(self.source.accepted.count(("metadata", "municipal")), 2)
                self.assertEqual(len(set(kind for kind in self.source.accepted if kind[0] == "data")), 4)
                self.assertTrue(all(client.closed for client in self.source.clients))

    def test_cancelled_replacement_keeps_previous_base_and_resumes_persisted_stages(self):
        self.synchronize()
        previous = self.read()
        cancel = Event()

        def cancellation(kind):
            if kind == ("data", True, "2025-11", "2025-12"):
                cancel.set()

        self.source.value += 8
        self.source.hook = cancellation
        with self.assertRaises(Cancelled):
            self.synchronize(cancel=cancel, audit=True)
        self.assertEqual(self.read(), previous)
        run = self.store.pending_run_info()["run_id"]
        self.assertTrue(self.store.has_stage(run, False, "2025-11", "2025-12"))
        self.assertFalse(self.store.has_stage(run, True, "2025-11", "2025-12"))
        count = len(self.source.attempts)
        self.source.hook = None
        self.store = HistoryStore(self.path, ("29161220",), clock=self.clock)
        self.synchronize()
        self.assertEqual(self.source.attempts[count], ("data", True, "2025-11", "2025-12"))
        self.assertNotEqual(self.read().local_revision, previous.local_revision)

    def test_changed_final_metadata_abandons_staging_and_never_replaces_previous_base(self):
        self.synchronize()
        previous = self.read()

        def revision(kind):
            if kind == ("data", True, "2026-01", "2026-01"):
                self.source.publication["updated"] = "2026-03-06"

        self.source.value += 4
        self.source.hook = revision
        with self.assertRaises(HistorySyncError):
            self.synchronize(audit=True)
        self.assertEqual(self.read(), previous)
        self.assertIsNone(self.store.pending_run_info())
        self.assertIsNone(self.store.get_checkpoint("metadata:initial"))
        self.source.hook = None
        count = len(self.source.attempts)
        self.synchronize()
        self.assertEqual(len([kind for kind in self.source.attempts[count:] if kind[0] == "data"]), 4)
        self.assertEqual(self.store.status()["publication"], self.source.publication)

    def test_domain_error_is_not_retained_as_a_successful_general_stage(self):
        self.source.state = "UF desconhecida"
        with self.assertRaises(ComexError):
            self.synchronize()
        pending = self.store.pending_run_info()
        self.assertFalse(self.store.has_stage(pending["run_id"], False, "2025-11", "2025-12"))
        self.assertFalse(self.store.contains(self.period))
        self.source.state = "SP"
        count = len(self.source.attempts)
        self.synchronize()
        self.assertEqual(self.source.attempts[count], ("data", False, "2025-11", "2025-12"))

    def test_bad_municipal_metadata_keeps_only_the_validated_general_metadata_checkpoint(self):
        self.source.publication["municipal_updated"] = "não é uma data"
        with self.assertRaises(HistorySyncError):
            self.synchronize()
        saved = self.store.get_checkpoint("metadata:initial")
        self.assertIn("general", saved)
        self.assertNotIn("municipal", saved)
        self.assertIsNone(self.store.pending_run_info())
        self.source.publication["municipal_updated"] = "2026-02-04"
        count = len(self.source.attempts)
        self.synchronize()
        self.assertEqual(self.source.attempts[count], ("metadata", "municipal"))

    def test_expired_or_invalid_metadata_checkpoint_is_reacquired_instead_of_being_called_current(self):
        for epoch in (self.clock() - 86400, self.clock() + 1, True, 10**400):
            with self.subTest(epoch=str(epoch)[:50]):
                self.store.put_checkpoint("metadata:initial", {
                    "schema": "liarte.comex-metadata/1",
                    "general": {"latest": "2026-02", "updated": "2026-03-05", "received_epoch": epoch, "received_at": "2026-11-10T00:00:00+00:00"},
                })
                client = self.source.factory(Event(), lambda *_: None)
                try:
                    self.syncer()._publication(client, Event(), key="metadata:initial")
                finally:
                    client.close()
                self.assertEqual(self.source.accepted[-2:], [("metadata", "general"), ("metadata", "municipal")])

    def test_corrupt_optional_checkpoint_is_reacquired_without_losing_accepted_data(self):
        self.synchronize()
        previous = self.read()
        self.store.put_checkpoint("metadata:initial", {"schema": "liarte.comex-metadata/1"})
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE checkpoints SET digest='corrupt' WHERE key='metadata:initial'")
        count = len(self.source.attempts)
        result = self.synchronize(force=True)
        self.assertEqual(result["status"], "unchanged")
        self.assertEqual(self.read(), previous)
        self.assertEqual(self.source.attempts[count:], [("metadata", "general"), ("metadata", "municipal")])

    def test_corrupt_final_checkpoint_keeps_all_stages_and_reacquires_only_metadata(self):
        self.synchronize()
        previous = self.read()
        self.source.value += 6
        baseline_municipal = self.source.accepted.count(("metadata", "municipal"))

        def failed_last_metadata(kind):
            if kind == ("metadata", "municipal") and self.source.accepted.count(kind) == baseline_municipal + 2:
                raise engine.ComexStatError("Falha sintética nos metadados finais")

        self.source.hook = failed_last_metadata
        with self.assertRaises(engine.ComexStatError):
            self.synchronize(audit=True)
        self.assertEqual(self.read(), previous)
        run = self.store.pending_run_info()["run_id"]
        final_key = "metadata:final:" + run
        self.assertIn("general", self.store.get_checkpoint(final_key))
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE checkpoints SET digest='corrupt' WHERE key=?", (final_key,))
        self.source.hook = None
        count = len(self.source.attempts)
        self.synchronize()
        self.assertEqual(self.source.attempts[count:], [("metadata", "general"), ("metadata", "municipal")])
        self.assertNotEqual(self.read().local_revision, previous.local_revision)

    def test_generic_checkpoint_storage_error_is_not_treated_as_an_optional_cache_miss(self):
        self.synchronize()
        count = len(self.source.attempts)
        with patch.object(self.store, "get_checkpoint", side_effect=HistoryError("Storage unavailable")):
            with self.assertRaises(HistoryError):
                self.synchronize(force=True)
        self.assertEqual(len(self.source.attempts), count)

    def test_corrupted_staging_is_abandoned_and_the_next_attempt_reextracts_it(self):
        self.synchronize()
        for damage in ("facts", "coverage"):
            with self.subTest(damage=damage):
                previous = self.read()
                self.source.value += 5
                corrupted_run = None

                def corrupt_before_verification(percent, message):
                    nonlocal corrupted_run
                    if percent == 97 and corrupted_run is None:
                        corrupted_run = self.store.pending_run_info()["run_id"]
                        with closing(sqlite3.connect(self.path)) as db, db:
                            if damage == "facts":
                                db.execute(
                                    "DELETE FROM facts WHERE stage_id IN "
                                    "(SELECT id FROM stages WHERE run_id=? AND municipal=0)",
                                    (corrupted_run,),
                                )
                            else:
                                db.execute(
                                    "DELETE FROM coverage WHERE stage_id IN "
                                    "(SELECT id FROM stages WHERE run_id=? AND municipal=0)",
                                    (corrupted_run,),
                                )

                with self.assertRaises(HistoryStagingError):
                    self.synchronize(audit=True, progress=corrupt_before_verification)
                self.assertEqual(self.read(), previous)
                self.assertIsNone(self.store.pending_run_info())
                self.assertIsNone(self.store.get_checkpoint("metadata:final:" + corrupted_run))
                with closing(sqlite3.connect(self.path)) as db, db:
                    status = db.execute("SELECT status FROM runs WHERE id=?", (corrupted_run,)).fetchone()[0]
                self.assertEqual(status, "corrupt")
                self.assertTrue(self.store.status()["reextract_required"])

                self.source.next_allowed = self.clock() + 180
                with self.assertRaises(engine.ComexRateLimitError):
                    self.synchronize()
                self.store = HistoryStore(self.path, ("29161220",), clock=self.clock)
                self.assertTrue(self.store.status()["reextract_required"])
                self.clock.advance(180)
                count = len(self.source.accepted)
                result = self.synchronize()
                calls = self.source.accepted[count:]
                self.assertEqual(result["status"], "updated")
                self.assertEqual(sum(call[0] == "data" for call in calls), 4)
                self.assertEqual(sum(call[0] == "metadata" for call in calls), 4)
                self.assertNotEqual(self.read().local_revision, previous.local_revision)
                self.assertFalse(self.store.status()["reextract_required"])

    def test_generic_staging_io_error_preserves_the_run_for_a_later_retry(self):
        self.synchronize()
        previous = self.read()
        self.source.value += 5
        with patch.object(self.store, "_verify_partitions", side_effect=HistoryError("Storage unavailable")):
            with self.assertRaisesRegex(HistoryError, "Storage unavailable"):
                self.synchronize(audit=True)
        self.assertEqual(self.read(), previous)
        pending = self.store.pending_run_info()
        self.assertIsNotNone(pending)
        self.assertEqual(self.store.status()["staged_stages"], 4)
        count = len(self.source.accepted)
        self.synchronize(force=True)
        self.assertEqual(self.source.accepted[count:], [("metadata", "general"), ("metadata", "municipal")])
        self.assertNotEqual(self.read().local_revision, previous.local_revision)

    def test_busy_writer_does_not_change_the_other_operation_or_construct_a_client(self):
        before = self.store.status()
        with self.store.writer_lock(lambda: None), self.assertRaises(HistoryBusy):
            self.synchronize()
        self.assertEqual(self.store.status(), before)
        self.assertEqual(self.source.clients, [])

    def test_already_cancelled_worker_makes_no_request_and_keeps_accepted_data(self):
        self.synchronize()
        previous, count = self.read(), len(self.source.attempts)
        cancel = Event()
        cancel.set()
        with self.assertRaises(Cancelled):
            self.synchronize(cancel=cancel)
        self.assertEqual(self.read(), previous)
        self.assertEqual(len(self.source.attempts), count)

    def test_publication_guard_rolls_back_and_final_metadata_is_rechecked_on_retry(self):
        self.synchronize()
        previous = self.read()

        @contextmanager
        def denied():
            raise Cancelled()
            yield

        self.source.value += 5
        with self.assertRaises(Cancelled):
            self.syncer(publication_guard=denied).synchronize(Event(), lambda *_: None, audit=True)
        self.assertEqual(self.read(), previous)
        self.assertIsNotNone(self.store.pending_run_info())
        count = len(self.source.attempts)
        self.synchronize()
        self.assertEqual(self.source.attempts[count:], [("metadata", "general"), ("metadata", "municipal")])
        self.assertNotEqual(self.read().local_revision, previous.local_revision)

    def test_cancellation_from_final_ui_callback_does_not_report_rollback_after_commit(self):
        cancel = Event()

        def after_commit(value, message):
            if value == 100:
                cancel.set()
                raise Cancelled()

        result = self.synchronize(cancel=cancel, progress=after_commit)
        self.assertEqual(result["status"], "updated")
        self.assertTrue(result["changed"])
        self.assertTrue(self.store.contains(self.period))
        self.assertEqual(self.store.status()["sync_state"], "ready")

    def test_policy_intervals_are_explicit_and_nbm_is_not_silently_mapped_to_ncm(self):
        for key in ("audit_interval", "check_interval"):
            for invalid in (True, -1, float("nan"), float("inf"), 10**400):
                with self.subTest(key=key, invalid=str(invalid)[:30]), self.assertRaises(ValueError):
                    self.syncer(**{key: invalid})
        with self.assertRaises(ValueError):
            HistorySynchronizer(self.store, self.source.factory, self.validate, first_month="1989-01")


class ComexSyncApiIntegrationTests(unittest.TestCase):
    def test_native_api_obeys_durable_pause_and_resumes_metadata_and_stages_after_restart(self):
        for spacing in (180, 900):
            with self.subTest(spacing=spacing), tempfile.TemporaryDirectory() as directory:
                clock = EpochClock()
                source = HistoricalSource(clock)
                source.spacing = spacing
                path = Path(directory) / "history.sqlite3"
                pause_path = Path(directory) / "api-pause.json"

                def transport(request, **kwargs):
                    endpoint = urlsplit(request.full_url).path
                    if request.method == "GET":
                        base = "general" if endpoint.startswith("/general/") else "municipal"
                        kind = ("metadata", base)
                    else:
                        body = json.loads(request.data)
                        municipal = endpoint == "/cities"
                        start, end = body["period"]["from"], body["period"]["to"]
                        kind = ("data", municipal, start, end)
                    try:
                        source.touch(kind)
                    except engine.ComexRateLimitError as exc:
                        raise HTTPError(
                            request.full_url, 429, "synthetic limit",
                            {"Retry-After": str(exc.retry_after)},
                            io.BytesIO(b'{"error":{"code":429,"message":"synthetic limit"}}'),
                        ) from exc
                    if request.method == "GET":
                        latest = source.publication["latest" if base == "general" else "municipal_latest"]
                        document = {"success": True, "data": {
                            "year": latest[:4], "monthNumber": latest[5:],
                            "updated": source.publication["updated" if base == "general" else "municipal_updated"],
                        }}
                    else:
                        codes = tuple(str(code).zfill(4 if municipal else 8) for code in body["filters"][0]["values"])
                        document = {"success": True, "data": {"list": source.rows(municipal, codes, start)}}

                    class Response(io.BytesIO):
                        status = 200

                        def __init__(self):
                            data = json.dumps(document).encode()
                            super().__init__(data)
                            self.headers = {"Content-Length": str(len(data))}

                    return Response()

                def factory(cancel, progress):
                    return ApiClient(
                        max_attempts=1, rate_limit_attempts=1,
                        pause_state=ApiPause(pause_path, clock=clock),
                        cancel_check=lambda: checkpoint(cancel), cancel_wait=clock.advance,
                        progress_callback=progress,
                    )

                with patch.object(ApiClient, "_open", side_effect=transport):
                    for _ in range(10):
                        store = HistoryStore(path, ("29161220",), clock=clock)
                        syncer = HistorySynchronizer(
                            store, factory, ComexSyncTests.validate,
                            first_month="2026-01", clock=clock,
                        )
                        try:
                            result = syncer.synchronize(Event(), lambda *_: None)
                            break
                        except engine.ComexRateLimitError:
                            self.assertFalse(store.status()["complete"])
                            pause = ApiPause(pause_path, clock=clock)
                            self.assertGreaterEqual(pause.remaining(), spacing)
                            previous = len(source.attempts)
                            with self.assertRaises(engine.ComexRateLimitError):
                                syncer.synchronize(Event(), lambda *_: None)
                            self.assertEqual(len(source.attempts), previous)
                            clock.advance(pause.remaining() + 1)
                    else:
                        self.fail("O transporte nativo repetiu uma etapa concluída.")
                    self.assertEqual(result["status"], "updated")
                    self.assertEqual(len(source.accepted), 6)
                    self.assertEqual(len(source.attempts), 11)
                    self.assertEqual(source.accepted, [
                        ("metadata", "general"), ("metadata", "municipal"),
                        ("data", False, "2026-01", "2026-01"),
                        ("data", True, "2026-01", "2026-01"),
                        ("metadata", "general"), ("metadata", "municipal"),
                    ])
                    accepted = store.read(Period("2026-01", "2026-01"), Event())
                    self.assertEqual(len(accepted.general), 1)
                    self.assertEqual(len(source.attempts), 11)
