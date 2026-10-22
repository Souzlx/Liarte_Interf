"""Consulta local imutável: filtros, totais, busca, ordenação e paginação."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from heapq import merge
from threading import Event
from typing import Callable, Protocol

from .domain import (
    ImportRecord,
    MunicipalRecord,
    Selection,
    period_label,
    search_key,
    selected_values,
    record_predicate,
)
from .procurement import Procurement, ProcurementBuilder


class Cancelled(Exception):
    """Cancelamento cooperativo, sem resultado parcial."""


def checkpoint(cancel: Event):
    if cancel.is_set():
        raise Cancelled()


@dataclass(frozen=True, slots=True)
class Totals:
    records: int
    fob_cents: int
    value_cents: int
    kg: int
    ncms: int
    countries: int
    basis: str = "CIF"

    @property
    def price(self) -> Decimal | None:
        return Decimal(self.value_cents) / 100 / self.kg if self.kg else None

    @property
    def cif_cents(self):
        if self.basis != "CIF":
            raise ValueError("A base municipal não publica CIF.")
        return self.value_cents


@dataclass(frozen=True, slots=True)
class QueryResult:
    selection: Selection
    rows: tuple[ImportRecord | MunicipalRecord, ...]
    totals: Totals
    table_count: int
    page: int
    pages: int
    monthly: tuple[tuple[str, int], ...]
    countries: tuple[tuple[str, int], ...]
    dataset_size: int
    procurement: Procurement


@dataclass(frozen=True, slots=True)
class _Scope:
    rows: tuple[ImportRecord | MunicipalRecord, ...]
    totals: Totals
    monthly: tuple[tuple[str, int], ...]
    countries: tuple[tuple[str, int], ...]
    procurement: Procurement


Progress = Callable[[int, str], None]


class ImportProvider(Protocol):
    def query(self, selection: Selection, cancel: Event, progress: Progress) -> QueryResult: ...


class DatasetQuery:
    """Uso serial por um worker do controlador; nunca é cache de dados oficiais.

    Quatro recortes, seis ordenações e apenas um índice de busca em memória.
    Mudança da fonte invalida tudo. Publica apenas estruturas completas e imutáveis.
    cached_query permite ler uma página já pronta na thread visual, somente quando
    o controlador não possui worker de consulta em execução.
    """

    SCOPE_LIMIT = 4
    VIEW_LIMIT = 6
    SORT_BATCH = 4096

    def __init__(self, rows=()):
        self._rows = rows
        self._cache_source = None
        self._scopes = OrderedDict()
        self._views = OrderedDict()
        self._search_rows = None
        self._search_texts = ()
        self._statistics = dict(
            scope_builds=0, scope_hits=0, view_builds=0, view_hits=0, search_builds=0
        )

    @property
    def cache_info(self):
        return dict(self._statistics, scopes=len(self._scopes), views=len(self._views))

    @staticmethod
    def _remember(cache, key, value, limit):
        cache[key] = value
        cache.move_to_end(key)
        while len(cache) > limit:
            cache.popitem(last=False)

    def _dataset(self, cancel, progress):
        checkpoint(cancel)
        return self._rows

    def _scope(self, source, selection, key, cancel, progress):
        if key in self._scopes:
            self._statistics["scope_hits"] += 1
            self._scopes.move_to_end(key)
            progress(80, "Aplicando os filtros da análise")
            return self._scopes[key]
        selected = []
        fob = cif = kg = 0
        ncms, countries = set(), set()
        monthly = {m: 0 for m in selection.period.months}
        country_totals = {}
        procurement = ProcurementBuilder(selection.period.months, selection.kind == "municipal")
        matches = record_predicate(selection)
        for i, row in enumerate(source):
            if i % 2048 == 0:
                checkpoint(cancel)
                progress(45 + int(i * 35 / max(1, len(source))), "Aplicando período e filtros")
            if not matches(row):
                continue
            selected.append(row)
            procurement.add(row)
            fob += row.fob_cents
            cif += row.value_cents
            kg += row.kg
            ncms.add(row.code)
            countries.add(row.country)
            monthly[row.period] += row.value_cents
            country_totals[row.country] = country_totals.get(row.country, 0) + row.value_cents
        scope = _Scope(
            tuple(selected),
            Totals(
                len(selected),
                fob,
                cif,
                kg,
                len(ncms),
                len(countries),
                "FOB" if selection.kind == "municipal" else "CIF",
            ),
            tuple(monthly.items()),
            tuple(sorted(country_totals.items(), key=lambda x: (-x[1], x[0]))),
            procurement.finish(lambda: checkpoint(cancel)),
        )
        checkpoint(cancel)
        self._remember(self._scopes, key, scope, self.SCOPE_LIMIT)
        self._statistics["scope_builds"] += 1
        return scope

    def _search(self, rows, terms, cancel, progress):
        if not terms:
            return rows
        if self._search_rows is not rows:
            texts = []
            for i, row in enumerate(rows):
                if i % 1024 == 0:
                    checkpoint(cancel)
                    progress(81, "Preparando a busca na tabela")
                texts.append(
                    search_key(
                        " ".join(
                            (
                                row.code,
                                row.product,
                                row.state,
                                row.country,
                                row.port,
                                getattr(row, "city", ""),
                                getattr(row, "official_description", ""),
                                row.period,
                                period_label(row.period),
                            )
                        )
                    )
                )
            checkpoint(cancel)
            self._search_rows, self._search_texts = rows, tuple(texts)
            self._statistics["search_builds"] += 1
        found = []
        for i, (row, text) in enumerate(zip(rows, self._search_texts, strict=True)):
            if i % 2048 == 0:
                checkpoint(cancel)
                progress(84, "Buscando nos registros da tabela")
            if all(term in text for term in terms):
                found.append(row)
        return found

    def _ordered(self, rows, selection, cancel, progress):
        columns = (
            "period",
            "product",
            "ncm",
            "state",
            "country",
            "port",
            "fob_cents",
            "freight_cents",
            "insurance_cents",
            "cif_cents",
            "kg",
            "unit_price",
        )
        if selection.kind == "municipal":
            columns = (
                "period",
                "city",
                "state",
                "heading",
                "product",
                "country",
                "fob_cents",
                "kg",
                "unit_price",
            )
        attr = columns[selection.sort_column]
        chunks, missing = [], []
        total = len(rows)
        for start in range(0, total, self.SORT_BATCH):
            checkpoint(cancel)
            progress(85 + int(start * 7 / max(1, total)), "Ordenando os registros da tabela")
            decorated = []
            for row in rows[start : start + self.SORT_BATCH]:
                value = (
                    (Fraction(row.value_cents, row.kg) if row.kg else None)
                    if attr == "unit_price"
                    else getattr(row, attr)
                )
                if value is None:
                    missing.append(row)
                else:
                    if attr in ("product", "country", "port", "city"):
                        value = search_key(value)
                    decorated.append((value, row.identifier, row))
            decorated.sort(key=lambda d: d[:2], reverse=selection.descending)
            chunks.append(decorated)
        ordered = []
        for i, decorated in enumerate(
            merge(*chunks, key=lambda d: d[:2], reverse=selection.descending)
        ):
            if i % self.SORT_BATCH == 0:
                checkpoint(cancel)
                progress(93 + int(i * 5 / max(1, total)), "Preparando a página da tabela")
            ordered.append(decorated[2])
        ordered.extend(missing)
        checkpoint(cancel)
        return tuple(ordered)

    @staticmethod
    def _scope_key(selection):
        return (
            selection.period,
            selection.kind,
            *(
                selected_values(selection, name)
                for name in ("ncm", "country", "state", "port", "city")
            ),
        )

    @staticmethod
    def _view_key(selection, scope_key):
        terms = tuple(sorted(set(search_key(selection.search.strip()).split())))
        return (scope_key, terms, selection.sort_column, selection.descending)

    @staticmethod
    def _page_result(selection, scope, ordered, dataset_size):
        pages = max(1, (len(ordered) + selection.page_size - 1) // selection.page_size)
        page = min(selection.page, pages)
        offset = (page - 1) * selection.page_size
        return QueryResult(
            selection,
            ordered[offset : offset + selection.page_size],
            scope.totals,
            len(ordered),
            page,
            pages,
            scope.monthly,
            scope.countries,
            dataset_size,
            scope.procurement,
        )

    def cached_query(self, selection):
        """Read only completed cached results; never fetch, filter or sort here.

        Call serially with query(), never concurrently with a query worker.
        Identity of the immutable source prevents reuse after a data refresh.
        """
        if self._cache_source is not self._rows or self._cache_source is None:
            return None
        scope_key = self._scope_key(selection)
        view_key = self._view_key(selection, scope_key)
        scope = self._scopes.get(scope_key)
        ordered = self._views.get(view_key)
        if scope is None or ordered is None:
            return None
        self._scopes.move_to_end(scope_key)
        self._views.move_to_end(view_key)
        self._statistics["scope_hits"] += 1
        self._statistics["view_hits"] += 1
        return self._page_result(selection, scope, ordered, len(self._cache_source))

    def query(self, selection, cancel, progress):
        checkpoint(cancel)
        source = self._dataset(cancel, progress)
        if source is not self._cache_source:
            self._scopes.clear()
            self._views.clear()
            self._search_rows, self._search_texts = None, ()
            self._cache_source = source
        scope_key = self._scope_key(selection)
        scope = self._scope(source, selection, scope_key, cancel, progress)
        view_key = self._view_key(selection, scope_key)
        if view_key in self._views:
            ordered = self._views[view_key]
            self._views.move_to_end(view_key)
            self._statistics["view_hits"] += 1
        else:
            selected = self._search(scope.rows, view_key[1], cancel, progress)
            ordered = self._ordered(selected, selection, cancel, progress)
            checkpoint(cancel)
            self._remember(self._views, view_key, ordered, self.VIEW_LIMIT)
            self._statistics["view_builds"] += 1
        checkpoint(cancel)
        progress(100, "Análise pronta")
        return self._page_result(selection, scope, ordered, len(source))
