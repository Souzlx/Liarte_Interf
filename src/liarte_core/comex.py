"""Adaptador Comex Stat real; dados gerais e municipais nunca são cruzados como fatos."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from concurrent.futures import ThreadPoolExecutor
import json
import hashlib
import logging
import math
from pathlib import Path
from threading import Event, Lock
import time

from liarte_engine import comexstat_importacoes as engine
from liarte_engine.liarte_dados import atomic_json
from liarte_engine.numeric import published_units
from liarte_engine.pdf_importacoes import commercial_product_name, display_country
from liarte_engine.comex_gateway_client import GatewayError, load_connection
from .catalog import catalog
from .domain import ImportRecord, MunicipalRecord, Period, selected_values
from .query import DatasetQuery, checkpoint
from .comex_api import ApiClient, ApiPause

LOGGER = logging.getLogger("liarte.desktop")


class ComexError(RuntimeError):
    """Erro de acesso/contrato que pode ser apresentado sem expor uma pilha técnica."""


def integral(value, *, cents=False):
    # A API publica estas métricas sem separador de milhar. Nunca arredondar
    # silenciosamente peso ou uma fração de centavo que o contrato não suporta.
    try:
        return published_units(value, places=2 if cents else 0)
    except ValueError as exc:
        raise ComexError(str(exc)) from exc


def uf(value):
    label = engine.state_abbreviation(value)
    if label in engine.STATE_ABBREVIATIONS.values():
        return label
    if engine.text_key(value) in (
        "NAO DECLARADA",
        "NAO DECLARADO",
        "NAO IDENTIFICADA",
        "NAO IDENTIFICADO",
        "ND",
        "99",
    ):
        return "ND"
    if engine.text_key(value) in ("EXTERIOR", "EX", "98"):
        return "EX"
    raise ComexError(
        f"UF não reconhecida na resposta oficial: {engine.clean_text(value)[:80]}."
    )


@dataclass(frozen=True, slots=True)
class Availability:
    latest: str
    updated: str
    checked_at: str
    cached: bool = False
    municipal_latest: str = ""
    municipal_updated: str = ""
    confirmed: bool = True

    def __post_init__(self):
        if not all(
            isinstance(v, str)
            for v in (
                self.latest,
                self.updated,
                self.checked_at,
                self.municipal_latest,
                self.municipal_updated,
            )
        ):
            raise ComexError("Metadados de disponibilidade inválidos.")
        for value in (self.latest, self.municipal_latest):
            if value:
                Period("1997-01", value)
                if value > date.today().strftime("%Y-%m"):
                    raise ComexError("Metadados informam um mês futuro.")
        for value in (self.updated, self.municipal_updated):
            if value:
                date.fromisoformat(value)
        datetime.fromisoformat(self.checked_at)


@dataclass(frozen=True, slots=True)
class Snapshot:
    period: Period
    general: tuple[dict, ...]
    municipal: tuple[dict, ...]
    general_records: tuple[ImportRecord, ...]
    municipal_records: tuple[MunicipalRecord, ...]
    availability: Availability
    fetched_at: str
    cache_hits: int
    api_requests: int
    totals_verified: bool = False
    shared_cache_hits: int = 0
    source_channels: tuple[str, ...] = ()
    response_validated: bool = False


class ComexProvider:
    is_demo = False

    def __init__(
        self,
        directory: Path,
        *,
        client_factory=None,
        codes=None,
        automatic_access=False,
        verify_official_totals=False,
    ):
        self.directory = Path(directory)
        # A aplicação usa exclusivamente a API. O opt-in legado é conservado
        # para ferramentas de migração e regressão; não é exposto no desktop.
        automatic = bool(automatic_access)
        self.direct_api = not automatic
        self.client_factory = client_factory or (engine.ComexStatClient if automatic or verify_official_totals else ApiClient)
        self._native_api = self.client_factory is ApiClient
        self._api_pause = ApiPause(self.directory / "acesso_api.json") if self._native_api else None
        if self._api_pause is not None and (self.directory / "acesso_comex.sqlite3").is_file():
            # Migra somente uma pausa real ainda vigente. Não importa a fila,
            # intervalos preventivos ou resultados de consultas de versões antigas.
            from liarte_engine.comex_access import RequestCoordinator

            previous_pause = RequestCoordinator.peek(self.directory / "acesso_comex.sqlite3")
            if previous_pause["pause_seconds"]:
                self._api_pause.defer(previous_pause["pause_seconds"], 429)
        self._verify_official_totals = automatic or bool(verify_official_totals)
        if automatic:
            from .comex_automatic import AutomaticAccess

            self._automatic = AutomaticAccess(self.directory)
        else:
            self._automatic = None
        allowed = {item["ncm"] for item in catalog()}
        if isinstance(codes, (str, bytes)):
            raise ValueError("Informe uma sequência de códigos do cadastro LIARTE.")
        self.codes = tuple(sorted(set(codes if codes is not None else allowed)))
        if not self.codes or not set(self.codes) <= allowed:
            raise ValueError("Código fora do cadastro LIARTE.")
        self._availability = None
        self._availability_time = 0.0
        self._snapshot = None
        self._options = {
            k: {
                "countries": [],
                "states": [],
                "ports": [],
                "cities": [],
                "headings": [],
            }
            for k in ("general", "municipal")
        }
        self._lock = Lock()
        self._general = DatasetQuery()
        self._municipal = DatasetQuery()
        self._refresh_next = False
        self._revalidate_next = False
        if self._automatic is not None:
            self._automatic.start_managed()

    @property
    def snapshot(self):
        with self._lock:
            return self._snapshot

    def cancel_pending_options(self):
        self._refresh_next = False
        self._revalidate_next = False

    def revalidate_next(self):
        self._refresh_next = False
        self._revalidate_next = True

    def connection_changed(self):
        """Chamado apenas com os workers parados; preserva a última consulta válida."""
        self._availability = None
        self._availability_time = 0
        self.revalidate_next()

    def force_refresh(self):
        self._refresh_next = True

    def close(self):
        if self._automatic is not None:
            self._automatic.close()

    def access_status(self):
        if self._api_pause is not None:
            return {"pause_seconds": min(2**31 - 1, math.ceil(self._api_pause.remaining()))}
        from liarte_engine.comex_access import RequestCoordinator

        # An API pause does not block the independent official file source.
        # The source adapter continues respecting that pause internally.
        if not self.direct_api and self.client_factory is engine.ComexStatClient:
            return {"pause_seconds": 0}
        return RequestCoordinator.peek(self.directory / "acesso_comex.sqlite3")

    def _record_failure(self, event):
        record = dict(event)
        record["response_excerpt"] = str(record.get("response_excerpt", ""))[:1500]
        record["excerpt_sha256"] = hashlib.sha256(
            record["response_excerpt"].encode()
        ).hexdigest()
        try:
            atomic_json(self.directory / "ultima_falha_comex.json", record)
        except OSError:
            LOGGER.warning("Não foi possível salvar o diagnóstico da API.")
        LOGGER.warning(
            "API Comex Stat HTTP %s em %s. Retry-After: %s. Resposta: %s",
            record.get("observed_http_status"),
            record.get("endpoint"),
            record.get("retry_after_header", ""),
            record["response_excerpt"],
        )

    def _client(self, cancel, progress=None, *, cache=True, refresh=False):
        if self.direct_api:
            # Não lê pareamentos antigos, não abre porta HTTP e não utiliza
            # respostas de disco. Cada consulta explícita obtém dados da API.
            return self.client_factory(
                timeout=120,
                min_interval=0.0,
                max_attempts=2 if self._native_api else 1,
                use_cache=False,
                coordinator_path=self.directory / ("acesso_api.json" if self._native_api else "acesso_comex.sqlite3"),
                gateway=None,
                cancel_check=lambda: checkpoint(cancel),
                cancel_wait=cancel.wait,
                progress_callback=progress,
                failure_callback=self._record_failure,
                verify_official_totals=self._verify_official_totals,
                window_months=None,
                **({"pause_state": self._api_pause} if self._native_api else {}),
            )
        try:
            connection = load_connection(self.directory / "conexao_comex.json")
        except GatewayError as exc:
            raise engine.ComexStatError(str(exc)) from exc
        gateway = connection if connection.enabled else self._automatic
        if self._automatic is not None:
            try:
                gateway = self._automatic.gateway(connection)
            except GatewayError as exc:
                raise engine.ComexStatError(str(exc)) from exc
        return self.client_factory(
            timeout=25,
            min_interval=15.0,
            max_attempts=3,
            use_cache=cache,
            cache_path=self.directory / "consultas.sqlite3",
            refresh_cache=refresh,
            coordinator_path=self.directory / "acesso_comex.sqlite3",
            gateway=gateway,
            source_revision=(
                {
                    "period": self._availability.latest,
                    "updated": self._availability.updated,
                    "municipal_updated": self._availability.municipal_updated,
                    "acquisition": "mdic-files-and-api-v1",
                }
                if self._availability
                else None
            ),
            cancel_check=lambda: checkpoint(cancel),
            cancel_wait=cancel.wait,
            progress_callback=progress,
        )

    def availability(self, cancel: Event, *, force=False):
        checkpoint(cancel)
        if (
            self._availability
            and not force
            and time.monotonic() - self._availability_time < 300
        ):
            return self._availability
        client = self._client(cancel, cache=False, refresh=force)
        city_client = None
        try:
            # Tiny, independent metadata endpoints; dataset POSTs remain serial
            # and rate limited. Never do this work on the GUI thread.
            if self.direct_api:
                # Uma falha encerra esta verificação, sem deixar uma segunda
                # chamada concorrente repetindo acessos durante a mesma pausa.
                latest, updated = client.latest_published_period()
                city_data = client.request_json("GET", "/cities/dates/updated").get(
                    "data", {}
                )
            else:
                city_client = self._client(cancel, cache=False, refresh=force)
                with ThreadPoolExecutor(
                    max_workers=2, thread_name_prefix="liarte-metadados"
                ) as pool:
                    general_future = pool.submit(client.latest_published_period)
                    city_future = pool.submit(
                        city_client.request_json, "GET", "/cities/dates/updated"
                    )
                    latest, updated = general_future.result()
                    city_data = city_future.result().get("data", {})
            if not isinstance(city_data, dict):
                raise ComexError(
                    "A disponibilidade municipal retornou um formato inválido."
                )
            city_latest = f"{city_data.get('year', '')}-{str(city_data.get('monthNumber', '')).zfill(2)}"
            Period("1997-01", city_latest)
            if max(latest, city_latest) > date.today().strftime("%Y-%m"):
                raise ComexError(
                    "A API informou um mês futuro; disponibilidade não confirmada."
                )
            checked = datetime.now(timezone.utc).isoformat(timespec="seconds")
            availability = Availability(
                latest,
                str(updated or ""),
                checked,
                False,
                city_latest,
                str(city_data.get("updated", "")),
            )
            self._availability = availability
            self._availability_time = time.monotonic()
            try:
                atomic_json(
                    self.directory / "disponibilidade.json",
                    {
                        "latest": latest,
                        "updated": availability.updated,
                        "checked_at": checked,
                        "municipal_latest": availability.municipal_latest,
                        "municipal_updated": availability.municipal_updated,
                    },
                )
            except OSError:
                pass  # Cache failure never replaces a valid official response.
            return availability
        except (engine.ComexStatError, ComexError, OSError, ValueError) as exc:
            checkpoint(cancel)
            if self.direct_api and force:
                raise ComexError(
                    "Não foi possível confirmar a publicação pela API do Comex Stat: "
                    + str(exc)[:400]
                ) from exc
            try:
                path = self.directory / "disponibilidade.json"
                if path.stat().st_size > 64 * 1024:
                    raise ValueError("Cache de metadados excessivo.")
                stored = json.loads(path.read_text(encoding="utf-8"))
                Period("1997-01", stored["latest"])
                availability = Availability(
                    stored["latest"],
                    stored["updated"],
                    stored["checked_at"],
                    True,
                    stored.get("municipal_latest", stored["latest"]),
                    stored.get("municipal_updated", stored["updated"]),
                )
            except (OSError, ValueError, ComexError, KeyError, TypeError):
                raise ComexError(
                    "Não foi possível confirmar a disponibilidade do Comex Stat. Verifique a conexão e tente novamente."
                ) from exc
            self._availability = availability
            # Offline fallback is explicit and retried on the next query.
            return availability
        finally:
            client.close()
            if city_client is not None:
                city_client.close()

    def _convert(self, general, municipal, cancel):
        generals = []
        municipals = []
        for i, row in enumerate(general):
            if i % 512 == 0:
                checkpoint(cancel)
            fob = integral(row["metricFOB"], cents=True)
            freight = integral(row["metricFreight"], cents=True)
            insurance = integral(row["metricInsurance"], cents=True)
            if fob + freight + insurance != integral(row["metricCIF"], cents=True):
                raise ComexError(
                    "CIF divergente de FOB + frete + seguro. Os dados não foram publicados."
                )
            code = engine.normalize_ncm(row["coNcm"])
            generals.append(
                ImportRecord(
                    i,
                    engine.row_period(row),
                    code,
                    commercial_product_name(code, row["ncm"]),
                    uf(row["state"]),
                    display_country(row["country"]),
                    engine.clean_text(row["urf"]),
                    fob,
                    freight,
                    insurance,
                    integral(row["metricKG"]),
                    engine.clean_text(row["ncm"]),
                )
            )
        for i, row in enumerate(municipal):
            if i % 512 == 0:
                checkpoint(cancel)
            municipals.append(
                MunicipalRecord(
                    i,
                    engine.row_period(row),
                    engine.normalize_heading(row["headingCode"]),
                    engine.clean_text(row["heading"]),
                    uf(row["state"]),
                    display_country(row["country"]),
                    engine.municipal_name(row),
                    integral(row["metricFOB"], cents=True),
                    integral(row["metricKG"]),
                )
            )
        return tuple(generals), tuple(municipals)

    def load(self, period, cancel, progress):
        refresh = self._refresh_next
        current = self.snapshot
        # Consultar baixa cada base uma vez. Filtros e páginas utilizam apenas
        # o resultado já carregado; metadados têm uma ação manual independente.
        if (
            current is not None
            and current.period == period
            and not refresh
            and not self._revalidate_next
        ):
            return current
        checkpoint(cancel)
        if self.direct_api:
            today = date.today()
            last_complete = date(today.year, today.month, 1).toordinal() - 1
            if period.start < "1997-01" or period.end > date.fromordinal(
                last_complete
            ).strftime("%Y-%m"):
                raise ComexError(
                    "Selecione um período a partir de 1997 e anterior ao mês atual."
                )
            # A resposta de dados não certifica a última data de publicação.
            # Não inventar essa informação a partir do período solicitado.
            availability = Availability(
                "",
                "",
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
                confirmed=False,
            )
        else:
            availability = self.availability(cancel, force=refresh)
            if period.start < "1997-01" or period.end > availability.latest:
                raise ComexError(
                    f"O Comex Stat possui dados publicados até {availability.latest}."
                )
            if (
                availability.municipal_latest
                and period.end > availability.municipal_latest
            ):
                raise ComexError(
                    f"A base municipal está publicada até {availability.municipal_latest}. Selecione um período coberto pelas duas bases."
                )
        progress(3, "Baixando dados gerais do Comex Stat")

        def report_general(fraction, message):
            progress(5 + int(42 * (fraction or 0)), message)

        client = self._client(cancel, report_general, refresh=refresh)
        try:
            general = client.query_imports(self.codes, period.start, period.end, 50)
            checkpoint(cancel)
            client.progress_callback = lambda fraction, message: progress(
                48 + int(32 * (fraction or 0)), message
            )
            municipal = client.query_municipal_imports(
                self.codes, period.start, period.end, 50
            )
            checkpoint(cancel)
            # Complete both endpoints and validate them before replacing anything.
            general_records, municipal_records = self._convert(
                general, municipal, cancel
            )
            cache = client.cache
            stats = cache.stats if cache is not None else {}
            snapshot = Snapshot(
                period,
                tuple(general),
                tuple(municipal),
                general_records,
                municipal_records,
                availability,
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
                stats.get("hits", 0),
                getattr(client, "network_requests", 0)
                if self.direct_api
                else max(
                    0,
                    stats.get("requests", 0)
                    + getattr(client, "control_requests", 0)
                    - getattr(client, "shared_cache_hits", 0),
                ),
                self._verify_official_totals,
                getattr(client, "shared_cache_hits", 0),
                tuple(
                    sorted(
                        {
                            r.get("__liarte_source", "comex-api")
                            for r in (*general, *municipal)
                        }
                    )
                ),
                True,
            )
            checkpoint(cancel)
            options = {}
            for kind, records in (
                ("general", general_records),
                ("municipal", municipal_records),
            ):
                options[kind] = {
                    "countries": sorted({r.country for r in records}),
                    "states": sorted({r.state for r in records}),
                    "ports": sorted({r.port for r in records if r.port}),
                    "cities": sorted({r.city for r in records})
                    if kind == "municipal"
                    else [],
                    "headings": sorted({(r.heading, r.product) for r in records})
                    if kind == "municipal"
                    else [],
                }
            with self._lock:
                self._snapshot = snapshot
                self._options = options
            self._general._rows = snapshot.general_records
            self._municipal._rows = snapshot.municipal_records
            self._refresh_next = False
            self._revalidate_next = False
            return snapshot
        except engine.ComexStatError as exc:
            raise ComexError(
                "Consulta oficial não concluída: " + str(exc)[:500]
            ) from exc
        finally:
            client.close()

    def cached_query(self, selection):
        """A prepared local view; never bypass an explicit source revalidation.

        The controller calls this only when no query worker is running.
        """
        with self._lock:
            if (
                self._snapshot is None
                or self._snapshot.period != selection.period
                or self._refresh_next
                or self._revalidate_next
            ):
                return None
            local = self._municipal if selection.kind == "municipal" else self._general
            return local.cached_query(selection)

    def query(self, selection, cancel, progress):
        checkpoint(cancel)
        allowed = (
            set(self.codes)
            if selection.kind == "general"
            else {code[:4] for code in self.codes}
        )
        if not set(selected_values(selection, "ncm")) <= allowed:
            raise ComexError(
                "A classificação selecionada não pertence à base consultada."
            )
        self.load(selection.period, cancel, progress)
        local = self._municipal if selection.kind == "municipal" else self._general
        return local.query(
            selection, cancel, lambda p, m: progress(82 + int(p * 0.18), m)
        )

    def options(self, kind):
        with self._lock:
            return self._options[kind].copy()
