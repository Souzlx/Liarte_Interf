"""Estoque: contratos tipados e análise local, sem dependência de Qt ou do ERP.

Quantidades usam milionésimos da unidade original; custos usam centavos de real.
Giro e dias de estoque são indicadores da fonte, nunca somados entre posições.
"""

from __future__ import annotations

import math
import statistics
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from threading import Event

from .query import checkpoint

SCALE = 1_000_000


def _checked(values, cancel: Event):
    """Percorre fatos em lotes limitados, inclusive nas compreensões."""
    checkpoint(cancel)
    for index, value in enumerate(values):
        if index and index % 512 == 0:
            checkpoint(cancel)
        yield value
    checkpoint(cancel)


def scaled(value, factor: int) -> int:
    try:
        number = Decimal(str(value))
        if not number.is_finite() or abs(number) > Decimal("1e16"):
            raise ValueError("Valor numérico fora do limite.")
        return int((number * factor).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("Valor numérico inválido na base de estoque.") from exc


def folded(value: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", value.casefold()) if not unicodedata.combining(c)
    )


def number(value, digits=2) -> str:
    if value is None or not math.isfinite(float(value)):
        return "—"
    return f"{value:,.{digits}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def money(cents: int) -> str:
    return "R$ " + number(Decimal(cents) / 100)


def compact_money(cents: int) -> str:
    if abs(cents) >= 100_000_000:
        return "R$ " + number(Decimal(cents) / 100_000_000, 2) + " mi"
    return money(cents)


def closing_summary(points) -> dict:
    """Variação apenas entre meses consecutivos observados, sem pular lacunas."""
    index = next((i for i in range(len(points) - 1, -1, -1) if points[i]["raw"] is not None), None)
    if index is None:
        return {
            "value": "—",
            "period": "Sem fechamento no período",
            "change": "",
            "changeValue": None,
        }
    last = points[index]
    previous = points[index - 1] if index > 0 else None
    change = (
        (last["raw"] - previous["raw"]) / previous["raw"] * 100
        if previous
        and previous["raw"] is not None
        and previous["raw"] > 0
        and not last.get("partial", False)
        and not previous.get("partial", False)
        else None
    )
    return {
        "value": compact_money(last["raw"]),
        "full": money(last["raw"]),
        "period": ("Fechamento parcial · " if last.get("partial", False) else "Fechamento · ")
        + last["label"],
        "changeValue": change,
        "change": (("+" if change > 0 else "") + number(change, 1) + "% vs. " + previous["label"])
        if change is not None
        else "",
    }


def month_range(start: str, end: str) -> tuple[str, ...]:
    first = date.fromisoformat(start + "-01")
    last = date.fromisoformat(end + "-01")
    if last < first or (last.year - first.year) * 12 + last.month - first.month > 240:
        raise ValueError("Selecione um período válido de até 20 anos.")
    result = []
    while first <= last:
        result.append(first.strftime("%Y-%m"))
        first = date(first.year + first.month // 12, first.month % 12 + 1, 1)
    return tuple(result)


def month_end(period: str) -> date:
    first = date.fromisoformat(period + "-01")
    return date(first.year + first.month // 12, first.month % 12 + 1, 1) - timedelta(days=1)


@dataclass(frozen=True, slots=True)
class Product:
    code: str
    name: str
    group: str
    kind: str
    unit: str


@dataclass(frozen=True, slots=True)
class Balance:
    product: str
    branch: str
    warehouse: str
    unit: str
    quantity: int
    cost: int


@dataclass(frozen=True, slots=True)
class Closing:
    product: str
    branch: str
    warehouse: str
    unit: str
    period: str
    quantity: int
    cost: int
    turnover: float | None
    days: float | None


@dataclass(frozen=True, slots=True)
class Sale:
    product: str
    branch: str
    unit: str
    day: date
    quantity: int
    cost: int
    had_positive: bool | None = None


@dataclass(frozen=True, slots=True)
class InventoryData:
    as_of: date
    source_name: str
    source_hash: str
    products: tuple[Product, ...]
    balances: tuple[Balance, ...]
    closings: tuple[Closing, ...]
    sales: tuple[Sale, ...]
    branches: tuple[tuple[str, str], ...] = ()
    warehouses: tuple[tuple[str, str], ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class StockSelection:
    start: str
    end: str
    product: str = ""
    group: str = ""
    branch: str = ""
    warehouse: str = ""
    unit: str = ""
    kind: str = ""
    abc: str = ""
    activity: str = ""
    balance: str = ""
    search: str = ""


@dataclass(frozen=True, slots=True)
class StockRow:
    balance: Balance
    name: str
    group: str
    abc: str
    activity: str
    last_sale: date | None
    days_since_sale: int | None
    sold: int
    coverage: float | None
    turnover: float | None
    source_days: float | None
    source_period: str
    cv: float | None
    monthly_mean: float | None
    monthly_std: float | None
    full_months: int


@dataclass(frozen=True, slots=True)
class StockAnalysis:
    rows: tuple[StockRow, ...]
    metrics: tuple[dict, ...]
    trend: tuple[dict, ...]
    ranking: tuple[dict, ...]
    activity: tuple[dict, ...]
    historical_scope: str
    quantity_label: str
    total_cost: int
    sales_months: tuple[dict, ...] = field(default_factory=tuple)
    history_summary: dict = field(default_factory=dict)


def _abc(costs: dict[str, int], cancel: Event) -> dict[str, str]:
    """ABC por capital positivo; o item que cruza o limite mantém a classe anterior."""
    positive = sorted(
        ((k, v) for k, v in _checked(costs.items(), cancel) if v > 0),
        key=lambda x: (-x[1], x[0]),
    )
    total = sum(v for _, v in _checked(positive, cancel))
    cumulative = 0
    result = {}
    for key, value in _checked(positive, cancel):
        result[key] = (
            "A" if cumulative * 100 < total * 80 else "B" if cumulative * 100 < total * 95 else "C"
        )
        cumulative += value
    return result


def analyze_inventory(
    data: InventoryData, selected: StockSelection, *, cancel: Event | None = None
) -> StockAnalysis:
    cancel = cancel if cancel is not None else Event()

    def checked(values):
        return _checked(values, cancel)

    checkpoint(cancel)
    periods = month_range(selected.start, selected.end)
    period_set = set(periods)
    start = date.fromisoformat(selected.start + "-01")
    end = min(month_end(selected.end), data.as_of)
    if start > end:
        raise ValueError("O período começa depois da data da base.")
    # Não atribuir meses anteriores à primeira observação como vendas nulas.
    sales_begin = min((s.day for s in checked(data.sales)), default=None)
    observed_start = max(start, sales_begin) if sales_begin is not None else None
    observed_days = max(0, (end - observed_start).days + 1) if observed_start else 0
    products = {p.code: p for p in checked(data.products)}
    terms = folded(selected.search).split()
    permitted = {
        p.code
        for p in checked(data.products)
        if (not selected.product or p.code == selected.product)
        and (not selected.group or p.group == selected.group)
        and (not selected.kind or p.kind == selected.kind)
        and all(term in folded(p.code + " " + p.name + " " + p.group) for term in terms)
    }

    def scope(row):
        return (
            row.product in permitted
            and (not selected.branch or row.branch == selected.branch)
            and (not selected.warehouse or row.warehouse == selected.warehouse)
            and (not selected.unit or row.unit == selected.unit)
        )

    balances = [b for b in checked(data.balances) if scope(b)]
    capital = defaultdict(int)
    for b in checked(balances):
        capital[b.product] += b.cost
    classes = _abc(capital, cancel)
    latest = max((c.period for c in checked(data.closings)), default="")
    closing_lookup = {
        (c.product, c.branch, c.warehouse, c.unit): c
        for c in checked(data.closings)
        if c.period == latest
    }
    sold = defaultdict(int)
    sale_months = defaultdict(lambda: defaultdict(int))
    last_sales = {}
    for sale in checked(data.sales):
        if sale.product not in permitted or sale.day > data.as_of:
            continue
        key = (sale.product, sale.branch, sale.unit)
        if sale.had_positive if sale.had_positive is not None else sale.quantity > 0:
            last_sales[key] = max(sale.day, last_sales.get(key, sale.day))
        if observed_start is not None and observed_start <= sale.day <= end:
            sold[key] += sale.quantity
            sale_months[key][sale.day.strftime("%Y-%m")] += sale.quantity
    full_months = [
        p
        for p in periods
        if sales_begin is not None
        and date.fromisoformat(p + "-01") >= sales_begin
        and month_end(p) <= end
    ]
    full_month_set = set(full_months)
    full_count = len(full_months)
    stock_at_branch = defaultdict(int)
    for b in checked(balances):
        stock_at_branch[b.product, b.branch, b.unit] += b.quantity
    rows = []
    demand_stats = {}
    for b in checked(balances):
        key = (b.product, b.branch, b.unit)
        last_sale = last_sales.get(key)
        elapsed = (data.as_of - last_sale).days if last_sale else None
        activity = (
            "Sem venda"
            if elapsed is None
            else "Até 30 dias"
            if elapsed <= 30
            else "31–90 dias"
            if elapsed <= 90
            else "Mais de 90 dias"
        )
        abc = classes.get(b.product, "—")
        if (
            selected.abc
            and abc != selected.abc
            or selected.activity
            and activity != selected.activity
        ):
            continue
        if (
            selected.balance == "positive"
            and b.quantity <= 0
            or selected.balance == "zero"
            and b.quantity != 0
            or selected.balance == "negative"
            and b.quantity >= 0
        ):
            continue
        if key not in demand_stats:
            # Inteiros preservam a variância de demandas grandes/quase iguais.
            # Meses sem venda contribuem zero pelo denominador, sem lista densa.
            quantities = [
                value
                for period, value in sale_months.get(key, {}).items()
                if period in full_month_set
            ]
            total_quantity = sum(quantities)
            mean = total_quantity / full_count / SCALE if full_count else None
            std = (
                math.sqrt(
                    (full_count * sum(value * value for value in quantities) - total_quantity**2)
                    / (full_count * (full_count - 1))
                )
                / SCALE
                if full_count >= 3
                else None
            )
            cv = (
                std / mean
                if std is not None
                and mean is not None
                and mean > 0
                and all(value >= 0 for value in quantities)
                else None
            )
            demand_stats[key] = mean, std, cv
        mean, std, cv = demand_stats[key]
        total_sold = sold[key]
        branch_qty = stock_at_branch[key]
        coverage = (
            branch_qty * observed_days / total_sold
            if not selected.warehouse and branch_qty >= 0 and total_sold > 0 and observed_days
            else None
        )
        c = closing_lookup.get((b.product, b.branch, b.warehouse, b.unit))
        rows.append(
            StockRow(
                b,
                products[b.product].name,
                products[b.product].group,
                abc,
                activity,
                last_sale,
                elapsed,
                total_sold,
                coverage,
                c.turnover if c else None,
                c.days if c else None,
                latest if c else "",
                cv,
                mean,
                std,
                len(full_months),
            )
        )
    # Filtros derivados de saldo restringem o histórico às posições selecionadas.
    derived_filter = bool(selected.abc or selected.activity or selected.balance)
    position_keys = {
        (r.balance.product, r.balance.branch, r.balance.warehouse, r.balance.unit)
        for r in checked(rows)
    }
    history = [
        c
        for c in checked(data.closings)
        if c.period in period_set
        and scope(c)
        and (not derived_filter or (c.product, c.branch, c.warehouse, c.unit) in position_keys)
    ]
    monthly_cost = defaultdict(int)
    for c in checked(history):
        monthly_cost[c.period] += c.cost
    trend = []
    for p in periods:
        value = monthly_cost.get(p)
        previous = trend[-2:] + [{"raw": value}]
        rolling = (
            statistics.mean(v["raw"] for v in previous)
            if len(previous) == 3 and all(v["raw"] is not None for v in previous)
            else None
        )
        trend.append(
            {
                "period": p,
                "label": p[5:] + "/" + p[:4],
                "raw": value,
                "partial": bool(value is not None and month_end(p) > data.as_of),
                "value": value / 100_000_000 if value is not None else None,
                "display": money(value) if value is not None else "Sem fechamento",
                "movingValue": rolling / 100_000_000 if rolling is not None else None,
                "movingDisplay": money(round(rolling)) if rolling is not None else "",
            }
        )
    costs, activity_values, units = defaultdict(int), defaultdict(int), defaultdict(int)
    for row in checked(rows):
        b = row.balance
        costs[b.product] += b.cost
        units[b.unit] += b.quantity
        activity_values[row.activity] += max(0, b.cost)
    total = sum(r.balance.cost for r in checked(rows))
    positive_capital = sum(max(0, v) for v in checked(costs.values()))
    ranked = sorted(
        ((k, v) for k, v in checked(costs.items()) if v > 0), key=lambda x: (-x[1], x[0])
    )
    cumulative = 0
    ranking = []
    for code, value in ranked[:12]:
        cumulative += value
        ranking.append(
            {
                "code": code,
                "name": products[code].name,
                "value": value,
                "display": money(value),
                "share": number(100 * value / positive_capital, 1) + "%",
                "cumulative": number(100 * cumulative / positive_capital, 1) + "%",
                "shareValue": 100 * value / positive_capital,
                "cumulativeValue": 100 * cumulative / positive_capital,
                "abc": classes.get(code, "—"),
            }
        )
    giro = [
        r.turnover
        for r in checked(rows)
        if r.turnover is not None and r.turnover >= 0 and r.balance.quantity > 0
    ]
    product_quantities = defaultdict(int)
    for row in checked(rows):
        product_quantities[row.balance.product, row.balance.unit] += row.balance.quantity
    distinct = len(
        {code for (code, unit), quantity in checked(product_quantities.items()) if quantity > 0}
    )
    old_value = sum(
        max(0, r.balance.cost)
        for r in checked(rows)
        if r.days_since_sale is not None and r.days_since_sale > 90 or r.last_sale is None
    )
    quantity = (
        (number(Decimal(next(iter(units.values()))) / SCALE, 3) + " " + next(iter(units)))
        if len(units) == 1
        else f"{len(units)} unidades distintas"
        if units
        else "—"
    )
    metrics = (
        {
            "label": "Estoque a custo",
            "value": compact_money(total),
            "detail": "Saldo atual · a custo",
            "full": money(total),
        },
        {
            "label": "Produtos com saldo",
            "value": number(distinct, 0),
            "detail": f"{len(rows)} posições no recorte",
        },
        {
            "label": "Quantidade",
            "value": "Por unidade" if len(units) > 1 else quantity,
            "full": "; ".join(
                f"{unit}: {number(Decimal(qty) / SCALE, 3)}" for unit, qty in sorted(units.items())
            ),
            "detail": " · ".join(sorted(units))
            if len(units) > 1
            else "Saldo atual na unidade indicada",
        },
        {
            "label": "Giro mensal · mediana",
            "value": number(statistics.median(giro), 2) + " x" if giro else "—",
            "detail": f"Fonte · {latest[5:]}/{latest[:4]} · {len(giro)} posições"
            if giro
            else "Sem giro na fonte neste recorte",
            "full": "Mediana do giro mensal em quantidade informado em Fact_Estoque, no último fechamento da base. Não é o giro consolidado. Considera posições com saldo atual positivo e giro não negativo.",
        },
        {
            "label": "Sem venda >90 dias",
            "value": compact_money(old_value),
            "detail": "Inclui sem venda registrada",
            "full": money(old_value)
            + ". Capital positivo de produtos cuja última venda observada é anterior a 90 dias, ou sem venda registrada até a data da base. Não inclui consumo interno.",
        },
    )
    scopes = sorted({(c.branch, c.warehouse) for c in checked(history)})
    scope_label = (
        "; ".join(f"Filial {f} · arm. {a}" for f, a in scopes) or "Sem fechamentos no recorte"
    )
    activity_result = tuple(
        {"name": name, "value": activity_values[name], "display": money(activity_values[name])}
        for name in ("Até 30 dias", "31–90 dias", "Mais de 90 dias", "Sem venda")
    )
    sale_keys = {(r.balance.product, r.balance.branch, r.balance.unit) for r in checked(rows)}
    month_totals = defaultdict(lambda: defaultdict(int))
    for key in checked(sale_keys):
        for p, quantity_value in checked(sale_months[key].items()):
            month_totals[p][key[2]] += quantity_value
    sales_months = tuple(
        {
            "period": p,
            "unit": unit,
            "quantity": month_totals[p].get(unit, 0)
            if sales_begin is not None
            and month_end(p) >= sales_begin
            and date.fromisoformat(p + "-01") <= end
            else None,
            "partial": sales_begin is not None
            and (date.fromisoformat(p + "-01") < sales_begin or month_end(p) > data.as_of),
        }
        for p in checked(periods)
        for unit in checked(sorted(units))
    )
    checkpoint(cancel)
    return StockAnalysis(
        tuple(rows),
        metrics,
        tuple(trend),
        tuple(ranking),
        activity_result,
        scope_label,
        quantity,
        total,
        sales_months,
        closing_summary(trend),
    )
