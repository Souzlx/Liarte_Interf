"""Consulta real e conciliação independente; não usa dados sintéticos nem altera relatórios."""

from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from threading import Event

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from liarte_core.comex import ComexProvider, integral
from liarte_core.domain import Period, Selection
from liarte_engine import comexstat_importacoes as engine


def verify(directory, output, *, start=None, end=None):
    provider = ComexProvider(directory)
    try:
        return _verify(provider, output, start=start, end=end)
    finally:
        provider.close()


def _verify(provider, output, *, start=None, end=None):
    cancel = Event()
    availability = provider.availability(cancel, force=True)
    first, last = start or availability.latest, end or availability.latest
    provider.query(
        Selection(Period(first, last), sort_column=9, descending=True),
        cancel,
        lambda p, m: print(f"{p:3}% {m}", flush=True),
    )
    snapshot = provider.snapshot
    client = provider._client(cancel, cache=False)
    ncms = provider.codes
    body = {
        "flow": "import",
        "monthDetail": True,
        "period": {"from": first, "to": last},
        "filters": [{"filter": "ncm", "values": [int(n) for n in ncms]}],
        "details": ["ncm"],
        "metrics": engine.DEFAULT_METRICS,
    }
    try:
        control = []
        for window_start, window_end in engine.period_windows(first, last):
            window_body = {**body, "period": {"from": window_start, "to": window_end}}
            control.extend(
                client.request_json("POST", "/general?language=pt", json_body=window_body)["data"][
                    "list"
                ]
            )
        totals = {
            field: sum(integral(r[field], cents=field != "metricKG") for r in control)
            for field in engine.DEFAULT_METRICS
        }
        detailed = {
            field: sum(integral(r[field], cents=field != "metricKG") for r in snapshot.general)
            for field in engine.DEFAULT_METRICS
        }
        if totals != detailed:
            raise RuntimeError("Detalhes gerais divergem do total oficial independente.")
        headings = sorted({code[:4] for code in ncms})
        body.update(
            filters=[{"filter": "heading", "values": [int(code) for code in headings]}],
            details=["heading"],
            metrics=engine.MUNICIPAL_METRICS,
        )
        municipal_control = []
        for window_start, window_end in engine.period_windows(first, last):
            window_body = {**body, "period": {"from": window_start, "to": window_end}}
            municipal_control.extend(
                client.request_json("POST", "/cities?language=pt", json_body=window_body)["data"][
                    "list"
                ]
            )
        municipal_totals = {
            field: sum(integral(r[field], cents=field == "metricFOB") for r in municipal_control)
            for field in engine.MUNICIPAL_METRICS
        }
        municipal_detailed = {
            field: sum(integral(r[field], cents=field == "metricFOB") for r in snapshot.municipal)
            for field in engine.MUNICIPAL_METRICS
        }
        if municipal_totals != municipal_detailed:
            raise RuntimeError("Detalhes municipais divergem do total SH4 oficial independente.")
    finally:
        client.close()
    report = {
        "status": "ok",
        "synthetic": False,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "period": {"from": first, "to": last},
        "published_until": availability.latest,
        "source_updated": availability.updated,
        "municipal_updated": availability.municipal_updated,
        "ncm_count": len(ncms),
        "sh4_count": len(headings),
        "general_rows": len(snapshot.general),
        "municipal_rows": len(snapshot.municipal),
        "general_control": totals,
        "municipal_control": municipal_totals,
        "money_unit": "US$ cents",
        "weight_unit": "kg",
        "independent_reconciliations": 2,
        "source_channels": list(snapshot.source_channels),
        "note": "Base municipal SH4 e base geral NCM são universos distintos; seus totais não devem ser comparados nem somados.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--inicio")
    p.add_argument("--fim")
    p.add_argument("--dados", type=Path, default=ROOT / "logs/validacao-dados")
    p.add_argument("--saida", type=Path, default=ROOT / "logs/validacao-comex.json")
    args = p.parse_args()
    verify(args.dados, args.saida, start=args.inicio, end=args.fim)


if __name__ == "__main__":
    main()
