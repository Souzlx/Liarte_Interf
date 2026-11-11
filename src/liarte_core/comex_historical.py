"""Consultas locais do Comex, independentes da aquisição oficial em segundo plano."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from threading import Event

from liarte_engine import comexstat_importacoes as engine

from .catalog import catalog
from .comex import Availability, ComexError, ComexProvider, Snapshot
from .comex_api import ApiClient
from .comex_history import HistoryError, HistoryStore, HistoryUnavailable
from .comex_sync import HistorySynchronizer
from .domain import Period
from .query import Cancelled, checkpoint


@dataclass(frozen=True, slots=True)
class HistoricalSnapshot(Snapshot):
    """A revisão e os horários pertencem às partições lidas, não ao último GET."""

    historical: bool = True
    local_revision: str = ""
    source_publication: tuple[tuple[str, str], ...] = ()


class HistoricalComexProvider(ComexProvider):
    """O worker de consultas só lê a geração aceita no banco local.

    A sincronização tem seu próprio cancelamento e geração. Cancelar uma análise
    não descarta estágios adquiridos nem interrompe uma atualização independente.
    """

    is_historical = True

    def __init__(
        self,
        directory: Path,
        *,
        codes=None,
        client_factory=None,
        history=None,
        synchronizer_factory=HistorySynchronizer,
        sync_options=None,
    ):
        if isinstance(codes, (str, bytes)):
            raise ValueError("Informe uma sequência de códigos dos produtos acompanhados.")
        values = codes if codes is not None else (item["ncm"] for item in catalog())
        try:
            normalized = tuple(sorted({engine.normalize_ncm(code) for code in values}))
        except (TypeError, ValueError) as exc:
            raise ValueError("O catálogo contém um NCM inválido.") from exc
        if not normalized or None in normalized or len(normalized) > 200:
            raise ValueError("Informe entre 1 e 200 NCMs válidos no catálogo.")
        if client_factory is not None and not callable(client_factory):
            raise ValueError("O adaptador de aquisição deve ser chamável.")

        # The direct provider supplies conversion and the existing shared API
        # pause. Its seed restriction does not define this configured catalogue.
        super().__init__(directory, client_factory=ApiClient)
        self.codes = normalized
        self.client_factory = client_factory or ApiClient
        self._native_api = True
        self._history_owned = history is None
        self.history = history if history is not None else HistoryStore(
            self.directory / "historico_comex.sqlite3", self.codes
        )
        if tuple(self.history.codes) != self.codes:
            raise ValueError("O histórico local pertence a outro catálogo de produtos.")
        self._synchronizer_factory = synchronizer_factory
        self._sync_options = dict(sync_options or {})
        if "publication_guard" in self._sync_options:
            raise ValueError("A guarda de publicação pertence ao provedor.")
        self._history_sync_generation = 0
        self._history_closed = False

    def _history_identity(self):
        return self.history, tuple(self.codes), self.client_factory

    def _check_history_catalog(self):
        if tuple(self.history.codes) != tuple(self.codes):
            raise ComexError(
                "O catálogo de produtos mudou. Reconfigure a atualização do histórico local."
            )

    @staticmethod
    def _rows(rows, municipal, codes, period, cancel):
        """Recheck the read boundary and never mutate an accepted raw snapshot."""
        validate = engine.validate_municipal_api_row if municipal else engine.validate_api_row
        identity = engine.municipal_row_identity if municipal else engine.api_row_identity
        signature = engine.municipal_metric_signature if municipal else engine.api_metric_signature
        allowed = {code[:4] for code in codes} if municipal else set(codes)
        accepted = {}
        for index, row in enumerate(rows):
            if index % 512 == 0:
                checkpoint(cancel)
            if not isinstance(row, dict):
                raise ComexError("O histórico local contém um registro inválido.")
            validate(row, allowed, period.start, period.end, "histórico local")
            key = identity(row)
            previous = accepted.get(key)
            if previous is not None and signature(previous) != signature(row):
                raise ComexError("O histórico local contém registros duplicados divergentes.")
            accepted[key] = dict(row)
        checkpoint(cancel)
        return tuple(accepted.values())

    @staticmethod
    def _product_options(records, cancel):
        # This bounded catalogue is prepared by the worker. GUI properties must
        # not scan every historical row to build a product selector.
        latest = {}
        for index, row in enumerate(records):
            if index % 512 == 0:
                checkpoint(cancel)
            label = row.official_description or row.product
            candidate = row.period, label
            previous = latest.get(row.ncm)
            if previous is None or candidate > previous:
                # A stable lexical tie-break keeps equal-period descriptions
                # independent of response order without altering source rows.
                latest[row.ncm] = candidate
        checkpoint(cancel)
        return tuple((code, latest[code][1]) for code in sorted(latest))

    def load(self, period: Period, cancel: Event, progress):
        checkpoint(cancel)
        with self._lock:
            if self._history_closed:
                raise Cancelled()
            self._check_history_catalog()
            identity = self._history_identity()
            generation = self._operation_generation
            history = self.history
            current = self._snapshot
            refresh = self._refresh_next

        try:
            revision = history.period_revision(period)
            checkpoint(cancel)
            if (
                current is not None and current.period == period and not refresh
                and current.local_revision == revision and revision
            ):
                with self._lock:
                    self._check_query_boundary(cancel, generation, identity)
                    self._check_period_revision(history, period, revision)
                    self._refresh_next = self._revalidate_next = False
                return current

            progress(3, "Lendo o período no histórico local")
            data = history.read(period, cancel)
            general = self._rows(data.general, False, identity[1], period, cancel)
            municipal = self._rows(data.municipal, True, identity[1], period, cancel)
            progress(35, "Conferindo os registros do histórico local")
            general_records, municipal_records = self._convert(general, municipal, cancel)
            publication = data.publication
            checked_at = data.checked_at
            if not checked_at:
                raise ComexError("A referência de conferência da base local está indisponível.")
            availability = Availability(
                publication["latest"], publication["updated"], checked_at,
                cached=True,
                municipal_latest=publication["municipal_latest"],
                municipal_updated=publication["municipal_updated"],
                confirmed=True,
            )
            snapshot = HistoricalSnapshot(
                period=period,
                general=general,
                municipal=municipal,
                general_records=general_records,
                municipal_records=municipal_records,
                availability=availability,
                fetched_at=data.fetched_at,
                cache_hits=1,
                api_requests=0,
                totals_verified=False,
                source_channels=("comex-api", "local-history"),
                response_validated=True,
                acquisition_started_at=data.acquisition_started_at,
                general_received_at=data.general_received_at,
                municipal_received_at=data.municipal_received_at,
                local_revision=data.local_revision,
                source_publication=tuple(sorted(publication.items())),
            )
            options = {}
            for kind, records in (("general", general_records), ("municipal", municipal_records)):
                checkpoint(cancel)
                options[kind] = {
                    "countries": sorted({row.country for row in records}),
                    "states": sorted({row.state for row in records}),
                    "ports": sorted({row.port for row in records if row.port}),
                    "cities": sorted({row.city for row in records}) if kind == "municipal" else [],
                    "headings": sorted({(row.heading, row.product) for row in records})
                    if kind == "municipal" else [],
                }
            options["general"]["products"] = self._product_options(general_records, cancel)
            # Synchronization takes this same lock across its manifest commit.
            # An older read must not replace the current view after that commit.
            # Existing exports continue holding their own immutable snapshot.
            progress(80, "Histórico local carregado")
            with self._lock:
                self._check_query_boundary(cancel, generation, identity)
                self._check_period_revision(history, period, data.local_revision)
                self._snapshot = snapshot
                self._options = options
                self._general._rows = snapshot.general_records
                self._municipal._rows = snapshot.municipal_records
                self._refresh_next = self._revalidate_next = False
            return snapshot
        except HistoryUnavailable as exc:
            raise ComexError(
                "O histórico local ainda não cobre todo o período solicitado. "
                "Acompanhe a carga e a cobertura da base."
            ) from exc
        except HistoryError as exc:
            raise ComexError("Não foi possível ler a base local de importações.") from exc
        except engine.ComexStatError as exc:
            raise ComexError("O histórico local não passou na validação: " + str(exc)[:400]) from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise ComexError("O histórico local contém dados ou metadados inválidos.") from exc

    def _check_query_boundary(self, cancel, generation, identity):
        checkpoint(cancel)
        if (
            self._history_closed or generation != self._operation_generation
            or identity != self._history_identity()
        ):
            raise ComexError("A consulta foi cancelada ou a origem local mudou. Consulte novamente.")

    @staticmethod
    def _check_period_revision(history, period, revision):
        if not revision or history.period_revision(period) != revision:
            raise ComexError("A base local foi atualizada durante a consulta. Consulte novamente.")

    def cached_query(self, selection):
        with self._lock:
            current = self._snapshot
            if (
                self._history_closed or current is None or current.period != selection.period
                or self._refresh_next or self._revalidate_next
            ):
                return None
            history = self.history
            identity = self._history_identity()
        try:
            revision = history.period_revision(selection.period)
        except HistoryError:
            return None
        with self._lock:
            if (
                self._snapshot is not current or identity != self._history_identity()
                or current.local_revision != revision or not revision
            ):
                return None
            local = self._municipal if selection.kind == "municipal" else self._general
            return local.cached_query(selection)

    def synchronize(self, cancel: Event, progress, *, force=False, audit=False):
        checkpoint(cancel)
        with self._lock:
            if self._history_closed:
                raise Cancelled()
            self._check_history_catalog()
            generation = self._history_sync_generation
            identity = self._history_identity()
            history = self.history

        def check_sync():
            checkpoint(cancel)
            if (
                self._history_closed or generation != self._history_sync_generation
                or identity != self._history_identity()
            ):
                raise Cancelled()

        @contextmanager
        def publication_guard():
            with self._lock:
                check_sync()
                yield

        def create_client(client_cancel, client_progress):
            with self._lock:
                check_sync()
                client = self._client(client_cancel, client_progress)
            # A source replacement must stop the old request at its next
            # transport checkpoint, not merely at the final SQLite commit.
            original = getattr(client, "cancel_check", None)

            def check_client():
                if original is not None:
                    original()
                check_sync()

            client.cancel_check = check_client
            return client

        syncer = self._synchronizer_factory(
            history, create_client, self._convert,
            publication_guard=publication_guard, **self._sync_options,
        )
        return syncer.synchronize(cancel, progress, force=force, audit=audit)

    def history_status(self):
        return self.history.status()

    def has_local_period(self, start, end):
        try:
            return self.history.contains(Period(start, end))
        except (HistoryError, ValueError):
            return False

    def local_period_revision(self, start, end):
        try:
            return self.history.period_revision(Period(start, end))
        except (HistoryError, ValueError):
            return ""

    def access_status(self):
        state = self._api_pause.snapshot()
        state.update(
            historical_mode=True,
            resume_pending=False, resume_start="", resume_end="",
            resume_started_at="", resume_received_at="", resume_valid_seconds=0,
            resume_expired=False, resume_unavailable=False,
        )
        return state

    def availability(self, cancel, *, force=False):
        checkpoint(cancel)
        status = self.history.status()
        publication = status.get("publication") or {}
        if not publication:
            raise ComexError("A carga inicial do histórico local ainda não foi concluída.")
        checked_at = status.get("checked_at")
        if not checked_at:
            raise ComexError("A referência de atualização da base local está indisponível.")
        return Availability(
            publication["latest"], publication["updated"], checked_at,
            cached=True,
            municipal_latest=publication["municipal_latest"],
            municipal_updated=publication["municipal_updated"],
            confirmed=True,
        )

    def connection_changed(self):
        with self._lock:
            self._history_sync_generation += 1
            self._availability = None
            self._availability_time = 0
            self._discard_incomplete_locked()
            if self._history_owned:
                self.history = HistoryStore(self.directory / "historico_comex.sqlite3", self.codes)
            self._refresh_next = False
            self._revalidate_next = True

    def close(self):
        with self._lock:
            self._history_closed = True
            self._history_sync_generation += 1
            self._discard_incomplete_locked()
