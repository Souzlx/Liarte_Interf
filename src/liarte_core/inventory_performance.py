"""Desempenho por produto sobre o cache mensal já aceito, sem reler a fonte.

Quantidades permanecem em milionésimos da UM original e custos em centavos.
Vendas são líquidas e não têm armazém. Giro é o indicador de cada posição da
fonte: a mediana abaixo nunca representa um giro consolidado calculado.
"""

from __future__ import annotations

from dataclasses import fields
from datetime import date
import math
import statistics
from threading import Event

from .inventory import SCALE, StockSelection, _checked, month_end, month_range
from .query import checkpoint


def _label(period: str) -> str:
    return period[5:] + "/" + period[:4]


def _shift(period: str, offset: int) -> str:
    first = date.fromisoformat(period + "-01")
    value = first.year * 12 + first.month - 1 + offset
    year, month = divmod(value, 12)
    if not 1 <= year <= 9999:
        raise ValueError("O período não permite formar as duas janelas de comparação.")
    return f"{year:04d}-{month + 1:02d}"


def _range_label(periods: tuple[str, ...]) -> str:
    if not periods:
        return ""
    return _label(periods[0]) + (" a " + _label(periods[-1]) if len(periods) > 1 else "")


def _integer(value) -> int:
    if type(value) is not int:
        raise ValueError(
            "As quantidades e os custos mensais devem manter a escala inteira original."
        )
    return value


def _source_turnover(row) -> float | None:
    value = row.get("turnover")
    if type(value) in (int, float) and math.isfinite(value) and value >= 0 and row["quantity"] > 0:
        return float(value)
    return None


def _permitted(row, selected: StockSelection, *, stock: bool) -> bool:
    return (
        (not selected.product or row["code"] == selected.product)
        and (not selected.unit or row["unit"] == selected.unit)
        and (not selected.branch or row["branch"] == selected.branch)
        and (not stock or not selected.warehouse or row["warehouse"] == selected.warehouse)
    )


def _prepare(months, selected: StockSelection, window: int, cancel: Event):
    if type(window) is not int or window not in (1, 3, 6):
        raise ValueError("Selecione uma janela de 1, 3 ou 6 meses.")
    periods = month_range(selected.start, selected.end)
    allowed = set(periods)
    indexed = {}
    for month in _checked(months, cancel):
        period = month["period"]
        # Validate dates before comparing strings; malformed cache entries must
        # not accidentally become an apparently comparable calendar month.
        if len(period) != 7 or date.fromisoformat(period + "-01").strftime("%Y-%m") != period:
            raise ValueError("O cache contém um mês inválido.")
        if period not in allowed:
            continue
        if period in indexed:
            raise ValueError("O cache contém mais de um registro para o mesmo mês.")
        indexed[period] = month
    endpoint = selected.end
    final = indexed.get(endpoint)
    excluded = ()
    # A partial final month is excluded once. An absent/unobserved month is a
    # gap, not permission to walk backwards until a more convenient window.
    if final and (final.get("partial", False) or final.get("stockPartial", False)):
        excluded = (endpoint,)
        endpoint = _shift(endpoint, -1)
    target = tuple(_shift(endpoint, i) for i in range(1 - window, 1))
    base = tuple(_shift(endpoint, i) for i in range(1 - 2 * window, 1 - window))
    return periods, indexed, base, target, excluded


def _window_reason(periods, indexed, selected: StockSelection, *, unit=None) -> str:
    if selected.warehouse:
        return (
            "Vendas não podem ser atribuídas ao armazém. Retire esse filtro para comparar produtos."
        )
    for period in periods:
        month = indexed.get(period)
        if month is None:
            return (
                "Falta o mês "
                + _label(period)
                + "; as duas janelas precisam ser consecutivas e estar no recorte."
            )
        if month.get("partial", False):
            return "O mês " + _label(period) + " é parcial; ele não entra na comparação de vendas."
        if not month.get("salesObserved", False):
            return (
                "Vendas não observadas em "
                + _label(period)
                + "; meses indisponíveis não representam zero."
            )
        if unit is not None and month.get("salesQuantity", {}).get(unit) is None:
            return "Vendas da unidade " + unit + " não estão observadas em " + _label(period) + "."
    return ""


def _stock_known(month) -> bool:
    return bool(
        month
        and not month.get("stockPartial", False)
        and (month.get("stockCost") is not None or month.get("stockRows"))
    )


def _days(periods) -> int:
    return sum(month_end(period).day for period in periods)


def _new_row(code, name, unit):
    return {
        "code": code,
        "name": name,
        "unit": unit,
        "sold": None,
        "previous": None,
        "change": None,
        "percentage": None,
        "status": "insufficient",
        "stockQuantity": None,
        "stockCost": None,
        "turnover": None,
        "turnoverCount": 0,
        "turnoverInvalidCount": 0,
        "coverage": None,
        "coverageReason": "Sem fechamento conhecido do produto no mês de referência.",
        "matchedStockChange": None,
        "matchedStockCostChange": None,
        "matchedCount": 0,
        "addedCount": None,
        "missingCount": None,
        "stockCoverageChanged": False,
        "stockBranches": (),
        "salesBranches": (),
        "negativeStockPositionCount": 0,
        "positiveMonths": None,
        "noPositiveMonths": None,
    }


def _selection_key(selected: StockSelection) -> tuple:
    return tuple(getattr(selected, field.name) for field in fields(selected))


def _status(before: int | None, after: int | None) -> str:
    if before is None or after is None:
        return "insufficient"
    if before < 0 or after < 0:
        return "negative"
    if after == 0:
        return "no_positive"
    if before == 0:
        return "resumed"
    return "up" if after > before else "down" if after < before else "stable"


def _stock_pairs(before, after, known: bool, cancel: Event):
    """Return per-product changes of the exact positions present in both ends."""
    result = {}
    if not known:
        return result
    for key, row in _checked(before.items(), cancel):
        group = result.setdefault((row["code"], row["unit"]), [0, 0, 0, 0, 0])
        other = after.get(key)
        if other is None:
            group[4] += 1
        else:
            group[0] += other["quantity"] - row["quantity"]
            group[1] += other["cost"] - row["cost"]
            group[2] += 1
    for key, row in _checked(after.items(), cancel):
        if key not in before:
            result.setdefault((row["code"], row["unit"]), [0, 0, 0, 0, 0])[3] += 1
    return result


def analyze_product_performance(
    months,
    selected: StockSelection,
    *,
    window: int = 3,
    cancel: Event | None = None,
) -> dict:
    """Compare adjacent equal calendar windows using complete monthly facts.

    ``matchedStockChange`` is a scaled quantity, not money. Its cost equivalent
    is ``matchedStockCostChange``. Both compare the final snapshots of B and T,
    only at identical product/branch/warehouse/unit positions. Rows remain
    complete for export; pagination/ranking belongs to the presentation layer.
    """
    cancel = cancel if cancel is not None else Event()
    checkpoint(cancel)
    periods, indexed, base, target, excluded = _prepare(months, selected, window, cancel)
    base_reason = _window_reason(base, indexed, selected)
    target_reason = _window_reason(target, indexed, selected)
    reason = target_reason or base_reason
    exclusion = (
        "Mês parcial "
        + _label(excluded[0])
        + " excluído; a referência é "
        + _label(target[-1])
        + "."
        if excluded
        else ""
    )
    if exclusion:
        reason = (reason + " " + exclusion).strip()
    rows = {}
    totals_base, totals_target = {}, {}
    target_sales_branches, target_positive_months = {}, {}
    base_positions, target_positions = {}, {}
    base_set, target_set = set(base), set(target)
    units = {selected.unit} if selected.unit else set()
    for period in _checked(periods, cancel):
        month = indexed.get(period)
        if month is None:
            continue
        units.update(month.get("salesQuantity", {}))
        units.update(month.get("stockQuantity", {}))
        monthly_totals = {}
        for source in _checked(month.get("saleRows", ()), cancel):
            if not _permitted(source, selected, stock=False):
                continue
            key = source["code"], source["unit"]
            units.add(key[1])
            if key not in rows:
                rows[key] = _new_row(key[0], source["name"], key[1])
            qty = _integer(source["quantity"])
            if period in base_set:
                totals_base[key] = totals_base.get(key, 0) + qty
            if period in target_set:
                totals_target[key] = totals_target.get(key, 0) + qty
                target_sales_branches.setdefault(key, set()).add(source["branch"])
                monthly_totals[key] = monthly_totals.get(key, 0) + qty
        if period in target_set:
            for key, qty in _checked(monthly_totals.items(), cancel):
                if qty > 0:
                    target_positive_months[key] = target_positive_months.get(key, 0) + 1
        for source in _checked(month.get("stockRows", ()), cancel):
            if not _permitted(source, selected, stock=True):
                continue
            key = source["code"], source["unit"]
            units.add(key[1])
            if key not in rows:
                rows[key] = _new_row(key[0], source["name"], key[1])
            _integer(source["quantity"])
            _integer(source["cost"])
            position = source["code"], source["branch"], source["warehouse"], source["unit"]
            for endpoint, positions in ((base[-1], base_positions), (target[-1], target_positions)):
                if period == endpoint:
                    if position in positions:
                        raise ValueError("Há posições de estoque duplicadas no fechamento mensal.")
                    positions[position] = source
    if selected.unit:
        units = {selected.unit}
    before_month, after_month = indexed.get(base[-1]), indexed.get(target[-1])
    pairs = _stock_pairs(
        base_positions,
        target_positions,
        _stock_known(before_month) and _stock_known(after_month),
        cancel,
    )
    stock_branches, turnovers = {}, {}
    if _stock_known(after_month):
        for source in _checked(target_positions.values(), cancel):
            key = source["code"], source["unit"]
            row = rows[key]
            row["stockQuantity"] = (row["stockQuantity"] or 0) + source["quantity"]
            row["stockCost"] = (row["stockCost"] or 0) + source["cost"]
            row["negativeStockPositionCount"] += int(source["quantity"] < 0)
            stock_branches.setdefault(key, set()).add(source["branch"])
            giro = _source_turnover(source)
            if giro is not None:
                turnovers.setdefault(key, []).append(giro)
            elif source["quantity"] > 0 and source.get("turnover") is not None:
                row["turnoverInvalidCount"] += 1
    unit_reasons = {
        unit: (
            _window_reason(base, indexed, selected, unit=unit),
            _window_reason(target, indexed, selected, unit=unit),
        )
        for unit in _checked(sorted(units), cancel)
    }
    days = _days(target)
    for key, row in _checked(rows.items(), cancel):
        b_reason, t_reason = unit_reasons[row["unit"]]
        row["previous"] = None if b_reason else totals_base.get(key, 0)
        row["sold"] = None if t_reason else totals_target.get(key, 0)
        row["status"] = _status(row["previous"], row["sold"])
        row["reason"] = t_reason or b_reason
        if row["previous"] is not None and row["sold"] is not None:
            row["change"] = row["sold"] - row["previous"]
            if row["previous"] > 0 and row["sold"] >= 0:
                row["percentage"] = row["change"] / row["previous"] * 100
        if not t_reason:
            row["positiveMonths"] = target_positive_months.get(key, 0)
            row["noPositiveMonths"] = window - row["positiveMonths"]
        values = turnovers.get(key, ())
        row["turnover"] = statistics.median(values) if values else None
        row["turnoverCount"] = len(values)
        row["stockBranches"] = tuple(sorted(stock_branches.get(key, ())))
        row["salesBranches"] = tuple(sorted(target_sales_branches.get(key, ())))
        if key in pairs:
            qty, cost, count, added, missing = pairs[key]
            row.update(
                matchedStockChange=qty,
                matchedStockCostChange=cost,
                matchedCount=count,
                addedCount=added,
                missingCount=missing,
                stockCoverageChanged=bool(added or missing),
            )
        if selected.warehouse:
            row["coverageReason"] = (
                "Vendas sem alocação por armazém; cobertura indisponível neste filtro."
            )
        elif t_reason:
            row["coverageReason"] = (
                "A cobertura exige uma janela recente de meses completos observados. " + t_reason
            )
        elif row["stockQuantity"] is None:
            pass
        elif row["negativeStockPositionCount"]:
            row["coverageReason"] = (
                "Cobertura indisponível: há saldo negativo em uma posição."
            )
        elif row["sold"] <= 0:
            row["coverageReason"] = (
                "Sem quantidade líquida positiva na janela recente para estimar cobertura."
            )
        elif row["stockBranches"] != row["salesBranches"]:
            row["coverageReason"] = (
                "Filiais com estoque e com vendas registradas diferem; os escopos não permitem estimar cobertura conjunta."
            )
        else:
            row["coverage"] = row["stockQuantity"] * days / row["sold"]
            row["coverageReason"] = (
                "Dias estimados pelo saldo do fechamento e pelo ritmo líquido registrado em "
                + str(days)
                + " dias de calendário, nas mesmas filiais. Não representa idade do lote."
            )
    sales_scope = (
        after_month.get("salesScope", "")
        if after_month
        else "Recorte mensal selecionado; sem mês-alvo observado."
    )
    stock_scope = (
        after_month.get("scope", "Sem fechamento observado.")
        if after_month
        else "Sem fechamento observado."
    )
    scope = "Estoque: " + stock_scope + " Vendas: " + sales_scope
    scope += " Quantidades separadas por unidade; vendas líquidas podem incluir devoluções."
    if selected.abc or selected.activity or selected.balance:
        scope += " ABC, atividade e saldo selecionam a coorte atual, não a situação histórica."
    result = {
        "window": window,
        "selectionStart": selected.start,
        "selectionEnd": selected.end,
        "selectionKey": _selection_key(selected),
        "basePeriods": base,
        "targetPeriods": target,
        "baseLabel": _range_label(base),
        "targetLabel": _range_label(target),
        "targetPeriod": target[-1],
        "baseDays": _days(base),
        "targetDays": days,
        "excludedPeriods": excluded,
        "available": not base_reason and not target_reason,
        "reason": reason,
        "scope": scope.strip(),
        "notice": (
            (exclusion + " " if exclusion else "")
            + "Janelas de "
            + str(window)
            + " mês(es): base com "
            + str(_days(base))
            + " dias e recente com "
            + str(days)
            + " dias de calendário. Os totais não são ajustados pelo número de dias."
        ),
        "units": tuple(sorted(units)),
        "rows": tuple(rows[key] for key in _checked(sorted(rows), cancel)),
    }
    checkpoint(cancel)
    return result


def _detail_indicators(row, report, series, cancel):
    """Keep observations numeric, with the original scale and source periods.

    Values are suitable for reconciliation and export without parsing a
    generated sentence. Peak ties retain every month. Concentration uses only
    positive complete-month totals and publishes its numerator and denominator.
    """
    indicators = []
    unit = row["unit"]
    base, target = tuple(report["basePeriods"]), tuple(report["targetPeriods"])
    closing = (report["targetPeriod"],)
    endpoints = (base[-1], target[-1])

    def add(key, label, value, symbol, periods, *, scale=1, reason=""):
        checkpoint(cancel)
        indicators.append({
            "key": key, "label": label, "value": value, "scale": scale,
            "unit": symbol, "periods": tuple(periods),
            "reason": reason if value is None else "",
        })

    sales_reason = row.get("reason", "")
    add("previous", "Vendas líquidas · anterior", row["previous"], unit, base,
        scale=SCALE, reason=sales_reason)
    add("sold", "Vendas líquidas · recente", row["sold"], unit, target,
        scale=SCALE, reason=sales_reason)
    add("change", "Diferença das vendas líquidas", row["change"], unit, base + target,
        scale=SCALE, reason=sales_reason)
    add("percentage", "Variação das vendas líquidas", row["percentage"], "%", base + target,
        reason=sales_reason or "Percentual exige base positiva e janela recente não negativa.")
    add("stockQuantity", "Saldo no fechamento", row["stockQuantity"], unit, closing,
        scale=SCALE, reason="Sem fechamento conhecido do produto.")
    add("stockCost", "Estoque a custo", row["stockCost"], "R$", closing,
        scale=100, reason="Sem fechamento conhecido do produto.")
    add("turnover", "Giro da fonte · mediana", row["turnover"], "x/mês", closing,
        reason="Sem posições elegíveis com giro conhecido.")
    add("turnoverCount", "Posições com giro elegível", row["turnoverCount"], "posições", closing)
    add("coverage", "Cobertura estimada", row["coverage"], "dias", target,
        reason=row.get("coverageReason", ""))
    paired_known = row["matchedStockChange"] is not None
    paired_reason = "Fechamentos comparáveis indisponíveis."
    add("matchedStockChange", "Variação do saldo · posições pareadas",
        row["matchedStockChange"], unit, endpoints, scale=SCALE, reason=paired_reason)
    add("matchedStockCostChange", "Variação do custo · posições pareadas",
        row["matchedStockCostChange"], "R$", endpoints, scale=100, reason=paired_reason)
    add("matchedCount", "Posições pareadas", row["matchedCount"] if paired_known else None,
        "posições", endpoints, reason=paired_reason)
    add("addedCount", "Posições somente no fechamento recente", row["addedCount"],
        "posições", closing, reason=paired_reason)
    add("missingCount", "Posições somente no fechamento anterior", row["missingCount"],
        "posições", (base[-1],), reason=paired_reason)
    add("positiveMonths", "Meses com quantidade líquida > 0", row["positiveMonths"],
        "meses", target, reason=sales_reason)
    add("noPositiveMonths", "Meses com quantidade líquida ≤ 0", row["noPositiveMonths"],
        "meses", target, reason=sales_reason)
    add("baseDays", "Dias de calendário · anterior", report["baseDays"], "dias", base)
    add("targetDays", "Dias de calendário · recente", report["targetDays"], "dias", target)
    add("stockBranchCount", "Filiais com registros de estoque",
        len(row["stockBranches"]) if row["stockQuantity"] is not None else None,
        "filiais", closing, reason="Sem fechamento conhecido do produto.")
    add("salesBranchCount", "Filiais com registros de vendas",
        len(row["salesBranches"]) if row["sold"] is not None else None,
        "filiais", target, reason=sales_reason)

    complete = [point for point in _checked(series, cancel)
                if point["sales"] is not None and not point["salesPartial"]]
    complete_periods = tuple(point["period"] for point in complete)
    add("completeSalesMonths", "Meses completos com vendas observadas", len(complete),
        "meses", complete_periods)
    peak = max((point["sales"] for point in _checked(complete, cancel)), default=None)
    peak_periods = tuple(point["period"] for point in _checked(complete, cancel)
                         if point["sales"] == peak)
    add("peakMonthlySales", "Máximo mensal de vendas líquidas", peak, unit, peak_periods,
        scale=SCALE, reason="Sem meses completos com vendas observadas.")
    add("peakMonthCount", "Meses no máximo mensal", len(peak_periods) if peak is not None else None,
        "meses", peak_periods, reason="Sem meses completos com vendas observadas.")
    positive = [point for point in _checked(complete, cancel) if point["sales"] > 0]
    leaders = sorted(positive, key=lambda point: (-point["sales"], point["period"]))[:3]
    leader_periods = tuple(point["period"] for point in leaders)
    positive_periods = tuple(point["period"] for point in positive)
    total = sum(point["sales"] for point in _checked(positive, cancel)) if complete else None
    leading_total = sum(point["sales"] for point in _checked(leaders, cancel)) if complete else None
    add("top3PositiveSales", "Vendas líquidas positivas · até três maiores meses",
        leading_total, unit, leader_periods, scale=SCALE,
        reason="Sem meses completos com vendas observadas.")
    add("positiveMonthlySales", "Vendas líquidas positivas · denominador",
        total, unit, positive_periods, scale=SCALE,
        reason="Sem meses completos com vendas observadas.")
    add("top3PositiveShare", "Participação dos até três maiores meses positivos",
        leading_total / total * 100 if total else None, "%", leader_periods,
        reason="Sem quantidade mensal líquida positiva no denominador.")
    return tuple(indicators)


def product_performance_detail(
    months,
    selected: StockSelection,
    code: str,
    unit: str,
    *,
    window: int = 3,
    report: dict | None = None,
    cancel: Event | None = None,
) -> dict:
    """Build one product's history on demand, reusing an accepted report."""
    cancel = cancel if cancel is not None else Event()
    checkpoint(cancel)
    if report is None:
        report = analyze_product_performance(months, selected, window=window, cancel=cancel)
    elif (
        report.get("window") != window
        or report.get("selectionStart", selected.start) != selected.start
        or report.get("selectionEnd", selected.end) != selected.end
        or report.get("selectionKey", _selection_key(selected)) != _selection_key(selected)
    ):
        raise ValueError("Atualize o relatório para o período e a janela selecionados.")
    row = next(
        (
            r
            for r in _checked(report.get("rows", ()), cancel)
            if r["code"] == code and r["unit"] == unit
        ),
        None,
    )
    if row is None:
        return {
            "code": code,
            "name": "",
            "unit": unit,
            "row": None,
            "series": (),
            "indicators": (),
            "limitations": (),
            "reason": "Produto e unidade indisponíveis no recorte mensal selecionado.",
        }
    periods, indexed, _, _, _ = _prepare(months, selected, window, cancel)
    series = []
    previous_positions, previous_known = {}, False
    for period in _checked(periods, cancel):
        month = indexed.get(period)
        positions, values = {}, []
        qty = cost = None
        sales = None
        if month is not None:
            for source in _checked(month.get("stockRows", ()), cancel):
                if (
                    source["code"] != code
                    or source["unit"] != unit
                    or not _permitted(source, selected, stock=True)
                ):
                    continue
                position = source["code"], source["branch"], source["warehouse"], source["unit"]
                if position in positions:
                    raise ValueError("Há posições de estoque duplicadas no fechamento mensal.")
                positions[position] = source
                qty = (qty or 0) + _integer(source["quantity"])
                cost = (cost or 0) + _integer(source["cost"])
                giro = _source_turnover(source)
                if giro is not None:
                    values.append(giro)
            if (
                not selected.warehouse
                and month.get("salesObserved", False)
                and month.get("salesQuantity", {}).get(unit) is not None
            ):
                sales = sum(
                    _integer(source["quantity"])
                    for source in _checked(month.get("saleRows", ()), cancel)
                    if source["code"] == code
                    and source["unit"] == unit
                    and _permitted(source, selected, stock=False)
                )
        known = _stock_known(month)
        pairs = _stock_pairs(previous_positions, positions, previous_known and known, cancel)
        paired = pairs.get((code, unit))
        sales_partial = bool(month and month.get("partial", False))
        stock_partial = bool(month and month.get("stockPartial", False))
        series.append(
            {
                "period": period,
                "label": month.get("label", _label(period)) if month else _label(period),
                "partial": sales_partial or stock_partial,
                "salesPartial": sales_partial,
                "stockPartial": stock_partial,
                "salesObserved": sales is not None,
                "sales": sales,
                "quantity": qty,
                "cost": cost,
                "turnover": statistics.median(values) if values else None,
                "count": len(values),
                "turnoverCount": len(values),
                "matchedStockChange": paired[0] if paired else None,
                "matchedStockCostChange": paired[1] if paired else None,
                "matchedCount": paired[2] if paired else 0,
                "addedCount": paired[3] if paired else None,
                "missingCount": paired[4] if paired else None,
            }
        )
        # Missing/partial months explicitly interrupt adjacent comparisons.
        previous_positions, previous_known = positions, known
    indicators = _detail_indicators(row, report, series, cancel)
    limitations = [
        "Vendas são quantidades líquidas por filial; devoluções podem compensar saídas positivas. Um mês sem registro contribui zero apenas no calendário observado, sem certificar completude por produto ou filial.",
        "Quantidades de unidades diferentes não são somadas. As janelas têm o mesmo número de meses, mas podem ter números diferentes de dias de calendário.",
        "Giro é o indicador da fonte por posição, apresentado pela mediana das posições válidas com saldo positivo; não é um giro consolidado nem uma soma de giros.",
        "Cobertura estima dias ao ritmo registrado e não mede idade do lote. Tempo sem venda também não determina há quanto tempo as unidades estão no estoque.",
        "Estoque a custo não representa receita; esta análise não contém entradas, lotes, pedidos não atendidos ou preços de venda.",
        "Máximo mensal inclui os empates entre meses completos observados. Participação dos três maiores meses usa apenas quantidades líquidas mensais positivas no numerador e no denominador.",
    ]
    if selected.warehouse:
        limitations.append(
            "O filtro de armazém permite consultar fechamentos, mas impede atribuir vendas e estimar cobertura."
        )
    if selected.abc or selected.activity or selected.balance:
        limitations.append(
            "Filtros ABC, atividade e saldo usam a situação atual para definir a coorte histórica."
        )
    result = {
        "code": code,
        "name": row["name"],
        "unit": unit,
        "row": row,
        "series": tuple(series),
        "indicators": indicators,
        "limitations": tuple(limitations),
        "reason": report.get("reason", ""),
    }
    checkpoint(cancel)
    return result
