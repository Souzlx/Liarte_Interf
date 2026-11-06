"""Atomic numerical reconciliation reports, without running the source model."""

from __future__ import annotations

import json
import math
import os
from decimal import Decimal
from pathlib import Path
import tempfile
from threading import Event

from .query import checkpoint

_EXCEL_ROWS = 1_048_576
_MAX_ROWS = _EXCEL_ROWS
_HEADERS = (
    "Camada",
    "Produto",
    "Filial",
    "Armazém",
    "UM",
    "Dia",
    "Mês",
    "Indicador",
    "Escala",
    "Unidade do valor",
    "Valor fonte",
    "Valor aplicativo",
    "Diferença",
    "Presente na fonte",
    "Presente no aplicativo",
    "Estado",
)
_WIDTHS = (27, 24, 18, 18, 12, 16, 15, 30, 18, 20, 27, 27, 27, 24, 27, 24)
_DEFINITIONS = (
    (
        "Escopo",
        "Registros de estoque e saídas gravados no PBIX e os cálculos conferidos; "
        "não executa medidas DAX, expressões M, SQL ou atualizações do Power BI.",
    ),
    (
        "Chave",
        "Produto, filial, armazém quando aplicável, unidade e dia ou mês. "
        "Vendas não possuem armazém neste contrato.",
    ),
    (
        "Quantidade",
        "JSON conserva inteiros em milionésimos da unidade original. "
        "O Excel apresenta valores divididos pela escala indicada, sem somar unidades diferentes.",
    ),
    ("Custo", "JSON conserva centavos inteiros. O Excel apresenta reais; custo não é receita."),
    (
        "Diferença",
        "Valor do aplicativo menos valor da fonte. Só é calculada quando os dois "
        "valores numéricos estão disponíveis.",
    ),
    (
        "Ausência",
        "Presença do registro é informada separadamente. Campo vazio representa "
        "valor desconhecido; zero conhecido permanece numérico.",
    ),
    ("Giro e dias", "Indicadores originais por posição; não são somados entre posições."),
    (
        "Precisão Excel",
        "Valores além de 15 dígitos significativos ficam em texto decimal "
        "exato, com comentário na célula. O JSON conserva os inteiros originais.",
    ),
    (
        "Revisão",
        "Aprovação exige referências e datas compatíveis. O hash identifica "
        "a versão lida; não comprova consistência transacional de consultas SQL futuras.",
    ),
    (
        "Contagens",
        "Total = iguais + diferentes + ausentes + extras + desconhecidos. "
        "Ambos os valores desconhecidos não comprovam igualdade numérica.",
    ),
    (
        "Relatório",
        "As abas de diferenças contêm apenas divergências. O resumo contabiliza "
        "também as verificações iguais e desconhecidas, sem truncar diferenças.",
    ),
)


def _metadata(report, cancel):
    yield "Relatório", "format", report.get("format", "")
    yield "Relatório", "status", report.get("status", "")
    yield "Relatório", "comparable", report.get("comparable")

    def flatten(group, values, prefix=""):
        for key, value in values.items():
            checkpoint(cancel)
            name = prefix + str(key)
            if isinstance(value, dict):
                yield from flatten(group, value, name + ".")
            elif isinstance(value, (list, tuple)):
                yield group, name, json.dumps(value, ensure_ascii=False, allow_nan=False)
            else:
                yield group, name, value

    for name, label in (
        ("source", "Fonte"),
        ("app", "Aplicativo"),
        ("context", "Contexto"),
        ("checks", "Verificações"),
    ):
        values = report.get(name, {})
        if not isinstance(values, dict):
            raise ValueError("Metadados da reconciliação inválidos.")
        yield from flatten(label, values)
    for section, values in report.get("sections", {}).items():
        checkpoint(cancel)
        if not isinstance(values, dict):
            raise ValueError("Contagens da reconciliação inválidas.")
        yield from flatten("Camada · " + str(section), values)


def _excel_value(value, scale=1):
    from .inventory_export import _ExactText, _excel_scaled

    if type(scale) is not int or scale < 1 or str(scale).rstrip("0") != "1":
        raise ValueError("Escala inválida no relatório de reconciliação.")
    if value is None or isinstance(value, (str, bool)):
        return value
    if type(value) is int:
        return _excel_scaled(value, scale)
    if type(value) is float and scale == 1 and math.isfinite(value):
        decimal = Decimal(str(value))
        if len("".join(map(str, decimal.as_tuple().digits)).rstrip("0")) > 15:
            return _ExactText(format(decimal, "f"))
        return value
    raise ValueError("Valor inválido no relatório de reconciliação.")


def _append_literal(sheet, values, row):
    from .inventory_export import _append_values

    _append_values(sheet, values, row)
    for column, value in enumerate(values, 1):
        if isinstance(value, str):
            sheet.cell(row, column).data_type = "s"
            if sheet.cell(row, column).comment is not None:
                sheet.cell(row, column).number_format = "@"


def _write_excel(report, path, cancel):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from .inventory_export import _validate_staged_workbook

    book = Workbook()
    summary = book.active
    summary.title = "Resumo"
    _append_literal(summary, ("Grupo", "Campo", "Valor"), 1)
    for index, row in enumerate(_metadata(report, cancel), 2):
        checkpoint(cancel)
        if index > _EXCEL_ROWS:
            raise ValueError("Metadados da reconciliação excedem o limite do Excel.")
        _append_literal(summary, [row[0], row[1], _excel_value(row[2])], index)
    for letter, width in (("A", 30), ("B", 45), ("C", 100)):
        summary.column_dimensions[letter].width = width

    try:
        for field, title in (("totals", "Totais"), ("differences", "Diferenças")):
            part = 0
            sheet = None
            row_number = 0

            def new_data_sheet():
                nonlocal part, sheet, row_number
                part += 1
                sheet = book.create_sheet(title + (f" {part}" if part > 1 else ""))
                _append_literal(sheet, _HEADERS, 1)
                for column, width in enumerate(_WIDTHS, 1):
                    sheet.column_dimensions[get_column_letter(column)].width = width
                row_number = 1

            for difference in report.get(field, ()):
                checkpoint(cancel)
                if sheet is None or row_number >= _MAX_ROWS:
                    new_data_sheet()
                scale = difference.get("scale", 1)
                row_number += 1
                values = [
                    difference.get("section", ""),
                    difference.get("product", ""),
                    difference.get("branch", ""),
                    difference.get("warehouse", ""),
                    difference.get("unit", ""),
                    difference.get("day", ""),
                    difference.get("period", ""),
                    difference.get("metric", ""),
                    scale,
                    difference.get("valueUnit", ""),
                    _excel_value(difference.get("sourceValue"), scale),
                    _excel_value(difference.get("appValue"), scale),
                    _excel_value(difference.get("difference"), scale),
                    difference.get("sourcePresent"),
                    difference.get("appPresent"),
                    difference.get("status", ""),
                ]
                _append_literal(sheet, values, row_number)
                places = len(str(scale)) - 1
                number_format = "#,##0" + ("." + "0" * places if places else "")
                for column in (11, 12, 13):
                    cell = sheet.cell(row_number, column)
                    if cell.data_type != "s":
                        cell.number_format = number_format if scale != 1 else "General"
            if sheet is None:
                new_data_sheet()
        methodology = book.create_sheet("Metodologia")
        _append_literal(methodology, ("Campo", "Definição"), 1)
        for index, definition in enumerate(_DEFINITIONS, 2):
            _append_literal(methodology, definition, index)
        methodology.column_dimensions["A"].width = 28
        methodology.column_dimensions["B"].width = 115
        for current in book:
            checkpoint(cancel)
            current.freeze_panes = "A2"
            current.sheet_view.showGridLines = False
            current.auto_filter.ref = current.dimensions
            for cell in current[1]:
                cell.font = Font(name="Calibri", bold=True, color="FFFFFF")
                cell.fill = PatternFill("solid", fgColor="103F70")
            for row in current.iter_rows(min_row=2):
                checkpoint(cancel)
                for cell in row:
                    cell.alignment = Alignment(vertical="top", wrap_text=True)
            current.print_title_rows = "1:1"
        checkpoint(cancel)
        book.save(path)
        checkpoint(cancel)
        _validate_staged_workbook(path, cancel)
    finally:
        book.close()


def export_inventory_reconciliation(
    report: dict, path: Path, *, cancel=None, before_publish=None
) -> Path:
    """Publish one complete JSON/XLSX report; failure preserves the old file.

    JSON retains original integer scales. XLSX displays scaled numerical values
    and explicit units, marking exact decimal text beyond Excel's precision.
    The caller owns input/output collision checks when source files are used.
    """
    cancel = cancel if cancel is not None else Event()
    checkpoint(cancel)
    path = Path(path)
    suffix = path.suffix.casefold()
    if suffix not in (".json", ".xlsx"):
        raise ValueError("Selecione um relatório .json ou .xlsx.")
    if not isinstance(report, dict) or report.get("status") not in (
        "equal",
        "different",
        "not_comparable",
    ):
        raise ValueError("Relatório de reconciliação inválido.")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".reconciliacao-", suffix=suffix, dir=path.parent)
    os.close(descriptor)
    staging = Path(name)
    try:
        if suffix == ".json":
            encoder = json.JSONEncoder(ensure_ascii=False, allow_nan=False, indent=2)
            with staging.open("w", encoding="utf-8", newline="\n") as stream:
                for chunk in encoder.iterencode(report):
                    checkpoint(cancel)
                    stream.write(chunk)
                stream.write("\n")
        else:
            _write_excel(report, staging, cancel)
        checkpoint(cancel)
        if before_publish is not None:
            before_publish()
            checkpoint(cancel)
        os.replace(staging, path)
    finally:
        staging.unlink(missing_ok=True)
    return path
