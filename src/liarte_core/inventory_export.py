"""Excel de estoque do recorte exibido, com unidades e regras explícitas."""

from __future__ import annotations

import os
import math
import tempfile
from dataclasses import asdict
from datetime import date
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


def _append_monthly_sheets(workbook, months, cancel):
    """Exporta todas as linhas mensais, sem limitar às classificações da tela.

    Resumos monetários ocupam uma única linha por mês; as quantidades ficam em
    linhas distintas por unidade para que não exista um total misturando KG/L/UN.
    """
    money_format = '"R$" #,##0.00;[Red]("R$" #,##0.00)'
    quantity_format = "#,##0.000;[Red](#,##0.000)"
    layouts = {}

    class Table:
        def __init__(self, title, headers, widths):
            self.title, self.headers, self.widths = title, headers, widths
            self.part = 0
            self.sheet = None
            self.new_sheet()

        def new_sheet(self):
            self.part += 1
            title = self.title if self.part == 1 else self.title + " " + str(self.part)
            self.sheet = workbook.create_sheet(title)
            self.sheet.append(self.headers)
            layouts[title] = self.widths

        def append(self, values, formats=()):
            checkpoint(cancel)
            # A base aceita até dois milhões de fatos. Dividir antes do limite
            # do XLSX conserva todas as linhas, inclusive nas bases maiores.
            if self.sheet.max_row >= 1_048_576:
                self.new_sheet()
            self.sheet.append(values)
            for column, fmt in formats:
                self.sheet.cell(self.sheet.max_row, column).number_format = fmt

    summary = Table(
        "Análise mensal",
        (
            "Mês",
            "Registro",
            "UM",
            "Estoque a custo (R$)",
            "Quantidade no fechamento",
            "Vendas das filiais (quantidade)",
            "Giro fonte · mediana (x/mês)",
            "Posições elegíveis para giro",
            "Giros inválidos · saldo positivo",
            "Produtos no fechamento",
            "Variação do custo · posições pareadas (R$)",
            "Variação total do custo (R$)",
            "Variação das vendas (quantidade)",
            "Vendas em mês parcial",
            "Posições novas",
            "Posições ausentes",
            "Abrangência dos fechamentos",
            "Abrangência das vendas",
            "Comparação do estoque",
            "Comparação das vendas",
            "Observações",
            "Fechamento em mês parcial",
            "Vendas observadas",
            "Custo dos registros novos (R$)",
            "Custo dos registros ausentes (R$)",
        ),
        (
            15,
            26,
            10,
            25,
            25,
            27,
            27,
            22,
            26,
            24,
            29,
            28,
            27,
            23,
            20,
            20,
            48,
            48,
            54,
            54,
            68,
            26,
            23,
            29,
            30,
        ),
    )
    changes = Table(
        "Variações mensais",
        ("Mês", "Comparação", "Análise", "UM", "Código", "Produto", "Variação", "Contexto"),
        (15, 20, 33, 10, 18, 52, 27, 90),
    )
    products = Table(
        "Produtos mensais",
        (
            "Mês",
            "Registro",
            "Código",
            "Produto",
            "Filial",
            "Armazém",
            "UM",
            "Quantidade no fechamento",
            "Vendas das filiais (quantidade)",
            "Estoque a custo (R$)",
            "Giro fonte (x/mês)",
            "Dias fonte",
            "Última venda observada",
            "Dias sem venda observada",
            "Observações",
        ),
        (15, 26, 18, 52, 14, 14, 10, 27, 30, 27, 23, 20, 25, 27, 90),
    )
    for month in months:
        period = month["period"]
        stock_cost = month["stockCost"]
        matched = month["matchedStockChange"]
        total_change = month["stockChange"]
        new_cost = month["newPositionCost"]
        missing_cost = month["missingPositionCost"]
        summary.append(
            [
                period,
                "Resumo mensal",
                None,
                stock_cost / 100 if stock_cost is not None else None,
                None,
                None,
                month["turnover"],
                month["turnoverCount"],
                month["turnoverInvalidCount"],
                month["productCount"],
                matched / 100 if matched is not None else None,
                total_change / 100 if total_change is not None else None,
                None,
                "Sim" if month["partial"] else "Não",
                month["newPositionCount"],
                month["missingPositionCount"],
                month["scope"],
                month["salesScope"],
                month["comparison"],
                month["salesComparison"],
                month["notice"],
                "Sim" if month["stockPartial"] else "Não",
                "Sim" if month["salesObserved"] else "Não",
                new_cost / 100 if new_cost is not None else None,
                missing_cost / 100 if missing_cost is not None else None,
            ],
            (
                (4, money_format),
                (7, "0.00"),
                (11, money_format),
                (12, money_format),
                (24, money_format),
                (25, money_format),
            ),
        )
        units = sorted(set(month["stockQuantity"]) | set(month["salesQuantity"]))
        for unit in units:
            quantity = month["stockQuantity"].get(unit)
            sold = month["salesQuantity"].get(unit)
            sales_change = month["salesChange"].get(unit)
            summary.append(
                [
                    period,
                    "Quantidade por unidade",
                    unit,
                    None,
                    quantity / SCALE if quantity is not None else None,
                    sold / SCALE if sold is not None else None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    sales_change / SCALE if sales_change is not None else None,
                ],
                ((5, quantity_format), (6, quantity_format), (13, quantity_format)),
            )
        changes.append(
            [
                period,
                month["previousLabel"],
                "Abrangência da comparação",
                None,
                None,
                None,
                None,
                f"{month['newPositionCount']} posições novas; "
                f"{month['missingPositionCount']} ausentes. "
                + month["comparison"]
                + " Registros ausentes não são presumidos como saldo zero.",
            ],
        )
        for item in month["changes"]:
            changes.append(
                [
                    period,
                    month["previousLabel"],
                    "Custo · posições pareadas",
                    None,
                    item["code"],
                    item["name"],
                    item["value"] / 100,
                    item["detail"],
                ],
                ((7, money_format),),
            )
        for unit, entries in sorted(month["salesChangesByUnit"].items()):
            for item in entries:
                changes.append(
                    [
                        period,
                        month["previousLabel"],
                        "Vendas das filiais",
                        unit,
                        item["code"],
                        item["name"],
                        item["value"] / SCALE,
                        item["detail"],
                    ],
                    ((7, quantity_format),),
                )
        for item in month["stockRows"]:
            # A recência é da filial/produto/unidade e usa o fim deste mês,
            # limitado à data da base; não atribuir a venda a um armazém.
            last_sale = item["lastSale"]
            products.append(
                [
                    period,
                    "Fechamento",
                    item["code"],
                    item["name"],
                    item["branch"],
                    item["warehouse"],
                    item["unit"],
                    item["quantity"] / SCALE,
                    None,
                    item["cost"] / 100,
                    item["turnover"],
                    item["days"],
                    date.fromisoformat(last_sale) if last_sale else None,
                    item["daysSinceSale"],
                    "Dias sem venda observada na filial; não medem idade física nem consumo interno. "
                    + ("Sem saída positiva observada até este mês." if not last_sale else ""),
                ],
                (
                    (8, quantity_format),
                    (10, money_format),
                    (11, "0.00"),
                    (12, "0.00"),
                    (13, "dd/mm/yyyy"),
                ),
            )
        for item in month["saleRows"]:
            products.append(
                [
                    period,
                    "Vendas da filial",
                    item["code"],
                    item["name"],
                    item["branch"],
                    None,
                    item["unit"],
                    None,
                    item["quantity"] / SCALE,
                    None,
                    None,
                    None,
                    None,
                    None,
                    "Vendas líquidas por filial e unidade, sem alocação por armazém. "
                    "Quantidade não representa consumo interno ou faturamento.",
                ],
                ((9, quantity_format),),
            )
    return layouts


def export_inventory(
    data: InventoryData,
    analysis: StockAnalysis,
    selection: StockSelection,
    path: Path,
    cancel: Event,
    *,
    monthly=None,
):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    from .inventory_monthly import analyze_monthly_inventory

    if monthly is None:
        monthly = analyze_monthly_inventory(data, selection, analysis=analysis)
    checkpoint(cancel)

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
        [
            "Mês",
            "UM",
            "Vendas por filial · produtos das posições atuais selecionadas · "
            "sem alocação por armazém",
            "Mês parcial",
        ]
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
    monthly_layouts = _append_monthly_sheets(workbook, monthly, cancel)
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
            "Vendas por filial · posições atuais",
            "A aba Vendas por filial considera somente produtos, filiais e unidades das posições "
            "ATUAIS selecionadas na aba Estoque. Produtos sem posição atual não entram nessa série. "
            "Com filtro de armazém, as posições atuais definem a coorte, mas suas vendas continuam "
            "sendo da filial inteira, pois a fonte não identifica o armazém da venda. "
            "A aba Análise mensal possui universo histórico próprio, descrito em Vendas mensais.",
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
        (
            "Análise mensal",
            "Estoque e giro pertencem ao fechamento de cada mês, sem reconstrução do saldo atual. "
            "O resumo monetário aparece uma vez por mês; quantidades ficam em linhas separadas por unidade. "
            "Produtos mensais inclui todas as posições históricas e todas as vendas da seleção, "
            "inclusive produtos sem saldo atual; não é limitado ao ranking exibido na tela.",
        ),
        (
            "Giro mediano mensal",
            "Mediana dos indicadores não negativos da fonte em posições com saldo positivo no mês. "
            "O número de posições elegíveis e os giros negativos são informados separadamente. "
            "Não é o giro consolidado da empresa nem é somado entre posições.",
        ),
        (
            "Variações mensais",
            "Compara meses consecutivos do período selecionado, sem pular lacunas. "
            "Contribuições de custo usam somente posições presentes nos dois fechamentos. "
            "Posições novas/ausentes são alterações de registros, não entradas/saídas físicas presumidas. "
            "A variação total corresponde à variação pareada mais o custo dos registros novos "
            "menos o custo dos registros ausentes. "
            "Contribuições indicam onde o valor variou; não comprovam compras, consumo, "
            "transferências, ajustes ou suas causas.",
        ),
        (
            "Vendas mensais",
            "Nas abas Análise mensal e Produtos mensais, a quantidade líquida vem dos registros "
            "históricos de produto, filial e unidade, inclusive produtos sem posição atual. "
            "ABC, atividade e saldo restringem esse universo à coorte atual selecionada, quando aplicados. "
            "Não há faturamento nesta análise. Sem atribuição a armazéns: o filtro de armazém "
            "indisponibiliza as vendas nessas duas abas, enquanto Vendas por filial mantém a série "
            "dos produtos das posições atuais selecionadas, com vendas da filial inteira. "
            "Meses sem cobertura ficam em branco; meses parciais são identificados e não geram comparação mensal.",
        ),
        (
            "Recência mensal",
            "Última saída positiva observada até o fim do mês, limitada à data da base, "
            "por produto/filial/unidade. Dias sem venda não medem idade física ou obsolescência. "
            "Consumo interno e histórico de entradas/lotes não estão disponíveis nesta base.",
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
        if ws.title in monthly_layouts:
            for column, width in enumerate(monthly_layouts[ws.title], 1):
                ws.column_dimensions[get_column_letter(column)].width = width
            ws.auto_filter.ref = f"A1:{get_column_letter(ws.max_column)}{ws.max_row}"
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
        if ws is sales:
            ws.row_dimensions[header_row].height = 60
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
