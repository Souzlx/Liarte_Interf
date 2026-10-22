"""Apresentação do módulo Estoque: tarefas canceláveis e sessão persistente."""

from __future__ import annotations

import logging
import os
from dataclasses import replace
from datetime import date
from pathlib import Path
from threading import Event
from uuid import uuid4

from PySide6.QtCore import (
    Property,
    QAbstractTableModel,
    QModelIndex,
    QObject,
    Qt,
    QThread,
    QTimer,
    QUrl,
    Signal,
    Slot,
)

from liarte_core.inventory import (
    SCALE,
    StockSelection,
    analyze_inventory,
    money,
    month_range,
    month_end,
    number,
)
from liarte_core.inventory_export import export_inventory
from liarte_core.inventory_assets import verify_bundled_inventory
from liarte_core.inventory_search import ProductSearch
from liarte_core.inventory_io import load_inventory, write_snapshot
from liarte_core.query import Cancelled, checkpoint

LOGGER = logging.getLogger("liarte.desktop")
HEADERS = (
    "Código",
    "Produto",
    "Filial",
    "Arm.",
    "UM",
    "Saldo",
    "Custo (R$)",
    "ABC",
    "Últ. venda",
    "Giro (x/mês)",
    "Dias fonte",
)


def stock_cells(row):
    b = row.balance
    return (
        b.product,
        row.name,
        b.branch,
        b.warehouse,
        b.unit,
        number(b.quantity / SCALE, 3),
        money(b.cost),
        row.abc,
        row.last_sale.strftime("%d/%m/%Y") if row.last_sale else "—",
        number(row.turnover, 2),
        number(row.source_days, 1),
    )


class StockTableModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = ()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(HEADERS)

    def roleNames(self):
        return {int(Qt.ItemDataRole.DisplayRole): b"display"}

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if (
            orientation == Qt.Orientation.Horizontal
            and role == Qt.ItemDataRole.DisplayRole
            and 0 <= section < len(HEADERS)
        ):
            return HEADERS[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if (
            index.isValid()
            and 0 <= index.row() < len(self.rows)
            and 0 <= index.column() < len(HEADERS)
            and role == Qt.ItemDataRole.DisplayRole
        ):
            return stock_cells(self.rows[index.row()])[index.column()]
        return None

    def setRows(self, rows):
        self.beginResetModel()
        self.rows = tuple(rows)
        self.endResetModel()


class InventoryWorker(QObject):
    done = Signal(object)
    failed = Signal(str)
    progress = Signal(int, str)
    finished = Signal()

    def __init__(self, action, cancel):
        super().__init__()
        self.action, self.cancel = action, cancel

    @Slot()
    def run(self):
        try:
            result = self.action(self.cancel, self.progress.emit)
            checkpoint(self.cancel)
            self.done.emit(result)
        except Cancelled:
            pass
        except PermissionError:
            LOGGER.exception("Permissão de arquivo negada na operação de estoque")
            self.failed.emit(
                "Não foi possível acessar ou salvar o arquivo. Feche a planilha no Excel e verifique a permissão da pasta."
            )
        except (ValueError, OSError) as exc:
            LOGGER.exception("Falha na operação de estoque")
            self.failed.emit(str(exc)[:400])
        except Exception:
            LOGGER.exception("Falha na operação de estoque")
            self.failed.emit(
                "Não foi possível concluir esta operação. A base anterior foi mantida. Consulte o diagnóstico se o problema persistir."
            )
        finally:
            self.finished.emit()


class InventoryController(QObject):
    changed = Signal()
    optionsChanged = Signal()
    analysisChanged = Signal()
    detailChanged = Signal()

    def __init__(self, settings=None, parent=None, *, cache_path=None, bundled_path=None):
        super().__init__(parent)
        self.table = StockTableModel(self)
        self._settings = settings
        self._cache = Path(cache_path) if cache_path else None
        self._data = None
        self._analysis = None
        self._selection = None
        self._applied_selection = None
        self._options = []
        self._thread = None
        self._worker = None
        self._cancel = Event()
        self._generation = 0
        self._running_generation = 0
        self._pending = False
        self._error = ""
        self._task = ""
        self._progress = 0
        self._label = ""
        self._page = 1
        self._sort = 6
        self._descending = True
        self._ordered = ()
        self._detail = {}
        self._selected_index = -1
        self._restored = False
        self._closed = False
        self._staged_cache = None
        self._bundled = Path(bundled_path) if bundled_path is not None else None
        self._search = None
        self._sales_begin = None
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(140)
        self._debounce.timeout.connect(self._schedule_analysis)

    @Property("QVariantMap", notify=changed)
    def state(self):
        data, analysis = self._data, self._analysis
        selection = self._selection
        return {
            "loaded": data is not None,
            "busy": self._thread is not None,
            "current": self._selection == self._applied_selection
            and not self._pending
            and not self._debounce.isActive(),
            "task": self._task,
            "progress": self._progress,
            "busyLabel": self._label,
            "error": self._error,
            "asOf": data.as_of.strftime("%d/%m/%Y") if data else "",
            "source": data.source_name if data else "",
            "productLabel": self._search.names.get(selection.product, "")
            if self._search and selection
            else "",
            "metrics": list(analysis.metrics) if analysis else [],
            "trend": list(analysis.trend) if analysis else [],
            "ranking": list(analysis.ranking) if analysis else [],
            "activityChart": list(analysis.activity) if analysis else [],
            "historicalScope": analysis.historical_scope if analysis else "",
            "selection": {k: getattr(selection, k) for k in selection.__dataclass_fields__}
            if selection
            else {},
            "page": self._page,
            "pages": max(1, (len(self._ordered) + 49) // 50),
            "count": len(self._ordered),
            "sortColumn": self._sort,
            "descending": self._descending,
            "detail": self._detail,
            "selectedRow": self._selected_index,
            "notes": list(data.notes) if data else [],
        }

    @Property("QVariantList", notify=optionsChanged)
    def options(self):
        return self._options

    @Property("QVariantMap", notify=analysisChanged)
    def analysis(self):
        result = self._analysis
        return {
            "metrics": list(result.metrics) if result else [],
            "trend": list(result.trend) if result else [],
            "plotTrend": [
                dict(
                    p,
                    value=p["raw"] / 100 if p["raw"] is not None else None,
                    movingValue=p["movingValue"] * 1_000_000
                    if p["movingValue"] is not None
                    else None,
                )
                for p in result.trend
            ]
            if result
            else [],
            "ranking": list(result.ranking) if result else [],
            "activityChart": list(result.activity) if result else [],
            "historicalScope": result.historical_scope if result else "",
            "historySummary": result.history_summary if result else {},
        }

    @Property("QVariantMap", notify=detailChanged)
    def detail(self):
        return self._detail

    def _build_options(self):
        if self._data is None:
            return []
        d = self._data

        def choices(values, label="Todos"):
            return [{"value": "", "label": label}] + [
                {"value": v, "label": v} for v in sorted(set(values))
            ]

        branches = dict(d.branches)
        warehouses = dict(d.warehouses)
        oldest = min(
            [c.period for c in d.closings]
            + [s.day.strftime("%Y-%m") for s in d.sales]
            + [d.as_of.strftime("%Y-%m")]
        )
        minimum_index = d.as_of.year * 12 + d.as_of.month - 1 - 240
        minimum = f"{minimum_index // 12:04d}-{minimum_index % 12 + 1:02d}"
        periods = month_range(max(oldest, minimum), d.as_of.strftime("%Y-%m"))
        return [
            {
                "key": "branch",
                "label": "Filial",
                "values": [{"value": "", "label": "Todas as filiais"}]
                + [
                    {"value": k, "label": k + " · " + branches.get(k, k)}
                    for k in sorted({b.branch for b in d.balances})
                ],
            },
            {
                "key": "warehouse",
                "label": "Armazém",
                "values": [{"value": "", "label": "Todos os armazéns"}]
                + [
                    {"value": k, "label": k + " · " + warehouses.get(k, k)}
                    for k in sorted({b.warehouse for b in d.balances})
                ],
            },
            {"key": "group", "label": "Grupo", "values": choices(p.group for p in d.products)},
            {"key": "unit", "label": "Unidade", "values": choices(b.unit for b in d.balances)},
            {"key": "kind", "label": "Tipo", "values": choices(p.kind for p in d.products)},
            {
                "key": "product",
                "label": "Produto",
                "values": [{"value": "", "label": "Todos os produtos"}]
                + [
                    {"value": p.code, "label": p.code + " · " + p.name}
                    for p in sorted(d.products, key=lambda p: p.name)
                ],
            },
            {"key": "abc", "label": "Curva ABC", "values": choices(("A", "B", "C"))},
            {
                "key": "activity",
                "label": "Última venda",
                "values": choices(("Até 30 dias", "31–90 dias", "Mais de 90 dias", "Sem venda")),
            },
            {
                "key": "balance",
                "label": "Saldo",
                "values": [
                    {"value": "", "label": "Todos"},
                    {"value": "positive", "label": "Com saldo positivo"},
                    {"value": "zero", "label": "Zerado"},
                    {"value": "negative", "label": "Saldo negativo"},
                ],
            },
            {
                "key": "start",
                "label": "Mês inicial",
                "values": [{"value": p, "label": p[5:] + "/" + p[:4]} for p in periods],
            },
            {
                "key": "end",
                "label": "Mês final",
                "values": [{"value": p, "label": p[5:] + "/" + p[:4]} for p in periods],
            },
        ]

    @Slot()
    def ensureLoaded(self):
        if self._restored or self._data or self._thread:
            return
        self._restored = True
        if self._cache and self._cache.is_file():
            self._open_path(self._cache, fallback=self._bundled)
        elif self._bundled is not None:
            self._open_path(self._bundled)

    def _default_selection(self, data):
        end = data.as_of.strftime("%Y-%m")
        index = data.as_of.year * 12 + data.as_of.month - 12
        start = f"{index // 12:04d}-{index % 12 + 1:02d}"
        first_month = min(
            [c.period for c in data.closings]
            + [s.day.strftime("%Y-%m") for s in data.sales]
            + [end]
        )
        start = max(start, first_month)
        return StockSelection(start, end)

    @Slot(QUrl)
    def openFile(self, url):
        if self._thread or self._closed or not url.isLocalFile():
            return
        self._open_path(Path(url.toLocalFile()))

    def _open_path(self, path, *, fallback=None):
        if self._thread or self._closed:
            return
        self._generation += 1
        self._pending = False
        self._debounce.stop()
        staged = (
            self._cache.with_name(".base-" + uuid4().hex + ".liarte")
            if self._cache and (path.resolve() != self._cache.resolve() or fallback is not None)
            else None
        )
        self._staged_cache = staged

        def action(cancel, progress):
            def read(candidate):
                if self._bundled is not None and candidate.resolve() == self._bundled.resolve():
                    verify_bundled_inventory(candidate)
                return load_inventory(candidate, cancel, progress)

            try:
                data = read(path)
            except (ValueError, OSError):
                if fallback is None:
                    raise
                LOGGER.exception("Cópia local de estoque indisponível; recuperando base integrada")
                checkpoint(cancel)
                data = read(fallback)
                data = replace(
                    data,
                    notes=(
                        *data.notes,
                        "A cópia local não pôde ser lida. Foi recuperada a base integrada de "
                        + data.as_of.strftime("%d/%m/%Y")
                        + ".",
                    ),
                )
            selected = self._default_selection(data)
            analysis = analyze_inventory(data, selected)
            checkpoint(cancel)
            if staged:
                write_snapshot(data, staged, cancel)
            return ("load", data, selected, analysis)

        self._start(action, "load")

    @Slot(str, result="QVariantMap")
    def searchProducts(self, text):
        return self._search.find(text) if self._search else {"items": [], "count": 0}

    @Slot()
    def reload(self):
        if self._cache and self._cache.is_file() and not self._thread:
            self.openFile(QUrl.fromLocalFile(str(self._cache)))

    @Slot(str, str)
    def setFilter(self, key, value):
        if (
            self._selection is None
            or self._task in {"load", "export"}
            or key not in self._selection.__dataclass_fields__
        ):
            return
        if key != "search":
            option = next((o for o in self.options if o["key"] == key), None)
            if not option or value not in {v["value"] for v in option["values"]}:
                return
        elif len(value) > 200:
            return
        updates = {key: value}
        if key == "product" and value:
            updates["search"] = ""
        elif key == "search" and value:
            updates["product"] = ""
        updated = replace(self._selection, **updates)
        if updated == self._selection:
            return
        self._selection = updated
        self._generation += 1
        self._pending = True
        self._error = ""
        self._page = 1
        self._debounce.start()
        self.changed.emit()

    @Slot()
    def resetFilters(self):
        if self._data is None or self._task in {"load", "export"}:
            return
        self._selection = self._default_selection(self._data)
        self._generation += 1
        self._pending = True
        self._page = 1
        self._debounce.start()
        self.changed.emit()

    def _schedule_analysis(self):
        if self._thread or self._data is None or self._closed:
            return
        self._pending = False
        data, selected = self._data, self._selection
        self._start(
            lambda cancel, progress: ("analysis", analyze_inventory(data, selected)), "analysis"
        )

    def _start(self, action, task):
        self._cancel = Event()
        self._running_generation = self._generation
        self._task = task
        self._progress = 0
        self._label = (
            "Atualizando análise"
            if task == "analysis"
            else "Preparando Excel"
            if task == "export"
            else "Abrindo base"
        )
        self._error = ""
        self._thread = QThread(self)
        self._worker = InventoryWorker(action, self._cancel)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.done.connect(self._accept)
        self._worker.failed.connect(self._fail)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._finished)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()
        self.changed.emit()

    @Slot(int, str)
    def _on_progress(self, value, label):
        self._progress, self._label = value, label
        self.changed.emit()

    @Slot(object)
    def _accept(self, result):
        if self._cancel.is_set() or self._running_generation != self._generation or self._closed:
            return
        if result[0] == "load":
            # Publicar a base e a sessão juntas na thread visual: um Cancelar
            # ocorrido antes da aceitação não pode substituir o cache válido.
            if self._staged_cache is not None:
                try:
                    os.replace(self._staged_cache, self._cache)
                except OSError:
                    LOGGER.exception("Falha ao publicar a base de estoque")
                    self._fail(
                        "Não foi possível salvar a base de estoque. Verifique a permissão da pasta de dados da LIARTE."
                    )
                    return
                self._staged_cache = None
            _, self._data, self._selection, self._analysis = result
            self._search = ProductSearch(self._data)
            self._sales_begin = min((s.day for s in self._data.sales), default=self._data.as_of)
            self._page = 1
            self._detail = {}
            self._options = self._build_options()
            self.optionsChanged.emit()
        elif result[0] == "analysis":
            self._analysis = result[1]
        elif result[0] == "export":
            self.changed.emit()
            return
        self._applied_selection = self._selection
        self._publish_rows()
        self.analysisChanged.emit()
        self.changed.emit()

    @Slot(str)
    def _fail(self, message):
        if self._running_generation == self._generation and not self._cancel.is_set():
            self._error = message
            self.changed.emit()

    @Slot()
    def _finished(self):
        self._discard_staged_cache()
        self._thread = self._worker = None
        self._task = ""
        self._progress = 0
        self.changed.emit()
        if self._pending and not self._closed:
            self._debounce.start(0)

    def _publish_rows(self):
        if not self._analysis:
            return

        def key(row):
            b = row.balance
            value = (
                b.product,
                row.name,
                b.branch,
                b.warehouse,
                b.unit,
                b.quantity,
                b.cost,
                row.abc,
                row.last_sale or date.min,
                row.turnover,
                row.source_days,
            )[self._sort]
            return (
                value is not None,
                value if value is not None else -1,
                b.product,
                b.branch,
                b.warehouse,
            )

        self._ordered = tuple(sorted(self._analysis.rows, key=key, reverse=self._descending))
        self._page = min(self._page, max(1, (len(self._ordered) + 49) // 50))
        self.table.setRows(self._ordered[(self._page - 1) * 50 : self._page * 50])
        self._selected_index = -1
        self._detail = {}
        self.detailChanged.emit()

    @Slot(int)
    def sortByColumn(self, column):
        if not 0 <= column < len(HEADERS):
            return
        self._descending = not self._descending if column == self._sort else column in (5, 6, 9, 10)
        self._sort = column
        self._page = 1
        self._publish_rows()
        self.changed.emit()

    @Slot(int)
    def setPage(self, page):
        page = min(max(1, page), max(1, (len(self._ordered) + 49) // 50))
        if page != self._page:
            self._page = page
            self._publish_rows()
            self.changed.emit()

    @Slot(int)
    def selectRow(self, index):
        if (
            not 0 <= index < len(self.table.rows)
            or self._selection != self._applied_selection
            or self._pending
            or self._debounce.isActive()
            or self._task == "load"
        ):
            return
        row = self.table.rows[index]
        b = row.balance
        self._selected_index = index
        periods = month_range(self._selection.start, self._selection.end)
        monthly_sales = {p: 0 if month_end(p) >= self._sales_begin else None for p in periods}
        for sale in self._data.sales:
            if (sale.product, sale.branch, sale.unit) == (b.product, b.branch, b.unit):
                period = sale.day.strftime("%Y-%m")
                if period in monthly_sales and monthly_sales[period] is not None:
                    monthly_sales[period] += sale.quantity
        monthly_giro = {
            c.period: c.turnover
            for c in self._data.closings
            if (c.product, c.branch, c.warehouse, c.unit)
            == (b.product, b.branch, b.warehouse, b.unit)
        }
        self._detail = {
            "code": b.product,
            "unit": b.unit,
            "title": b.product + " · " + row.name,
            "location": "Filial " + b.branch + " · armazém " + b.warehouse,
            "balance": number(b.quantity / SCALE, 3) + " " + b.unit,
            "cost": money(b.cost),
            "sold": number(row.sold / SCALE, 3) + " " + b.unit + " · filial inteira",
            "coverage": number(row.coverage, 1) + " dias"
            if row.coverage is not None
            else "Indisponível neste recorte",
            "lastSale": row.last_sale.strftime("%d/%m/%Y")
            if row.last_sale
            else "Sem venda registrada",
            "mean": number(row.monthly_mean, 3) + " " + b.unit
            if row.monthly_mean is not None
            else "—",
            "std": number(row.monthly_std, 3) + " " + b.unit
            if row.monthly_std is not None
            else "—",
            "cv": number(row.cv * 100, 1) + "%" if row.cv is not None else "—",
            "months": row.full_months,
            "turnover": number(row.turnover, 2) + " x/mês" if row.turnover is not None else "—",
            "sourcePeriod": row.source_period[5:] + "/" + row.source_period[:4]
            if row.source_period
            else "Sem fechamento desta posição",
            "salesTrend": [
                {
                    "period": p,
                    "label": p[5:]
                    + "/"
                    + p[:4]
                    + (
                        " (parcial)"
                        if month_end(p) > self._data.as_of
                        or date.fromisoformat(p + "-01") < self._sales_begin <= month_end(p)
                        else ""
                    ),
                    "value": qty / SCALE if qty is not None else None,
                    "display": number(qty / SCALE, 3) + " " + b.unit
                    if qty is not None
                    else "Sem dados",
                }
                for p, qty in monthly_sales.items()
            ],
            "giroTrend": [
                {
                    "period": p,
                    "label": p[5:] + "/" + p[:4],
                    "value": monthly_giro.get(p),
                    "display": number(monthly_giro.get(p), 3) + " x/mês"
                    if monthly_giro.get(p) is not None
                    else "Sem fechamento",
                }
                for p in periods
            ],
        }
        self.detailChanged.emit()
        self.changed.emit()

    @Slot(QUrl)
    def exportExcel(self, url):
        if (
            self._thread
            or self._debounce.isActive()
            or self._data is None
            or self._analysis is None
            or self._selection != self._applied_selection
            or not url.isLocalFile()
        ):
            return
        path = Path(url.toLocalFile())
        if path.suffix.lower() != ".xlsx":
            path = path.with_suffix(".xlsx")
        data, analysis, selected = self._data, self._analysis, self._selection

        def action(cancel, progress):
            export_inventory(data, analysis, selected, path, cancel)
            return ("export",)

        self._start(action, "export")

    @Slot()
    def cancel(self):
        self._pending = False
        self._debounce.stop()
        self._cancel.set()
        if self._applied_selection is not None:
            self._selection = self._applied_selection
        self.changed.emit()

    def shutdown(self):
        self._closed = True
        self.cancel()
        if self._thread:
            self._thread.quit()
            self._thread.wait(15000)
        self._discard_staged_cache()

    def _discard_staged_cache(self):
        if self._staged_cache is not None:
            try:
                self._staged_cache.unlink(missing_ok=True)
            except OSError:
                LOGGER.warning("Não foi possível remover base temporária de estoque", exc_info=True)
            self._staged_cache = None
