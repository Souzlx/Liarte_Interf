"""Verify or recover a local history copy to a new file, without network."""

from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from liarte_core.comex_history_backup import restore_to_new_file, verify_backup  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backup", type=Path, help="Pasta da cópia com manifest.json")
    parser.add_argument(
        "--recover-to", type=Path, help="Arquivo SQLite novo; nunca substitui o existente"
    )
    args = parser.parse_args()
    metadata = verify_backup(args.backup)
    if args.recover_to is not None:
        restore_to_new_file(args.backup, args.recover_to)
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
