"""Exact published units, independent of binary floats and ambient Decimal precision."""

from decimal import Decimal, InvalidOperation


def published_units(value, *, places=0):
    """Convert API dollars to cents, or kg to integers, without rounding.

    Comex uses a dot as decimal separator and does not publish thousands
    separators in JSON metrics. Reject unsupported precision rather than guess.
    """
    if isinstance(value, bool) or value is None or places not in (0, 2):
        raise ValueError("Métrica oficial ausente ou inválida.")
    text = str(value).strip()
    if not text or len(text) > 256:
        raise ValueError("Métrica oficial inválida.")
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("Métrica oficial inválida.") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError("Métrica oficial negativa ou não finita.")
    _, digits, exponent = amount.as_tuple()
    if not -256 <= exponent <= 128:
        raise ValueError("Métrica oficial fora da capacidade numérica prevista.")
    coefficient = int("".join(map(str, digits)))
    shift = exponent + places
    if shift >= 0:
        return coefficient * 10**shift
    units, remainder = divmod(coefficient, 10**-shift)
    if remainder:
        raise ValueError("Métrica oficial fora da precisão prevista. Nenhum valor foi arredondado.")
    return units


def from_units(units, *, places=2):
    """Decimal construction is exact even when the caller changes the context."""
    return Decimal((int(units < 0), tuple(map(int, str(abs(units)))), -places))


def sum_published(values, *, places=2):
    units = sum(published_units(value, places=places) for value in values)
    return from_units(units, places=places) if places else units
