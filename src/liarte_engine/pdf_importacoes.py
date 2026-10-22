#!/usr/bin/env python3
"""Gera uma relação A4 filtrada e pronta para impressão das importações."""

from __future__ import annotations

from .commercial_names import COMMERCIAL_NAMES_BY_NCM

from .liarte_analise import selection_values
from .numeric import from_units, published_units

import os
import re
import tempfile
import unicodedata
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP, localcontext
from pathlib import Path
from typing import Any, Mapping, Sequence
from xml.sax.saxutils import escape

try:
    from pypdf import PdfReader
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.platypus import (
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )
except ImportError as exc:  # pragma: no cover - mensagem amigável no dashboard
    raise SystemExit(
        "Dependência PDF ausente. Execute: python -m pip install -r requirements.txt"
    ) from exc

from .comexstat_importacoes import (
    clean_text,
    normalize_ncm,
    state_abbreviation,
)


PDF_GENERATOR_VERSION = "5.0.0-rc.9"
PDF_LOGO_PATH = (
    Path(__file__).resolve().parents[1] / "liarte_desktop/assets/liarte-logo-transparente.png"
)
MIN_RELEVANT_KG = 1_000.0
PDF_HEADERS = (
    "Descrição NCM",
    "UF",
    "País",
    "URF",
    "Peso líq. (kg)",
    "US$/kg",
)

# Vocabulário comercial usado exclusivamente no relatório para impressão.
# O cadastro interno seleciona os NCMs, mas seus códigos de produto (G10, G12,
# S34 etc.) não são úteis para a equipe comercial no relatório impresso.

COUNTRY_DISPLAY_NAMES: dict[str, str] = {
    "HOLANDA": "Holanda",
    "PAISES BAIXOS": "Holanda",
    "PAISES BAIXOS (HOLANDA)": "Holanda",
    "TAIWAN": "Taiwan",
    "TAIWAN (FORMOSA)": "Taiwan",
}


class PdfGenerationError(RuntimeError):
    """Falha ao montar ou validar o PDF de impressão."""


def _key(value: Any) -> str:
    text = clean_text(value)
    text = unicodedata.normalize("NFKD", text)
    return "".join(char for char in text if not unicodedata.combining(char)).upper()


def is_airport_urf(value: Any) -> bool:
    """Identifica unidades aduaneiras aeroportuárias sem confundir Porto Alegre."""
    key = _key(value)
    return any(
        marker in key
        for marker in (
            "AEROPORTO",
            "AEROPORTUARIA",
            "AEROPORTUARIO",
            "AIRPORT",
            "AEROP.",
        )
    )


def port_name(value: Any) -> str:
    """Remove códigos e siglas administrativas, preservando o nome da localidade."""
    label = clean_text(value)
    if not label:
        return "-"

    parts = re.split(r"\s+[-–—]\s+", label, maxsplit=1)
    if len(parts) == 2:
        prefix = _key(parts[0])
        if prefix.isdigit() or prefix in {"ALF", "IRF", "DRF", "SRRF"}:
            label = clean_text(parts[1])

    label = re.sub(r"^\s*\d{4,}\s*[-–—:/]?\s*", "", label).strip()
    label = re.sub(
        r"^\s*(?:ALF|IRF|DRF|SRRF)\b\s*[-–—:/]?\s*",
        "",
        label,
        flags=re.IGNORECASE,
    ).strip()
    port_match = re.search(r"\bPORTO\b.*$", label, flags=re.IGNORECASE)
    if port_match:
        label = port_match.group(0).strip()
    return label or "-"


def _format_pt(value, maximum_decimals):
    amount = Decimal(str(value))
    if not amount.is_finite():
        return "-"
    with localcontext() as context:
        context.prec = max(28, amount.adjusted() + maximum_decimals + 4)
        amount = amount.quantize(Decimal(1).scaleb(-maximum_decimals), rounding=ROUND_HALF_UP)
    rendered = f"{amount:,.{maximum_decimals}f}"
    if maximum_decimals:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered.translate(str.maketrans({",": ".", ".": ","}))


def _paragraph_text(value: Any) -> str:
    """Escapa dados externos antes de entregá-los ao interpretador do ReportLab."""
    return escape(clean_text(value)) or "-"


def display_country(value: Any) -> str:
    """Retorna o país em forma curta, sem qualificadores históricos."""
    country = clean_text(value)
    if not country:
        return "-"
    return COUNTRY_DISPLAY_NAMES.get(_key(country), country)


def commercial_product_name(ncm: Any, official_description: Any = "") -> str:
    """Converte o NCM em nome comercial claro para a equipe de vendas."""
    normalized_ncm = normalize_ncm(ncm)
    if normalized_ncm in COMMERCIAL_NAMES_BY_NCM:
        return COMMERCIAL_NAMES_BY_NCM[normalized_ncm]

    description = clean_text(official_description)
    if not description:
        return "Produto sem descrição"

    # Mantém o PDF legível também para NCMs futuros que ainda não estejam no
    # dicionário, simplificando as nomenclaturas oficiais mais recorrentes.
    substitutions = (
        (r"^Ésteres? de etila do ácido acrílico$", "Acrilato de etila"),
        (r"^Ésteres? de butila do ácido acrílico$", "Acrilato de butila"),
        (r"^Ésteres? de 2-etilexila do ácido acrílico$", "Acrilato 2-etilexila"),
        (r"^Ésteres? de metila do ácido metacrílico$", "Metacrilato de metila"),
        (r"^Ésteres? de n?-?butila do ácido metacrílico$", "Metacrilato de butila"),
        (r"^Acetonas que não contenham outras funções oxigenadas$", "Acetona"),
        (r"^Butanona\s*\(metiletilcetona\)$", "Metiletilcetona"),
    )
    for pattern, replacement in substitutions:
        if re.fullmatch(pattern, description, flags=re.IGNORECASE):
            return replacement
    return description


def consolidate_pdf_rows(
    pairs: Sequence[Any],
    api_rows: Sequence[dict[str, Any]],
    selected_product: str = "",
) -> list[dict[str, Any]]:
    """Consolida somente importações relevantes e calcula US$/kg ponderado."""
    # Parâmetros preservados para compatibilidade com o dashboard e eventuais
    # integrações existentes. A descrição impressa é determinada pelo NCM.
    _ = (pairs, selected_product)
    # Commercial names and shortened port names are presentation labels, not
    # statistical identities. Distinct NCMs/URFs must never be merged by label.
    grouped = defaultdict(lambda: {"kg": 0, "cif_cents": 0, "description": "", "port": ""})
    for row in api_rows:
        ncm = normalize_ncm(row.get("coNcm"))
        if not ncm:
            continue
        kg = published_units(row.get("metricKG"))
        if kg <= MIN_RELEVANT_KG:
            continue
        if is_airport_urf(row.get("urf")):
            continue
        description = commercial_product_name(ncm, row.get("ncm"))
        key = (
            ncm,
            state_abbreviation(row.get("state")) or "-",
            display_country(row.get("country")),
            clean_text(row.get("urf")),
        )
        grouped[key]["kg"] += kg
        grouped[key]["cif_cents"] += published_units(row.get("metricCIF"), places=2)
        grouped[key]["description"] = description
        grouped[key]["port"] = port_name(row.get("urf"))

    result: list[dict[str, Any]] = []
    for (_, state, country, _), metrics in grouped.items():
        kg = Decimal(metrics["kg"])
        cif = from_units(metrics["cif_cents"])
        with localcontext() as context:
            context.prec = 40
            price = cif / kg if kg else None
        result.append(
            {
                "description": metrics["description"],
                "state": state,
                "country": country,
                "urf": metrics["port"],
                "kg": kg,
                "usd_per_kg": price,
            }
        )
    return sorted(
        result,
        key=lambda item: (
            str(item["description"]).casefold(),
            str(item["state"]),
            str(item["country"]),
            str(item["urf"]).casefold(),
        ),
    )


def default_pdf_name(start_period: str, end_period: str) -> str:
    return f"IMPORTACOES_FILTRADAS_{start_period}_{end_period}.pdf"


def _filter_summary(filters: Mapping[str, Any]) -> str:
    items: list[str] = []
    names = list(
        dict.fromkeys(
            commercial_product_name(code) for code in selection_values(filters.get("ncm"), "NCM")
        )
    )
    if names:
        items.append("Produto: " + ", ".join(names))
    for key, label, display in (
        ("country", "País", display_country),
        ("state", "UF", state_abbreviation),
        ("urf", "URF", port_name),
    ):
        values = selection_values(filters.get(key), label)
        if values:
            items.append(
                label + ": " + ", ".join(dict.fromkeys(display(value) for value in values))
            )
    return f"Filtros: {' - '.join(items)}" if items else ""


def create_import_pdf(
    output_path: Path,
    pairs: Sequence[Any],
    api_rows: Sequence[dict[str, Any]],
    start_period: str,
    end_period: str,
    active_filters: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Cria um PDF A4 compacto com o cabeçalho repetido em cada página."""
    filters = dict(active_filters or {})
    rows = consolidate_pdf_rows(
        pairs,
        api_rows,
        selected_product=clean_text(filters.get("product")),
    )
    if not rows:
        raise ValueError(
            "Nenhuma importação relevante corresponde aos filtros. "
            "O PDF considera apenas volumes acima de 1.000 kg e exclui aeroportos."
        )

    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    period = f"{start_period} a {end_period}"
    summary = _filter_summary(filters)
    # O mesmo recurso original da interface é incluído também no executável.
    # A marca ocupa apenas o cabeçalho já reservado, sem tocar no Frame da tabela.
    try:
        logo = ImageReader(str(PDF_LOGO_PATH))
        logo_width, logo_height = logo.getSize()
        if logo_width <= 0 or logo_height <= 0:
            raise ValueError("Dimensões inválidas da marca.")
    except Exception as exc:
        raise PdfGenerationError(
            "A logo do relatório não pôde ser carregada. Repare a instalação do aplicativo."
        ) from exc
    page_size = A4
    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "LiarteBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=7.0,
        leading=8.4,
        textColor=colors.HexColor("#142638"),
        alignment=TA_LEFT,
    )
    center = ParagraphStyle("LiarteCenter", parent=body, alignment=TA_CENTER)
    right = ParagraphStyle("LiarteRight", parent=body, alignment=TA_RIGHT)
    header = ParagraphStyle(
        "LiarteHeader",
        parent=body,
        fontName="Helvetica-Bold",
        fontSize=7.0,
        leading=8.2,
        textColor=colors.white,
        alignment=TA_CENTER,
    )

    table_data: list[list[Any]] = [
        [Paragraph(_paragraph_text(label), header) for label in PDF_HEADERS]
    ]
    for item in rows:
        unit_value = item["usd_per_kg"]
        table_data.append(
            [
                Paragraph(_paragraph_text(item["description"]), body),
                Paragraph(_paragraph_text(item["state"]), center),
                Paragraph(_paragraph_text(item["country"]), body),
                Paragraph(_paragraph_text(item["urf"]), body),
                Paragraph(_paragraph_text(_format_pt(item["kg"], 3)), right),
                Paragraph(
                    _paragraph_text(_format_pt(unit_value, 3) if unit_value is not None else "-"),
                    right,
                ),
            ]
        )

    column_widths = (
        45 * mm,
        12 * mm,
        30 * mm,
        54 * mm,
        25 * mm,
        20 * mm,
    )

    def measured_height(row: list[Any]) -> float:
        content_height = max(
            cell.wrap(width - 7, page_size[1])[1] for cell, width in zip(row, column_widths, strict=True)
        )
        return content_height + 7

    header_height = measured_height(table_data[0])
    # Reserva também o preenchimento interno do Frame do ReportLab. Essa folga
    # impede que a última linha seja empurrada isoladamente para outra página.
    available_table_height = page_size[1] - (23 * mm) - (13 * mm) - (10 * mm)
    body_capacity = available_table_height - header_height
    pages: list[list[tuple[int, list[Any], float]]] = []
    current_page: list[tuple[int, list[Any], float]] = []
    current_height = 0.0
    for global_index, row in enumerate(table_data[1:], start=1):
        height = measured_height(row)
        if current_page and current_height + height > body_capacity:
            pages.append(current_page)
            current_page = []
            current_height = 0.0
        current_page.append((global_index, row, height))
        current_height += height
    if current_page:
        pages.append(current_page)

    def page_table(entries: list[tuple[int, list[Any], float]]) -> Table:
        page_rows = [table_data[0], *(entry[1] for entry in entries)]
        row_heights = [header_height, *(entry[2] for entry in entries)]
        table = Table(
            page_rows,
            colWidths=column_widths,
            rowHeights=row_heights,
            repeatRows=1,
            splitByRow=1,
            hAlign="CENTER",
        )
        style_commands: list[tuple[Any, ...]] = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E78")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#B8C7D3")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 3.5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3.5),
            ("TOPPADDING", (0, 0), (-1, -1), 3.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ]
        for local_index, (global_index, _row, _height) in enumerate(entries, start=1):
            if global_index % 2 == 0:
                style_commands.append(
                    (
                        "BACKGROUND",
                        (0, local_index),
                        (-1, local_index),
                        colors.HexColor("#EEF4F8"),
                    )
                )
        table.setStyle(TableStyle(style_commands))
        return table

    def page_header_footer(canvas: Any, document: Any) -> None:
        canvas.saveState()
        width, height = page_size
        brand_width = 24 * mm
        brand_height = brand_width * logo_height / logo_width
        canvas.drawImage(
            logo,
            14 * mm,
            height - 14.5 * mm,
            width=brand_width,
            height=brand_height,
            preserveAspectRatio=True,
            mask="auto",
        )
        canvas.setFillColor(colors.HexColor("#0B1F35"))
        canvas.setFont("Helvetica-Bold", 11)
        canvas.drawString(42 * mm, height - 11 * mm, "Importações filtradas")
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor("#4B6478"))
        canvas.drawRightString(width - 14 * mm, height - 11 * mm, f"Período: {period}")
        available = width - 28 * mm
        if summary:
            compact_summary = summary
            while (
                stringWidth(compact_summary, "Helvetica", 7.2) > available
                and len(compact_summary) > 24
            ):
                compact_summary = compact_summary[:-6].rstrip() + "..."
            canvas.setFont("Helvetica", 7.2)
            canvas.drawString(14 * mm, height - 16 * mm, compact_summary)
        canvas.setStrokeColor(colors.HexColor("#18B7B1"))
        canvas.setLineWidth(0.8)
        canvas.line(14 * mm, height - 19 * mm, width - 14 * mm, height - 19 * mm)
        canvas.setFillColor(colors.HexColor("#6B7E8F"))
        canvas.setFont("Helvetica", 7)
        canvas.drawRightString(width - 14 * mm, 8 * mm, f"Página {document.page}")
        canvas.restoreState()

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{output_path.stem}-",
            suffix=".pdf",
            dir=output_path.parent,
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
        document = SimpleDocTemplate(
            str(temporary_path),
            pagesize=page_size,
            leftMargin=12 * mm,
            rightMargin=12 * mm,
            topMargin=23 * mm,
            bottomMargin=13 * mm,
            title=f"Importações filtradas - {period}",
            author="LIARTE",
            creator=f"LIARTE Comex Intelligence {PDF_GENERATOR_VERSION}",
            subject="Relação filtrada de importações para impressão",
        )
        story: list[Any] = []
        for page_number, entries in enumerate(pages):
            if page_number:
                story.append(PageBreak())
            story.extend((Spacer(1, 1 * mm), page_table(entries)))
        document.build(
            story,
            onFirstPage=page_header_footer,
            onLaterPages=page_header_footer,
        )

        reader = PdfReader(str(temporary_path))
        if not reader.pages:
            raise PdfGenerationError("O PDF foi criado sem páginas.")
        for page_number, page in enumerate(reader.pages, start=1):
            extracted = page.extract_text() or ""
            if not all(label in extracted for label in PDF_HEADERS):
                raise PdfGenerationError(
                    f"O cabeçalho da tabela não foi repetido corretamente na página {page_number}."
                )
            images = page["/Resources"].get("/XObject", {})
            if not any(item.get_object().get("/Subtype") == "/Image" for item in images.values()):
                raise PdfGenerationError(
                    f"A logo não foi incorporada corretamente na página {page_number}."
                )
        os.replace(temporary_path, output_path)
        temporary_path = None
    except (ValueError, PdfGenerationError):
        raise
    except Exception as exc:
        raise PdfGenerationError(f"Não foi possível montar o PDF: {exc}") from exc
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    return {
        "path": str(output_path),
        "file_name": output_path.name,
        "pages": len(reader.pages),
        "rows": len(rows),
        "logo": True,
    }


__all__ = [
    "PDF_GENERATOR_VERSION",
    "MIN_RELEVANT_KG",
    "COMMERCIAL_NAMES_BY_NCM",
    "COUNTRY_DISPLAY_NAMES",
    "PdfGenerationError",
    "commercial_product_name",
    "consolidate_pdf_rows",
    "create_import_pdf",
    "default_pdf_name",
    "display_country",
    "is_airport_urf",
    "port_name",
]
