"""Análise mensal de fechamentos e vendas, sem inferir movimentos ou idade de lotes.

O universo histórico não depende do saldo atual. Filtros derivados (ABC,
atividade e sinal do saldo) são a única exceção: selecionam explicitamente
uma coorte de posições atuais. Custos usam centavos e quantidades usam SCALE.
"""

from __future__ import annotations

import math
import statistics
from bisect import bisect_right
from collections import defaultdict
from datetime import date
from decimal import Decimal

from .inventory import (
    SCALE,
    InventoryData,
    StockAnalysis,
    StockSelection,
    analyze_inventory,
    folded,
    money,
    month_end,
    month_range,
    number,
)


def _label(period: str) -> str:
    return period[5:] + "/" + period[:4]


def _position(row):
    return row.product, row.branch, row.warehouse, row.unit


def _sale_key(row):
    return row.product, row.branch, row.unit


def _quantity(value: int, unit: str, *, signed=False) -> str:
    prefix = "+" if signed and value > 0 else ""
    return prefix + number(Decimal(value) / SCALE, 3) + " " + unit


def _signed_money(value: int) -> str:
    return ("+" if value > 0 else "−" if value < 0 else "") + money(abs(value))


def _last_sale(dates, key, cutoff):
    days = dates.get(key, ())
    index = bisect_right(days, cutoff) - 1
    return days[index] if index >= 0 else None


def analyze_monthly_inventory(
    data: InventoryData,
    selected: StockSelection,
    analysis: StockAnalysis | None = None,
) -> tuple[dict, ...]:
    """Retorna meses selecionados e rankings completos, sem truncar exportações.

    Ausência de uma posição no fechamento não significa saldo zero. A
    comparação de estoque separa posições pareadas de registros novos/ausentes.
    Vendas são líquidas por produto/filial/unidade; não possuem armazém e ficam
    indisponíveis quando esse filtro é aplicado. Não se trata de faturamento.
    """
    periods = month_range(selected.start, selected.end)
    period_set = set(periods)
    if date.fromisoformat(selected.start + "-01") > data.as_of:
        raise ValueError("O período começa depois da data da base.")
    products = {p.code: p for p in data.products}
    terms = folded(selected.search).split()
    permitted = {
        p.code
        for p in data.products
        if (not selected.product or p.code == selected.product)
        and (not selected.group or p.group == selected.group)
        and (not selected.kind or p.kind == selected.kind)
        and all(term in folded(p.code + " " + p.name + " " + p.group) for term in terms)
    }
    derived = bool(selected.abc or selected.activity or selected.balance)
    position_keys = sale_keys = None
    if derived:
        analysis = analysis if analysis is not None else analyze_inventory(data, selected)
        position_keys = {_position(r.balance) for r in analysis.rows}
        sale_keys = {_sale_key(r.balance) for r in analysis.rows}

    def primary(row):
        return (
            row.product in permitted
            and (not selected.branch or row.branch == selected.branch)
            and (not selected.unit or row.unit == selected.unit)
        )

    closings = defaultdict(dict)
    units = set()
    for closing in data.closings:
        if (
            primary(closing)
            and (not selected.warehouse or closing.warehouse == selected.warehouse)
            and (not derived or _position(closing) in position_keys)
        ):
            units.add(closing.unit)
            if closing.period in period_set:
                closings[closing.period][_position(closing)] = closing
    # Include a unit with current positions but no monthly closure/sale, so the
    # UI can communicate missing data instead of silently hiding the selection.
    for balance in data.balances:
        if (
            primary(balance)
            and (not selected.warehouse or balance.warehouse == selected.warehouse)
            and (not derived or _position(balance) in position_keys)
        ):
            units.add(balance.unit)
    if selected.unit:
        units.add(selected.unit)

    sales = defaultdict(lambda: defaultdict(int))
    sale_dates = defaultdict(list)
    sale_universe = set()
    for sale in data.sales:
        if sale.day > data.as_of or not primary(sale):
            continue
        key = _sale_key(sale)
        if derived and key not in sale_keys:
            continue
        if sale.had_positive if sale.had_positive is not None else sale.quantity > 0:
            sale_dates[key].append(sale.day)
        if not selected.warehouse:
            units.add(sale.unit)
            sale_universe.add(key)
            period = sale.day.strftime("%Y-%m")
            if period in period_set:
                sales[period][key] += sale.quantity
    for days in sale_dates.values():
        days.sort()
    units = sorted(units)
    sales_begin = min((s.day for s in data.sales if s.day <= data.as_of), default=None)

    result = []
    for index, period in enumerate(periods):
        first = date.fromisoformat(period + "-01")
        end = month_end(period)
        cutoff = min(end, data.as_of)
        previous_period = periods[index - 1] if index else ""
        previous = result[-1] if result else None
        current = closings.get(period, {})
        prior = closings.get(previous_period, {}) if previous_period else {}
        stock_cost = sum(c.cost for c in current.values()) if current else None
        stock_partial = bool(current and end > data.as_of)
        stock_quantity = {unit: None for unit in units}
        for closing in current.values():
            stock_quantity[closing.unit] = (stock_quantity[closing.unit] or 0) + closing.quantity
        scopes = sorted({(c.branch, c.warehouse) for c in current.values()})
        scope = (
            "; ".join(f"Filial {branch} · arm. {warehouse}" for branch, warehouse in scopes)
            or "Sem fechamento neste mês e recorte"
        )
        positive = [c for c in current.values() if c.quantity > 0]
        valid_giro = [
            c.turnover
            for c in positive
            if c.turnover is not None and math.isfinite(c.turnover) and c.turnover >= 0
        ]
        invalid_giro = sum(
            c.turnover is not None and (not math.isfinite(c.turnover) or c.turnover < 0)
            for c in positive
        )
        low_turnover = [
            {
                "code": c.product,
                "name": products[c.product].name,
                "value": c.turnover,
                "display": number(c.turnover, 2) + " x/mês",
                "detail": "Giro da fonte · filial "
                + c.branch
                + " · arm. "
                + c.warehouse
                + " · saldo "
                + _quantity(c.quantity, c.unit)
                + " · "
                + money(c.cost),
                "branch": c.branch,
                "warehouse": c.warehouse,
                "unit": c.unit,
                "quantity": c.quantity,
                "cost": c.cost,
            }
            for c in sorted(
                (
                    c
                    for c in positive
                    if c.turnover is not None and math.isfinite(c.turnover) and c.turnover >= 0
                ),
                key=lambda c: (c.turnover, -c.cost, c.product, c.branch, c.warehouse, c.unit),
            )
        ]
        observed = (
            not selected.warehouse
            and sales_begin is not None
            and first <= data.as_of
            and end >= sales_begin
        )
        partial = bool(observed and (first < sales_begin or end > data.as_of))
        monthly_sales = sales.get(period, {}) if observed else {}
        sales_quantity = {unit: 0 if observed else None for unit in units}
        if observed:
            for (_, _, unit), qty in monthly_sales.items():
                sales_quantity[unit] += qty
        branches = sorted({key[1] for key in sale_universe})
        sales_scope = (
            "Vendas indisponíveis por armazém"
            if selected.warehouse
            else "Vendas das filiais " + ", ".join(branches) + " · sem alocação por armazém"
            if branches
            else "Sem vendas registradas no recorte"
        )

        notices = [
            "Fechamentos e vendas podem cobrir locais diferentes. Tempo sem venda não é idade do lote."
        ]
        if selected.warehouse:
            notices.append(
                "Retire o filtro de armazém para analisar vendas; a última venda abaixo é da filial."
            )
        if derived:
            notices.append(
                "ABC, atividade e saldo selecionam posições pela situação atual da base, não pela situação histórica."
            )
        if invalid_giro:
            notices.append(f"{invalid_giro} giro(s) negativo(s) ou inválido(s) fora da mediana.")
        if stock_partial:
            notices.append("O fechamento deste mês é parcial na data da base.")

        # Sales aggregate by product within the same unit, with one contribution
        # per branch, independently of how many warehouses contain that product.
        sellers = {unit: [] for unit in units}
        if observed:
            grouped_sales = defaultdict(int)
            for (code, _, unit), qty in monthly_sales.items():
                grouped_sales[code, unit] += qty
            for unit in units:
                positive_sales = sorted(
                    (
                        (code, qty)
                        for (code, um), qty in grouped_sales.items()
                        if um == unit and qty > 0
                    ),
                    key=lambda item: (-item[1], item[0]),
                )
                denominator = sum(qty for _, qty in positive_sales)
                sellers[unit] = [
                    {
                        "code": code,
                        "name": products[code].name,
                        "value": qty,
                        "display": _quantity(qty, unit),
                        "share": number(100 * qty / denominator, 1) + "%",
                        "shareValue": 100 * qty / denominator,
                        "detail": "Quantidade líquida vendida · "
                        + _label(period)
                        + "; participação entre produtos com quantidade líquida positiva na mesma unidade",
                    }
                    for code, qty in positive_sales
                ]

        slow_groups = defaultdict(lambda: [0, 0])
        for closing in positive:
            pair = slow_groups[_sale_key(closing)]
            pair[0] += closing.quantity
            pair[1] += closing.cost
        slow = []
        for (code, branch, unit), (qty, cost) in slow_groups.items():
            last_sale = _last_sale(sale_dates, (code, branch, unit), cutoff)
            elapsed = (cutoff - last_sale).days if last_sale else None
            slow.append(
                {
                    "code": code,
                    "name": products[code].name,
                    "branch": branch,
                    "unit": unit,
                    "quantity": qty,
                    "cost": cost,
                    "lastSale": last_sale.isoformat() if last_sale else "",
                    "daysSinceSale": elapsed,
                    "value": elapsed,
                    "display": f"{elapsed} dias sem venda"
                    if elapsed is not None
                    else "Sem venda registrada",
                    "detail": "Filial "
                    + branch
                    + " · saldo de fechamento "
                    + _quantity(qty, unit)
                    + " · "
                    + money(cost)
                    + (
                        " · última venda " + last_sale.strftime("%d/%m/%Y")
                        if last_sale
                        else " · sem saída positiva observada até o mês"
                    ),
                }
            )
        # Keep an explicit 'no recorded sale' bucket rather than inventing an
        # age from the beginning of the dataset. Those entries appear first.
        slow.sort(
            key=lambda row: (
                row["daysSinceSale"] is not None,
                -(row["daysSinceSale"] or 0),
                -row["cost"],
                row["code"],
                row["branch"],
                row["unit"],
            )
        )

        changes = []
        stock_change = matched_change = None
        new_count = missing_count = 0
        new_cost = missing_cost = None
        if current and prior and not stock_partial and not previous["stockPartial"]:
            shared = current.keys() & prior.keys()
            added = current.keys() - prior.keys()
            missing = prior.keys() - current.keys()
            new_count, missing_count = len(added), len(missing)
            new_cost = sum(current[key].cost for key in added)
            missing_cost = sum(prior[key].cost for key in missing)
            stock_change = stock_cost - sum(c.cost for c in prior.values())
            by_product = defaultdict(int)
            for key in shared:
                by_product[key[0]] += current[key].cost - prior[key].cost
            matched_change = sum(by_product.values())
            changes = [
                {
                    "code": code,
                    "name": products[code].name,
                    "value": delta,
                    "display": _signed_money(delta),
                    "detail": "Variação a custo em posições presentes nos dois meses",
                }
                for code, delta in sorted(
                    by_product.items(), key=lambda item: (-abs(item[1]), item[0])
                )
                if delta
            ]
            comparison = (
                "Variação total observada "
                + _signed_money(stock_change)
                + " vs. "
                + _label(previous_period)
                + "; posições comparáveis "
                + _signed_money(matched_change)
                + f" ({len(shared)} posições). "
                + f"{new_count} registro(s) novo(s) ({money(new_cost)}) e {missing_count} ausente(s) ({money(missing_cost)}) no fechamento. "
                + "O ranking usa apenas posições comparáveis; registros novos/ausentes não comprovam entradas ou saídas físicas."
            )
        else:
            comparison = (
                "Sem comparação: selecione também o mês anterior consecutivo com fechamento. "
                "Meses e posições ausentes não são tratados como saldo zero."
            )

        sales_changes = {unit: [] for unit in units}
        sales_change = {unit: None for unit in units}
        previous_observed = bool(previous and previous["salesObserved"])
        comparable_sales = (
            observed and not partial and previous_observed and not previous["partial"]
        )
        if comparable_sales:
            previous_sales = sales.get(previous_period, {})
            product_changes = defaultdict(int)
            for code, branch, unit in monthly_sales.keys() | previous_sales.keys():
                key = (code, branch, unit)
                product_changes[code, unit] += monthly_sales.get(key, 0) - previous_sales.get(
                    key, 0
                )
            for unit in units:
                sales_change[unit] = sales_quantity[unit] - previous["salesQuantity"][unit]
                sales_changes[unit] = [
                    {
                        "code": code,
                        "name": products[code].name,
                        "value": delta,
                        "display": _quantity(delta, unit, signed=True),
                        "detail": "Variação líquida vendida vs. " + _label(previous_period),
                    }
                    for (code, um), delta in sorted(
                        product_changes.items(), key=lambda item: (-abs(item[1]), item[0])
                    )
                    if um == unit and delta
                ]
            sales_comparison = (
                "Comparação com "
                + _label(previous_period)
                + ": dois meses completos observados. Vendas líquidas podem incluir devoluções; quantidades separadas por unidade."
            )
        elif selected.warehouse:
            sales_comparison = "Vendas não podem ser atribuídas ao armazém. Retire esse filtro para comparar as filiais."
        elif partial or (previous and previous["partial"]):
            sales_comparison = "Comparação de vendas indisponível: um dos meses é parcial. Não comparar mês incompleto com mês completo."
        else:
            sales_comparison = "Comparação de vendas exige o mês anterior consecutivo e dois meses completos observados."

        result.append(
            {
                "period": period,
                "label": _label(period),
                "previousLabel": _label(previous_period) if previous_period else "",
                "scope": scope,
                "salesScope": sales_scope,
                "notice": " ".join(notices),
                "partial": partial,
                "stockPartial": stock_partial,
                "salesObserved": bool(observed),
                "stockCost": stock_cost,
                "stockQuantity": stock_quantity,
                "salesQuantity": sales_quantity,
                "turnover": statistics.median(valid_giro) if valid_giro else None,
                "turnoverCount": len(valid_giro),
                "turnoverInvalidCount": invalid_giro,
                "productCount": len({c.product for c in positive}) if current else None,
                "stockChange": stock_change,
                "matchedStockChange": matched_change,
                "newPositionCount": new_count,
                "missingPositionCount": missing_count,
                "newPositionCost": new_cost,
                "missingPositionCost": missing_cost,
                "sellersByUnit": sellers,
                "slow": slow,
                "lowTurnover": low_turnover,
                "changes": changes,
                "salesChangesByUnit": sales_changes,
                "salesChange": sales_change,
                "comparison": comparison,
                "salesComparison": sales_comparison,
                "stockRows": [
                    {
                        "code": c.product,
                        "name": products[c.product].name,
                        "branch": c.branch,
                        "warehouse": c.warehouse,
                        "unit": c.unit,
                        "quantity": c.quantity,
                        "cost": c.cost,
                        "turnover": c.turnover,
                        "days": c.days,
                        "lastSale": last_sale.isoformat() if last_sale else "",
                        "daysSinceSale": (cutoff - last_sale).days if last_sale else None,
                        "lastSaleScope": "filial",
                    }
                    for _, c in sorted(current.items())
                    for last_sale in [_last_sale(sale_dates, _sale_key(c), cutoff)]
                ],
                "saleRows": [
                    {
                        "code": code,
                        "name": products[code].name,
                        "branch": branch,
                        "unit": unit,
                        "quantity": qty,
                    }
                    for (code, branch, unit), qty in sorted(monthly_sales.items())
                ],
            }
        )
    return tuple(result)
