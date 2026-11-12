"""Offline source-comparison benchmark; synthetic facts and exact result digests."""

from pathlib import Path
import argparse
from dataclasses import replace
import hashlib
import json
import sys
import tempfile
from threading import Event
from time import perf_counter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--rows", type=int, default=50_000)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sys.path[:0] = [str(args.source_root / "src"), str(args.source_root)]
    from liarte_core.comex_historical import HistoricalComexProvider
    from liarte_core.domain import Period, Selection
    from tests.test_comex_history import CODES, STARTED, RECEIVED, general, municipal, publication

    report = {
        "data": "synthetic",
        "source_root": str(args.source_root),
        "rows": args.rows,
        "times": {},
    }

    def timed(key, action):
        before = perf_counter()
        result = action()
        report["times"][key] = perf_counter() - before
        return result

    with tempfile.TemporaryDirectory(prefix="liarte-dashboard-benchmark-") as scratch:
        provider = HistoricalComexProvider(Path(scratch), codes=CODES)
        store = provider.history
        months = Period("2024-01", "2024-12")
        data = [
            general(f"2024-{i % 12 + 1:02}", fob=10**16 + i, country=f"Origem sintética {i:07}")
            for i in range(args.rows)
        ]
        cities = [municipal(m) for m in months.months]
        run = store.begin_run(publication(months.end), months.start, months.end)
        timed(
            "write",
            lambda: store.write_stage(
                run,
                False,
                months.start,
                months.end,
                data,
                received_at=RECEIVED,
                acquisition_started_at=STARTED,
            ),
        )
        store.write_stage(
            run,
            True,
            months.start,
            months.end,
            cities,
            received_at=RECEIVED,
            acquisition_started_at=STARTED,
        )
        store.record_check(publication(months.end))
        timed("validate_publish", lambda: store.publish_run(run))
        noop, cancel = lambda *_: None, Event()
        timed("read_1month", lambda: store.read(Period("2024-02", "2024-02"), cancel))
        timed("read_12months", lambda: store.read(months, cancel))
        selection = Selection(months)
        result = timed("query_cold", lambda: provider.query(selection, cancel, noop))
        timed("query_warm", lambda: provider.query(selection, cancel, noop))
        timed(
            "search_first",
            lambda: provider.query(replace(selection, search="sintetica"), cancel, noop),
        )
        short = replace(selection, period=Period("2024-02", "2024-02"))
        timed("period_other", lambda: provider.query(short, cancel, noop))
        again = timed("period_return", lambda: provider.query(selection, cancel, noop))
        report["exact_digest"] = hashlib.sha256(
            repr((result.totals, result.monthly, result.countries, again.totals)).encode()
        ).hexdigest()
        report["db_bytes"] = store.path.stat().st_size
        report["general_rows"] = result.totals.records
        provider.close()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
