"""Referências históricas de compra, sem previsão ou cotação de fornecedor.

Todos os cálculos usam centavos inteiros e razões Decimal. A conversão para
ponto flutuante ocorre exclusivamente na apresentação geométrica dos gráficos.
Os meses sem importação permanecem na série; preços sem peso não viram zero.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext


def ratio(numerator: int | Decimal, denominator: int | Decimal) -> Decimal | None:
    if not denominator:
        return None
    with localcontext() as context:
        context.prec = max(40, len(str(abs(numerator))) + len(str(abs(denominator))) + 10)
        return Decimal(numerator) / Decimal(denominator)


def change(current: Decimal | int | None, previous: Decimal | int | None) -> Decimal | None:
    """Variação relativa; uma base ausente ou zero não define percentual."""
    if current is None or previous is None or previous == 0:
        return None
    with localcontext() as context:
        context.prec = 40
        return (Decimal(current) / Decimal(previous) - 1) * 100


@dataclass(frozen=True, slots=True)
class Aggregate:
    fob_cents: int
    freight_cents: int | None
    insurance_cents: int | None
    kg: int
    records: int
    unweighed_cents: int = 0

    @property
    def value_cents(self):
        return self.fob_cents + (self.freight_cents or 0) + (self.insurance_cents or 0)

    @property
    def unit_price(self):
        return ratio(self.value_cents, 100 * self.kg)

    @property
    def fob_per_kg(self):
        return ratio(self.fob_cents, 100 * self.kg)

    @property
    def freight_per_kg(self):
        if self.freight_cents is None:
            return None
        return ratio(self.freight_cents, 100 * self.kg)

    @property
    def freight_share(self):
        return (
            ratio(self.freight_cents * 100, self.value_cents)
            if self.freight_cents is not None
            else None
        )


def combine(items: tuple[Aggregate, ...], municipal: bool) -> Aggregate:
    return Aggregate(
        sum(a.fob_cents for a in items),
        None if municipal else sum(a.freight_cents for a in items),
        None if municipal else sum(a.insurance_cents for a in items),
        sum(a.kg for a in items),
        sum(a.records for a in items),
        sum(a.unweighed_cents for a in items),
    )


@dataclass(frozen=True, slots=True)
class Month:
    period: str
    aggregate: Aggregate
    rolling: Aggregate | None
    rolling_price_valid: bool


@dataclass(frozen=True, slots=True)
class Origin:
    name: str
    aggregate: Aggregate
    latest: Aggregate
    previous: Aggregate | None
    priced_months: int = 0


@dataclass(frozen=True, slots=True)
class Procurement:
    total: Aggregate
    months: tuple[Month, ...]
    origins: tuple[Origin, ...]
    codes: tuple[str, ...]
    municipal: bool
    top3_share: Decimal | None
    product_label: str = ""


class ProcurementBuilder:
    """Acumulação única por recorte; finalização custa meses × países, não linhas."""

    def __init__(self, months, municipal=False):
        self.periods = months
        self.municipal = municipal
        self.months = {month: [0] * 6 for month in months}
        self.origins = {}
        self.origin_months = {}
        self.codes = set()
        self.labels = {}

    @staticmethod
    def _add(bucket, row, freight, insurance):
        bucket[0] += row.fob_cents
        bucket[1] += freight
        bucket[2] += insurance
        bucket[3] += row.kg
        bucket[4] += 1
        if row.kg == 0:
            bucket[5] += row.value_cents

    def add(self, row):
        freight = 0 if self.municipal else row.freight_cents
        insurance = 0 if self.municipal else row.insurance_cents
        self._add(self.months[row.period], row, freight, insurance)
        self._add(self.origins.setdefault(row.country, [0] * 6), row, freight, insurance)
        self._add(
            self.origin_months.setdefault((row.country, row.period), [0] * 6),
            row,
            freight,
            insurance,
        )
        self.codes.add(row.code)
        self.labels.setdefault(row.code, row.product)

    def _aggregate(self, bucket):
        fob, freight, insurance, kg, records, unweighed = bucket
        return Aggregate(
            fob,
            None if self.municipal else freight,
            None if self.municipal else insurance,
            kg,
            records,
            unweighed,
        )

    def finish(self, checkpoint=lambda: None):
        months = tuple(self._aggregate(b) for b in self.months.values())
        total = combine(months, self.municipal)
        series = []
        for i, (period, aggregate) in enumerate(zip(self.periods, months, strict=True)):
            checkpoint()
            window = months[i - 2 : i + 1] if i >= 2 else ()
            series.append(
                Month(
                    period,
                    aggregate,
                    combine(window, self.municipal) if window else None,
                    bool(window) and all(a.records and a.kg for a in window),
                )
            )
        origins = []
        for country, bucket in self.origins.items():
            checkpoint()
            latest = self._aggregate(self.origin_months.get((country, self.periods[-1]), [0] * 6))
            previous = (
                self._aggregate(self.origin_months.get((country, self.periods[-2]), [0] * 6))
                if len(self.periods) >= 2
                else None
            )
            priced_months = sum(
                self.origin_months.get((country, period), (0, 0, 0, 0))[3] > 0
                for period in self.periods
            )
            origins.append(
                Origin(country, self._aggregate(bucket), latest, previous, priced_months)
            )
        origins.sort(key=lambda o: (-o.aggregate.kg, -o.aggregate.value_cents, o.name))
        top3 = sum(sorted((o.aggregate.value_cents for o in origins), reverse=True)[:3])
        return Procurement(
            total,
            tuple(series),
            tuple(origins),
            tuple(sorted(self.codes)),
            self.municipal,
            ratio(top3 * 100, total.value_cents),
            next(iter(self.labels.values())) if len(self.codes) == 1 else "",
        )
