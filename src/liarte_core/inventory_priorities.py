"""Review priorities over an accepted monthly product-performance report.

Quantities keep the original millionth scale and costs remain integer cents.
Every rule refers to the report's closing and complete sales windows. Negative
positions disable coverage; they do not erase an observed aggregate sales drop
or zero net sales. Those facts retain a warning about the negative positions.
Capital is an ordered view, without a threshold that would imply excess stock.
"""

from __future__ import annotations

import math
from threading import Event

from .inventory import SCALE, _checked, folded
from .query import checkpoint


_CATEGORIES = (
    ("review", "Critérios combinados"),
    ("coverage", "Cobertura < limite"),
    ("decline", "Variação de vendas < 0"),
    ("idle", "Saldo > 0 · vendas líquidas = 0"),
    ("capital", "Estoque a custo"),
)
_LABELS = dict(_CATEGORIES)
_METADATA = (
    "window", "units", "selectionStart", "selectionEnd", "selectionKey",
    "basePeriods", "targetPeriods", "baseLabel", "targetLabel", "targetPeriod",
    "baseDays", "targetDays", "excludedPeriods", "scope", "notice", "reason",
)


def _integer(row, field):
    value = row.get(field)
    if value is not None and type(value) is not int:
        raise ValueError("Quantidades e custos das prioridades devem preservar a escala inteira.")
    return value


def _condition(metric, label, value, operator, reference, scale, unit, periods):
    """Keep the exact facts behind a rule separate from its presentation."""
    return {
        "metric": metric, "label": label, "value": value,
        "operator": operator, "reference": reference, "scale": scale,
        "unit": unit, "periods": tuple(periods),
    }


def _criterion(key, *conditions):
    return {"key": key, "label": _LABELS[key], "conditions": tuple(conditions)}


def analyze_product_priorities(
    report: dict, *, coverage_days: int = 30, cancel: Event | None = None
) -> dict:
    """Classify complete product/unit facts without loading or recomputing data.

    ``review`` is the deduplicated union of coverage, decline and idle. Rows may
    belong to several categories; their counts must not be added. ``capital``
    includes positive closing stock at a positive aggregate cost and does not
    assert that this capital is idle. Known zero net sales can include returns.

    Comparison availability only gates decline. A complete recent window can
    still support coverage or zero net sales when the earlier window is absent.
    Missing, negative and nonfinite coverage never become a zero-day estimate.
    The input report and its rows are not modified.
    """
    if type(coverage_days) is not int or not 1 <= coverage_days <= 3650:
        raise ValueError("O limite de cobertura deve ser um inteiro entre 1 e 3650 dias.")
    if not isinstance(report, dict) or not isinstance(report.get("rows", ()), (tuple, list)):
        raise ValueError("O relatório de desempenho das prioridades é inválido.")
    cancel = cancel if cancel is not None else Event()
    checkpoint(cancel)
    counts = dict.fromkeys((key for key, _ in _CATEGORIES), 0)
    rows, seen = [], set()
    closing_periods = (report["targetPeriod"],) if report.get("targetPeriod") else ()
    recent_periods = tuple(report.get("targetPeriods", ()))
    previous_periods = tuple(report.get("basePeriods", ()))
    comparable = report.get("available") is True
    source_count = 0
    for original in _checked(report.get("rows", ()), cancel):
        if not isinstance(original, dict):
            raise ValueError("Há um produto inválido no relatório das prioridades.")
        code, unit = original.get("code"), original.get("unit")
        if not isinstance(code, str) or not code or not isinstance(unit, str):
            raise ValueError("O produto e a unidade precisam identificar cada prioridade.")
        identity = code, unit
        if identity in seen:
            raise ValueError("Há mais de um registro para o mesmo produto e unidade.")
        seen.add(identity)
        source_count += 1
        quantity = _integer(original, "stockQuantity")
        cost = _integer(original, "stockCost")
        sold = _integer(original, "sold")
        before = _integer(original, "previous")
        change = _integer(original, "change")
        negative_positions = original.get("negativeStockPositionCount", 0)
        if type(negative_positions) is not int or negative_positions < 0:
            raise ValueError("A contagem de posições negativas é inválida.")
        coverage = original.get("coverage")
        criteria = []
        if (
            quantity is not None and quantity >= 0 and negative_positions == 0
            and sold is not None and sold > 0
            and type(coverage) in (int, float) and math.isfinite(coverage)
            and 0 <= coverage < coverage_days
        ):
            criteria.append(_criterion(
                "coverage",
                _condition("coverage", "Cobertura", coverage, "<", coverage_days,
                           1, "dias", recent_periods),
                _condition("sold", "Vendas líquidas", sold, ">", 0,
                           SCALE, unit, recent_periods),
                _condition("stockQuantity", "Saldo", quantity, ">=", 0,
                           SCALE, unit, closing_periods),
                _condition("negativeStockPositionCount", "Posições negativas",
                           negative_positions, "=", 0, 1, "posições", closing_periods),
            ))
        if (
            comparable and quantity is not None and quantity > 0
            and before is not None and before > 0 and sold is not None and sold >= 0
            and change is not None and change < 0 and change == sold - before
            and original.get("status") in ("down", "no_positive")
        ):
            criteria.append(_criterion(
                "decline",
                _condition("change", "Δ vendas líquidas", change, "<", 0,
                           SCALE, unit, previous_periods + recent_periods),
                _condition("previous", "Vendas anteriores", before, ">", 0,
                           SCALE, unit, previous_periods),
                _condition("sold", "Vendas recentes", sold, ">=", 0,
                           SCALE, unit, recent_periods),
                _condition("stockQuantity", "Saldo", quantity, ">", 0,
                           SCALE, unit, closing_periods),
            ))
        if quantity is not None and quantity > 0 and sold == 0:
            criteria.append(_criterion(
                "idle",
                _condition("sold", "Vendas líquidas", sold, "=", 0,
                           SCALE, unit, recent_periods),
                _condition("stockQuantity", "Saldo", quantity, ">", 0,
                           SCALE, unit, closing_periods),
            ))
        if quantity is not None and quantity > 0 and cost is not None and cost > 0:
            criteria.append(_criterion(
                "capital",
                _condition("stockCost", "Estoque a custo", cost, ">", 0,
                           100, "R$", closing_periods),
                _condition("stockQuantity", "Saldo", quantity, ">", 0,
                           SCALE, unit, closing_periods),
            ))
        if not criteria:
            continue
        categories = tuple(criterion["key"] for criterion in criteria)
        for key in categories:
            counts[key] += 1
        if any(key != "capital" for key in categories):
            counts["review"] += 1
        notices = []
        if negative_positions:
            notices.append(
                "Há saldo negativo em " + str(negative_positions)
                + " posição(ões). A cobertura fica indisponível; saldo e custo "
                "apresentados são os agregados do fechamento."
            )
        if cost is not None and cost < 0:
            notices.append("Custo agregado negativo; fora do critério Estoque a custo > 0.")
        rows.append({
            **original,
            "categories": categories,
            "criteria": tuple(criteria),
            "primaryCategory": categories[0],
            "primaryTitle": criteria[0]["label"],
            "dataNotice": " ".join(notices),
        })

    sorted_count = 0

    def order(row):
        nonlocal sorted_count
        if sorted_count % 512 == 0:
            checkpoint(cancel)
        sorted_count += 1
        cost = row.get("stockCost")
        known = cost is not None
        return (
            not known, -(cost if known else 0),
            folded(str(row.get("name") or row["code"])), row["code"], row["unit"],
        )

    ordered = tuple(sorted(rows, key=order))
    checkpoint(cancel)
    result = {key: report[key] for key in _METADATA if key in report}
    result.update(
        rows=ordered,
        categories=tuple({"key": key, "label": label, "count": counts[key]}
                         for key, label in _CATEGORIES),
        counts=counts,
        coverageDays=coverage_days,
        coveragePolicy="Limite configurado em Ajustar alertas",
        comparisonAvailable=comparable,
        sourceCount=source_count,
        referenceNotice="Saldo e capital se referem ao fechamento indicado, não ao saldo atual.",
    )
    return result
