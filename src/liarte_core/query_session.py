"""Small, versioned accepted-query checkpoints; never serialize executable data."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from threading import Condition, Thread
from uuid import uuid4

from .domain import Period, Selection

LIMIT = 64 * 1024


def _body(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def _read(path):
    with Path(path).open("rb") as stream:
        raw = stream.read(LIMIT + 1)
    if len(raw) > LIMIT:
        raise ValueError("A consulta salva excede o limite.")
    envelope = json.loads(raw)
    payload = envelope["payload"]
    if envelope["schema"] != 1 or hashlib.sha256(_body(payload)).hexdigest() != envelope["sha256"]:
        raise ValueError("A consulta salva está inválida.")
    if not isinstance(payload, dict):
        raise ValueError("A consulta salva está inválida.")
    return payload


def load_session(path):
    """Try the last complete checkpoint, then its previous complete copy."""
    for candidate in (Path(path), Path(str(path) + ".previous")):
        try:
            return _read(candidate)
        except (OSError, ValueError, TypeError, KeyError, RecursionError):
            continue
    return None


def save_session(path, payload):
    path = Path(path)
    raw = _body(
        {"schema": 1, "payload": payload, "sha256": hashlib.sha256(_body(payload)).hexdigest()}
    )
    if len(raw) > LIMIT:
        raise ValueError("A consulta salva excede o limite.")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("." + path.name + "-" + uuid4().hex)
    previous_temp = temporary.with_suffix(".previous")
    try:
        with temporary.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        if path.is_file():
            try:
                old = _read(path)
            except (OSError, ValueError, KeyError, TypeError, RecursionError):
                old = None
            if old is not None:
                # Copy, do not move: primary remains intact if final replace fails.
                previous = _body(
                    {"schema": 1, "payload": old, "sha256": hashlib.sha256(_body(old)).hexdigest()}
                )
                with previous_temp.open("xb") as stream:
                    stream.write(previous)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(previous_temp, Path(str(path) + ".previous"))
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
        previous_temp.unlink(missing_ok=True)


def import_session(selection, catalog_key, revision):
    return {
        "module": "imports",
        "catalog": catalog_key,
        "revision": revision,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "selection": asdict(selection),
    }


def import_selection(payload, catalog_key):
    if payload.get("module") != "imports" or payload.get("catalog") != catalog_key:
        raise ValueError("A consulta salva pertence a outra base.")
    values = dict(payload["selection"])
    values["period"] = Period(**values["period"])
    for key in ("ncm", "country", "state", "port", "city"):
        values[key + "_values"] = tuple(values[key + "_values"])
    return Selection(**values)


class SessionWriter:
    """Coalesced background writes; normal shutdown flushes the latest acceptance."""

    def __init__(self, path):
        self.path = Path(path)
        self._condition = Condition()
        self._pending = None
        self._closed = False
        self._thread = None
        self.error = ""

    def submit(self, payload):
        # Detach small JSON-compatible values from the GUI's mutable state.
        payload = json.loads(_body(payload))
        with self._condition:
            if self._closed:
                return
            self._pending = payload
            if self._thread is None:
                self._thread = Thread(target=self._run, name="liarte-query-checkpoint", daemon=True)
                self._thread.start()
            self._condition.notify()

    def _run(self):
        while True:
            with self._condition:
                self._condition.wait_for(lambda: self._pending is not None or self._closed)
                if self._pending is None:
                    return
                payload, self._pending = self._pending, None
            try:
                save_session(self.path, payload)
                self.error = ""
            except (OSError, ValueError, TypeError, RecursionError):
                self.error = "Não foi possível salvar a última consulta neste perfil."

    def close(self):
        with self._condition:
            self._closed = True
            self._condition.notify()
        if self._thread is not None:
            self._thread.join()
