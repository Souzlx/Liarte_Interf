"""Busca determinística do catálogo: código primeiro, depois nome e grupo, sem acentos.

Não aproxima nomes químicos: uma sugestão sempre corresponde a um cadastro real.
O índice é preparado uma vez por base; digitação não percorre fatos de estoque/vendas.
"""

from collections import defaultdict
from decimal import Decimal

from .inventory import SCALE, folded, number


class ProductSearch:
    def __init__(self, data):
        quantities, costs = defaultdict(lambda: defaultdict(int)), defaultdict(int)
        for balance in data.balances:
            quantities[balance.product][balance.unit] += balance.quantity
            costs[balance.product] += balance.cost
        self.names = {p.code: p.code + " · " + p.name for p in data.products}
        self.entries = []
        for product in data.products:
            units = quantities.get(product.code, {})
            balance = (
                " · ".join(
                    number(Decimal(qty) / SCALE, 3) + " " + unit
                    for unit, qty in sorted(units.items())
                )
                or "Sem posição atual"
            )
            code, name = folded(product.code), folded(product.name)
            self.entries.append(
                (
                    code,
                    name,
                    folded(product.group),
                    costs[product.code],
                    {
                        "code": product.code,
                        "name": product.name,
                        "group": product.group,
                        "balance": balance,
                        "label": self.names[product.code],
                    },
                )
            )

    def find(self, query: str, limit: int = 12) -> dict:
        query = folded(query.strip())[:200]
        terms = query.split()
        matches = []
        for code, name, group, cost, item in self.entries:
            text = code + " " + name + " " + group
            if not all(term in text for term in terms):
                continue
            rank = (
                0
                if code == query
                else 1
                if code.startswith(query)
                else 2
                if name.startswith(query)
                else 3
                if all(any(word.startswith(term) for word in text.split()) for term in terms)
                else 4
            )
            matches.append((rank, -cost, name, code, item))
        matches.sort(key=lambda row: row[:4])
        return {
            "items": [row[4] for row in matches[: max(1, min(30, limit))]],
            "count": len(matches),
        }
