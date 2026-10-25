"""Configurable stock review lists derived only from an existing analysis.

Recency refers to the source date and does not measure physical stock age.
Coverage belongs to the whole product/branch/unit, never to an individual
warehouse. Quantities and capital below describe the selected current positions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import math
from threading import Event

from .inventory import InventoryData, StockAnalysis, StockSelection, _checked
from .query import checkpoint


@dataclass(frozen=True, slots=True)
class AlertPolicy:
    stale_days: int = 90
    coverage_days: int = 30

    def __post_init__(self):
        for value in (self.stale_days, self.coverage_days):
            if type(value) is not int or not 1 <= value <= 3650:
                raise ValueError("Os limites dos alertas devem ser dias inteiros entre 1 e 3650.")


@dataclass(frozen=True, slots=True)
class StockAlert:
    code: str
    name: str
    branch: str
    unit: str
    quantity: int
    cost: int
    last_sale: date | None
    days_since_sale: int | None
    coverage: float | None


@dataclass(frozen=True, slots=True)
class StockAlerts:
    policy: AlertPolicy
    as_of: date
    start: str
    end: str
    stale: tuple[StockAlert, ...]
    low_coverage: tuple[StockAlert, ...]
    no_sale: tuple[StockAlert, ...]
    coverage_available: bool
    coverage_unavailable_count: int
    scope_count: int


def _ordered(values, key, cancel):
    """Check both collection and sort-key preparation before returning a list."""
    count = 0

    def checked_key(item):
        nonlocal count
        if count % 512 == 0:
            checkpoint(cancel)
        count += 1
        return key(item)

    result = tuple(sorted(_checked(values, cancel), key=checked_key))
    checkpoint(cancel)
    return result


def analyze_stock_alerts(
    data: InventoryData,
    selected: StockSelection,
    analysis: StockAnalysis,
    policy: AlertPolicy = AlertPolicy(),
    *,
    cancel: Event | None = None,
) -> StockAlerts:
    """Return complete, deduplicated lists for the current selected positions.

    A key is product/branch/unit, even if several selected warehouses contain
    it. Capital is the positive part of the sum of its selected position costs.
    The two thresholds are strict: elapsed > stale_days, coverage < coverage_days.
    No observed positive sale is reported separately, without an inferred age.

    No facts are read again: demand/coverage are reused from StockRow. With a
    warehouse filter, coverage is unavailable. Negative selected grouped stock
    and unknown/invalid coverage cannot produce a low-coverage alert. Zero
    stock can, provided the existing analysis has positive demand and coverage.
    """
    if not isinstance(policy, AlertPolicy):
        raise ValueError("Política de alertas inválida.")
    cancel = cancel if cancel is not None else Event()
    checkpoint(cancel)
    groups = {}
    for row in _checked(analysis.rows, cancel):
        balance = row.balance
        key = balance.product, balance.branch, balance.unit
        if key not in groups:
            groups[key] = [row, balance.quantity, balance.cost]
        else:
            group = groups[key]
            group[1] += balance.quantity
            group[2] += balance.cost

    coverage_available = not bool(selected.warehouse)
    unavailable = 0
    stale, low, no_sale = [], [], []
    for (code, branch, unit), (row, quantity, cost) in _checked(groups.items(), cancel):
        last_sale = row.last_sale
        elapsed = (data.as_of - last_sale).days if last_sale is not None else None
        coverage = row.coverage
        if (
            not coverage_available
            or quantity < 0
            or coverage is None
            or not math.isfinite(coverage)
            or coverage < 0
        ):
            coverage = None
            unavailable += 1
        item = StockAlert(
            code, row.name, branch, unit, quantity, max(0, cost),
            last_sale, elapsed, coverage,
        )
        if quantity > 0:
            if last_sale is None:
                no_sale.append(item)
            elif elapsed > policy.stale_days:
                stale.append(item)
        if coverage is not None and coverage < policy.coverage_days:
            low.append(item)

    def identity(item):
        return item.code, item.branch, item.unit
    return StockAlerts(
        policy=policy,
        as_of=data.as_of,
        start=selected.start,
        end=selected.end,
        stale=_ordered(
            stale, lambda item: (-item.days_since_sale, -item.cost, *identity(item)), cancel
        ),
        low_coverage=_ordered(
            low, lambda item: (item.coverage, -item.cost, *identity(item)), cancel
        ),
        no_sale=_ordered(no_sale, lambda item: (-item.cost, *identity(item)), cancel),
        coverage_available=coverage_available,
        coverage_unavailable_count=unavailable,
        scope_count=len(groups),
    )
