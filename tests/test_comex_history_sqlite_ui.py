"""Integração Qt, SQLite e aquisição oficial simulada; nenhuma rede pública."""

from pathlib import Path
import tempfile
from threading import Event
import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent

from liarte_core.comex_api import ApiClient
from liarte_core.comex_historical import HistoricalComexProvider
from liarte_core.domain import Period
from liarte_desktop import app as desktop
from liarte_desktop.controller import DesktopController
from liarte_desktop.runtime_profile import RuntimeProfile
from tests.test_comex import Transport
from tests.test_comex_access import Clock
from tests.test_comex_pause_flow import refusal
from tests.test_qt import APP, pump


class ComexHistorySqliteDesktopTests(unittest.TestCase):
    @staticmethod
    def provider(directory, **options):
        return HistoricalComexProvider(
            directory, codes=("29161220",),
            sync_options={"first_month": "2026-09", "check_interval": 0},
            **options,
        )

    @staticmethod
    def dispose(controller, provider):
        controller.shutdown()
        provider.close()
        controller.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        APP.processEvents()

    def test_first_requested_query_is_loaded_after_the_real_history_is_published(self):
        with tempfile.TemporaryDirectory() as temporary:
            provider = self.provider(Path(temporary))
            transport = Transport()
            controller = DesktopController(provider)
            try:
                self.assertFalse(provider.history.status()["complete"])
                self.assertFalse(controller.state["loaded"])
                with patch.object(ApiClient, "_open", side_effect=transport):
                    controller.queryPeriod("2026-09", "2026-09")
                    self.assertTrue(pump(
                        lambda: controller.state["loaded"]
                        and not controller.state["busy"]
                        and not controller.history.running,
                        10,
                    ), (controller.state, controller.history.state))
                self.assertEqual(len(transport.calls), 6)
                self.assertTrue(provider.history.status()["complete"])
                self.assertTrue((Path(temporary) / "historico_comex.sqlite3").is_file())
                self.assertEqual(controller._result.totals.value_cents, 234015200)
                self.assertEqual(controller._accepted_snapshot.local_revision,
                                 provider.local_period_revision("2026-09", "2026-09"))
                self.assertEqual(controller._accepted_snapshot.api_requests, 0)
                self.assertEqual(controller.state["sourceStatus"], "Base local · Comex Stat")
                self.assertFalse(controller.state["error"])
                self.assertFalse(controller.history.state["error"])
            finally:
                self.dispose(controller, provider)

    def test_restarted_desktop_queries_sqlite_offline_during_a_persisted_rate_pause(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            original = self.provider(directory)
            try:
                with patch.object(ApiClient, "_open", side_effect=Transport()):
                    original.synchronize(Event(), lambda *_: None)
                expected = original.load(Period("2026-09", "2026-09"), Event(), lambda *_: None)
                original._api_pause.defer(180, 429, source_delay=180)
            finally:
                original.close()

            provider = self.provider(directory)
            controller = DesktopController(provider)
            try:
                with patch.object(ApiClient, "_open", side_effect=AssertionError("offline query used network")) as network:
                    controller.queryPeriod("2026-09", "2026-09")
                    self.assertTrue(pump(
                        lambda: controller.state["loaded"] and not controller.state["busy"], 10,
                    ), controller.state)
                    for _ in range(3):
                        controller.history._tick()
                    network.assert_not_called()
                self.assertFalse(controller.history.running)
                self.assertGreater(controller.state["sourcePauseSeconds"], 0)
                self.assertGreater(controller.history.state["pauseSeconds"], 0)
                self.assertEqual(controller._accepted_snapshot.local_revision, expected.local_revision)
                self.assertEqual(controller._accepted_snapshot.general_received_at, expected.general_received_at)
                self.assertEqual(controller._accepted_snapshot.availability.checked_at,
                                 expected.availability.checked_at)
                self.assertEqual(controller._result.totals.value_cents, 234015200)
                self.assertFalse(controller.state["error"])
            finally:
                self.dispose(controller, provider)

    def test_default_bundle_uses_a_profile_local_history_without_starting_network(self):
        with tempfile.TemporaryDirectory() as temporary:
            profile = RuntimeProfile(Path(temporary), development=True)
            bundle = None
            with patch.object(ApiClient, "_open", side_effect=AssertionError("constructor started network")) as network:
                try:
                    bundle = desktop.create_bundle(profile=profile, initial_module="home")
                    desktop.install_availability_refresh(bundle)
                    APP.processEvents()
                    self.assertIsInstance(bundle.controller._provider, HistoricalComexProvider)
                    self.assertEqual(bundle.controller._provider.history.path,
                                     profile.data_dir / "historico_comex.sqlite3")
                    self.assertFalse(bundle.controller.history.running)
                    self.assertFalse(bundle.controller.state["loaded"])
                    self.assertEqual(bundle.controller.history.state["completeMonths"], 0)
                    self.assertEqual(bundle.messages, [])
                    network.assert_not_called()
                finally:
                    if bundle is not None:
                        bundle.services.comex_access.shutdown()
                        bundle.controller.shutdown()
                        desktop._finish_inventory_shutdown(bundle.inventory)
                        bundle.controller._provider.close()
                        for window in bundle.engine.rootObjects():
                            window.close()
                        bundle.engine.deleteLater()
                        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                        APP.processEvents()

    def test_rate_retry_resumes_when_its_pause_expires_and_other_failures_keep_the_cooldown(self):
        # A controlled clock advances the real persisted ApiPause, including
        # its safety margin. No sleep or public source request is needed.
        for status in (429, 503):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as temporary:
                clock = Clock()

                def fail_once_client(**options):
                    options.update(max_attempts=1, rate_limit_attempts=1)
                    return ApiClient(**options)

                provider = self.provider(Path(temporary), client_factory=fail_once_client)
                provider._api_pause.clock = clock
                controller = DesktopController(provider)
                owner = controller.history
                owner.clock = clock
                started_at = clock()
                transport, attempts = Transport(), []

                def official_transport(request, **options):
                    attempts.append(request.full_url)
                    if len(attempts) == 1:
                        raise refusal(request, status=status, seconds=84)
                    return transport(request, **options)

                try:
                    with patch.object(ApiClient, "_open", side_effect=official_transport):
                        owner.startAutomatic()
                        self.assertTrue(pump(lambda: not owner.running and bool(owner.state["error"]), 10))
                        self.assertEqual(len(attempts), 1)
                        pause_deadline = provider._api_pause.until
                        if status == 429:
                            self.assertLessEqual(owner._next_attempt, pause_deadline)
                        else:
                            self.assertEqual(owner._next_attempt, started_at + owner.check_interval)
                        clock.wait(pause_deadline - clock() - 1)
                        owner._tick()
                        APP.processEvents()
                        self.assertEqual(len(attempts), 1)
                        clock.wait(1.001)
                        if status == 503:
                            owner._tick()
                            APP.processEvents()
                            self.assertEqual(len(attempts), 1)
                            clock.wait(started_at + owner.check_interval - clock())
                        owner._tick()
                        self.assertTrue(pump(
                            lambda: provider.history.status()["complete"] and not owner.running, 10,
                        ), owner.state)
                        self.assertEqual(len(attempts), 7)
                        self.assertFalse(owner.state["error"])
                        for _ in range(3):
                            owner._tick()
                        APP.processEvents()
                        self.assertEqual(len(attempts), 7)
                finally:
                    self.dispose(controller, provider)
