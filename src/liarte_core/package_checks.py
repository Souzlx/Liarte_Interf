"""Autoteste offline do pacote compilado. Fixtures explicitamente sintéticas e temporárias."""

from pathlib import Path
from datetime import datetime, timezone
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
        # Exercise SQLite and the real local provider inside the frozen binary,
        # without opening the network or touching an existing user profile.
        from .comex_historical import HistoricalComexProvider
        from .domain import Period, Selection
        from threading import Event

        provider = HistoricalComexProvider(root / "historico-sintetico", codes=(general["coNcm"],))
        try:
            publication = {
                "latest": "2026-09", "updated": "2026-10-06",
                "municipal_latest": "2026-09", "municipal_updated": "2026-10-06",
            }
            period = Period("2026-09", "2026-09")
            run = provider.history.begin_run(publication, period.start, period.end)
            stamp = datetime.now(timezone.utc).isoformat()
            for municipal_base, rows in ((False, [general]), (True, [municipal])):
                provider.history.write_stage(
                    run, municipal_base, period.start, period.end, rows,
                    received_at=stamp, acquisition_started_at=stamp,
                )
            provider.history.record_check(publication)
            provider.history.publish_run(run)
            result = provider.query(Selection(period), Event(), lambda *_: None)
            city_result = provider.query(Selection(period, kind="municipal"), Event(), lambda *_: None)
            if (
                result.totals.records != 1 or result.totals.value_cents != 1_601_000
                or city_result.totals.records != 1 or city_result.totals.value_cents != 3_000_000
                or not provider.snapshot.local_revision or provider.snapshot.api_requests != 0
            ):
                raise RuntimeError("O histórico sintético não passou na consulta local do pacote.")
        finally:
            provider.close()
        return {
            "excel": "ok",
            "pdf": "ok" if pdf["pages"] == 1 else "failed",
            "pdf_logo": pdf["logo"],
            "powerbi": "ok",
            "powerbi_pages": bi["pages"],
            "powerbi_visuals": bi["visuals"],
            "comex_history": "ok",
            "comex_history_offline_query": True,
            "synthetic": True,
            "temporary": True,
        }
