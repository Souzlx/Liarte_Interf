"""Exact reconciliation of an independent stock reference and application output.

The reference adapter owns extraction and normalization. Expected indicators are
aggregated directly from its records, never calculated by running the application
analyzers over that reference. Only discrepancies are retained in the report.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
import json
import math
from threading import Event

from .inventory import (
    SCALE,
    Balance,
    Closing,
    InventoryData,
    Sale,
    StockSelection,
    _checked,
    analyze_inventory,
    month_end,
)
from .inventory_io import RECORD_LIMITS, validate_data
from .inventory_monthly import analyze_monthly_inventory
from .query import checkpoint

_COUNTERS = ("total", "passed", "different", "missing", "extra", "unknown")


@dataclass(frozen=True, slots=True)
class InventoryReference:
    as_of: date
    source_name: str
    source_hash: str
    balances: tuple[Balance, ...]
    closings: tuple[Closing, ...]
    sales: tuple[Sale, ...]
    counts: dict | None = None


def _identity(row, kind):
    result = row.product, row.branch
    if kind != "sales":
        result += (row.warehouse,)
    result += (row.unit,)
    if kind == "closings":
        result += (row.period,)
    elif kind == "sales":
        result += (row.day.isoformat(),)
    return result


def _indexed(rows, kind, cancel):
    indexed = {}
    for row in _checked(rows, cancel):
        key = _identity(row, kind)
        if key in indexed:
            raise ValueError("Há registros duplicados na conferência: " + kind + ".")
        indexed[key] = row
    return indexed


def _reference_valid(reference, cancel):
    if not isinstance(reference, InventoryReference):
        raise ValueError("Referência de estoque inválida.")
    if (
        type(reference.as_of) is not date
        or not isinstance(reference.source_name, str)
        or not reference.source_name.strip()
        or not isinstance(reference.source_hash, str)
        or len(reference.source_hash) != 64
        or any(char not in "0123456789abcdef" for char in reference.source_hash)
    ):
        raise ValueError("Identificação da referência de estoque inválida.")
    for kind, cls in (("balances", Balance), ("closings", Closing), ("sales", Sale)):
        rows = getattr(reference, kind)
        if not isinstance(rows, (tuple, list)) or len(rows) > RECORD_LIMITS[kind]:
            raise ValueError("Coleção da referência ultrapassa o limite de registros.")
        for row in _checked(rows, cancel):
            if type(row) is not cls:
                raise ValueError("Registro inválido na referência: " + kind + ".")
            for field in ("product", "branch", "unit") + (
                () if kind == "sales" else ("warehouse",)
            ):
                value = getattr(row, field)
                if not isinstance(value, str) or not value.strip():
                    raise ValueError("Chave inválida na referência de estoque.")
            for field in ("quantity", "cost"):
                value = getattr(row, field)
                if type(value) is not int or abs(value) > 10**23:
                    raise ValueError("A referência deve preservar quantidades e custos inteiros.")
            if kind == "closings":
                if not isinstance(row.period, str) or len(row.period) != 7:
                    raise ValueError("Período de fechamento inválido na referência.")
                try:
                    stamp = date.fromisoformat(row.period + "-01")
                except ValueError as exc:
                    raise ValueError("Período de fechamento inválido na referência.") from exc
                if stamp > reference.as_of:
                    raise ValueError("Fechamento da referência posterior à data da base.")
                for value in (row.turnover, row.days):
                    if value is not None and (
                        type(value) not in (int, float)
                        or not math.isfinite(value)
                        or abs(value) > 10**24
                    ):
                        raise ValueError("Indicador inválido na referência.")
            elif kind == "sales":
                if type(row.day) is not date or row.day > reference.as_of:
                    raise ValueError("Data de venda inválida na referência.")
                if row.had_positive is not None and type(row.had_positive) is not bool:
                    raise ValueError("Sinal de saída positiva inválido na referência.")
        _indexed(rows, kind, cancel)
    if reference.counts is not None and not isinstance(reference.counts, dict):
        raise ValueError("Contagens da referência inválidas.")
    try:
        json.dumps(reference.counts, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("Contagens da referência inválidas.") from exc


def _dimensions(key, kind):
    product, branch = key[:2]
    if kind == "sales":
        return dict(
            product=product, branch=branch, warehouse="", unit=key[2], day=key[3], period=key[3][:7]
        )
    return dict(
        product=product,
        branch=branch,
        warehouse=key[2],
        unit=key[3],
        day="",
        period=key[4] if kind == "closings" else "",
    )


class _Collector:
    def __init__(self, cancel):
        self.cancel = cancel
        self.checks = dict.fromkeys(_COUNTERS, 0)
        self.sections = {}
        self.differences = []
        self.totals = []

    def section(self, name, source_rows, app_rows):
        section = self.sections.setdefault(name, dict.fromkeys(_COUNTERS, 0))
        section["sourceRows"] = source_rows
        section["appRows"] = app_rows

    def check(
        self,
        section,
        dimensions,
        metric,
        source,
        app,
        *,
        scale=1,
        value_unit="",
        source_present=True,
        app_present=True,
        exact=True,
        total=False,
    ):
        if self.checks["total"] % 512 == 0:
            checkpoint(self.cancel)
        for value in (source, app):
            if value is not None and (
                type(value) not in (int, float, bool)
                or isinstance(value, float)
                and not math.isfinite(value)
            ):
                raise ValueError("Valor não numérico ou não finito na conferência: " + metric + ".")
        if not source_present:
            status = "extra"
        elif not app_present:
            status = "missing"
        elif source is None and app is None:
            status = "unknown"
        elif source is None or app is None:
            status = "different"
        elif source != app or (
            exact
            and type(source) is not type(app)
            or isinstance(source, bool) != isinstance(app, bool)
        ):
            status = "different"
        else:
            status = "passed"
        for counters in (self.checks, self.sections[section]):
            counters["total"] += 1
            counters[status] += 1
        failed = status not in ("passed", "unknown")
        if not failed and not total:
            return
        delta = (
            app - source
            if source_present
            and app_present
            and source is not None
            and app is not None
            and not isinstance(source, bool)
            and not isinstance(app, bool)
            else None
        )
        entry = {
            "section": section,
            "product": "",
            "branch": "",
            "warehouse": "",
            "unit": "",
            "day": "",
            "period": "",
            **dimensions,
            "metric": metric,
            "scale": scale,
            "valueUnit": value_unit,
            "sourceValue": source,
            "appValue": app,
            "difference": delta,
            "sourcePresent": source_present,
            "appPresent": app_present,
            "status": status,
        }
        if failed:
            self.differences.append(entry)
        if total:
            self.totals.append(dict(entry))


def _records(collector, section, expected, actual, kind, metrics):
    collector.section(section, len(expected), len(actual))
    for key in sorted(expected.keys() | actual.keys()):
        source, app = expected.get(key), actual.get(key)
        dimensions = _dimensions(key, kind)
        for metric, scale, value_unit, exact in metrics:
            collector.check(
                section,
                dimensions,
                metric,
                getattr(source, metric) if source is not None else None,
                getattr(app, metric) if app is not None else None,
                scale=scale,
                value_unit=dimensions["unit"] if value_unit == "unit" else value_unit,
                source_present=source is not None,
                app_present=app is not None,
                exact=exact,
            )


def _calendar(start, end):
    current = date.fromisoformat(start + "-01")
    last = date.fromisoformat(end + "-01")
    while current <= last:
        yield current.isoformat()[:7]
        if current == last:
            break
        current = date(current.year + current.month // 12, current.month % 12 + 1, 1)


def _source_metadata(value, *, counts=None):
    result = {
        "sourceName": value.source_name,
        "sourceHash": value.source_hash,
        "asOf": value.as_of.isoformat(),
        "recordCounts": {
            kind: len(getattr(value, kind)) for kind in ("balances", "closings", "sales")
        },
    }
    if counts is not None:
        result["tableCounts"] = json.loads(json.dumps(counts, allow_nan=False))
    return result


def reconcile_inventory(reference: InventoryReference, data: InventoryData, *, cancel=None) -> dict:
    """Compare complete facts and real current/monthly application indicators.

    Counts are comparisons of metric values, not row counts. ``unknown`` means
    both rows contain an unavailable value; it is distinct from a known match.
    A value present on only one side is always a discrepancy. Different source
    revisions or business dates produce ``not_comparable`` without a pass claim.
    """
    cancel = cancel if cancel is not None else Event()
    checkpoint(cancel)
    _reference_valid(reference, cancel)
    validate_data(data, cancel)
    source = _source_metadata(reference, counts=reference.counts or {})
    app = _source_metadata(data)
    compatibility = {
        "sameAsOf": reference.as_of == data.as_of,
        "sameSourceHash": reference.source_hash == data.source_hash,
    }
    dates = [row.period for row in _checked(reference.closings, cancel)]
    dates.extend(row.day.isoformat()[:7] for row in _checked(reference.sales, cancel))
    dates.extend(row.period for row in _checked(data.closings, cancel))
    dates.extend(row.day.isoformat()[:7] for row in _checked(data.sales, cancel))
    end = reference.as_of.isoformat()[:7]
    start = min(dates, default=end)
    periods = tuple(_calendar(start, end))
    context = {
        "scope": "complete",
        "start": start,
        "end": end,
        "monthCount": len(periods),
        "quantityScale": SCALE,
        "costScale": 100,
        "differencesOnly": True,
        "comparability": compatibility,
    }
    collector = _Collector(cancel)
    report = {
        "format": "liarte.inventory.reconciliation/1",
        "source": source,
        "app": app,
        "context": context,
        "comparable": all(compatibility.values()),
        "status": "not_comparable",
        "checks": collector.checks,
        "sections": collector.sections,
        "differences": (),
        "totals": (),
    }
    if not report["comparable"]:
        checkpoint(cancel)
        return report
    measures = (("quantity", SCALE, "unit", True), ("cost", 100, "R$", True))
    for kind in ("balances", "closings", "sales"):
        metrics = measures
        if kind == "closings":
            metrics += (("turnover", 1, "x/mês", False), ("days", 1, "dias", False))
        elif kind == "sales":
            metrics += (("had_positive", 1, "bool", True),)
        _records(
            collector,
            kind,
            _indexed(getattr(reference, kind), kind, cancel),
            _indexed(getattr(data, kind), kind, cancel),
            kind,
            metrics,
        )

    # Current balance indicators do not require a historical demand window.
    current = analyze_inventory(data, StockSelection(end, end), cancel=cancel)
    collector.section("current_indicators", len(reference.balances), len(current.rows))
    collector.check(
        "current_indicators",
        {},
        "cost",
        sum(row.cost for row in _checked(reference.balances, cancel)),
        current.total_cost,
        scale=100,
        value_unit="R$",
        total=True,
    )
    collector.check(
        "current_indicators",
        {},
        "position_count",
        len(reference.balances),
        len(current.rows),
        value_unit="posições",
        total=True,
    )
    current_source, current_app = defaultdict(int), defaultdict(int)
    for row in _checked(reference.balances, cancel):
        current_source[row.unit] += row.quantity
    for row in _checked(current.rows, cancel):
        current_app[row.balance.unit] += row.balance.quantity
    for unit in sorted(current_source.keys() | current_app.keys()):
        collector.check(
            "current_indicators",
            {"unit": unit},
            "quantity",
            current_source.get(unit),
            current_app.get(unit),
            scale=SCALE,
            value_unit=unit,
            source_present=unit in current_source,
            app_present=unit in current_app,
            total=True,
        )
    current_rows = _indexed(
        tuple(row.balance for row in _checked(current.rows, cancel)), "balances", cancel
    )
    _records(
        collector,
        "current_positions",
        _indexed(reference.balances, "balances", cancel),
        current_rows,
        "balances",
        measures,
    )

    units = {
        row.unit
        for kind in ("balances", "closings", "sales")
        for row in _checked(getattr(reference, kind), cancel)
    }
    by_period = defaultdict(list)
    for row in _checked(reference.closings, cancel):
        by_period[row.period].append(row)
    sale_periods = defaultdict(lambda: defaultdict(int))
    for row in _checked(reference.sales, cancel):
        sale_periods[row.day.isoformat()[:7]][row.product, row.branch, row.unit] += row.quantity
    sales_begin = min((row.day for row in _checked(reference.sales, cancel)), default=None)
    # The existing analysis bounds one selection to 20 years. Independent
    # batches cover a longer reference without dropping or relabeling history.
    for offset in range(0, len(periods), 240):
        checkpoint(cancel)
        window = periods[offset : offset + 240]
        actual_months = analyze_monthly_inventory(
            data, StockSelection(window[0], window[-1]), cancel=cancel
        )
        actual_index = {}
        for month in _checked(actual_months, cancel):
            period = month.get("period")
            if not isinstance(period, str) or period in actual_index:
                raise ValueError("Mês inválido ou duplicado nos indicadores do aplicativo.")
            actual_index[period] = month
        for period in sorted(set(window) | actual_index.keys()):
            _monthly(
                collector,
                period,
                by_period.get(period, ()),
                sale_periods.get(period, {}),
                units,
                sales_begin,
                reference.as_of,
                actual_index.get(period),
                period in window,
            )
    checkpoint(cancel)
    report["status"] = (
        "different"
        if any(collector.checks[key] for key in ("different", "missing", "extra"))
        else "equal"
    )
    report["differences"] = tuple(collector.differences)
    report["totals"] = tuple(collector.totals)
    return report


def _monthly(collector, period, rows, sales, units, sales_begin, as_of, actual, source_present):
    """Expected monthly values are aggregations of reference facts only."""
    first = date.fromisoformat(period + "-01")
    last = month_end(period)
    observed = bool(sales_begin is not None and first <= as_of and last >= sales_begin)
    expected_stock = {unit: None for unit in units}
    for row in _checked(rows, collector.cancel):
        expected_stock[row.unit] = (expected_stock[row.unit] or 0) + row.quantity
    expected_sales = {unit: 0 if observed else None for unit in units}
    if observed:
        for (_, _, unit), quantity in _checked(sales.items(), collector.cancel):
            expected_sales[unit] += quantity
    eligible = sorted(
        row.turnover
        for row in _checked(rows, collector.cancel)
        if row.quantity > 0 and row.turnover is not None and row.turnover >= 0
    )
    middle = len(eligible) // 2
    giro = (
        (eligible[middle] if len(eligible) % 2 else (eligible[middle - 1] + eligible[middle]) / 2)
        if eligible
        else None
    )
    expected = {
        "stockCost": sum(row.cost for row in _checked(rows, collector.cancel)) if rows else None,
        "salesObserved": observed,
        "partial": bool(observed and (first < sales_begin or last > as_of)),
        "stockPartial": bool(rows and last > as_of),
        "turnover": giro,
        "turnoverCount": len(eligible),
        "turnoverInvalidCount": sum(
            row.quantity > 0 and row.turnover is not None and row.turnover < 0
            for row in _checked(rows, collector.cancel)
        ),
        "productCount": len(
            {row.product for row in _checked(rows, collector.cancel) if row.quantity > 0}
        )
        if rows
        else None,
    }
    section = "monthly_totals"
    if section not in collector.sections:
        collector.section(section, 0, 0)
    collector.sections[section]["sourceRows"] += int(source_present)
    collector.sections[section]["appRows"] += int(actual is not None)
    for field, value in expected.items():
        collector.check(
            section,
            {"period": period},
            field,
            value,
            actual.get(field) if actual is not None else None,
            scale=100 if field == "stockCost" else 1,
            value_unit="R$"
            if field == "stockCost"
            else "x/mês"
            if field == "turnover"
            else "bool"
            if isinstance(value, bool)
            else "produtos"
            if field == "productCount"
            else "posições"
            if field.endswith("Count")
            else "",
            source_present=source_present,
            app_present=actual is not None and field in actual,
            exact=field != "turnover",
            total=field == "stockCost",
        )
    for field, expected_values in (
        ("stockQuantity", expected_stock),
        ("salesQuantity", expected_sales),
    ):
        values = actual.get(field, {}) if actual is not None else {}
        if not isinstance(values, dict):
            raise ValueError("Totais mensais por unidade inválidos no aplicativo.")
        for unit in sorted(expected_values.keys() | values.keys()):
            collector.check(
                section,
                {"period": period, "unit": unit},
                field,
                expected_values.get(unit),
                values.get(unit),
                scale=SCALE,
                value_unit=unit,
                source_present=source_present and unit in expected_values,
                app_present=actual is not None and unit in values,
                total=True,
            )
    _monthly_positions(collector, period, rows, actual)
    _monthly_sales(collector, period, sales if observed and source_present else {}, actual)


def _monthly_positions(collector, period, rows, actual):
    name = "monthly_positions"
    expected = {(row.product, row.branch, row.warehouse, row.unit): row for row in rows}
    actual_rows = actual.get("stockRows", ()) if actual is not None else ()
    index = _output_rows(actual_rows, ("code", "branch", "warehouse", "unit"), collector.cancel)
    if name not in collector.sections:
        collector.section(name, 0, 0)
    collector.sections[name]["sourceRows"] += len(expected)
    collector.sections[name]["appRows"] += len(index)
    for key in sorted(expected.keys() | index.keys()):
        source, app = expected.get(key), index.get(key)
        dimensions = dict(
            product=key[0], branch=key[1], warehouse=key[2], unit=key[3], period=period
        )
        for field, scale, value_unit, exact in (
            ("quantity", SCALE, key[3], True),
            ("cost", 100, "R$", True),
            ("turnover", 1, "x/mês", False),
            ("days", 1, "dias", False),
        ):
            collector.check(
                name,
                dimensions,
                field,
                getattr(source, field) if source is not None else None,
                app.get(field) if app is not None else None,
                scale=scale,
                value_unit=value_unit,
                source_present=source is not None,
                app_present=app is not None and field in app,
                exact=exact,
            )


def _monthly_sales(collector, period, expected, actual):
    name = "monthly_sales"
    actual_rows = actual.get("saleRows", ()) if actual is not None else ()
    index = _output_rows(actual_rows, ("code", "branch", "unit"), collector.cancel)
    if name not in collector.sections:
        collector.section(name, 0, 0)
    collector.sections[name]["sourceRows"] += len(expected)
    collector.sections[name]["appRows"] += len(index)
    for key in sorted(expected.keys() | index.keys()):
        app = index.get(key)
        collector.check(
            name,
            dict(product=key[0], branch=key[1], unit=key[2], period=period),
            "quantity",
            expected.get(key),
            app.get("quantity") if app is not None else None,
            scale=SCALE,
            value_unit=key[2],
            source_present=key in expected,
            app_present=app is not None and "quantity" in app,
        )


def _output_rows(rows, fields, cancel):
    if not isinstance(rows, (list, tuple)):
        raise ValueError("Linhas inválidas nos indicadores do aplicativo.")
    result = {}
    for row in _checked(rows, cancel):
        if not isinstance(row, dict) or any(
            not isinstance(row.get(field), str) or not row[field] for field in fields
        ):
            raise ValueError("Chaves inválidas nos indicadores do aplicativo.")
        key = tuple(row[field] for field in fields)
        if key in result:
            raise ValueError("Chaves duplicadas nos indicadores do aplicativo.")
        result[key] = row
    return result
