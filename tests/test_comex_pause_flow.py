"""Recovery continues one unfinished operation without renewing its HTTP pressure."""

import io
import json
from threading import Event
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlsplit

from liarte_core.comex import ComexError
from liarte_core.comex_api import ApiClient
from liarte_core.domain import Period
from liarte_core.query import Cancelled
from tests import test_comex_api as api_tests
from tests import test_comex as ui_fixture
from tests.test_comex_access import Clock
from tests.test_qt import pump, settled


def refusal(request, status=429, seconds=180):
    return HTTPError(
        request.full_url, status, "controlled rejection", {"Retry-After": str(seconds)},
        io.BytesIO(json.dumps({"error": {"code": status, "message": "controlled"}}).encode()),
    )


class LockBoundary:
    """Schedule an invalidation just before the worker acquires its lock."""

    def __init__(self, lock):
        self.lock = lock
        self.before_acquire = None

    def __enter__(self):
        callback, self.before_acquire = self.before_acquire, None
        if callback is not None:
            callback()
        self.lock.acquire()
        return self

    def __exit__(self, *args):
        self.lock.release()


class ComexPauseFlowTests(unittest.TestCase):
    setUp = api_tests.NativeApiTests.setUp
    tearDown = api_tests.NativeApiTests.tearDown
    load = api_tests.NativeApiTests.load

    def pending(self):
        clock, wire = getattr(self, "_flow_clock", None) or Clock(), []
        self._flow_clock = clock
        self.provider._api_pause.clock = clock
        self.provider._operation_clock = clock

        def limit_municipal(request, **kwargs):
            path = urlsplit(request.full_url).path
            wire.append(path)
            if path == "/cities":
                raise refusal(request)
            return self.transport(request, **kwargs)

        with patch.object(ApiClient, "_open", side_effect=limit_municipal):
            with self.assertRaises(ComexError):
                self.load()
        self.assertEqual(wire, ["/general", "/cities"])
        self.assertTrue(self.provider.access_status()["resume_pending"])
        return clock, wire

    def test_global_rate_limit_no_longer_replays_general_after_each_pause(self):
        clock, wire = Clock(), []
        self.provider._api_pause.clock = clock
        self.provider._operation_clock = clock
        next_allowed = 0.0

        def one_request_per_pause(request, **kwargs):
            nonlocal next_allowed
            wire.append(urlsplit(request.full_url).path)
            if clock() < next_allowed:
                raise refusal(request)
            next_allowed = clock() + 180
            return self.transport(request, **kwargs)

        with patch.object(ApiClient, "_open", side_effect=one_request_per_pause):
            with self.assertRaises(ComexError):
                self.load()
            self.assertIsNone(self.provider.snapshot)
            deadline = self.provider._api_pause.until
            with self.assertRaises(ComexError):
                self.load()
            self.assertEqual(wire, ["/general", "/cities"])
            self.assertEqual(self.provider._api_pause.until, deadline)
            clock.wait(self.provider._api_pause.remaining() + 1)
            snapshot = self.load()
        self.assertEqual(wire, ["/general", "/cities", "/cities"])
        self.assertEqual(snapshot.api_requests, 3)
        self.assertTrue(snapshot.response_validated)
        self.assertFalse(self.provider.access_status()["resume_pending"])
        self.assertEqual(len(snapshot.general), len(self.transport.general))
        self.assertTrue(snapshot.acquisition_started_at)
        self.assertTrue(snapshot.general_received_at)
        self.assertTrue(snapshot.municipal_received_at)

    def test_legitimate_nine_hundred_second_source_pause_keeps_a_valid_recovery_window(self):
        clock, wire = Clock(), []
        self.provider._api_pause.clock = self.provider._operation_clock = clock
        next_allowed = 0.0

        def origin(request, **kwargs):
            nonlocal next_allowed
            wire.append(urlsplit(request.full_url).path)
            if clock() < next_allowed:
                raise refusal(request, seconds=900)
            next_allowed = clock() + 900
            return self.transport(request, **kwargs)

        with patch.object(ApiClient, "_open", side_effect=origin):
            with self.assertRaises(ComexError):
                self.load()
            state = self.provider.access_status()
            self.assertGreater(state["resume_valid_seconds"], state["pause_seconds"])
            received = state["resume_received_at"]
            clock.wait(self.provider._api_pause.remaining() + 1)
            result = self.load()
        self.assertEqual(wire, ["/general", "/cities", "/cities"])
        self.assertEqual(result.general_received_at, received)

    def recover_annual_stages(self, period, seconds):
        self.period = period
        clock, attempts, accepted = Clock(), [], []
        self.provider._api_pause.clock = self.provider._operation_clock = clock
        next_allowed = 0.0
        first_expiry = None
        started_at = None

        def origin(request, **kwargs):
            nonlocal next_allowed
            body = json.loads(request.data)
            window = body["period"]
            stage = (urlsplit(request.full_url).path, window["from"], window["to"])
            attempts.append(stage)
            if clock() < next_allowed:
                raise refusal(request, seconds=seconds)
            next_allowed = clock() + seconds
            accepted.append(stage)
            return self.transport(request, **kwargs)

        with patch.object(ApiClient, "_open", side_effect=origin):
            # At most one new stage fits each source interval. Completed empty
            # years are still complete and cannot consume the next interval.
            for _ in range(2 * (int(period.end[:4]) - int(period.start[:4]) + 1)):
                try:
                    result = self.load()
                    break
                except ComexError:
                    self.assertIsNone(self.provider.snapshot)
                    pending = self.provider._incomplete_api
                    self.assertIsNotNone(pending)
                    if first_expiry is None:
                        first_expiry = pending.expires_clock
                        started_at = pending.started_at
                        self.assertEqual(len(pending.completed_stages), 1)
                        self.assertEqual(next(iter(pending.completed_stages.values())), ())
                    self.assertEqual(pending.expires_clock, first_expiry)
                    self.assertEqual(pending.started_at, started_at)
                    pause = self.provider._api_pause.remaining()
                    self.assertGreater(pending.expires_clock - clock(), pause)
                    clock.wait(pause + 1)
            else:
                self.fail("A retomada repetiu etapas já aceitas sem concluir a operação")
        expected = [
            (path, max(period.start, f"{year}-01"), min(period.end, f"{year}-12"))
            for path in ("/general", "/cities")
            for year in range(int(period.start[:4]), int(period.end[:4]) + 1)
        ]
        self.assertEqual(accepted, expected)
        self.assertEqual(len(attempts), 2 * len(expected) - 1)
        self.assertEqual(result.api_requests, len(attempts))
        self.assertEqual(result.acquisition_started_at, started_at)
        self.assertEqual(len(result.general), len(self.transport.general))
        self.assertEqual(len(result.municipal), len(self.transport.municipal))
        self.assertFalse(self.provider.access_status()["resume_pending"])
        self.assertLessEqual(first_expiry - 1000, 3600)

    def test_two_calendar_years_resume_each_validated_stage_with_a_nine_hundred_second_pause(self):
        self.recover_annual_stages(Period("2025-10", "2026-09"), 900)

    def test_three_calendar_years_resume_empty_and_nonempty_stages_without_replaying_them(self):
        self.recover_annual_stages(Period("2024-03", "2026-09"), 180)

    def test_more_than_fifty_ncms_keep_one_municipal_heading_union_per_year(self):
        codes = tuple(f"2916{i:04d}" for i in range(100))
        completed, requests = {}, []

        def empty_origin(request, **kwargs):
            body = json.loads(request.data)
            requests.append((urlsplit(request.full_url).path, body["period"], body["filters"][0]["values"]))
            return api_tests.BytesResponse(b'{"success":true,"data":{"list":[]}}')

        client = ApiClient(pause_state=self.provider._api_pause)
        try:
            with patch.object(ApiClient, "_open", side_effect=empty_origin):
                for _ in range(2):
                    self.assertEqual(client.query_imports(codes, "2025-10", "2026-09", completed_stages=completed), [])
                    self.assertEqual(client.query_municipal_imports(codes, "2025-10", "2026-09", completed_stages=completed), [])
        finally:
            client.close()
        self.assertEqual([path for path, _, _ in requests], ["/general"] * 2 + ["/cities"] * 2)
        self.assertEqual([values for path, _, values in requests if path == "/general"], [list(map(int, codes))] * 2)
        self.assertEqual([values for path, _, values in requests if path == "/cities"], [["2916"], ["2916"]])
        self.assertEqual(len(completed), 4)

    def test_expiration_discards_only_the_partial_and_does_not_shorten_the_source_pause(self):
        clock, _ = self.pending()
        source_deadline = self.provider._api_pause.until
        clock.wait(self.provider.access_status()["resume_valid_seconds"] + 1)
        state = self.provider.access_status()
        self.assertTrue(state["resume_expired"])
        self.assertFalse(state["resume_pending"])
        self.assertEqual(self.provider._api_pause.until, source_deadline)
        before = len(self.transport.calls)
        self.load()
        self.assertEqual(self.transport.calls[before:], [("POST", "/general"), ("POST", "/cities")])
        self.assertFalse(self.provider.access_status()["resume_expired"])

    def test_a_repeated_rejection_does_not_renew_the_lifetime_of_the_general_part(self):
        clock, _ = self.pending()
        expiry = self.provider._incomplete_api.expires_clock
        clock.wait(self.provider._api_pause.remaining() + 1)

        def denied(request, **kwargs):
            raise refusal(request)

        with patch.object(ApiClient, "_open", side_effect=denied):
            with self.assertRaises(ComexError):
                self.load()
        self.assertEqual(self.provider._incomplete_api.expires_clock, expiry)

    def reject_at_retention_boundary(self, action, *, cancel=None):
        boundary = LockBoundary(self.provider._lock)
        invoked = []

        def invalidate():
            invoked.append(True)
            action()

        def denied(request, **kwargs):
            if urlsplit(request.full_url).path == "/cities":
                boundary.before_acquire = invalidate
                raise refusal(request)
            return self.transport(request, **kwargs)

        self.provider.revalidate_next()
        with (
            patch.object(self.provider, "_lock", boundary),
            patch.object(ApiClient, "_open", side_effect=denied),
            self.assertRaises(ComexError),
        ):
            self.provider.load(self.period, cancel or Event(), lambda *_: None)
        self.assertEqual(invoked, [True])

    def test_cancellation_at_retention_boundary_cannot_restore_the_discarded_operation(self):
        previous = self.load()
        cancel = Event()

        def cancellation():
            cancel.set()
            self.provider.cancel_pending_options()

        self.reject_at_retention_boundary(cancellation, cancel=cancel)
        self.assertTrue(cancel.is_set())
        self.assertIs(self.provider.snapshot, previous)
        self.assertFalse(self.provider.access_status()["resume_pending"])

    def test_same_identity_discard_at_retention_boundary_invalidates_the_older_worker(self):
        previous = self.load()
        clock = Clock()
        self.provider._api_pause.clock = self.provider._operation_clock = clock
        for method in ("cancel_pending_options", "force_refresh", "connection_changed", "close"):
            with self.subTest(method=method):
                clock.wait(self.provider._api_pause.remaining() + 1)
                identity = self.provider._operation_identity(self.period)
                self.reject_at_retention_boundary(getattr(self.provider, method))
                self.assertEqual(self.provider._operation_identity(self.period), identity)
                self.assertIs(self.provider.snapshot, previous)
                self.assertFalse(self.provider.access_status()["resume_pending"])

    def test_source_change_at_retention_boundary_cannot_keep_an_obsolete_stage(self):
        previous = self.load()

        def source_change():
            self.provider.codes = ("29161220", "29161310")

        self.reject_at_retention_boundary(source_change)
        self.assertIs(self.provider.snapshot, previous)
        self.assertFalse(self.provider.access_status()["resume_pending"])

    def test_expiration_at_retention_boundary_cannot_restore_an_expired_operation(self):
        previous = self.load()
        clock, _ = self.pending()
        expiry = self.provider._incomplete_api.expires_clock
        clock.wait(self.provider._api_pause.remaining() + 1)
        self.reject_at_retention_boundary(lambda: clock.wait(expiry - clock() + 1))
        self.assertIs(self.provider.snapshot, previous)
        state = self.provider.access_status()
        self.assertFalse(state["resume_pending"])
        self.assertTrue(state["resume_expired"])

    def test_same_identity_discard_at_publication_boundary_preserves_the_complete_snapshot(self):
        previous = self.load()
        original = ApiClient.query_municipal_imports
        for method in ("cancel_pending_options", "force_refresh", "connection_changed", "close"):
            with self.subTest(method=method):
                boundary = LockBoundary(self.provider._lock)
                identity = self.provider._operation_identity(self.period)

                def arm_publication(client, *args, **kwargs):
                    rows = original(client, *args, **kwargs)
                    boundary.before_acquire = getattr(self.provider, method)
                    return rows

                with (
                    patch.object(self.provider, "_lock", boundary),
                    patch.object(ApiClient, "query_municipal_imports", new=arm_publication),
                    self.assertRaisesRegex(ComexError, "reiniciada ou cancelada"),
                ):
                    self.load()
                self.assertEqual(self.provider._operation_identity(self.period), identity)
                self.assertIs(self.provider.snapshot, previous)
                self.assertFalse(self.provider.access_status()["resume_pending"])

    def test_a_response_arriving_after_partial_expiration_is_not_published(self):
        clock, _ = self.pending()
        clock.wait(self.provider._api_pause.remaining() + 1)

        def late(request, **kwargs):
            clock.wait(self.provider.access_status()["resume_valid_seconds"] + 1)
            return self.transport(request, **kwargs)

        with patch.object(ApiClient, "_open", side_effect=late):
            with self.assertRaisesRegex(ComexError, "expirou"):
                self.load()
        self.assertIsNone(self.provider.snapshot)
        self.assertTrue(self.provider.access_status()["resume_expired"])

    def test_expiration_during_conversion_preserves_the_previous_complete_snapshot(self):
        previous = self.load()
        clock, _ = self.pending()
        clock.wait(self.provider._api_pause.remaining() + 1)
        expiry = self.provider._incomplete_api.expires_clock
        original = self.provider._convert

        def expire_while_converting(general, municipal, cancel):
            result = original(general, municipal, cancel)
            clock.wait(expiry - clock() + 1)
            return result

        with patch.object(self.provider, "_convert", side_effect=expire_while_converting):
            with self.assertRaisesRegex(ComexError, "expirou"):
                self.load()
        self.assertIs(self.provider.snapshot, previous)
        self.assertFalse(self.provider.access_status()["resume_pending"])
        self.assertTrue(self.provider.access_status()["resume_expired"])

    def test_cancellation_during_preparation_never_publishes_a_snapshot(self):
        previous = self.load()
        cancel = Event()
        original = self.provider._convert

        class CancelOnOptions(tuple):
            def __iter__(self):
                cancel.set()
                return super().__iter__()

        def cancellation_during_options(general, municipal, token):
            records, municipal_records = original(general, municipal, token)
            # The complete conversion succeeds; cancellation arrives when
            # options are read, after the earlier conversion checkpoint.
            return (CancelOnOptions(records) if municipal else records), municipal_records

        with patch.object(self.provider, "_convert", side_effect=cancellation_during_options):
            self.provider.revalidate_next()
            with self.assertRaises(Cancelled):
                self.provider.load(self.period, cancel, lambda *_: None)
        self.assertIs(self.provider.snapshot, previous)
        self.assertFalse(self.provider.access_status()["resume_pending"])

    def test_source_change_during_preparation_never_publishes_a_resumed_snapshot(self):
        previous = self.load()
        clock, _ = self.pending()
        clock.wait(self.provider._api_pause.remaining() + 1)
        original = self.provider._convert

        def change_source(general, municipal, cancel):
            result = original(general, municipal, cancel)
            self.provider.codes = ("29161220", "29161310")
            return result

        with patch.object(self.provider, "_convert", side_effect=change_source):
            with self.assertRaisesRegex(ComexError, "origem.*mudou"):
                self.load()
        self.assertIs(self.provider.snapshot, previous)
        self.assertFalse(self.provider.access_status()["resume_pending"])

    def test_general_domain_validation_finishes_before_any_resumable_data_is_kept(self):
        previous = self.load()
        self.transport.general[0]["state"] = "UF inválida da fonte"
        wire = []

        def denied_municipal(request, **kwargs):
            wire.append(urlsplit(request.full_url).path)
            if wire[-1] == "/cities":
                raise refusal(request)
            return self.transport(request, **kwargs)

        with patch.object(ApiClient, "_open", side_effect=denied_municipal):
            with self.assertRaisesRegex(ComexError, "UF não reconhecida"):
                self.load()
        self.assertEqual(wire, ["/general"])
        self.assertIs(self.provider.snapshot, previous)
        self.assertFalse(self.provider.access_status()["resume_pending"])

    def test_a_pause_beyond_supported_freshness_is_not_offered_as_resumable(self):
        clock = Clock()
        self.provider._api_pause.clock = self.provider._operation_clock = clock

        def long_pause(request, **kwargs):
            if urlsplit(request.full_url).path == "/cities":
                raise refusal(request, seconds=7200)
            return self.transport(request, **kwargs)

        with patch.object(ApiClient, "_open", side_effect=long_pause):
            with self.assertRaises(ComexError):
                self.load()
        state = self.provider.access_status()
        self.assertGreaterEqual(state["pause_seconds"], 7200)
        self.assertFalse(state["resume_pending"])
        self.assertTrue(state["resume_unavailable"])

    def test_confirmed_source_revision_change_discards_the_partial(self):
        clock, _ = self.pending()
        clock.wait(self.provider._api_pause.remaining() + 1)
        self.provider.availability(Event(), force=True)
        self.assertFalse(self.provider.access_status()["resume_pending"])
        before = len(self.transport.calls)
        self.load()
        self.assertEqual(self.transport.calls[before:], [("POST", "/general"), ("POST", "/cities")])

    def test_complete_next_consultation_starts_fresh_and_never_uses_the_completed_stage(self):
        clock, _ = self.pending()
        clock.wait(self.provider._api_pause.remaining() + 1)
        resumed = self.load()
        previous_calls = len(self.transport.calls)
        complete = self.load()
        self.assertEqual(len(self.transport.calls) - previous_calls, 2)
        self.assertEqual(complete.api_requests, 2)
        self.assertIsNot(complete, resumed)

    def test_different_period_discards_general_from_the_failed_period(self):
        clock, _ = self.pending()
        clock.wait(self.provider._api_pause.remaining() + 1)
        before = len(self.transport.calls)
        period = Period("2026-08", "2026-09")
        self.provider.revalidate_next()
        result = self.provider.load(period, Event(), lambda *_: None)
        self.assertEqual(result.period, period)
        self.assertEqual(self.transport.calls[before:], [("POST", "/general"), ("POST", "/cities")])
        self.assertFalse(self.provider.access_status()["resume_pending"])

    def test_cancel_refresh_and_source_change_discard_the_unfinished_response(self):
        for method in ("cancel_pending_options", "force_refresh", "connection_changed"):
            with self.subTest(method=method):
                clock, _ = self.pending()
                clock.wait(self.provider._api_pause.remaining() + 1)
                getattr(self.provider, method)()
                self.assertFalse(self.provider.access_status()["resume_pending"])
                before = len(self.transport.calls)
                self.load()
                self.assertEqual(self.transport.calls[before:], [("POST", "/general"), ("POST", "/cities")])

    def test_an_already_cancelled_operation_discards_its_pending_response(self):
        self.pending()
        cancel = Event()
        cancel.set()
        with self.assertRaises(Cancelled):
            self.provider.load(self.period, cancel, lambda *_: None)
        self.assertFalse(self.provider.access_status()["resume_pending"])

    def test_other_failure_discards_pending_data_and_preserves_previous_complete_snapshot(self):
        previous = self.load()
        clock, _ = self.pending()
        self.assertIs(self.provider.snapshot, previous)
        clock.wait(self.provider._api_pause.remaining() + 1)
        wire = []

        def forbidden(request, **kwargs):
            wire.append(urlsplit(request.full_url).path)
            raise refusal(request, 403)

        with patch.object(ApiClient, "_open", side_effect=forbidden):
            with self.assertRaises(ComexError):
                self.load()
        self.assertEqual(wire, ["/cities"])
        self.assertIs(self.provider.snapshot, previous)
        self.assertFalse(self.provider.access_status()["resume_pending"])

    def test_incomplete_data_is_not_restored_from_disk_in_a_second_provider(self):
        from liarte_core.comex import ComexProvider

        self.pending()
        following = ComexProvider(self.directory, codes=self.provider.codes)
        try:
            self.assertFalse(following.access_status()["resume_pending"])
            self.assertIsNone(following.snapshot)
        finally:
            following.close()


class ComexPauseFlowQtTests(unittest.TestCase):
    setUp = api_tests.NativeApiQtTests.setUp
    tearDown = api_tests.NativeApiQtTests.tearDown
    item = api_tests.NativeApiQtTests.item
    load = api_tests.NativeApiQtTests.load

    def test_controller_retakes_the_pending_endpoint_after_the_real_button_is_reenabled(self):
        clock = Clock()
        self.provider._api_pause.clock = clock
        self.provider._operation_clock = clock
        next_allowed, wire = 0.0, []

        def one_request_per_pause(request, **kwargs):
            nonlocal next_allowed
            wire.append(urlsplit(request.full_url).path)
            if clock() < next_allowed:
                raise refusal(request)
            next_allowed = clock() + 180
            return self.transport(request, **kwargs)

        with patch.object(ApiClient, "_open", side_effect=one_request_per_pause):
            self.controller.queryPeriod("2026-09", "2026-09")
            settled(self.controller)
            self.assertFalse(self.controller.state["loaded"])
            self.assertFalse(self.item("queryButton").property("enabled"))
            self.assertEqual(self.item("queryButton").property("text"), "Retomar consulta")
            wire_before = list(wire)
            self.controller._sync_access_status()
            self.assertEqual(wire, wire_before)
            clock.wait(self.provider._api_pause.remaining() + 1)
            self.controller._sync_access_status()
            self.assertTrue(pump(lambda: self.item("queryButton").property("enabled")))
            self.assertEqual(wire, wire_before)
            # revalidate_next() must preserve this unfinished source operation
            # when the real QML button dispatches its public controller slot.
            ui_fixture.click(self.window, self.item("queryButton"))
            settled(self.controller)
        self.assertTrue(self.controller.state["loaded"], self.controller.state["error"])
        self.assertFalse(self.controller.state["error"])
        self.assertEqual(wire, ["/general", "/cities", "/cities"])
        self.assertFalse(self.controller.state["sourceResumeStart"])
        self.assertNotEqual(self.item("queryButton").property("text"), "Retomar consulta")
        self.assertEqual(self.bundle.messages, [])

    def test_explicit_restart_respects_the_pause_and_refetches_both_endpoints(self):
        clock = Clock()
        self.provider._api_pause.clock = self.provider._operation_clock = clock

        def blocked(request, **kwargs):
            if urlsplit(request.full_url).path == "/cities":
                raise refusal(request)
            return self.transport(request, **kwargs)

        with patch.object(ApiClient, "_open", side_effect=blocked):
            self.controller.queryPeriod("2026-09", "2026-09")
            settled(self.controller)
        self.assertTrue(self.provider.access_status()["resume_pending"])
        calls = len(self.transport.calls)
        self.controller.restartQueryPeriod("2026-09", "2026-09")
        self.assertEqual(len(self.transport.calls), calls)
        self.assertTrue(self.provider.access_status()["resume_pending"])
        clock.wait(self.provider._api_pause.remaining() + 1)
        self.controller._sync_access_status()
        self.assertTrue(pump(lambda: self.item("restartIncompleteQuery").property("enabled")))
        ui_fixture.click(self.window, self.item("restartIncompleteQuery"))
        settled(self.controller)
        self.assertTrue(self.controller.state["loaded"], self.controller.state["error"])
        self.assertEqual(self.transport.calls[calls:], [("POST", "/general"), ("POST", "/cities")])
        self.assertFalse(self.provider.access_status()["resume_pending"])
        self.assertEqual(self.bundle.messages, [])

    def test_local_recovery_and_temporary_unavailability_have_distinct_countdown_messages(self):
        clock = Clock()
        pause = self.provider._api_pause
        pause.clock = clock
        for status, reason, expected in (
            (429, "source", "solicitou uma pausa"),
            (429, "recovery", "recuperação da aplicação"),
            (503, "unavailable", "indisponível (HTTP 503)"),
        ):
            with self.subTest(status=status, reason=reason):
                pause.defer(84, status, source_delay=10.5 if reason == "recovery" else 84)
                self.controller._sync_access_status()
                text = self.item("queryError").property("text")
                self.assertIn(expected, text)
                self.assertFalse(self.item("queryButton").property("enabled"))
                if status == 503:
                    self.assertNotIn("solicitou uma pausa", text)
                clock.wait(pause.remaining() + 1)
                self.controller._sync_access_status()
                self.assertTrue(pump(lambda: self.item("queryButton").property("enabled")))
        self.assertEqual(self.transport.calls, [])
        self.assertEqual(self.bundle.messages, [])
