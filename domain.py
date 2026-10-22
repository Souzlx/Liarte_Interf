"""Contratos de dados: base geral por NCM e base municipal por SH4."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP, localcontext

MONTHS = (
    "Janeiro",
    "Fevereiro",
    "Março",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
)
UF_CODES = frozenset(
    "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split()
)


def period_index(value: str) -> int:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", value):
        raise ValueError("Informe um mês válido no formato AAAA-MM.")
    year, month = map(int, value.split("-"))
    if not 1997 <= year <= 9999:
        raise ValueError("O ano deve estar entre 1997 e 9999.")
    return year * 12 + month - 1


def period_value(index: int) -> str:
    year, month = divmod(index, 12)
    return f"{year:04d}-{month + 1:02d}"


def period_label(value: str) -> str:
    period_index(value)
    return f"{MONTHS[int(value[5:]) - 1]} de {value[:4]}"


@dataclass(frozen=True, slots=True)
class Period:
    start: str
    end: str

    def __post_init__(self):
        if period_index(self.start) > period_index(self.end):
            raise ValueError("O mês inicial deve ser anterior ou igual ao mês final.")

    @property
    def months(self) -> tuple[str, ...]:
        return tuple(
            period_value(i) for i in range(period_index(self.start), period_index(self.end) + 1)
        )


@dataclass(frozen=True, slots=True)
class ImportRecord:
    identifier: int
    period: str
    ncm: str
    product: str
    state: str
    country: str
    port: str
    fob_cents: int
    freight_cents: int
    insurance_cents: int
    kg: int
    official_description: str = ""

    def __post_init__(self):
        period_index(self.period)
        if not isinstance(self.ncm, str) or not re.fullmatch(r"[0-9]{8}", self.ncm):
            raise ValueError("O NCM precisa conter oito dígitos.")
        if not isinstance(self.state, str) or self.state not in UF_CODES | {"ND", "EX"}:
            raise ValueError("UF inválida.")
        if any(
            type(v) is not int or v < 0
            for v in (
                self.identifier,
                self.fob_cents,
                self.freight_cents,
                self.insurance_cents,
                self.kg,
            )
        ):
            raise ValueError("Valores e peso devem ser inteiros não negativos.")
        if not all(
            isinstance(v, str) and v.strip() for v in (self.product, self.country, self.port)
        ):
            raise ValueError("O registro possui descrição vazia.")

    @property
    def cif_cents(self) -> int:
        return self.fob_cents + self.freight_cents + self.insurance_cents

    @property
    def unit_price(self) -> Decimal | None:
        return Decimal(self.cif_cents) / Decimal(100) / Decimal(self.kg) if self.kg else None

    @property
    def code(self):
        return self.ncm

    @property
    def value_cents(self):
        return self.cif_cents


@dataclass(frozen=True, slots=True)
class MunicipalRecord:
    identifier: int
    period: str
    heading: str
    product: str
    state: str
    country: str
    city: str
    fob_cents: int
    kg: int

    def __post_init__(self):
        period_index(self.period)
        if not re.fullmatch(r"[0-9]{4}", self.heading):
            raise ValueError("SH4 inválido.")
        if self.state not in UF_CODES | {"ND", "EX"}:
            raise ValueError("UF inválida.")
        if any(type(v) is not int or v < 0 for v in (self.identifier, self.fob_cents, self.kg)):
            raise ValueError("Métricas municipais inválidas.")
        if not all(
            isinstance(v, str) and v.strip() for v in (self.product, self.country, self.city)
        ):
            raise ValueError("Identificação municipal incompleta.")

    @property
    def code(self):
        return self.heading

    @property
    def port(self):
        return ""

    @property
    def value_cents(self):
        return self.fob_cents

    @property
    def unit_price(self):
        return Decimal(self.fob_cents) / 100 / self.kg if self.kg else None


@dataclass(frozen=True, slots=True)
class Selection:
    period: Period
    ncm: str = ""
    country: str = ""
    state: str = ""
    search: str = ""
    sort_column: int = 0
    descending: bool = False
    page: int = 1
    page_size: int = 50
    port: str = ""
    kind: str = "general"
    city: str = ""
    ncm_values: tuple[str, ...] = ()
    country_values: tuple[str, ...] = ()
    state_values: tuple[str, ...] = ()
    port_values: tuple[str, ...] = ()
    city_values: tuple[str, ...] = ()

    def __post_init__(self):
        if not isinstance(self.period, Period):
            raise ValueError("Período inválido.")
        for field in ("ncm", "country", "state", "port", "city"):
            values = getattr(self, field + "_values")
            if (
                not isinstance(values, tuple)
                or len(values) > 200
                or not all(isinstance(v, str) and v and len(v) <= 250 for v in values)
            ):
                raise ValueError("Seleção múltipla inválida ou excessiva.")
            object.__setattr__(self, field + "_values", tuple(sorted(set(values))))
        if (
            self.kind not in ("general", "municipal")
            or not isinstance(self.city, str)
            or len(self.city) > 250
        ):
            raise ValueError("Base ou município inválido.")
        if not all(
            isinstance(v, str) for v in (self.ncm, self.country, self.state, self.search, self.port)
        ):
            raise ValueError("Os filtros devem ser textos válidos.")
        if self.ncm and not re.fullmatch(
            r"[0-9]{8}" if self.kind == "general" else r"[0-9]{4}", self.ncm
        ):
            raise ValueError("Filtro de NCM inválido.")
        if any(
            not re.fullmatch(r"[0-9]{8}" if self.kind == "general" else r"[0-9]{4}", v)
            for v in self.ncm_values
        ):
            raise ValueError("Códigos inválidos na seleção.")
        if any(v not in UF_CODES | {"ND", "EX"} for v in self.state_values):
            raise ValueError("UF inválida na seleção.")
        if self.state and self.state not in UF_CODES | {"ND", "EX"}:
            raise ValueError("Filtro de UF inválido.")
        if len(self.search) > 250 or len(self.country) > 120 or len(self.port) > 250:
            raise ValueError("O filtro excedeu o limite de caracteres.")
        if type(self.page) is not int or not 1 <= self.page <= 1_000_000:
            raise ValueError("Página inválida.")
        if type(self.page_size) is not int or self.page_size not in (25, 50, 100, 200):
            raise ValueError("Quantidade de linhas inválida.")
        if type(self.sort_column) is not int or self.sort_column not in range(12):
            raise ValueError("Coluna de ordenação inválida.")
        if self.kind == "municipal" and (self.port or self.port_values or self.sort_column > 8):
            raise ValueError("A base municipal não publica URF e usa nove colunas.")
        if type(self.descending) is not bool:
            raise ValueError("Direção de ordenação inválida.")


def selected_values(selection, dimension):
    multiple = getattr(selection, dimension + "_values")
    single = getattr(selection, dimension)
    return multiple or ((single,) if single else ())


def record_predicate(selection):
    tests = tuple(
        (field, frozenset(selected_values(selection, name)))
        for name, field in (
            ("ncm", "code"),
            ("country", "country"),
            ("state", "state"),
            ("port", "port"),
            ("city", "city"),
        )
        if selected_values(selection, name)
    )
    start, end = selection.period.start, selection.period.end
    if not tests:
        return lambda row: start <= row.period <= end
    return lambda row: start <= row.period <= end and all(
        getattr(row, field, "") in values for field, values in tests
    )


def search_key(value: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", value.casefold()) if not unicodedata.combining(c)
    )


def number(value: int | Decimal | None, decimals: int = 0) -> str:
    if value is None:
        return "—"
    if type(decimals) is not int or not 0 <= decimals <= 6:
        raise ValueError("Use entre zero e seis casas decimais.")
    amount = Decimal(value)
    if not amount.is_finite():
        raise ValueError("O valor deve ser finito.")
    with localcontext() as context:
        context.prec = max(
            28, amount.adjusted() + decimals + 3, len(amount.as_tuple().digits) + decimals + 3
        )
        amount = amount.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
    if amount.is_zero():
        amount = abs(amount)
    return f"{amount:,.{decimals}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def money(cents: int) -> str:
    return "US$ " + number(Decimal(cents) / 100, 2)


def compact_money(cents: int) -> str:
    dollars = Decimal(cents) / 100
    for divisor, label in ((10**9, "bi"), (10**6, "mi"), (10**3, "mil")):
        if abs(dollars) >= divisor:
            return "US$ " + number(dollars / divisor, 1) + " " + label
    return money(cents)
