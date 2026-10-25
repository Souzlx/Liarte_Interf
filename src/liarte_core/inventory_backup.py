"""Versioned local stock snapshots; publication never overwrites an old backup."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
from threading import Event
from uuid import uuid4

from .inventory import InventoryData
from .inventory_io import MAX_COMPRESSED, read_snapshot
from .query import checkpoint

LOGGER = logging.getLogger("liarte.desktop")
FORMAT = "liarte.inventory-backup/1"
MAX_BACKUPS = 10
MAX_FOLDERS = 1000
MAX_MANIFEST_BYTES = 8192
_ID = re.compile(r"[0-9]{8}T[0-9]{12}Z-[0-9a-f]{32}")
_MANIFEST_KEYS = {
    "format",
    "id",
    "created_at",
    "as_of",
    "source_name",
    "products",
    "balances",
    "sha256",
    "bytes",
}


@dataclass(frozen=True, slots=True)
class BackupInfo:
    id: str
    path: Path
    created_at: str
    as_of: str
    source_name: str
    products: int
    balances: int
    sha256: str
    bytes: int


def _safe_path(path: Path) -> Path:
    path = Path(path).absolute()
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError("O histórico de bases não aceita links simbólicos.")
    return path


def _directory(cache_path: Path, *, create=False) -> Path:
    directory = _safe_path(Path(cache_path).parent / "backups")
    if create:
        directory.mkdir(parents=True, exist_ok=True)
        _safe_path(directory)
    if directory.exists() and not directory.is_dir():
        raise ValueError("A pasta do histórico de bases é inválida.")
    return directory


def _reader(path: Path, limit: int):
    path = _safe_path(path)
    if not path.is_file():
        raise ValueError("A cópia de segurança deve ser um arquivo regular.")
    descriptor = os.open(
        path,
        os.O_RDONLY
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0),
    )
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError("Arquivo do histórico inválido ou acima do limite permitido.")
        return os.fdopen(descriptor, "rb")
    except BaseException:
        os.close(descriptor)
        raise


def _digest(path: Path, cancel: Event) -> tuple[str, int]:
    digest, size = hashlib.sha256(), 0
    with _reader(path, MAX_COMPRESSED) as source:
        while block := source.read(1024 * 1024):
            checkpoint(cancel)
            size += len(block)
            if size > MAX_COMPRESSED:
                raise ValueError("A cópia de segurança ultrapassa o tamanho permitido.")
            digest.update(block)
    checkpoint(cancel)
    return digest.hexdigest(), size


def _read_backup(directory: Path, cancel: Event) -> tuple[BackupInfo, InventoryData]:
    checkpoint(cancel)
    directory = _safe_path(directory)
    if not _ID.fullmatch(directory.name) or not directory.is_dir():
        raise ValueError("Identificação de cópia de segurança inválida.")
    names = set()
    for count, child in enumerate(directory.iterdir(), 1):
        checkpoint(cancel)
        if count > 2:
            raise ValueError("Estrutura da cópia de segurança inválida.")
        names.add(child.name)
    if names != {"base.liarte", "manifest.json"}:
        raise ValueError("Estrutura da cópia de segurança inválida.")
    with _reader(directory / "manifest.json", MAX_MANIFEST_BYTES) as source:
        raw = source.read(MAX_MANIFEST_BYTES + 1)
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ValueError("Manifesto de cópia de segurança acima do limite.")
    try:
        manifest = json.loads(raw)
    except (ValueError, RecursionError) as exc:
        raise ValueError("Manifesto de cópia de segurança inválido.") from exc
    if (
        not isinstance(manifest, dict)
        or set(manifest) != _MANIFEST_KEYS
        or manifest.get("format") != FORMAT
        or manifest.get("id") != directory.name
        or not isinstance(manifest.get("created_at"), str)
        or not isinstance(manifest.get("sha256"), str)
        or re.fullmatch("[0-9a-f]{64}", manifest["sha256"]) is None
        or any(type(manifest.get(key)) is not int for key in ("products", "balances", "bytes"))
    ):
        raise ValueError("Manifesto de cópia de segurança inválido.")
    created = datetime.fromisoformat(manifest["created_at"])
    if (
        created.utcoffset() != timedelta(0)
        or manifest["created_at"] != created.isoformat(timespec="microseconds")
        or created.strftime("%Y%m%dT%H%M%S%fZ") != directory.name.split("-", 1)[0]
    ):
        raise ValueError("Data de cópia de segurança inválida.")
    snapshot = directory / "base.liarte"
    digest, size = _digest(snapshot, cancel)
    if digest != manifest["sha256"] or size != manifest["bytes"]:
        raise ValueError("A integridade da cópia de segurança não pôde ser confirmada.")
    data = read_snapshot(snapshot, cancel)
    if (
        data.as_of.isoformat() != manifest["as_of"]
        or data.source_name != manifest["source_name"]
        or len(data.products) != manifest["products"]
        or len(data.balances) != manifest["balances"]
    ):
        raise ValueError("O conteúdo da cópia diverge do manifesto.")
    return BackupInfo(path=snapshot, **{k: manifest[k] for k in _MANIFEST_KEYS - {"format"}}), data


def backup_previous(
    cache_path: Path, staged_path: Path | None = None, cancel: Event | None = None
) -> BackupInfo | None:
    """Copy the current valid cache before replacement; a copy failure propagates.

    A missing/corrupt previous snapshot does not prevent recovery from a valid
    source. The caller publishes its new base separately and only then prunes.
    """
    cancel = cancel or Event()
    checkpoint(cancel)
    cache_path = _safe_path(cache_path)
    if not cache_path.exists():
        return None
    # An oversized previous file is invalid, not a snapshot worth retaining.
    if cache_path.is_file() and cache_path.stat().st_size > MAX_COMPRESSED:
        return None
    # Validate the copied previous base before touching the backup store. A
    # corrupt cache must not make fallback depend on that store being writable.
    # Both locations share cache.parent's filesystem, preserving atomic rename.
    staging = Path(tempfile.mkdtemp(prefix=".backup-", dir=cache_path.parent))
    try:
        snapshot = staging / "base.liarte"
        digest, size = hashlib.sha256(), 0
        with _reader(cache_path, MAX_COMPRESSED) as source, snapshot.open("xb") as target:
            while block := source.read(1024 * 1024):
                checkpoint(cancel)
                size += len(block)
                if size > MAX_COMPRESSED:
                    return None
                digest.update(block)
                target.write(block)
            target.flush()
            os.fsync(target.fileno())
        checkpoint(cancel)
        try:
            data = read_snapshot(snapshot, cancel)
        except ValueError as exc:
            # A real disk access error while validating our own new file is a
            # backup failure; malformed gzip/JSON is an invalid previous base.
            cause = exc.__cause__
            if isinstance(cause, OSError) and cause.errno is not None:
                raise cause from exc
            return None
        sha256 = digest.hexdigest()
        if staged_path is not None and _digest(staged_path, cancel) == (sha256, size):
            return None
        directory = _directory(cache_path, create=True)
        created = datetime.now(timezone.utc)
        identifier = created.strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid4().hex
        manifest = {
            "format": FORMAT,
            "id": identifier,
            "created_at": created.isoformat(timespec="microseconds"),
            "as_of": data.as_of.isoformat(),
            "source_name": data.source_name,
            "products": len(data.products),
            "balances": len(data.balances),
            "sha256": sha256,
            "bytes": size,
        }
        with (staging / "manifest.json").open("x", encoding="utf-8") as output:
            json.dump(manifest, output, ensure_ascii=False, separators=(",", ":"))
            output.flush()
            os.fsync(output.fileno())
        destination = directory / identifier
        if destination.exists() or destination.is_symlink():
            raise FileExistsError("A identificação da cópia de segurança já existe.")
        checkpoint(cancel)
        os.replace(staging, destination)
        return BackupInfo(
            path=destination / "base.liarte",
            **{k: manifest[k] for k in _MANIFEST_KEYS - {"format"}},
        )
    finally:
        if staging.exists():
            try:
                shutil.rmtree(staging)
            except OSError:
                LOGGER.warning(
                    "Não foi possível remover cópia temporária: %s", staging, exc_info=True
                )


def list_backups(cache_path: Path, cancel: Event | None = None) -> tuple[BackupInfo, ...]:
    """Return verified copies newest first; malformed entries remain untouched."""
    cancel = cancel or Event()
    checkpoint(cancel)
    directory = _directory(cache_path)
    if not directory.exists():
        return ()
    backups = []
    for count, candidate in enumerate(directory.iterdir(), 1):
        checkpoint(cancel)
        if count > MAX_FOLDERS:
            raise ValueError("O histórico contém entradas demais para leitura segura.")
        if not _ID.fullmatch(candidate.name):
            continue
        try:
            # Keep metadata only. Holding the previous InventoryData until the
            # next read would unnecessarily double the history's peak memory.
            info = _read_backup(candidate, cancel)[0]
        except (ValueError, OSError, RecursionError):
            LOGGER.warning(
                "Cópia de segurança inválida ignorada: %s", candidate.name, exc_info=True
            )
            continue
        backups.append(info)
    return tuple(sorted(backups, key=lambda info: (info.created_at, info.id), reverse=True))


def load_backup(cache_path: Path, backup_id: str, cancel: Event | None = None) -> InventoryData:
    """Resolve only opaque managed identifiers and verify before returning data."""
    cancel = cancel or Event()
    checkpoint(cancel)
    if not isinstance(backup_id, str) or _ID.fullmatch(backup_id) is None:
        raise ValueError("Selecione uma cópia de segurança válida.")
    return _read_backup(_directory(cache_path) / backup_id, cancel)[1]


def prune_backups(
    cache_path: Path,
    *,
    keep: int = MAX_BACKUPS,
    preserve_ids=(),
    cancel: Event | None = None,
) -> None:
    """Prune verified managed folders only, after the caller commits its base."""
    cancel = cancel or Event()
    if type(keep) is not int or not 1 <= keep <= MAX_BACKUPS:
        raise ValueError("O histórico deve manter entre uma e dez cópias.")
    preserve = set(preserve_ids)
    if len(preserve) > keep or any(
        not isinstance(i, str) or not _ID.fullmatch(i) for i in preserve
    ):
        raise ValueError("Identificação de cópia preservada inválida.")
    backups = list_backups(cache_path, cancel)
    retained = {info.id for info in backups if info.id in preserve}
    for info in backups:
        if len(retained) == keep:
            break
        retained.add(info.id)
    for info in backups:
        checkpoint(cancel)
        if info.id not in retained:
            folder = _safe_path(info.path.parent)
            # Recheck the managed pair immediately before removal. A directory
            # edited since listing is not eligible for automatic cleanup.
            _read_backup(folder, cancel)
            shutil.rmtree(folder)
