"""Bounded priority views over accepted monthly facts, outside the GUI thread."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import logging
from threading import Event

from PySide6.QtCore import QObject, Property, QThread, Signal, Slot

from liarte_core.inventory import SCALE, folded, money, number
from liarte_core.inventory_performance import analyze_product_performance
from liarte_core.inventory_priorities import analyze_product_priorities
from liarte_core.query import Cancelled, checkpoint

LOGGER = logging.getLogger("liarte.desktop")
_SHUTTING_DOWN = set()
PAGE_SIZE = 8
_WINDOWS = (1, 3, 6)
_CATEGORIES = (
    ("review", "Critérios combinados"),
    ("coverage", "Cobertura < limite"),
    ("decline", "Variação de vendas < 0"),
    ("idle", "Saldo > 0 · vendas líquidas = 0"),
    ("capital", "Estoque a custo"),
)


def _quantity(value, unit):
    return number(Decimal(value) / SCALE, 3) + " " + unit if value is not None else "—"


def _evolution(row):
    change = row.get("change")
    if change is None:
        return "Sem comparação entre janelas completas"
    value = ("+" if change > 0 else "") + _quantity(change, row["unit"])
    percentage = row.get("percentage")
    if percentage is not None:
        value += " · " + ("+" if percentage > 0 else "") + number(percentage, 1) + "%"
    return value


def _criterion_for(row, category):
    criteria = row.get("criteria", ())
    key = row.get("primaryCategory") if category == "review" else category
    return next((criterion for criterion in criteria if criterion["key"] == key), {})


def _condition_value(value, condition):
    unit, scale = condition["unit"], condition["scale"]
    if unit == "R$":
        return money(value)
    if scale == SCALE:
        return _quantity(value, unit)
    if unit == "dias":
        return number(value, 1) + " dias"
    return number(value, 0) + (" " + unit if unit else "")


def _condition_expression(condition):
    return (
        condition["label"] + ": "
        + _condition_value(condition["value"], condition) + " "
        + condition["operator"] + " "
        + _condition_value(condition["reference"], condition)
    )


def _present_criterion(criterion, report):
    conditions = criterion.get("conditions", ())
    closing = report.get("targetPeriod", "")
    closing_label = closing[5:] + "/" + closing[:4] if closing else "—"
    reference = "Fechamento: " + closing_label
    if criterion["key"] in ("coverage", "decline", "idle"):
        reference += " · Vendas: " + report.get("targetLabel", "")
    if criterion["key"] == "decline":
        reference += " vs. " + report.get("baseLabel", "")
    if criterion["key"] == "coverage":
        reference += " · " + report.get("coveragePolicy", "Limite configurado")
    return {
        "label": criterion["label"],
        "value": _condition_expression(conditions[0]) if conditions else "—",
        "detail": " · ".join([*(_condition_expression(value) for value in conditions[1:]), reference]),
    }


def _present_row(row, category):
    criterion = _criterion_for(row, category)
    conditions = criterion.get("conditions", ())
    coverage = row.get("coverage")
    return {
        "code": row["code"], "name": row["name"], "unit": row["unit"],
        "primaryTitle": criterion.get("label", row.get("primaryTitle", "")),
        "stockQuantity": _quantity(row.get("stockQuantity"), row["unit"]),
        "stockCost": money(row["stockCost"]) if row.get("stockCost") is not None else "—",
        "sold": _quantity(row.get("sold"), row["unit"]),
        "evolution": _evolution(row),
        "coverage": number(coverage, 1) + " dias" if coverage is not None else "—",
        "criterion": _condition_expression(conditions[0]) if conditions else "",
        "categories": [
            {"key": key, "label": label} for key, label in _CATEGORIES
            if key != "review" and key in row.get("categories", ())
        ],
    }


def _present_detail(row, report, category):
    closing = report.get("targetPeriod", "")
    closing_label = closing[5:] + "/" + closing[:4] if closing else "Sem fechamento"
    presented = _present_row(row, category)
    return {
        "code": row["code"], "name": row["name"], "unit": row["unit"],
        "title": presented["primaryTitle"],
        "metrics": [
            {"label": "Saldo no fechamento", "value": presented["stockQuantity"],
             "detail": closing_label},
            {"label": "Estoque a custo", "value": presented["stockCost"],
             "detail": closing_label + " · Não representa faturamento."},
            {"label": "Vendas líquidas", "value": presented["sold"],
             "detail": report.get("targetLabel", "")},
            {"label": "Vendas líquidas anteriores", "value": _quantity(row.get("previous"), row["unit"]),
             "detail": report.get("baseLabel", "")},
            {"label": "Evolução entre janelas", "value": presented["evolution"],
             "detail": report.get("targetLabel", "") + " vs. " + report.get("baseLabel", "")},
            {"label": "Cobertura estimada", "value": presented["coverage"],
             "detail": row.get("coverageReason", "")},
        ],
        "criteria": [_present_criterion(criterion, report) for criterion in row.get("criteria", ())],
        "notice": row.get("dataNotice", ""),
    }


def _view(report, unit, category, query, requested_page, cancel):
    needle = folded(query.strip())
    counts = dict.fromkeys((key for key, _ in _CATEGORIES), 0)
    rows, lookup = [], {}
    for index, row in enumerate(report.get("rows", ())):
        if index % 256 == 0:
            checkpoint(cancel)
        if row["unit"] != unit or needle and needle not in folded(row["code"] + " " + row["name"]):
            continue
        categories = row.get("categories", ())
        review = any(key in categories for key in ("coverage", "decline", "idle"))
        if review:
            counts["review"] += 1
        for key in categories:
            if key in counts and key != "review":
                counts[key] += 1
        if category == "review" and not review or category != "review" and category not in categories:
            continue
        rows.append(row)
        lookup[row["code"], row["unit"]] = row
    page = max(1, min(requested_page, max(1, (len(rows) + PAGE_SIZE - 1) // PAGE_SIZE)))
    closing = report.get("targetPeriod", "")
    summary = {
        "rows": [_present_row(row, category) for row in rows[(page - 1) * PAGE_SIZE:page * PAGE_SIZE]],
        "targetLabel": report.get("targetLabel", ""),
        "baseLabel": report.get("baseLabel", ""),
        "targetPeriod": closing,
        "closingLabel": closing[5:] + "/" + closing[:4] if closing else "Sem fechamento",
        "scope": report.get("scope", ""),
        "referenceNotice": report.get("referenceNotice", ""),
        "coverageDays": report.get("coverageDays"),
        "coveragePolicy": report.get("coveragePolicy", ""),
        "notice": report.get("notice", ""),
        "reason": report.get("reason", ""),
        "orderLabel": "Estoque a custo · maior valor primeiro",
    }
    categories = tuple({"value": key, "label": label, "count": counts[key]} for key, label in _CATEGORIES)
    checkpoint(cancel)
    return tuple(rows), lookup, summary, categories, page


@dataclass(frozen=True, slots=True)
class _Result:
    options: tuple
    performance: dict
    report: dict
    units: tuple
    rows: tuple
    lookup: dict
    summary: dict
    categories: tuple
    page: int


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
        except Exception:
            LOGGER.exception("Falha ao preparar prioridades dos produtos")
            self.failed.emit("Não foi possível preparar as prioridades. Confira o recorte e tente novamente.")
        finally:
            self.finished.emit()


class InventoryPrioritiesController(QObject):
    """Own one cooperative task; expose only one page and an explicit selection."""

    changed = Signal()
    shutdownFinished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._months = self._selected = None
        self._coverage_days = 30
        self._source_generation = self._generation = self._running_generation = 0
        self._accepted_source = -1
        self._thread = self._worker = None
        self._cancel = Event()
        self._pending = self._requested = self._closed = self._shutdown_complete = False
        self._cancelled = False
        self._unit, self._window, self._category, self._query = "", 3, "review", ""
        self._page = self._applied_page = 1
        self._units = self._rows = self._categories = ()
        self._lookup, self._summary, self._detail = {}, {}, {}
        self._raw_detail = self._report = self._applied = None
        self._performance_cache, self._priority_cache = {}, {}
        self._error = ""

    def _options(self):
        return self._unit, self._window, self._category, self._query

    def _is_current(self):
        return (
            not self._closed and bool(self._months) and self._thread is None and not self._pending
            and self._report is not None and self._accepted_source == self._source_generation
            and self._applied == self._options()
        )

    @Property("QVariantMap", notify=changed)
    def state(self):
        return {
            "available": bool(self._months) and not self._closed,
            "busy": self._thread is not None or self._pending,
            "current": self._is_current(), "error": self._error,
            "cancelled": self._cancelled,
            "units": [{"value": unit, "label": unit} for unit in self._units],
            "unit": self._unit,
            "windows": [{"value": value, "label": str(value) + (" mês" if value == 1 else " meses")} for value in _WINDOWS],
            "window": self._window, "category": self._category,
            "categories": list(self._categories) or [
                {"value": key, "label": label, "count": 0} for key, label in _CATEGORIES
            ],
            "query": self._query, "page": self._page,
            "pages": max(1, (len(self._rows) + PAGE_SIZE - 1) // PAGE_SIZE),
            "count": len(self._rows),
        }

    @Property("QVariantMap", notify=changed)
    def summary(self):
        return self._summary

    @Property("QVariantMap", notify=changed)
    def detail(self):
        return self._detail

    @property
    def report(self):
        return self._report if self._is_current() else None

    def export_snapshot(self):
        return (self._report, self._raw_detail) if self._is_current() else (None, None)

    def set_source(self, months, selected, coverage_days=30):
        if type(coverage_days) is not int or not 1 <= coverage_days <= 3650:
            raise ValueError("O limite de cobertura deve ser um inteiro entre 1 e 3650.")
        same_data = months is self._months and selected == self._selected
        if self._closed or same_data and coverage_days == self._coverage_days:
            return
        self._months, self._selected, self._coverage_days = months, selected, coverage_days
        self._source_generation += 1
        self._generation += 1
        self._cancel.set()
        if not same_data:
            self._performance_cache = {}
        self._priority_cache = {}
        self._report = self._raw_detail = self._applied = None
        self._rows = self._units = self._categories = ()
        self._lookup, self._summary, self._detail = {}, {}, {}
        self._page = 1
        self._error = ""
        self._cancelled = False
        self._pending = self._requested and bool(months)
        self.changed.emit()
        if self._pending and self._thread is None:
            self._schedule()

    @Slot()
    def refresh(self):
        if self._closed:
            return
        self._requested = True
        was_cancelled = self._cancelled
        self._cancelled = False
        if was_cancelled and self._months and self._thread is not None:
            self._request()
            return
        if not self._months or self._is_current() or self._thread is not None or self._pending:
            if was_cancelled:
                self.changed.emit()
            return
        self._request()

    @Slot(str, int, str, str)
    def configure(self, unit, window, category, query):
        if self._closed or not self._months:
            return
        if (
            type(window) is not int or window not in _WINDOWS
            or category not in dict(_CATEGORIES) or len(query) > 200
            or self._units and unit and unit not in self._units
        ):
            self._error = "Escolha unidade, janela, foco e busca válidos (até 200 caracteres)."
            self.changed.emit()
            return
        options = unit, window, category, query.strip()
        was_cancelled = self._cancelled
        self._cancelled = False
        if options == self._options() and (
            self._is_current() or not was_cancelled and (self._thread is not None or self._pending)
        ):
            if was_cancelled:
                self.changed.emit()
            return
        self._unit, self._window, self._category, self._query = options
        self._requested = True
        self._page = 1
        self._request()

    def _request(self):
        self._generation += 1
        self._cancel.set()
        self._pending = True
        self._error = ""
        self._cancelled = False
        self.changed.emit()
        if self._thread is None:
            self._schedule()

    def _schedule(self):
        if self._closed or not self._months or self._thread is not None:
            return
        self._pending = False
        months, selected, coverage_days = self._months, self._selected, self._coverage_days
        unit, window, category, query = self._options()
        performance = self._performance_cache.get(window)
        report = self._priority_cache.get(window)
        requested_page = self._page

        def action(cancel):
            prepared = performance
            if prepared is None:
                prepared = analyze_product_performance(months, selected, window=window, cancel=cancel)
            priorities = report
            if priorities is None:
                priorities = analyze_product_priorities(prepared, coverage_days=coverage_days, cancel=cancel)
            units = tuple(priorities.get("units", ()))
            focused = unit if unit in units else selected.unit if selected.unit in units else units[0] if units else ""
            rows, lookup, summary, categories, page = _view(priorities, focused, category, query, requested_page, cancel)
            return _Result((focused, window, category, query), prepared, priorities, units, rows, lookup, summary, categories, page)

        self._cancel = Event()
        self._running_generation = self._generation
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
        previous_identity = (self._detail.get("code"), self._detail.get("unit"))
        keep_detail = self._accepted_source == self._source_generation and self._applied and result.options[:2] == self._applied[:2]
        self._performance_cache[result.options[1]] = result.performance
        self._priority_cache[result.options[1]] = result.report
        self._report = result.report
        self._unit, self._window, self._category, self._query = result.options
        self._applied = result.options
        self._accepted_source = self._source_generation
        self._rows, self._lookup, self._summary = result.rows, result.lookup, result.summary
        self._units, self._categories = result.units, result.categories
        self._page = self._applied_page = result.page
        self._error = ""
        self._cancelled = False
        row = self._lookup.get(previous_identity) if keep_detail else None
        self._raw_detail = row
        self._detail = _present_detail(row, self._report, self._category) if row else {}
        self.changed.emit()

    def _restore_applied(self):
        if self._applied is not None and self._accepted_source == self._source_generation:
            self._unit, self._window, self._category, self._query = self._applied
            self._page = self._applied_page

    @Slot(str)
    def _fail(self, message):
        if not self._closed and not self._cancel.is_set() and self._running_generation == self._generation:
            self._error = message
            self._restore_applied()
            self.changed.emit()

    @Slot()
    def _finished(self):
        thread = self._thread
        if thread is None:
            return
        thread.wait()
        self._thread = self._worker = None
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
        if page != self._page:
            self._page = page
            self._request()

    @Slot(str, str)
    def investigate(self, code, unit):
        if not self._is_current():
            return
        row = self._lookup.get((code, unit))
        if row is not None:
            self._raw_detail = row
            self._detail = _present_detail(row, self._report, self._category)
            self.changed.emit()

    @Slot()
    def closeDetail(self):
        self._detail = {}
        self._raw_detail = None
        self.changed.emit()

    @Slot()
    def cancel(self):
        if self._closed:
            return
        self._pending = False
        self._cancelled = True
        self._generation += 1
        self._cancel.set()
        self._restore_applied()
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
