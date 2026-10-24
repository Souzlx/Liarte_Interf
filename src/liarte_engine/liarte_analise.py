"""Filtros e paginação da análise local, sem alterar os arquivos exportados."""

from __future__ import annotations

import math
from decimal import Decimal
import unicodedata
from typing import Any, Callable, Iterable, Sequence

MAX_FILTER_VALUES = 200
MAX_FILTER_LENGTH = 500
TABLE_PAGE_SIZES = (25, 50, 100, 200)
FilterSelection = str | list[str] | tuple[str, ...] | None


def selection_values(value: FilterSelection, label: str = "filtro") -> tuple[str, ...]:
    """Preserva nomes com vírgulas; nunca interpreta uma seleção como CSV."""
    if value is None or value == "":
        return ()
    values = [value] if isinstance(value, str) else value
    if not isinstance(values, (list, tuple)) or len(values) > MAX_FILTER_VALUES:
        raise ValueError(f"A seleção de {label} é inválida ou excessiva.")
    clean: set[str] = set()
    for item in values:
        if not isinstance(item, str) or len(item) > MAX_FILTER_LENGTH:
            raise ValueError(f"O valor de {label} é inválido ou excessivo.")
        if item.strip():
            clean.add(item.strip())
    return tuple(sorted(clean, key=lambda item: (item.casefold(), item)))


def validated_selection(
    value: FilterSelection,
    allowed: Iterable[str],
    label: str,
    normalizer: Callable[[str], str | None] | None = None,
) -> str | list[str]:
    values = selection_values(value, label)
    try:
        normalized = [str(normalizer(item) or "") if normalizer else item for item in values]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"O filtro de {label} é inválido.") from exc
    valid = set(allowed)
    if any(not item or item not in valid for item in normalized):
        raise ValueError(f"O filtro de {label} não pertence a este relatório.")
    result = sorted(set(normalized), key=lambda item: (item.casefold(), item))
    return "" if not result else result[0] if len(result) == 1 else result


def search_key(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str("" if value is None else value).casefold())
    return "".join(char for char in text if not unicodedata.combining(char))


def table_page(
    records: Sequence[dict[str, Any]],
    columns: Sequence[str],
    *,
    page: int | str = 1,
    page_size: int | str = 50,
    search: str = "",
    sort: str = "",
    direction: str = "asc",
) -> dict[str, Any]:
    """Busca em todos os registros filtrados; ordena antes de paginar."""
    try:
        if isinstance(page, bool) or isinstance(page_size, bool):
            raise ValueError
        page_number, size = int(page), int(page_size)
        if str(page_number) != str(page) or str(size) != str(page_size):
            raise ValueError
        if not 1 <= page_number <= 1_000_000 or size not in TABLE_PAGE_SIZES:
            raise ValueError
    except (TypeError, ValueError) as exc:
        raise ValueError("Página ou quantidade de linhas inválida.") from exc
    if not isinstance(search, str) or len(search) > 250:
        raise ValueError("A busca é inválida ou excessiva.")
    if sort and sort not in columns:
        raise ValueError("Coluna de ordenação inválida.")
    if direction not in {"asc", "desc"}:
        raise ValueError("Direção de ordenação inválida.")
    terms = search_key(search.strip()).split()
    selected = list(records)
    if terms:

        def matches(row: dict[str, Any]) -> bool:
            searchable = search_key(
                " ".join(
                    str("" if row.get(key) is None else row[key])
                    for key in (*columns, "_period", "_search")
                )
            )
            return all(term in searchable for term in terms)

        selected = [row for row in selected if matches(row)]
    if sort:

        def sort_key(row: dict[str, Any]) -> tuple[int, Any]:
            value = row.get("_period") if sort == "Mês" else row.get(sort)
            if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
                return (0, value)
            return (1, search_key(value))

        present = [row for row in selected if row.get(sort) is not None]
        missing = [row for row in selected if row.get(sort) is None]
        selected = sorted(present, key=sort_key, reverse=direction == "desc") + missing
    pages = max(1, math.ceil(len(selected) / size))
    page_number = min(page_number, pages)
    offset = (page_number - 1) * size
    return {
        "rows": [
            {key: row.get(key) for key in columns} for row in selected[offset : offset + size]
        ],
        "page": page_number,
        "page_size": size,
        "pages": pages,
        "total": len(selected),
        "filtered_total": len(records),
        "search": search,
        "sort": sort,
        "direction": direction,
    }
