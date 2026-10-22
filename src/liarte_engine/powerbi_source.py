"""Auditoria streaming do XLSX antes de gerar o BI; dinheiro em centavos exatos."""

from __future__ import annotations
from collections import defaultdict
from decimal import Decimal, InvalidOperation
import hashlib
from pathlib import Path
import re
from typing import Callable
from xml.etree import ElementTree as ET
import zipfile

from .numeric import published_units

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
CURRENCY_MAX = Decimal("922337203685477.5807")
INT_MAX = 2**63 - 1


def period(value, start, end):
    text = str(value).strip().split(".", 1)[0]
    if re.fullmatch(r"\d{1,2}", text):
        if start[:4] != end[:4]:
            raise ValueError("Mês sem ano em período de vários anos.")
        text = start[:4] + "-" + text.zfill(2)
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", text) or not start <= text <= end:
        raise ValueError("Mês inválido ou fora do período do relatório.")
    return text


def code(value, size):
    text = str(value).strip() if value is not None else ""
    if not re.fullmatch(r"[0-9]{1," + str(size) + "}", text):
        raise ValueError("Código fiscal inválido.")
    return text.zfill(size)


def number(value, currency=False):
    if not isinstance(value, Decimal):
        raise ValueError("Valor numérico ausente ou textual.")
    if not value.is_finite() or value < 0:
        raise ValueError("Valor negativo ou não finito.")
    try:
        amount = published_units(value, places=2 if currency else 0)
    except ValueError as exc:
        raise ValueError(
            "Valor monetário com mais de duas casas."
            if currency
            else "Peso fracionário incompatível com os kg publicados."
        ) from exc
    if value > (CURRENCY_MAX if currency else Decimal(INT_MAX)):
        raise ValueError("Valor excede a capacidade do modelo.")
    return amount


def _rows(archive, path, strings, checkpoint):
    container = None
    counter = 0
    with archive.open(path) as source:
        for event, element in ET.iterparse(source, events=("start", "end")):
            if event == "start":
                if element.tag == NS + "sheetData":
                    container = element
                continue
            if element.tag != NS + "row":
                continue
            values = {}
            for cell in element.findall(NS + "c"):
                letters = re.match(r"([A-Z]+)", cell.get("r", "").upper())
                if not letters:
                    raise ValueError("Referência de célula inválida.")
                index = 0
                for letter in letters.group():
                    index = index * 26 + ord(letter) - 64
                if cell.find(NS + "f") is not None:
                    raise ValueError("Fórmula não permitida na base do BI.")
                kind = cell.get("t")
                raw = cell.findtext(NS + "v")
                if kind == "inlineStr":
                    value = "".join(x.text or "" for x in cell.findall(".//" + NS + "t"))
                elif kind == "s":
                    value = strings[int(raw)]
                elif kind in (None, "n"):
                    try:
                        value = Decimal(raw) if raw is not None else None
                    except InvalidOperation as exc:
                        raise ValueError("Número inválido no Excel.") from exc
                elif kind == "str":
                    value = raw or ""
                else:
                    raise ValueError("Tipo de célula inválido para a base do BI.")
                values[index - 1] = value
            counter += 1
            row = tuple(values.get(i) for i in range(max(values, default=-1) + 1))
            line = element.get("r", str(counter))
            element.clear()
            if container is not None:
                container.clear()
            if checkpoint and counter % 2048 == 0:
                checkpoint()
            yield line, row


def audit_source(
    path: Path, manifest: dict, start: str, end: str, checkpoint: Callable[[], None] | None = None
) -> dict:
    strings = manifest["strings"]
    pairs = set()
    ncms = set()
    products = set()
    with zipfile.ZipFile(path) as archive:
        product_name, product_path = manifest["products"]
        rows = _rows(archive, product_path, strings, checkpoint)
        next(rows, None)
        for line, row in rows:
            if not any(v is not None for v in row):
                continue
            try:
                product = str(row[0]).strip() if row[0] is not None else ""
                if not product:
                    raise ValueError("Produto ausente.")
                ncm = code(row[1], 8)
                pairs.add((product, ncm))
                ncms.add(ncm)
                products.add(product)
            except (ValueError, IndexError) as exc:
                raise ValueError(f"{product_name}, linha {line}: {exc}") from exc
        if not pairs:
            raise ValueError("O cadastro de produtos está vazio.")
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        output = {
            "version": 1,
            "source": path.name,
            "sha256": digest,
            "period": {"start": start, "end": end},
            "money_unit": "US$ centavos inteiros",
            "weight_unit": "kg inteiros",
            "catalog": {"relations": len(pairs), "ncms": len(ncms), "products": len(products)},
        }
        for kind in ("general", "municipal"):
            totals = {"rows": 0, "zero_weight_rows": 0, "kg": 0, "fob_cents": 0}
            if kind == "general":
                totals.update({"freight_cents": 0, "insurance_cents": 0, "cif_cents": 0})
            monthly = defaultdict(lambda keys=tuple(totals): dict.fromkeys(keys, 0))
            seen = set()
            for name, sheet_path in manifest[kind]:
                rows = _rows(archive, sheet_path, strings, checkpoint)
                next(rows, None)
                try:
                    for line, row in rows:
                        if not any(v is not None for v in row):
                            continue
                        try:
                            p = period(row[0], start, end)
                            if kind == "general":
                                ncm = code(row[1], 8)
                                if ncm not in ncms:
                                    raise ValueError("NCM fora do cadastro do relatório.")
                                dims = [
                                    str(row[i]).strip() if row[i] is not None else ""
                                    for i in (3, 4, 5)
                                ]
                                key = (p, ncm, *dims)
                                fob, freight, insurance, cif = (
                                    number(row[i], True) for i in (6, 7, 8, 9)
                                )
                                kg = number(row[10])
                                if cif != fob + freight + insurance:
                                    raise ValueError("CIF diverge da soma de FOB, frete e seguro.")
                                values = {
                                    "rows": 1,
                                    "zero_weight_rows": int(kg == 0),
                                    "kg": kg,
                                    "fob_cents": fob,
                                    "freight_cents": freight,
                                    "insurance_cents": insurance,
                                    "cif_cents": cif,
                                }
                            else:
                                heading = code(row[3], 4)
                                if heading not in {x[:4] for x in ncms}:
                                    raise ValueError("SH4 fora do universo do cadastro.")
                                dims = [
                                    str(row[i]).strip() if row[i] is not None else ""
                                    for i in (1, 2, 5)
                                ]
                                key = (p, heading, *dims)
                                fob = number(row[6], True)
                                kg = number(row[7])
                                values = {
                                    "rows": 1,
                                    "zero_weight_rows": int(kg == 0),
                                    "kg": kg,
                                    "fob_cents": fob,
                                }
                            if not all(dims):
                                raise ValueError("Dimensão obrigatória ausente.")
                            if key in seen:
                                raise ValueError(
                                    "Registro estatístico duplicado na mesma granularidade."
                                )
                            seen.add(key)
                            for k, v in values.items():
                                totals[k] += v
                                monthly[p][k] += v
                        except (ValueError, IndexError) as exc:
                            raise ValueError(f"{name}, linha {line}: {exc}") from exc
                except (ET.ParseError, KeyError, InvalidOperation) as exc:
                    raise ValueError(f"{name}: dados internos inválidos.") from exc
            for k, v in totals.items():
                if (k.endswith("_cents") and Decimal(v) / 100 > CURRENCY_MAX) or (
                    k == "kg" and v > INT_MAX
                ):
                    raise ValueError("Totais excedem a capacidade numérica do modelo.")
            output[kind] = {"totals": totals, "monthly": dict(sorted(monthly.items()))}
        return output
