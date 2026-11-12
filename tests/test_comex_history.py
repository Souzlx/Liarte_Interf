"""Durable, exact and transactional history with entirely synthetic records."""

from contextlib import closing, contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from decimal import localcontext
import json
import multiprocessing
import os
from pathlib import Path
import sqlite3
import tempfile
from threading import Event, Thread
import unittest
from unittest.mock import patch

from liarte_core.comex_history import HistoryBusy, HistoryCheckpointError, HistoryError, HistoryStore, HistoryUnavailable
from liarte_core.domain import Period
from liarte_core.query import Cancelled, checkpoint
from liarte_engine.numeric import published_units


CODES = ("29161220", "29161310")
STARTED = "2024-03-01T10:00:00+00:00"
RECEIVED = "2024-03-01T10:01:00+00:00"


def publication(end="2024-02", revision="2024-03-01"):
    return {"latest": end, "updated": revision, "municipal_latest": end, "municipal_updated": revision}


def general(month="2024-01", *, fob=100, ncm=CODES[0], country="País sintético"):
    return {"year": month[:4], "monthNumber": month[5:], "coNcm": ncm,
            "ncm": "Produto sintético", "state": "SP", "country": country,
            "urf": "0000001 - Terminal sintético", "metricFOB": str(fob),
            "metricFreight": "10", "metricInsurance": "1", "metricCIF": str(fob + 11), "metricKG": "20"}


def municipal(month="2024-01", *, fob=80, heading="2916"):
    return {"year": month[:4], "monthNumber": month[5:], "headingCode": heading,
            "heading": "Posição sintética", "state": "SP", "country": "País sintético",
            "noMunMinsgUf": "Município sintético - SP", "metricFOB": str(fob), "metricKG": "10"}


def held_writer(path, ready, release):
    store = HistoryStore(Path(path), CODES)
    with store.writer_lock():
        ready.set()
        if release.wait(15):
            # Model abrupt application termination without running finally.
            os._exit(0)


class _Fixture:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "historico.sqlite3"
        self.now = 1_794_000_000.0
        self.store = HistoryStore(self.path, CODES, clock=lambda: self.now)

    def tearDown(self):
        self.temp.cleanup()

    def fill(self, run_id, start, end, rows=None, cities=None):
        rows = [general(start)] if rows is None else rows
        cities = [municipal(start)] if cities is None else cities
        for year in range(int(start[:4]), int(end[:4]) + 1):
            first, last = max(start, f"{year}-01"), min(end, f"{year}-12")
            for kind, values in ((False, rows), (True, cities)):
                selected = [row for row in values if first <= row["year"] + "-" + row["monthNumber"] <= last]
                self.store.write_stage(run_id, kind, first, last, selected,
                                       received_at=RECEIVED, acquisition_started_at=STARTED)

    def accept(self, *, start="2024-01", end="2024-02", rows=None, cities=None, pub=None):
        pub = pub or publication(end)
        run_id = self.store.begin_run(pub, start, end)
        self.fill(run_id, start, end, rows, cities)
        self.store.record_check(pub)
        self.store.publish_run(run_id)
        return run_id


class HistoryStoreTests(_Fixture, unittest.TestCase):
    def test_empty_store_is_unavailable_without_claiming_zero_or_publication(self):
        period = Period("2024-01", "2024-01")
        self.assertFalse(self.store.contains(period))
        self.assertEqual(self.store.period_revision(period), "")
        with self.assertRaises(HistoryUnavailable):
            self.store.read(period, Event())
        status = self.store.status()
        self.assertFalse(status["complete"])
        self.assertEqual(status["complete_months"], 0)
        self.assertEqual(status["publication"], {})
        self.assertEqual(status["coverage_start"], "")

    def test_catalog_normalization_is_order_independent_and_expansion_is_isolated(self):
        same = HistoryStore(self.path, [29161310, "29161220", "29161220"])
        self.assertEqual(same.codes, CODES)
        self.assertEqual(same.catalog_key, self.store.catalog_key)
        self.accept()
        expanded = HistoryStore(self.path, (*CODES, "29011000"))
        self.assertNotEqual(expanded.catalog_key, self.store.catalog_key)
        self.assertFalse(expanded.contains(Period("2024-01", "2024-01")))
        self.assertTrue(self.store.contains(Period("2024-01", "2024-01")))

    def test_invalid_catalog_and_network_location_are_rejected(self):
        for codes in ([], "29161220", [None], [True], ["123"], ["abcdefgh"]):
            with self.subTest(codes=codes), self.assertRaises(HistoryError):
                HistoryStore(self.path, codes)
        with self.assertRaises(HistoryError):
            HistoryStore("//servidor/rede/historico.sqlite3", CODES)

    def test_staging_survives_restart_without_becoming_queryable(self):
        run = self.store.begin_run(publication(), "2024-01", "2024-02")
        self.store.write_stage(run, False, "2024-01", "2024-02", [general()], received_at=RECEIVED, acquisition_started_at=STARTED)
        reopened = HistoryStore(self.path, CODES)
        self.assertEqual(reopened.begin_run(publication(), "2024-01", "2024-02"), run)
        self.assertTrue(reopened.has_stage(run, False, "2024-01", "2024-02"))
        self.assertFalse(reopened.has_stage(run, True, "2024-01", "2024-02"))
        self.assertFalse(reopened.contains(Period("2024-01", "2024-02")))
        self.assertEqual(reopened.pending_run_info()["run_id"], run)
        self.assertEqual(reopened.status()["staged_stages"], 1)
        self.assertEqual(reopened.status()["planned_stages"], 2)

    def test_completed_audit_is_not_reused_for_a_fresh_run(self):
        first = self.accept()
        second = self.store.begin_run(publication(), "2024-01", "2024-02")
        self.assertNotEqual(first, second)
        self.assertFalse(self.store.has_stage(second, False, "2024-01", "2024-02"))
        self.assertTrue(self.store.contains(Period("2024-01", "2024-02")))

    def test_identical_verified_audit_preserves_the_accepted_generation_and_receipts(self):
        self.accept()
        before = self.store.read(Period("2024-01", "2024-02"), Event())
        with closing(sqlite3.connect(self.path)) as db:
            generation = db.execute("SELECT generation_id FROM active").fetchone()[0]
            counts = [db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                      for table in ("generations", "runs", "stages", "facts", "manifest")]
        self.now += 90000
        run = self.store.begin_run(publication(), "2024-01", "2024-02")
        self.fill(run, "2024-01", "2024-02")
        self.store.record_check(publication())
        self.assertFalse(self.store.publish_run(run))
        self.assertEqual(self.store.read(Period("2024-01", "2024-02"), Event()), before)
        self.assertEqual(self.store.status()["last_full_sync_epoch"], self.now)
        self.assertIsNone(self.store.pending_run_info())
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT generation_id FROM active").fetchone()[0], generation)
            self.assertEqual([db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                              for table in ("generations", "runs", "stages", "facts", "manifest")], counts)

    def test_identical_fresh_data_repairs_corrupt_accepted_content_or_provenance(self):
        self.accept()
        expected = self.store.read(Period("2024-01", "2024-02"), Event())
        for damage in ("fact", "manifest", "plan", "publication"):
            with self.subTest(damage=damage):
                with closing(sqlite3.connect(self.path)) as db, db:
                    generation = db.execute("SELECT generation_id FROM active").fetchone()[0]
                    if damage == "fact":
                        db.execute("UPDATE facts SET payload='damaged' WHERE stage_id IN (SELECT stage_id FROM manifest WHERE generation_id=?)", (generation,))
                    elif damage == "manifest":
                        db.execute("DELETE FROM manifest WHERE generation_id=? AND municipal=1 AND month='2024-02'", (generation,))
                    elif damage == "plan":
                        db.execute("UPDATE generations SET start='2023-12' WHERE id=?", (generation,))
                    else:
                        db.execute("UPDATE generations SET publication=? WHERE id=?", (json.dumps(publication(revision="2024-03-02")), generation))
                self.now += 10
                run = self.store.begin_run(publication(), "2024-01", "2024-02")
                self.fill(run, "2024-01", "2024-02")
                self.store.record_check(publication())
                self.assertTrue(self.store.publish_run(run))
                actual = self.store.read(Period("2024-01", "2024-02"), Event())
                self.assertEqual((actual.general, actual.municipal), (expected.general, expected.municipal))
                self.assertEqual(actual.local_revision, expected.local_revision)
                self.assertEqual(actual.publication, expected.publication)
                self.assertTrue(self.store.status()["complete"])
                with closing(sqlite3.connect(self.path)) as db:
                    self.assertNotEqual(db.execute("SELECT generation_id FROM active").fetchone()[0], generation)

    def test_identical_fresh_audit_repairs_invalid_generation_and_stage_receipts(self):
        self.accept()
        expected = self.store.read(Period("2024-01", "2024-02"), Event())
        damage = [
            (table, field, value)
            for table, fields in (("generations", ("fetched_at", "checked_at")),
                                  ("stages", ("received_at", "acquisition_started_at")))
            for field in fields for value in ("invalid", "2024-03-01T10:01:00")
        ]
        damage.append(("stages", "acquisition_started_at", "2024-03-01T11:00:00+00:00"))
        for table, field, value in damage:
            with self.subTest(table=table, field=field, value=value):
                with closing(sqlite3.connect(self.path)) as db, db:
                    generation = db.execute("SELECT generation_id FROM active").fetchone()[0]
                    if table == "generations":
                        db.execute(f"UPDATE generations SET {field}=? WHERE id=?", (value, generation))
                    else:
                        db.execute(f"UPDATE stages SET {field}=? WHERE id IN (SELECT stage_id FROM manifest WHERE generation_id=?)", (value, generation))
                self.now += 10
                run = self.store.begin_run(publication(), "2024-01", "2024-02")
                self.fill(run, "2024-01", "2024-02")
                self.store.record_check(publication())
                self.assertTrue(self.store.publish_run(run))
                actual = self.store.read(Period("2024-01", "2024-02"), Event())
                self.assertEqual((actual.general, actual.municipal, actual.local_revision),
                                 (expected.general, expected.municipal, expected.local_revision))
                self.assertEqual(datetime.fromisoformat(actual.fetched_at), datetime.fromtimestamp(self.now, timezone.utc))
                self.assertEqual(datetime.fromisoformat(actual.checked_at), datetime.fromtimestamp(self.now, timezone.utc))
                self.assertEqual(datetime.fromisoformat(actual.acquisition_started_at), datetime.fromisoformat(STARTED))
                self.assertEqual(datetime.fromisoformat(actual.general_received_at), datetime.fromisoformat(RECEIVED))
                self.assertEqual(datetime.fromisoformat(actual.municipal_received_at), datetime.fromisoformat(RECEIVED))
                with closing(sqlite3.connect(self.path)) as db:
                    self.assertNotEqual(db.execute("SELECT generation_id FROM active").fetchone()[0], generation)

    def test_new_publication_or_plan_abandons_incompatible_staging_only(self):
        old = self.accept()
        active = self.store.status()["local_revision"]
        pending = self.store.begin_run(publication(), "2024-01", "2024-02")
        newer = self.store.begin_run(publication(revision="2024-03-02"), "2024-01", "2024-02")
        self.assertNotIn(newer, (old, pending))
        with self.assertRaises(HistoryError):
            self.store.has_stage(pending, False, "2024-01", "2024-02")
        self.assertEqual(self.store.status()["local_revision"], active)
        changed_plan = self.store.begin_run(publication(revision="2024-03-02"), "2024-02", "2024-02")
        self.assertNotEqual(changed_plan, newer)

    def test_abandoned_run_cannot_publish_and_does_not_erase_accepted_data(self):
        self.accept()
        revision = self.store.status()["local_revision"]
        run = self.store.begin_run(publication(), "2024-01", "2024-02")
        self.fill(run, "2024-01", "2024-02")
        self.store.abandon_run(run)
        self.assertIsNone(self.store.pending_run_info())
        with self.assertRaises(HistoryError):
            self.store.publish_run(run)
        self.assertEqual(self.store.status()["local_revision"], revision)

    def test_general_only_never_publishes_as_a_complete_history(self):
        run = self.store.begin_run(publication(), "2024-01", "2024-02")
        self.store.write_stage(run, False, "2024-01", "2024-02", [general()], received_at=RECEIVED, acquisition_started_at=STARTED)
        with self.assertRaises(HistoryUnavailable):
            self.store.publish_run(run)
        self.assertFalse(self.store.status()["complete"])

    def test_empty_validated_months_are_distinct_from_uncovered_intervals(self):
        self.accept(rows=[], cities=[])
        result = self.store.read(Period("2024-01", "2024-02"), Event())
        self.assertEqual(result.general, ())
        self.assertEqual(result.municipal, ())
        self.assertTrue(result.local_revision)
        self.assertEqual(self.store.status()["complete_months"], 2)
        self.assertFalse(self.store.contains(Period("2023-12", "2024-02")))
        self.assertFalse(self.store.contains(Period("2024-01", "2024-03")))

    def test_interval_reads_do_not_load_other_months_or_years(self):
        self.accept(start="2023-12", end="2024-02", rows=[general("2023-12"), general("2024-01"), general("2024-02")], cities=[municipal("2023-12"), municipal("2024-01"), municipal("2024-02")])
        result = self.store.read(Period("2024-01", "2024-01"), Event())
        self.assertEqual(len(result.general), 1)
        self.assertEqual(len(result.municipal), 1)
        self.assertEqual(result.general[0]["monthNumber"], "01")
        with closing(sqlite3.connect(self.path)) as db, db:
            other = db.execute("SELECT stage_id,identity FROM facts WHERE month='2023-12' LIMIT 1").fetchone()
            db.execute("UPDATE facts SET payload='corrompido' WHERE stage_id=? AND identity=?", other)
        # Integrity checks are limited to the interval, never a scan of decades.
        self.assertEqual(len(self.store.read(Period("2024-01", "2024-01"), Event()).general), 1)

    def test_big_integers_and_cents_are_exact_without_float_or_int64(self):
        value = 10**65 + 123
        row = general(fob=value)
        row["metricKG"] = str(10**70 + 7)
        with localcontext() as context:
            context.prec = 3
            self.accept(rows=[row])
            read = self.store.read(Period("2024-01", "2024-01"), Event()).general[0]
        self.assertEqual(published_units(read["metricFOB"], places=2), value * 100)
        self.assertEqual(published_units(read["metricCIF"], places=2), (value + 11) * 100)
        self.assertEqual(published_units(read["metricKG"]), 10**70 + 7)
        self.assertIsInstance(read["metricCIF"], str)
        with closing(sqlite3.connect(self.path)) as db, db:
            self.assertEqual(db.execute("SELECT DISTINCT typeof(payload) FROM facts").fetchall(), [("text",)])

    def test_fractional_cents_and_large_scientific_notation_keep_exact_contract(self):
        penny = general()
        penny.update(metricFOB="0.01", metricFreight="0.02", metricInsurance="0.03", metricCIF="0.06")
        huge = general(country="Outra origem sintética")
        huge.update(metricFOB="1e128", metricFreight="0", metricInsurance="0", metricCIF="1e128", metricKG="1e128")
        boundary = general(country="Limite numérico sintético")
        boundary_value = str(10**254 + 1)
        boundary.update(metricFOB=boundary_value, metricFreight="0", metricInsurance="0", metricCIF=boundary_value)
        self.accept(rows=[penny, huge, boundary])
        data = self.store.read(Period("2024-01", "2024-01"), Event()).general
        by_country = {row["country"]: row for row in data}
        self.assertEqual(published_units(by_country["País sintético"]["metricCIF"], places=2), 6)
        self.assertEqual(published_units(by_country["Outra origem sintética"]["metricCIF"], places=2), 10**130)
        self.assertEqual(published_units(by_country["Limite numérico sintético"]["metricCIF"], places=2), (10**254 + 1) * 100)

    def test_equal_duplicates_are_collapsed_but_conflicting_duplicates_abort(self):
        run = self.store.begin_run(publication(), "2024-01", "2024-02")
        self.store.write_stage(run, False, "2024-01", "2024-02", [general(), deepcopy(general())], received_at=RECEIVED, acquisition_started_at=STARTED)
        self.assertTrue(self.store.has_stage(run, False, "2024-01", "2024-02"))
        with self.assertRaises(HistoryError):
            self.store.write_stage(run, True, "2024-01", "2024-02", [municipal(), municipal(fob=81)], received_at=RECEIVED, acquisition_started_at=STARTED)
        self.assertFalse(self.store.has_stage(run, True, "2024-01", "2024-02"))
        self.store.write_stage(run, True, "2024-01", "2024-02", [municipal()], received_at=RECEIVED, acquisition_started_at=STARTED)
        self.store.record_check(publication())
        self.store.publish_run(run)
        self.assertEqual(len(self.store.read(Period("2024-01", "2024-02"), Event()).general), 1)

    def test_repeated_same_stage_is_idempotent_and_changed_stage_requires_a_new_run(self):
        run = self.store.begin_run(publication(), "2024-01", "2024-02")
        for _ in range(2):
            self.store.write_stage(run, False, "2024-01", "2024-02", [general()], received_at=RECEIVED, acquisition_started_at=STARTED)
        with self.assertRaises(HistoryError):
            self.store.write_stage(run, False, "2024-01", "2024-02", [general(fob=101)], received_at=RECEIVED, acquisition_started_at=STARTED)
        self.assertEqual(self.store.status()["staged_stages"], 1)

    def test_malformed_source_rows_never_create_stage_coverage(self):
        run = self.store.begin_run(publication(), "2024-01", "2024-02")
        malformed = [general(ncm="29011000"), general("2023-12")]
        for key, value in (("metricKG", "0.1"), ("metricFOB", True), ("metricCIF", "999"), ("metricInsurance", None), ("country", "")):
            row = general()
            row[key] = value
            malformed.append(row)
        for row in malformed:
            with self.subTest(row=row), self.assertRaises(HistoryError):
                self.store.write_stage(run, False, "2024-01", "2024-02", [row], received_at=RECEIVED, acquisition_started_at=STARTED)
        self.assertFalse(self.store.has_stage(run, False, "2024-01", "2024-02"))

    def test_invalid_annual_window_base_and_acquisition_times_are_rejected(self):
        run = self.store.begin_run(publication(), "2024-01", "2024-02")
        for args in ((False, "2024-01", "2024-01"), (False, "2023-12", "2024-02"), (1, "2024-01", "2024-02")):
            with self.subTest(args=args), self.assertRaises(HistoryError):
                self.store.write_stage(run, *args, [], received_at=RECEIVED, acquisition_started_at=STARTED)
        for instant in ("2024-03-01T10:01:00", "invalid", ""):
            with self.subTest(instant=instant), self.assertRaises(HistoryError):
                self.store.write_stage(run, False, "2024-01", "2024-02", [], received_at=instant, acquisition_started_at=STARTED)
        with self.assertRaises(HistoryError):
            self.store.write_stage(run, False, "2024-01", "2024-02", [], received_at=STARTED, acquisition_started_at=RECEIVED)

    def test_historical_correction_and_deletion_replace_the_whole_partition(self):
        self.accept(rows=[general(), general(country="Origem removida")])
        before = self.store.read(Period("2024-01", "2024-01"), Event())
        self.now += 10
        self.accept(rows=[general(fob=250)], pub=publication(revision="2024-03-02"))
        after = self.store.read(Period("2024-01", "2024-01"), Event())
        self.assertEqual(len(after.general), 1)
        self.assertEqual(published_units(after.general[0]["metricFOB"], places=2), 25000)
        self.assertNotEqual(after.local_revision, before.local_revision)
        self.assertEqual(after.publication["updated"], "2024-03-02")

    def test_unrelated_month_updates_leave_selected_period_revision_unchanged(self):
        self.accept(rows=[general(), general("2024-02")])
        january = self.store.period_revision(Period("2024-01", "2024-01"))
        february = self.store.period_revision(Period("2024-02", "2024-02"))
        self.now += 10
        self.accept(rows=[general(), general("2024-02", fob=300)])
        self.assertEqual(self.store.period_revision(Period("2024-01", "2024-01")), january)
        self.assertNotEqual(self.store.period_revision(Period("2024-02", "2024-02")), february)

    def test_metadata_checks_do_not_relabel_the_accepted_generation(self):
        self.accept()
        old = self.store.status()
        self.now += 100
        self.store.record_check(publication(revision="2024-03-02"))
        status = self.store.status()
        self.assertEqual(status["publication"], old["publication"])
        self.assertEqual(status["checked_at"], old["checked_at"])
        self.assertEqual(status["last_full_sync_at"], old["last_full_sync_at"])
        self.assertGreater(status["last_check_epoch"], old["last_check_epoch"])
        self.assertEqual(self.store.read(Period("2024-01", "2024-01"), Event()).checked_at, old["checked_at"])

    def test_acquisition_timestamps_remain_source_receipts_after_offline_reopen(self):
        self.accept()
        reopened = HistoryStore(self.path, CODES)
        result = reopened.read(Period("2024-01", "2024-01"), Event())
        self.assertEqual(result.acquisition_started_at, "2024-03-01T10:00:00.000000+00:00")
        self.assertEqual(result.general_received_at, "2024-03-01T10:01:00.000000+00:00")
        self.assertEqual(result.municipal_received_at, result.general_received_at)
        self.assertNotEqual(result.fetched_at, result.general_received_at)

    def test_checkpoints_are_durable_isolated_bounded_and_not_query_results(self):
        value = {"general": {"latest": "2024-02", "received_epoch": 100.25}}
        self.store.put_checkpoint("metadata:initial", value)
        value["general"]["latest"] = "changed outside"
        reopened = HistoryStore(self.path, CODES)
        self.assertEqual(reopened.get_checkpoint("metadata:initial")["general"]["latest"], "2024-02")
        other = HistoryStore(self.path, (CODES[0],))
        self.assertIsNone(other.get_checkpoint("metadata:initial"))
        self.assertFalse(reopened.status()["complete"])
        for bad in ([1], {"number": float("nan")}, {"payload": "x" * 40000}):
            with self.subTest(bad=type(bad)), self.assertRaises(HistoryError):
                self.store.put_checkpoint("bad", bad)
        self.store.clear_checkpoint("metadata:initial")
        self.assertIsNone(reopened.get_checkpoint("metadata:initial"))

    def test_corrupted_checkpoint_and_fact_are_rejected(self):
        self.store.put_checkpoint("metadata:initial", {"test": 1})
        self.accept()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE checkpoints SET payload='{}'")
            db.execute("UPDATE facts SET payload='{}' WHERE rowid=(SELECT MIN(rowid) FROM facts)")
        with self.assertRaises(HistoryCheckpointError):
            self.store.get_checkpoint("metadata:initial")
        with self.assertRaises(HistoryError):
            self.store.read(Period("2024-01", "2024-01"), Event())

    def test_missing_partition_is_not_hidden_by_minimum_and_maximum_dates(self):
        self.accept()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("DELETE FROM coverage WHERE month='2024-01' AND stage_id IN (SELECT id FROM stages WHERE municipal=1)")
        self.assertFalse(self.store.contains(Period("2024-01", "2024-02")))
        self.assertFalse(self.store.status()["complete"])
        self.assertEqual(self.store.status()["coverage_start"], "")
        with self.assertRaises(HistoryUnavailable):
            self.store.read(Period("2024-01", "2024-02"), Event())

    def test_corrupted_staging_cannot_replace_an_accepted_generation(self):
        self.accept()
        active = self.store.status()["local_revision"]
        run = self.store.begin_run(publication(), "2024-01", "2024-02")
        self.fill(run, "2024-01", "2024-02", rows=[general(fob=300)])
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("DELETE FROM facts WHERE stage_id IN (SELECT id FROM stages WHERE run_id=? AND municipal=0)", (run,))
        with self.assertRaises(HistoryError):
            self.store.publish_run(run)
        self.assertEqual(self.store.status()["local_revision"], active)

    def test_missing_or_different_publication_check_never_activates_a_run(self):
        run = self.store.begin_run(publication(), "2024-01", "2024-02")
        self.fill(run, "2024-01", "2024-02")
        with self.assertRaises(HistoryUnavailable):
            self.store.publish_run(run)
        self.store.record_check(publication(revision="2024-03-02"))
        with self.assertRaises(HistoryUnavailable):
            self.store.publish_run(run)
        self.assertFalse(self.store.status()["complete"])
        self.store.record_check(publication())
        self.store.publish_run(run)
        self.assertTrue(self.store.status()["complete"])

    def test_stage_write_cancellation_rolls_back_and_preserves_accepted_base(self):
        self.accept()
        previous = self.store.status()["local_revision"]
        run = self.store.begin_run(publication(), "2024-01", "2024-02")
        calls = 0
        def check():
            nonlocal calls
            calls += 1
            if calls >= 5:
                raise Cancelled()
        with self.assertRaises(Cancelled):
            self.store.write_stage(run, False, "2024-01", "2024-02", [general()], check=check, received_at=RECEIVED, acquisition_started_at=STARTED)
        self.assertFalse(self.store.has_stage(run, False, "2024-01", "2024-02"))
        self.assertEqual(self.store.status()["local_revision"], previous)

    def test_cancelled_reads_do_not_mutate_history(self):
        self.accept()
        cancel = Event()
        cancel.set()
        with self.assertRaises(Cancelled):
            self.store.read(Period("2024-01", "2024-01"), cancel)
        self.assertTrue(self.store.status()["complete"])

    def test_unsupported_schema_preserves_original_database(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("PRAGMA user_version=99")
        with self.assertRaises(HistoryError):
            HistoryStore(self.path, CODES)
        with closing(sqlite3.connect(self.path)) as db, db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 99)

    def test_old_generations_are_bounded_without_deleting_other_catalogs(self):
        for value in (100, 200, 300, 400):
            self.accept(rows=[general(fob=value)])
            self.now += 1
        with closing(sqlite3.connect(self.path)) as db, db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM generations").fetchone()[0], 2)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM runs").fetchone()[0], 2)
        self.assertEqual(published_units(self.store.read(Period("2024-01", "2024-01"), Event()).general[0]["metricFOB"], places=2), 40000)


class HistoryStoreConcurrencyTests(_Fixture, unittest.TestCase):
    def test_reopening_an_initialized_reader_does_not_require_the_ingestion_writer_lock(self):
        self.accept()
        period = Period("2024-01", "2024-02")
        accepted = self.store.read(period, Event())
        with closing(sqlite3.connect(self.path)) as writer, writer:
            writer.execute("BEGIN IMMEDIATE")
            reopened = HistoryStore(self.path, CODES, clock=lambda: self.now)
            self.assertEqual(reopened.read(period, Event()), accepted)
            self.assertTrue(reopened.status()["complete"])
            writer.rollback()

    def test_writer_reservation_is_exclusive_but_never_blocks_readers(self):
        self.accept()
        second = HistoryStore(self.path, CODES)
        results = []
        with self.store.writer_lock():
            with self.assertRaises(HistoryBusy):
                with second.writer_lock():
                    self.fail("Duplicate writer")
            thread = Thread(target=lambda: results.append(second.read(Period("2024-01", "2024-01"), Event())))
            thread.start()
            thread.join(5)
            self.assertFalse(thread.is_alive())
        self.assertEqual(len(results), 1)
        with second.writer_lock():
            pass

    def test_process_termination_releases_the_native_writer_lock(self):
        context = multiprocessing.get_context("spawn")
        ready, release = context.Event(), context.Event()
        process = context.Process(target=held_writer, args=(str(self.path), ready, release))
        process.start()
        try:
            self.assertTrue(ready.wait(10), "writer did not start")
            with self.assertRaises(HistoryBusy):
                with self.store.writer_lock():
                    self.fail("Duplicate process writer")
            release.set()
            process.join(10)
            self.assertEqual(process.exitcode, 0)
            with self.store.writer_lock():
                pass
        finally:
            release.set()
            if process.is_alive():
                process.terminate()
            process.join(10)

    def test_publication_guard_covers_commit_and_rejection_keeps_the_old_generation(self):
        self.accept()
        old = self.store.status()["local_revision"]
        run = self.store.begin_run(publication(), "2024-01", "2024-02")
        self.fill(run, "2024-01", "2024-02", rows=[general(fob=250)])
        held, checks = False, 0
        @contextmanager
        def guard():
            nonlocal held
            self.assertFalse(held)
            held = True
            try:
                yield
            finally:
                held = False
        def reject_before_commit():
            nonlocal checks
            if held:
                checks += 1
                if checks >= 3:
                    raise Cancelled()
        with self.assertRaises(Cancelled):
            self.store.publish_run(run, check=reject_before_commit, guard=guard)
        self.assertFalse(held)
        self.assertEqual(self.store.status()["local_revision"], old)
        commits = []
        original_connection = self.store._connection
        class ConnectionProxy:
            def __init__(self, wrapped):
                self.wrapped = wrapped
            def __getattr__(self, key):
                return getattr(self.wrapped, key)
            def commit(self):
                commits.append(held)
                self.wrapped.commit()
        @contextmanager
        def instrumented_connection():
            with original_connection() as db:
                yield ConnectionProxy(db)
        with patch.object(self.store, "_connection", instrumented_connection):
            self.store.publish_run(run, guard=guard)
        self.assertEqual(commits, [True, False])
        self.assertNotEqual(self.store.status()["local_revision"], old)

    def test_cleanup_runs_after_commit_without_the_presentation_guard(self):
        self.accept()
        run = self.store.begin_run(publication(), "2024-01", "2024-02")
        self.fill(run, "2024-01", "2024-02", rows=[general(fob=250)])
        held = False
        @contextmanager
        def guard():
            nonlocal held
            held = True
            try:
                yield
            finally:
                held = False
        def failing_cleanup(db):
            self.assertFalse(held)
            active = db.execute("SELECT run_id FROM generations g JOIN active a ON a.generation_id=g.id WHERE a.catalog_key=?", (self.store.catalog_key,)).fetchone()
            self.assertEqual(active[0], run)
            raise HistoryError("synthetic cleanup failure")
        with patch.object(self.store, "_cleanup", side_effect=failing_cleanup), self.assertLogs("liarte.desktop", level="WARNING") as logs:
            self.store.publish_run(run, guard=guard)
        self.assertIn("limpeza local foi adiada", " ".join(logs.output))
        self.assertEqual(self.store.status()["sync_state"], "ready")
        self.assertIsNone(self.store.pending_run_info())
        result = self.store.read(Period("2024-01", "2024-01"), Event())
        self.assertEqual(published_units(result.general[0]["metricFOB"], places=2), 25000)

    def test_a_reader_keeps_one_generation_while_another_writer_commits(self):
        self.accept(rows=[general(fob=100)], cities=[municipal(fob=80)])
        reader = HistoryStore(self.path, CODES)
        run = self.store.begin_run(publication(revision="2024-03-02"), "2024-01", "2024-02")
        self.fill(run, "2024-01", "2024-02", rows=[general(fob=250)], cities=[municipal(fob=200)])
        self.store.record_check(publication(revision="2024-03-02"))
        original_interval = reader._interval
        published = False
        def publish_between_snapshot_and_rows(db, generation, period):
            nonlocal published
            interval = original_interval(db, generation, period)
            if not published:
                published = True
                self.store.publish_run(run)
                # The third generation's cleanup removes the first manifest
                # and facts while this reader still sees their WAL snapshot.
                self.accept(rows=[general(fob=900)], cities=[municipal(fob=700)], pub=publication(revision="2024-03-03"))
            return interval
        with patch.object(reader, "_interval", side_effect=publish_between_snapshot_and_rows):
            result = reader.read(Period("2024-01", "2024-01"), Event())
        self.assertEqual(published_units(result.general[0]["metricFOB"], places=2), 10000)
        self.assertEqual(published_units(result.municipal[0]["metricFOB"], places=2), 8000)
        latest = reader.read(Period("2024-01", "2024-01"), Event())
        self.assertEqual(published_units(latest.general[0]["metricFOB"], places=2), 90000)
        self.assertEqual(published_units(latest.municipal[0]["metricFOB"], places=2), 70000)

    def test_guard_cancellation_invalidates_no_data_before_the_transaction(self):
        self.accept()
        old = self.store.status()["local_revision"]
        run = self.store.begin_run(publication(), "2024-01", "2024-02")
        self.fill(run, "2024-01", "2024-02")
        cancel = Event()
        @contextmanager
        def guard():
            cancel.set()
            checkpoint(cancel)
            yield
        with self.assertRaises(Cancelled):
            self.store.publish_run(run, check=lambda: checkpoint(cancel), guard=guard)
        self.assertEqual(self.store.status()["local_revision"], old)
