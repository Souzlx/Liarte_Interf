"""Bounded Qt presentations prepared beside a complete monthly comparison."""

from __future__ import annotations

from decimal import Decimal

from liarte_core.inventory import SCALE, money, number
from liarte_core.inventory_compare import compare_inventory_months
from liarte_core.query import checkpoint


def comparison_pair(months, base="", target=""):
    periods = tuple(month["period"] for month in months)
    if not periods:
        return "", ""
    if base in periods and target in periods:
        return base, target
    complete = tuple(
        month["period"] for month in months
        if month["stockCost"] is not None and not month["stockPartial"]
    ) or tuple(
        month["period"] for month in months
        if month["salesObserved"] and not month["partial"]
    ) or periods
    target = target if target in periods else complete[-1]
    if base not in periods:
        base = next((period for period in reversed(complete) if period < target), "")
        base = base or next((period for period in periods if period != target), target)
    return base, target


def _metric(summary, key, label, unit, result, branches, cancel):
    currency = key == "stock"

    def display(value, *, signed=False):
        if value is None:
            return "—"
        prefix = ("+" if value > 0 else "−" if value < 0 else "") if signed else ""
        value = abs(value) if signed else value
        return prefix + (money(value) if currency else number(Decimal(value) / SCALE, 3) + " " + unit)

    prepared = {}
    for dimension, field in (("products", "code"), ("branches", "branch")):
        rows = []
        for row in summary[dimension][:8]:
            checkpoint(cancel)
            identifier = row[field]
            name = row["name"]
            if field == "branch" and branches.get(identifier):
                name = "Filial " + identifier + " · " + branches[identifier]
            coverage = (
                f"{row['matchedCount']} posições comparáveis · "
                f"{row['addedCount']} registros só em {result['targetLabel']} · "
                f"{row['missingCount']} só em {result['baseLabel']}"
                if key != "sales" else "Vendas observadas da filial, sem atribuição a armazém."
            )
            rows.append({
                "key": row["key"], field: identifier, "name": name,
                "before": display(row["before"]), "after": display(row["after"]),
                "change": display(row["change"], signed=True),
                "matched": display(row["matchedChange"], signed=True),
                "coverage": coverage,
                "detail": (
                    "Comparáveis: " + display(row["matchedChange"], signed=True)
                    + " · só no comparado: " + display(row["addedValue"])
                    + " · só na base: " + display(row["missingValue"])
                    if key != "sales" else "Variação líquida observada na unidade selecionada."
                ),
                # QML uses this only for the direction, never numeric formatting.
                "value": float(row["change"]),
            })
        prepared[dimension] = rows
    percent = summary["percentage"]
    percentage = (
        ("+" if percent > 0 else "") + number(percent, 1) + "%"
        if percent is not None else "Percentual indisponível: base ausente, nula ou negativa"
    )
    if not summary["available"]:
        percentage = "Percentual indisponível neste recorte"
    coverage = (
        f"{summary['matchedCount']} posições comparáveis · "
        f"{summary['addedCount']} registros só em {result['targetLabel']} · "
        f"{summary['missingCount']} só em {result['baseLabel']}. "
        if key != "sales" and summary["available"] else ""
    ) + summary.get("coverageNote", "")
    return {
        "key": key, "label": label, "unit": "R$" if currency else unit,
        "before": display(summary["before"]), "after": display(summary["after"]),
        "change": display(summary["change"], signed=True), "percentage": percentage,
        "available": summary["available"], "reason": summary["reason"],
        "matched": display(summary["matchedChange"], signed=True),
        "added": display(summary["addedValue"]), "missing": display(summary["missingValue"]),
        "coverage": coverage,
        "productCount": len(summary["products"]), "branchCount": len(summary["branches"]),
        **prepared,
    }


def prepare_comparison(months, base, target, branches, cancel, *, compare=compare_inventory_months):
    base, target = comparison_pair(months, base, target)
    if not base:
        return None, {}, "", ""
    result = compare(months, base, target, cancel=cancel)
    stock = _metric(result["stock"], "stock", "Estoque a custo", "", result, branches, cancel)
    views = {}
    for unit in result["units"] or ("",):
        checkpoint(cancel)
        metrics = [stock]
        for field, key, label in (
            ("quantityByUnit", "quantity", "Quantidade em estoque"),
            ("salesByUnit", "sales", "Vendas líquidas"),
        ):
            summary = result[field].get(unit)
            if summary is not None:
                metrics.append(_metric(summary, key, label, unit, result, branches, cancel))
        views[unit] = {
            "base": base, "target": target,
            "baseLabel": result["baseLabel"], "targetLabel": result["targetLabel"],
            "unit": unit, "metrics": metrics,
            "notice": "Comparação direta entre os meses escolhidos, sem interpolar intervalos. "
            "Estoque a custo considera todas as unidades do recorte; quantidades e vendas usam "
            "a unidade selecionada acima.",
        }
    checkpoint(cancel)
    return result, views, base, target
