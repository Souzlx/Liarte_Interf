"""Complete Excel tables for an accepted two-month stock comparison."""

from __future__ import annotations

from dataclasses import asdict

from .inventory import SCALE
from .query import checkpoint

_MAX_ROWS = 1_048_576


def append_comparison_sheets(workbook, comparison, data, selection, cancel):
    """Write the complete comparison, retaining missing values and exact decimals.

    Monetary stock appears once, over all units in the selected scope. Quantity
    and sales each have separate rows/tables per original unit. Product and
    branch contributions are two views of the same change, never additive.
    """
    # Both writers are shared with the ordinary stock sheets. Import only when
    # invoked, after inventory_export has finished initializing its helpers.
    from .inventory_export import _append_values, _excel_scaled

    checkpoint(cancel)
    layouts = {}

    class Table:
        def __init__(self, title, headers, widths):
            self.title, self.headers, self.widths = title, headers, widths
            self.part = 0
            self.new_sheet()

        def new_sheet(self):
            self.part += 1
            title = self.title if self.part == 1 else f"{self.title} {self.part}"
            self.sheet = workbook.create_sheet(title)
            self.sheet.append(self.headers)
            self.row_number = 1
            layouts[title] = self.widths

        def append(self, values, scale, value_columns, date_column):
            checkpoint(cancel)
            if self.row_number >= _MAX_ROWS:
                self.new_sheet()
            self.row_number += 1
            _append_values(self.sheet, values, self.row_number)
            value_format = (
                '"R$" #,##0.00;[Red]("R$" #,##0.00)'
                if scale == 100
                else "#,##0.000;[Red](#,##0.000)"
            )
            for column in value_columns:
                self.sheet.cell(self.row_number, column).number_format = value_format
            self.sheet.cell(self.row_number, date_column).number_format = "dd/mm/yyyy"

    summary_table = Table(
        "Comparação mensal",
        (
            "Indicador", "UM", "Mês base", "Mês comparado", "Valor na base",
            "Valor no comparado", "Diferença observada", "Variação (%)",
            "Diferença pareada", "Valor só no comparado", "Valor só na base",
            "Posições pareadas", "Registros só no comparado", "Registros só na base",
            "Comparação disponível", "Motivo e abrangência", "Data da base", "Fonte",
            "Período do recorte", "Filtros", "Definição",
        ),
        (28, 12, 16, 18, 23, 23, 25, 20, 25, 26, 24, 22, 26, 24, 24, 90, 18, 48, 27, 80, 100),
    )
    contributions = Table(
        "Contribuições",
        (
            "Indicador", "Dimensão", "Código", "Nome", "UM", "Mês base",
            "Mês comparado", "Valor na base", "Valor no comparado",
            "Contribuição observada", "Diferença pareada", "Valor só no comparado",
            "Valor só na base", "Posições pareadas", "Registros só no comparado",
            "Registros só na base", "Data da base", "Período do recorte", "Filtros",
            "Definição",
        ),
        (28, 16, 18, 48, 12, 16, 18, 23, 23, 27, 25, 26, 24, 22, 26, 24, 18, 27, 80, 100),
    )
    scope = "; ".join(f"{key}={value}" for key, value in asdict(selection).items() if value)
    period = selection.start + " a " + selection.end
    base, target = comparison["base"], comparison["target"]
    stock_definition = (
        "Estoque a custo de todas as unidades do recorte. Contribuição observada = "
        "diferença das posições pareadas + valor dos registros só no comparado "
        "− valor dos registros só na base. Ausência de posição não é saldo zero. "
        "Registros novos ou ausentes não comprovam entradas ou saídas físicas. "
        "As dimensões Produto e Filial são perspectivas do mesmo total; não devem ser somadas."
    )
    quantity_definition = (
        "Quantidade de fechamento apenas na unidade indicada. Contribuição observada = "
        "diferença pareada + quantidade só no comparado − quantidade só na base. "
        "Ausência de posição não é saldo zero; alterações de registros não comprovam "
        "movimentos físicos. As dimensões Produto e Filial não devem ser somadas."
    )
    sales_definition = (
        "Vendas líquidas observadas da filial apenas na unidade indicada, sem atribuição "
        "a armazém. A ausência de uma transação em um mês completo observado contribui zero; "
        "um mês sem observação ou parcial não gera comparação. Variação não comprova "
        "sua causa. As dimensões Produto e Filial são perspectivas do mesmo total."
    )
    metrics = [("Estoque a custo", "R$", comparison["stock"], 100, stock_definition)]
    for unit in comparison["units"]:
        metrics.append((
            "Quantidade em estoque", unit, comparison["quantityByUnit"][unit],
            SCALE, quantity_definition,
        ))
        metrics.append((
            "Vendas líquidas", unit, comparison["salesByUnit"][unit], SCALE, sales_definition,
        ))
    for label, unit, metric, scale, definition in metrics:
        checkpoint(cancel)
        notes = " ".join(dict.fromkeys(
            str(metric.get(key) or "")
            for key in ("reason", "coverageNote", "scope")
            if metric.get(key)
        ))
        summary_table.append(
            [
                label, unit, base, target,
                _excel_scaled(metric["before"], scale),
                _excel_scaled(metric["after"], scale),
                _excel_scaled(metric["change"], scale),
                metric.get("percentage"),
                _excel_scaled(metric.get("matchedChange"), scale),
                _excel_scaled(metric.get("addedValue"), scale),
                _excel_scaled(metric.get("missingValue"), scale),
                metric.get("matchedCount"), metric.get("addedCount"), metric.get("missingCount"),
                "Sim" if metric["available"] else "Não", notes, data.as_of,
                data.source_name, period, scope, definition,
            ],
            scale, (5, 6, 7, 9, 10, 11), 17,
        )
        summary_table.sheet.cell(summary_table.row_number, 8).number_format = "0.00"
        for dimension, key in (("Produto", "products"), ("Filial", "branches")):
            for row in metric[key]:
                checkpoint(cancel)
                contributions.append(
                    [
                        label, dimension, row["key"], row["name"], unit, base, target,
                        _excel_scaled(row["before"], scale),
                        _excel_scaled(row["after"], scale),
                        _excel_scaled(row["change"], scale),
                        _excel_scaled(row.get("matchedChange"), scale),
                        _excel_scaled(row.get("addedValue"), scale),
                        _excel_scaled(row.get("missingValue"), scale),
                        row.get("matchedCount"), row.get("addedCount"), row.get("missingCount"),
                        data.as_of, period, scope, definition,
                    ],
                    scale, (8, 9, 10, 11, 12, 13), 17,
                )
    checkpoint(cancel)
    return layouts
