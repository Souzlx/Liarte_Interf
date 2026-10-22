"""Relatório executivo PBIR com visuais nativos, navegação e filtros consistentes."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shutil
from .powerbi_semantic import lineage

CANVAS_WIDTH = 1440
CANVAS_HEIGHT = 900
THEME_FILE = "LIARTE_Executive_2026.json"
LOGO_FILE = "liarte-logo-2026.png"
SCHEMA_BASE = "https://developer.microsoft.com/json-schemas/fabric/item/report/"
NAVY = "#103F70"
TEAL = "#087E91"
TEXT = "#20384F"
MUTED = "#52677D"
SURFACE = "#F5F7FA"
LINE = "#DAE3ED"


@dataclass(frozen=True)
class FieldRef:
    table: str
    name: str
    kind: str = "column"
    label: str = ""


@dataclass(frozen=True)
class VisualSpec:
    visual_type: str
    x: int
    y: int
    width: int
    height: int
    title: str = ""
    roles: tuple[tuple[str, tuple[FieldRef, ...]], ...] = ()
    sort_by: FieldRef | None = None
    sort_direction: str = "Descending"
    slicer_mode: str | None = None
    sync_group: str = ""
    text: str = ""
    key: str = ""


def col(table, name, label=""):
    return FieldRef(table, name, "column", label)


def meas(name, label="", municipal=False):
    return FieldRef("Municipios" if municipal else "Importacoes", name, "measure", label)


def _chart(kind, x, y, w, h, title, category, values, tips=(), sort=None, ascending=False):
    roles = [("Category", (category,)), ("Y", tuple(values))]
    if tips:
        roles.append(("Tooltips", tuple(tips)))
    return VisualSpec(
        kind,
        x,
        y,
        w,
        h,
        title,
        tuple(roles),
        sort or values[0],
        "Ascending" if ascending else "Descending",
    )


def _cards(fields, y=254):
    # As medidas de apresentação em milhões têm também valores integrais no tooltip.
    full = {
        "CIF (US$ mi)": "Valor CIF",
        "Peso Líquido (t)": "Peso líquido (kg)",
        "Frete (US$ mi)": "Frete",
        "FOB municipal (US$ mi)": "Valor FOB Municipal",
        "Peso Municipal (t)": "Peso municipal (kg)",
    }
    tips = tuple(FieldRef(f.table, full[f.name], "measure") for f in fields if f.name in full)
    roles = (("Data", tuple(fields)),) + ((("Tooltips", tips),) if tips else ())
    return VisualSpec("cardVisual", 24, y, 1392, 92, roles=roles)


def _slicers(municipal=False):
    if municipal:
        fields = [
            (196, "Período", col("Calendario", "Período")),
            (376, "Município fiscal", col("MunicipiosFiscais", "Município / UF")),
            (104, "UF", col("UFs", "UF")),
            (280, "Posição SH4", col("SH4", "Código SH4")),
            (372, "País de origem", col("Paises", "País")),
        ]
    else:
        fields = [
            (196, "Período", col("Calendario", "Período")),
            (168, "Produto", col("Produtos", "Produto")),
            (332, "Produto / NCM", col("NCM", "Produto / NCM")),
            (224, "País de origem", col("Paises", "País")),
            (124, "UF", col("UFs", "UF")),
            (268, "URF", col("URFs", "Unidade aduaneira")),
        ]
    x = 24
    result = []
    for width, title, field in fields:
        result.append(
            VisualSpec(
                "slicer",
                x,
                158,
                width,
                80,
                title,
                (("Values", (field,)),),
                slicer_mode="Dropdown",
                sync_group=("municipal_" if municipal else "geral_") + field.table,
            )
        )
        x += width + 16
    return result


def _header(title, start, end, municipal=False):
    interval = f"{start[5:]}/{start[:4]} a {end[5:]}/{end[:4]}"
    scope = (
        ("Municípios · SH4 · FOB" if municipal else "Dados gerais · NCM · CIF")
        + "  |  Base: "
        + interval
    )
    return [
        VisualSpec("image", 24, 22, 126, 43, title="LIARTE", key="logo"),
        VisualSpec("textbox", 178, 16, 1238, 36, text=title, key="heading"),
        VisualSpec("textbox", 178, 56, 1238, 24, text=scope, key="scope"),
        VisualSpec(
            "pageNavigator", 24, 96, 1392, 44, title="Páginas do relatório", key="navigation"
        ),
    ] + _slicers(municipal)


def pages(start="2026-01", end="2026-12"):
    period = col("Calendario", "Período")
    country = col("Paises", "País")
    ncm = col("NCM", "Produto / NCM")
    m = meas
    executive = [
        _cards(
            (
                m("CIF (US$ mi)", "Valor CIF · US$ mi"),
                m("Peso Líquido (t)", "Peso líquido · t"),
                m("Custo Logístico % CIF", "Logística / CIF"),
                m("Países de origem", "Países de origem"),
            )
        ),
        _chart(
            "lineChart",
            24,
            374,
            684,
            466,
            "Evolução mensal · CIF (US$ mi)",
            period,
            [m("CIF gráfico (mi)", "CIF")],
            [m("Valor CIF"), m("Peso Líquido (t)"), m("CIF vs mês anterior")],
            period,
            True,
        ),
        _chart(
            "clusteredBarChart",
            724,
            374,
            692,
            466,
            "10 principais produtos / NCM · CIF (US$ mi)",
            ncm,
            [m("CIF top NCM", "CIF")],
            [m("Peso Líquido (t)"), m("CIF por kg"), m("Participação CIF por NCM")],
        ),
    ]
    market = [
        _cards(
            (
                m("Países de origem"),
                m("UFs do produto"),
                m("Concentração Top 5 Países", "Top 5 países · participação"),
                m("Registros estatísticos", "Registros estatísticos"),
            )
        ),
        _chart(
            "clusteredBarChart",
            24,
            374,
            508,
            466,
            "10 principais países · CIF (US$ mi)",
            country,
            [m("CIF top países", "CIF")],
            [m("Peso Líquido (t)"), m("Participação CIF por país")],
        ),
        _chart(
            "clusteredBarChart",
            548,
            374,
            292,
            466,
            "UFs · CIF (US$ mi)",
            col("UFs", "UF"),
            [m("CIF gráfico (mi)", "CIF")],
        ),
        _chart(
            "clusteredBarChart",
            856,
            374,
            560,
            466,
            "10 principais URFs · CIF (US$ mi)",
            col("URFs", "Unidade aduaneira"),
            [m("CIF top URFs", "CIF")],
            [m("Peso Líquido (t)")],
        ),
    ]
    products = [
        _cards(
            (
                m("CIF por kg último mês", "CIF/kg · último mês"),
                m("CIF por kg MM3", "CIF/kg · MM3 ponderada"),
                m("CIF por kg vs mês anterior", "CIF/kg · variação mensal"),
                m("Frete por kg comparável", "Frete/kg · período"),
            )
        ),
        VisualSpec(
            "cardVisual",
            24,
            358,
            1392,
            56,
            roles=(("Data", (m("Contexto de preços"),)),),
            key="context",
        ),
        _chart(
            "lineChart",
            24,
            430,
            796,
            410,
            "Evolução de preço · US$/kg · escala automática",
            period,
            [
                m("CIF por kg comparável", "CIF/kg"),
                m("FOB por kg comparável", "FOB/kg"),
                m("CIF por kg MM3", "CIF/kg · MM3"),
            ],
            [m("Peso líquido (kg)"), m("Registros sem peso")],
            period,
            True,
        ),
        _chart(
            "clusteredBarChart",
            836,
            430,
            580,
            410,
            "CIF/kg por origem · 10 maiores volumes",
            country,
            [m("CIF por origem relevante", "CIF/kg")],
            [m("Peso líquido (kg)"), m("Valor CIF")],
        ),
    ]
    logistics = [
        _cards(
            (
                m("Frete (US$ mi)", "Frete · US$ mi"),
                m("Seguro", "Seguro · US$"),
                m("Custo Logístico % FOB", "Logística / FOB"),
                m("Índice CIF/FOB", "CIF / FOB"),
            )
        ),
        _chart(
            "lineChart",
            24,
            374,
            684,
            466,
            "Frete mensal · US$ mi",
            period,
            [m("Frete gráfico (mi)", "Frete · US$ mi")],
            [m("Frete"), m("Peso Líquido (t)"), m("Frete por kg"), m("Registros sem peso")],
            period,
            True,
        ),
        _chart(
            "clusteredBarChart",
            724,
            374,
            692,
            466,
            "Logística / FOB · 10 maiores países por CIF",
            country,
            [m("Logística top países", "Logística / FOB")],
            [m("Custo Logístico"), m("Valor FOB"), m("Valor CIF")],
        ),
    ]
    detail_fields = tuple(
        col("Importacoes", field, label)
        for field, label in (
            ("Data", "Mês"),
            ("Código NCM", "NCM"),
            ("Nome comercial", "Produto"),
            ("UF do Produto", "UF"),
            ("URF", "URF"),
            ("Países", "País"),
            ("US$ FOB", "FOB"),
            ("US$ Frete", "Frete"),
            ("US$ Seguro", "Seguro"),
            ("Valor US$ CIF", "CIF"),
            ("Quilograma Líquido", "Peso líquido"),
            ("US$ CIF/kg", "CIF/kg"),
            ("Descrição NCM", "Descrição oficial"),
            ("Produtos relacionados", "Produtos relacionados"),
        )
    )
    detail = [
        VisualSpec(
            "tableEx",
            24,
            254,
            1392,
            586,
            "Registros estatísticos mensais",
            (("Values", detail_fields),),
            col("Importacoes", "Data"),
            "Ascending",
        )
    ]

    def mm(name, label=""):
        return m(name, label, True)

    municipal = [
        _cards(
            (
                mm("FOB municipal (US$ mi)", "FOB · US$ mi"),
                mm("Peso Municipal (t)", "Peso líquido · t"),
                mm("Municípios ativos", "Municípios / UF"),
                mm("FOB Municipal por kg", "FOB/kg · SH4 selecionado"),
            )
        ),
        _chart(
            "lineChart",
            24,
            366,
            684,
            230,
            "Evolução mensal · FOB (US$ mi)",
            period,
            [mm("FOB municipal gráfico (mi)", "FOB")],
            [mm("Valor FOB Municipal"), mm("Peso Municipal (t)")],
            period,
            True,
        ),
        _chart(
            "clusteredBarChart",
            724,
            366,
            692,
            230,
            "8 principais municípios · FOB (US$ mi)",
            col("MunicipiosFiscais", "Município / UF"),
            [mm("FOB top municípios", "FOB")],
            [mm("Peso Municipal (t)")],
        ),
        _chart(
            "clusteredBarChart",
            24,
            612,
            500,
            228,
            "8 principais posições SH4 · FOB (US$ mi)",
            col("SH4", "Código SH4"),
            [mm("FOB top SH4", "FOB")],
            [mm("Peso Municipal (t)")],
        ),
        VisualSpec(
            "tableEx",
            540,
            612,
            876,
            228,
            "Detalhamento municipal",
            (
                (
                    "Values",
                    (
                        col("Municipios", "Data", "Mês"),
                        col("Municipios", "Município / UF"),
                        col("Municipios", "Código SH4", "SH4"),
                        col("Municipios", "Países", "País"),
                        col("Municipios", "US$ FOB", "FOB"),
                        col("Municipios", "Quilograma Líquido", "Peso líquido"),
                        col("Municipios", "US$ FOB/kg", "FOB/kg"),
                        col("Municipios", "Descrição SH4"),
                    ),
                ),
            ),
            col("Municipios", "US$ FOB"),
            "Descending",
        ),
    ]
    result = []
    for name, items, note, is_municipal in (
        (
            "Visão Executiva",
            executive,
            "Fonte: Comex Stat · Valores nominais em US$ · Registros estatísticos mensais, não pedidos individuais.",
            False,
        ),
        (
            "Mercado e Origem",
            market,
            "Participações calculadas dentro dos filtros selecionados · País de origem não identifica o fornecedor.",
            False,
        ),
        (
            "Produtos e NCM",
            products,
            "US$/kg = soma do valor ÷ soma do peso · Selecione um NCM · MM3 ponderada, sem previsão ou ajuste de mix.",
            False,
        ),
        (
            "Custos Logísticos",
            logistics,
            "Logística = frete + seguro · Valores agregados publicados; não incluem custos internos, tributos ou condições contratuais.",
            False,
        ),
        (
            "Base Detalhada",
            detail,
            "Valores integrais em US$ · Peso em kg · Descrição oficial e produtos relacionados preservados para conferência.",
            False,
        ),
        (
            "Análise Municipal",
            municipal,
            "Municipal SH4/FOB · Domicílio fiscal · Não somar à base geral · FOB/kg indisponível quando há valor positivo sem peso.",
            True,
        ),
    ):
        result.append(
            (
                name,
                _header(name, start, end, is_municipal)
                + items
                + [VisualSpec("textbox", 24, 856, 1392, 28, text=note, key="footnote")],
            )
        )
    return result


def _literal(value):
    if isinstance(value, bool):
        text = "true" if value else "false"
    elif isinstance(value, (int, float)):
        text = str(value) + "D"
    else:
        text = "'" + str(value).replace("'", "''") + "'"
    return {"expr": {"Literal": {"Value": text}}}


def _color(value):
    return {"solid": {"color": _literal(value)}}


def _obj(**properties):
    colors = {
        "fontColor",
        "color",
        "labelColor",
        "strokeColor",
        "markerColor",
        "gridlineColor",
        "fillColor",
        "defaultColor",
        "backgroundColor",
        "fontColorPrimary",
        "fontColorSecondary",
        "backColor",
        "backColorPrimary",
        "backColorSecondary",
        "gridHorizontalColor",
        "backgroundFillColor",
    }
    return [
        {
            "properties": {
                k: (_color(v) if k in colors else _literal(v)) for k, v in properties.items()
            }
        }
    ]


def _selected(props, selector=None):
    result = {"properties": props}
    if selector is not None:
        result["selector"] = selector
    return result


def field_expression(field):
    return {
        ("Measure" if field.kind == "measure" else "Column"): {
            "Expression": {"SourceRef": {"Entity": field.table}},
            "Property": field.name,
        }
    }


def projection(field):
    result = {
        "field": field_expression(field),
        "queryRef": field.table + "." + field.name,
        "nativeQueryRef": field.label or field.name,
    }
    if field.label:
        result["displayName"] = field.label
    return result


def _vco(spec):
    plain = spec.visual_type in ("textbox", "image", "pageNavigator")
    card = spec.visual_type == "cardVisual"
    result = {
        "general": _obj(altText=spec.title or spec.text or "Indicadores da seleção"),
        "background": _obj(show=not plain, color="#FFFFFF", transparency=0),
        "border": _obj(show=not plain and not card, color=LINE, radius=6, width=1),
        "padding": _obj(
            top=8 if not plain else 0,
            bottom=8 if not plain else 0,
            left=12 if not plain else 0,
            right=12 if not plain else 0,
        ),
    }
    if spec.title and not plain and spec.visual_type != "slicer":
        result["title"] = _obj(
            show=True,
            text=spec.title,
            fontColor=TEXT,
            fontFamily="Segoe UI Semibold",
            fontSize=13,
            alignment="left",
        )
    if spec.visual_type == "tableEx":
        result["stylePreset"] = _obj(name="None")
    if card:
        result["spacing"] = [
            {
                "selector": {"id": "default"},
                "properties": {"customizeSpacing": _literal(True), "verticalSpacing": _literal(2)},
            }
        ]
    return result


def _objects(spec):
    kind = spec.visual_type
    if kind == "textbox":
        size = 23 if spec.key == "heading" else 11
        color = NAVY if spec.key == "heading" else MUTED
        return {
            "general": [
                {
                    "properties": {
                        "paragraphs": [
                            {
                                "textRuns": [
                                    {
                                        "value": spec.text,
                                        "textStyle": {
                                            "fontFamily": "Segoe UI Semibold"
                                            if spec.key == "heading"
                                            else "Segoe UI",
                                            "fontSize": f"{size}pt",
                                            "color": color,
                                        },
                                    }
                                ]
                            }
                        ]
                    }
                }
            ]
        }
    if kind == "image":
        return {
            "general": [
                {
                    "properties": {
                        "imageUrl": {
                            "expr": {
                                "ResourcePackageItem": {
                                    "PackageName": "RegisteredResources",
                                    "PackageType": 1,
                                    "ItemName": LOGO_FILE,
                                }
                            }
                        }
                    }
                }
            ],
            "image": _obj(fit="Fit"),
        }
    if kind == "slicer":
        return {
            "data": _obj(mode="Dropdown"),
            "header": _obj(
                show=True,
                text=spec.title,
                fontColor=TEXT,
                textSize=12,
                fontFamily="Segoe UI Semibold",
            ),
            "items": _obj(fontColor=TEXT, textSize=11, fontFamily="Segoe UI", background="#FFFFFF"),
            "selection": _obj(
                selectAllCheckboxEnabled=True, singleSelect=False, strictSingleSelect=False
            ),
        }
    if kind == "pageNavigator":
        fill = [
            {"properties": {"fillColor": _color("#FFFFFF"), "show": _literal(True)}},
            {
                "selector": {"id": "hover"},
                "properties": {"fillColor": _color("#E8F0F8"), "show": _literal(True)},
            },
            {
                "selector": {"id": "selected"},
                "properties": {"fillColor": _color(NAVY), "show": _literal(True)},
            },
        ]
        text = [
            {
                "properties": {
                    "fontColor": _color(MUTED),
                    "fontSize": _literal(12),
                    "fontFamily": _literal("Segoe UI Semibold"),
                }
            },
            {"selector": {"id": "selected"}, "properties": {"fontColor": _color("#FFFFFF")}},
        ]
        return {
            "layout": _obj(orientation=0, rowCount=1, columnCount=6, cellPadding=8),
            "fill": fill,
            "text": text,
            "outline": _obj(show=False),
        }
    if kind == "cardVisual":
        context = spec.key == "context"
        return {
            "border": _obj(show=False),
            "outline": _obj(show=False),
            "fillCustom": _obj(show=True, fillColor=SURFACE, transparency=0),
            "layout": _obj(
                maxTiles=4,
                cellPadding=12,
                autoGrid=False,
                columnCount=1 if context else 4,
                rowCount=1,
                orientation=0,
                topOuterMargin=0,
                bottomOuterMargin=0,
                leftOuterMargin=0,
                rightOuterMargin=0,
            ),
            "value": _obj(
                fontFamily="Segoe UI Semibold",
                fontSize=12 if context else 25,
                fontColor=TEXT,
                show=True,
                labelDisplayUnits=1,
                showBlankAs="—",
                textWrap=True,
                horizontalAlignment="left",
            ),
            "label": _obj(
                show=not context,
                fontFamily="Segoe UI",
                fontSize=13,
                fontColor=MUTED,
                position="belowValue",
                textWrap=True,
                horizontalAlignment="left",
            ),
            "padding": _obj(paddingSelection="Custom", paddingUniform=8, paddingIndividual=False),
        }
    if kind == "tableEx":
        return {
            "columnHeaders": _obj(
                fontColor="#FFFFFF",
                backColor=NAVY,
                fontFamily="Segoe UI Semibold",
                fontSize=11,
                autoSizeColumnWidth=True,
                columnAdjustment="growToFit",
                wordWrap=True,
            ),
            "values": _obj(
                fontColorPrimary=TEXT,
                fontColorSecondary=TEXT,
                backColorPrimary="#FFFFFF",
                backColorSecondary=SURFACE,
                fontFamily="Segoe UI",
                fontSize=11,
                wordWrap=False,
            ),
            "grid": _obj(
                gridVertical=False, gridHorizontal=True, gridHorizontalColor=LINE, rowPadding=5
            ),
            "total": _obj(
                totals=False,
                fontColor=NAVY,
                backColor=SURFACE,
                fontFamily="Segoe UI Semibold",
                fontSize=11,
            ),
        }
    result = {
        "categoryAxis": _obj(
            show=True, fontFamily="Segoe UI", fontSize=11, labelColor=MUTED, showAxisTitle=False
        ),
        "valueAxis": _obj(
            show=True,
            fontFamily="Segoe UI",
            fontSize=11,
            labelColor=MUTED,
            showAxisTitle=False,
            labelDisplayUnits=1,
            gridlineColor=LINE,
            gridlineShow=True,
        ),
        "legend": _obj(show=False),
        "dataPoint": _obj(defaultColor=TEAL),
        "labels": _obj(show=False),
    }
    if kind == "clusteredBarChart":
        result["valueAxis"][0]["properties"]["start"] = _literal(0)
    if kind == "lineChart":
        result["categoryAxis"][0]["properties"]["axisType"] = _literal("Categorical")
        result["lineStyles"] = _obj(strokeWidth=2, lineStyle="solid", showMarker=True, markerSize=4)
        ys = dict(spec.roles).get("Y", ())
        if ys and all(f.name.endswith("gráfico (mi)") for f in ys):
            result["valueAxis"][0]["properties"]["start"] = _literal(0)
        if len(ys) > 1:
            result["legend"] = _obj(
                show=True, position="Top", fontFamily="Segoe UI", fontSize=11, labelColor=MUTED
            )
            result["dataPoint"] = [
                {
                    "selector": {"metadata": f.table + "." + f.name},
                    "properties": {"fill": _color(c)},
                }
                for f, c in zip(ys, (TEAL, "#6B8094", NAVY), strict=False)
            ]
            for field, shape, style in zip(
                ys, ("circle", "square", "diamond"), ("solid", "solid", "dashed"), strict=False
            ):
                result["lineStyles"].append(
                    {
                        "selector": {"metadata": field.table + "." + field.name},
                        "properties": {
                            "lineStyle": _literal(style),
                            "markerShape": _literal(shape),
                        },
                    }
                )

    return result


def visual_payload(spec, page_name, index):
    visual = {
        "visualType": spec.visual_type,
        "objects": _objects(spec),
        "visualContainerObjects": _vco(spec),
    }
    if spec.visual_type == "cardVisual":
        for entries in visual["objects"].values():
            for entry in entries:
                entry.setdefault("selector", {"id": "default"})
    if spec.roles:
        query = {
            "queryState": {
                role: {"projections": [projection(field) for field in fields]}
                for role, fields in spec.roles
            }
        }
        if spec.sort_by:
            query["sortDefinition"] = {
                "sort": [
                    {"field": field_expression(spec.sort_by), "direction": spec.sort_direction}
                ],
                "isDefaultSort": False,
            }
        visual["query"] = query
    if spec.sync_group:
        visual["syncGroup"] = {
            "groupName": spec.sync_group,
            "fieldChanges": True,
            "filterChanges": True,
        }
    return {
        "$schema": SCHEMA_BASE + "definition/visualContainer/2.9.0/schema.json",
        "name": lineage("visual", page_name, str(index)).replace("-", "")[:20],
        "position": {
            "x": spec.x,
            "y": spec.y,
            "z": index * 1000,
            "width": spec.width,
            "height": spec.height,
            "tabOrder": index * 1000,
        },
        "visual": visual,
    }


def theme():
    return {
        "name": THEME_FILE,
        "dataColors": [TEAL, NAVY, "#8A9CAD", "#55A6AC", "#B5C7D8", "#C59758"],
        "background": "#FFFFFF",
        "foreground": TEXT,
        "tableAccent": TEAL,
        "textClasses": {
            "label": {"fontFace": "Segoe UI", "fontSize": 11, "color": TEXT},
            "title": {"fontFace": "Segoe UI Semibold", "fontSize": 13, "color": TEXT},
            "callout": {"fontFace": "Segoe UI Semibold", "fontSize": 25, "color": TEXT},
        },
    }


def _write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_report(root: Path, start: str, end: str, version: str):
    report = root / "LIARTE_Importacoes.Report"
    definition = report / "definition"
    _write(
        report / ".platform",
        {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
            "metadata": {"type": "Report", "displayName": "LIARTE Importações"},
            "config": {"version": "2.0", "logicalId": lineage("report")},
        },
    )
    _write(
        report / "definition.pbir",
        {
            "$schema": SCHEMA_BASE + "definitionProperties/2.0.0/schema.json",
            "version": "4.0",
            "datasetReference": {"byPath": {"path": "../LIARTE_Importacoes.SemanticModel"}},
        },
    )
    _write(
        definition / "version.json",
        {
            "$schema": SCHEMA_BASE + "definition/versionMetadata/1.0.0/schema.json",
            "version": "2.0.0",
        },
    )
    _write(
        definition / "report.json",
        {
            "$schema": SCHEMA_BASE + "definition/report/3.1.0/schema.json",
            "themeCollection": {
                "customTheme": {
                    "name": THEME_FILE,
                    "reportVersionAtImport": {
                        "visual": "2.9.0",
                        "page": "2.1.0",
                        "report": "3.1.0",
                    },
                    "type": "RegisteredResources",
                }
            },
            "resourcePackages": [
                {
                    "name": "RegisteredResources",
                    "type": "RegisteredResources",
                    "items": [
                        {"name": THEME_FILE, "path": THEME_FILE, "type": "CustomTheme"},
                        {"name": LOGO_FILE, "path": LOGO_FILE, "type": "Image"},
                    ],
                }
            ],
            "annotations": [
                {"name": "generator", "value": "Liarte Importações"},
                {"name": "generatorVersion", "value": version},
            ],
        },
    )
    resources = report / "StaticResources" / "RegisteredResources"
    _write(resources / THEME_FILE, theme())
    shutil.copyfile(
        Path(__file__).resolve().parents[1]
        / "liarte_desktop"
        / "assets"
        / "liarte-logo-transparente.png",
        resources / LOGO_FILE,
    )
    order = []
    for title, specs in pages(start, end):
        page_name = "ReportSection" + lineage("page", title).replace("-", "")[:24]
        order.append(page_name)
        page_dir = definition / "pages" / page_name
        _write(
            page_dir / "page.json",
            {
                "$schema": SCHEMA_BASE + "definition/page/2.1.0/schema.json",
                "name": page_name,
                "displayName": title,
                "displayOption": "FitToPage",
                "height": CANVAS_HEIGHT,
                "width": CANVAS_WIDTH,
            },
        )
        for i, spec in enumerate(specs, 1):
            payload = visual_payload(spec, page_name, i)
            _write(page_dir / "visuals" / payload["name"] / "visual.json", payload)
    _write(
        definition / "pages" / "pages.json",
        {
            "$schema": SCHEMA_BASE + "definition/pagesMetadata/1.0.0/schema.json",
            "pageOrder": order,
            "activePageName": order[0],
        },
    )
