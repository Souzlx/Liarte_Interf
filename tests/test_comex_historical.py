"""Consultas e gerações do histórico local com fatos e transportes sintéticos."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import io
import json
from pathlib import Path
from threading import Event
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

from liarte_core.comex import ComexError
from liarte_core.comex_api import ApiClient
from liarte_core.comex_historical import HistoricalComexProvider
from liarte_core.domain import Period, Selection
from liarte_core.query import Cancelled


CODE = "99887766"
STAMP = "2020-02-03T10:00:00+00:00"
PUBLICATION = {
    "latest": "2019-03", "updated": "2019-04-08",
    "municipal_latest": "2019-03", "municipal_updated": "2019-04-09",
}


def synthetic_general(*, amount=101, month="03", code=CODE, state="SP"):
    return {
        "coNcm": code, "ncm": "Produto sintético de teste",
        "year": "2019", "monthNumber": month,
        "state": state, "urf": "Recinto sintético", "country": "País sintético",
        "metricFOB": str(amount), "metricFreight": "3", "metricInsurance": "2",
        "metricCIF": str(amount + 5), "metricKG": "7",
    }


def synthetic_municipal(*, amount=97, month="03", code=CODE):
    return {
        "headingCode": code[:4], "heading": "Posição sintética de teste",
        "year": "2019", "monthNumber": month,
        "state": "SP", "country": "País sintético",
        "noMunMinsgUf": "Município sintético - SP",
        "metricFOB": str(amount), "metricKG": "11",
    }


class HistoricalComexProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.period = Period("2019-03", "2019-03")
        self.provider = HistoricalComexProvider(self.directory, codes=(CODE,))
        self.store = self.provider.history
        self.network = patch.object(ApiClient, "_open", side_effect=AssertionError("unexpected network"))
        self.network.start()

    def tearDown(self):
        self.provider.close()
        self.network.stop()
        self.temp.cleanup()

    def accept(self, *, general=None, municipal=None, publication=None, store=None):
        store = store or self.store
        publication = dict(publication or PUBLICATION)
        start, end = self.period.start, self.period.end
        run = store.begin_run(publication, start, end)
        store.write_stage(
            run, False, start, end,
            [synthetic_general()] if general is None else general,
            received_at=STAMP, acquisition_started_at=STAMP,
        )
        store.write_stage(
            run, True, start, end,
            [synthetic_municipal()] if municipal is None else municipal,
            received_at=STAMP, acquisition_started_at=STAMP,
        )
        store.record_check(publication)
        store.publish_run(run)
        return run

    def load(self, *, cancel=None, progress=None):
        return self.provider.load(self.period, cancel or Event(), progress or (lambda *_: None))

    def test_empty_installation_reports_missing_coverage_without_a_network_fallback(self):
        self.assertFalse(self.provider.has_local_period(self.period.start, self.period.end))
        with self.assertRaisesRegex(ComexError, "ainda não cobre"):
            self.load()
        self.assertIsNone(self.provider.snapshot)

    def test_query_uses_complete_local_data_during_a_persisted_api_pause(self):
        self.accept()
        self.provider._api_pause.defer(180, 429, source_delay=180)
        result = self.provider.query(Selection(self.period), Event(), lambda *_: None)
        snapshot = self.provider.snapshot
        self.assertEqual(result.totals.value_cents, 10600)
        self.assertEqual(snapshot.api_requests, 0)
        self.assertTrue(snapshot.historical)
        self.assertTrue(snapshot.response_validated)
        self.assertEqual(snapshot.source_channels, ("comex-api", "local-history"))
        self.assertGreater(self.provider.access_status()["pause_seconds"], 0)
        self.assertTrue(self.provider.access_status()["historical_mode"])
        self.assertFalse(self.provider.access_status()["resume_pending"])

    def test_restart_reads_the_persisted_history_and_its_original_provenance(self):
        self.accept()
        first = self.load()
        self.provider.close()
        self.provider = HistoricalComexProvider(self.directory, codes=(CODE,))
        second = self.load()
        self.assertEqual(second.general, first.general)
        self.assertEqual(second.local_revision, first.local_revision)
        self.assertEqual(dict(second.source_publication), PUBLICATION)
        self.assertEqual(second.acquisition_started_at, first.acquisition_started_at)
        self.assertEqual(second.general_received_at, first.general_received_at)
        self.assertEqual(second.availability.checked_at, first.availability.checked_at)

    def test_repeated_consultation_reads_the_same_local_revision_without_refetching(self):
        self.accept()
        first = self.load()
        self.provider.revalidate_next()
        second = self.load()
        self.assertIs(second, first)
        self.assertFalse(self.provider._revalidate_next)

    def test_insert_change_and_delete_replace_the_visible_local_revision_exactly(self):
        self.accept(general=[synthetic_general(), synthetic_general(amount=203, state="RJ")])
        first = self.load()
        previous_rows = tuple(dict(row) for row in first.general)
        self.accept(general=[synthetic_general(amount=107)])
        second = self.load()
        self.assertNotEqual(first.local_revision, second.local_revision)
        self.assertEqual(len(second.general_records), 1)
        self.assertEqual(second.general_records[0].cif_cents, 11200)
        self.assertEqual(first.general, previous_rows)
        self.assertEqual(len(first.general_records), 2)

    def test_empty_validated_month_is_a_local_zero_result_instead_of_a_gap(self):
        self.accept(general=[], municipal=[])
        result = self.provider.query(Selection(self.period), Event(), lambda *_: None)
        self.assertEqual(result.totals.records, 0)
        self.assertEqual(result.totals.value_cents, 0)
        self.assertEqual(self.provider.snapshot.general, ())
        self.assertEqual(self.provider.options("general")["products"], ())
        self.assertTrue(self.provider.has_local_period(self.period.start, self.period.end))

    def test_product_options_use_latest_source_labels_without_changing_the_rows(self):
        second_code = "99887767"
        self.provider.close()
        self.provider = HistoricalComexProvider(self.directory, codes=(second_code, CODE))
        self.store = self.provider.history
        self.period = Period("2019-01", "2019-03")
        rows = [
            dict(synthetic_general(month="01"), ncm="Descrição anterior"),
            dict(synthetic_general(month="03", state="RJ"), ncm="Descrição Z sintética"),
            dict(synthetic_general(month="03", state="SP"), ncm="Descrição A sintética"),
            dict(synthetic_general(month="02", code=second_code), ncm="Outro produto sintético"),
        ]
        self.accept(general=rows)
        snapshot = self.load()
        expected = ((CODE, "Descrição Z sintética"), (second_code, "Outro produto sintético"))
        self.assertEqual(self.provider.options("general")["products"], expected)
        self.assertEqual(
            {row.official_description for row in snapshot.general_records},
            {row["ncm"] for row in rows},
        )
        self.accept(general=list(reversed(rows)))
        self.provider.force_refresh()
        self.load()
        self.assertEqual(self.provider.options("general")["products"], expected)

    def test_unavailable_period_preserves_the_previous_complete_snapshot(self):
        self.accept()
        first = self.load()
        with self.assertRaisesRegex(ComexError, "ainda não cobre"):
            self.provider.load(Period("2019-02", "2019-03"), Event(), lambda *_: None)
        self.assertIs(self.provider.snapshot, first)

    def test_integer_values_above_sqlite_int64_remain_exact_in_the_analysis(self):
        amount = 10**35 + 17
        self.accept(general=[synthetic_general(amount=amount)])
        result = self.provider.query(Selection(self.period), Event(), lambda *_: None)
        self.assertEqual(result.totals.fob_cents, amount * 100)
        self.assertEqual(result.totals.value_cents, (amount + 5) * 100)

    def test_cancel_during_preparation_never_replaces_the_previous_snapshot(self):
        self.accept()
        first = self.load()
        self.accept(general=[synthetic_general(amount=109)])
        cancel = Event()

        def report(percent, _message):
            if percent == 35:
                cancel.set()

        with self.assertRaises(Cancelled):
            self.load(cancel=cancel, progress=report)
        self.assertIs(self.provider.snapshot, first)

    def test_same_identity_discard_at_publication_prevents_the_older_read(self):
        self.accept()
        first = self.load()
        self.accept(general=[synthetic_general(amount=109)])

        def report(percent, _message):
            if percent == 80:
                self.provider.cancel_pending_options()

        with self.assertRaisesRegex(ComexError, "cancelada"):
            self.load(progress=report)
        self.assertIs(self.provider.snapshot, first)

    def test_manifest_change_during_preparation_is_not_published_as_the_newer_base(self):
        self.accept()
        first = self.load()
        self.accept(general=[synthetic_general(amount=109)])

        def report(percent, _message):
            if percent == 80:
                self.accept(general=[synthetic_general(amount=113)])

        with self.assertRaisesRegex(ComexError, "atualizada durante"):
            self.load(progress=report)
        self.assertIs(self.provider.snapshot, first)
        self.assertEqual(self.load().general_records[0].cif_cents, 11800)

    def test_bad_domain_data_preserves_the_previous_accepted_analysis(self):
        self.accept()
        first = self.load()
        self.accept(general=[synthetic_general(state="UF sintética inválida")])
        with self.assertRaisesRegex(ComexError, "UF não reconhecida"):
            self.load()
        self.assertIs(self.provider.snapshot, first)

    def test_read_boundary_rejects_rows_outside_the_requested_period(self):
        self.accept()
        first = self.load()
        self.accept(general=[synthetic_general(amount=109)])
        data = self.store.read(self.period, Event())
        broken = replace(data, general=(synthetic_general(month="02"),))
        with patch.object(self.store, "read", return_value=broken), self.assertRaisesRegex(ComexError, "fora da janela"):
            self.load()
        self.assertIs(self.provider.snapshot, first)

    def test_cached_navigation_is_invalidated_by_an_accepted_database_revision(self):
        self.accept()
        selection = Selection(self.period)
        self.provider.query(selection, Event(), lambda *_: None)
        self.assertIsNotNone(self.provider.cached_query(selection))
        self.accept(general=[synthetic_general(amount=137)])
        self.assertIsNone(self.provider.cached_query(selection))

    def test_a_check_of_another_publication_cannot_relabel_the_accepted_reference(self):
        self.accept()
        first = self.load()
        self.store.record_check(dict(PUBLICATION, updated="2019-04-15"))
        availability = self.provider.availability(Event(), force=True)
        self.assertEqual(availability.updated, first.availability.updated)
        self.assertEqual(availability.checked_at, first.availability.checked_at)
        self.assertTrue(availability.cached)

    def test_catalogue_expansion_has_its_own_coverage_and_does_not_reuse_another_catalogue(self):
        self.accept()
        first = self.load()
        expanded = HistoricalComexProvider(self.directory, codes=(CODE, "99887767"))
        try:
            self.assertNotEqual(expanded.history.catalog_key, self.store.catalog_key)
            self.assertFalse(expanded.has_local_period(self.period.start, self.period.end))
            with self.assertRaisesRegex(ComexError, "ainda não cobre"):
                expanded.load(self.period, Event(), lambda *_: None)
            self.assertEqual(self.load().local_revision, first.local_revision)
        finally:
            expanded.close()

    def install_controlled_syncer(self, action):
        provider = self.provider

        class ControlledSynchronizer:
            def __init__(self, store, factory, validate, *, publication_guard, **options):
                self.store, self.factory, self.validate = store, factory, validate
                self.guard = publication_guard

            def synchronize(self, cancel, progress, *, force=False, audit=False):
                return action(self, cancel, progress, force, audit)

        provider._synchronizer_factory = ControlledSynchronizer

    def test_cancelling_a_query_does_not_cancel_the_independent_sync_generation(self):
        accepted = []

        def run(syncer, cancel, _progress, force, audit):
            self.provider.cancel_pending_options()
            with syncer.guard():
                accepted.append((force, audit, cancel.is_set()))
            return {"status": "updated"}

        self.install_controlled_syncer(run)
        self.provider.synchronize(Event(), lambda *_: None, force=True, audit=True)
        self.assertEqual(accepted, [(True, True, False)])

    def test_sync_cancel_or_source_generation_change_blocks_publication(self):
        for invalidation in ("cancel", "source", "close"):
            with self.subTest(invalidation=invalidation):
                if invalidation == "close":
                    self.assertFalse(self.provider._history_closed)
                accepted = []

                def run(syncer, cancel, _progress, _force, _audit):
                    if invalidation == "cancel":
                        cancel.set()
                    elif invalidation == "source":
                        self.provider.connection_changed()
                    else:
                        self.provider.close()
                    with syncer.guard():
                        accepted.append(True)

                self.install_controlled_syncer(run)
                with self.assertRaises(Cancelled):
                    self.provider.synchronize(Event(), lambda *_: None)
                self.assertEqual(accepted, [])

    def test_old_transport_stops_at_its_next_checkpoint_after_a_source_change(self):
        def run(syncer, cancel, _progress, _force, _audit):
            client = syncer.factory(cancel, lambda *_: None)
            self.provider.connection_changed()
            client._check()

        self.install_controlled_syncer(run)
        with self.assertRaises(Cancelled):
            self.provider.synchronize(Event(), lambda *_: None)

    def test_snapshot_and_publication_metadata_are_immutable_for_held_exports(self):
        self.accept()
        snapshot = self.load()
        with self.assertRaises(FrozenInstanceError):
            snapshot.local_revision = "other"
        self.assertIsInstance(snapshot.source_publication, tuple)

    def test_real_synchronizer_and_provider_acquire_once_then_query_offline(self):
        self.provider._sync_options = {"first_month": "2019-03"}
        requests = []

        class Response(io.BytesIO):
            status = 200

            def __init__(self, payload):
                raw = json.dumps(payload).encode()
                super().__init__(raw)
                self.headers = {"Content-Length": str(len(raw))}

        def official_transport(request, **_kwargs):
            path = urlsplit(request.full_url).path
            requests.append((request.method, path))
            if request.method == "GET":
                return Response({"data": {
                    "year": "2019", "monthNumber": "03",
                    "updated": PUBLICATION["municipal_updated" if path.startswith("/cities") else "updated"],
                }})
            return Response({"data": {"list": [
                synthetic_municipal() if path == "/cities" else synthetic_general()
            ]}})

        with patch.object(ApiClient, "_open", side_effect=official_transport):
            outcome = self.provider.synchronize(Event(), lambda *_: None, force=True)
        self.assertEqual(outcome["status"], "updated")
        self.assertEqual(len(requests), 6)
        snapshot = self.load()
        self.assertEqual(snapshot.general_records[0].cif_cents, 10600)
        self.assertEqual(len(requests), 6)
