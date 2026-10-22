"""Coordenação entre processos no mesmo host. A rede usa a Central, nunca um SQLite em SMB."""

from __future__ import annotations

import math
import sqlite3
import time
from contextlib import closing, contextmanager
from pathlib import Path
from uuid import uuid4


class AccessError(RuntimeError):
    pass


class RequestLease:
    def __init__(self, owner, token, interval):
        self.owner, self.token, self.interval = owner, token, interval
        self.active = True

    def defer(self, seconds):
        self.owner.defer(seconds)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.release()

    def release(self):
        if not self.active:
            return
        self.active = False
        try:
            with self.owner.connect() as db:
                db.execute(
                    "UPDATE access SET owner='', lease_until=0, next_at=MAX(next_at, ?) "
                    "WHERE id=1 AND owner=?",
                    (self.owner.clock() + self.interval, self.token),
                )
        except sqlite3.Error as exc:
            raise AccessError(
                "Não foi possível liberar a fila local de consultas."
            ) from exc


class RequestCoordinator:
    @staticmethod
    def peek(path: Path):
        """Leitura curta para a UI: não cria banco nem aguarda travas de escrita."""
        try:
            with closing(
                sqlite3.connect(
                    Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=0
                )
            ) as db:
                row = db.execute(
                    "SELECT cooldown_until FROM access WHERE id=1"
                ).fetchone()
            if row is not None and math.isfinite(row[0]):
                return {"pause_seconds": max(0, math.ceil(row[0] - time.time()))}
        except (OSError, sqlite3.Error, TypeError, ValueError):
            pass
        return {"pause_seconds": 0}

    def __init__(self, path: Path, *, clock=time.time):
        self.path, self.clock = Path(path), clock
        if str(self.path).startswith(("\\\\", "//")):
            raise AccessError(
                "Use a Central de Consultas para acesso em rede; a fila local precisa ficar neste computador."
            )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self.connect() as db:
                db.execute("PRAGMA journal_mode=WAL")
                db.execute(
                    "CREATE TABLE IF NOT EXISTS access (id INTEGER PRIMARY KEY CHECK(id=1), "
                    "owner TEXT NOT NULL, lease_until REAL NOT NULL, "
                    "next_at REAL NOT NULL, cooldown_until REAL NOT NULL)"
                )
                db.execute("INSERT OR IGNORE INTO access VALUES(1, '', 0, 0, 0)")
        except sqlite3.Error as exc:
            raise AccessError(
                "Não foi possível abrir a fila local de consultas. Consulte o diagnóstico."
            ) from exc

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=0.25)
        try:
            with db:
                yield db
        finally:
            db.close()

    def defer(self, seconds):
        if (
            not isinstance(seconds, (int, float))
            or not math.isfinite(seconds)
            or seconds < 0
        ):
            raise ValueError("Intervalo de espera inválido.")
        try:
            with self.connect() as db:
                db.execute(
                    "UPDATE access SET cooldown_until=MAX(cooldown_until, ?) WHERE id=1",
                    (self.clock() + seconds,),
                )
        except sqlite3.Error as exc:
            raise AccessError(
                "Não foi possível registrar a pausa solicitada pelo Comex Stat."
            ) from exc

    def status(self):
        with self.connect() as db:
            row = db.execute("SELECT cooldown_until FROM access WHERE id=1").fetchone()
        return {"pause_seconds": max(0, math.ceil(row[0] - self.clock()))}

    def acquire(self, interval, lease_seconds, *, check, wait, notify=None):
        if not all(
            isinstance(v, (int, float)) and math.isfinite(v) and v >= 0
            for v in (interval, lease_seconds)
        ):
            raise AccessError("O intervalo de acesso está inválido.")
        token = uuid4().hex
        last_notice = -float("inf")
        while True:
            check()
            now = self.clock()
            try:
                with self.connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    owner, lease, next_at, cooldown = db.execute(
                        "SELECT owner, lease_until, next_at, cooldown_until FROM access WHERE id=1"
                    ).fetchone()
                    if not all(math.isfinite(v) for v in (lease, next_at, cooldown)):
                        raise AccessError("A fila local contém um horário inválido.")
                    # Uma política sem intervalo não herda a espera preventiva
                    # de versões antigas. Pausas reais da API e tarefas em curso
                    # continuam sendo respeitadas integralmente.
                    until = max(
                        next_at if interval else 0, cooldown, lease if owner else 0
                    )
                    if until <= now:
                        db.execute(
                            "UPDATE access SET owner=?, lease_until=? WHERE id=1",
                            (token, now + lease_seconds),
                        )
                        return RequestLease(self, token, interval)
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc).lower() and "busy" not in str(exc).lower():
                    raise AccessError(
                        "Não foi possível consultar a fila local."
                    ) from exc
                until, cooldown, owner = now + 0.25, 0, ""
            except sqlite3.Error as exc:
                raise AccessError("Não foi possível consultar a fila local.") from exc
            if notify and now - last_notice >= 1:
                label = (
                    "Comex Stat solicitou uma pausa"
                    if cooldown > now
                    else "Aguardando outra consulta"
                    if owner and lease > now
                    else "Aguardando o intervalo entre consultas"
                )
                notify(
                    None,
                    label + (f" · {math.ceil(until - now)} s" if not owner else ""),
                )
                last_notice = now
            wait(min(0.25, max(0.01, until - now)))
