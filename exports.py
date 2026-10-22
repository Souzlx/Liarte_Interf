"""Exportações reais: Excel/BI do período inteiro; PDF do recorte selecionado."""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import tempfile
from threading import Event
from liarte_engine import comexstat_importacoes as engine
from liarte_engine.pdf_importacoes import create_import_pdf
from liarte_engine.powerbi_importacoes import create_powerbi_package
from liarte_engine.liarte_dados import atomic_json, file_sha256
from .comex import Snapshot
from .domain import (
    Selection,
    search_key,
    period_label,
    record_predicate,
    selected_values,
)
from .query import checkpoint


@dataclass(frozen=True, slots=True)
class ExportRequest:
    kind: str
    destination: Path
    snapshot: Snapshot
    selection: Selection
    monthly_sheets: bool = True


def pdf_source(request, cancel):
    selection = request.selection
    if selection.kind != "general":
        raise ValueError("O PDF comercial utiliza a Base geral por NCM, UF e URF.")
    if len(request.snapshot.general) != len(request.snapshot.general_records):
        raise ValueError("A base geral está incompleta. Consulte novamente o período.")
    selected = []
    terms = tuple(search_key(selection.search.strip()).split())
    matches = record_predicate(selection)
    for i, (raw, row) in enumerate(
        zip(request.snapshot.general, request.snapshot.general_records, strict=True)
    ):
        if i % 512 == 0:
            checkpoint(cancel)
        if not matches(row):
            continue
        text = search_key(
            " ".join(
                (
                    row.ncm,
                    row.product,
                    row.state,
                    row.country,
                    row.port,
                    row.period,
                    period_label(row.period),
                    row.official_description,
                )
            )
        )
        if all(term in text for term in terms):
            selected.append(raw)
    return selected


def export_document(
    request: ExportRequest, cancel: Event, progress, audit_directory: Path
):
    if request.kind not in ("excel", "powerbi", "pdf"):
        raise ValueError("Formato de exportação inválido.")
    checkpoint(cancel)
    destination = Path(request.destination).expanduser().resolve()
    expected = {"excel": ".xlsx", "powerbi": ".zip", "pdf": ".pdf"}[request.kind]
    if destination.suffix.lower() != expected:
        raise ValueError(f"Escolha um arquivo {expected}.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    snapshot = request.snapshot
    period = snapshot.period
    if len(snapshot.general) != len(snapshot.general_records) or len(
        snapshot.municipal
    ) != len(snapshot.municipal_records):
        raise ValueError(
            "Os dados carregados estão incompletos. Consulte novamente o período."
        )
    if request.selection.period != period:
        raise ValueError(
            "O período selecionado difere dos dados carregados. Consulte o período antes de exportar."
        )
    pairs = engine.internal_product_ncms()

    def report(percent, message):
        checkpoint(cancel)
        progress(max(0, min(100, int(percent))), message)

    # Stage in the destination filesystem, preserving the previous file on
    # failure/cancellation. The native file dialog confirms overwriting first.
    with tempfile.TemporaryDirectory(
        prefix=".liarte-export-", dir=destination.parent
    ) as temporary:
        staged = Path(temporary) / destination.name
        if request.kind == "pdf":
            report(5, "Aplicando os filtros do PDF")
            raw = pdf_source(request, cancel)
            report(20, "Montando páginas A4 e conferindo cabeçalhos")
            details = create_import_pdf(
                staged,
                pairs,
                raw,
                period.start,
                period.end,
                {
                    "ncm": selected_values(request.selection, "ncm"),
                    "country": selected_values(request.selection, "country"),
                    "state": selected_values(request.selection, "state"),
                    "urf": selected_values(request.selection, "port"),
                },
            )
        else:
            excel = (
                staged
                if request.kind == "excel"
                else Path(temporary) / f"IMPORTACAO_{period.start}_{period.end}.xlsx"
            )
            ceiling = 98 if request.kind == "excel" else 65
            engine.create_report(
                excel,
                pairs,
                snapshot.general,
                period.start,
                period.end,
                request.monthly_sheets,
                snapshot.municipal,
                progress_callback=lambda p, m: report(p * ceiling / 100, m),
            )
            if request.kind == "powerbi":
                details = create_powerbi_package(
                    excel,
                    staged,
                    period.start,
                    period.end,
                    progress_callback=lambda p, m: report(65 + p * 0.34, m),
                )
            else:
                details = {
                    "rows": len(snapshot.general),
                    "municipal_rows": len(snapshot.municipal),
                }
        report(99, "Publicando o arquivo conferido")
        digest = file_sha256(staged)
        checkpoint(cancel)
        os.replace(staged, destination)
    audit = {
        "format": request.kind,
        "file": str(destination),
        "sha256": digest,
        "period": {"from": period.start, "to": period.end},
        "published_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_updated": snapshot.availability.updated,
        "municipal_source_updated": snapshot.availability.municipal_updated,
        "totals_verified": snapshot.totals_verified,
        "response_validated": snapshot.response_validated,
        "source_channels": list(snapshot.source_channels),
        "verification": (
            "Conferência adicional de totais por produto/mês na fonte oficial."
            if snapshot.totals_verified
            else "Validação da resposta recebida: estrutura, período, códigos, duplicidades e valores exatos; CIF = FOB + frete + seguro. Sem consulta adicional de totais."
        ),
        "fetched_at": snapshot.fetched_at,
        "general_records": len(snapshot.general),
        "municipal_records": len(snapshot.municipal),
        "filtered_pdf": request.kind == "pdf",
    }
    # Audit failure cannot turn a successfully saved document into a failed job.
    try:
        atomic_json(Path(audit_directory) / (digest + ".json"), audit)
    except OSError:
        pass
    progress(100, "Arquivo salvo")
    return {
        "path": str(destination),
        "name": destination.name,
        "sha256": digest,
        "format": request.kind,
        **{k: v for k, v in details.items() if k not in ("path", "file_name")},
    }
