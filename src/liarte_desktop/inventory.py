"""Apresentação do módulo Estoque: tarefas canceláveis e sessão persistente."""

from __future__ import annotations

import logging
import os
import stat
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from itertools import chain
from pathlib import Path
from threading import Event
from types import MappingProxyType, SimpleNamespace
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
    compact_money,
    money,
    month_range,
    month_end,
    number,
)
from liarte_core.inventory_export import export_inventory
from liarte_core.inventory_monthly import analyze_monthly_inventory
from liarte_core.inventory_assets import verify_bundled_inventory
from liarte_core.inventory_search import ProductSearch
from liarte_core.inventory_io import load_inventory, write_snapshot
from liarte_core.inventory_backup import (
    backup_previous,
    list_backups,
    load_backup,
    prune_backups,
)
from liarte_core.query import Cancelled, checkpoint

LOGGER = logging.getLogger("liarte.desktop")
# A timed-out shutdown must retain its QObject tree until QThread.finished.
_SHUTTING_DOWN = set()
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
        number(Decimal(b.quantity) / SCALE, 3),
        money(b.cost),
        row.abc,
        row.last_sale.strftime("%d/%m/%Y") if row.last_sale else "—",
        number(row.turnover, 2),
        number(row.source_days, 1),
    )


def _checked(values, cancel):
    for index, value in enumerate(values):
        if cancel is not None and index % 256 == 0:
            checkpoint(cancel)
        yield value
    if cancel is not None:
        checkpoint(cancel)


def _cache_fingerprint(path):
    """Cheap optimistic publication check; no file content is read on the GUI."""
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("A base local deve ser um arquivo regular.")
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _backup_items(cache, cancel):
    """Prepare bounded labels off the GUI; paths and hashes stay internal."""
    return tuple(
        {
            "id": entry.id,
            "savedAt": datetime.fromisoformat(entry.created_at)
            .astimezone()
            .strftime("%d/%m/%Y %H:%M"),
            "asOf": date.fromisoformat(entry.as_of).strftime("%d/%m/%Y"),
            "source": entry.source_name,
            "products": entry.products,
        }
        for entry in list_backups(cache, cancel)[:10]
    )


def _read_backup_items(cache, cancel):
    if cache is None:
        return (), ""
    try:
        return _backup_items(cache, cancel), ""
    except (OSError, ValueError):
        LOGGER.warning("Não foi possível listar as bases anteriores", exc_info=True)
        return (), "Não foi possível consultar as bases anteriores. Tente novamente."


class _CheckedRows:
    def __init__(self, rows, cancel):
        self.rows, self.cancel = rows, cancel

    def __iter__(self):
        return _checked(self.rows, self.cancel)


def _order_rows(rows, column, descending, cancel=None):
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
        )[column]
        return (
            value is not None,
            value if value is not None else -1,
            b.product,
            b.branch,
            b.warehouse,
        )

    ordered = tuple(sorted(_checked(rows, cancel), key=key, reverse=descending))
    if cancel is not None:
        checkpoint(cancel)
    return ordered


def _monthly_presentation(months, cancel):
    """Cap only the QML summaries; complete monthly facts remain available to export."""
    prepared, units = [], set()
    for month in _checked(months, cancel):
        checkpoint(cancel)
        units.update(month["stockQuantity"])
        units.update(month["salesQuantity"])
        slow, never = [], []
        for row in _checked(month["slow"], cancel):
            (never if row["daysSinceSale"] is None else slow).append(row)
        slow.sort(
            key=lambda r: (-r["daysSinceSale"], -r["cost"], r["code"], r["branch"], r["unit"])
        )
        prepared.append(
            dict(
                month,
                slow=tuple(slow[:12]),
                neverSold=tuple(never[:12]),
                lowTurnover=tuple(month["lowTurnover"][:12]),
                changes=tuple(month["changes"][:12]),
                sellersByUnit={u: tuple(rows[:12]) for u, rows in month["sellersByUnit"].items()},
                salesChangesByUnit={
                    u: tuple(rows[:12]) for u, rows in month["salesChangesByUnit"].items()
                },
            )
        )
    checkpoint(cancel)
    return tuple(prepared), tuple(sorted(units))


@dataclass(frozen=True, slots=True)
class _LoadPresentation:
    search: object
    options: tuple
    sales_begin: date | None
    sales: object
    closings: object
    backups: tuple = ()
    backup_error: str = ""


@dataclass(frozen=True, slots=True)
class _Publication:
    # Prepared in the worker, then transferred once. No further producer mutation.
    kind: str
    data: object
    selected: StockSelection
    analysis: object
    monthly: tuple
    ordered: tuple
    sort: tuple
    monthly_display: tuple
    monthly_units: tuple
    monthly_view: dict
    period: str
    unit: str
    load: _LoadPresentation | None = None
    cache_fingerprint: tuple | None = None
    backup_id: str = ""


def _prepare_publication(
    kind,
    data,
    selected,
    analysis,
    monthly,
    column,
    descending,
    period,
    unit,
    names,
    cancel,
    load=None,
):
    display, units = _monthly_presentation(monthly, cancel)
    view, period, unit = _monthly_view(display, units, selected, names, period, unit)
    ordered = _order_rows(analysis.rows, column, descending, cancel)
    checkpoint(cancel)
    return _Publication(
        kind,
        data,
        selected,
        analysis,
        monthly,
        ordered,
        (column, descending),
        display,
        units,
        view,
        period,
        unit,
        load,
    )


def _monthly_view(months, units, selected, names, period, unit):
    """Prepare only the focused month for QML; changing focus never reloads data."""
    if not months:
        return {}, "", ""
    periods = {m["period"] for m in months}
    if period not in periods:
        period = next(
            (m["period"] for m in reversed(months) if m["stockCost"] is not None),
            months[-1]["period"],
        )
    focused = next(m for m in months if m["period"] == period)
    if unit not in units:
        unit = units[0] if units else ""
    index = months.index(focused)
    previous = months[index - 1] if index else None

    def quantity(value):
        return number(Decimal(value) / SCALE, 3) + " " + unit if value is not None else "—"

    def variation(current, before, *, currency=False):
        if current is None or before is None:
            return "Sem comparação mensal disponível"
        delta = current - before
        signed = ("+" if delta > 0 else "") + (money(delta) if currency else quantity(delta))
        percentage = (
            " · " + ("+" if delta > 0 else "") + number(delta / before * 100, 1) + "%"
            if before > 0
            else ""
        )
        return signed + percentage + " vs. " + focused["previousLabel"]

    stock = focused["stockQuantity"].get(unit)
    sales = focused["salesQuantity"].get(unit)
    giro = focused["turnover"]
    before_stock = previous["stockQuantity"].get(unit) if previous else None
    before_sales = previous["salesQuantity"].get(unit) if previous else None
    stock_detail = (
        variation(focused["stockCost"], previous["stockCost"], currency=True)
        if focused["stockChange"] is not None and previous
        else "Sem fechamento no mês e recorte"
        if focused["stockCost"] is None
        else focused["label"] + " · " + str(focused["productCount"]) + " produtos com saldo"
    )
    metrics = [
        {
            "label": "Estoque no fechamento",
            "value": compact_money(focused["stockCost"])
            if focused["stockCost"] is not None
            else "—",
            "detail": stock_detail,
            "full": (money(focused["stockCost"]) + ". " if focused["stockCost"] is not None else "")
            + focused["comparison"],
        },
        {
            "label": "Quantidade em estoque",
            "value": quantity(stock),
            "detail": "Fechamento · " + (unit or "sem unidade disponível"),
            "full": (
                variation(stock, before_stock)
                if focused["stockChange"] is not None
                else "Sem comparação entre fechamentos completos consecutivos"
            )
            + ". Registros observados; confira mudanças de cobertura.",
        },
        {
            "label": "Vendas do mês" + (" · parcial" if focused["partial"] else ""),
            "value": quantity(sales),
            "detail": variation(sales, before_sales)
            if focused["salesChange"].get(unit) is not None
            else "Mês parcial · sem comparação"
            if focused["partial"]
            else "Quantidade líquida · filial · " + (unit or "—"),
            "full": focused["salesComparison"],
        },
        {
            "label": "Giro da fonte · mediana",
            "value": number(giro, 2) + " x" if giro is not None else "—",
            "detail": str(focused["turnoverCount"]) + " posições válidas · " + focused["label"],
            "full": "Mediana dos giros não negativos da fonte em posições com saldo positivo no mês. Não é giro consolidado. "
            + str(focused["turnoverInvalidCount"])
            + " valores negativos ou inválidos fora da mediana. Valores ausentes não entram no cálculo.",
        },
    ]

    def series(key, title, symbol, note):
        points = []
        for month in months:
            if key == "cost":
                raw = month["stockCost"]
                value, display = (
                    (raw / 100, money(raw)) if raw is not None else (None, "Sem fechamento")
                )
            elif key == "turnover":
                value = month["turnover"]
                display = number(value, 2) + " x/mês" if value is not None else "Sem giro elegível"
            else:
                raw = month["salesQuantity" if key == "sales" else "stockQuantity"].get(unit)
                value, display = (
                    (raw / SCALE, quantity(raw)) if raw is not None else (None, "Sem dados")
                )
            points.append(
                {
                    "period": month["period"],
                    "label": month["label"]
                    + (" (parcial)" if key == "sales" and month["partial"] else ""),
                    "value": value,
                    "display": display,
                }
            )
        return {"title": title, "unit": symbol, "points": points, "note": note}

    view = {
        "months": [{"value": m["period"], "label": m["label"]} for m in months],
        "period": focused["period"],
        "label": focused["label"],
        "product": selected.product,
        "productLabel": names.get(selected.product, ""),
        "previousLabel": focused["previousLabel"],
        "units": [{"value": u, "label": u} for u in units],
        "unit": unit,
        "scope": focused["scope"],
        "salesScope": focused["salesScope"],
        "notice": focused["notice"],
        "metrics": metrics,
        "comparison": focused["comparison"],
        "salesComparison": focused["salesComparison"],
        "sellers": list(focused["sellersByUnit"].get(unit, ())[:12]),
        "slow": list(focused["slow"]),
        "neverSold": list(focused["neverSold"]),
        "lowTurnover": list(focused["lowTurnover"][:12]),
        "changes": list(focused["changes"][:12]),
        "salesChanges": list(focused["salesChangesByUnit"].get(unit, ())[:12]),
        "empty": "Nenhum registro neste mês e recorte."
        if focused["stockCost"] is None and sales is None
        else "",
        "seriesKinds": [
            {"value": "cost", "label": "Estoque a custo"},
            {"value": "quantity", "label": "Quantidade em estoque"},
            {"value": "sales", "label": "Vendas"},
            {"value": "turnover", "label": "Giro da fonte"},
        ],
        "series": {
            "cost": series(
                "cost",
                "Estoque a custo",
                "R$",
                "Fechamentos observados; lacunas não representam saldo zero.",
            ),
            "quantity": series(
                "quantity",
                "Quantidade em estoque",
                unit,
                "Quantidade no fechamento, somente na unidade selecionada.",
            ),
            "sales": series(
                "sales",
                "Vendas mensais da filial",
                unit,
                "Vendas líquidas; meses parciais identificados. Sem alocação por armazém.",
            ),
            "turnover": series(
                "turnover",
                "Giro da fonte · mediana",
                "x/mês",
                "Mediana por mês das posições elegíveis; não é giro consolidado.",
            ),
        },
    }
    return view, period, unit


class StockTableModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = ()
        self._display = ()

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
            return self._display[index.row()][index.column()]
        return None

    def setRows(self, rows):
        self.beginResetModel()
        self.rows = tuple(rows)
        self._display = tuple(stock_cells(row) for row in self.rows)
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
    monthlyChanged = Signal()
    backupChanged = Signal()
    shutdownFinished = Signal()

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
        self._applied_sort = (self._sort, self._descending)
        self._ordered = ()
        self._detail = {}
        self._selected_index = -1
        self._restored = False
        self._closed = False
        self._staged_cache = None
        self._backup_entries = ()
        self._backup_error = ""
        self._backup_notice = ""
        self._restoring_backup = False
        self._prune_requested = False
        self._prune_preserve_ids = set()
        self._bundled = Path(bundled_path) if bundled_path is not None else None
        self._search = None
        self._sales_begin = None
        self._sales_by_position = {}
        self._closings_by_position = {}
        self._default = None
        self._shutdown_complete = False
        self._monthly_data = ()
        self._monthly_display = ()
        self._monthly_units = ()
        self._monthly_period = ""
        self._monthly_unit = ""
        self._monthly_view = {}
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
        return list(self._options)

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

    @Property("QVariantMap", notify=monthlyChanged)
    def monthly(self):
        return self._monthly_view

    @Property("QVariantMap", notify=backupChanged)
    def backupState(self):
        available = self._cache is not None and not self._closed
        busy = self._thread is not None or self._pending or self._debounce.isActive()
        return {
            "available": available,
            "busy": busy,
            "canRestore": available and not busy,
            "error": self._backup_error,
            "notice": self._backup_notice,
            "items": list(self._backup_entries),
        }

    @Slot()
    def refreshBackups(self):
        self._refresh_backups(clear_notice=True)

    def _refresh_backups(self, *, clear_notice):
        if not self.backupState["canRestore"]:
            return
        self._backup_error = ""
        if clear_notice:
            self._backup_notice = ""
        cache = self._cache
        prune, preserved = self._prune_requested, tuple(self._prune_preserve_ids)
        self._prune_requested = False

        def action(cancel, progress):
            error = ""
            if prune:
                try:
                    prune_backups(cache, preserve_ids=preserved, cancel=cancel)
                except (OSError, ValueError):
                    LOGGER.warning("Não foi possível limitar as bases anteriores", exc_info=True)
                    error = "A base foi salva, mas não foi possível limpar cópias antigas."
            entries, listing_error = _read_backup_items(cache, cancel)
            return ("backups", entries, error or listing_error)

        self._start(action, "backups")

    @Slot(str)
    def restoreBackup(self, backup_id):
        if not self.backupState["canRestore"]:
            return
        if backup_id not in {entry["id"] for entry in self._backup_entries}:
            self._backup_error = (
                "A base anterior selecionada não está disponível. Atualize a lista."
            )
            self.backupChanged.emit()
            return
        self._open_path(self._cache, backup_id=backup_id)

    def _refresh_monthly(self):
        # Only bounded month summaries are visited here, never inventory facts/rankings.
        self._monthly_view, self._monthly_period, self._monthly_unit = _monthly_view(
            self._monthly_display,
            self._monthly_units,
            self._applied_selection,
            self._search.names if self._search else {},
            self._monthly_period,
            self._monthly_unit,
        )
        self.monthlyChanged.emit()

    @Slot(str)
    def setMonthlyPeriod(self, period):
        if (
            not self.state["current"]
            or self._thread
            or period not in {m["period"] for m in self._monthly_data}
        ):
            return
        if period != self._monthly_period:
            self._monthly_period = period
            self._refresh_monthly()

    @Slot(str)
    def setMonthlyUnit(self, unit):
        if (
            not self.state["current"]
            or self._thread
            or unit not in {v["value"] for v in self._monthly_view.get("units", [])}
        ):
            return
        if unit != self._monthly_unit:
            self._monthly_unit = unit
            self._refresh_monthly()

    @staticmethod
    def _build_options(d, cancel):
        def choices(values, label="Todos"):
            return [{"value": "", "label": label}] + [
                {"value": v, "label": v} for v in sorted(set(_checked(values, cancel)))
            ]

        branches = dict(d.branches)
        warehouses = dict(d.warehouses)
        oldest = min(
            chain(
                (c.period for c in _checked(d.closings, cancel)),
                (s.day.strftime("%Y-%m") for s in _checked(d.sales, cancel)),
                (d.as_of.strftime("%Y-%m"),),
            )
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
                    for k in sorted(
                        {b.branch for b in _checked(chain(d.balances, d.closings, d.sales), cancel)}
                    )
                ],
            },
            {
                "key": "warehouse",
                "label": "Armazém",
                "values": [{"value": "", "label": "Todos os armazéns"}]
                + [
                    {"value": k, "label": k + " · " + warehouses.get(k, k)}
                    for k in sorted(
                        {b.warehouse for b in _checked(chain(d.balances, d.closings), cancel)}
                    )
                ],
            },
            {"key": "group", "label": "Grupo", "values": choices(p.group for p in d.products)},
            {
                "key": "unit",
                "label": "Unidade",
                "values": choices(
                    b.unit for b in _checked(chain(d.balances, d.closings, d.sales), cancel)
                ),
            },
            {"key": "kind", "label": "Tipo", "values": choices(p.kind for p in d.products)},
            {
                "key": "product",
                "label": "Produto",
                "values": [{"value": "", "label": "Todos os produtos"}]
                + [
                    {"value": p.code, "label": p.code + " · " + p.name}
                    for p in sorted(_checked(d.products, cancel), key=lambda p: p.name)
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

    @staticmethod
    def _default_selection(data, cancel=None):
        end = data.as_of.strftime("%Y-%m")
        index = data.as_of.year * 12 + data.as_of.month - 12
        start = f"{index // 12:04d}-{index % 12 + 1:02d}"
        first_month = min(
            chain(
                (c.period for c in _checked(data.closings, cancel)),
                (s.day.strftime("%Y-%m") for s in _checked(data.sales, cancel)),
                (end,),
            )
        )
        start = max(start, first_month)
        return StockSelection(start, end)

    @Slot(QUrl)
    def openFile(self, url):
        if self._thread or self._closed or not url.isLocalFile():
            return
        self._open_path(Path(url.toLocalFile()))

    def _open_path(self, path, *, fallback=None, backup_id=None):
        if self._thread or self._closed:
            return
        self._generation += 1
        self._pending = False
        self._debounce.stop()
        self._backup_error = self._backup_notice = ""
        self._restoring_backup = backup_id is not None
        staged = (
            self._cache.with_name(".base-" + uuid4().hex + ".liarte")
            if self._cache
            and (
                path.resolve() != self._cache.resolve()
                or fallback is not None
                or backup_id is not None
            )
            else None
        )
        self._staged_cache = staged

        column, descending = self._sort, self._descending

        def action(cancel, progress):
            def read(candidate):
                if self._bundled is not None and candidate.resolve() == self._bundled.resolve():
                    verify_bundled_inventory(candidate)
                return load_inventory(candidate, cancel, progress)

            try:
                if backup_id is not None:
                    progress(0, "Restaurando base anterior")
                    data = load_backup(self._cache, backup_id, cancel)
                else:
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
            selected = self._default_selection(data, cancel)
            analysis = analyze_inventory(data, selected, cancel=cancel)
            monthly = analyze_monthly_inventory(data, selected, analysis=analysis, cancel=cancel)
            # No QObjects/models here: all work proportional to the full source is
            # complete before the GUI commits a generation's references.
            search = ProductSearch(
                SimpleNamespace(
                    products=_CheckedRows(data.products, cancel),
                    balances=_CheckedRows(data.balances, cancel),
                )
            )
            search.names = MappingProxyType(search.names)
            search.entries = tuple(search.entries)
            options = tuple(self._build_options(data, cancel))
            sales, closings = defaultdict(list), defaultdict(list)
            sales_begin = None
            for sale in _checked(data.sales, cancel):
                sales_begin = min(sales_begin, sale.day) if sales_begin else sale.day
                sales[(sale.product, sale.branch, sale.unit)].append(sale)
            for closing in _checked(data.closings, cancel):
                closings[(closing.product, closing.branch, closing.warehouse, closing.unit)].append(
                    closing
                )
            load = _LoadPresentation(
                search,
                options,
                sales_begin,
                MappingProxyType(
                    {key: tuple(rows) for key, rows in _checked(sales.items(), cancel)}
                ),
                MappingProxyType(
                    {key: tuple(rows) for key, rows in _checked(closings.items(), cancel)}
                ),
            )
            publication = _prepare_publication(
                "restore" if backup_id is not None else "load",
                data,
                selected,
                analysis,
                monthly,
                column,
                descending,
                "",
                "",
                search.names,
                cancel,
                load,
            )
            checkpoint(cancel)
            if staged:
                write_snapshot(data, staged, cancel)
                fingerprint = _cache_fingerprint(self._cache)
                backup = backup_previous(self._cache, staged, cancel)
                if fingerprint != _cache_fingerprint(self._cache):
                    raise ValueError(
                        "A base local foi alterada por outra operação. Abra a base novamente."
                    )
                publication = replace(
                    publication,
                    cache_fingerprint=fingerprint,
                    backup_id=backup.id if backup is not None else "",
                )
            entries, backup_error = _read_backup_items(self._cache, cancel)
            return replace(
                publication, load=replace(load, backups=entries, backup_error=backup_error)
            )

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
            or self._closed
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
        if self._thread:
            self._cancel.set()
        self._pending = True
        self._error = ""
        self._page = 1
        self._debounce.start()
        self.changed.emit()
        self.backupChanged.emit()

    @Slot()
    def resetFilters(self):
        if self._closed or self._data is None or self._task in {"load", "export"}:
            return
        self._selection = self._default
        self._generation += 1
        if self._thread:
            self._cancel.set()
        self._pending = True
        self._page = 1
        self._debounce.start()
        self.changed.emit()
        self.backupChanged.emit()

    def _schedule_analysis(self):
        if self._thread or self._data is None or self._closed:
            return
        self._pending = False
        data, selected = self._data, self._selection
        column, descending = self._sort, self._descending
        period, unit = self._monthly_period, self._monthly_unit
        names = self._search.names

        def action(cancel, progress):
            analysis = analyze_inventory(data, selected, cancel=cancel)
            checkpoint(cancel)
            monthly = analyze_monthly_inventory(data, selected, analysis=analysis, cancel=cancel)
            return _prepare_publication(
                "analysis",
                data,
                selected,
                analysis,
                monthly,
                column,
                descending,
                period,
                unit,
                names,
                cancel,
            )

        self._start(action, "analysis")

    def _start(self, action, task):
        self._cancel = Event()
        self._running_generation = self._generation
        self._task = task
        self._progress = 0
        self._label = (
            "Atualizando análise"
            if task in {"analysis", "sort"}
            else "Preparando Excel"
            if task == "export"
            else "Consultando bases anteriores"
            if task == "backups"
            else "Abrindo base"
        )
        if task != "backups":
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
        self.backupChanged.emit()

    @Slot(int, str)
    def _on_progress(self, value, label):
        self._progress, self._label = value, label
        self.changed.emit()

    @Slot(object)
    def _accept(self, result):
        if self._cancel.is_set() or self._running_generation != self._generation or self._closed:
            return
        if isinstance(result, tuple):
            if result[0] == "sort":
                self._ordered = result[1]
                self._applied_sort = result[2]
                self._publish_rows()
            elif result[0] == "backups":
                self._backup_entries, self._backup_error = result[1:]
                self._prune_preserve_ids.clear()
                self.backupChanged.emit()
            self.changed.emit()
            return
        if result.kind in {"load", "restore"}:
            # Commit only after preparation succeeded and this generation is live.
            if self._staged_cache is not None:
                try:
                    if _cache_fingerprint(self._cache) != result.cache_fingerprint:
                        raise ValueError(
                            "A base local foi alterada por outra operação. Abra a base novamente."
                        )
                    os.replace(self._staged_cache, self._cache)
                except (OSError, ValueError) as exc:
                    LOGGER.exception("Falha ao publicar a base de estoque")
                    self._fail(
                        str(exc)
                        if isinstance(exc, ValueError)
                        else "Não foi possível salvar a base de estoque. Verifique a permissão da pasta de dados da LIARTE."
                    )
                    return
                self._staged_cache = None
                self._prune_requested = True
                if result.backup_id:
                    self._prune_preserve_ids.add(result.backup_id)
            self._data = result.data
            self._selection = self._default = result.selected
            self._search = result.load.search
            self._options = result.load.options
            self._sales_begin = result.load.sales_begin
            self._sales_by_position = result.load.sales
            self._closings_by_position = result.load.closings
            self._page = 1
            self._backup_entries = result.load.backups
            self._backup_error = result.load.backup_error
            if result.kind == "restore":
                self._backup_notice = "Base anterior restaurada."
            self.backupChanged.emit()
            self.optionsChanged.emit()
        self._analysis = result.analysis
        self._monthly_data = result.monthly
        self._ordered = result.ordered
        self._applied_sort = result.sort
        self._monthly_display = result.monthly_display
        self._monthly_units = result.monthly_units
        self._monthly_view = result.monthly_view
        self._monthly_period, self._monthly_unit = result.period, result.unit
        self._applied_selection = result.selected
        self._publish_rows()
        self.monthlyChanged.emit()
        self.analysisChanged.emit()
        self.changed.emit()

    @Slot(str)
    def _fail(self, message):
        if self._running_generation == self._generation and not self._cancel.is_set():
            if self._task == "backups":
                self._backup_error = message
                self.backupChanged.emit()
                return
            if self._task == "sort":
                self._sort, self._descending = self._applied_sort
            self._error = message
            if self._restoring_backup:
                self._backup_error = message
                self.backupChanged.emit()
            self.changed.emit()

    @Slot()
    def _finished(self):
        thread = self._thread
        if thread is None:
            return
        # QThread.finished is emitted before native/TLS cleanup has necessarily
        # completed. Join before releasing the QObject tree or reporting a safe
        # shutdown; a queued signal alone does not establish that boundary.
        thread.wait()
        self._discard_staged_cache()
        self._thread = self._worker = None
        self._task = ""
        self._restoring_backup = False
        self._progress = 0
        self.changed.emit()
        self.backupChanged.emit()
        if self._closed:
            self._complete_shutdown()
        elif self._pending:
            self._debounce.start(0)
        elif self._prune_requested:
            self._refresh_backups(clear_notice=False)

    def _publish_rows(self):
        """Commit just one page; callers prepare the complete ordering separately."""
        if not self._analysis:
            return
        self._page = min(self._page, max(1, (len(self._ordered) + 49) // 50))
        self.table.setRows(self._ordered[(self._page - 1) * 50 : self._page * 50])
        self._selected_index = -1
        self._detail = {}
        self.detailChanged.emit()

    @Slot(int)
    def sortByColumn(self, column):
        if (
            not 0 <= column < len(HEADERS)
            or self._closed
            or self._thread
            or self._pending
            or self._debounce.isActive()
            or not self._analysis
        ):
            return
        self._descending = not self._descending if column == self._sort else column in (5, 6, 9, 10)
        self._sort = column
        self._page = 1
        rows, descending = self._analysis.rows, self._descending
        if len(rows) <= 50:
            # A single visible page is bounded GUI work and preserves immediate sorting.
            self._ordered = _order_rows(rows, column, descending)
            self._applied_sort = (column, descending)
            self._publish_rows()
        else:

            def action(cancel, progress):
                return ("sort", _order_rows(rows, column, descending, cancel), (column, descending))

            self._start(action, "sort")
        self.changed.emit()
        self.backupChanged.emit()

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
        monthly_sales = {
            p: 0
            if self._sales_begin is not None
            and month_end(p) >= self._sales_begin
            and date.fromisoformat(p + "-01") <= self._data.as_of
            else None
            for p in periods
        }
        for sale in self._sales_by_position.get((b.product, b.branch, b.unit), ()):
            if sale.day <= self._data.as_of:
                period = sale.day.strftime("%Y-%m")
                if period in monthly_sales and monthly_sales[period] is not None:
                    monthly_sales[period] += sale.quantity
        monthly_closings = {
            c.period: c
            for c in self._closings_by_position.get((b.product, b.branch, b.warehouse, b.unit), ())
        }
        monthly_giro = {period: closing.turnover for period, closing in monthly_closings.items()}
        self._detail = {
            "code": b.product,
            "unit": b.unit,
            "title": b.product + " · " + row.name,
            "location": "Filial " + b.branch + " · armazém " + b.warehouse,
            "balance": number(Decimal(b.quantity) / SCALE, 3) + " " + b.unit,
            "cost": money(b.cost),
            "sold": number(Decimal(row.sold) / SCALE, 3) + " " + b.unit + " · filial inteira",
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
                        or (
                            self._sales_begin is not None
                            and date.fromisoformat(p + "-01") < self._sales_begin <= month_end(p)
                        )
                        else ""
                    ),
                    "value": qty / SCALE if qty is not None else None,
                    "display": number(Decimal(qty) / SCALE, 3) + " " + b.unit
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
            "stockQuantityTrend": [
                {
                    "period": p,
                    "label": p[5:] + "/" + p[:4],
                    "value": monthly_closings[p].quantity / SCALE
                    if p in monthly_closings
                    else None,
                    "display": number(Decimal(monthly_closings[p].quantity) / SCALE, 3)
                    + " "
                    + b.unit
                    if p in monthly_closings
                    else "Sem fechamento",
                }
                for p in periods
            ],
            "stockCostTrend": [
                {
                    "period": p,
                    "label": p[5:] + "/" + p[:4],
                    "value": monthly_closings[p].cost / 100 if p in monthly_closings else None,
                    "display": money(monthly_closings[p].cost)
                    if p in monthly_closings
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
            or self._closed
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
        monthly = self._monthly_data

        def action(cancel, progress):
            export_inventory(data, analysis, selected, path, cancel, monthly=monthly)
            return ("export",)

        self._start(action, "export")

    @Slot()
    def cancel(self):
        self._pending = False
        self._debounce.stop()
        self._cancel.set()
        self._sort, self._descending = self._applied_sort
        if self._applied_selection is not None:
            self._selection = self._applied_selection
        self.changed.emit()
        self.backupChanged.emit()

    def shutdown(self, *, wait_ms=15000):
        """Return False while cooperative cancellation still owns a live QThread."""
        if self._shutdown_complete:
            return True
        self._closed = True
        self.cancel()
        thread = self._thread
        if thread is not None:
            thread.quit()
            if not thread.wait(wait_ms):
                # A QObject parent may be destroyed by a caller after shutdown.
                # Keep this independent tree and its staging file until finished.
                self.setParent(None)
                _SHUTTING_DOWN.add(self)
                return False
            # QThread.finished may still be queued in the GUI event loop.
            self._finished()
        else:
            self._complete_shutdown()
        return True

    def _complete_shutdown(self):
        if self._shutdown_complete:
            return
        self._discard_staged_cache()
        self._shutdown_complete = True
        self.backupChanged.emit()
        _SHUTTING_DOWN.discard(self)
        self.shutdownFinished.emit()

    def _discard_staged_cache(self):
        if self._staged_cache is not None:
            try:
                self._staged_cache.unlink(missing_ok=True)
            except OSError:
                LOGGER.warning("Não foi possível remover base temporária de estoque", exc_info=True)
            self._staged_cache = None
