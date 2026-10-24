"""Auditoria streaming do XLSX antes de gerar o BI; dinheiro em centavos exatos."""

from __future__ import annotations
from collections import defaultdict
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
import hashlib
from pathlib import Path
import posixpath
import re
from typing import Callable
from xml.etree import ElementTree as ET
import zipfile

from .numeric import published_units

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
CURRENCY_MAX = Decimal("922337203685477.5807")
INT_MAX = 2**63 - 1


# Bounds apply before reading ZIP members or constructing XML trees.
MAX_XLSX_ENTRIES = 20_000
MAX_XLSX_BYTES = 1024 * 1024 * 1024
MAX_PART_BYTES = 256 * 1024 * 1024
MAX_METADATA_BYTES = 8 * 1024 * 1024
MAX_SHARED_STRINGS_BYTES = 32 * 1024 * 1024
MAX_SHARED_STRINGS = 500_000
MAX_XLSX_COLUMNS = 16_384
MAX_XLSX_ROWS = 1_048_576
REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"
OFFICE_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
CONTENT_NS = "{http://schemas.openxmlformats.org/package/2006/content-types}"
MAIN_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"
SHEET_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"


class _XMLReader:
    def __init__(self, source, checkpoint=None):
        self.source, self.checkpoint = source, checkpoint
        self.tail, self.count = b"", 0

    def read(self, size=-1):
        chunk = self.source.read(min(size, 65536) if size >= 0 else 65536)
        combined = (self.tail + chunk).replace(b"\x00", b"").upper()
        if b"<!DOCTYPE" in combined or b"<!ENTITY" in combined:
            raise ValueError("Declarações DTD/ENTITY não são permitidas no XLSX.")
        self.tail = combined[-64:]
        previous = self.count
        self.count += len(chunk)
        if self.checkpoint and self.count // (1024 * 1024) != previous // (1024 * 1024):
            self.checkpoint()
        return chunk


@contextmanager
def xml_source(archive, path, checkpoint=None):
    with archive.open(path) as source:
        yield _XMLReader(source, checkpoint)


def cell_reference(reference):
    match = re.fullmatch(r"([A-Z]{1,3})([1-9][0-9]{0,6})", reference or "")
    if match is None:
        raise ValueError("Referência de célula inválida.")
    column = 0
    for letter in match[1]:
        column = column * 26 + ord(letter) - 64
    row = int(match[2])
    if column > MAX_XLSX_COLUMNS or row > MAX_XLSX_ROWS:
        raise ValueError("Referência de célula fora dos limites XLSX.")
    return column, row


def shared_string(strings, raw):
    if raw is None or re.fullmatch(r"[0-9]{1,10}", raw) is None:
        raise ValueError("Índice de texto compartilhado inválido.")
    index = int(raw)
    if index >= len(strings):
        raise ValueError("Índice de texto compartilhado fora dos limites.")
    return strings[index]


def _tree(archive, path, checkpoint=None):
    if archive.getinfo(path).file_size > MAX_METADATA_BYTES:
        raise ValueError("Metadados XLSX excedem o limite de recursos.")
    with xml_source(archive, path, checkpoint) as source:
        return ET.parse(source).getroot()


def _target(base, target):
    if not target or "\\" in target or "?" in target or "#" in target or ":" in target:
        raise ValueError("Relacionamento XLSX com destino inválido.")
    path = posixpath.normpath(
        target.lstrip("/")
        if target.startswith("/")
        else posixpath.join(posixpath.dirname(base), target)
    )
    if path.startswith("../") or path in (".", ".."):
        raise ValueError("Relacionamento XLSX fora do pacote.")
    return path


def validate_xlsx_container(archive, checkpoint=None):
    """Validate OPC structure with bounded metadata; worksheets stay streaming."""
    entries = archive.infolist()
    names = {info.filename for info in entries}
    if len(entries) > MAX_XLSX_ENTRIES or len(names) != len(entries):
        raise ValueError("O XLSX contém arquivos internos excessivos ou duplicados.")
    if sum(info.file_size for info in entries) > MAX_XLSX_BYTES:
        raise ValueError("O XLSX excede o limite de recursos descomprimidos.")
    for info in entries:
        if info.flag_bits & 1 or info.file_size > MAX_PART_BYTES:
            raise ValueError("Parte XLSX criptografada ou acima do limite de recursos.")
        if info.file_size > 4 * 1024 * 1024 and info.file_size > max(1, info.compress_size) * 1000:
            raise ValueError("Compressão XLSX excede o limite de recursos.")
        if (
            info.filename.startswith("/")
            or "\\" in info.filename
            or posixpath.normpath(info.filename) != info.filename
        ):
            raise ValueError("Nome de parte XLSX inválido.")
    required = {
        "[Content_Types].xml",
        "_rels/.rels",
        "xl/workbook.xml",
        "xl/_rels/workbook.xml.rels",
    }
    if not required <= names:
        raise ValueError("A planilha não possui a estrutura XLSX esperada.")
    types = _tree(archive, "[Content_Types].xml", checkpoint)
    if types.tag != CONTENT_NS + "Types":
        raise ValueError("Content types XLSX inválidos.")
    overrides, defaults = {}, {}
    for child in types:
        if child.tag == CONTENT_NS + "Override":
            part = child.get("PartName", "")
            if (
                not part.startswith("/")
                or part[1:] not in names
                or part in overrides
                or not child.get("ContentType")
            ):
                raise ValueError("Content type XLSX com parte inválida ou duplicada.")
            overrides[part] = child.get("ContentType")
        elif child.tag == CONTENT_NS + "Default":
            extension = child.get("Extension", "")
            if not extension or extension in defaults or not child.get("ContentType"):
                raise ValueError("Content type XLSX inválido ou duplicado.")
            defaults[extension] = child.get("ContentType")
        else:
            raise ValueError("Content type XLSX inválido.")

    def content_type(path):
        return overrides.get("/" + path, defaults.get(path.rsplit(".", 1)[-1]))

    if content_type("xl/workbook.xml") != MAIN_TYPE:
        raise ValueError("Content type do workbook XLSX inválido.")
    relations = {}
    for relpath in sorted(name for name in names if name.endswith(".rels")):
        root = _tree(archive, relpath, checkpoint)
        if root.tag != REL_NS + "Relationships":
            raise ValueError("Relacionamentos XLSX inválidos.")
        base = (
            ""
            if relpath == "_rels/.rels"
            else posixpath.join(
                posixpath.dirname(posixpath.dirname(relpath)), posixpath.basename(relpath)[:-5]
            )
        )
        found = {}
        for item in root:
            identifier, kind = item.get("Id"), item.get("Type", "")
            if (
                item.tag != REL_NS + "Relationship"
                or not identifier
                or identifier in found
                or not kind
            ):
                raise ValueError("Relacionamento XLSX inválido ou duplicado.")
            if item.get("TargetMode") == "External":
                found[identifier] = (kind, None)
                continue
            if item.get("TargetMode") not in (None, "Internal"):
                raise ValueError("Modo de relacionamento XLSX inválido.")
            target = _target(base, item.get("Target", ""))
            if target not in names or content_type(target) is None:
                raise ValueError("Relacionamento XLSX aponta para componente ausente.")
            found[identifier] = kind, target
        relations[base] = found
    office = [
        target for kind, target in relations[""].values() if kind == OFFICE_REL + "officeDocument"
    ]
    if office != ["xl/workbook.xml"]:
        raise ValueError("Relacionamento principal XLSX inválido.")
    workbook = _tree(archive, "xl/workbook.xml", checkpoint)
    if workbook.tag != NS + "workbook":
        raise ValueError("Workbook XLSX inválido.")
    sheets, identifiers = {}, set()
    for sheet in workbook.findall(NS + "sheets/" + NS + "sheet"):
        name = sheet.get("name", "")
        identifier = sheet.get("{" + OFFICE_REL[:-1] + "}id", "")
        kind, target = relations["xl/workbook.xml"].get(identifier, (None, None))
        if (
            not name
            or name in sheets
            or identifier in identifiers
            or kind != OFFICE_REL + "worksheet"
            or target is None
            or content_type(target) != SHEET_TYPE
        ):
            raise ValueError("Aba ou relacionamento de aba XLSX inválido.")
        sheets[name] = target
        identifiers.add(identifier)
    if not sheets:
        raise ValueError("Workbook XLSX sem abas.")
    # Parse auxiliary XML too, bounded by the metadata budget. Sheet payloads
    # are checked by row iterators, so no dense workbook is allocated here.
    sheet_parts = set(sheets.values())
    for path in names:
        if path.endswith(".xml") and path not in sheet_parts and path != "xl/sharedStrings.xml":
            _tree(archive, path, checkpoint)
    return sheets


def read_shared_strings(archive, checkpoint=None):
    path = "xl/sharedStrings.xml"
    if path not in archive.namelist():
        return []
    if archive.getinfo(path).file_size > MAX_SHARED_STRINGS_BYTES:
        raise ValueError("Textos compartilhados XLSX excedem o limite de recursos.")
    strings = []
    with xml_source(archive, path, checkpoint) as source:
        root = None
        for event, element in ET.iterparse(source, events=("start", "end")):
            if root is None:
                root = element
                if root.tag != NS + "sst":
                    raise ValueError("Textos compartilhados XLSX inválidos.")
            if event == "end" and element.tag == NS + "si":
                value = "".join(node.text or "" for node in element.iter(NS + "t"))
                if len(value) > 32767 or len(strings) >= MAX_SHARED_STRINGS:
                    raise ValueError("Textos compartilhados XLSX excedem o limite de recursos.")
                strings.append(value)
                element.clear()
                root.clear()
    return strings


def period(value, start, end):
    if isinstance(value, (Decimal, int, float)) and not isinstance(value, bool):
        month = value if isinstance(value, Decimal) else Decimal(str(value))
        if not month.is_finite() or month != month.to_integral_value():
            raise ValueError("Mês numérico deve ser inteiro.")
        if not 1 <= month <= 12:
            raise ValueError("Mês inválido ou fora do período do relatório.")
        text = str(int(month))
    else:
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


def _rows(archive, path, strings, checkpoint, max_columns=13, *, allow_formulas=False):
    container = None
    counter = 0
    previous_line = 0
    root_seen = False
    depth = 0
    with xml_source(archive, path, checkpoint) as source:
        for event, element in ET.iterparse(source, events=("start", "end")):
            if event == "start":
                depth += 1
                if depth > 64:
                    raise ValueError("XML XLSX excede a profundidade permitida.")
                if not root_seen:
                    root_seen = True
                    if element.tag != NS + "worksheet":
                        raise ValueError("XML da aba XLSX inválido.")
                if element.tag == NS + "sheetData":
                    container = element
                continue
            depth -= 1
            if element.tag != NS + "row":
                continue
            line = element.get("r", "")
            if (
                re.fullmatch(r"[1-9][0-9]{0,6}", line) is None
                or not previous_line < int(line) <= MAX_XLSX_ROWS
            ):
                raise ValueError("Referência de linha XLSX inválida ou duplicada.")
            previous_line = int(line)
            values, seen = {}, set()
            for cell in element.findall(NS + "c"):
                index, cell_row = cell_reference(cell.get("r", ""))
                if cell_row != previous_line or index in seen:
                    raise ValueError("Referência de célula duplicada ou fora da linha.")
                seen.add(index)
                formula = cell.find(NS + "f") is not None
                if formula and not allow_formulas:
                    raise ValueError("Fórmula não permitida na base do BI.")
                kind = cell.get("t")
                raw = cell.findtext(NS + "v")
                if formula:
                    # Structural validation permits formulas in auxiliary
                    # sheets; the exact fact audit rejects them independently.
                    value = raw or None
                elif kind == "inlineStr":
                    value = "".join(x.text or "" for x in cell.findall(".//" + NS + "t"))
                    if len(value) > 32767:
                        raise ValueError("Texto de célula XLSX excede o limite.")
                elif kind == "s":
                    value = shared_string(strings, raw)
                elif kind in (None, "n"):
                    try:
                        if raw is not None and len(raw) > 256:
                            raise ValueError("Número XLSX excede o limite de recursos.")
                        value = Decimal(raw) if raw is not None else None
                    except InvalidOperation as exc:
                        raise ValueError("Número inválido no Excel.") from exc
                elif kind == "str":
                    value = raw or ""
                elif kind in ("b", "e", "d") and allow_formulas:
                    value = raw
                else:
                    raise ValueError("Tipo de célula inválido para a base do BI.")
                if index <= max_columns:
                    values[index - 1] = value
            counter += 1
            row = tuple(values.get(i) for i in range(min(max_columns, max(values, default=-1) + 1)))
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
        rows = _rows(archive, product_path, strings, checkpoint, 2)
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
                rows = _rows(
                    archive, sheet_path, strings, checkpoint, 13 if kind == "general" else 11
                )
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
