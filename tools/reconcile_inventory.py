"""Conferência offline dos registros PBIX e dos cálculos de Estoque."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from threading import Event

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# The standalone command must also work before the package is installed.
from liarte_core.inventory_io import _hash, read_pbix, read_snapshot  # noqa: E402
from liarte_core.inventory_reconciliation import reconcile_inventory  # noqa: E402
from liarte_core.inventory_reconciliation_export import export_inventory_reconciliation  # noqa: E402
from liarte_core.inventory_reference import read_pbix_reference  # noqa: E402
from liarte_core.query import Cancelled  # noqa: E402


def _check_paths(pbix, base, output):
    if pbix.suffix.casefold() != ".pbix" or not pbix.is_file():
        raise ValueError("Origem PBIX inválida.")
    if base is not None and (base.suffix.casefold() != ".liarte" or not base.is_file()):
        raise ValueError("Base de comparação inválida.")
    if output.suffix.casefold() not in (".json", ".xlsx"):
        raise ValueError("Extensão de relatório inválida.")
    destination = output.resolve()
    for source in (pbix, base):
        if source is None:
            continue
        if destination == source.resolve() or output.exists() and output.samefile(source):
            raise ValueError("O relatório não pode substituir um arquivo de entrada.")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pbix", type=Path, required=True, help="PBIX com os dados gravados.")
    parser.add_argument(
        "--base", type=Path, help="Snapshot .liarte a conferir; sem ele importa o PBIX."
    )
    parser.add_argument("--output", type=Path, required=True, help="Relatório .json ou .xlsx.")
    arguments = parser.parse_args(argv)
    cancel = Event()
    try:
        _check_paths(arguments.pbix, arguments.base, arguments.output)
        inputs = (arguments.pbix,) + ((arguments.base,) if arguments.base is not None else ())
        revisions = tuple(_hash(source, cancel) for source in inputs)
        reference = read_pbix_reference(arguments.pbix, cancel=cancel)
        data = (
            read_snapshot(arguments.base, cancel=cancel)
            if arguments.base is not None
            else read_pbix(arguments.pbix, cancel=cancel)
        )
        report = reconcile_inventory(reference, data, cancel=cancel)
        checks = report["checks"]
        result_code = {"equal": 0, "different": 1, "not_comparable": 2}[report["status"]]
        summary = (
            "status="
            + report["status"]
            + "; verificações="
            + str(checks.get("total", 0))
            + "; iguais="
            + str(checks.get("passed", 0))
            + "; diferentes="
            + str(checks.get("different", 0))
            + "; ausentes="
            + str(checks.get("missing", 0))
            + "; extras="
            + str(checks.get("extra", 0))
            + "; desconhecidos="
            + str(checks.get("unknown", 0))
        )

        def unchanged():
            if any(
                _hash(source, cancel) != revision for source, revision in zip(inputs, revisions)
            ):
                raise ValueError("Uma entrada mudou durante a conferência.")
            # Repeat collision checks before publication in case the
            # destination or its directory changed while calculations ran.
            _check_paths(arguments.pbix, arguments.base, arguments.output)

        unchanged()
        export_inventory_reconciliation(
            report, arguments.output, cancel=cancel, before_publish=unchanged
        )
        print(summary)
        print("Relatório: " + arguments.output.name)
        return result_code
    except (KeyboardInterrupt, Cancelled):
        cancel.set()
        print("Conferência cancelada; nenhum relatório incompleto foi publicado.", file=sys.stderr)
        return 130
    except Exception:
        # Import/validation exceptions can contain source records or financial
        # identifiers. Details remain in a completed, explicitly chosen report.
        print(
            "Conferência não concluída. Verifique as entradas e o destino do relatório.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
