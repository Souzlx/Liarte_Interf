"""Desempenho por produto sobre o cache mensal já aceito, sem reler a fonte.

Quantidades permanecem em milionésimos da UM original e custos em centavos.
Vendas são líquidas e não têm armazém. Giro é o indicador de cada posição da
fonte: a mediana abaixo nunca representa um giro consolidado calculado.
"""

from __future__ import annotations

from dataclasses import fields
from datetime import date
from decimal import Decimal
import math
import statistics
from threading import Event

from .inventory import SCALE, StockSelection, _checked, money, month_end, month_range, number
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
                "Há saldo negativo em uma posição; confira a base antes de estimar cobertura."
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


def _quantity(value, unit) -> str:
    return number(Decimal(value) / SCALE, 3) + " " + unit


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
            "evidence": (),
            "hypotheses": (),
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
    evidence, hypotheses = [], []
    if row["sold"] is not None:
        evidence.append(
            "Quantidade líquida registrada em "
            + report["targetLabel"]
            + ": "
            + _quantity(row["sold"], unit)
            + "."
        )
    if row["previous"] is not None and row["sold"] is not None:
        evidence.append(
            "Na janela anterior ("
            + report["baseLabel"]
            + "): "
            + _quantity(row["previous"], unit)
            + "; variação líquida "
            + _quantity(row["change"], unit)
            + (" (" + number(row["percentage"], 1) + "%)" if row["percentage"] is not None else "")
            + "."
        )
    elif report.get("reason"):
        evidence.append(report["reason"])
    if row["stockQuantity"] is not None:
        evidence.append(
            "Saldo observado no fechamento de "
            + _label(report["targetPeriod"])
            + ": "
            + _quantity(row["stockQuantity"], unit)
            + ", a custo de "
            + money(row["stockCost"])
            + "."
        )
    else:
        evidence.append(
            "Não há fechamento conhecido deste produto no mês de referência; o saldo não foi tratado como zero."
        )
    if row["turnover"] is not None:
        evidence.append(
            "Giro mensal da fonte: mediana de "
            + number(row["turnover"], 2)
            + " x/mês em "
            + str(row["turnoverCount"])
            + " posição(ões) com saldo positivo e indicador válido."
        )
    if row["matchedCount"]:
        evidence.append(
            "Entre os fechamentos finais das janelas, "
            + str(row["matchedCount"])
            + " posição(ões) presentes nos dois meses variaram "
            + _quantity(row["matchedStockChange"], unit)
            + "."
        )
    if row["stockCoverageChanged"]:
        evidence.append(
            "Há "
            + str(row["addedCount"])
            + " registro(s) apenas no fechamento-alvo e "
            + str(row["missingCount"])
            + " apenas no fechamento-base. Isso altera a cobertura observada, sem comprovar movimentos físicos."
        )
    if row["coverage"] is not None:
        evidence.append(
            "Cobertura estimada de "
            + number(row["coverage"], 1)
            + " dias se o ritmo líquido registrado se repetir. "
            + row["coverageReason"]
        )
    if row["noPositiveMonths"]:
        evidence.append(
            str(row["noPositiveMonths"])
            + " de "
            + str(window)
            + " meses completos da janela recente não tiveram quantidade líquida positiva registrada. Isso não exclui vendas compensadas por devoluções."
        )
    complete_sales = [
        point
        for point in _checked(series, cancel)
        if point["sales"] is not None and not point["salesPartial"]
    ]
    positive_sales = [point for point in _checked(complete_sales, cancel) if point["sales"] > 0]
    if positive_sales:
        peak = max(point["sales"] for point in _checked(positive_sales, cancel))
        peak_labels = [
            point["label"] for point in _checked(positive_sales, cancel) if point["sales"] == peak
        ]
        evidence.append(
            "Maior quantidade líquida mensal nos meses completos do recorte: "
            + _quantity(peak, unit)
            + " em "
            + ", ".join(peak_labels)
            + (" (empate entre meses)" if len(peak_labels) > 1 else "")
            + ". Isso identifica um pico observado, sem demonstrar sazonalidade."
        )
        if len(complete_sales) >= 4:
            leaders = sorted(positive_sales, key=lambda point: (-point["sales"], point["period"]))[
                :3
            ]
            positive_total = sum(point["sales"] for point in _checked(positive_sales, cancel))
            share = sum(point["sales"] for point in leaders) / positive_total * 100
            evidence.append(
                number(share, 1)
                + "% da soma das quantidades líquidas mensais positivas ficou em "
                + ", ".join(point["label"] for point in leaders)
                + ". Meses com líquido zero ou negativo ficam fora desse denominador."
            )
    if row["status"] == "negative":
        hypotheses.append(
            "Uma janela tem quantidade líquida negativa. Devoluções podem explicar esse sinal; confira os movimentos antes de interpretar o resultado como mudança de demanda."
        )
    if row["change"] is not None and row["matchedCount"] and row["status"] != "negative":
        if row["change"] < 0 and row["matchedStockChange"] > 0:
            hypotheses.append(
                "A venda líquida caiu no recorte enquanto o saldo cresceu nas posições comparáveis. Houve redução do ritmo de saída ou mudança na finalidade do item? Confira entradas, consumo interno e a adequação do saldo antes de concluir excesso de estoque."
            )
        elif row["change"] > 0 and row["matchedStockChange"] < 0:
            hypotheses.append(
                "A venda líquida cresceu no recorte enquanto o saldo caiu nas posições comparáveis. Convém revisar disponibilidade e planejamento de reposição; os fechamentos mensais não demonstram ruptura ou venda perdida."
            )
    if (
        row["stockQuantity"] is not None
        and row["stockQuantity"] > 0
        and row["sold"] is not None
        and row["sold"] <= 0
    ):
        hypotheses.append(
            "Há saldo positivo e nenhuma quantidade líquida positiva na janela recente. Confira se o item é destinado à venda ou ao consumo interno, e se devoluções ou a cobertura da base explicam o resultado, antes de classificá-lo como baixa movimentação."
        )
    if (
        row["stockBranches"]
        and row["salesBranches"]
        and row["stockBranches"] != row["salesBranches"]
    ):
        hypotheses.append(
            "Estoque e vendas têm filiais com registros diferentes. A exportação e o recorte cobrem os mesmos locais?"
        )
    if not hypotheses:
        hypotheses.append(
            "Para investigar a variação observada, confira a finalidade do item (venda ou consumo interno), a cobertura da base, entradas e mudanças de demanda. Esses dados não determinam uma causa."
        )
    limitations = [
        "Vendas são quantidades líquidas por filial; devoluções podem compensar saídas positivas. Um mês sem registro contribui zero apenas no calendário observado, sem certificar completude por produto ou filial.",
        "Quantidades de unidades diferentes não são somadas. As janelas têm o mesmo número de meses, mas podem ter números diferentes de dias de calendário.",
        "Giro é o indicador da fonte por posição, apresentado pela mediana das posições válidas com saldo positivo; não é um giro consolidado nem uma soma de giros.",
        "Cobertura estima dias ao ritmo registrado e não mede idade do lote. Tempo sem venda também não determina há quanto tempo as unidades estão no estoque.",
        "Não há dados de entradas, lotes, pedidos não atendidos, preços de venda ou motivos das transações nesta análise. Não é possível confirmar reposição, ruptura, excesso de compras, margem ou causa da variação.",
        "Confira se o item é destinado à venda ou ao consumo interno. Picos mensais isolados não comprovam sazonalidade, e custo do estoque não representa receita.",
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
        "evidence": tuple(evidence),
        "hypotheses": tuple(hypotheses),
        "limitations": tuple(limitations),
        "reason": report.get("reason", ""),
    }
    checkpoint(cancel)
    return result
