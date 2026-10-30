"""Review priorities over an accepted monthly product-performance report.

Quantities keep the original millionth scale and costs remain integer cents.
Every rule refers to the report's closing and complete sales windows. Negative
positions disable coverage; they do not erase an observed aggregate sales drop
or zero net sales. Those facts retain a warning about the negative positions.
Capital is an ordered view, without a threshold that would imply excess stock.
"""

from __future__ import annotations

from decimal import Decimal
import math
from threading import Event

from .inventory import SCALE, _checked, folded, money, number
from .query import checkpoint


_CATEGORIES = (
    ("review", "Situações para revisar"),
    ("coverage", "Revisar reposição"),
    ("decline", "Vendas em queda"),
    ("idle", "Saldo sem venda líquida"),
    ("capital", "Maior capital"),
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


def _quantity(value, unit):
    return number(Decimal(value) / SCALE, 3) + (" " + unit if unit else "")


def _period_label(period):
    return period[5:] + "/" + period[:4] if len(period) == 7 else period


def _reason(key, fact, next_step):
    return {"key": key, "title": _LABELS[key], "fact": fact, "nextStep": next_step}


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
    reference = _period_label(str(report.get("targetPeriod", "")))
    recent = str(report.get("targetLabel", "")) or reference
    previous = str(report.get("baseLabel", "")) or "janela anterior"
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
        reasons = []
        if (
            quantity is not None and quantity >= 0 and negative_positions == 0
            and sold is not None and sold > 0
            and type(coverage) in (int, float) and math.isfinite(coverage)
            and 0 <= coverage < coverage_days
        ):
            reasons.append(_reason(
                "coverage",
                "Cobertura estimada de " + number(coverage, 1) + " dias no fechamento de "
                + reference + ", abaixo do limite de " + str(coverage_days)
                + " dias, pelo ritmo líquido de " + recent + ".",
                "Confira prazo de reposição, pedidos em aberto e consumo interno. "
                "A estimativa não confirma ruptura nem determina uma compra.",
            ))
        if (
            comparable and quantity is not None and quantity > 0
            and before is not None and before > 0 and sold is not None and sold >= 0
            and change is not None and change < 0 and change == sold - before
            and original.get("status") in ("down", "no_positive")
        ):
            reasons.append(_reason(
                "decline",
                "Quantidade líquida de " + _quantity(sold, unit) + " em " + recent
                + ", ante " + _quantity(before, unit) + " em " + previous
                + "; saldo no fechamento de " + reference + ": "
                + _quantity(quantity, unit) + ".",
                "Confira demanda, devoluções e a finalidade desse saldo. "
                "A queda observada não identifica sua causa.",
            ))
        if quantity is not None and quantity > 0 and sold == 0:
            reasons.append(_reason(
                "idle",
                "Saldo de " + _quantity(quantity, unit) + " no fechamento de " + reference
                + " e quantidade líquida registrada igual a zero em " + recent
                + ". Saídas podem ter sido compensadas por devoluções.",
                "Confira as transações e o uso interno antes de avaliar esse saldo. "
                "Zero líquido não comprova ausência de vendas, obsolescência ou idade de lote.",
            ))
        if quantity is not None and quantity > 0 and cost is not None and cost > 0:
            reasons.append(_reason(
                "capital",
                "Estoque a custo de " + money(cost) + " no fechamento de " + reference
                + ", dentro do recorte selecionado.",
                "Avalie esse capital junto com demanda, giro e finalidade do produto. "
                "A ordenação por valor não define excesso ou capital parado.",
            ))
        if not reasons:
            continue
        categories = tuple(reason["key"] for reason in reasons)
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
            notices.append("Custo agregado negativo preservado para conferência; fora de Maior capital.")
        rows.append({
            **original,
            "categories": categories,
            "reasons": tuple(reasons),
            "primaryCategory": categories[0],
            "primaryTitle": reasons[0]["title"],
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
        comparisonAvailable=comparable,
        sourceCount=source_count,
        referenceNotice="Saldo e capital se referem ao fechamento indicado, não ao saldo atual.",
    )
    return result
