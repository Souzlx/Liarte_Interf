"""Consistent SQLite backups, independent of WAL files and UI sessions."""

from __future__ import annotations

from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
from threading import Event
from uuid import uuid4

from .query import checkpoint


def _digest(path, cancel):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            checkpoint(cancel)
            digest.update(chunk)
    return digest.hexdigest()


def _metadata(db, catalog):
    row = db.execute(
        "SELECT g.revision,g.start,g.end,c.contract FROM active a JOIN generations g ON g.id=a.generation_id JOIN catalogs c ON c.key=a.catalog_key WHERE a.catalog_key=?",
        (catalog,),
    ).fetchone()
    if row is None:
        raise ValueError("O histórico não possui uma versão aceita para copiar.")
    return {
        "catalog": catalog,
        "revision": row[0],
        "start": row[1],
        "end": row[2],
        "codes": json.loads(row[3])["codes"],
    }


def verify_backup(directory, *, cancel=None):
    cancel = cancel or Event()
    directory = Path(directory)
    with (directory / "manifest.json").open("rb") as stream:
        raw = stream.read(64 * 1024 + 1)
    if len(raw) > 64 * 1024:
        raise ValueError("Manifesto de backup inválido.")
    metadata = json.loads(raw)
    path = directory / "historico.sqlite3"
    if metadata["schema"] != 1 or _digest(path, cancel) != metadata["sha256"]:
        raise ValueError("A cópia do histórico falhou na verificação de integridade.")
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.set_progress_handler(lambda: 1 if cancel.is_set() else 0, 4096)
        if (
            db.execute("PRAGMA quick_check").fetchone()[0] != "ok"
            or db.execute("PRAGMA foreign_key_check").fetchone() is not None
        ):
            raise ValueError("A cópia do banco está inválida.")
        if _metadata(db, metadata["catalog"]) != {
            key: metadata[key] for key in ("catalog", "revision", "start", "end", "codes")
        }:
            raise ValueError("A referência do backup é divergente.")
    checkpoint(cancel)
    return metadata


def create_backup(store, cancel=None, *, keep=5):
    """Called in the synchronization worker; retain only verified generations."""
    cancel = cancel or Event()
    if type(keep) is not int or keep < 1:
        raise ValueError("A retenção precisa preservar ao menos uma cópia.")
    status = store.status()
    revision = status.get("local_revision")
    if not status.get("complete") or not revision:
        return None
    directory = store.path.parent / "backups-comex"
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / (store.catalog_key[:16] + "-" + revision)
    if destination.is_dir():
        verify_backup(destination, cancel=cancel)
        return destination
    temporary = directory / (".backup-" + uuid4().hex)
    temporary.mkdir()
    try:
        path = temporary / "historico.sqlite3"
        with (
            closing(
                sqlite3.connect(store.path.resolve().as_uri() + "?mode=ro", uri=True)
            ) as source,
            closing(sqlite3.connect(path)) as target,
        ):
            source.backup(target, pages=128, progress=lambda *_: checkpoint(cancel), sleep=0.01)
            metadata = _metadata(target, store.catalog_key)
            if metadata["revision"] != revision:
                raise ValueError("A base mudou durante a preparação do backup. Tente novamente.")
        metadata.update(schema=1, sha256=_digest(path, cancel))
        with (temporary / "manifest.json").open("x", encoding="utf-8") as stream:
            json.dump(metadata, stream, ensure_ascii=False, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        verify_backup(temporary, cancel=cancel)
        checkpoint(cancel)
        try:
            os.rename(temporary, destination)
        except OSError:
            # Another installation process may already have published this revision.
            if not destination.is_dir():
                raise
            verify_backup(destination, cancel=cancel)
        valid = []
        for candidate in directory.iterdir():
            if candidate.name.startswith(store.catalog_key[:16] + "-"):
                try:
                    verify_backup(candidate, cancel=cancel)
                    valid.append(candidate)
                except (OSError, ValueError, sqlite3.Error, KeyError, TypeError):
                    continue
        older = sorted(
            (p for p in valid if p != destination), key=lambda p: p.stat().st_mtime_ns, reverse=True
        )
        for candidate in older[max(0, keep - 1) :]:
            checkpoint(cancel)
            shutil.rmtree(candidate)
        return destination
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def restore_to_new_file(directory, destination, *, cancel=None):
    """Recover to a new name; never replace a live or newer database."""
    cancel = cancel or Event()
    directory, destination = Path(directory), Path(destination)
    verify_backup(directory, cancel=cancel)
    if destination.exists() or any(
        Path(str(destination) + suffix).exists() for suffix in ("-wal", "-shm")
    ):
        raise ValueError("Escolha um arquivo novo; o banco atual será preservado.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(".restore-" + uuid4().hex)
    try:
        with (directory / "historico.sqlite3").open("rb") as source, temporary.open("xb") as target:
            while chunk := source.read(1024 * 1024):
                checkpoint(cancel)
                target.write(chunk)
            target.flush()
            os.fsync(target.fileno())
        # Atomic create-if-absent: even a competing creator cannot be overwritten.
        checkpoint(cancel)
        os.link(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination
