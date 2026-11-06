"""Leitura offline do modelo LIARTE e de bases portáteis validadas.

Nunca executa SQL, M ou DAX. Copia apenas campos de estoque e saídas agregadas;
clientes, documentos, pedidos e dados financeiros de terceiros são descartados.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
import tempfile
import zipfile
import zlib
from dataclasses import fields
from datetime import date, datetime
from itertools import chain
from pathlib import Path
from threading import Event

from .inventory import SCALE, Balance, Closing, InventoryData, Product, Sale, _checked, scaled
from .inventory_source import inventory_from_records
from .query import checkpoint

FORMAT = "liarte.inventory/1"
MAX_COMPRESSED = 512 * 1024 * 1024
MAX_JSON = 180 * 1024 * 1024
RECORD_LIMITS = {
    "products": 100_000,
    "balances": 200_000,
    "closings": 2_000_000,
    "sales": 2_000_000,
}
_FIELDS = {
    cls: tuple(field.name for field in fields(cls)) for cls in (Product, Balance, Closing, Sale)
}


def _hash(path: Path, cancel: Event) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            checkpoint(cancel)
            digest.update(block)
    return digest.hexdigest()


def _text(value, label="campo", *, empty=False, max_length=1000) -> str:
    if not isinstance(value, str) or len(value) > max_length or not value.strip() and not empty:
        raise ValueError(f"{label} ausente ou inválido na base.")
    if any(
        not (
            c in "\t\n\r"
            or " " <= c <= "\ud7ff"
            or "\ue000" <= c <= "\ufffd"
            or "\U00010000" <= c <= "\U0010ffff"
        )
        for c in value
    ):
        raise ValueError(f"{label} contém caractere inválido para XML/Excel na base.")
    return value.strip()


def _integer(value) -> int:
    if type(value) is not int or abs(value) > 10**23:
        raise ValueError("Quantidade ou custo inválido na base.")
    return value


def _ratio(value) -> float | None:
    if value is None:
        return None
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or abs(value) > 10**24
        or not math.isfinite(value)
    ):
        raise ValueError("Indicador de giro ou dias inválido na fonte.")
    return float(value)


def validate_data(data: InventoryData, cancel: Event | None = None) -> InventoryData:
    cancel = cancel or Event()
    checkpoint(cancel)
    _check_counts(data)
    if not data.products or not data.balances:
        raise ValueError("A base não contém produtos e saldos atuais.")
    if (
        type(data.as_of) is not date
        or not isinstance(data.source_hash, str)
        or len(data.source_hash) != 64
        or any(c not in "0123456789abcdef" for c in data.source_hash)
    ):
        raise ValueError("Identificação da fonte inválida.")
    _text(data.source_name, "Nome da fonte")
    codes = set()
    for p in data.products:
        checkpoint(cancel)
        for label in _FIELDS[Product]:
            _text(getattr(p, label), "Produto · " + label)
        if p.code in codes:
            raise ValueError(f"Código de produto duplicado: {p.code}")
        codes.add(p.code)
    seen = set()
    for row in chain(data.balances, data.closings):
        checkpoint(cancel)
        for label in ("product", "branch", "warehouse", "unit"):
            _text(getattr(row, label), "Posição · " + label)
        if row.product not in codes:
            raise ValueError(f"Produto sem cadastro: {row.product}")
        _integer(row.quantity)
        _integer(row.cost)
        key = (type(row).__name__, row.product, row.branch, row.warehouse, row.unit)
        if isinstance(row, Closing):
            if not isinstance(row.period, str) or len(row.period) != 7:
                raise ValueError("Mês de fechamento inválido.")
            if date.fromisoformat(row.period + "-01") > data.as_of:
                raise ValueError("Fechamento posterior à data da base.")
            _ratio(row.turnover)
            _ratio(row.days)
            key += (row.period,)
        if key in seen:
            raise ValueError("Saldos duplicados na mesma posição de estoque.")
        seen.add(key)
    seen_sales = set()
    for sale in data.sales:
        checkpoint(cancel)
        for label in ("product", "branch", "unit"):
            _text(getattr(sale, label), "Venda · " + label)
        if sale.product not in codes or type(sale.day) is not date or sale.day > data.as_of:
            raise ValueError("Venda sem produto cadastrado ou posterior à data da base.")
        _integer(sale.quantity)
        _integer(sale.cost)
        if sale.had_positive is not None and type(sale.had_positive) is not bool:
            raise ValueError("Sinal de venda positiva inválido na base.")
        key = (sale.product, sale.branch, sale.unit, sale.day)
        if key in seen_sales:
            raise ValueError("Vendas duplicadas no mesmo dia, produto, filial e unidade.")
        seen_sales.add(key)
    for label, entries in (("Filial", data.branches), ("Armazém", data.warehouses)):
        if not isinstance(entries, (tuple, list)) or any(
            not isinstance(row, (tuple, list)) or len(row) != 2 for row in _checked(entries, cancel)
        ):
            raise ValueError("Dimensão de local inválida na base.")
        keys = set()
        for key, value in _checked(entries, cancel):
            _text(key, label + " · código")
            _text(value, label + " · nome")
            if key in keys:
                raise ValueError("Dimensão de local duplicada.")
            keys.add(key)
    if not isinstance(data.notes, (tuple, list)):
        raise ValueError("Notas inválidas na base.")
    for note in _checked(data.notes, cancel):
        _text(note, "Nota")
    _check_json_capacity(data, cancel)
    return data


def _check_counts(data):
    for name, limit in RECORD_LIMITS.items():
        values = data[name] if isinstance(data, dict) else getattr(data, name)
        if not isinstance(values, (list, tuple)) or len(values) > limit:
            raise ValueError("A base ultrapassa o limite de registros ou contém coleção inválida.")


def _snapshot_chunks(data: InventoryData, cancel: Event):
    """JSON canônico em fluxo: sem listas/dicionários adicionais por fato."""
    encode = json.JSONEncoder(ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode
    header = {
        "format": FORMAT,
        "as_of": data.as_of.isoformat(),
        "source_name": data.source_name,
        "source_hash": data.source_hash,
    }
    yield encode(header)[:-1]
    for name in (*RECORD_LIMITS, "branches", "warehouses", "notes"):
        yield "," + encode(name) + ":["
        for index, row in enumerate(_checked(getattr(data, name), cancel)):
            if index:
                yield ","
            if name in RECORD_LIMITS:
                row = [getattr(row, field) for field in _FIELDS[type(row)]]
                if name == "sales":
                    row[3] = row[3].isoformat()
            yield encode(row)
        yield "]"
    yield "}"


def _encoded_snapshot(data: InventoryData, cancel: Event):
    size = 0
    for chunk in _snapshot_chunks(data, cancel):
        body = chunk.encode("utf-8")
        size += len(body)
        if size > MAX_JSON:
            raise ValueError("A base expandida ultrapassa o limite permitido.")
        yield body


def _check_json_capacity(data: InventoryData, cancel: Event):
    for _ in _encoded_snapshot(data, cancel):
        pass


def read_snapshot(path: Path, cancel: Event | None = None) -> InventoryData:
    cancel = cancel or Event()
    if path.stat().st_size > MAX_COMPRESSED:
        raise ValueError("A base ultrapassa o tamanho permitido.")
    checkpoint(cancel)
    try:
        with gzip.open(path, "rb") as stream:
            body = bytearray()
            while block := stream.read(min(1024 * 1024, MAX_JSON + 1 - len(body))):
                checkpoint(cancel)
                body.extend(block)
                if len(body) > MAX_JSON:
                    break
        if len(body) > MAX_JSON:
            raise ValueError("A base expandida ultrapassa o limite permitido.")
        checkpoint(cancel)
        p = json.loads(body)
        if not isinstance(p, dict) or p.get("format") != FORMAT:
            raise ValueError("Formato de base de estoque não reconhecido.")
        allowed = {
            "format",
            "as_of",
            "source_name",
            "source_hash",
            "products",
            "balances",
            "closings",
            "sales",
            "branches",
            "warehouses",
            "notes",
        }
        if set(p) != allowed:
            raise ValueError("Estrutura de base incompatível.")
        _check_counts(p)

        def records(name, arities):
            values = p[name]
            if not isinstance(values, list):
                raise ValueError(f"Coleção {name} inválida na base.")
            for row in _checked(values, cancel):
                if not isinstance(row, list) or len(row) not in arities:
                    raise ValueError(f"Registro {name} inválido na base.")
                yield row

        if not isinstance(p["notes"], list):
            raise ValueError("Notas inválidas na base.")
        return inventory_from_records(
            as_of=date.fromisoformat(p["as_of"]),
            source_name=p["source_name"],
            source_hash=p["source_hash"],
            products=tuple(Product(*r) for r in records("products", (5,))),
            balances=tuple(Balance(*r) for r in records("balances", (6,))),
            closings=tuple(Closing(*r) for r in records("closings", (9,))),
            sales=tuple(Sale(*r[:3], date.fromisoformat(r[3]), *r[4:]) for r in records("sales", (6, 7))),
            branches=tuple(tuple(r) for r in records("branches", (2,))),
            warehouses=tuple(tuple(r) for r in records("warehouses", (2,))),
            notes=tuple(p["notes"]),
            cancel=cancel,
        )
    except (
        OSError,
        EOFError,
        zlib.error,
        json.JSONDecodeError,
        TypeError,
        KeyError,
        AttributeError,
        RecursionError,
    ) as exc:
        raise ValueError(
            "Não foi possível ler esta base de estoque. Selecione um arquivo .liarte válido."
        ) from exc


def write_snapshot(data: InventoryData, path: Path, cancel: Event | None = None):
    """Publica atomicamente; a base anterior permanece íntegra em caso de falha."""
    cancel = cancel or Event()
    validate_data(data, cancel)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".estoque-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as stream:
                pending = bytearray()
                for chunk in _encoded_snapshot(data, cancel):
                    pending.extend(chunk)
                    if len(pending) >= 64 * 1024:
                        checkpoint(cancel)
                        stream.write(pending)
                        pending.clear()
                stream.write(pending)
            if raw.tell() > MAX_COMPRESSED:
                raise ValueError("A base ultrapassa o tamanho permitido.")
            raw.flush()
            os.fsync(raw.fileno())
        checkpoint(cancel)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def read_pbix(
    path: Path, cancel: Event | None = None, progress=lambda value, label: None
) -> InventoryData:
    cancel = cancel or Event()
    if path.stat().st_size > MAX_COMPRESSED:
        raise ValueError("Selecione um PBIX de até 512 MB.")
    try:
        with zipfile.ZipFile(path) as archive:
            info = archive.getinfo("DataModel")
            if info.file_size > MAX_COMPRESSED:
                raise ValueError("O modelo de dados ultrapassa o limite permitido.")
    except (zipfile.BadZipFile, KeyError) as exc:
        raise ValueError(
            "Este arquivo não contém a base de dados. Exporte o PBIX com dados do modelo."
        ) from exc
    progress(5, "Lendo o modelo de dados")
    source_hash = _hash(path, cancel)
    from pandas import isna
    from pbixray import PBIXRay

    def indicator(value):
        return None if isna(value) else _ratio(float(value))

    with PBIXRay(str(path)) as model:
        required = {
            "Dim_Produtos",
            "Dim_Filiais",
            "Dim_Armazem",
            "Dim_Atualizacao",
            "Fato_EstoqueAtual",
            "Fact_Estoque",
            "Fato_DocumentoSaida",
        }
        if not required.issubset(model.tables):
            raise ValueError("O PBIX não contém as tabelas de estoque do modelo LIARTE esperado.")

        def table(name, columns):
            checkpoint(cancel)
            df = model.get_table(name, columns=columns)
            if not set(columns).issubset(df.columns):
                raise ValueError(f"Colunas obrigatórias ausentes em {name}.")
            if "DELETED" in df:
                flags = df["DELETED"].fillna("").astype(str).str.strip().str.casefold()
                if not flags.isin(("", "0", "0.0", "false", "*", "1", "1.0", "true")).all():
                    raise ValueError(f"Marcador de exclusão não reconhecido em {name}.")
                df = df[flags.isin(("", "0", "0.0", "false"))]
            capacity = {
                "Dim_Produtos": "products",
                "Fato_EstoqueAtual": "balances",
                "Fact_Estoque": "closings",
            }.get(name)
            if capacity and len(df) > RECORD_LIMITS[capacity]:
                raise ValueError("A base ultrapassa o limite de registros.")
            return df.loc[:, columns]

        stamp = table("Dim_Atualizacao", ["Data Atualizacao"])["Data Atualizacao"].tolist()
        if len(stamp) != 1:
            raise ValueError("A data de atualização do modelo não está disponível.")
        as_of = None
        for fmt in ("%m/%d/%Y %I:%M:%S %p", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%Y-%m-%d"):
            try:
                as_of = datetime.strptime(str(stamp[0]), fmt).date()
                break
            except ValueError:
                pass
        if as_of is None:
            raise ValueError("Formato de data de atualização do modelo não reconhecido.")
        progress(15, "Carregando produtos e locais")
        pcols = [
            "CodProduto",
            "NomeProduto",
            "NomeGrupo",
            "TipoProduto",
            "UnidadeMedida",
            "DELETED",
        ]
        products = tuple(
            Product(
                _text(a, "Produto"),
                _text(b, "Descrição"),
                _text(c, empty=True) or "Sem grupo",
                _text(d, empty=True) or "Sem tipo",
                _text(e, empty=True) or "—",
            )
            for a, b, c, d, e, _ in _checked(
                table("Dim_Produtos", pcols).fillna("").itertuples(index=False, name=None), cancel
            )
        )
        branches = tuple(
            (str(a).strip(), str(b).strip())
            for a, b, _ in _checked(
                table("Dim_Filiais", ["CodFilial", "NomeFilial", "DELETED"]).itertuples(
                    index=False, name=None
                ),
                cancel,
            )
        )
        warehouses = tuple(
            (str(a).strip(), str(b).strip())
            for a, b, _ in _checked(
                table("Dim_Armazem", ["CodArmazem", "Descricao", "DELETED"]).itertuples(
                    index=False, name=None
                ),
                cancel,
            )
        )
        progress(25, "Conferindo saldos atuais")
        balances = []
        for product, branch, warehouse, unit, qty, cost, _ in _checked(
            table(
                "Fato_EstoqueAtual",
                [
                    "Produto",
                    "Filial",
                    "Armazem",
                    "UnidadeMedida",
                    "SaldoFechamento",
                    "CustoTotal",
                    "DELETED",
                ],
            ).itertuples(index=False, name=None),
            cancel,
        ):
            balances.append(
                Balance(
                    _text(product),
                    _text(branch),
                    _text(warehouse),
                    _text(unit),
                    scaled(qty, SCALE),
                    scaled(cost, 100),
                )
            )
        progress(35, "Carregando fechamentos mensais")
        closings = []
        cols = [
            "Produto",
            "Filial",
            "Armazem",
            "UnidadeMedida",
            "DataFechamento",
            "SaldoFechamento",
            "CustoTotal",
            "GiroEstoqueMensalQtd",
            "DiasEstoqueQtd",
            "DELETED",
        ]
        for i, (product, branch, warehouse, unit, day, qty, cost, giro, days, _) in enumerate(
            table("Fact_Estoque", cols).itertuples(index=False, name=None)
        ):
            if i % 2000 == 0:
                checkpoint(cancel)
            closings.append(
                Closing(
                    _text(product),
                    _text(branch),
                    _text(warehouse),
                    _text(unit),
                    day.strftime("%Y-%m"),
                    scaled(qty, SCALE),
                    scaled(cost, 100),
                    indicator(giro),
                    indicator(days),
                )
            )
        progress(65, "Consolidando vendas por produto")
        # Sem códigos de cliente, documentos, pedidos ou vendedores no destino.
        daily = {}
        cols = [
            "Produto",
            "Filial",
            "UnidadeMedida",
            "DataEmissao",
            "Quantidade",
            "CustoTotal",
            "DELETED",
        ]
        for i, (product, branch, unit, day, qty, cost, _) in enumerate(
            table("Fato_DocumentoSaida", cols).itertuples(index=False, name=None)
        ):
            if i % 2000 == 0:
                checkpoint(cancel)
            key = (_text(product), _text(branch), _text(unit), day.date())
            total = daily.setdefault(key, [0, 0, False])
            if len(daily) > RECORD_LIMITS["sales"]:
                raise ValueError("A base ultrapassa o limite de registros.")
            quantity = scaled(qty, SCALE)
            total[0] += quantity
            total[1] += scaled(cost, 100)
            total[2] = total[2] or quantity > 0
        sales = tuple(
            Sale(*key, *values) for key, values in _checked(sorted(daily.items()), cancel)
        )
        checkpoint(cancel)
        # Chaves antigas sem dimensão não podem desaparecer dos saldos/histórico.
        # Preservar valores e sinalizar o cadastro ausente, sem inventar descrição.
        codes = {p.code for p in products}
        missing = {r.product for r in _checked(chain(balances, closings, sales), cancel)} - codes
        if len(products) + len(missing) > RECORD_LIMITS["products"]:
            raise ValueError("A base ultrapassa o limite de registros.")
        products += tuple(
            Product(code, "Cadastro indisponível · " + code, "Sem cadastro", "Sem cadastro", "—")
            for code in sorted(missing)
        )
        notes = (
            (f"{len(missing)} códigos históricos sem cadastro de produto; valores preservados.",)
            if missing
            else ()
        )
        if any(
            (c.turnover is not None and c.turnover < 0)
            or (c.days is not None and (c.days < 0 or c.days > 36500))
            for c in closings
        ):
            notes += (
                "O BI contém indicadores de giro/dias negativos ou extremos; os valores originais foram preservados.",
            )
    if _hash(path, cancel) != source_hash:
        raise ValueError(
            "O PBIX foi alterado durante a leitura. Aguarde a atualização e tente novamente."
        )
    progress(85, "Validando a base de estoque")
    data = inventory_from_records(
        as_of=as_of,
        source_name=path.name,
        source_hash=source_hash,
        products=products,
        balances=balances,
        closings=closings,
        sales=sales,
        branches=branches,
        warehouses=warehouses,
        notes=notes,
        cancel=cancel,
    )
    progress(95, "Preparando a análise")
    return data


def load_inventory(path: Path, cancel: Event, progress=lambda value, label: None) -> InventoryData:
    if not path.is_file():
        raise ValueError("Arquivo não encontrado. Selecione novamente a base de estoque.")
    if path.suffix.lower() == ".pbix":
        return read_pbix(path, cancel, progress)
    if path.suffix.lower() == ".liarte":
        progress(20, "Carregando a base de estoque")
        data = read_snapshot(path, cancel)
        progress(95, "Preparando a análise")
        return data
    raise ValueError("Selecione um arquivo PBIX com dados ou uma base .liarte.")
