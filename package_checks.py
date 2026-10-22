"""Autoteste offline do pacote compilado. Fixtures explicitamente sintéticas e temporárias."""

from pathlib import Path
import tempfile
from liarte_engine import comexstat_importacoes as engine
from liarte_engine.pdf_importacoes import create_import_pdf
from liarte_engine.powerbi_importacoes import create_powerbi_package


def verify_document_resources():
    general = {
        "coNcm": "29161220",
        "year": "2026",
        "monthNumber": "09",
        "ncm": "Ésteres de etila do ácido acrílico",
        "state": "Rio de Janeiro",
        "urf": "PORTO DE SANTOS",
        "country": "China",
        "metricFOB": "15000",
        "metricFreight": "1000",
        "metricInsurance": "10",
        "metricCIF": "16010",
        "metricKG": "10000",
    }
    municipal = {
        "noMunMinsgUf": "Rio de Janeiro - RJ",
        "year": "2026",
        "monthNumber": "09",
        "state": "Rio de Janeiro",
        "headingCode": "2916",
        "heading": "Ácidos carboxílicos",
        "country": "China",
        "metricFOB": "30000",
        "metricKG": "20000",
    }
    with tempfile.TemporaryDirectory(prefix="liarte-autoteste-docs-") as folder:
        root = Path(folder)
        pairs = engine.internal_product_ncms()
        excel = root / "AUTOTESTE_SINTETICO.xlsx"
        engine.create_report(excel, pairs, [general], "2026-09", "2026-09", True, [municipal])
        pdf = create_import_pdf(
            root / "AUTOTESTE_SINTETICO.pdf", pairs, [general], "2026-09", "2026-09"
        )
        bi = create_powerbi_package(
            excel, root / "AUTOTESTE_SINTETICO_BI.zip", "2026-09", "2026-09"
        )
        return {
            "excel": "ok",
            "pdf": "ok" if pdf["pages"] == 1 else "failed",
            "pdf_logo": pdf["logo"],
            "powerbi": "ok",
            "powerbi_pages": bi["pages"],
            "powerbi_visuals": bi["visuals"],
            "synthetic": True,
            "temporary": True,
        }
