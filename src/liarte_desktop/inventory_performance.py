"""Product investigation over an immutable monthly cache, outside the GUI thread."""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from decimal import Decimal
from threading import Event

from PySide6.QtCore import QObject, Property, QThread, Signal, Slot

from liarte_core.inventory import SCALE, folded, money, number
from liarte_core.inventory_performance import (
    analyze_product_performance,
    product_performance_detail,
)
from liarte_core.query import Cancelled, checkpoint

LOGGER = logging.getLogger("liarte.desktop")
_SHUTTING_DOWN = set()
PAGE_SIZE = 10
_METRICS = {
    "turnover": "Giro mensal da fonte · mediana",
    "stockCost": "Estoque a custo no fechamento",
    "stockQuantity": "Saldo no fechamento",
    "coverage": "Cobertura estimada",
    "name": "Produto",
}
_METRIC_ORDERS = {
    f"metric:{field}:{direction}": (field, direction == "desc")
    for field in _METRICS for direction in ("asc", "desc")
}
_SORTS = {"most", "least", "decline", "turnover", "all"} | _METRIC_ORDERS.keys()
_WINDOWS = (1, 3, 6)
_STATUS = {
    "insufficient": "Histórico insuficiente",
    "negative": "Saldo líquido negativo · confira devoluções",
    "no_positive": "Quantidade líquida zero",
    "resumed": "Sem quantidade líquida positiva na janela anterior",
    "up": "Quantidade líquida em alta",
    "down": "Quantidade líquida em queda",
    "stable": "Quantidade líquida estável",
}


def _quantity(value, unit):
    return number(Decimal(value) / SCALE, 3) + " " + unit if value is not None else "—"


def _evolution(row):
    change = row.get("change")
    if change is None:
        return "Sem comparação entre janelas completas"
    prefix = "+" if change > 0 else ""
    text = prefix + _quantity(change, row["unit"])
    percentage = row.get("percentage")
    if percentage is not None:
        text += " · " + ("+" if percentage > 0 else "") + number(percentage, 1) + "%"
    return text


def _metric_value(row, field):
    value = row.get(field)
    if field == "name":
        return folded(str(value or "")) if value else None
    if value is None or not isinstance(value, int) and not math.isfinite(value):
        return None
    if field in {"turnover", "coverage"} and value < 0:
        return None
    return value


def _present_row(row, field=None):
    giro = row.get("turnover")
    result = {
        "code": row["code"],
        "name": row["name"],
        "unit": row["unit"],
        "sold": _quantity(row.get("sold"), row["unit"]),
        "evolution": _evolution(row),
        "turnover": number(giro, 2) + " x/mês" if giro is not None else "Sem giro elegível",
        "status": _STATUS.get(row.get("status"), "Histórico insuficiente"),
        "stock": "Estoque no fechamento: " + _quantity(row.get("stockQuantity"), row["unit"])
        if row.get("stockQuantity") is not None else "Sem fechamento",
    }
    if field and field != "name":
        value = _metric_value(row, field)
        display = (
            "Sem giro elegível" if field == "turnover" else "Indisponível"
        ) if value is None else (
            money(value) if field == "stockCost" else
            _quantity(value, row["unit"]) if field == "stockQuantity" else
            number(value, 2) + " x/mês" if field == "turnover" else
            number(value, 1) + " dias"
        )
        result.update(sortField=field, sortLabel=_METRICS[field], sortValue=display)
    return result


def _list_rows(report, unit, order, query, cancel):
    """Filter compact summaries only; negative net sales never rank as low demand."""
    needle = folded(query.strip())
    rows = []
    lookup = {}
    for index, row in enumerate(report.get("rows", ())):
        if index % 256 == 0:
            checkpoint(cancel)
        lookup[(row["code"], row["unit"])] = row
        if row["unit"] != unit or needle and needle not in folded(row["code"] + " " + row["name"]):
            continue
        sold, previous = row.get("sold"), row.get("previous")
        if order == "most" and (sold is None or sold <= 0):
            continue
        if order == "least" and (
            sold is None or sold < 0 or row.get("stockQuantity") is None
            or row["stockQuantity"] <= 0
        ):
            continue
        if order == "decline" and (
            row.get("change") is None or row["change"] >= 0
            or sold is None or sold < 0 or previous is None or previous < 0
        ):
            continue
        if order == "turnover" and row.get("turnover") is None:
            continue
        rows.append(row)
    metric = _METRIC_ORDERS.get(order)
    if metric:
        field, descending = metric
        # Stable identity ties and absent/ineligible values stay at the end in
        # either direction. Sort every matching summary before slicing a page.
        rows.sort(key=lambda row: (row["code"], row["unit"], row["name"]))
        known = [row for row in rows if _metric_value(row, field) is not None]
        missing = [row for row in rows if _metric_value(row, field) is None]
        known.sort(key=lambda row: _metric_value(row, field), reverse=descending)
        rows = known + missing
    elif order == "all":
        rows.sort(key=lambda row: (row["code"], row["name"]))
    else:
        field = {"most": "sold", "least": "sold", "decline": "change", "turnover": "turnover"}[order]
        rows.sort(key=lambda row: (
            -row[field] if order == "most" else row[field], row["code"], row["name"]
        ))
    checkpoint(cancel)
    return tuple(rows), lookup


def _summary(report, rows, page, cancel, order=""):
    page = max(1, min(page, max(1, (len(rows) + PAGE_SIZE - 1) // PAGE_SIZE)))
    prepared = []
    for row in rows[(page - 1) * PAGE_SIZE:page * PAGE_SIZE]:
        checkpoint(cancel)
        metric = _METRIC_ORDERS.get(order)
        prepared.append(_present_row(row, metric[0] if metric else None))
    reason = report.get("reason", "").strip()
    reason_parts = set(re.split(r"(?<=[.!?])\s+", reason))
    notice = " ".join(
        part for part in re.split(r"(?<=[.!?])\s+", report.get("notice", "").strip())
        if part and part not in reason_parts
    )
    metric = _METRIC_ORDERS.get(order)
    order_label = ""
    if metric:
        field, descending = metric
        direction = ("Z–A" if descending else "A–Z") if field == "name" else (
            "Maior primeiro" if descending else "Menor primeiro"
        )
        order_label = _METRICS[field] + " · " + direction
        if field != "name":
            order_label += " · Valores ausentes ou inelegíveis ao final."
    elif order == "all":
        order_label = "Todos os produtos · Código crescente"
    return {
        "scope": report.get("scope", ""),
        "periodLabel": report.get("targetLabel", ""),
        "comparisonLabel": report.get("targetLabel", "") + " vs. " + report.get("baseLabel", ""),
        "notice": notice,
        "reason": reason,
        "orderLabel": order_label,
        "rows": prepared,
    }, page


def _present_detail(raw, report, cancel):
    row = raw.get("row")
    if row is None:
        return {}
    unit = row["unit"]
    giro, coverage = row.get("turnover"), row.get("coverage")
    target_period = report.get("targetPeriod", "")
    target_label = target_period[5:] + "/" + target_period[:4] if target_period else ""
    percentage = row.get("percentage")
    evolution_value = (
        ("+" if percentage > 0 else "") + number(percentage, 1) + "%"
        if percentage is not None else _quantity(row.get("change"), unit)
    )
    evolution_note = _STATUS.get(row.get("status"), "Histórico insuficiente")
    if row.get("change") is not None:
        evolution_note = (
            ("+" if row["change"] > 0 else "") + _quantity(row["change"], unit)
            + " vs. " + report.get("baseLabel", "") + " · " + evolution_note
        )
    series = {}
    for key, field, title, symbol, note in (
        ("sales", "sales", "Vendas líquidas mensais", unit,
         "Quantidade líquida da filial. Meses parciais identificados; lacunas não representam zero."),
        ("quantity", "quantity", "Quantidade no fechamento", unit,
         "Fechamentos observados no recorte; ausência de registro não representa saldo zero."),
        ("turnover", "turnover", "Giro da fonte · mediana", "x/mês",
         "Mediana mensal das posições elegíveis. Não é giro consolidado nem idade do estoque."),
    ):
        points = []
        for point in raw.get("series", ()):
            checkpoint(cancel)
            value = point.get(field)
            partial = point.get("salesPartial", point.get("partial", False)) if key == "sales" else point.get("stockPartial", False)
            display = (
                number(value, 2) + " x/mês" if key == "turnover" and value is not None
                else _quantity(value, unit) if value is not None else "Sem dados"
            )
            points.append({
                "period": point["period"],
                "label": point["label"] + (" (parcial)" if partial else ""),
                "value": float(value) / SCALE if key != "turnover" and value is not None else value,
                "display": display,
            })
        series[key] = {"title": title, "unit": symbol, "points": points, "note": note}
    return {
        "code": row["code"], "name": row["name"], "unit": unit,
        "scope": report.get("scope", ""),
        "metrics": [
            {"label": "Vendas líquidas", "value": _quantity(row.get("sold"), unit),
             "detail": report.get("targetLabel", "")},
            {"label": "Evolução entre janelas", "value": evolution_value,
             "detail": evolution_note},
            {"label": "Cobertura estimada", "value": number(coverage, 1) + " dias" if coverage is not None else "—",
             "detail": (
                 target_label + " · ao ritmo de "
                 + str(report.get("targetDays", "")) + " dias registrados. Não é idade do lote."
                 if coverage is not None else row.get("coverageReason") or "Indisponível neste recorte."
             )},
            {"label": "Giro da fonte · mediana", "value": number(giro, 2) + " x/mês" if giro is not None else "—",
             "detail": str(row.get("turnoverCount", 0)) + " posições válidas · " + target_label},
        ],
        "seriesKinds": [
            {"value": "sales", "label": "Vendas"},
            {"value": "quantity", "label": "Quantidade no fechamento"},
            {"value": "turnover", "label": "Giro da fonte"},
        ],
        "series": series,
        "evidence": list(raw.get("evidence", ())),
        "hypotheses": list(raw.get("hypotheses", ())),
        "limitations": list(raw.get("limitations", ())),
    }


@dataclass(frozen=True, slots=True)
class _Result:
    task: str
    options: tuple
    report: dict
    units: tuple
    rows: tuple = ()
    lookup: dict | None = None
    summary: dict | None = None
    page: int = 1
    detail: dict | None = None
    raw_detail: dict | None = None


class _Worker(QObject):
    done = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, action, cancel):
        super().__init__()
        self._action, self._cancel = action, cancel

    @Slot()
    def run(self):
        try:
            result = self._action(self._cancel)
            checkpoint(self._cancel)
            self.done.emit(result)
        except Cancelled:
            pass
        except (ValueError, OSError):
            LOGGER.exception("Falha ao analisar desempenho dos produtos")
            self.failed.emit("Não foi possível concluir a análise. Confira o período e tente novamente.")
        except Exception:
            LOGGER.exception("Falha inesperada ao analisar desempenho dos produtos")
            self.failed.emit("Não foi possível concluir a análise. Os resultados anteriores foram mantidos.")
        finally:
            self.finished.emit()


class InventoryPerformanceController(QObject):
    """Own one cooperative job and publish only a page or a selected product."""

    changed = Signal()
    shutdownFinished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._months = None
        self._selected = None
        self._source_generation = 0
        self._generation = 0
        self._running_generation = 0
        self._thread = self._worker = None
        self._cancel = Event()
        self._pending = False
        self._requested = False
        self._closed = False
        self._shutdown_complete = False
        self._task = ""
        self._unit = ""
        self._window = 3
        self._sort = "most"
        self._query = ""
        self._units = ()
        self._page = 1
        self._applied_page = 1
        self._rows = ()
        self._lookup = {}
        self._summary = {}
        self._detail = {}
        self._raw_detail = None
        self._cache = {}
        self._report = None
        self._accepted_source = -1
        self._applied = None
        self._error = ""

    def _options(self):
        return self._unit, self._window, self._sort, self._query

    @Property("QVariantMap", notify=changed)
    def state(self):
        return {
            "available": bool(self._months) and not self._closed,
            "busy": self._thread is not None or self._pending,
            "current": self._is_current(),
            "error": self._error,
            "units": [{"value": unit, "label": unit} for unit in self._units],
            "unit": self._unit,
            "windows": [{"value": value, "label": str(value) + (" mês" if value == 1 else " meses")} for value in _WINDOWS],
            "window": self._window,
            "sort": self._sort,
            "query": self._query,
            "page": self._page,
            "pages": max(1, (len(self._rows) + PAGE_SIZE - 1) // PAGE_SIZE),
            "count": len(self._rows),
        }

    def _is_current(self):
        return (
            not self._closed and bool(self._months) and self._thread is None
            and not self._pending and self._report is not None
            and self._accepted_source == self._source_generation
            and self._applied == self._options()
        )

    @Property("QVariantMap", notify=changed)
    def summary(self):
        return self._summary

    @Property("QVariantMap", notify=changed)
    def detail(self):
        return self._detail

    @property
    def report(self):
        """Complete accepted summaries for a worker export, never a QML payload."""
        return self._report if self._is_current() else None

    def export_snapshot(self):
        """Capture accepted immutable references before starting an Excel worker."""
        if not self._is_current():
            return None, None
        return self._report, self._raw_detail

    def set_source(self, months, selected):
        if self._closed or months is self._months and selected == self._selected:
            return
        self._months, self._selected = months, selected
        self._source_generation += 1
        self._generation += 1
        self._cancel.set()
        self._cache = {}
        self._report = None
        self._rows = ()
        self._lookup = {}
        self._summary = {}
        self._detail = {}
        self._raw_detail = None
        self._units = ()
        self._page = 1
        self._error = ""
        self._pending = self._requested and bool(months)
        self.changed.emit()
        if self._pending and self._thread is None:
            self._schedule()

    @Slot()
    def refresh(self):
        if self._closed:
            return
        self._requested = True
        if not self._months or self._is_current() or self._thread is not None or self._pending:
            return
        self._request()

    @Slot(str, int, str, str)
    def configure(self, unit, window, order, query):
        if self._closed or not self._months:
            return
        if (
            window not in _WINDOWS or order not in _SORTS or len(query) > 200
            or self._units and unit and unit not in self._units
        ):
            self._error = "Escolha uma janela, ordenação e busca válidas (até 200 caracteres)."
            self.changed.emit()
            return
        options = unit, window, order, query.strip()
        if options == self._options() and (self._is_current() or self._thread is not None or self._pending):
            return
        self._unit, self._window, self._sort, self._query = options
        self._requested = True
        self._page = 1
        self._request()

    def _request(self):
        self._generation += 1
        self._cancel.set()
        self._pending = True
        self._error = ""
        self.changed.emit()
        if self._thread is None:
            self._schedule()

    def _schedule(self):
        if self._closed or not self._months or self._thread is not None:
            return
        self._pending = False
        months, selected = self._months, self._selected
        unit, window, order, query = self._options()
        report = self._cache.get(window)
        requested_page = self._page

        def action(cancel):
            accepted = report
            if accepted is None:
                accepted = analyze_product_performance(months, selected, window=window, cancel=cancel)
            units = tuple(accepted.get("units", ()))
            focused = unit if unit in units else selected.unit if selected.unit in units else units[0] if units else ""
            rows, lookup = _list_rows(accepted, focused, order, query, cancel)
            summary, page = _summary(accepted, rows, requested_page, cancel, order)
            return _Result("list", (focused, window, order, query), accepted, units, rows, lookup, summary, page)

        self._start(action, "list")

    def _start(self, action, task):
        self._cancel = Event()
        self._running_generation = self._generation
        self._task = task
        self._thread = QThread(self)
        self._worker = _Worker(action, self._cancel)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.done.connect(self._accept)
        self._worker.failed.connect(self._fail)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._finished)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()
        self.changed.emit()

    @Slot(object)
    def _accept(self, result):
        if self._closed or self._cancel.is_set() or self._running_generation != self._generation:
            return
        self._error = ""
        if result.task == "detail":
            self._detail, self._raw_detail = result.detail or {}, result.raw_detail
        else:
            keep_detail = bool(
                self._detail and self._report is result.report and self._applied
                and result.options[:2] == self._applied[:2]
                and result.options[3] == self._applied[3]
            )
            self._report = result.report
            self._cache[result.options[1]] = result.report
            self._unit, self._window, self._sort, self._query = result.options
            self._applied = result.options
            self._accepted_source = self._source_generation
            self._units = result.units
            self._rows, self._lookup = result.rows, result.lookup or {}
            self._summary, self._page = result.summary or {}, result.page
            self._applied_page = self._page
            if not keep_detail:
                self._detail = {}
                self._raw_detail = None
        self.changed.emit()

    @Slot(str)
    def _fail(self, message):
        if not self._closed and not self._cancel.is_set() and self._running_generation == self._generation:
            self._error = message
            # A failed request must not relabel accepted results with new options.
            if self._applied is not None and self._accepted_source == self._source_generation:
                self._unit, self._window, self._sort, self._query = self._applied
                self._page = self._applied_page
            self.changed.emit()

    @Slot()
    def _finished(self):
        thread = self._thread
        if thread is None:
            return
        # finished precedes native/TLS cleanup on some Windows Python versions.
        thread.wait()
        self._thread = self._worker = None
        self._task = ""
        self.changed.emit()
        if self._closed:
            self._complete_shutdown()
        elif self._pending:
            self._schedule()

    @Slot(int)
    def setPage(self, page):
        if not self._is_current():
            return
        page = max(1, min(page, max(1, (len(self._rows) + PAGE_SIZE - 1) // PAGE_SIZE)))
        if page == self._page:
            return
        self._page = page
        self._request()

    @Slot(str, str)
    def investigate(self, code, unit):
        if not self._is_current() or (code, unit) not in self._lookup:
            return
        months, selected, report = self._months, self._selected, self._report
        options = self._options()
        units = self._units

        def action(cancel):
            raw = product_performance_detail(months, selected, code, unit, window=options[1], report=report, cancel=cancel)
            detail = _present_detail(raw, report, cancel)
            return _Result("detail", options, report, units, detail=detail, raw_detail=raw)

        self._generation += 1
        self._error = ""
        self._start(action, "detail")

    @Slot()
    def closeDetail(self):
        if self._task == "detail" and self._thread is not None:
            self._generation += 1
            self._cancel.set()
        self._detail = {}
        self._raw_detail = None
        self.changed.emit()

    def shutdown(self, *, wait_ms=5000):
        if self._shutdown_complete:
            return True
        self._closed = True
        self._pending = False
        self._generation += 1
        self._cancel.set()
        thread = self._thread
        if thread is not None:
            thread.quit()
            if not thread.wait(wait_ms):
                self.setParent(None)
                _SHUTTING_DOWN.add(self)
                return False
            self._finished()
        else:
            self._complete_shutdown()
        return True

    def _complete_shutdown(self):
        if self._shutdown_complete:
            return
        self._shutdown_complete = True
        _SHUTTING_DOWN.discard(self)
        self.changed.emit()
        self.shutdownFinished.emit()
