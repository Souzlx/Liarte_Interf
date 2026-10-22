"""Cadastro interno LIARTE e constantes exclusivas dos testes demonstrativos."""

from pathlib import Path
import json
from .domain import Period

DEMO_PERIOD = Period("2025-01", "2026-09")
COUNTRIES = (
    "China",
    "Estados Unidos",
    "Holanda",
    "Alemanha",
    "Coreia do Sul",
    "Índia",
    "Taiwan",
    "Bélgica",
)
STATES = ("SP", "RJ", "BA", "MG", "PR", "SC", "RS", "PE")
PORTS = (
    "Porto de Santos",
    "Porto do Rio de Janeiro",
    "Porto de Paranaguá",
    "Porto de Suape",
    "Porto de Itajaí",
    "Porto do Rio Grande",
)


def catalog() -> tuple[dict, ...]:
    payload = json.loads(Path(__file__).with_name("catalog.json").read_text(encoding="utf-8"))
    items = payload["items"]
    if len(items) != 35 or len({item["ncm"] for item in items}) != 35:
        raise ValueError("O cadastro da prova técnica não passou na verificação.")
    return tuple(items)
