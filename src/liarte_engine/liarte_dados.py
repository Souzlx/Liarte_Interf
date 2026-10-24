"""Cache incremental, rastreabilidade e comparações. Apenas biblioteca padrão."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import shutil
import sqlite3
import tempfile
import time
from collections import defaultdict
from contextlib import closing
from datetime import datetime, timezone
from decimal import Decimal, localcontext

from .numeric import from_units, published_units
from pathlib import Path
from typing import Any, Callable, Sequence

LOGGER = logging.getLogger("liarte-comex-intelligence")
CACHE_SCHEMA = 1
CACHE_BUDGET = 256 * 1024 * 1024


def data_directory() -> Path:
    """Dados por usuário, independentes da pasta do executável."""
    root = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_CACHE_HOME")
    return (Path(root) if root else Path.home() / ".cache") / "LIARTE"


def _json_text(value: Any, *, pretty: bool = False) -> str:
    """JSON numbers retain Decimal digits; canonical output stays byte compatible."""
    active = set()

    def encode(item, level=0):
        if isinstance(item, Decimal):
            if not item.is_finite():
                raise ValueError("JSON não admite números não finitos.")
            return str(item)
        if isinstance(item, (dict, list, tuple)):
            identity = id(item)
            if identity in active:
                raise ValueError("Circular reference detected")
            active.add(identity)
            try:
                if isinstance(item, dict):
                    parts = []
                    for key in sorted(item):
                        if not isinstance(key, str):
                            raise TypeError("As chaves JSON devem ser texto.")
                        parts.append(
                            json.dumps(key, ensure_ascii=False)
                            + (": " if pretty else ":")
                            + encode(item[key], level + 1)
                        )
                    opening, closing = "{", "}"
                else:
                    parts = [encode(child, level + 1) for child in item]
                    opening, closing = "[", "]"
                if pretty and parts:
                    indent = "  " * (level + 1)
                    return (
                        opening
                        + "\n"
                        + indent
                        + (",\n" + indent).join(parts)
                        + "\n"
                        + "  " * level
                        + closing
                    )
                return opening + ",".join(parts) + closing
            finally:
                active.remove(identity)
        return json.dumps(item, ensure_ascii=False, allow_nan=False, separators=(",", ":"))

    return encode(value)


def json_bytes(value: Any) -> bytes:
    return _json_text(value).encode("utf-8")


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.stem + "-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(_json_text(value, pretty=True))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_rows_sha256(rows: Sequence[dict]) -> str:
    """Mesmo SHA-256 canônico anterior, sem serializar a lista inteira de novo."""
    serialized = sorted(json_bytes(row) for row in rows)
    digest = hashlib.sha256(b"[")
    for index, row in enumerate(serialized):
        if index:
            digest.update(b",")
        digest.update(row)
    digest.update(b"]")
    return digest.hexdigest()


def publish_report_group(files: Sequence[tuple[Path, Path]]) -> None:
    """Publica arquivos já validados, sem substituir relatórios anteriores.

    Copia para temporários na pasta final, confere SHA-256 e publica cada arquivo
    atomicamente. Se a operação falhar, remove apenas as cópias desta tentativa.
    O documento original continua disponível na área temporária até a conclusão.
    """
    if len({str(destination) for _, destination in files}) != len(files):
        raise ValueError("Os arquivos do relatório precisam de destinos distintos.")
    prepared: list[tuple[Path, Path, str]] = []
    published: list[tuple[Path, str]] = []
    try:
        for source, destination in files:
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                raise FileExistsError(
                    f"O arquivo {destination.name} já existe. Gere novamente para reservar outro nome."
                )
            digest = file_sha256(source)
            descriptor, name = tempfile.mkstemp(
                prefix=".liarte-", suffix=".tmp", dir=destination.parent
            )
            temporary = Path(name)
            prepared.append((temporary, destination, digest))
            with os.fdopen(descriptor, "wb") as output, source.open("rb") as original:
                shutil.copyfileobj(original, output, 1024 * 1024)
                output.flush()
                os.fsync(output.fileno())
            if file_sha256(temporary) != digest:
                raise ValueError(
                    f"A cópia de {destination.name} não passou na verificação de integridade."
                )
        for temporary, destination, digest in prepared:
            if os.name == "nt":
                os.rename(temporary, destination)  # Windows: falha se o destino existir.
            else:
                os.link(temporary, destination)  # Publicação exclusiva no mesmo volume.
            published.append((destination, digest))
    except Exception:
        for destination, digest in reversed(published):
            try:
                # Não remove um arquivo que tenha sido alterado por outra ação.
                if destination.is_file() and file_sha256(destination) == digest:
                    destination.unlink()
            except OSError:
                LOGGER.warning(
                    "Não foi possível remover a cópia incompleta de %s", destination, exc_info=True
                )
        raise
    finally:
        for temporary, _destination, _digest in prepared:
            temporary.unlink(missing_ok=True)


def month_index(value: str) -> int:
    year, month = map(int, value.split("-"))
    if not 1 <= month <= 12:
        raise ValueError("Mês inválido.")
    return year * 12 + month - 1


def month_from_index(value: int) -> str:
    year, month = divmod(value, 12)
    return f"{year:04d}-{month + 1:02d}"


def month_range(start: str, end: str) -> list[str]:
    return [month_from_index(i) for i in range(month_index(start), month_index(end) + 1)]


class IncrementalCache:
    """Somente respostas completas e validadas entram no SQLite.

    Cada entrada representa um mês/código, inclusive quando sem movimentos.
    Hash detecta corrupção acidental. Revisão oficial e contrato fazem parte da
    chave; mudança de publicação invalida as entradas da revisão anterior.
    Falhas de disco/banco desativam apenas a otimização, nunca a consulta oficial.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path if path is not None else data_directory() / "cache" / "comexstat.sqlite3"
        self.stats = {"hits": 0, "misses": 0, "requests": 0, "unavailable": False}
        self.extractions: list[dict[str, Any]] = []

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=3)
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("""CREATE TABLE IF NOT EXISTS monthly_cache (
                dataset TEXT NOT NULL, code TEXT NOT NULL, period TEXT NOT NULL,
                contract TEXT NOT NULL, fetched_at REAL NOT NULL,
                payload BLOB NOT NULL, digest TEXT NOT NULL,
                PRIMARY KEY (dataset, code, period, contract))""")
            return connection
        except sqlite3.Error:
            connection.close()
            raise

    def _unavailable(self, exc: Exception) -> None:
        if not self.stats["unavailable"]:
            LOGGER.warning("Cache local indisponível; consulta oficial será utilizada: %s", exc)
        self.stats["unavailable"] = True

    def _load(self, dataset: str, contract: str, start: str, end: str) -> dict:
        if self.stats["unavailable"]:
            return {}
        try:
            with closing(self._connect()) as connection:
                records = connection.execute(
                    "SELECT code, period, fetched_at, payload, digest FROM monthly_cache "
                    "WHERE dataset=? AND contract=? AND period BETWEEN ? AND ?",
                    (dataset, contract, start, end),
                ).fetchall()
            result = {}
            now = time.time()
            recent = month_index(datetime.now(timezone.utc).strftime("%Y-%m")) - 2
            for code, period, fetched, payload, digest in records:
                ttl = 6 * 3600 if month_index(period) >= recent else 7 * 86400
                if not 0 <= now - fetched <= ttl:
                    continue
                if hashlib.sha256(payload).hexdigest() != digest:
                    continue
                try:
                    rows = json.loads(payload, parse_float=Decimal)
                    if isinstance(rows, list) and all(isinstance(row, dict) for row in rows):
                        result[(code, period)] = (rows, fetched, digest)
                except (UnicodeError, ValueError):
                    continue
            return result
        except (OSError, sqlite3.Error, ValueError, TypeError) as exc:
            self._unavailable(exc)
            return {}

    def _store(self, dataset: str, contract: str, parts: dict, fetched: float) -> None:
        if self.stats["unavailable"]:
            return
        try:
            entries = []
            for (code, period), rows in parts.items():
                payload = json_bytes(rows)
                entries.append(
                    (
                        dataset,
                        code,
                        period,
                        contract,
                        fetched,
                        payload,
                        hashlib.sha256(payload).hexdigest(),
                    )
                )
            with closing(self._connect()) as connection, connection:
                connection.executemany(
                    "INSERT OR REPLACE INTO monthly_cache VALUES (?,?,?,?,?,?,?)", entries
                )
                # Limita o conteúdo e elimina revisões antigas. VACUUM não é feito
                # durante consultas para evitar bloquear outro processo do usuário.
                connection.execute(
                    "DELETE FROM monthly_cache WHERE fetched_at < ?", (time.time() - 30 * 86400,)
                )
                size = connection.execute(
                    "SELECT COALESCE(SUM(LENGTH(payload)),0) FROM monthly_cache"
                ).fetchone()[0]
                if size > CACHE_BUDGET:
                    for rowid, length in connection.execute(
                        "SELECT rowid,LENGTH(payload) FROM monthly_cache ORDER BY fetched_at"
                    ).fetchall():
                        connection.execute("DELETE FROM monthly_cache WHERE rowid=?", (rowid,))
                        size -= length
                        if size <= CACHE_BUDGET:
                            break
        except (OSError, sqlite3.Error, ValueError, TypeError) as exc:
            self._unavailable(exc)

    def query(
        self,
        *,
        dataset: str,
        codes: Sequence[str],
        start: str,
        end: str,
        contract: dict,
        refresh: bool,
        reader: Callable,
        validator: Callable,
        code_of: Callable,
        period_of: Callable,
        chunk_size: int,
        window_months: int = 12,
        progress_callback: Callable[[float | None, str], None] | None = None,
    ) -> list[dict[str, Any]]:
        codes = sorted(set(codes))
        periods = month_range(start, end)
        key = hashlib.sha256(json_bytes({"schema": CACHE_SCHEMA, **contract})).hexdigest()
        cached = {} if refresh else self._load(dataset, key, start, end)
        rows = []
        total_units = max(1, len(codes) * len(periods))
        completed_units = 0
        missing: dict[str, tuple[str, ...]] = {}
        for period in periods:
            absent = []
            for code in codes:
                entry = cached.get((code, period))
                if entry is not None:
                    try:
                        for row in entry[0]:
                            validator(row, {code}, period, period, "cache local")
                    except (ValueError, TypeError, RuntimeError):
                        entry = None
                if entry is None:
                    absent.append(code)
                    self.stats["misses"] += 1
                else:
                    rows.extend(entry[0])
                    completed_units += 1
                    self.stats["hits"] += 1
                    self.extractions.append(
                        {
                            "dataset": dataset,
                            "code": code,
                            "period": period,
                            "fetched_at": entry[1],
                            "sha256": entry[2],
                            "source": "cache",
                        }
                    )
            missing[period] = tuple(absent)
            if progress_callback is not None:
                progress_callback(
                    completed_units / total_units, f"Conferindo os dados locais de {period}"
                )
        # Meses consecutivos com a mesma cobertura ausente viram uma consulta.
        tasks: list[tuple[tuple[str, ...], str, str]] = []
        for period in periods:
            absent = missing[period]
            if not absent:
                continue
            if (
                tasks
                and tasks[-1][0] == absent
                and month_index(period) == month_index(tasks[-1][2]) + 1
                and month_index(period) - month_index(tasks[-1][1]) < window_months
            ):
                tasks[-1] = (absent, tasks[-1][1], period)
            else:
                tasks.append((absent, period, period))
        for absent, first, last in tasks:
            for offset in range(0, len(absent), chunk_size):
                batch = list(absent[offset : offset + chunk_size])
                fetched_rows = reader(batch, first, last, chunk_size)
                self.stats["requests"] += 1
                parts: dict[tuple[str, str], list] = {
                    (code, period): [] for code in batch for period in month_range(first, last)
                }
                requested = set(batch)
                for row in fetched_rows:
                    validator(row, requested, first, last, "consulta incremental")
                    parts[(code_of(row), period_of(row))].append(row)
                fetched = time.time()
                self._store(dataset, key, parts, fetched)
                for (code, period), part in parts.items():
                    self.extractions.append(
                        {
                            "dataset": dataset,
                            "code": code,
                            "period": period,
                            "fetched_at": fetched,
                            "sha256": hashlib.sha256(json_bytes(part)).hexdigest(),
                            "source": "api",
                        }
                    )
                rows.extend(fetched_rows)
                completed_units += len(parts)
                if progress_callback is not None:
                    progress_callback(
                        completed_units / total_units,
                        f"Dados oficiais de {first} a {last} recebidos e validados",
                    )
        return rows


def _json_number(value: Decimal):
    """Usual JSON numeric types, exact decimal text beyond binary-float precision."""
    if value == value.to_integral_value():
        return int(value)
    approximate = float(value)
    return approximate if Decimal(str(approximate)) == value else format(value, "f")


def _json_numbers(value, approximate=False):
    if isinstance(value, Decimal):
        if approximate:
            result = float(value)
            return result if math.isfinite(result) else format(value, "f")
        return _json_number(value)
    if isinstance(value, dict):
        return {
            key: _json_numbers(item, approximate or key in {"ratio", "price", "share"})
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_json_numbers(item, approximate) for item in value]
    return value


def create_manifest(
    *,
    excel_path: Path,
    powerbi_path: Path | None,
    version: str,
    catalog_version: str,
    pairs: Sequence,
    start: str,
    end: str,
    general_rows: Sequence[dict],
    municipal_rows: Sequence[dict],
    number: Callable,
    municipal_status: str = "complete",
    publication: Any = None,
    cache: IncrementalCache | None = None,
) -> Path:
    """Documento de auditoria separado das planilhas e dos filtros de visualização."""
    catalog = sorted({(pair.ncm, pair.product) for pair in pairs})
    files = [
        {"name": path.name, "bytes": path.stat().st_size, "sha256": file_sha256(path)}
        for path in (excel_path, powerbi_path)
        if path is not None
    ]

    def totals(rows: Sequence[dict], fields: Sequence[str]) -> dict:
        return {
            field: _json_number(
                from_units(
                    sum(
                        published_units(row[field], places=0 if field == "metricKG" else 2)
                        for row in rows
                    ),
                    places=0 if field == "metricKG" else 2,
                )
            )
            for field in fields
        }

    manifest = {
        "schema": 2,
        "numeric_encoding": "JSON numbers when exact; decimal strings otherwise",
        "total_units": {"money": "US$", "weight": "kg"},
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "application_version": version,
        "catalog": {
            "version": catalog_version,
            "products": len(catalog),
            "ncms": len({ncm for ncm, _ in catalog}),
            "sha256": hashlib.sha256(json_bytes(catalog)).hexdigest(),
        },
        "period": {"from": start, "to": end},
        "publication": publication,
        "source": "https://comexstat.mdic.gov.br/",
        "general": {
            "status": "complete",
            "records": len(general_rows),
            "grain": "mês/NCM/UF/URF/país",
            "totals": totals(
                general_rows,
                ["metricFOB", "metricFreight", "metricInsurance", "metricCIF", "metricKG"],
            ),
            "sha256": canonical_rows_sha256(general_rows),
        },
        "municipal": {
            "status": municipal_status,
            "records": len(municipal_rows),
            "grain": "mês/município fiscal/UF/SH4/país",
            "totals": totals(municipal_rows, ["metricFOB", "metricKG"])
            if municipal_status == "complete"
            else None,
            "sha256": canonical_rows_sha256(municipal_rows),
        },
        "files": files,
        "cache": dict(cache.stats) if cache else {"enabled": False},
        "extractions": list(cache.extractions) if cache else [],
        "method": "Dados agregados oficiais. Bases geral e municipal independentes. "
        "Produtos vinculados ao mesmo NCM não multiplicam seus valores.",
    }
    path = excel_path.with_suffix(".manifesto.json")
    atomic_json(path, manifest)
    return path


def period_comparisons(
    rows: Sequence[dict], start: str, end: str, number: Callable, state_label: Callable = str
) -> dict:
    """Compara último mês com o anterior/mesmo mês anterior, dentro da cobertura.

    A ausência de registros em um mês consultado significa movimento zero. Um
    mês fora da cobertura é indisponível e nunca é convertido em zero.
    """
    metrics = {"cif": "metricCIF", "fob": "metricFOB", "kg": "metricKG"}

    def total(selected: Sequence[dict]) -> dict:
        result = {
            key: from_units(
                sum(
                    published_units(row[field], places=0 if key == "kg" else 2) for row in selected
                ),
                places=0 if key == "kg" else 2,
            )
            for key, field in metrics.items()
        }
        result["price"] = divide(result["cif"], result["kg"])
        return result

    def divide(numerator, denominator):
        if not denominator:
            return None
        with localcontext() as context:
            context.prec = max(50, len(str(numerator)) + len(str(denominator)) + 10)
            return numerator / denominator

    def delta(before, after) -> dict:
        if before is None or after is None:
            return {"previous": before, "current": after, "change": None, "ratio": None}
        with localcontext() as context:
            context.prec = max(50, len(str(before)) + len(str(after)) + 10)
            change = after - before
        return {
            "previous": before,
            "current": after,
            "change": change,
            "ratio": divide(change, before),
        }

    dimensions = {
        "ncm": lambda r: str(r["coNcm"]).zfill(8),
        "country": lambda r: str(r["country"]),
        "state": lambda r: state_label(r["state"]),
        "urf": lambda r: str(r["urf"]),
    }
    current = [
        row for row in rows if f"{int(row['year']):04d}-{int(row['monthNumber']):02d}" == end
    ]
    current_total = total(current)
    result: dict[str, Any] = {}
    for mode, offset in (("monthly", 1), ("yearly", 12)):
        previous = month_from_index(month_index(end) - offset)
        if previous < start:
            result[mode] = {"available": False, "current_period": end, "previous_period": previous}
            continue
        old = [
            row
            for row in rows
            if f"{int(row['year']):04d}-{int(row['monthNumber']):02d}" == previous
        ]
        old_total = total(old)
        compared = {
            "available": True,
            "current_period": end,
            "previous_period": previous,
            "metrics": {key: delta(old_total[key], current_total[key]) for key in current_total},
            "dimensions": {},
        }
        for dimension, label in dimensions.items():
            groups: dict[str, list[list]] = defaultdict(lambda: [[], []])
            for side, selected in enumerate((old, current)):
                for row in selected:
                    groups[label(row)][side].append(row)
            details = []
            for name, (before_rows, after_rows) in groups.items():
                before, after = total(before_rows), total(after_rows)
                share_before = divide(before["cif"], old_total["cif"])
                share_after = divide(after["cif"], current_total["cif"])
                details.append(
                    {
                        "name": name,
                        "metrics": {key: delta(before[key], after[key]) for key in after},
                        "share": delta(share_before, share_after),
                    }
                )
            compared["dimensions"][dimension] = sorted(
                details,
                key=lambda x: (x["metrics"]["cif"]["change"].copy_abs().copy_negate(), x["name"]),
            )
        result[mode] = compared
    result["numeric_encoding"] = (
        "Exact money (US$) and kg: JSON numbers or decimal strings; ratios approximate"
    )
    return _json_numbers(result)
