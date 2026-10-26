"""Complete product rankings and the selected investigation for Excel."""

from __future__ import annotations

from dataclasses import asdict

from .inventory import SCALE
from .query import checkpoint

_MAX_ROWS = 1_048_576


def append_performance_sheets(workbook, report, detail, data, selection, cancel):
    from .inventory_export import _append_values, _excel_scaled

    layouts = {}
    headers = (
        "Código", "Produto", "UM", "Janela anterior", "Janela recente",
        "Vendas líquidas anteriores", "Vendas líquidas recentes", "Diferença nas vendas",
        "Variação (%)", "Situação", "Mês do fechamento", "Quantidade no fechamento",
        "Estoque a custo (R$)", "Giro fonte · mediana (x/mês)", "Posições elegíveis",
        "Cobertura estimada (dias)", "Disponibilidade da cobertura",
        "Variação estoque · posições pareadas", "Posições só no alvo",
        "Posições só na base", "Fonte", "Data da base", "Filtros", "Definição e limites",
    )
    widths = (18, 48, 12, 27, 27, 26, 26, 26, 20, 26, 22, 28, 27, 30, 22,
              28, 80, 35, 24, 24, 48, 18, 80, 100)
    filters = "; ".join(f"{key}={value}" for key, value in asdict(selection).items() if value)
    definition = (
        "Vendas líquidas por produto e unidade; janelas consecutivas de meses completos. "
        "Percentual apenas com base positiva, sem saldo líquido negativo. "
        "Ausência de fechamento não representa zero. Giro: mediana das posições elegíveis "
        "no fechamento-alvo; não é giro consolidado. Cobertura estimada ao ritmo registrado "
        "não mede idade de lote. A tabela inclui todos os produtos e unidades do recorte, "
        "independentemente da busca, ordenação e paginação da tela. "
        + str(report.get("reason", ""))
    )
    sheet, row_number, part = None, 0, 0
    for row in report.get("rows", ()):
        checkpoint(cancel)
        if sheet is None or row_number >= _MAX_ROWS:
            part += 1
            title = "Desempenho dos produtos" + (f" {part}" if part > 1 else "")
            sheet = workbook.create_sheet(title)
            sheet.append(headers)
            row_number = 1
            layouts[title] = widths
        row_number += 1
        status = {
            "insufficient": "Histórico insuficiente",
            "negative": "Saldo líquido negativo · confira devoluções",
            "no_positive": "Quantidade líquida zero",
            "resumed": "Sem quantidade líquida positiva na janela anterior",
            "up": "Quantidade líquida em alta", "down": "Quantidade líquida em queda",
            "stable": "Quantidade líquida estável",
        }.get(row.get("status"), "Histórico insuficiente")
        values = [
            row["code"], row["name"], row["unit"], report.get("baseLabel", ""),
            report.get("targetLabel", ""), _excel_scaled(row.get("previous"), SCALE),
            _excel_scaled(row.get("sold"), SCALE), _excel_scaled(row.get("change"), SCALE),
            row.get("percentage"), status, report.get("targetPeriod", ""),
            _excel_scaled(row.get("stockQuantity"), SCALE), _excel_scaled(row.get("stockCost"), 100),
            row.get("turnover"), row.get("turnoverCount"), row.get("coverage"),
            row.get("coverageReason", ""), _excel_scaled(row.get("matchedStockChange"), SCALE),
            row.get("addedCount"), row.get("missingCount"), data.source_name, data.as_of,
            filters, definition,
        ]
        _append_values(sheet, values, row_number)
        for column in (6, 7, 8, 12, 18):
            sheet.cell(row_number, column).number_format = "#,##0.000;[Red](#,##0.000)"
        for column in (9, 14, 16):
            sheet.cell(row_number, column).number_format = "0.00"
        sheet.cell(row_number, 13).number_format = '"R$" #,##0.00;[Red]("R$" #,##0.00)'
        sheet.cell(row_number, 22).number_format = "dd/mm/yyyy"
    if sheet is None:
        sheet = workbook.create_sheet("Desempenho dos produtos")
        sheet.append(headers)
        layouts[sheet.title] = widths
    if detail:
        sheet = workbook.create_sheet("Investigação do produto")
        sheet.append(("Categoria", "Informação"))
        layouts[sheet.title] = (30, 110)
        entries = [
            ("Produto", str(detail.get("code", "")) + " · " + str(detail.get("name", ""))),
            ("Unidade", detail.get("unit", "")), ("Abrangência", report.get("scope", "")),
            ("Janela anterior", report.get("baseLabel", "")),
            ("Janela recente", report.get("targetLabel", "")),
        ]
        for category, key in (("O que os dados mostram", "evidence"),
                              ("Hipótese a verificar", "hypotheses"),
                              ("Limite da análise", "limitations")):
            entries.extend((category, value) for value in detail.get(key, ()))
        for index, entry in enumerate(entries, 2):
            checkpoint(cancel)
            _append_values(sheet, list(entry), index)
    checkpoint(cancel)
    return layouts
