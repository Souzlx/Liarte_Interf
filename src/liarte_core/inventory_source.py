"""Shared acceptance boundary for already normalized inventory records.

Adapters own extraction, field mappings and a consistent source read. This
module accepts the typed stock contract without knowing PBIX, SQL or Qt. A
content revision identifies the accepted values; it cannot make an inconsistent
extraction consistent or detect a source change that was never extracted.
"""

from __future__ import annotations

from dataclasses import fields, replace
from datetime import date
import hashlib
import json
from threading import Event

from .inventory import Balance, Closing, InventoryData, Product, Sale, _checked
from .query import checkpoint

_CONTENT_REVISION = object()
_RECORD_TYPES = {"products": Product, "balances": Balance, "closings": Closing, "sales": Sale}
_IDENTITIES = {
    "products": ("code",),
    "balances": ("product", "branch", "warehouse", "unit"),
    "closings": ("product", "branch", "warehouse", "unit", "period"),
    "sales": ("product", "branch", "unit", "day"),
}


def _collection(values, name, cancel, *, limit=None, record_type=None):
    if not isinstance(values, (tuple, list)) or limit is not None and len(values) > limit:
        raise ValueError("A base ultrapassa o limite de registros ou contém coleção inválida.")
    if record_type is not None:
        for row in _checked(values, cancel):
            if type(row) is not record_type:
                raise ValueError(f"Registro normalizado inválido em {name}.")
    checkpoint(cancel)
    return tuple(values)


def _content_revision(data, cancel):
    """Hash fields exactly, independent of extraction order and source label."""
    encode = json.JSONEncoder(ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode
    digest = hashlib.sha256()

    def add(value):
        digest.update(encode(value).encode("utf-8"))

    add(("liarte.inventory.content/1", data.as_of.isoformat()))
    for name in (*_RECORD_TYPES, "branches", "warehouses", "notes"):
        checkpoint(cancel)
        add(name)
        keys = _IDENTITIES.get(name)
        count = 0

        def order(row):
            nonlocal count
            if count % 512 == 0:
                checkpoint(cancel)
            count += 1
            return tuple(getattr(row, key) for key in keys) if keys else row

        # One collection's references at a time. The accepted record order and
        # caller-owned collections are never changed by revision calculation.
        ordered = sorted(getattr(data, name), key=order)
        add(len(ordered))
        for row in _checked(ordered, cancel):
            if name in _RECORD_TYPES:
                values = []
                for field in fields(_RECORD_TYPES[name]):
                    value = getattr(row, field.name)
                    if type(value) is date:
                        value = value.isoformat()
                    elif name == "closings" and field.name in ("turnover", "days"):
                        # The ratio contract accepts int/float; equal ratios
                        # have one numeric representation. Quantities and costs
                        # remain exact integers and never pass through float.
                        value = float(value) if value is not None else None
                        if value == 0:
                            value = 0.0
                    values.append(value)
                add(values)
            else:
                add(row)
    checkpoint(cancel)
    return digest.hexdigest()


def inventory_from_records(
    *,
    as_of: date,
    source_name: str,
    products,
    balances,
    closings=(),
    sales=(),
    branches=(),
    warehouses=(),
    notes=(),
    source_hash=_CONTENT_REVISION,
    cancel: Event | None = None,
) -> InventoryData:
    """Freeze and validate one complete normalized extraction.

    Collections must already be bounded lists/tuples of Product, Balance,
    Closing and Sale records in the domain's integer scales. No raw SQL rows,
    schema discovery, business inference or aggregation happens here.

    An explicitly supplied source_hash is validated and preserved, including
    the original file identity in PBIX and portable snapshots. Omitting it
    derives a versioned SHA-256 from all accepted normalized fields except the
    source name and hash itself. Explicit None is not a valid supplied hash.
    """
    # Kept lazy so the existing file validators/serializers can call this
    # factory without a module-import cycle or moving the legacy file format.
    from .inventory_io import RECORD_LIMITS, validate_data

    cancel = cancel if cancel is not None else Event()
    checkpoint(cancel)
    raw = {"products": products, "balances": balances, "closings": closings, "sales": sales}
    collections = {
        name: _collection(
            values, name, cancel, limit=RECORD_LIMITS[name], record_type=_RECORD_TYPES[name]
        )
        for name, values in raw.items()
    }
    for name, values in (("branches", branches), ("warehouses", warehouses), ("notes", notes)):
        collections[name] = _collection(values, name, cancel)
    for name in ("branches", "warehouses"):
        locations = []
        for row in _checked(collections[name], cancel):
            if not isinstance(row, (tuple, list)) or len(row) != 2:
                raise ValueError("Dimensão de local inválida na base.")
            locations.append(tuple(row))
        collections[name] = tuple(locations)
    derive_revision = source_hash is _CONTENT_REVISION
    data = validate_data(
        InventoryData(
            as_of=as_of,
            source_name=source_name,
            source_hash="0" * 64 if derive_revision else source_hash,
            **collections,
        ),
        cancel,
    )
    if derive_revision:
        data = replace(data, source_hash=_content_revision(data, cancel))
    checkpoint(cancel)
    return data
