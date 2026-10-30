"""Compare two observed monthly snapshots without inferring physical movements.

Input is the complete result of analyze_monthly_inventory, not a truncated
presentation. Stock positions match by product/branch/warehouse/unit; sales
match by product/branch/unit. Integer cents and scaled quantities stay exact.
"""

from __future__ import annotations

from datetime import date
import math
import re
from threading import Event

from .inventory import _checked
from .query import checkpoint


def _period(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}", value):
        raise ValueError("Selecione meses válidos no formato AAAA-MM.")
    try:
        date.fromisoformat(value + "-01")
    except ValueError as exc:
        raise ValueError("Selecione meses válidos no formato AAAA-MM.") from exc
    return value


def _label(period):
    return period[5:] + "/" + period[:4]


def _integer(value):
    if value is not None and type(value) is not int:
        raise ValueError("Valores mensais devem ser inteiros na escala original.")
    return value


def _index(rows, *, sales, cancel):
    result = {}
    for row in _checked(rows, cancel):
        key = (
            (row["code"], row["branch"], row["unit"])
            if sales
            else (row["code"], row["branch"], row["warehouse"], row["unit"])
        )
        if key in result:
            raise ValueError("Os dados mensais contêm registros duplicados para a mesma chave.")
        result[key] = row
    return result


def _ordered(groups, cancel):
    count = 0

    def key(row):
        nonlocal count
        if count % 512 == 0:
            checkpoint(cancel)
        count += 1
        return -abs(row["change"]), row["key"]

    rows = tuple(sorted(_checked(groups.values(), cancel), key=key))
    checkpoint(cancel)
    return rows


class _Comparison:
    def __init__(self, before, after, available, reason, field, *, zero_missing=False):
        self.before, self.after = _integer(before), _integer(after)
        self.available, self.reason, self.field = available, reason, field
        self.zero_missing = zero_missing
        self.matched_change = self.added_value = self.missing_value = 0
        self.matched_count = self.added_count = self.missing_count = 0
        self.products, self.branches = {}, {}

    def _group(self, groups, identity, row, dimension):
        if identity not in groups:
            groups[identity] = {
                "key": identity,
                dimension: identity,
                "name": row["name"] if dimension == "code" else "Filial " + identity,
                "before": 0 if self.zero_missing else None,
                "after": 0 if self.zero_missing else None,
                "change": 0,
                "matchedChange": 0,
                "addedValue": 0,
                "missingValue": 0,
                "matchedCount": 0,
                "addedCount": 0,
                "missingCount": 0,
            }
        return groups[identity]

    def add(self, before, after):
        row = after if after is not None else before
        first = _integer(before[self.field]) if before is not None else None
        second = _integer(after[self.field]) if after is not None else None
        if before is None:
            kind, count, amount, change = "addedValue", "addedCount", second, second
            self.added_value += second
            self.added_count += 1
        elif after is None:
            kind, count, amount, change = "missingValue", "missingCount", first, -first
            self.missing_value += first
            self.missing_count += 1
        else:
            kind, count, amount, change = (
                "matchedChange",
                "matchedCount",
                second - first,
                second - first,
            )
            self.matched_change += change
            self.matched_count += 1
        for group in (
            self._group(self.products, row["code"], row, "code"),
            self._group(self.branches, row["branch"], row, "branch"),
        ):
            if first is not None:
                group["before"] = (group["before"] or 0) + first
            if second is not None:
                group["after"] = (group["after"] or 0) + second
            group["change"] += change
            group[kind] += amount
            group[count] += 1

    def result(self, cancel):
        change = self.after - self.before if self.available else None
        percentage = None
        if self.available and self.before > 0:
            try:
                value = change / self.before * 100
                percentage = value if math.isfinite(value) else None
            except OverflowError:
                pass
        return {
            "available": self.available,
            "reason": self.reason,
            "before": self.before,
            "after": self.after,
            "change": change,
            "percentage": percentage,
            "matchedChange": self.matched_change if self.available else None,
            "addedValue": self.added_value if self.available else None,
            "missingValue": self.missing_value if self.available else None,
            "matchedCount": self.matched_count,
            "addedCount": self.added_count,
            "missingCount": self.missing_count,
            "products": _ordered(self.products, cancel),
            "branches": _ordered(self.branches, cancel),
        }


def _reason(before, after, base, target, *, sales):
    labels = (base, target) if base != target else (base,)
    endpoints = ((base, before), (target, after))
    if sales:
        missing = [period for period, month in endpoints if not month.get("salesObserved", False)]
        if missing:
            scopes = dict.fromkeys(month.get("salesScope", "") for _, month in endpoints)
            detail = " ".join(scope + "." for scope in scopes if scope)
            return (
                "Vendas indisponíveis em "
                + ", ".join(_label(p) for p in dict.fromkeys(missing))
                + ". Ausência de dados não representa zero. "
                + detail
            )
        partial = [period for period, month in endpoints if month.get("partial", False)]
        subject = "vendas"
    else:
        missing = [period for period, month in endpoints if month.get("stockCost") is None]
        if missing:
            return (
                "Sem fechamento em "
                + ", ".join(_label(p) for p in dict.fromkeys(missing))
                + ". Meses ausentes não representam saldo zero."
            )
        partial = [period for period, month in endpoints if month.get("stockPartial", False)]
        subject = "estoque"
    if partial:
        return (
            "Comparação de "
            + subject
            + " indisponível: mês parcial em "
            + ", ".join(_label(p) for p in dict.fromkeys(partial))
            + "."
        )
    if len(labels) == 1:
        return "O mesmo mês foi selecionado nos dois campos; a diferença observada é zero."
    return ""


def compare_inventory_months(months, base_period, target_period, *, cancel=None):
    """Compare explicit endpoints, including nonconsecutive or inverted months.

    Missing complete-month sale records contribute zero under the existing
    observation contract. Missing stock positions contribute only to coverage
    accounting; their unknown physical balance is never presented as zero.
    """
    cancel = cancel if cancel is not None else Event()
    checkpoint(cancel)
    base_period, target_period = _period(base_period), _period(target_period)
    available_months = {}
    for month in _checked(months, cancel):
        period = month["period"]
        if period in available_months:
            raise ValueError("Os dados mensais contêm o mesmo mês mais de uma vez.")
        available_months[period] = month
    if base_period not in available_months or target_period not in available_months:
        raise ValueError("Selecione dois meses disponíveis no recorte carregado.")
    before, after = available_months[base_period], available_months[target_period]
    units = tuple(
        sorted(
            set(
                key
                for month in (before, after)
                for metric in ("stockQuantity", "salesQuantity")
                for key in month.get(metric, {})
            )
        )
    )
    stock_reason = _reason(before, after, base_period, target_period, sales=False)
    stock_available = (
        before.get("stockCost") is not None
        and after.get("stockCost") is not None
        and not before.get("stockPartial", False)
        and not after.get("stockPartial", False)
    )
    stock = _Comparison(
        before.get("stockCost"), after.get("stockCost"), stock_available, stock_reason, "cost"
    )
    quantities = {}
    for unit in _checked(units, cancel):
        first = before.get("stockQuantity", {}).get(unit)
        second = after.get("stockQuantity", {}).get(unit)
        reason = stock_reason
        if stock_available and (first is None or second is None):
            reason = (
                "Sem fechamento conhecido de "
                + unit
                + " nos dois meses selecionados. Quantidade ausente não representa zero."
            )
        quantities[unit] = _Comparison(
            first,
            second,
            stock_available and first is not None and second is not None,
            reason,
            "quantity",
        )
    if stock_available:
        first = _index(before.get("stockRows", ()), sales=False, cancel=cancel)
        second = (
            first
            if before is after
            else _index(after.get("stockRows", ()), sales=False, cancel=cancel)
        )
        for key, row in _checked(first.items(), cancel):
            other = second.get(key)
            stock.add(row, other)
            if quantities[row["unit"]].available:
                quantities[row["unit"]].add(row, other)
        for key, row in _checked(second.items(), cancel):
            if key not in first:
                stock.add(None, row)
                if quantities[row["unit"]].available:
                    quantities[row["unit"]].add(None, row)
    sales_available = (
        bool(before.get("salesObserved", False))
        and bool(after.get("salesObserved", False))
        and not before.get("partial", False)
        and not after.get("partial", False)
    )
    sales_reason = _reason(before, after, base_period, target_period, sales=True)
    sales = {}
    before_branches, after_branches = {}, {}
    for unit in _checked(units, cancel):
        first = before.get("salesQuantity", {}).get(unit)
        second = after.get("salesQuantity", {}).get(unit)
        reason = sales_reason
        if sales_available and (first is None or second is None):
            reason = "Vendas da unidade " + unit + " não estão observadas nos dois meses."
        sales[unit] = _Comparison(
            first,
            second,
            sales_available and first is not None and second is not None,
            reason,
            "quantity",
            zero_missing=True,
        )
        before_branches[unit], after_branches[unit] = set(), set()
    if sales_available:
        first = _index(before.get("saleRows", ()), sales=True, cancel=cancel)
        second = (
            first
            if before is after
            else _index(after.get("saleRows", ()), sales=True, cancel=cancel)
        )
        for key, row in _checked(first.items(), cancel):
            unit = row["unit"]
            before_branches[unit].add(row["branch"])
            if sales[unit].available:
                sales[unit].add(row, second.get(key))
        for key, row in _checked(second.items(), cancel):
            unit = row["unit"]
            after_branches[unit].add(row["branch"])
            if key not in first and sales[unit].available:
                sales[unit].add(None, row)
    result = {
        "base": base_period,
        "target": target_period,
        "baseLabel": before.get("label", _label(base_period)),
        "targetLabel": after.get("label", _label(target_period)),
        "units": units,
        "stock": stock.result(cancel),
        "quantityByUnit": {
            unit: quantities[unit].result(cancel) for unit in _checked(units, cancel)
        },
        "salesByUnit": {unit: sales[unit].result(cancel) for unit in _checked(units, cancel)},
    }
    result["stock"].update(
        {
            "coverageNote": "Registros presentes apenas em um fechamento alteram a cobertura observada. Não comprovam entradas ou saídas físicas. A contribuição é a variação pareada mais registros apenas no alvo menos registros apenas na base.",
            "beforeScope": before.get("scope", ""),
            "afterScope": after.get("scope", ""),
        }
    )
    for unit in _checked(units, cancel):
        result["quantityByUnit"][unit]["coverageNote"] = result["stock"]["coverageNote"]
        comparable = sales[unit].available
        coverage_note = (
            "Filiais com registros de venda nesta unidade: base "
            + (", ".join(sorted(before_branches[unit])) or "nenhuma")
            + "; comparação "
            + (", ".join(sorted(after_branches[unit])) or "nenhuma")
            + ". Ausência de documento em mês observado contribui zero; não certifica cobertura por filial nem explica as causas da variação."
            if comparable
            else "A comparação de vendas exige dois meses completos observados. O recorte de vendas é informado para cada mês; dados indisponíveis não comprovam ausência de transações."
        )
        result["salesByUnit"][unit].update(
            {
                "coverageNote": coverage_note,
                "beforeBranches": tuple(sorted(before_branches[unit])) if comparable else None,
                "afterBranches": tuple(sorted(after_branches[unit])) if comparable else None,
                "beforeScope": before.get("salesScope", ""),
                "afterScope": after.get("salesScope", ""),
            }
        )
    checkpoint(cancel)
    return result
