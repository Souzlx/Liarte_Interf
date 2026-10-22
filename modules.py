"""Cadastro explícito dos módulos, independente da interface e dos dados do ERP."""

from __future__ import annotations

from dataclasses import dataclass
import re
from types import MappingProxyType


@dataclass(frozen=True, slots=True)
class Module:
    key: str
    title: str
    description: str
    icon: str
    available: bool = False


class ModuleRegistry:
    """Somente módulos cadastrados e disponíveis podem ser abertos.

    Este cadastro descreve disponibilidade do produto, não permissões de usuário.
    Integração, identidade e autorização no servidor são etapas posteriores.
    """

    def __init__(self, modules: tuple[Module, ...]):
        entries = {}
        for module in modules:
            if (
                not isinstance(module.key, str)
                or not re.fullmatch(r"[a-z][a-z0-9_]{0,39}", module.key)
                or module.key in {"home", "settings", "help"}
                or module.key in entries
                or not isinstance(module.title, str)
                or not module.title.strip()
                or not isinstance(module.description, str)
                or not module.description.strip()
                or type(module.available) is not bool
            ):
                raise ValueError(f"Cadastro de módulo inválido: {module.key!r}")
            entries[module.key] = module
        self._entries = MappingProxyType(entries)

    @property
    def modules(self) -> tuple[Module, ...]:
        return tuple(self._entries.values())

    def can_open(self, key: str) -> bool:
        module = self._entries.get(key)
        return module is not None and module.available

    def get(self, key: str) -> Module | None:
        return self._entries.get(key)


def default_registry() -> ModuleRegistry:
    return ModuleRegistry(
        (
            Module(
                "imports", "Importações", "Mercado, origens e custos de importação.", "chart", True
            ),
            Module("inventory", "Estoque", "Saldos, capital, giro e análise de vendas.", "box", True),
            Module(
                "credit", "Crédito", "Análise e acompanhamento das linhas de crédito.", "credit"
            ),
        )
    )
