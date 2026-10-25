#!/usr/bin/env python3
"""Gera um projeto Power BI (PBIP) executivo a partir do Excel de importações.

O formato fechado ``.pbix`` só pode ser gravado pelo Power BI Desktop. Este
módulo produz o equivalente editável e documentado: um projeto ``.pbip`` com
modelo semântico, medidas DAX, seis páginas de relatório e a planilha fonte.
O resultado é empacotado em ZIP para download e transporte.

O pacote contém ``Abrir_PowerBI.cmd``. No Windows, esse iniciador localiza a
planilha dentro da pasta extraída, atualiza o parâmetro da fonte e abre o PBIP.
Depois da atualização dos dados, o Power BI Desktop permite salvar como PBIX.

O módulo usa somente a biblioteca padrão do Python.
"""

from __future__ import annotations

import argparse
import json
import hashlib
import math
import posixpath
import re
import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence
from xml.etree import ElementTree


from . import powerbi_semantic as semantic
from . import powerbi_visuals as visuals
from .powerbi_source import (
    audit_source,
    cell_reference,
    read_shared_strings,
    validate_xlsx_container,
    _rows,
)
from .powerbi_visuals import CANVAS_WIDTH, CANVAS_HEIGHT

PROJECT_NAME = "LIARTE_Importacoes"
REPORT_DIR_NAME = f"{PROJECT_NAME}.Report"
MODEL_DIR_NAME = f"{PROJECT_NAME}.SemanticModel"
PBIP_FILE_NAME = f"{PROJECT_NAME}.pbip"
POWERBI_PACKAGE_PREFIX = "POWERBI_LIARTE_IMPORTACOES"
POWERBI_GENERATOR_VERSION = "5.3.1-rc.1"
MIN_POWERBI_PERIOD = "1997-01"
MAX_XLSX_ENTRIES = 20_000

GENERAL_SHEET_PREFIX = "Base geral"
MUNICIPAL_SHEET_PREFIX = "Base municipal"
PRODUCT_SHEET_NAME = "Produtos"
LEGACY_GENERAL_SHEET_PREFIX = "Import_Full"
LEGACY_MUNICIPAL_SHEET_PREFIX = "Import_Municipios"
LEGACY_PRODUCT_SHEET_NAME = "NCM_Produtos"
EXPECTED_IMPORT_HEADERS = (
    "Mês",
    "NCM",
    "Descrição",
    "UF",
    "URF",
    "País",
    "FOB",
    "Frete",
    "Seguro",
    "CIF",
    "Peso líq.",
    "Produtos",
    "CIF/kg",
)
EXPECTED_PRODUCT_HEADERS = ("Produto", "NCM")
EXPECTED_MUNICIPAL_HEADERS = (
    "Mês",
    "Município fiscal",
    "UF",
    "SH4",
    "Descrição",
    "País",
    "FOB",
    "Peso líq.",
    "Produtos",
    "NCMs",
    "FOB/kg",
)
LEGACY_EXPECTED_IMPORT_HEADERS = (
    "Mês",
    "Código NCM",
    "Descrição NCM",
    "UF do Produto",
    "URF",
    "Países",
    "US$ FOB",
    "US$ Frete",
    "US$ Seguro",
    "Valor US$ CIF",
    "Quilograma Líquido",
    "Produtos relacionados",
    "US$ CIF/kg",
)
LEGACY_EXPECTED_PRODUCT_HEADERS = ("Produto", "Código NCM")
LEGACY_EXPECTED_MUNICIPAL_HEADERS = (
    "Mês",
    "Município fiscal",
    "UF do Município",
    "Código SH4",
    "Descrição SH4",
    "Países",
    "US$ FOB",
    "Quilograma Líquido",
    "Produtos relacionados",
    "NCMs relacionados",
    "US$ FOB/kg",
)


class PowerBIProjectError(RuntimeError):
    """Erro de criação ou validação do projeto Power BI."""


def _json_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _text_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def _safe_stem(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", value).strip("_")
    return cleaned or "relatorio"


def default_powerbi_path(excel_path: Path) -> Path:
    """Retorna o nome padrão do pacote Power BI ao lado do Excel."""
    match = re.search(r"(\d{4}-\d{2})_(\d{4}-\d{2})", excel_path.stem)
    suffix = f"_{match.group(1)}_{match.group(2)}" if match else ""
    return excel_path.with_name(f"{POWERBI_PACKAGE_PREFIX}{suffix}.zip")


def _column_index(reference: str) -> int:
    return cell_reference(reference)[0]


def _sheet_headers(
    archive: zipfile.ZipFile,
    sheet_path: str,
    shared_strings: Sequence[str],
    checkpoint: Callable[[], None] | None = None,
) -> tuple[str, ...]:
    first_row = None
    # Every row is validated, including unused extra columns, without allocating
    # a dense tuple wider than any source table consumed by this model.
    for _, row in _rows(archive, sheet_path, shared_strings, checkpoint, 13, allow_formulas=True):
        if first_row is None:
            first_row = tuple("" if value is None else str(value) for value in row)
    return first_row or ()


def _validate_excel_source(
    excel_path: Path, checkpoint: Callable[[], None] | None = None
) -> dict[str, Any]:
    """Valida o XLSX e os cabeçalhos consumidos pelas consultas do Power BI."""
    try:
        with zipfile.ZipFile(excel_path) as archive:
            sheet_paths = validate_xlsx_container(archive, checkpoint)
            names = set(archive.namelist())
            current_import_sheets = sorted(
                name for name in sheet_paths if name.startswith(GENERAL_SHEET_PREFIX)
            )
            legacy_import_sheets = sorted(
                name for name in sheet_paths if name.startswith(LEGACY_GENERAL_SHEET_PREFIX)
            )
            import_sheets = current_import_sheets or legacy_import_sheets
            current_municipal_sheets = sorted(
                name for name in sheet_paths if name.startswith(MUNICIPAL_SHEET_PREFIX)
            )
            legacy_municipal_sheets = sorted(
                name for name in sheet_paths if name.startswith(LEGACY_MUNICIPAL_SHEET_PREFIX)
            )
            municipal_sheets = current_municipal_sheets or legacy_municipal_sheets
            product_sheet = (
                PRODUCT_SHEET_NAME
                if PRODUCT_SHEET_NAME in sheet_paths
                else LEGACY_PRODUCT_SHEET_NAME
                if LEGACY_PRODUCT_SHEET_NAME in sheet_paths
                else None
            )
            if not import_sheets or not municipal_sheets or product_sheet is None:
                raise PowerBIProjectError(
                    "O Excel deve conter Base geral, Base municipal e Produtos "
                    "para alimentar o Power BI."
                )

            shared_strings = read_shared_strings(archive, checkpoint)
            selected_paths = {
                sheet_paths[name] for name in (*import_sheets, *municipal_sheets, product_sheet)
            }
            for path in set(sheet_paths.values()) - selected_paths:
                _sheet_headers(archive, path, shared_strings, checkpoint)
            for sheet_name in import_sheets:
                path = sheet_paths[sheet_name]
                if path not in names:
                    raise PowerBIProjectError(f"Arquivo interno ausente para a aba {sheet_name}.")
                headers = _sheet_headers(archive, path, shared_strings, checkpoint)
                header_prefix = headers[: len(EXPECTED_IMPORT_HEADERS)]
                if header_prefix not in {
                    EXPECTED_IMPORT_HEADERS,
                    LEGACY_EXPECTED_IMPORT_HEADERS,
                }:
                    raise PowerBIProjectError(f"Cabeçalhos incompatíveis na aba {sheet_name}.")
            for sheet_name in municipal_sheets:
                path = sheet_paths[sheet_name]
                if path not in names:
                    raise PowerBIProjectError(f"Arquivo interno ausente para a aba {sheet_name}.")
                headers = _sheet_headers(archive, path, shared_strings, checkpoint)
                header_prefix = headers[: len(EXPECTED_MUNICIPAL_HEADERS)]
                if header_prefix not in {
                    EXPECTED_MUNICIPAL_HEADERS,
                    LEGACY_EXPECTED_MUNICIPAL_HEADERS,
                }:
                    raise PowerBIProjectError(
                        f"Cabeçalhos incompatíveis na aba municipal {sheet_name}."
                    )
            product_path = sheet_paths[product_sheet]
            headers = _sheet_headers(archive, product_path, shared_strings, checkpoint)
            header_prefix = headers[: len(EXPECTED_PRODUCT_HEADERS)]
            if header_prefix not in {
                EXPECTED_PRODUCT_HEADERS,
                LEGACY_EXPECTED_PRODUCT_HEADERS,
            }:
                raise PowerBIProjectError(f"Cabeçalhos incompatíveis na aba {product_sheet}.")
            return {
                "general": [(name, sheet_paths[name]) for name in import_sheets],
                "municipal": [(name, sheet_paths[name]) for name in municipal_sheets],
                "products": (product_sheet, product_path),
                "strings": shared_strings,
            }
    except (ElementTree.ParseError, KeyError, OSError, zipfile.BadZipFile, ValueError) as exc:
        raise PowerBIProjectError(
            "A planilha de origem está corrompida ou não é um XLSX válido."
        ) from exc


def _pages():
    return visuals.pages()


def _build_model(root: Path, start_period: str, end_period: str) -> None:
    semantic.build_model(root, start_period, end_period)


def _build_report(root: Path, start_period: str, end_period: str) -> None:
    visuals.build_report(root, start_period, end_period, POWERBI_GENERATOR_VERSION)


def _powershell_launcher() -> str:
    return r"""$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Excels = @(Get-ChildItem -LiteralPath (Join-Path $Root "Dados") -Filter "*.xlsx" -File)
if ($Excels.Count -ne 1) { throw "A pasta Dados deve conter exatamente uma planilha Excel." }
$Excel = $Excels[0]

$Tmdl = Join-Path $Root "LIARTE_Importacoes.SemanticModel\definition\expressions.tmdl"
if (-not (Test-Path -LiteralPath $Tmdl -PathType Leaf)) { throw "O modelo semântico está incompleto." }
$Content = [System.IO.File]::ReadAllText($Tmdl)
$SafePath = $Excel.FullName.Replace('#(', '#(#)(').Replace('"', '""')
$Pattern = '(?m)^expression CaminhoArquivoExcel = ".*" meta'
$Replacement = 'expression CaminhoArquivoExcel = "' + $SafePath + '" meta'
$Evaluator = [System.Text.RegularExpressions.MatchEvaluator] { param($Match) $Replacement }
$Updated = [System.Text.RegularExpressions.Regex]::Replace($Content, $Pattern, $Evaluator)
if ($Updated -eq $Content -and $Content -notmatch [regex]::Escape($SafePath)) {
    throw "Não foi possível configurar o caminho do Excel no modelo semântico."
}
[System.IO.File]::WriteAllText($Tmdl, $Updated, (New-Object System.Text.UTF8Encoding($false)))

$Pbip = Join-Path $Root "LIARTE_Importacoes.pbip"
if (-not (Test-Path -LiteralPath $Pbip -PathType Leaf)) { throw "O arquivo PBIP não foi encontrado." }
Start-Process -FilePath $Pbip
"""


def _cmd_launcher() -> str:
    return r"""@echo off
setlocal
title LIARTE - Abrir Power BI
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Configurar_e_Abrir.ps1"
if errorlevel 1 (
  echo.
  echo Nao foi possivel abrir o projeto. Consulte o arquivo LEIA-ME.txt.
  pause
)
endlocal
"""


def _readme(excel_name: str, start_period: str, end_period: str) -> str:
    return f"""LIARTE — IMPORTAÇÕES NO POWER BI
Período: {start_period} até {end_period}
Fonte: Dados\\{excel_name}

1. Extraia todo o ZIP para uma pasta do Windows.
2. Instale o Power BI Desktop. Habilite projetos PBIP, TMDL e PBIR nas opções
   de visualização prévia, se a versão instalada exigir. Reinicie o Desktop.
3. Execute Abrir_PowerBI.cmd. O caminho do Excel será configurado automaticamente.
4. No Desktop, clique em Atualizar e confirme a privacidade da fonte local.
   Atualizar lê este Excel; uma nova consulta ao Comex é feita no aplicativo.
5. Salve como PBIX no Desktop, se necessário. O Python gera o projeto editável
   PBIP; o aplicativo não grava o formato fechado PBIX.

PÁGINAS
Visão Executiva: CIF, peso, logística e evolução mensal.
Mercado e Origem: concentração, países, UFs e URFs.
Produtos e NCM: CIF/kg, FOB/kg, MM3 ponderada e variação mensal.
Custos Logísticos: frete, seguro e índices relativos.
Base Detalhada: valores integrais e descrições oficiais.
Análise Municipal: FOB, SH4, município fiscal, país e peso.

LEITURA CORRETA
- As cinco páginas gerais compartilham os filtros; a municipal tem filtros
  independentes. Limpe os segmentadores pelo ícone de borracha do Power BI.
- Tabelas detalhadas usam as colunas da própria base, sem totais artificiais de
  preços unitários. CIF/kg e FOB/kg de cada linha são recalculados a partir do
  valor e peso da mesma observação; quando kg = 0, a razão fica vazia.
- O gráfico logístico mensal usa o frete integral em US$ mi. Frete/kg permanece
  disponível nos recortes com peso completo e na análise de um único NCM.
- Valores por kg agregados são razões de somas, não médias das linhas. A página de preços
  exige um único NCM para evitar comparar produtos diferentes. MM3 requer três
  meses consecutivos selecionados, com peso publicado em todos eles.
- Valor positivo sem peso torna a respectiva razão indisponível; ausência de
  dados permanece vazia. Nenhuma observação é silenciosamente descartada.
- Um NCM pode corresponder a vários produtos do cadastro. A ponte de produtos
  filtra a união dos NCMs sem multiplicar os fatos. Rankings usam NCMs únicos.
- Valores nominais em US$, sem estimativa de preço futuro, inflação ou câmbio.
- Estatísticas mensais não representam pedidos, declarações ou fornecedores.
- A base municipal é SH4, mais ampla que os NCMs do cadastro. Não contém CIF,
  frete, seguro, URF ou NCM8. Não deve ser somada à base geral. Município é o
  domicílio fiscal do declarante, não o destino físico da mercadoria.
- O Excel completo permanece inalterado dentro de Dados. CONTROLE_FONTE.json
  registra SHA-256, totais e meses: dinheiro em centavos e peso em kg inteiros.
- VERIFICAR_MEDIDAS.dax permite comparar medidas no Desktop com esses controles.
  Converta os valores em US$ para centavos (x100) ao conferir o JSON.
- Ao mover a pasta, execute Abrir_PowerBI.cmd novamente antes de abrir o projeto.
- Os validadores estruturais não substituem Atualizar e conferir visualmente
  as seis páginas na sua versão do Power BI Desktop.
"""


def _build_project_tree(
    root: Path,
    excel_path: Path,
    start_period: str,
    end_period: str,
) -> None:
    _json_write(
        root / PBIP_FILE_NAME,
        {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json",
            "version": "1.0",
            "artifacts": [{"report": {"path": REPORT_DIR_NAME}}],
            "settings": {"enableAutoRecovery": True},
        },
    )
    _text_write(root / ".gitignore", "**/.pbi/localSettings.json\n**/.pbi/cache.abf\n")
    _build_model(root, start_period, end_period)
    _build_report(root, start_period, end_period)
    data_dir = root / "Dados"
    data_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(excel_path, data_dir / excel_path.name)
    _text_write(root / "Configurar_e_Abrir.ps1", _powershell_launcher())
    _text_write(root / "Abrir_PowerBI.cmd", _cmd_launcher())
    _text_write(root / "VERIFICAR_MEDIDAS.dax", _verification_dax())
    _text_write(root / "LEIA-ME.txt", _readme(excel_path.name, start_period, end_period))


def _iter_json_files(root: Path) -> Iterable[Path]:
    yield from sorted(path for path in root.rglob("*.json") if path.is_file())
    yield from sorted(path for path in root.rglob("*.pbir") if path.is_file())
    yield from sorted(path for path in root.rglob("*.pbism") if path.is_file())
    yield from sorted(path for path in root.rglob("*.pbip") if path.is_file())


def _field_reference_from_expression(expression: dict[str, Any]) -> str:
    for kind in ("Column", "Measure"):
        node = expression.get(kind)
        if not isinstance(node, dict):
            continue
        source = (node.get("Expression") or {}).get("SourceRef") or {}
        table = str(source.get("Entity") or "")
        field = str(node.get("Property") or "")
        if table and field:
            return f"{table}.{field}"
    return ""


def _validate_field_reference(
    reference: str,
    known_fields: dict[str, set[str]],
    context: Path,
) -> None:
    if "." not in reference:
        raise PowerBIProjectError(f"Referência inválida em {context}: {reference}")
    table, field = reference.split(".", 1)
    if field not in known_fields.get(table, set()):
        raise PowerBIProjectError(f"Campo inexistente em {context}: {reference}")


def _verification_dax() -> str:
    return """// Execute no modo Consulta DAX do Power BI Desktop após Atualizar.
// Sem filtros do relatório. Compare com CONTROLE_FONTE.json; US$ x100 = centavos.
EVALUATE
ROW(
    "CIF US$", [Valor CIF], "FOB US$", [Valor FOB], "Frete US$", [Frete],
    "Seguro US$", [Seguro], "Peso kg", [Peso líquido (kg)],
    "Registros gerais", [Registros estatísticos], "NCMs", [NCMs ativos],
    "Registros gerais sem peso", [Registros sem peso],
    "FOB municipal US$", [Valor FOB Municipal], "Peso municipal kg", [Peso municipal (kg)],
    "Registros municipais", [Registros estatísticos municipais], "Municípios / UF", [Municípios ativos],
    "Registros municipais sem peso", [Registros municipais sem peso]
)

EVALUATE
SUMMARIZECOLUMNS(
    'Calendario'[Período], 'Calendario'[Índice mês],
    "CIF US$", [Valor CIF], "FOB US$", [Valor FOB], "Frete US$", [Frete],
    "Seguro US$", [Seguro], "Peso kg", [Peso líquido (kg)],
    "Registros gerais", [Registros estatísticos],
    "FOB municipal US$", [Valor FOB Municipal], "Peso municipal kg", [Peso municipal (kg)],
    "Registros municipais", [Registros estatísticos municipais]
)
ORDER BY 'Calendario'[Índice mês]
"""


def validate_powerbi_project(root: Path) -> dict[str, int]:
    """Valida o contrato do projeto antes da gravação atômica do pacote.

    Complementa os schemas públicos: referências reais do TMDL, tipos de
    projeção, geometria, relacionamentos, sincronização e integridade da fonte.
    Não executa DAX ou refresh M; essas etapas pertencem ao Power BI Desktop.
    """
    root = Path(root)
    model = root / MODEL_DIR_NAME
    definition = model / "definition"
    report = root / REPORT_DIR_NAME
    tables = semantic.tables()
    required = [
        root / PBIP_FILE_NAME,
        model / "definition.pbism",
        model / ".platform",
        report / "definition.pbir",
        report / ".platform",
        definition / "database.tmdl",
        definition / "model.tmdl",
        definition / "expressions.tmdl",
        definition / "relationships.tmdl",
        report / "definition" / "report.json",
        report / "definition" / "version.json",
        root / "CONTROLE_FONTE.json",
        root / "LEIA-ME.txt",
        root / "Abrir_PowerBI.cmd",
        root / "Configurar_e_Abrir.ps1",
        root / "VERIFICAR_MEDIDAS.dax",
        *(definition / "tables" / (t.name + ".tmdl") for t in tables),
    ]
    for path in required:
        if not path.is_file():
            raise PowerBIProjectError(f"Arquivo necessário ausente: {path.relative_to(root)}")
    json_count = 0
    for path in _iter_json_files(root):
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            raise PowerBIProjectError(f"JSON inválido em {path.relative_to(root)}") from exc
        json_count += 1

    def read(path):
        return json.loads(path.read_text(encoding="utf-8"))

    def fail(message):
        raise PowerBIProjectError(message)

    # TMDL é inspecionado; uma lista estática de campos não mascarará uma remoção.
    known = {}
    declaration = re.compile(r"^\t(column|measure) ('(?:[^']|'')*'|[^\s=]+)(?:\s*=)?", re.M)
    for table in tables:
        text = (definition / "tables" / (table.name + ".tmdl")).read_text(encoding="utf-8")
        fields = {}
        for kind, token in declaration.findall(text):
            name = token[1:-1].replace("''", "'") if token.startswith("'") else token
            if name in fields:
                fail("Campo duplicado no modelo: " + table.name + "." + name)
            fields[name] = kind
        expected = {c.name: "column" for c in table.columns} | {
            m.name: "measure" for m in table.measures
        }
        if fields != expected:
            fail("Campos divergentes no TMDL: " + table.name)
        # O modelo declarativo é a autoridade para tipos, formatos e expressões.
        if text != semantic.table_tmdl(table):
            fail("Definição semântica divergente: " + table.name)
        known[table.name] = fields
    actual_relationships = (definition / "relationships.tmdl").read_text(encoding="utf-8")
    if actual_relationships != semantic.relationship_tmdl():
        fail("Relacionamentos ou cardinalidades divergentes.")
    model_text = (definition / "model.tmdl").read_text(encoding="utf-8")
    if "returnErrorValuesAsNull" in model_text:
        fail("O modelo não pode ocultar erros de origem.")
    if "discourageImplicitMeasures" not in model_text:
        fail("O modelo exige medidas explícitas.")
    pbir = read(report / "definition.pbir")
    if pbir.get("datasetReference") != {"byPath": {"path": "../" + MODEL_DIR_NAME}}:
        fail("Vínculo portátil do modelo inválido.")
    report_json = read(report / "definition" / "report.json")
    for package in report_json.get("resourcePackages", []):
        for resource in package.get("items", []):
            name = str(resource.get("path", ""))
            if not name or name != posixpath.basename(name):
                fail("Recurso com caminho inválido.")
            if not (report / "StaticResources" / package["name"] / name).is_file():
                fail("Recurso do relatório ausente: " + name)
    theme = read(report / "StaticResources" / "RegisteredResources" / visuals.THEME_FILE)
    if theme.get("name") != visuals.THEME_FILE:
        fail("Nome do tema divergente.")
    pages_root = report / "definition" / "pages"
    metadata = read(pages_root / "pages.json")
    order = metadata.get("pageOrder", [])
    expected_pages = visuals.pages()
    if (
        len(order) != len(expected_pages)
        or len(set(order)) != len(order)
        or metadata.get("activePageName") != order[0]
    ):
        fail("Ordem de páginas inválida.")
    ids = set()
    count = 0
    groups = {}
    for page_name, (title, specs) in zip(order, expected_pages, strict=True):
        page_dir = pages_root / page_name
        page = read(page_dir / "page.json")
        if page.get("name") != page_name or page.get("displayName") != title:
            fail("Identificação de página divergente.")
        if (page.get("width"), page.get("height")) != (CANVAS_WIDTH, CANVAS_HEIGHT):
            fail("Dimensão de página divergente.")
        files = sorted((page_dir / "visuals").glob("*/visual.json"))
        if len(files) != len(specs):
            fail("Quantidade de visuais divergente na página " + title)
        rects = []
        tabs = set()
        for file in files:
            item = read(file)
            name = item.get("name")
            pos = item.get("position", {})
            v = item.get("visual", {})
            if not name or name in ids or name != file.parent.name:
                fail("ID visual ausente, duplicado ou divergente.")
            ids.add(name)
            coords = [pos.get(k) for k in ("x", "y", "width", "height")]
            if any(
                isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n)
                for n in coords
            ):
                fail("Geometria visual não finita.")
            x, y, w, h = coords
            if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > CANVAS_WIDTH or y + h > CANVAS_HEIGHT:
                fail("Visual fora do canvas.")
            if any(
                x < rx + rw and x + w > rx and y < ry + rh and y + h > ry
                for rx, ry, rw, rh in rects
            ):
                fail("Visuais sobrepostos na página " + title)
            rects.append((x, y, w, h))
            tab = pos.get("tabOrder")
            if tab in tabs:
                fail("Ordem de tabulação duplicada.")
            tabs.add(tab)
            if not v.get("visualContainerObjects", {}).get("general"):
                fail("Descrição de acessibilidade ausente.")
            query = v.get("query", {})
            state = query.get("queryState", {})
            for role, data in state.items():
                for projection in data.get("projections", []):
                    field = projection.get("field", {})
                    ref = _field_reference_from_expression(field)
                    _validate_field_reference(ref, {t: set(fs) for t, fs in known.items()}, file)
                    if projection.get("queryRef") != ref:
                        fail("Projeção divergente da expressão do campo.")
                    table, field_name = ref.split(".", 1)
                    kind = known[table][field_name]
                    if ("Measure" if kind == "measure" else "Column") not in field:
                        fail("Tipo incorreto de projeção.")
                    if role in ("Y", "Data", "Tooltips") and kind != "measure":
                        fail("Agregação numérica implícita não permitida: " + ref)
            if v.get("visualType") == "tableEx":
                # Flat statistical detail uses a single fact; no cross-dimension
                # query or total of per-row prices is needed to display records.
                if set(state) != {"Values"}:
                    fail("Tabela detalhada deve usar somente o papel Values.")
                projections = state["Values"].get("projections", [])
                source = "Municipios" if title == "Análise Municipal" else "Importacoes"
                if not projections or any(
                    "Column" not in item.get("field", {})
                    or not item.get("queryRef", "").startswith(source + ".")
                    or "active" in item
                    for item in projections
                ):
                    fail(
                        "Tabela detalhada exige colunas da mesma base, sem medidas ou níveis ativos."
                    )
                total = v.get("objects", {}).get("total", [])
                if (
                    not total
                    or total[0]
                    .get("properties", {})
                    .get("totals", {})
                    .get("expr", {})
                    .get("Literal", {})
                    .get("Value")
                    != "false"
                ):
                    fail("Tabela de registros não deve somar preços unitários no total.")
            for sort in query.get("sortDefinition", {}).get("sort", []):
                _validate_field_reference(
                    _field_reference_from_expression(sort.get("field", {})),
                    {t: set(fs) for t, fs in known.items()},
                    file,
                )
            if v.get("visualType") == "slicer":
                group = v.get("syncGroup", {}).get("groupName", "")
                expected_prefix = "municipal_" if title == "Análise Municipal" else "geral_"
                if not group.startswith(expected_prefix):
                    fail("Filtros municipais e gerais devem ter grupos separados.")
                projections = state.get("Values", {}).get("projections", [])
                if len(projections) != 1:
                    fail("Segmentador com campo inválido.")
                ref = projections[0]["queryRef"]
                if group in groups and groups[group] != ref:
                    fail("Grupo de filtros com campos divergentes.")
                groups[group] = ref
            count += 1
    excel_files = list((root / "Dados").glob("*.xlsx"))
    if len(excel_files) != 1:
        fail("O pacote deve conter exatamente um Excel em Dados.")
    controls = read(root / "CONTROLE_FONTE.json")
    with excel_files[0].open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if controls.get("sha256") != digest:
        fail("O hash do Excel diverge do controle da fonte.")
    expressions = (definition / "expressions.tmdl").read_text(encoding="utf-8")
    if "__LIARTE_EXCEL_PATH__" not in expressions:
        fail("Marcador portátil da fonte ausente.")
    return {
        "pages": len(order),
        "visuals": count,
        "json_files": json_count,
        "measures": sum(len(t.measures) for t in tables),
    }


def _zip_tree(source_dir: Path, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(f".{output_path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with zipfile.ZipFile(
            temporary,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
        ) as archive:
            for path in sorted(source_dir.rglob("*")):
                if path.is_file():
                    # XLSX já é um ZIP comprimido: preserva seus bytes sem
                    # recompressão cara. Os arquivos do modelo seguem comprimidos.
                    archive.write(
                        path,
                        path.relative_to(source_dir).as_posix(),
                        compress_type=zipfile.ZIP_STORED
                        if path.suffix.lower() == ".xlsx"
                        else zipfile.ZIP_DEFLATED,
                    )
        with zipfile.ZipFile(temporary) as archive:
            bad_file = archive.testzip()
            if bad_file:
                raise PowerBIProjectError(f"Arquivo corrompido dentro do ZIP: {bad_file}")
        try:
            temporary.replace(output_path)
        except PermissionError as exc:
            raise PowerBIProjectError(
                f"Não foi possível salvar {output_path.name}. Feche o arquivo e tente novamente."
            ) from exc
    finally:
        temporary.unlink(missing_ok=True)


def create_powerbi_package(
    excel_path: Path,
    output_path: Path,
    start_period: str,
    end_period: str,
    *,
    progress_callback: Callable[[float, str], None] | None = None,
) -> dict[str, Any]:
    """Cria e valida o pacote ZIP contendo o projeto PBIP e o Excel fonte."""

    def report(percent: float, message: str) -> None:
        if progress_callback is not None:
            progress_callback(percent, message)

    report(0, "Conferindo o Excel de origem do Power BI")
    excel_path = excel_path.expanduser().resolve()
    output_path = output_path.expanduser().resolve()
    if not excel_path.is_file():
        raise FileNotFoundError(f"Planilha de origem não encontrada: {excel_path}")
    if excel_path.suffix.casefold() != ".xlsx":
        raise ValueError("A origem do Power BI deve ser uma planilha .xlsx.")
    period_pattern = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
    if not period_pattern.fullmatch(start_period) or not period_pattern.fullmatch(end_period):
        raise ValueError("O período do Power BI deve estar no formato AAAA-MM.")
    if start_period > end_period:
        raise ValueError("O período inicial não pode ser posterior ao final.")
    if start_period < MIN_POWERBI_PERIOD:
        raise ValueError(f"Os dados gerais do Comex Stat começam em {MIN_POWERBI_PERIOD}.")
    manifest = _validate_excel_source(
        excel_path, lambda: report(3, "Conferindo a estrutura do Excel")
    )
    report(10, "Conferindo valores, códigos e totais do Excel")
    try:
        controls = audit_source(
            excel_path,
            manifest,
            start_period,
            end_period,
            lambda: report(10, "Conferindo valores e totais do Excel"),
        )
    except (ValueError, ArithmeticError, ElementTree.ParseError, KeyError, IndexError) as exc:
        raise PowerBIProjectError(f"A fonte do Power BI não passou na conferência: {exc}") from exc
    if output_path.suffix.casefold() != ".zip":
        output_path = output_path.with_suffix(".zip")

    with tempfile.TemporaryDirectory(prefix="liarte-powerbi-") as temporary:
        project_root = Path(temporary) / _safe_stem(PROJECT_NAME)
        project_root.mkdir(parents=True, exist_ok=True)
        report(20, "Montando o modelo e as páginas do Power BI")
        _build_project_tree(project_root, excel_path, start_period, end_period)
        _json_write(project_root / "CONTROLE_FONTE.json", controls)
        report(65, "Validando medidas, relacionamentos e gráficos do Power BI")
        stats = validate_powerbi_project(project_root)
        report(80, "Preparando o pacote Power BI para download")
        _zip_tree(project_root, output_path)
        report(100, "Pacote Power BI concluído")
    return {
        "path": output_path,
        "file_name": output_path.name,
        "pages": stats["pages"],
        "visuals": stats["visuals"],
        "size": output_path.stat().st_size,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Gera um projeto Power BI executivo a partir do Excel de importações."
    )
    parser.add_argument("excel", type=Path, help="Excel IMPORTACAO_*.xlsx gerado pelo sistema.")
    parser.add_argument("--inicio", required=True, help="Período inicial em AAAA-MM.")
    parser.add_argument("--fim", required=True, help="Período final em AAAA-MM.")
    parser.add_argument("--saida", type=Path, help="ZIP de saída. Padrão: ao lado do Excel.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = create_powerbi_package(
            args.excel,
            args.saida or default_powerbi_path(args.excel),
            args.inicio,
            args.fim,
        )
    except (FileNotFoundError, OSError, PowerBIProjectError, ValueError) as exc:
        print(f"Erro: {exc}")
        return 1
    print(
        f"Projeto Power BI criado: {result['path']} "
        f"({result['pages']} páginas, {result['visuals']} visuais)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
