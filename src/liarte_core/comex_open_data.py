"""Leitura verificável dos arquivos oficiais que alimentam o Comex Stat.

Não utiliza espelhos, proxies, mudança de IP ou aproximações de métricas. Um
arquivo anual é lido por inteiro para conferir os totais nacionais publicados;
somente o recorte do catálogo é mantido no índice. A API não participa desta
conferência. O repositório deve ficar no disco local do host da central.
"""

from __future__ import annotations

import csv
import codecs
import hashlib
import html
import http.client
import json
import logging
import math
import os
import re
import shutil
import time
import urllib.error
import urllib.request
import zlib
from collections import defaultdict
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from liarte_engine import comexstat_importacoes as engine
from liarte_engine.liarte_dados import atomic_json, json_bytes
from liarte_engine.secure_http import build_opener, certificate_failure, TLS_POLICY
from .catalog import catalog

LOGGER = logging.getLogger("liarte.desktop")
BASE = "https://balanca.mdic.gov.br/balanca/bd/"
PUBLICATION = (
    "https://www.gov.br/mdic/pt-br/assuntos/comercio-exterior/estatisticas/base-de-dados-bruta"
)
SCHEMA = "liarte.mdic-csv/1"
MAX_FILE = 3 * 1024**3
MAX_INDEX = 128 * 1024**2
OFFICIAL_HOSTS = frozenset({"balanca.mdic.gov.br", "balanca.economia.gov.br", "www.gov.br"})
GENERAL_HEADER = (
    "CO_ANO CO_MES CO_NCM CO_UNID CO_PAIS SG_UF_NCM CO_VIA CO_URF "
    "QT_ESTAT KG_LIQUIDO VL_FOB VL_FRETE VL_SEGURO"
).split()
MUNICIPAL_HEADER = "CO_ANO CO_MES SH4 CO_PAIS SG_UF_MUN CO_MUN KG_LIQUIDO VL_FOB".split()
REFERENCES = {
    "NCM": ("CO_NCM", "NO_NCM_POR"),
    "NCM_SH": ("CO_SH4", "NO_SH4_POR"),
    "PAIS": ("CO_PAIS", "NO_PAIS"),
    "UF_MUN": ("CO_MUN_GEO", "NO_MUN_MIN"),
    "URF": ("CO_URF", "NO_URF"),
}


class OpenDataError(engine.ComexStatError):
    """Download, contrato ou conferência oficial indisponível; nunca dado parcial."""


class OfficialRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        parts = urlsplit(new_url)
        if (
            parts.scheme != "https"
            or parts.hostname not in OFFICIAL_HOSTS
            or parts.username
            or parts.password
        ):
            raise OpenDataError("Redirecionamento fora das origens oficiais autorizadas.")
        return super().redirect_request(request, response, code, message, headers, new_url)


@contextmanager
def download_lock(path, check):
    """O sistema operacional libera a trava se o processo morrer, sem lease longo."""
    with Path(path).open("a+b") as handle:
        if os.fstat(handle.fileno()).st_size == 0:
            handle.write(b"0")
            handle.flush()
        while True:
            check()
            try:
                if os.name == "nt":
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except (BlockingIOError, PermissionError):
                time.sleep(0.05)
            except OSError as exc:
                if exc.errno not in (11, 13, 35, 36):
                    raise OpenDataError("Não foi possível reservar o download oficial.") from exc
                time.sleep(0.05)
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


def integer(value, context):
    value = str(value).strip()
    if not value or len(value) > 128 or not value.isascii() or not value.isdecimal():
        raise OpenDataError(f"Número inválido em {context}; a base não foi publicada.")
    return int(value)


def fingerprint(path, check):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while block := handle.read(1024 * 1024):
            check()
            digest.update(block)
    return digest.hexdigest()


@contextmanager
def csv_rows(path, *, check=lambda: None):
    # The MDIC tables historically use Latin-1. Detect UTF-8 strictly before
    # falling back; never replace undecodable bytes with U+FFFD.
    decoder = codecs.getincrementaldecoder("utf-8-sig")()
    try:
        with Path(path).open("rb") as probe:
            while sample := probe.read(256 * 1024):
                check()
                decoder.decode(sample, final=False)
            decoder.decode(b"", final=True)
        encoding = "utf-8-sig"
    except UnicodeDecodeError:
        encoding = "latin-1"
    with Path(path).open(encoding=encoding, newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";", strict=True)
        fields = reader.fieldnames
        if not fields or len(fields) != len(set(fields)):
            raise OpenDataError("Cabeçalho CSV oficial ausente ou duplicado.")
        fields = [f.strip().lstrip("\ufeff").upper() for f in fields]
        if len(fields) != len(set(fields)) or any(not f for f in fields):
            raise OpenDataError("Cabeçalho CSV oficial inválido.")
        reader.fieldnames = fields
        try:
            yield reader
        except (csv.Error, UnicodeError) as exc:
            raise OpenDataError(
                "O CSV oficial está incompleto ou possui codificação inválida."
            ) from exc


def require_fields(reader, required, context):
    if not set(required) <= set(reader.fieldnames):
        missing = ", ".join(sorted(set(required) - set(reader.fieldnames)))
        raise OpenDataError(f"Layout oficial não reconhecido em {context}: {missing}.")


class OfficialFiles:
    """Downloads condicionais, limitados, canceláveis e publicados atomicamente."""

    def __init__(self, directory, *, opener=None, clock=time.time):
        self.directory = Path(directory)
        if str(self.directory).startswith(("//", "\\\\")):
            raise OpenDataError("Os arquivos oficiais devem ficar no disco local da central.")
        # Lazy: abrir Estoque ou consultar índices válidos não requer TLS/rede.
        self.opener = opener or self._open
        self.clock = clock
        self._verified = {}

    def _open(self, request, *, timeout):
        return build_opener(OfficialRedirects()).open(request, timeout=timeout)

    def fetch(self, relative, *, check, notify, max_size=MAX_FILE, ttl=300, revision=None):
        publication = relative == "publication.html"
        url = PUBLICATION if publication else BASE + relative
        if not publication and not re.fullmatch(
            r"(?:tabelas/[A-Z_]+\.csv|comexstat-bd/(?:ncm|mun)/IMP_[A-Z0-9_]+\.csv)", relative
        ):
            raise OpenDataError("Arquivo fora da lista oficial de importações.")
        target = self.directory / relative
        manifest = target.with_suffix(target.suffix + ".json")
        target.parent.mkdir(parents=True, exist_ok=True)
        with download_lock(self.directory / "downloads.lock", check):
            check()
            stored = self._manifest(manifest)
            intact = False
            if target.is_file():
                info = target.stat()
                stamp = (info.st_size, info.st_mtime_ns, info.st_ctime_ns, stored.get("sha256"))
                if info.st_size == stored.get("bytes") and info.st_size <= max_size:
                    intact = self._verified.get(str(target)) == stamp or fingerprint(
                        target, check
                    ) == stored.get("sha256")
                    if intact:
                        self._verified[str(target)] = stamp
            if (
                intact
                and stored.get("publication_revision") == revision
                and 0 <= self.clock() - stored.get("checked_at", 0) < ttl
            ):
                return target, stored
            if stored.get("retry_at", 0) > self.clock():
                raise OpenDataError("O servidor dos arquivos oficiais está em pausa temporária.")
            headers = {"User-Agent": "LIARTE-Importacoes/5.2", "Accept-Encoding": "identity"}
            if intact:
                for key, name in (
                    ("etag", "If-None-Match"),
                    ("last_modified", "If-Modified-Since"),
                ):
                    if stored.get(key):
                        headers[name] = stored[key]
            temporary = target.with_name(target.name + "." + uuid4().hex + ".part")
            started = time.monotonic()
            retry_delay = 60.0
            try:
                notify(
                    None,
                    "Verificando publicação oficial"
                    if publication
                    else "Obtendo arquivo oficial " + target.name,
                )
                request = urllib.request.Request(url, headers=headers)
                try:
                    response = self.opener(request, timeout=15)
                except urllib.error.HTTPError as exc:
                    if exc.code == 304 and intact:
                        exc.close()
                        stored.update(
                            checked_at=self.clock(), retry_at=0, publication_revision=revision
                        )
                        atomic_json(manifest, stored)
                        return target, stored
                    if exc.code in (429, 503):
                        retry_delay = max(
                            60.0, engine.ComexStatClient._retry_seconds(exc.headers or {}, "", 1)
                        )
                    exc.close()
                    raise
                with response:
                    parts = urlsplit(response.geturl())
                    if parts.scheme != "https" or parts.hostname not in OFFICIAL_HOSTS:
                        raise OpenDataError(
                            "O download foi redirecionado para uma origem não autorizada."
                        )
                    if response.status != 200:
                        raise OpenDataError("O servidor não entregou o arquivo oficial completo.")
                    length = response.headers.get("Content-Length")
                    length = integer(length, "tamanho do download") if length is not None else None
                    if length is not None and (length <= 0 or length > max_size):
                        raise OpenDataError(
                            "O tamanho do arquivo oficial está fora do limite suportado."
                        )
                    if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                        raise OpenDataError("O servidor alterou a codificação do download.")
                    if (
                        shutil.disk_usage(target.parent).free
                        < (length or 32 * 1024**2) + 64 * 1024**2
                    ):
                        raise OpenDataError(
                            "Espaço insuficiente para obter a base oficial com segurança."
                        )
                    digest, size, last_notice = hashlib.sha256(), 0, -1
                    with temporary.open("xb") as output:
                        while True:
                            check()
                            if time.monotonic() - started > 1200:
                                raise OpenDataError("O download oficial excedeu 20 minutos.")
                            block = response.read(256 * 1024)
                            if not block:
                                break
                            size += len(block)
                            if size > max_size or length is not None and size > length:
                                raise OpenDataError(
                                    "O download oficial excedeu o tamanho anunciado."
                                )
                            output.write(block)
                            digest.update(block)
                            now = int(time.monotonic())
                            if now != last_notice:
                                notify(None, f"Obtendo {target.name} · {size / 1024**2:.1f} MB")
                                last_notice = now
                        output.flush()
                        os.fsync(output.fileno())
                    if not size or length is not None and size != length:
                        raise OpenDataError(
                            "Download oficial incompleto; a versão anterior foi preservada."
                        )
                    check()
                    meta = {
                        "url": url,
                        "bytes": size,
                        "sha256": digest.hexdigest(),
                        "etag": response.headers.get("ETag", ""),
                        "last_modified": response.headers.get("Last-Modified", ""),
                        "checked_at": self.clock(),
                        "retry_at": 0,
                        "publication_revision": revision,
                        "transport_policy": TLS_POLICY if os.name == "nt" else "system-openssl-v1",
                    }
                os.replace(temporary, target)
                atomic_json(manifest, meta)
                return target, meta
            except (
                urllib.error.URLError,
                TimeoutError,
                OSError,
                http.client.HTTPException,
                OpenDataError,
            ) as exc:
                # Store a short *file server* circuit, separate from the API's
                # Retry-After. Do not reinterpret a 503 here as an API quota.
                try:
                    stored.update(
                        checked_at=0,
                        retry_at=self.clock() + retry_delay,
                        failure_kind="TLS_CERTIFICATE" if certificate_failure(exc) else "DOWNLOAD",
                        transport_policy=TLS_POLICY if os.name == "nt" else "system-openssl-v1",
                    )
                    atomic_json(manifest, stored)
                except OSError:
                    pass
                message = "Não foi possível obter o arquivo oficial " + target.name + "."
                if certificate_failure(exc):
                    message += (
                        " O certificado HTTPS não foi validado pelo sistema. "
                        "Os dados anteriores foram preservados."
                    )
                raise OpenDataError(message) from exc
            finally:
                temporary.unlink(missing_ok=True)

    @staticmethod
    def _manifest(path):
        try:
            if path.stat().st_size > 8192:
                return {}
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                return {}
            for key in ("checked_at", "retry_at"):
                if type(value.get(key, 0)) not in (int, float) or not math.isfinite(
                    value.get(key, 0)
                ):
                    return {}
            return value
        except (OSError, ValueError, TypeError):
            return {}


class OpenDataRepository:
    def __init__(self, directory, *, files=None):
        self.directory = Path(directory)
        self.files = files or OfficialFiles(self.directory / "originais")
        self.codes = frozenset(p["ncm"] for p in catalog())
        self.headings = frozenset(code[:4] for code in self.codes)

    def availability(self, check, notify, *, force=False, municipal=False):
        path, _ = self.files.fetch(
            "publication.html",
            check=check,
            notify=notify,
            max_size=4 * 1024**2,
            ttl=0 if force else 300,
        )
        text = path.read_text(encoding="utf-8")
        plain = html.unescape(re.sub(r"<[^>]*>", " ", text))
        plain = re.sub(r"\s+", " ", plain)
        match = re.search(
            r"[Úú]ltimos dados dispon[íi]veis\s*:\s*janeiro\s*[-–]\s*(\w+)\s+de\s+(\d{4})", plain
        )
        updated = re.search(r"Atualizado em\s+(\d{2})/(\d{2})/(\d{4})", plain)
        if not match or not updated:
            raise OpenDataError("Não foi possível reconhecer a publicação oficial do MDIC.")
        months = "janeiro fevereiro março abril maio junho julho agosto setembro outubro novembro dezembro".split()
        try:
            month = months.index(match[1].lower()) + 1
            day, mon, year = map(int, updated.groups())
            day = date(year, mon, day).isoformat()
            period = f"{int(match[2]):04d}-{month:02d}"
            if not "1997-01" <= period <= date.today().strftime("%Y-%m"):
                raise ValueError("Mês futuro")
        except ValueError as exc:
            raise OpenDataError("Data inválida na publicação oficial do MDIC.") from exc
        epoch = json_bytes({"period": period, "updated": day}).decode()
        controls, _ = self._controls(municipal, check, notify, revision=epoch, refresh=force)
        latest = max(controls)
        covered = f"{latest[0]:04d}-{latest[1]:02d}"
        if covered != period:
            raise OpenDataError(
                "Os arquivos de conferência e a publicação do MDIC estão em revisões diferentes."
            )
        return {"year": covered[:4], "monthNumber": covered[5:], "updated": day}

    def _references(self, check, notify, *, revision=None, refresh=False):
        result, revisions = {}, {}
        for name, (key, description) in REFERENCES.items():
            path, meta = self.files.fetch(
                "tabelas/" + name + ".csv",
                check=check,
                notify=notify,
                max_size=16 * 1024**2,
                revision=revision,
                ttl=0 if refresh else 300,
            )
            table = {}
            with csv_rows(path, check=check) as reader:
                require_fields(reader, [key, description], name)
                for i, row in enumerate(reader):
                    if i % 512 == 0:
                        check()
                    if None in row or any(value is None for value in row.values()):
                        raise OpenDataError("Linha incompleta na tabela oficial " + name + ".")
                    code = str(integer(row[key], name))
                    label = engine.clean_text(row[description])
                    if not label or code in table and table[code] != label:
                        raise OpenDataError(
                            "Descrição ausente ou divergente na tabela " + name + "."
                        )
                    table[code] = label
            if not table:
                raise OpenDataError("Tabela oficial vazia: " + name + ".")
            result[name], revisions[name] = table, meta["sha256"]
        return result, revisions

    def _controls(self, municipal, check, notify, *, revision=None, refresh=False):
        relative = (
            "comexstat-bd/mun/IMP_TOTAIS_CONFERENCIA_MUN.csv"
            if municipal
            else "comexstat-bd/ncm/IMP_TOTAIS_CONFERENCIA.csv"
        )
        path, meta = self.files.fetch(
            relative,
            check=check,
            notify=notify,
            max_size=4 * 1024**2,
            revision=revision,
            ttl=0 if refresh else 300,
        )
        totals = {}
        with csv_rows(path, check=check) as reader:
            aliases = {"ANO": "CO_ANO", "MES": "CO_MES", "MÊS": "CO_MES"}
            reader.fieldnames = [aliases.get(k, k) for k in reader.fieldnames]
            require_fields(
                reader, ["CO_ANO", "CO_MES", "KG_LIQUIDO", "VL_FOB"], "totais de conferência"
            )
            for row in reader:
                check()
                if None in row or any(value is None for value in row.values()):
                    raise OpenDataError("Linha incompleta nos totais oficiais.")
                year, month = integer(row["CO_ANO"], "ano"), integer(row["CO_MES"], "mês")
                if not 1997 <= year <= date.today().year or not 1 <= month <= 12:
                    raise OpenDataError("Período inválido nos totais de conferência.")
                key = (year, month)
                if key in totals:
                    raise OpenDataError("Totais oficiais duplicados para o mesmo mês.")
                values = {
                    k: integer(row[k], k)
                    for k in ("KG_LIQUIDO", "VL_FOB", "VL_FRETE", "VL_SEGURO")
                    if k in row
                }
                for name in (
                    "QT_REGISTROS",
                    "QTD_REGISTROS",
                    "QT_LINHAS",
                    "QTD_LINHAS",
                    "REGISTROS",
                    "LINHAS",
                ):
                    if name in row:
                        values["rows"] = integer(row[name], name)
                        break
                totals[key] = values
        if not totals:
            raise OpenDataError("O arquivo de totais oficiais está vazio.")
        return totals, meta["sha256"]

    def query(self, body, municipal, check, notify, *, revision=None, refresh=False):
        revision = revision or {}
        epoch = json_bytes(
            {
                "period": revision.get("period"),
                "updated": revision.get("municipal_updated" if municipal else "updated")
                or revision.get("updated"),
            }
        ).decode()
        references, table_revision = self._references(
            check, notify, revision=epoch, refresh=refresh
        )
        controls, controls_sha = self._controls(
            municipal, check, notify, revision=epoch, refresh=refresh
        )
        start, end = body["period"]["from"], body["period"]["to"]
        codes = {
            str(integer(c, "filtro")).zfill(4 if municipal else 8)
            for c in body["filters"][0]["values"]
        }
        if not codes or not codes <= (self.headings if municipal else self.codes):
            raise OpenDataError("O filtro não pertence ao catálogo LIARTE.")
        rows = []
        control_query = body["details"] == ["heading" if municipal else "ncm"]
        for year in range(int(start[:4]), int(end[:4]) + 1):
            check()
            months = {int(m[5:]) for m in engine.iter_periods(start, end) if int(m[:4]) == year}
            if not all((year, month) in controls for month in months):
                raise OpenDataError(
                    "Os totais oficiais ainda não cobrem todos os meses solicitados."
                )
            filename = (
                f"comexstat-bd/mun/IMP_{year}_MUN.csv"
                if municipal
                else f"comexstat-bd/ncm/IMP_{year}.csv"
            )
            path, meta = self.files.fetch(
                filename, check=check, notify=notify, ttl=0 if refresh else 300, revision=epoch
            )
            signature = hashlib.sha256(
                json_bytes(
                    {
                        "schema": SCHEMA,
                        "source": meta["sha256"],
                        "controls": controls_sha,
                        "references": table_revision,
                        "catalog": sorted(self.codes),
                        "municipal": municipal,
                    }
                )
            ).hexdigest()
            index = (
                self.directory
                / "indices"
                / (f"municipal-{year}.json.z" if municipal else f"general-{year}.json.z")
            )
            payload = None if refresh else self._read_index(index, signature, check)
            if payload is None:
                payload = self._ingest(path, year, municipal, references, controls, check, notify)
                payload["signature"] = signature
                payload["source_sha256"] = meta["sha256"]
                self._write_index(index, payload, check)
            for row in payload["controls"] if control_query else payload["rows"]:
                if (
                    start <= engine.row_period(row) <= end
                    and row["headingCode" if municipal else "coNcm"] in codes
                ):
                    rows.append(row.copy())
        # Controls come from a separate raw-row accumulator, not the rendered
        # detailed rows. The engine still reconciles the two per product/month.
        return {"success": True, "data": {"list": rows}}

    def _ingest(self, path, year, municipal, references, controls, check, notify):
        national = defaultdict(lambda: defaultdict(int))
        grouped = {}
        product_totals = {}
        metrics = (
            ("VL_FOB", "KG_LIQUIDO")
            if municipal
            else ("VL_FOB", "VL_FRETE", "VL_SEGURO", "KG_LIQUIDO")
        )
        with csv_rows(path, check=check) as reader:
            require_fields(reader, MUNICIPAL_HEADER if municipal else GENERAL_HEADER, path.name)
            for i, row in enumerate(reader):
                if i % 4096 == 0:
                    check()
                    notify(None, f"Conferindo {path.name} · {i:,} registros".replace(",", "."))
                if None in row or any(value is None for value in row.values()):
                    raise OpenDataError(
                        "Linha incompleta no arquivo anual; nenhuma base foi substituída."
                    )
                current_year = integer(row["CO_ANO"], "ano")
                month = integer(row["CO_MES"], "mês")
                if (
                    current_year != year
                    or not 1 <= month <= 12
                    or f"{year:04d}-{month:02d}" > date.today().strftime("%Y-%m")
                ):
                    raise OpenDataError("Mês ou ano inválido no arquivo anual.")
                values = [integer(row[k], k) for k in metrics]
                totals = national[(year, month)]
                totals["rows"] += 1
                for key, value in zip(metrics, values, strict=True):
                    totals[key] += value
                code = str(integer(row["SH4" if municipal else "CO_NCM"], "classificação")).zfill(
                    4 if municipal else 8
                )
                if code not in (self.headings if municipal else self.codes):
                    continue
                control = product_totals.setdefault((month, code), [0] * len(metrics))
                for n, value in enumerate(values):
                    control[n] += value
                state = row["SG_UF_MUN" if municipal else "SG_UF_NCM"].strip()
                country = str(integer(row["CO_PAIS"], "país"))
                place = str(integer(row["CO_MUN" if municipal else "CO_URF"], "local"))
                key = (month, code, state, country, place)
                if len(code) != (4 if municipal else 8):
                    raise OpenDataError("Classificação fora do layout oficial no arquivo anual.")
                if key not in grouped and len(grouped) >= 500000:
                    raise OpenDataError(
                        "O recorte anual excedeu a capacidade segura de processamento."
                    )
                aggregate = grouped.setdefault(key, [0] * len(metrics))
                for n, value in enumerate(values):
                    aggregate[n] += value
        expected = {key: value for key, value in controls.items() if key[0] == year}
        if not expected or national.keys() != expected.keys():
            raise OpenDataError("Os meses do arquivo anual divergem dos totais oficiais.")
        for key, values in expected.items():
            if any(national[key][metric] != value for metric, value in values.items()):
                raise OpenDataError(
                    f"Totais oficiais divergentes em {key[0]}-{key[1]:02d}; o arquivo foi recusado."
                )
        result = []
        for i, ((month, code, state, country, place), values) in enumerate(sorted(grouped.items())):
            if i % 512 == 0:
                check()
            table = references["NCM_SH" if municipal else "NCM"]
            location = references["UF_MUN" if municipal else "URF"]
            try:
                product, country_name, location_name = (
                    table[str(int(code))],
                    references["PAIS"][country],
                    location[place],
                )
            except KeyError as exc:
                raise OpenDataError(
                    "Código sem descrição nas tabelas oficiais; a base foi recusada."
                ) from exc
            row = {
                "year": str(year),
                "monthNumber": f"{month:02d}",
                "state": state,
                "country": country_name,
                "metricFOB": str(values[0]),
                "metricKG": str(values[-1]),
                "__liarte_source": "mdic-csv",
            }
            if municipal:
                row.update(headingCode=code, heading=product, noMunMinsgUf=location_name)
                engine.validate_municipal_api_row(
                    row, self.headings, f"{year}-01", f"{year}-12", "CSV oficial"
                )
            else:
                row.update(
                    coNcm=code,
                    ncm=product,
                    urf=place.zfill(7) + " - " + location_name,
                    metricFreight=str(values[1]),
                    metricInsurance=str(values[2]),
                    metricCIF=str(sum(values[:3])),
                )
                engine.validate_api_row(row, self.codes, f"{year}-01", f"{year}-12", "CSV oficial")
            result.append(row)
        controls = []
        for (month, code), values in sorted(product_totals.items()):
            row = {
                "year": str(year),
                "monthNumber": f"{month:02d}",
                "headingCode" if municipal else "coNcm": code,
                "metricFOB": str(values[0]),
                "metricKG": str(values[-1]),
            }
            if not municipal:
                row.update(
                    metricFreight=str(values[1]),
                    metricInsurance=str(values[2]),
                    metricCIF=str(sum(values[:3])),
                )
            controls.append(row)
        return {
            "schema": SCHEMA,
            "rows": result,
            "controls": controls,
            "national_totals": {f"{k[0]}-{k[1]:02d}": dict(v) for k, v in national.items()},
        }

    @staticmethod
    def _read_index(path, signature, check):
        try:
            if path.stat().st_size > MAX_INDEX:
                return None
            packed = path.read_bytes()
            if len(packed) < 64:
                return None
            digest, compressed = packed[:64].decode("ascii"), packed[64:]
            unpack = zlib.decompressobj()
            raw = unpack.decompress(compressed, MAX_INDEX + 1)
            check()
            if (
                len(raw) > MAX_INDEX
                or not unpack.eof
                or unpack.unused_data
                or hashlib.sha256(raw).hexdigest() != digest
            ):
                return None
            payload = json.loads(raw)
            if (
                payload.get("schema") != SCHEMA
                or payload.get("signature") != signature
                or not isinstance(payload.get("rows"), list)
                or not isinstance(payload.get("controls"), list)
            ):
                return None
            return payload
        except (OSError, ValueError, TypeError, zlib.error):
            return None

    @staticmethod
    def _write_index(path, payload, check):
        raw = json_bytes(payload)
        if len(raw) > MAX_INDEX:
            raise OpenDataError("O índice oficial excedeu o limite de segurança.")
        packed = hashlib.sha256(raw).hexdigest().encode("ascii") + zlib.compress(raw)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + "." + uuid4().hex + ".part")
        try:
            with temporary.open("xb") as handle:
                handle.write(packed)
                handle.flush()
                os.fsync(handle.fileno())
            check()
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
