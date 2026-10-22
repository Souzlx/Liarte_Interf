"""Excel de estoque do recorte exibido, com unidades e regras explícitas."""

from __future__ import annotations

import os
import math
import tempfile
from dataclasses import asdict
from pathlib import Path
from threading import Event

from .inventory import SCALE, InventoryData, StockAnalysis, StockSelection
from .query import checkpoint

HEADERS = (
    "Código",
    "Produto",
    "Grupo",
    "Filial",
    "Arm.",
    "UM",
    "Saldo",
    "Custo (R$)",
    "ABC",
    "Últ. venda",
    "Dias sem venda",
    "Giro fonte (x/mês)",
    "Dias fonte",
    "Mês giro",
    "Cobertura filial (d)",
    "CV vendas mensais",
)


def export_inventory(
    data: InventoryData,
    analysis: StockAnalysis,
    selection: StockSelection,
    path: Path,
    cancel: Event,
):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Estoque"
    sheet.append(["LIARTE · Estoque · Base " + data.as_of.strftime("%d/%m/%Y")])
    sheet.append(["Saldos atuais; período de vendas " + selection.start + " a " + selection.end])
    sheet.append(HEADERS)
    for row in analysis.rows:
        checkpoint(cancel)
        b = row.balance
        sheet.append(
            [
                b.product,
                row.name,
                row.group,
                b.branch,
                b.warehouse,
                b.unit,
                b.quantity / SCALE,
                b.cost / 100,
                row.abc,
                row.last_sale,
                row.days_since_sale,
                row.turnover,
                row.source_days,
                row.source_period or None,
                row.coverage,
                row.cv,
            ]
        )
        n = sheet.max_row
        for col in (7,):
            sheet.cell(n, col).number_format = "#,##0.000;[Red](#,##0.000)"
        sheet.cell(n, 8).number_format = '"R$" #,##0.00;[Red]("R$" #,##0.00)'
        sheet.cell(n, 10).number_format = "dd/mm/yyyy"
        for col in (12, 13, 15):
            sheet.cell(n, col).number_format = "0.00"
        sheet.cell(n, 16).number_format = "0.0%"
    sheet.freeze_panes = "C4"
    sheet.auto_filter.ref = f"A3:P{max(3, sheet.max_row)}"
    widths = (16, 50, 26, 12, 10, 9, 19, 22, 9, 15, 19, 21, 16, 15, 23, 23)
    for i, width in enumerate(widths, 1):
        sheet.column_dimensions[get_column_letter(i)].width = width
    history = workbook.create_sheet("Fechamentos")
    history.append(["Mês", "Custo (R$)", "Abrangência"])
    for point in analysis.trend:
        history.append(
            [
                point["period"],
                point["raw"] / 100 if point["raw"] is not None else None,
                analysis.historical_scope,
            ]
        )
        history.cell(history.max_row, 2).number_format = '"R$" #,##0.00'
    sales = workbook.create_sheet("Vendas por filial")
    sales.append(
        ["Mês", "UM", "Vendas das filiais do recorte · sem alocação por armazém", "Mês parcial"]
    )
    for point in analysis.sales_months:
        sales.append(
            [
                point["period"],
                point["unit"],
                point["quantity"] / SCALE if point["quantity"] is not None else None,
                "Sim" if point["partial"] else "Não",
            ]
        )
        sales.cell(sales.max_row, 3).number_format = "#,##0.000"
    rules = workbook.create_sheet("Leitura dos indicadores")
    rules.append(["Indicador", "Definição"])
    for entry in (
        ("Fonte", data.source_name),
        ("SHA-256 da fonte", data.source_hash),
        ("Data da base", data.as_of.isoformat()),
        ("Qualidade da fonte", " ".join(data.notes) or "Sem ocorrências na validação estrutural."),
        (
            "Giro fonte",
            "GiroEstoqueMensalQtd de Fact_Estoque, último fechamento da base; não é recalculado nem somado entre posições.",
        ),
        ("Dias fonte", "DiasEstoqueQtd da mesma posição e fechamento. Campo original do BI."),
        (
            "Cobertura filial",
            "Saldo de todas as posições da filial e produto / média diária de vendas na mesma unidade e período. Indisponível com filtro de armazém, saldo negativo ou sem vendas positivas. Inclui dias sem venda; não mede consumo interno.",
        ),
        (
            "CV",
            "Desvio padrão amostral / média das quantidades vendidas por mês completo. Mínimo de três meses; sem cálculo para média nula/negativa ou meses com quantidade líquida negativa.",
        ),
        (
            "Série de vendas",
            "Meses observados sem venda recebem zero. Meses anteriores à primeira venda da base ficam em branco. Meses de início/fim incompletos são identificados como parciais e não entram na média mensal, desvio padrão e CV.",
        ),
        (
            "Última venda",
            "Última data de saída com quantidade positiva até a data da base, por produto, filial e unidade; não é última movimentação de estoque.",
        ),
        (
            "ABC",
            "Participação no capital positivo do recorte antes de filtrar ABC/atividade/saldo: A até atingir 80%; B até 95%; C restante. O produto que cruza o limite permanece na classe anterior.",
        ),
        (
            "Fechamentos",
            "Meses ausentes permanecem em branco. Abrangência do histórico pode diferir do estoque atual; valores de meses diferentes não são somados como saldo.",
        ),
        (
            "Unidades",
            "Quantidades de unidades diferentes não são somadas. Valores a custo em reais; saldos negativos são preservados.",
        ),
        ("Recorte", "; ".join(f"{k}={v}" for k, v in asdict(selection).items() if v)),
    ):
        rules.append(entry)
    edge = Side(style="thin", color="E3E9EF")
    for ws in workbook:
        header_row = 3 if ws is sheet else 1
        if ws is not sheet:
            ws.column_dimensions["A"].width = 27
            ws.column_dimensions["B"].width = 88 if ws is rules else 24
            ws.column_dimensions["C"].width = 60
            ws.freeze_panes = "A2"
        for row in ws:
            checkpoint(cancel)
            for cell in row:
                if isinstance(cell.value, str):
                    cell.data_type = "s"  # Não interpretar descrições como fórmulas.
                cell.alignment = Alignment(vertical="center", wrap_text=True)
                cell.font = Font(name="Calibri", size=11, color="20334A")
                cell.border = Border(bottom=edge)
                if cell.row == header_row:
                    cell.fill = PatternFill("solid", fgColor="103F70")
                    cell.font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
            ws.row_dimensions[row[0].row].height = (
                34
                if ws is sheet
                else max(30, math.ceil(len(str(row[1].value or "")) / 78) * 15 + 12)
                if ws is rules
                else 25
            )
        ws.print_title_rows = f"{header_row}:{header_row}"
        ws.sheet_view.showGridLines = False
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".estoque-", suffix=".xlsx", dir=path.parent)
    os.close(fd)
    try:
        workbook.save(name)
        checkpoint(cancel)
        os.replace(name, path)
    finally:
        workbook.close()
        if os.path.exists(name):
            os.unlink(name)
