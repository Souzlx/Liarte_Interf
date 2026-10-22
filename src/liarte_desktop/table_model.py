"""Modelo de página Qt; nenhum acesso a rede e nenhuma agregação financeira."""

from __future__ import annotations

from decimal import Decimal
import re

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Property, Qt, QThread, Signal, Slot

from liarte_core.domain import ImportRecord, MunicipalRecord, number, period_label

HEADERS = (
    "Mês",
    "Produto",
    "NCM",
    "UF",
    "País",
    "Porto / URF",
    "FOB (US$)",
    "Frete (US$)",
    "Seguro (US$)",
    "CIF (US$)",
    "Peso (kg)",
    "US$/kg",
)


MUNICIPAL_HEADERS = (
    "Mês",
    "Município fiscal",
    "UF",
    "SH4",
    "Descrição SH4",
    "País",
    "FOB (US$)",
    "Peso (kg)",
    "US$/kg FOB",
)


def port_label(value: str) -> str:
    """Nome primeiro na interface; a chave oficial e os documentos não mudam."""
    match = re.fullmatch(r"\s*(\d{6,8})\s*[-–]\s*(.+?)\s*", value)
    return f"{match[2]} · {match[1]}" if match else value


def cells(row: ImportRecord) -> tuple[str, ...]:
    if isinstance(row, MunicipalRecord):
        return (
            period_label(row.period),
            row.city,
            row.state,
            row.heading,
            row.product,
            row.country,
            number(Decimal(row.fob_cents) / 100, 2),
            number(row.kg),
            number(row.unit_price, 3),
        )
    return (
        period_label(row.period),
        row.product,
        row.ncm,
        row.state,
        row.country,
        row.port,
        number(Decimal(row.fob_cents) / 100, 2),
        number(Decimal(row.freight_cents) / 100, 2),
        number(Decimal(row.insurance_cents) / 100, 2),
        number(Decimal(row.cif_cents) / 100, 2),
        number(row.kg),
        number(row.unit_price, 3),
    )


class ImportTableModel(QAbstractTableModel):
    columnsChanged = Signal()
    contentChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows: tuple[ImportRecord, ...] = ()
        self.headers = HEADERS
        self._display: tuple[tuple[str, ...], ...] = ()
        self._profile = "full"

    def _columns(self):
        municipal = self.headers == MUNICIPAL_HEADERS
        if self._profile == "buying":
            # O índice de origem continua sendo o contrato de ordenação do motor.
            return (0, 4, 1, 2, 5, 7, 8, 6) if municipal else (0, 1, 4, 3, 10, 11, 5, 9)
        return tuple(range(len(self.headers)))

    @Property("QVariantList", notify=columnsChanged)
    def viewColumns(self):
        municipal = self.headers == MUNICIPAL_HEADERS
        widths = (
            (150, 245, 55, 75, 360, 160, 145, 135, 120)
            if municipal
            else (150, 235, 103, 55, 145, 220, 135, 125, 125, 145, 135, 105)
        )
        if self._profile == "buying":
            widths = (
                (96, 190, 48, 75, 240, 140, 132, 118, 112)
                if municipal
                else (96, 210, 100, 48, 134, 190, 135, 125, 125, 132, 118, 112)
            )
        return [
            {
                "source": column,
                "label": self.headers[column],
                "width": widths[column],
                "numeric": column >= 6,
            }
            for column in self._columns()
        ]

    @Slot(str)
    def setProfile(self, profile: str):
        if profile not in ("buying", "full") or profile == self._profile:
            return
        if QThread.currentThread() != self.thread():
            raise RuntimeError("Atualização do modelo fora da thread visual.")
        self.beginResetModel()
        self._profile = profile
        self.endResetModel()
        self.columnsChanged.emit()
        self.contentChanged.emit()

    def replace(self, rows, kind="general"):
        if QThread.currentThread() != self.thread():
            raise RuntimeError("Atualização do modelo fora da thread visual.")
        rows = tuple(rows)
        display = tuple(cells(row) for row in rows)
        headers = MUNICIPAL_HEADERS if kind == "municipal" else HEADERS
        if headers != self.headers:
            # The general and municipal bases intentionally have different
            # schemas. Ordinary pagination/filtering keeps the same model.
            self.beginResetModel()
            self.rows, self._display, self.headers = rows, display, headers
            self.endResetModel()
            self.columnsChanged.emit()
            self.contentChanged.emit()
            return
        if rows == self.rows:
            return
        old_count, new_count = len(self.rows), len(rows)
        common = min(old_count, new_count)
        changed = [i for i in range(common) if self._display[i] != display[i]]
        if new_count < old_count:
            self.beginRemoveRows(QModelIndex(), new_count, old_count - 1)
            self.rows, self._display = self.rows[:common], self._display[:common]
            self.endRemoveRows()
        self.rows, self._display = rows[:common], display[:common]
        if changed:
            self.dataChanged.emit(
                self.index(changed[0], 0),
                self.index(changed[-1], self.columnCount() - 1),
                [int(Qt.ItemDataRole.DisplayRole), int(Qt.ItemDataRole.ToolTipRole)],
            )
        if new_count > old_count:
            self.beginInsertRows(QModelIndex(), old_count, new_count - 1)
            self.rows, self._display = rows, display
            self.endInsertRows()
        self.contentChanged.emit()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._columns())

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if (
            not index.isValid()
            or not 0 <= index.row() < len(self.rows)
            or not 0 <= index.column() < len(self._columns())
        ):
            return None
        column = self._columns()[index.column()]
        value = self._display[index.row()][column]
        if role == Qt.ItemDataRole.ToolTipRole:
            return value
        if role == Qt.ItemDataRole.DisplayRole:
            if column == 0 and self._profile == "buying":
                period = self.rows[index.row()].period
                return f"{period[5:]}/{period[:4]}"
            if column == 5 and self.headers == HEADERS:
                return port_label(value)
            return value
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if (
            role == Qt.ItemDataRole.DisplayRole
            and orientation == Qt.Orientation.Horizontal
            and 0 <= section < len(self._columns())
        ):
            return self.headers[self._columns()[section]]
        return None

    def roleNames(self):
        return {
            int(Qt.ItemDataRole.DisplayRole): b"display",
            int(Qt.ItemDataRole.ToolTipRole): b"originalText",
        }
