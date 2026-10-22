"""Base empresarial integrada: recurso somente de leitura, com integridade verificável."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

DATA_DIRECTORY = Path(__file__).resolve().parent / "data"


def bundled_inventory_path() -> Path:
    return DATA_DIRECTORY / "estoque.liarte"


def verify_bundled_inventory(path: Path) -> None:
    """Não confiar em uma base integrada truncada ou trocada na distribuição."""
    try:
        manifest = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
        expected = manifest.get("sha256") if isinstance(manifest, dict) else None
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
    except (OSError, ValueError) as exc:
        raise ValueError("A base integrada está incompleta. Reinstale o pacote da LIARTE.") from exc
    if expected != actual:
        raise ValueError("A base integrada está incompleta. Reinstale o pacote da LIARTE.")
