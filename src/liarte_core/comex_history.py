"""Versioned local Comex history; accepted generations never depend on the network.

Only validated complete runs become visible. Monetary values and weights are
canonical decimal strings inside row JSON, so SQLite never narrows their
precision to signed int64 or binary floating point.
"""

from __future__ import annotations

from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import sqlite3
import time
from itertools import groupby
from uuid import uuid4

from liarte_engine import comexstat_importacoes as contract
from .comex_api import _try_file_lock
from .domain import Period
from .query import checkpoint


SCHEMA = "liarte.comex-history/1"
_CHECKPOINT_LIMIT = 32 * 1024
LOGGER = logging.getLogger("liarte.desktop")


def _NO_CHECK():
    pass


class HistoryError(RuntimeError):
    """The historical data or its local contract could not be accepted."""


class HistoryUnavailable(HistoryError):
    """The requested interval has no complete accepted local coverage."""


class HistoryBusy(HistoryError):
    """Another synchronization owns this installation's writer reservation."""


class HistoryCheckpointError(HistoryError):
    """An optional metadata checkpoint is malformed; accepted history is intact."""


class HistoryStagingError(HistoryError):
    """An unfinished run failed integrity checks; accepted history is intact."""


@dataclass(frozen=True, slots=True)
class HistoryRead:
    general: tuple[dict, ...]
    municipal: tuple[dict, ...]
    local_revision: str
    publication: dict
    acquisition_started_at: str
    general_received_at: str
    municipal_received_at: str
    fetched_at: str
    checked_at: str = ""


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _sha(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _iso(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec="microseconds")


def _timestamp(value):
    if not isinstance(value, str) or len(value) > 80:
        raise HistoryError("Horário de aquisição inválido.")
    try:
        instant = datetime.fromisoformat(value)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError("Timezone ausente")
        return instant.astimezone(timezone.utc).isoformat(timespec="microseconds")
    except (ValueError, TypeError, OverflowError) as exc:
        raise HistoryError("Horário de aquisição inválido.") from exc


def _publication(value):
    fields = ("latest", "updated", "municipal_latest", "municipal_updated")
    if not isinstance(value, dict) or any(not isinstance(value.get(k), str) for k in fields):
        raise HistoryError("Publicação do Comex inválida.")
    result = {key: value[key] for key in fields}
    try:
        for key in ("latest", "municipal_latest"):
            Period("1997-01", result[key])
        for key in ("updated", "municipal_updated"):
            if result[key]:
                result[key] = date.fromisoformat(result[key]).isoformat()
    except (ValueError, TypeError) as exc:
        raise HistoryError("Publicação do Comex inválida.") from exc
    return result


class HistoryStore:
    """One local SQLite file; each reader pins one accepted generation."""

    def __init__(self, path, codes, *, clock=time.time):
        raw_path = os.fspath(path)
        if raw_path.startswith(("//", "\\\\")):
            raise HistoryError("O histórico deve ficar em um disco local.")
        if isinstance(codes, (str, bytes)):
            raise HistoryError("Informe uma sequência de NCMs.")
        try:
            normalized = {contract.normalize_ncm(code) for code in codes}
        except (ValueError, TypeError) as exc:
            raise HistoryError("Catálogo de NCMs inválido.") from exc
        if not normalized or None in normalized or len(normalized) > 200:
            raise HistoryError("Informe entre 1 e 200 NCMs válidos.")
        self.codes = tuple(sorted(normalized))
        self.path, self.clock = Path(path), clock
        identity = {
            "schema": SCHEMA, "codes": self.codes,
            "details": contract.DEFAULT_DETAILS, "metrics": contract.DEFAULT_METRICS,
            "municipal_details": contract.MUNICIPAL_DETAILS,
            "municipal_metrics": contract.MUNICIPAL_METRICS,
            "source": "https://api-comexstat.mdic.gov.br", "flow": "import",
        }
        self.catalog_key = _sha(_json(identity))
        self._codes = set(self.codes)
        self._headings = {code[:4] for code in self.codes}
        self._read_index_ready = False
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self._connection() as db:
                version = db.execute("PRAGMA user_version").fetchone()[0]
                if version not in (0, 1):
                    raise HistoryError("A versão do histórico local não é compatível.")
                if version == 1:
                    existing = db.execute(
                        "SELECT contract FROM catalogs WHERE key=?", (self.catalog_key,)
                    ).fetchone()
                    if existing is not None:
                        if existing["contract"] != _json(identity):
                            raise HistoryError("O contrato do catálogo local não é compatível.")
                        if db.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal":
                            self._read_index_ready = db.execute("SELECT 1 FROM sqlite_master WHERE type='index' AND name='manifest_by_period'").fetchone() is not None
                            # Opening an already initialized reader must not
                            # acquire a writer reservation. Another instance can
                            # be ingesting a large stage while WAL readers use
                            # the last accepted generation.
                            return
                db.execute("PRAGMA journal_mode=WAL")
                db.executescript("""
                    CREATE TABLE IF NOT EXISTS catalogs (
                        key TEXT PRIMARY KEY, contract TEXT NOT NULL,
                        checked_publication TEXT NOT NULL DEFAULT '{}',
                        checked_at TEXT NOT NULL DEFAULT '', last_check_epoch REAL NOT NULL DEFAULT 0,
                        last_full_sync_at TEXT NOT NULL DEFAULT '', last_full_sync_epoch REAL NOT NULL DEFAULT 0,
                        sync_state TEXT NOT NULL DEFAULT 'idle', sync_error TEXT NOT NULL DEFAULT ''
                    );
                    CREATE TABLE IF NOT EXISTS runs (
                        id TEXT PRIMARY KEY, catalog_key TEXT NOT NULL REFERENCES catalogs(key),
                        publication TEXT NOT NULL, publication_key TEXT NOT NULL,
                        start TEXT NOT NULL, end TEXT NOT NULL,
                        status TEXT NOT NULL, created_at TEXT NOT NULL, created_epoch REAL NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS pending_runs ON runs(catalog_key,status,created_epoch);
                    CREATE TABLE IF NOT EXISTS stages (
                        id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                        municipal INTEGER NOT NULL CHECK(municipal IN (0,1)), start TEXT NOT NULL, end TEXT NOT NULL,
                        digest TEXT NOT NULL, received_at TEXT NOT NULL, acquisition_started_at TEXT NOT NULL,
                        UNIQUE(run_id,municipal,start,end)
                    );
                    CREATE TABLE IF NOT EXISTS facts (
                        stage_id TEXT NOT NULL REFERENCES stages(id) ON DELETE CASCADE,
                        position INTEGER NOT NULL, month TEXT NOT NULL, identity TEXT NOT NULL,
                        payload TEXT NOT NULL, digest TEXT NOT NULL,
                        PRIMARY KEY(stage_id,identity)
                    );
                    CREATE INDEX IF NOT EXISTS facts_by_month ON facts(stage_id,month,position);
                    CREATE TABLE IF NOT EXISTS coverage (
                        stage_id TEXT NOT NULL REFERENCES stages(id) ON DELETE CASCADE,
                        month TEXT NOT NULL, rows INTEGER NOT NULL, digest TEXT NOT NULL,
                        PRIMARY KEY(stage_id,month)
                    );
                    CREATE TABLE IF NOT EXISTS generations (
                        id TEXT PRIMARY KEY, catalog_key TEXT NOT NULL REFERENCES catalogs(key),
                        run_id TEXT NOT NULL REFERENCES runs(id), publication TEXT NOT NULL,
                        start TEXT NOT NULL, end TEXT NOT NULL, revision TEXT NOT NULL,
                        fetched_at TEXT NOT NULL, checked_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS manifest (
                        generation_id TEXT NOT NULL REFERENCES generations(id) ON DELETE CASCADE,
                        stage_id TEXT NOT NULL REFERENCES stages(id), municipal INTEGER NOT NULL, month TEXT NOT NULL,
                        PRIMARY KEY(generation_id,municipal,month)
                    );
                    CREATE TABLE IF NOT EXISTS active (
                        catalog_key TEXT PRIMARY KEY REFERENCES catalogs(key),
                        generation_id TEXT NOT NULL REFERENCES generations(id)
                    );
                    CREATE INDEX IF NOT EXISTS manifest_by_period ON manifest(generation_id,month,municipal,stage_id);
                    CREATE TABLE IF NOT EXISTS checkpoints (
                        catalog_key TEXT NOT NULL REFERENCES catalogs(key), key TEXT NOT NULL,
                        payload TEXT NOT NULL, digest TEXT NOT NULL,
                        PRIMARY KEY(catalog_key,key)
                    );
                    PRAGMA user_version=1;
                """)
                db.execute("INSERT OR IGNORE INTO catalogs(key,contract) VALUES(?,?)", (self.catalog_key, _json(identity)))
                db.commit()
                self._read_index_ready = True
        except (OSError, sqlite3.Error) as exc:
            raise HistoryError("Não foi possível preparar o histórico local.") from exc

    def _now(self):
        try:
            value = float(self.clock())
            if not math.isfinite(value):
                raise ValueError("Horário inválido")
            _iso(value)
            return value
        except (ValueError, TypeError, OverflowError, OSError) as exc:
            raise HistoryError("O relógio do histórico retornou um horário inválido.") from exc

    @contextmanager
    def _connection(self):
        db = None
        try:
            db = sqlite3.connect(self.path, timeout=2)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            yield db
        except sqlite3.Error as exc:
            if "locked" in str(exc).lower() or "busy" in str(exc).lower():
                raise HistoryBusy("O histórico está sendo atualizado por outra operação.") from exc
            raise HistoryError("Não foi possível acessar o histórico local.") from exc
        finally:
            if db is not None:
                db.close()

    @contextmanager
    def _transaction(self, *, check=_NO_CHECK, guard=nullcontext):
        context = guard() if callable(guard) else guard
        with context, self._connection() as db:
            check()
            db.execute("BEGIN IMMEDIATE")
            try:
                if not self._read_index_ready:
                    db.execute("CREATE INDEX IF NOT EXISTS manifest_by_period ON manifest(generation_id,month,municipal,stage_id)")
                yield db
                check()
                db.commit()
                self._read_index_ready = True
            except BaseException:
                db.rollback()
                raise

    @contextmanager
    def writer_lock(self, check=_NO_CHECK):
        check()
        lock_path = self.path.with_suffix(self.path.suffix + ".sync.lock")
        try:
            handle = lock_path.open("a+b")
        except OSError as exc:
            raise HistoryError("Não foi possível reservar a atualização local.") from exc
        with handle:
            if not _try_file_lock(handle):
                raise HistoryBusy("Outra atualização do histórico já está em andamento.")
            try:
                check()
                yield
            finally:
                if os.name == "nt":
                    import msvcrt
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _run(self, db, run_id, *, building=False):
        row = db.execute("SELECT * FROM runs WHERE id=? AND catalog_key=?", (run_id, self.catalog_key)).fetchone()
        if row is None or building and row["status"] != "building":
            raise HistoryError("A execução do histórico não está mais disponível para atualização.")
        return row

    def begin_run(self, publication, start, end, *, check=_NO_CHECK):
        publication = _publication(publication)
        try:
            Period(start, end)
        except (ValueError, TypeError) as exc:
            raise HistoryError("Período do histórico inválido.") from exc
        if end > min(publication["latest"], publication["municipal_latest"]):
            raise HistoryError("O período excede a publicação das duas bases.")
        body, key = _json(publication), _sha(_json(publication))
        with self._transaction(check=check) as db:
            existing = db.execute(
                "SELECT id FROM runs WHERE catalog_key=? AND status='building' "
                "AND publication_key=? AND start=? AND end=? ORDER BY created_epoch DESC LIMIT 1",
                (self.catalog_key, key, start, end),
            ).fetchone()
            if existing is not None:
                return existing["id"]
            db.execute("UPDATE runs SET status='abandoned' WHERE catalog_key=? AND status='building'", (self.catalog_key,))
            run_id, now = uuid4().hex, self._now()
            db.execute("INSERT INTO runs VALUES(?,?,?,?,?,?,?,?,?)", (run_id, self.catalog_key, body, key, start, end, "building", _iso(now), now))
            self._cleanup(db)
            return run_id

    def pending_run_info(self):
        with self._connection() as db:
            row = db.execute("SELECT * FROM runs WHERE catalog_key=? AND status='building' ORDER BY created_epoch DESC LIMIT 1", (self.catalog_key,)).fetchone()
            if row is None:
                return None
            return {"run_id": row["id"], "publication": json.loads(row["publication"]), "start": row["start"], "end": row["end"]}

    def abandon_run(self, run_id, *, corrupt=False):
        if type(corrupt) is not bool:
            raise HistoryError("O estado da execução inválida não foi reconhecido.")
        with self._transaction() as db:
            self._run(db, run_id)
            db.execute(
                "UPDATE runs SET status=? WHERE id=? AND status='building'",
                ("corrupt" if corrupt else "abandoned", run_id),
            )

    @staticmethod
    def _checkpoint_key(key):
        if not isinstance(key, str) or not key or len(key) > 200:
            raise HistoryError("Identificação de checkpoint inválida.")

    def get_checkpoint(self, key):
        self._checkpoint_key(key)
        with self._connection() as db:
            row = db.execute("SELECT payload,digest FROM checkpoints WHERE catalog_key=? AND key=?", (self.catalog_key, key)).fetchone()
            if row is None:
                return None
            try:
                if len(row["payload"].encode("utf-8")) > _CHECKPOINT_LIMIT or _sha(row["payload"]) != row["digest"]:
                    raise ValueError("Integridade inválida")
                value = json.loads(row["payload"])
                if not isinstance(value, dict) or _json(value) != row["payload"]:
                    raise ValueError("Formato inválido")
                return value
            except (ValueError, TypeError) as exc:
                raise HistoryCheckpointError("O checkpoint de atualização está inválido.") from exc

    def put_checkpoint(self, key, value):
        self._checkpoint_key(key)
        try:
            if not isinstance(value, dict):
                raise ValueError("Formato inválido")
            body = _json(value)
            if len(body.encode("utf-8")) > _CHECKPOINT_LIMIT:
                raise ValueError("Checkpoint excessivo")
        except (ValueError, TypeError, OverflowError) as exc:
            raise HistoryError("O checkpoint de atualização está inválido.") from exc
        with self._transaction() as db:
            db.execute("INSERT OR REPLACE INTO checkpoints VALUES(?,?,?,?)", (self.catalog_key, key, body, _sha(body)))

    def clear_checkpoint(self, key):
        self._checkpoint_key(key)
        with self._transaction() as db:
            db.execute("DELETE FROM checkpoints WHERE catalog_key=? AND key=?", (self.catalog_key, key))

    def _stage_window(self, run, municipal, start, end):
        if type(municipal) is not bool:
            raise HistoryError("A base da etapa é inválida.")
        try:
            Period(start, end)
        except (ValueError, TypeError) as exc:
            raise HistoryError("Período da etapa inválido.") from exc
        year = start[:4]
        expected = max(run["start"], year + "-01"), min(run["end"], year + "-12")
        if start[:4] != end[:4] or (start, end) != expected or start < run["start"] or end > run["end"]:
            raise HistoryError("A etapa não corresponde à janela anual planejada.")

    def has_stage(self, run_id, municipal, start, end):
        with self._connection() as db:
            run = self._run(db, run_id, building=True)
            self._stage_window(run, municipal, start, end)
            return db.execute("SELECT 1 FROM stages WHERE run_id=? AND municipal=? AND start=? AND end=?", (run_id, int(municipal), start, end)).fetchone() is not None

    def _canonical_row(self, raw, municipal, start, end):
        if not isinstance(raw, dict):
            raise HistoryError("A fonte retornou um registro inválido.")
        row = dict(raw)
        validate = contract.validate_municipal_api_row if municipal else contract.validate_api_row
        identify = contract.municipal_row_identity if municipal else contract.api_row_identity
        metrics = contract.MUNICIPAL_METRICS if municipal else contract.DEFAULT_METRICS
        try:
            validate(row, self._headings if municipal else self._codes, start, end, "histórico local")
            period = contract.row_period(row)
            row["year"], row["monthNumber"] = period[:4], period[5:]
            code_field = "headingCode" if municipal else "coNcm"
            row[code_field] = contract.normalize_heading(row[code_field]) if municipal else contract.normalize_ncm(row[code_field])
            for key in metrics:
                value = contract.validate_metric(row[key], key, "histórico local")
                text = str(value) if key == "metricKG" else f"{value // 100}.{value % 100:02d}"
                if len(text) > 256 and key != "metricKG":
                    # Adding '.00' must not make a valid 255-digit published
                    # integer exceed the transport's numeric text bound.
                    text = text.rstrip("0").rstrip(".")
                if len(text) > 256:
                    digits = str(value)
                    significant = digits.rstrip("0") or "0"
                    exponent = len(digits) - len(significant) - (0 if key == "metricKG" else 2)
                    text = significant + "e" + str(exponent)
                contract.validate_metric(text, key, "histórico local")
                row[key] = text
            # Decimal values can occur in additional API fields. Keep their
            # exact spelling instead of coercing to a binary float.
            row = {key: str(value) if isinstance(value, Decimal) else value for key, value in row.items()}
            body = _json(row)
            identity = _json(identify(row))
        except (contract.ComexStatError, ValueError, TypeError, OverflowError) as exc:
            raise HistoryError("O registro não passou na validação do histórico: " + str(exc)[:250]) from exc
        return period, identity, body

    @staticmethod
    def _month_digest(month, entries):
        digest = hashlib.sha256((month + "\n").encode())
        for identity, body in entries:
            digest.update(identity.encode("utf-8"))
            digest.update(b"\0")
            digest.update(body.encode("utf-8"))
            digest.update(b"\n")
        return digest.hexdigest()

    def write_stage(self, run_id, municipal, start, end, rows, *, check=_NO_CHECK, received_at, acquisition_started_at):
        received_at, acquisition_started_at = _timestamp(received_at), _timestamp(acquisition_started_at)
        if received_at < acquisition_started_at:
            raise HistoryError("O recebimento precede o início da aquisição.")
        with self._connection() as db:
            run = self._run(db, run_id, building=True)
            self._stage_window(run, municipal, start, end)
        check()
        unique = {}
        for position, raw in enumerate(rows):
            if position % 256 == 0:
                check()
            month, identity, body = self._canonical_row(raw, municipal, start, end)
            if identity in unique and unique[identity][1] != body:
                raise HistoryError("A fonte retornou registros duplicados divergentes.")
            unique[identity] = month, body
        months = {month: [] for month in Period(start, end).months}
        for identity, (month, body) in sorted(unique.items()):
            months[month].append((identity, body))
        month_digests = {month: self._month_digest(month, entries) for month, entries in months.items()}
        digest = _sha(_json(month_digests))
        with self._transaction(check=check) as db:
            self._run(db, run_id, building=True)
            existing = db.execute("SELECT digest FROM stages WHERE run_id=? AND municipal=? AND start=? AND end=?", (run_id, int(municipal), start, end)).fetchone()
            if existing is not None:
                if existing["digest"] != digest:
                    raise HistoryError("Uma etapa validada não pode ser substituída na mesma execução.")
                return
            stage_id = uuid4().hex
            db.execute("INSERT INTO stages VALUES(?,?,?,?,?,?,?,?)", (stage_id, run_id, int(municipal), start, end, digest, received_at, acquisition_started_at))
            for month, entries in months.items():
                check()
                db.execute("INSERT INTO coverage VALUES(?,?,?,?)", (stage_id, month, len(entries), month_digests[month]))
                for offset in range(0, len(entries), 256):
                    check()
                    db.executemany("INSERT INTO facts VALUES(?,?,?,?,?,?)", (
                        (stage_id, offset + index, month, identity, body, _sha(body))
                        for index, (identity, body) in enumerate(entries[offset:offset + 256])
                    ))

    def _planned_members(self, db, run, check=_NO_CHECK):
        members = []
        for year in range(int(run["start"][:4]), int(run["end"][:4]) + 1):
            check()
            start, end = max(run["start"], f"{year:04d}-01"), min(run["end"], f"{year:04d}-12")
            for municipal in (0, 1):
                stage = db.execute("SELECT * FROM stages WHERE run_id=? AND municipal=? AND start=? AND end=?", (run["id"], municipal, start, end)).fetchone()
                if stage is None:
                    raise HistoryUnavailable("A carga histórica ainda não terminou nas duas bases.")
                for month in Period(start, end).months:
                    coverage = db.execute("SELECT rows,digest FROM coverage WHERE stage_id=? AND month=?", (stage["id"], month)).fetchone()
                    if coverage is None:
                        raise HistoryStagingError("A etapa não possui cobertura mensal completa.")
                    members.append((stage["id"], municipal, month, coverage["digest"]))
        return members

    def _verify_partitions(self, db, members, check):
        for stage_id, base, month, digest in members:
            check()
            coverage = db.execute("SELECT rows FROM coverage WHERE stage_id=? AND month=?", (stage_id, month)).fetchone()
            if coverage is None:
                raise HistoryStagingError("Uma partição em preparação está ausente.")
            entries = []
            for index, row in enumerate(db.execute("SELECT identity,payload,digest FROM facts WHERE stage_id=? AND month=? ORDER BY position", (stage_id, month))):
                if index % 256 == 0:
                    check()
                if _sha(row["payload"]) != row["digest"]:
                    raise HistoryStagingError("Uma etapa em preparação falhou na verificação de integridade.")
                try:
                    raw = json.loads(row["payload"])
                    _, identity, body = self._canonical_row(raw, bool(base), month, month)
                except (ValueError, TypeError, HistoryError) as exc:
                    raise HistoryStagingError("Uma etapa em preparação está inválida.") from exc
                if identity != row["identity"] or body != row["payload"]:
                    raise HistoryStagingError("Uma etapa em preparação possui identidade divergente.")
                entries.append((identity, body))
            if len(entries) != coverage["rows"] or self._month_digest(month, entries) != digest:
                raise HistoryStagingError("Uma etapa em preparação está incompleta ou foi alterada.")

    def _run_revision(self, run, members):
        return _sha(_json({"catalog": self.catalog_key, "publication": json.loads(run["publication"]), "partitions": sorted((base, month, digest) for _, base, month, digest in members)}))

    @staticmethod
    def _verify_accepted_receipts(generation, members, check):
        try:
            _timestamp(generation["fetched_at"])
            _timestamp(generation["checked_at"])
        except HistoryError as exc:
            raise HistoryStagingError("Os recibos do histórico aceito estão inválidos.") from exc
        for member in members:
            check()
            try:
                received = _timestamp(member["received_at"])
                started = _timestamp(member["acquisition_started_at"])
                if received < started:
                    raise ValueError("O recebimento precede o início da aquisição.")
            except (HistoryError, ValueError) as exc:
                raise HistoryStagingError("Os recibos do histórico aceito estão inválidos.") from exc

    def publish_run(self, run_id, *, check=_NO_CHECK, guard=nullcontext):
        # Validation may inspect a large historical run. It happens outside the
        # provider's presentation lock. Stages are immutable through this API;
        # the guarded transaction rechecks their exact membership/digests.
        with self._connection() as validation:
            validation.execute("BEGIN")
            prepared = self._run(validation, run_id, building=True)
            planned = self._planned_members(validation, prepared, check)
            self._verify_partitions(validation, planned, check)
            previous = self._active(validation)
            identical = None
            if (
                previous is not None
                and all(previous[key] == prepared[key] for key in ("publication", "start", "end"))
                and previous["revision"] == self._run_revision(prepared, planned)
            ):
                try:
                    rows, _ = self._interval(validation, previous, Period(prepared["start"], prepared["end"]))
                    self._verify_accepted_receipts(previous, rows, check)
                    accepted = tuple((row["stage_id"], row["municipal"], row["month"], row["digest"]) for row in rows)
                    # A digest in the manifest is not proof that the accepted
                    # file remains intact. A fresh audit must still repair a
                    # damaged accepted partition with an identical good copy.
                    self._verify_partitions(validation, accepted, check)
                    identical = previous["id"], accepted
                except (HistoryUnavailable, HistoryStagingError):
                    pass
        with self._transaction(check=check, guard=guard) as db:
            run = self._run(db, run_id, building=True)
            members = self._planned_members(db, run, check)
            if members != planned:
                raise HistoryStagingError("As etapas mudaram durante a preparação da publicação.")
            now = self._now()
            revision = self._run_revision(run, members)
            state = db.execute("SELECT checked_publication,checked_at FROM catalogs WHERE key=?", (self.catalog_key,)).fetchone()
            checked_at = state["checked_at"] if state["checked_publication"] == run["publication"] else ""
            if not checked_at:
                raise HistoryUnavailable("A publicação desta execução ainda não foi conferida.")
            current = self._active(db)
            unchanged = False
            if (
                identical is not None and current is not None
                and current["id"] == identical[0] and current["revision"] == revision
                and all(current[key] == run[key] for key in ("publication", "start", "end"))
            ):
                try:
                    rows, _ = self._interval(db, current, Period(run["start"], run["end"]))
                    self._verify_accepted_receipts(current, rows, check)
                    unchanged = tuple((row["stage_id"], row["municipal"], row["month"], row["digest"]) for row in rows) == identical[1]
                except (HistoryUnavailable, HistoryStagingError):
                    pass
            if not unchanged:
                generation = uuid4().hex
                db.execute("INSERT INTO generations VALUES(?,?,?,?,?,?,?,?,?)", (generation, self.catalog_key, run_id, run["publication"], run["start"], run["end"], revision, _iso(now), checked_at))
                db.executemany("INSERT INTO manifest VALUES(?,?,?,?)", ((generation, stage_id, base, month) for stage_id, base, month, _ in members))
                db.execute("INSERT OR REPLACE INTO active VALUES(?,?)", (self.catalog_key, generation))
            db.execute("UPDATE runs SET status='complete' WHERE id=?", (run_id,))
            db.execute("UPDATE catalogs SET last_full_sync_at=?,last_full_sync_epoch=?,sync_state='ready',sync_error='' WHERE key=?", (_iso(now), now, self.catalog_key))
        # Deleting obsolete facts can take substantially longer than switching
        # the manifest. Do it after commit, outside the presentation guard. A
        # cleanup failure never turns an accepted generation into a failed run.
        try:
            with self._transaction() as db:
                self._cleanup(db)
        except Exception as exc:
            LOGGER.warning("O histórico foi publicado; a limpeza local foi adiada (%s).", type(exc).__name__)
        return not unchanged

    def _cleanup(self, db):
        # Keep the active and previous complete generations. Pending stages
        # remain resumable; abandoned runs without an accepted generation go.
        generations = db.execute("SELECT id FROM generations WHERE catalog_key=? ORDER BY rowid DESC", (self.catalog_key,)).fetchall()
        for generation in generations[2:]:
            db.execute("DELETE FROM generations WHERE id=?", (generation["id"],))
        db.execute("DELETE FROM runs WHERE catalog_key=? AND status!='building' AND id NOT IN (SELECT run_id FROM generations)", (self.catalog_key,))

    def record_check(self, publication):
        publication, now = _publication(publication), self._now()
        with self._transaction() as db:
            db.execute("UPDATE catalogs SET checked_publication=?,checked_at=?,last_check_epoch=? WHERE key=?", (_json(publication), _iso(now), now, self.catalog_key))

    def record_state(self, state, error=""):
        if not isinstance(state, str) or not state or len(state) > 80 or not isinstance(error, str):
            raise HistoryError("Estado da atualização inválido.")
        with self._transaction() as db:
            db.execute("UPDATE catalogs SET sync_state=?,sync_error=? WHERE key=?", (state, error[:1000], self.catalog_key))

    def _active(self, db):
        return db.execute("SELECT g.* FROM generations g JOIN active a ON a.generation_id=g.id WHERE a.catalog_key=?", (self.catalog_key,)).fetchone()

    def _interval(self, db, generation, period):
        if not isinstance(period, Period):
            raise HistoryError("Período de consulta inválido.")
        if generation is None or period.start < generation["start"] or period.end > generation["end"]:
            raise HistoryUnavailable("O período ainda não possui cobertura local completa.")
        rows = db.execute("SELECT m.stage_id,m.municipal,m.month,c.rows,c.digest,s.received_at,s.acquisition_started_at FROM manifest m JOIN coverage c ON c.stage_id=m.stage_id AND c.month=m.month JOIN stages s ON s.id=m.stage_id WHERE m.generation_id=? AND m.month>=? AND m.month<=? ORDER BY m.month,m.municipal", (generation["id"], period.start, period.end)).fetchall()
        expected = {(base, month) for base in (0, 1) for month in period.months}
        if {(row["municipal"], row["month"]) for row in rows} != expected:
            raise HistoryUnavailable("O período possui uma lacuna na cobertura local.")
        revision = _sha(_json({"catalog": self.catalog_key, "publication": json.loads(generation["publication"]), "partitions": [(row["municipal"], row["month"], row["digest"]) for row in rows]}))
        return rows, revision

    def read(self, period, cancel):
        checkpoint(cancel)
        with self._connection() as db:
            db.execute("BEGIN")
            generation = self._active(db)
            members, revision = self._interval(db, generation, period)
            bases, starts, receipts = [[], []], [], [[], []]
            # One indexed cursor for the requested interval, including empty
            # partitions through LEFT JOIN. Keep the exact per-month checks.
            cursor = db.execute("""
                SELECT m.month,m.municipal,f.identity,f.payload,f.digest
                FROM manifest m LEFT JOIN facts f
                    ON f.stage_id=m.stage_id AND f.month=m.month
                WHERE m.generation_id=? AND m.month>=? AND m.month<=?
                ORDER BY m.month,m.municipal,f.position
            """, (generation["id"], period.start, period.end))
            groups = iter(groupby(cursor, key=lambda row: (row["month"], row["municipal"])))
            for member in members:
                checkpoint(cancel)
                entries = []
                key, rows = next(groups, (None, ()))
                if key != (member["month"], member["municipal"]):
                    raise HistoryError("Uma partição do histórico está ausente.")
                for index, row in enumerate(rows):
                    if index % 256 == 0:
                        checkpoint(cancel)
                    if row["identity"] is None:
                        continue
                    if _sha(row["payload"]) != row["digest"]:
                        raise HistoryError("Um registro do histórico falhou na verificação de integridade.")
                    try:
                        raw = json.loads(row["payload"])
                    except (ValueError, TypeError) as exc:
                        raise HistoryError("Um registro do histórico está inválido.") from exc
                    _, identity, body = self._canonical_row(raw, bool(member["municipal"]), member["month"], member["month"])
                    if identity != row["identity"] or body != row["payload"]:
                        raise HistoryError("Um registro do histórico possui identidade divergente.")
                    entries.append((identity, body))
                    bases[member["municipal"]].append(raw)
                if len(entries) != member["rows"] or self._month_digest(member["month"], entries) != member["digest"]:
                    raise HistoryError("A partição do histórico está incompleta ou foi alterada.")
                starts.append(member["acquisition_started_at"])
                receipts[member["municipal"]].append(member["received_at"])
            checkpoint(cancel)
            return HistoryRead(tuple(bases[0]), tuple(bases[1]), revision, json.loads(generation["publication"]), min(starts), max(receipts[0]), max(receipts[1]), generation["fetched_at"], generation["checked_at"])

    def period_revision(self, period):
        try:
            with self._connection() as db:
                db.execute("BEGIN")
                return self._interval(db, self._active(db), period)[1]
        except HistoryUnavailable:
            return ""

    def contains(self, period):
        return bool(self.period_revision(period))

    def status(self):
        with self._connection() as db:
            db.execute("BEGIN")
            state = db.execute("SELECT * FROM catalogs WHERE key=?", (self.catalog_key,)).fetchone()
            generation = self._active(db)
            coverage_start = coverage_end = revision = checked_at = ""
            publication, complete_months, complete = {}, 0, False
            if generation is not None:
                period = Period(generation["start"], generation["end"])
                try:
                    self._interval(db, generation, period)
                    coverage_start, coverage_end = period.start, period.end
                    complete_months, complete = len(period.months), True
                except HistoryUnavailable:
                    # Never summarize a gapped or corrupted manifest as a
                    # continuous range by using only MIN/MAX.
                    pass
                revision, publication = generation["revision"], json.loads(generation["publication"])
                checked_at = generation["checked_at"]
            pending = db.execute("SELECT * FROM runs WHERE catalog_key=? AND status='building' ORDER BY created_epoch DESC LIMIT 1", (self.catalog_key,)).fetchone()
            reextract_required = db.execute(
                "SELECT 1 FROM runs WHERE catalog_key=? AND status='corrupt' LIMIT 1",
                (self.catalog_key,),
            ).fetchone() is not None
            staged = planned = 0
            if pending is not None:
                staged = db.execute("SELECT COUNT(*) FROM stages WHERE run_id=?", (pending["id"],)).fetchone()[0]
                planned = 2 * (int(pending["end"][:4]) - int(pending["start"][:4]) + 1)
            return {"catalog_key": self.catalog_key, "local_revision": revision,
                    "coverage_start": coverage_start, "coverage_end": coverage_end,
                    "complete_months": complete_months, "complete": complete,
                    "publication": publication, "checked_at": checked_at,
                    "last_full_sync_at": state["last_full_sync_at"], "last_full_sync_epoch": state["last_full_sync_epoch"],
                    "last_check_epoch": state["last_check_epoch"], "sync_state": state["sync_state"], "sync_error": state["sync_error"],
                    "reextract_required": reextract_required,
                    "staged_stages": staged, "planned_stages": planned,
                    "pending_start": pending["start"] if pending is not None else "",
                    "pending_end": pending["end"] if pending is not None else ""}
