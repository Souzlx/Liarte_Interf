"""Modelo semântico declarativo: valores exatos e dimensões sem duplicar fatos.

Somente biblioteca padrão. As consultas M leem o Excel entregue ao usuário;
medidas explícitas definem a agregação e preservam o contexto de seleção.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import uuid
from .commercial_names import COMMERCIAL_NAMES_BY_NCM

MONEY = '"US$" #,##0.00'
MONEY_INT = '"US$" #,##0'
UNIT = '"US$" #,##0.000"/kg"'
MILLION = '"US$" #,##0.00" mi"'
KG = '#,##0" kg"'
TON = '#,##0.00" t"'
PERCENT = "0.0%;-0.0%;0.0%"
INTEGER = "#,##0"
AXIS_MILLION = "#,##0.0"


def quote(value: str) -> str:
    return (
        value
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value)
        else "'" + value.replace("'", "''") + "'"
    )


def lineage(*parts: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "liarte.comex.powerbi." + ".".join(parts)))


def property_text(value: str) -> str:
    """TMDL usa aspas duplicadas, não escapes JSON, nas propriedades citadas."""
    return '"' + value.replace('"', '""') + '"'


def mtext(value: str) -> str:
    return property_text(value.replace("#(", "#(#)("))


@dataclass(frozen=True)
class Column:
    name: str
    dtype: str = "string"
    fmt: str | None = None
    hidden: bool = False
    sort: str | None = None
    description: str = ""


@dataclass(frozen=True)
class Measure:
    name: str
    expression: str
    fmt: str | None = MONEY
    folder: str = "01. Valores"
    description: str = ""
    hidden: bool = False


@dataclass(frozen=True)
class Table:
    name: str
    columns: tuple[Column, ...]
    source: str
    description: str
    measures: tuple[Measure, ...] = ()
    hidden: bool = False


def _measure(name, expr, fmt=MONEY, folder="01. Valores", description="", hidden=False):
    return Measure(name, expr, fmt, folder, description, hidden)


def _top(name, table, column, ranking, result, fmt, count=10):
    return _measure(
        name,
        f"""VAR Atual = SELECTEDVALUE('{table}'[{column}])
VAR Origens = TOPN({count}, ALLSELECTED('{table}'[{column}]), [{ranking}], DESC, '{table}'[{column}], ASC)
RETURN IF(NOT ISINSCOPE('{table}'[{column}]) || CONTAINS(Origens, '{table}'[{column}], Atual), [{result}])""",
        fmt,
        "99. Apoio visual",
        hidden=True,
    )


def _mom(name, base, price=False):
    guard = "HASONEVALUE('NCM'[Código NCM]) && " if price else ""
    return _measure(
        name,
        f"""VAR MesAtual = MAX('Calendario'[Índice mês])
VAR Anterior = FILTER(ALLSELECTED('Calendario'), 'Calendario'[Índice mês] = MesAtual - 1)
VAR ValorAnterior = CALCULATE([{base}], REMOVEFILTERS('Calendario'), Anterior)
VAR Atual = CALCULATE([{base}], REMOVEFILTERS('Calendario'), 'Calendario'[Índice mês] = MesAtual)
RETURN IF({guard}COUNTROWS(Anterior) = 1 && NOT ISBLANK(Atual) && NOT ISBLANK(ValorAnterior), DIVIDE(Atual - ValorAnterior, ValorAnterior))""",
        PERCENT,
        "04. Evolução",
        "Compara o último mês em contexto com o anterior somente se ambos estão selecionados e têm dados.",
    )


def general_measures() -> tuple[Measure, ...]:
    items = [
        _measure(name, f"SUM('Importacoes'[{col}])", fmt, folder)
        for name, col, fmt, folder in (
            ("Valor CIF", "Valor US$ CIF", MONEY, "01. Valores"),
            ("Valor FOB", "US$ FOB", MONEY, "01. Valores"),
            ("Frete", "US$ Frete", MONEY, "01. Valores"),
            ("Seguro", "US$ Seguro", MONEY, "01. Valores"),
            ("Peso líquido (kg)", "Quilograma Líquido", KG, "02. Volume"),
        )
    ]
    items += [_measure("Peso Líquido (t)", "DIVIDE([Peso líquido (kg)], 1000)", TON, "02. Volume")]
    for name, numerator, guard in (
        ("CIF por kg", "Valor CIF", "[CIF sem peso]"),
        (
            "FOB por kg",
            "Valor FOB",
            "CALCULATE([Valor FOB], 'Importacoes'[Quilograma Líquido] = 0)",
        ),
        ("Frete por kg", "Frete", "CALCULATE([Frete], 'Importacoes'[Quilograma Líquido] = 0)"),
    ):
        items.append(
            _measure(
                name,
                f"IF(NOT ({guard} > 0), DIVIDE([{numerator}], [Peso líquido (kg)]))",
                UNIT,
                "03. Valores por kg",
                "Razão entre somas, ponderada pelo peso. Indisponível se há valor sem peso no recorte.",
            )
        )
    items += [
        _measure("Custo Logístico", "[Frete] + [Seguro]"),
        _measure(
            "Custo Logístico % FOB",
            "DIVIDE([Custo Logístico], [Valor FOB])",
            PERCENT,
            "05. Logística",
        ),
        _measure(
            "Custo Logístico % CIF",
            "DIVIDE([Custo Logístico], [Valor CIF])",
            PERCENT,
            "05. Logística",
        ),
        _measure("Índice CIF/FOB", "DIVIDE([Valor CIF], [Valor FOB])", '0.000"x"', "05. Logística"),
    ]
    for name, column in [
        ("NCMs ativos", "Código NCM"),
        ("Países de origem", "Países"),
        ("UFs do produto", "UF do Produto"),
    ]:
        items.append(
            _measure(
                name,
                f"COALESCE(DISTINCTCOUNT('Importacoes'[{column}]), 0)",
                INTEGER,
                "06. Cobertura",
            )
        )
    items += [
        _measure(
            "Registros estatísticos",
            "COALESCE(COUNTROWS('Importacoes'), 0)",
            INTEGER,
            "06. Cobertura",
            "Agregações mensais; não são pedidos, fornecedores ou declarações individuais.",
        ),
        _measure(
            "CIF médio por registro",
            "DIVIDE([Valor CIF], [Registros estatísticos])",
            MONEY,
            "06. Cobertura",
            "Média por agregação estatística, não valor médio de um pedido.",
        ),
        _measure(
            "Produtos ativos",
            """VAR Movimentos = VALUES('Importacoes'[Código NCM])
RETURN COUNTROWS(CALCULATETABLE(VALUES('ProdutoNCM'[Produto]), KEEPFILTERS(TREATAS(Movimentos, 'ProdutoNCM'[Código NCM]))))""",
            INTEGER,
            "06. Cobertura",
        ),
    ]
    for name, base in [
        ("CIF (US$ mi)", "Valor CIF"),
        ("FOB (US$ mi)", "Valor FOB"),
        ("Frete (US$ mi)", "Frete"),
        ("Seguro (US$ mi)", "Seguro"),
    ]:
        items.append(
            _measure(name, f"DIVIDE([{base}], 1000000)", MILLION, "08. Escalas de apresentação")
        )
    for name, base in (
        ("CIF gráfico (mi)", "CIF (US$ mi)"),
        ("Frete gráfico (mi)", "Frete (US$ mi)"),
    ):
        items.append(
            _measure(
                name,
                f"[{base}]",
                AXIS_MILLION,
                "99. Apoio visual",
                "Escala em milhões indicada no título do gráfico; tooltip preserva o valor integral.",
                True,
            )
        )
    for base in ("CIF por kg", "FOB por kg", "Frete por kg"):
        items.append(
            _measure(
                base + " comparável",
                f"IF(HASONEVALUE('NCM'[Código NCM]), [{base}])",
                UNIT,
                "03. Valores por kg",
                "Disponível com um único NCM; evita comparar preços de misturas de produtos.",
            )
        )
    items.append(
        _measure(
            "CIF por kg MM3",
            """VAR MesAtual = MAX('Calendario'[Índice mês])
VAR Janela = FILTER(ALLSELECTED('Calendario'), 'Calendario'[Índice mês] >= MesAtual - 2 && 'Calendario'[Índice mês] <= MesAtual)
VAR MesesComPeso = CALCULATE(COUNTROWS(FILTER(VALUES('Calendario'[Data]), [Peso líquido (kg)] > 0)), REMOVEFILTERS('Calendario'), Janela)
RETURN IF(HASONEVALUE('NCM'[Código NCM]) && COUNTROWS(Janela) = 3 && MesesComPeso = 3, CALCULATE([CIF por kg], REMOVEFILTERS('Calendario'), Janela))""",
            UNIT,
            "04. Evolução",
            "Preço ponderado de três meses consecutivos selecionados com peso em todos eles; não é previsão.",
        )
    )
    items += [
        _mom("CIF por kg vs mês anterior", "CIF por kg", True),
        _mom("CIF vs mês anterior", "Valor CIF"),
    ]
    items += [
        _measure(
            "CIF por kg último mês",
            """VAR Ultimo = MAXX(ALLSELECTED('Calendario'), 'Calendario'[Índice mês])
RETURN CALCULATE([CIF por kg comparável], REMOVEFILTERS('Calendario'), 'Calendario'[Índice mês] = Ultimo)""",
            UNIT,
            "04. Evolução",
        ),
        _measure(
            "Registros sem peso",
            "COALESCE(CALCULATE(COUNTROWS('Importacoes'), 'Importacoes'[Quilograma Líquido] = 0), 0)",
            INTEGER,
            "07. Qualidade",
        ),
        _measure(
            "CIF sem peso",
            "CALCULATE([Valor CIF], 'Importacoes'[Quilograma Líquido] = 0)",
            MONEY,
            "07. Qualidade",
        ),
        _measure(
            "Participação CIF por país",
            "DIVIDE([Valor CIF], CALCULATE([Valor CIF], ALLSELECTED('Paises'[País])))",
            PERCENT,
            "06. Cobertura",
        ),
        _measure(
            "Participação CIF por NCM",
            "DIVIDE([Valor CIF], CALCULATE([Valor CIF], ALLSELECTED('NCM')))",
            PERCENT,
            "06. Cobertura",
        ),
        _measure(
            "Contexto de preços",
            """SWITCH(TRUE(),
[Registros estatísticos] = 0, "Sem registros para os filtros selecionados.",
NOT HASONEVALUE('NCM'[Código NCM]), "Selecione um único NCM no filtro Produto / NCM para comparar preços e origens.",
[CIF sem peso] > 0, "Há CIF sem peso publicado: US$/kg fica indisponível nos recortes afetados.",
HASONEVALUE('NCM'[Código NCM]), SELECTEDVALUE('NCM'[Produto / NCM]) & " · US$/kg ponderado · MM3 exige 3 meses consecutivos selecionados.",
"Selecione um NCM ou produto do cadastro para comparar valores por kg.")""",
            None,
            "09. Orientação",
        ),
    ]
    for suffix, table, column in [("Países", "Paises", "País"), ("NCMs", "NCM", "Produto / NCM")]:
        items.append(
            _measure(
                "Concentração Top 5 " + suffix,
                f"""VAR Principais = TOPN(5, ALLSELECTED('{table}'), [Valor CIF], DESC, '{table}'[{column}], ASC)
RETURN DIVIDE(SUMX(Principais, [Valor CIF]), CALCULATE([Valor CIF], ALLSELECTED('{table}')))""",
                PERCENT,
                "06. Cobertura",
                "Participação das cinco maiores origens ou NCMs dentro da seleção atual.",
            )
        )
    items += [
        _top("CIF top NCM", "NCM", "Produto / NCM", "Valor CIF", "CIF (US$ mi)", AXIS_MILLION),
        _top("CIF top países", "Paises", "País", "Valor CIF", "CIF (US$ mi)", AXIS_MILLION),
        _top(
            "CIF top URFs", "URFs", "Unidade aduaneira", "Valor CIF", "CIF (US$ mi)", AXIS_MILLION
        ),
        _top(
            "Logística top países", "Paises", "País", "Valor CIF", "Custo Logístico % FOB", PERCENT
        ),
        _top(
            "CIF por origem relevante",
            "Paises",
            "País",
            "Peso líquido (kg)",
            "CIF por kg comparável",
            UNIT,
        ),
    ]
    return tuple(items)


def municipal_measures() -> tuple[Measure, ...]:
    return (
        _measure("Valor FOB Municipal", "SUM('Municipios'[US$ FOB])"),
        _measure("Peso municipal (kg)", "SUM('Municipios'[Quilograma Líquido])", KG, "02. Volume"),
        _measure("Peso Municipal (t)", "DIVIDE([Peso municipal (kg)], 1000)", TON, "02. Volume"),
        _measure(
            "FOB Municipal por kg",
            "IF(NOT (CALCULATE([Valor FOB Municipal], 'Municipios'[Quilograma Líquido] = 0) > 0), DIVIDE([Valor FOB Municipal], [Peso municipal (kg)]))",
            UNIT,
            "03. Valores por kg",
            "Razão ponderada no universo municipal SH4 selecionado; não identifica o NCM8.",
        ),
        _measure(
            "Municípios ativos",
            "COALESCE(DISTINCTCOUNT('Municipios'[Chave município]), 0)",
            INTEGER,
            "06. Cobertura",
            "Município + UF; cidades homônimas em estados distintos permanecem separadas.",
        ),
        _measure(
            "Posições SH4 ativas",
            "COALESCE(DISTINCTCOUNT('Municipios'[Código SH4]), 0)",
            INTEGER,
            "06. Cobertura",
        ),
        _measure(
            "Países de origem municipais",
            "COALESCE(DISTINCTCOUNT('Municipios'[Países]), 0)",
            INTEGER,
            "06. Cobertura",
        ),
        _measure(
            "Registros estatísticos municipais",
            "COALESCE(COUNTROWS('Municipios'), 0)",
            INTEGER,
            "06. Cobertura",
        ),
        _measure(
            "FOB municipal (US$ mi)",
            "DIVIDE([Valor FOB Municipal], 1000000)",
            MILLION,
            "08. Escalas de apresentação",
        ),
        _measure(
            "Registros municipais sem peso",
            "COALESCE(CALCULATE(COUNTROWS('Municipios'), 'Municipios'[Quilograma Líquido] = 0), 0)",
            INTEGER,
            "07. Qualidade",
        ),
        _measure(
            "FOB municipal gráfico (mi)",
            "[FOB municipal (US$ mi)]",
            AXIS_MILLION,
            "99. Apoio visual",
            "Escala em milhões indicada no título.",
            True,
        ),
        _top(
            "FOB top municípios",
            "MunicipiosFiscais",
            "Município / UF",
            "Valor FOB Municipal",
            "FOB municipal (US$ mi)",
            AXIS_MILLION,
            8,
        ),
        _top(
            "FOB top SH4",
            "SH4",
            "Código SH4",
            "Valor FOB Municipal",
            "FOB municipal (US$ mi)",
            AXIS_MILLION,
            8,
        ),
    )


def _base_query(municipal=False):
    prefix, legacy = (
        ("Base municipal", "Import_Municipios") if municipal else ("Base geral", "Import_Full")
    )
    pairs = (
        [
            ("UF", "UF do Município"),
            ("SH4", "Código SH4"),
            ("Descrição", "Descrição SH4"),
            ("País", "Países"),
            ("FOB", "US$ FOB"),
            ("Peso líq.", "Quilograma Líquido"),
            ("Produtos", "Produtos relacionados"),
            ("NCMs", "NCMs relacionados"),
            ("FOB/kg", "US$ FOB/kg"),
        ]
        if municipal
        else [
            ("NCM", "Código NCM"),
            ("Descrição", "Descrição NCM"),
            ("UF", "UF do Produto"),
            ("País", "Países"),
            ("FOB", "US$ FOB"),
            ("Frete", "US$ Frete"),
            ("Seguro", "US$ Seguro"),
            ("CIF", "Valor US$ CIF"),
            ("Peso líq.", "Quilograma Líquido"),
            ("Produtos", "Produtos relacionados"),
            ("CIF/kg", "US$ CIF/kg"),
        ]
    )
    renames = "{" + ", ".join("{" + mtext(a) + ", " + mtext(b) + "}" for a, b in pairs) + "}"
    code_col = "Código SH4" if municipal else "Código NCM"
    size = 4 if municipal else 8
    money = ["US$ FOB"] if municipal else ["US$ FOB", "US$ Frete", "US$ Seguro", "Valor US$ CIF"]
    texts = (
        [
            "Município fiscal",
            "UF do Município",
            "Descrição SH4",
            "Países",
            "Produtos relacionados",
            "NCMs relacionados",
        ]
        if municipal
        else ["Descrição NCM", "UF do Produto", "URF", "Países", "Produtos relacionados"]
    )
    transforms = [
        "{" + mtext(c) + ", each Currency.From(fxNumero(_)), Currency.Type}" for c in money
    ]
    transforms += [
        "{" + mtext(c) + ', each if _ = null then "" else Text.Trim(Text.From(_)), type text}'
        for c in texts
    ]
    transforms += [
        '{"Mês", each if Value.Is(_, type number) and (Number.IsNaN(_) or _ = #infinity or _ = -#infinity or Number.RoundDown(_) <> _) then error "Mês numérico deve ser inteiro." else if _ = null then "" else Text.Trim(Text.From(_, "en-US")), type text}',
        "{" + mtext(code_col) + f", each fxCodigo(_, {size}), type text}}",
        '{"Quilograma Líquido", each let n = fxNumero(_) in if Number.RoundDown(n) <> n then error "Peso fracionário incompatível." else Int64.From(n), Int64.Type}',
    ]
    if municipal:
        extra = """,
    ComChave = Table.AddColumn(ComIndice, "Chave município", each [Município fiscal] & "|" & [UF do Município], type text),
    ComRotulo = Table.AddColumn(ComChave, "Município / UF", each if Text.EndsWith([Município fiscal], " - " & [UF do Município], Comparer.OrdinalIgnoreCase) then [Município fiscal] else [Município fiscal] & " - " & [UF do Município], type text),
    ComPreco = Table.AddColumn(ComRotulo, "US$ FOB/kg", each if [Quilograma Líquido] = 0 then null else [#"US$ FOB"] / [Quilograma Líquido], type number)"""
    else:
        extra = """,
    ComNome = Table.AddColumn(ComIndice, "Nome comercial", each Record.FieldOrDefault(NomesComerciais, [Código NCM], "NCM " & [Código NCM]), type text),
    ComPreco = Table.AddColumn(ComNome, "US$ CIF/kg", each if [Quilograma Líquido] = 0 then null else [#"Valor US$ CIF"] / [Quilograma Líquido], type number)"""
    # Precomputed Excel display ratios are ignored; only values and kg feed
    # the model's per-record ratio. No rounding is applied here.
    price_column = "US$ FOB/kg" if municipal else "US$ CIF/kg"
    return f"""let
    Atuais = Table.SelectRows(FonteExcel, each [Kind] = "Sheet" and Text.StartsWith([Item], {mtext(prefix)})),
    Legadas = Table.SelectRows(FonteExcel, each [Kind] = "Sheet" and Text.StartsWith([Item], {mtext(legacy)})),
    Abas = if Table.RowCount(Atuais) > 0 then Atuais else Legadas,
    Combinada = if Table.RowCount(Abas) = 0 then error "Aba {prefix} ausente." else Table.Combine(List.Transform(Abas[Data], each Table.PromoteHeaders(_, [PromoteAllScalars=true]))),
    Normalizada = Table.RenameColumns(Combinada, {renames}, MissingField.Ignore),
    SemPreco = Table.RemoveColumns(Normalizada, {{{mtext(price_column)}}}, MissingField.Ignore),
    Tipos = Table.TransformColumns(SemPreco, {{{", ".join(transforms)}}}),
    ComData = Table.AddColumn(Tipos, "Data", each fxDataMes([Mês]), type date),
    ComIndice = Table.AddColumn(ComData, "Índice mês", each Date.Year([Data]) * 12 + Date.Month([Data]), Int64.Type){extra}
in
    ComPreco"""


def expressions(start: str, end: str) -> tuple[tuple[str, str, str], ...]:
    return (
        (
            "CaminhoArquivoExcel",
            mtext("__LIARTE_EXCEL_PATH__")
            + ' meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]',
            "Text",
        ),
        (
            "PeriodoInicial",
            mtext(start)
            + ' meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]',
            "Text",
        ),
        (
            "PeriodoFinal",
            mtext(end)
            + ' meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]',
            "Text",
        ),
        ("FonteExcel", "Excel.Workbook(File.Contents(CaminhoArquivoExcel), null, true)", "Table"),
        (
            "fxDataMes",
            """(valor as any) as date =>
let
    Prefixo = Text.BeforeDelimiter(Text.Trim(Text.From(valor)) & ".", "."),
    Partes = Text.Split(Prefixo, "-"),
    Ano = if List.Count(Partes) = 2 then Number.FromText(Partes{0}, "en-US") else if Text.Start(PeriodoInicial, 4) = Text.Start(PeriodoFinal, 4) then Number.FromText(Text.Start(PeriodoInicial, 4), "en-US") else error "Mês sem ano em período de vários anos.",
    Mes = Number.FromText(List.Last(Partes), "en-US"),
    Data = #date(Ano, Mes, 1),
    Inicio = Date.FromText(PeriodoInicial & "-01", [Format="yyyy-MM-dd", Culture="en-US"]),
    Fim = Date.FromText(PeriodoFinal & "-01", [Format="yyyy-MM-dd", Culture="en-US"])
in
    if Data < Inicio or Data > Fim then error "Mês fora do período do relatório." else Data""",
            "Function",
        ),
        (
            "fxNumero",
            """(valor as any) as number =>
    if valor = null or not Value.Is(valor, type number) then error "Valor numérico ausente ou textual."
    else if Number.IsNaN(valor) or valor < 0 or valor = #infinity then error "Valor negativo ou não finito."
    else valor""",
            "Function",
        ),
        (
            "fxCodigo",
            """(valor as any, tamanho as number) as text =>
let
    Texto = if valor = null then "" else Text.Trim(Text.From(valor, "en-US")),
    Digitos = Text.Select(Texto, {"0".."9"})
in
    if Texto = "" or Digitos <> Texto or Text.Length(Texto) > tamanho then error "Código fiscal inválido."
    else Text.PadStart(Texto, tamanho, "0")""",
            "Function",
        ),
        (
            "CadastroProdutos",
            """let
    Nome = if List.Contains(FonteExcel[Item], "Produtos") then "Produtos" else "NCM_Produtos",
    Aba = FonteExcel{[Item=Nome, Kind="Sheet"]}[Data],
    Cabecalhos = Table.PromoteHeaders(Aba, [PromoteAllScalars=true]),
    Renomeada = Table.RenameColumns(Cabecalhos, {{"NCM", "Código NCM"}}, MissingField.Ignore),
    Colunas = Table.SelectColumns(Renomeada, {"Produto", "Código NCM"}),
    Tipos = Table.TransformColumns(Colunas, {{"Produto", each if _ = null or Text.Trim(Text.From(_)) = "" then error "Produto ausente." else Text.Trim(Text.From(_)), type text}, {"Código NCM", each fxCodigo(_, 8), type text}})
in
    Table.Distinct(Tipos)""",
            "Table",
        ),
        ("BaseGeral", _base_query(), "Table"),
        ("BaseMunicipal", _base_query(True), "Table"),
        (
            "NomesComerciais",
            "["
            + ", ".join(
                "#" + mtext(k) + "=" + mtext(v) for k, v in sorted(COMMERCIAL_NAMES_BY_NCM.items())
            )
            + "]",
            "Record",
        ),
    )


def tables() -> tuple[Table, ...]:
    general_cols = (
        Column("Data", "dateTime", "mmm/yyyy", True),
        Column("Índice mês", "int64", hidden=True),
        Column("Mês", hidden=True),
        Column("Código NCM", hidden=True),
        Column("Descrição NCM"),
        Column("Nome comercial", hidden=True),
        Column(
            "US$ CIF/kg",
            "double",
            UNIT,
            True,
            description="Razão da linha estatística; sem agregação implícita. Vazio quando kg = 0.",
        ),
        Column("UF do Produto", hidden=True),
        Column("URF", hidden=True),
        Column("Países", hidden=True),
        Column("Produtos relacionados"),
        *(
            Column(c, "decimal", MONEY, True)
            for c in ("US$ FOB", "US$ Frete", "US$ Seguro", "Valor US$ CIF")
        ),
        Column("Quilograma Líquido", "int64", KG, True),
    )
    municipal_cols = (
        Column("Data", "dateTime", "mmm/yyyy", True),
        Column("Índice mês", "int64", hidden=True),
        Column("Mês", hidden=True),
        Column("Chave município", hidden=True),
        Column("Município / UF", hidden=True),
        Column(
            "US$ FOB/kg",
            "double",
            UNIT,
            True,
            description="Razão da linha estatística municipal; vazio quando kg = 0.",
        ),
        *(
            Column(c)
            for c in (
                "Município fiscal",
                "UF do Município",
                "Código SH4",
                "Descrição SH4",
                "Países",
                "Produtos relacionados",
                "NCMs relacionados",
            )
        ),
        Column("US$ FOB", "decimal", MONEY, True),
        Column("Quilograma Líquido", "int64", KG, True),
    )
    return (
        Table(
            "Importacoes",
            general_cols,
            "BaseGeral",
            "Dados gerais por mês, NCM8, UF do produto, URF e país. Agregações estatísticas.",
            general_measures(),
        ),
        Table(
            "Municipios",
            municipal_cols,
            "BaseMunicipal",
            "Universo municipal SH4 por domicílio fiscal. Não somar aos dados gerais.",
            municipal_measures(),
        ),
        Table(
            "Calendario",
            (
                Column("Data", "dateTime", "mmm/yyyy", True),
                Column("Período", sort="Índice mês"),
                Column("Índice mês", "int64", hidden=True),
                Column("Ano", "int64"),
            ),
            """let
    Inicio = Date.FromText(PeriodoInicial & "-01", [Format="yyyy-MM-dd", Culture="en-US"]),
    Fim = Date.FromText(PeriodoFinal & "-01", [Format="yyyy-MM-dd", Culture="en-US"]),
    Meses = List.Generate(() => Inicio, each _ <= Fim, each Date.AddMonths(_, 1)),
    Datas = Table.FromList(Meses, Splitter.SplitByNothing(), {"Data"}),
    Tipos = Table.TransformColumnTypes(Datas, {{"Data", type date}}),
    Rotulo = Table.AddColumn(Tipos, "Período", each Date.ToText([Data], [Format="MMM/yyyy", Culture="pt-BR"]), type text),
    Indice = Table.AddColumn(Rotulo, "Índice mês", each Date.Year([Data]) * 12 + Date.Month([Data]), Int64.Type),
    Ano = Table.AddColumn(Indice, "Ano", each Date.Year([Data]), Int64.Type)
in
    Ano""",
            "Calendário mensal completo, incluindo meses sem movimento. Não é uma tabela diária.",
        ),
        Table(
            "ProdutoNCM",
            (Column("Produto"), Column("Código NCM")),
            "CadastroProdutos",
            "Ponte de relações únicas entre produto e NCM. Seleções usam união sem duplicar fatos.",
            hidden=True,
        ),
        Table(
            "Produtos",
            (Column("Produto"),),
            'Table.Sort(Table.Distinct(Table.SelectColumns(CadastroProdutos, {"Produto"})), {{"Produto", Order.Ascending}})',
            "Produtos do cadastro; um NCM pode corresponder a vários produtos.",
        ),
        Table(
            "NCM",
            (Column("Código NCM"), Column("Nome comercial"), Column("Produto / NCM")),
            """let
    Codigos = Table.Distinct(Table.Combine({Table.SelectColumns(BaseGeral, {"Código NCM"}), Table.SelectColumns(CadastroProdutos, {"Código NCM"})})),
    Nomes = Table.AddColumn(Codigos, "Nome comercial", each Record.FieldOrDefault(NomesComerciais, [Código NCM], "NCM " & [Código NCM]), type text),
    Rotulo = Table.AddColumn(Nomes, "Produto / NCM", each [Nome comercial] & " · " & [Código NCM], type text)
in
    Table.Sort(Rotulo, {{"Produto / NCM", Order.Ascending}})""",
            "NCM8 único com nome comercial e descrição oficial preservada na base detalhada.",
        ),
        Table(
            "Paises",
            (Column("País"),),
            """let
    Uniao = Table.Combine({Table.SelectColumns(BaseGeral, {"Países"}), Table.SelectColumns(BaseMunicipal, {"Países"})}),
    Renomeada = Table.RenameColumns(Uniao, {{"Países", "País"}})
in
    Table.Sort(Table.Distinct(Renomeada), {{"País", Order.Ascending}})""",
            "País de origem; não identifica o fornecedor.",
        ),
        Table(
            "UFs",
            (Column("UF"),),
            """let
    Geral = Table.RenameColumns(Table.SelectColumns(BaseGeral, {"UF do Produto"}), {{"UF do Produto", "UF"}}),
    Municipal = Table.RenameColumns(Table.SelectColumns(BaseMunicipal, {"UF do Município"}), {{"UF do Município", "UF"}})
in
    Table.Sort(Table.Distinct(Table.Combine({Geral, Municipal})), {{"UF", Order.Ascending}})""",
            "UF do produto nos dados gerais e do domicílio fiscal na página municipal.",
        ),
        Table(
            "URFs",
            (Column("URF", hidden=True), Column("Unidade aduaneira")),
            """let
    Unicos = Table.Distinct(Table.SelectColumns(BaseGeral, {"URF"})),
    Rotulo = Table.AddColumn(Unicos, "Unidade aduaneira", each let Partes = Text.Split([URF], " - "), Codigo = List.First(Partes), EhCodigo = List.Count(Partes) > 1 and Text.Length(Codigo) = 7 and Text.Select(Codigo, {"0".."9"}) = Codigo in if EhCodigo then Text.Combine(List.Skip(Partes), " - ") & " · " & Codigo else [URF], type text)
in
    Table.Sort(Rotulo, {{"Unidade aduaneira", Order.Ascending}})""",
            "Unidades aduaneiras: nome primeiro, código preservado ao final; chave original inalterada.",
        ),
        Table(
            "MunicipiosFiscais",
            (
                Column("Chave município", hidden=True),
                Column("Município fiscal"),
                Column("UF"),
                Column("Município / UF"),
            ),
            """let
    Unicos = Table.Distinct(Table.SelectColumns(BaseMunicipal, {"Chave município", "Município fiscal", "UF do Município", "Município / UF"})),
    Renomeada = Table.RenameColumns(Unicos, {{"UF do Município", "UF"}})
in
    Table.Sort(Renomeada, {{"Município / UF", Order.Ascending}})""",
            "Chave município + UF para separar cidades homônimas.",
        ),
        Table(
            "SH4",
            (Column("Código SH4"), Column("Descrição SH4")),
            """let
    Unicos = Table.Group(BaseMunicipal, {"Código SH4"}, {{"Descrição SH4", each List.First([Descrição SH4]), type text}})
in
    Table.Sort(Unicos, {{"Código SH4", Order.Ascending}})""",
            "Posição SH4 única. Descrições publicadas de cada linha preservadas no fato municipal.",
        ),
    )


def relationships() -> tuple[tuple[str, str, str, str, bool], ...]:
    return (
        ("Importacoes", "Data", "Calendario", "Data", False),
        ("Municipios", "Data", "Calendario", "Data", False),
        ("Importacoes", "Código NCM", "NCM", "Código NCM", False),
        ("ProdutoNCM", "Código NCM", "NCM", "Código NCM", True),
        ("ProdutoNCM", "Produto", "Produtos", "Produto", False),
        ("Importacoes", "Países", "Paises", "País", False),
        ("Municipios", "Países", "Paises", "País", False),
        ("Importacoes", "UF do Produto", "UFs", "UF", False),
        ("Municipios", "UF do Município", "UFs", "UF", False),
        ("Importacoes", "URF", "URFs", "URF", False),
        ("Municipios", "Chave município", "MunicipiosFiscais", "Chave município", False),
        ("Municipios", "Código SH4", "SH4", "Código SH4", False),
    )


def relationship_tmdl() -> str:
    return "\n".join(
        f"""relationship {lineage("relationship", a, ac, b, bc)}
\tfromColumn: {quote(a)}.{quote(ac)}
\ttoColumn: {quote(b)}.{quote(bc)}
\tfromCardinality: many
\ttoCardinality: one
\tcrossFilteringBehavior: {"bothDirections" if both else "oneDirection"}
"""
        for a, ac, b, bc, both in relationships()
    )


def table_tmdl(table: Table) -> str:
    lines = [
        "/// " + table.description,
        f"table {quote(table.name)}",
        f"\tlineageTag: {lineage(table.name)}",
    ]
    if table.hidden:
        lines.append("\tisHidden")
    for m in table.measures:
        lines += [""]
        if m.description:
            lines.append("\t/// " + m.description)
        lines += [
            f"\tmeasure {quote(m.name)} =",
            *("\t\t\t" + s for s in m.expression.splitlines()),
        ]
        if m.fmt:
            lines.append("\t\tformatString: " + property_text(m.fmt))
        lines += [
            f"\t\tdisplayFolder: {property_text(m.folder)}",
            f"\t\tlineageTag: {lineage(table.name, m.name)}",
        ]
        if m.hidden:
            lines.append("\t\tisHidden")
    for c in table.columns:
        lines += [""]
        if c.description:
            lines.append("\t/// " + c.description)
        lines += [
            f"\tcolumn {quote(c.name)}",
            f"\t\tdataType: {c.dtype}",
            f"\t\tsourceColumn: {property_text(c.name)}",
            "\t\tsummarizeBy: none",
            f"\t\tlineageTag: {lineage(table.name, c.name)}",
        ]
        if c.fmt:
            lines.append("\t\tformatString: " + property_text(c.fmt))
        if c.sort:
            lines.append("\t\tsortByColumn: " + quote(c.sort))
        if c.hidden:
            lines.append("\t\tisHidden")
    lines += [
        "",
        f"\tpartition {quote(table.name)} = m",
        "\t\tmode: import",
        "\t\tsource =",
        *("\t\t\t" + s for s in table.source.splitlines()),
        "",
        "\tannotation PBI_ResultType = Table",
        "",
    ]
    return "\n".join(lines)


def build_model(root: Path, start: str, end: str):
    model = root / "LIARTE_Importacoes.SemanticModel"
    definition = model / "definition"
    definition.mkdir(parents=True, exist_ok=True)
    (model / "definition.pbism").write_text(
        json.dumps({"version": "4.0", "settings": {"qnaEnabled": False}}, indent=2) + "\n",
        encoding="utf-8",
    )
    (model / ".platform").write_text(
        json.dumps(
            {
                "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
                "metadata": {"type": "SemanticModel", "displayName": "LIARTE Importações"},
                "config": {"version": "2.0", "logicalId": lineage("semanticModel")},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (definition / "database.tmdl").write_text(
        "database LIARTE_Importacoes\n\tcompatibilityLevel: 1601\n\tcompatibilityMode: powerBI\n",
        encoding="utf-8",
    )
    expressions_list = expressions(start, end)
    model_text = (
        "model Model\n\tculture: pt-BR\n\tdefaultPowerBIDataSourceVersion: powerBI_V3\n\tdiscourageImplicitMeasures\n\tsourceQueryCulture: pt-BR\n\nannotation __PBI_TimeIntelligenceEnabled = 0\n\nannotation PBI_QueryOrder = "
        + json.dumps(
            [n for n, _, _ in expressions_list] + [t.name for t in tables()], ensure_ascii=False
        )
        + "\n\n"
        + "\n".join("ref table " + quote(t.name) for t in tables())
        + "\n"
    )
    (definition / "model.tmdl").write_text(model_text, encoding="utf-8")
    expressions_text = []
    for name, source, kind in expressions_list:
        if name in ("CaminhoArquivoExcel", "PeriodoInicial", "PeriodoFinal"):
            expressions_text.append(
                f"expression {quote(name)} = {source}\n\tlineageTag: {lineage('expression', name)}\n\tannotation PBI_ResultType = {kind}\n"
            )
        else:
            expressions_text.append(
                f"expression {quote(name)} =\n"
                + "\n".join("\t\t" + s for s in source.splitlines())
                + f"\n\tlineageTag: {lineage('expression', name)}\n\tannotation PBI_ResultType = {kind}\n"
            )
    (definition / "expressions.tmdl").write_text("\n".join(expressions_text), encoding="utf-8")
    (definition / "relationships.tmdl").write_text(relationship_tmdl(), encoding="utf-8")
    (definition / "tables").mkdir(exist_ok=True)
    for table in tables():
        (definition / "tables" / (table.name + ".tmdl")).write_text(
            table_tmdl(table), encoding="utf-8"
        )
