"""Adaptador sintético explícito, utilizado somente em testes e --demo."""

from __future__ import annotations
import random
from .catalog import (
    catalog as catalog,
    DEMO_PERIOD as DEMO_PERIOD,
    COUNTRIES as COUNTRIES,
    STATES as STATES,
    PORTS as PORTS,
)
from .domain import ImportRecord
from .query import DatasetQuery, checkpoint
from .query import (
    Cancelled as Cancelled,
    ImportProvider as ImportProvider,
    QueryResult as QueryResult,
    Totals as Totals,
)


class DemoProvider(DatasetQuery):
    is_demo = True

    def __init__(self, size=100_000):
        if type(size) is not int or not 1 <= size <= 1_000_000:
            raise ValueError("Volume de demonstração inválido.")
        super().__init__()
        self.size = size
        self._rows = None

    def _dataset(self, cancel, progress):
        if self._rows is not None:
            return self._rows
        rng = random.Random(500001)
        products, months = catalog(), DEMO_PERIOD.months
        rows = []
        for i in range(self.size):
            if i % 1024 == 0:
                checkpoint(cancel)
                progress(int(i * 45 / self.size), "Preparando a base demonstrativa")
            item = products[rng.randrange(len(products))]
            kg = rng.randrange(500, 250_001)
            rows.append(
                ImportRecord(
                    i,
                    months[rng.randrange(len(months))],
                    item["ncm"],
                    item["name"],
                    rng.choice(STATES),
                    rng.choice(COUNTRIES),
                    rng.choice(PORTS),
                    kg * rng.randrange(65, 490),
                    kg * rng.randrange(3, 30),
                    kg * rng.randrange(0, 3),
                    kg,
                )
            )
        checkpoint(cancel)
        self._rows = tuple(rows)
        return self._rows

    def query(self, selection, cancel, progress):
        checkpoint(cancel)
        if selection.period.start < DEMO_PERIOD.start or selection.period.end > DEMO_PERIOD.end:
            raise ValueError("A demonstração contém dados de janeiro de 2025 a setembro de 2026.")
        if selection.ncm and selection.ncm not in {v["ncm"] for v in catalog()}:
            raise ValueError("O NCM não pertence ao cadastro da demonstração.")
        for value, available, label in (
            (selection.country, COUNTRIES, "País"),
            (selection.state, STATES, "UF"),
            (selection.port, PORTS, "Porto"),
        ):
            if value and value not in available:
                raise ValueError(label + " não disponível na demonstração.")
        return super().query(selection, cancel, progress)


__all__ = [
    "DemoProvider",
    "Cancelled",
    "ImportProvider",
    "QueryResult",
    "Totals",
    "catalog",
    "DEMO_PERIOD",
    "COUNTRIES",
    "STATES",
    "PORTS",
]
