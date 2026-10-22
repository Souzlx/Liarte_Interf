"""Apresentação de referências históricas; não altera fonte ou documentos."""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction

from liarte_core.domain import number, money, period_label
from liarte_core.procurement import Procurement, change, ratio


def unit_price(value):
    return "US$ " + number(value, 3) if value is not None else "—"


def percent(value, signed=False):
    if value is None:
        return "—"
    label = number(value, 1)
    return ("+" if signed and value > 0 and label != "0,0" else "") + label + "%"


def empty_analysis():
    return {
        "series": {},
        "cards": [],
        "origins": [],
        "comparable": False,
        "context": "",
        "note": "",
        "weightWarning": "",
        "range": "",
        "productLabel": "",
        "empty": True,
        "isMix": False,
        "codeCount": 0,
    }


def present(data: Procurement):
    municipal = data.municipal
    basis = "FOB" if municipal else "CIF"
    multiple = len(data.codes) > 1
    definitions = [
        (
            "value",
            "Valor " + basis,
            "US$ mi",
            2,
            lambda a: Decimal(a.value_cents),
            Decimal(100_000_000),
            False,
        ),
        ("price", basis + "/kg", "US$/kg", 3, lambda a: a.unit_price, Decimal(1), True),
        ("weight", "Peso", "mil kg", 1, lambda a: Decimal(a.kg), Decimal(1000), False),
    ]
    if not municipal:
        definitions += [
            ("fob", "FOB/kg", "US$/kg", 3, lambda a: a.fob_per_kg, Decimal(1), True),
            ("freight", "Frete/kg", "US$/kg", 3, lambda a: a.freight_per_kg, Decimal(1), True),
        ]
    series = {}
    for key, label, unit, precision, getter, scale, weighted in definitions:
        points = []
        for month in data.months:
            raw = getter(month.aggregate)
            moving = getter(month.rolling) if month.rolling else None
            if weighted and not month.rolling_price_valid:
                moving = None
            if not weighted and moving is not None:
                moving = ratio(moving, 3)
            display = (
                unit_price(raw)
                if weighted
                else money(month.aggregate.value_cents)
                if key == "value"
                else number(month.aggregate.kg) + " kg"
            )
            moving_display = (
                unit_price(moving)
                if weighted
                else "US$ " + number(ratio(moving, 100), 2)
                if key == "value" and moving is not None
                else number(moving, 2) + " kg"
                if moving is not None
                else "—"
            )
            points.append(
                {
                    "period": month.period,
                    "label": period_label(month.period),
                    "value": float(raw / scale) if raw is not None else None,
                    "display": display,
                    "movingValue": float(moving / scale) if moving is not None else None,
                    "movingDisplay": moving_display,
                    "kg": number(month.aggregate.kg),
                    "records": number(month.aggregate.records),
                    "tableValue": number(
                        ratio(raw, 100) if key == "value" and raw is not None else raw,
                        2 if key == "value" else 0 if key == "weight" else 3,
                    ),
                    "tableMoving": number(
                        ratio(moving, 100) if key == "value" and moving is not None else moving,
                        2 if key in ("value", "weight") else 3,
                    ),
                }
            )
        latest = getter(data.months[-1].aggregate) if data.months else None
        previous = getter(data.months[-2].aggregate) if len(data.months) >= 2 else None
        movement = change(latest, previous)
        first = getter(data.months[0].aggregate) if len(data.months) >= 2 else None
        series[key] = {
            "label": label,
            "unit": unit,
            "tableUnit": "US$" if key == "value" else "kg" if key == "weight" else "US$/kg",
            "precision": precision,
            "points": points,
            "change": percent(movement, True),
            "periodChange": percent(change(latest, first), True),
            "comparison": "vs. mês anterior"
            if movement is not None
            else "Sem base mensal comparável",
            "rollingLabel": "Média ponderada · 3 meses" if weighted else "Média mensal · 3 meses",
            "hasRolling": any(p["movingValue"] is not None for p in points),
            "coverage": f"{sum(p['value'] is not None for p in points)}/{len(points)} meses com valor",
        }
    last = data.months[-1] if data.months else None
    variations = []
    for index, month in enumerate(data.months):
        movement = change(
            month.aggregate.value_cents,
            data.months[index - 1].aggregate.value_cents if index else None,
        )
        variations.append(
            {
                "period": month.period,
                "label": period_label(month.period),
                "value": float(movement) if movement is not None else None,
                "display": percent(movement, True)
                if movement is not None
                else "Sem base comparável",
                "movingValue": None,
                "movingDisplay": "—",
                "kg": number(month.aggregate.kg),
                "records": number(month.aggregate.records),
                "tableValue": number(movement, 1),
                "tableMoving": "—",
            }
        )
    series["valueChange"] = {
        "label": "Variação do valor " + basis,
        "unit": "%",
        "tableUnit": "%",
        "precision": 1,
        "points": variations,
        "change": series["value"]["change"],
        "periodChange": series["value"]["periodChange"],
        "comparison": series["value"]["comparison"],
        "rollingLabel": "",
        "hasRolling": False,
        "coverage": f"{sum(p['value'] is not None for p in variations)}/{len(variations)} meses comparáveis",
    }
    previous = data.months[-2] if len(data.months) >= 2 else None
    last_price = last.aggregate.unit_price if last else None
    movement = change(last_price, previous.aggregate.unit_price if previous else None)
    rolling_price = (
        last.rolling.unit_price if last and last.rolling and last.rolling_price_valid else None
    )
    freight = data.total.freight_per_kg
    cards = [
        {
            "label": "Último mês · " + basis + "/kg",
            "value": unit_price(last_price),
            "detail": percent(movement, True) + " vs. mês anterior"
            if movement is not None
            else "Sem base mensal comparável",
            "full": (period_label(last.period) + ". " if last else "")
            + "Valor total ÷ kg total no mês. A variação usa o mês imediatamente anterior do período selecionado.",
        },
        {
            "label": "Referência · 3 meses",
            "value": unit_price(rolling_price),
            "detail": "por kg · ponderada pelo peso"
            if rolling_price is not None
            else "Requer 3 meses com peso positivo",
            "full": "Soma dos valores ÷ soma dos kg nos últimos 3 meses consecutivos da seleção; nunca a média simples dos preços mensais.",
        },
        {
            "label": "Volume no último mês" if municipal else "Frete no CIF",
            "value": number(last.aggregate.kg) + " kg"
            if municipal and last
            else percent(data.total.freight_share),
            "detail": (
                percent(change(last.aggregate.kg, previous.aggregate.kg), True)
                + " vs. mês anterior"
                if previous and previous.aggregate.kg
                else "Sem base mensal comparável"
            )
            if municipal
            else unit_price(freight) + "/kg"
            if freight is not None
            else "Peso indisponível para cálculo",
            "full": "Peso publicado no mês final da seleção."
            if municipal
            else "Frete total ÷ CIF total × 100. Frete/kg usa o peso total do recorte; seguro está incluído apenas no CIF.",
        },
        {
            "label": "3 principais origens",
            "value": percent(data.top3_share),
            "detail": "do valor " + basis + " no período",
            "full": "Participação acumulada dos até 3 países de maior valor no recorte. Não identifica fornecedores individuais.",
        },
    ]
    # Explain only an actual data issue, on the affected metric and time window.
    # A multi-product selection is an ordinary filter state, not a warning.
    for card, aggregate in zip(
        cards[:2], (last.aggregate if last else None, last.rolling if last else None), strict=True
    ):
        card["issue"] = (
            "Há importações com valor e 0 kg na fonte neste intervalo. A média usa os totais publicados pelo Comex Stat."
            if aggregate and aggregate.unweighed_cents
            else ""
        )
    origins = []
    # Rank by the exact rational unit value, never by a rounded label or float.
    price_order = {
        origin.name: index
        for index, origin in enumerate(
            sorted(
                data.origins,
                key=lambda o: (
                    o.aggregate.kg == 0,
                    Fraction(o.aggregate.value_cents, o.aggregate.kg)
                    if o.aggregate.kg
                    else Fraction(0),
                    -o.aggregate.kg,
                    o.name,
                ),
            )
        )
    }
    for volume_rank, origin in enumerate(data.origins):
        a = origin.aggregate
        origins.append(
            {
                "name": origin.name,
                "volumeRank": volume_rank,
                "priceRank": price_order[origin.name],
                "months": f"{origin.priced_months}/{len(data.months)} meses",
                "kg": number(a.kg),
                "kgValue": float(
                    a.kg
                ),  # Geometry/filter thresholds only; exact kg stays in the text.
                "price": float(a.unit_price) if a.unit_price is not None else None,
                "unit": number(a.unit_price, 3),
                "fob": number(a.fob_per_kg, 3),
                "freight": number(a.freight_per_kg, 3),
                "share": percent(ratio(a.value_cents * 100, data.total.value_cents)),
                "difference": percent(change(a.unit_price, data.total.unit_price), True),
                "unweighed": money(a.unweighed_cents) if a.unweighed_cents else "",
                "monthlyChange": percent(
                    change(
                        origin.latest.unit_price,
                        origin.previous.unit_price if origin.previous else None,
                    ),
                    True,
                ),
            }
        )
    valid_months = [m for m in data.months if m.aggregate.unit_price is not None]
    low = min(valid_months, key=lambda m: m.aggregate.unit_price) if valid_months else None
    high = max(valid_months, key=lambda m: m.aggregate.unit_price) if valid_months else None
    scope = (
        "Média da seleção"
        if multiple
        else ("SH4 " if municipal else "NCM ") + data.codes[0]
        if data.codes
        else "Sem importações no recorte"
    )
    note = "Valores históricos por kg, sujeitos a diferenças de qualidade, quantidade e rota."
    note += (
        " SH4 reúne produtos de uma mesma posição."
        if municipal
        else " CIF inclui frete e seguro; não inclui tributos e custos internos."
    )
    if multiple:
        note = (
            "O preço deste recorte representa um mix. Selecione um produto para comparar preços entre origens. "
            + note
        )
    return {
        "series": series,
        "cards": cards,
        "origins": origins,
        "comparable": len(data.codes) == 1,
        "context": scope,
        "productLabel": data.product_label,
        "empty": data.total.records == 0,
        "isMix": multiple,
        "codeCount": len(data.codes),
        "note": note,
        "weightWarning": "Há importações com valor e 0 kg na fonte. As médias por kg usam os totais publicados."
        if data.total.unweighed_cents
        else "",
        "reference": float(data.total.unit_price) if data.total.unit_price is not None else None,
        "referenceText": unit_price(data.total.unit_price),
        "range": f"Menor média mensal: {unit_price(low.aggregate.unit_price)} ({low.period[5:]}/{low.period[:4]}) · Maior: {unit_price(high.aggregate.unit_price)} ({high.period[5:]}/{high.period[:4]})"
        if low and high
        else "Sem peso disponível para referência de preço.",
        "basis": basis,
    }
