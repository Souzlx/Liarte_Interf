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
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from threading import Event

from .inventory import SCALE, Balance, Closing, InventoryData, Product, Sale, scaled
from .query import checkpoint

FORMAT = "liarte.inventory/1"
MAX_COMPRESSED = 512 * 1024 * 1024
MAX_JSON = 180 * 1024 * 1024


def _hash(path: Path, cancel: Event) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            checkpoint(cancel)
            digest.update(block)
    return digest.hexdigest()


def _text(value, label="campo", *, empty=False) -> str:
    if (
        not isinstance(value, str)
        or len(value) > 1000
        or "\0" in value
        or not value.strip()
        and not empty
    ):
        raise ValueError(f"{label} ausente ou inválido na base.")
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
        or not math.isfinite(value)
        or abs(value) > 10**24
    ):
        raise ValueError("Indicador de giro ou dias inválido na fonte.")
    return float(value)


def validate_data(data: InventoryData, cancel: Event | None = None) -> InventoryData:
    cancel = cancel or Event()
    if not data.products or not data.balances:
        raise ValueError("A base não contém produtos e saldos atuais.")
    if (
        not isinstance(data.as_of, date)
        or len(data.source_hash) != 64
        or any(c not in "0123456789abcdef" for c in data.source_hash)
    ):
        raise ValueError("Identificação da fonte inválida.")
    _text(data.source_name, "Nome da fonte")
    codes = set()
    for p in data.products:
        checkpoint(cancel)
        for label, value in asdict(p).items():
            _text(value, label)
        if p.code in codes:
            raise ValueError(f"Código de produto duplicado: {p.code}")
        codes.add(p.code)
    seen = set()
    for row in (*data.balances, *data.closings):
        checkpoint(cancel)
        for value in (row.product, row.branch, row.warehouse, row.unit):
            _text(value)
        if row.product not in codes:
            raise ValueError(f"Produto sem cadastro: {row.product}")
        _integer(row.quantity)
        _integer(row.cost)
        key = (type(row).__name__, row.product, row.branch, row.warehouse, row.unit)
        if isinstance(row, Closing):
            if len(row.period) != 7:
                raise ValueError("Mês de fechamento inválido.")
            if date.fromisoformat(row.period + "-01") > data.as_of:
                raise ValueError("Fechamento posterior à data da base.")
            _ratio(row.turnover)
            _ratio(row.days)
            key += (row.period,)
        if key in seen:
            raise ValueError("Saldos duplicados na mesma posição de estoque.")
        seen.add(key)
    for sale in data.sales:
        checkpoint(cancel)
        for value in (sale.product, sale.branch, sale.unit):
            _text(value)
        if sale.product not in codes or not isinstance(sale.day, date) or sale.day > data.as_of:
            raise ValueError("Venda sem produto cadastrado ou posterior à data da base.")
        _integer(sale.quantity)
        _integer(sale.cost)
        if sale.had_positive is not None and type(sale.had_positive) is not bool:
            raise ValueError("Sinal de venda positiva inválido na base.")
    for entries in (data.branches, data.warehouses):
        if len({k for k, _ in entries}) != len(entries):
            raise ValueError("Dimensão de local duplicada.")
        for key, value in entries:
            _text(key)
            _text(value)
    return data


def read_snapshot(path: Path, cancel: Event | None = None) -> InventoryData:
    cancel = cancel or Event()
    if path.stat().st_size > MAX_COMPRESSED:
        raise ValueError("A base ultrapassa o tamanho permitido.")
    checkpoint(cancel)
    try:
        with gzip.open(path, "rb") as stream:
            body = stream.read(MAX_JSON + 1)
        if len(body) > MAX_JSON:
            raise ValueError("A base expandida ultrapassa o limite permitido.")
        checkpoint(cancel)
        p = json.loads(body)
        if p.get("format") != FORMAT:
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
        if any(
            len(p[k]) > limit
            for k, limit in (
                ("products", 100_000),
                ("balances", 200_000),
                ("closings", 2_000_000),
                ("sales", 2_000_000),
            )
        ):
            raise ValueError("A base ultrapassa o limite de registros.")
        data = InventoryData(
            date.fromisoformat(p["as_of"]),
            p["source_name"],
            p["source_hash"],
            tuple(Product(*r) for r in p["products"]),
            tuple(Balance(*r) for r in p["balances"]),
            tuple(Closing(*r) for r in p["closings"]),
            tuple(Sale(*r[:3], date.fromisoformat(r[3]), *r[4:]) for r in p["sales"]),
            tuple(tuple(r) for r in p["branches"]),
            tuple(tuple(r) for r in p["warehouses"]),
            tuple(p["notes"]),
        )
        return validate_data(data, cancel)
    except (OSError, EOFError, json.JSONDecodeError, TypeError, KeyError, AttributeError) as exc:
        raise ValueError(
            "Não foi possível ler esta base de estoque. Selecione um arquivo .liarte válido."
        ) from exc


def write_snapshot(data: InventoryData, path: Path, cancel: Event | None = None):
    """Publica atomicamente; a base anterior permanece íntegra em caso de falha."""
    cancel = cancel or Event()
    validate_data(data, cancel)
    payload = {
        "format": FORMAT,
        "as_of": data.as_of.isoformat(),
        "source_name": data.source_name,
        "source_hash": data.source_hash,
    }
    for key in ("products", "balances", "closings", "sales"):
        payload[key] = [list(asdict(r).values()) for r in getattr(data, key)]
    for row in payload["sales"]:
        row[3] = row[3].isoformat()
    for key in ("branches", "warehouses", "notes"):
        payload[key] = getattr(data, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".estoque-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as stream:
                stream.write(
                    json.dumps(
                        payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")
                    ).encode("utf-8")
                )
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
            for a, b, c, d, e, _ in table("Dim_Produtos", pcols)
            .fillna("")
            .itertuples(index=False, name=None)
        )
        branches = tuple(
            (str(a).strip(), str(b).strip())
            for a, b, _ in table("Dim_Filiais", ["CodFilial", "NomeFilial", "DELETED"]).itertuples(
                index=False, name=None
            )
        )
        warehouses = tuple(
            (str(a).strip(), str(b).strip())
            for a, b, _ in table("Dim_Armazem", ["CodArmazem", "Descricao", "DELETED"]).itertuples(
                index=False, name=None
            )
        )
        progress(25, "Conferindo saldos atuais")
        balances = []
        for product, branch, warehouse, unit, qty, cost, _ in table(
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
        ).itertuples(index=False, name=None):
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
            quantity = scaled(qty, SCALE)
            total[0] += quantity
            total[1] += scaled(cost, 100)
            total[2] = total[2] or quantity > 0
        sales = tuple(Sale(*key, *values) for key, values in sorted(daily.items()))
        checkpoint(cancel)
        # Chaves antigas sem dimensão não podem desaparecer dos saldos/histórico.
        # Preservar valores e sinalizar o cadastro ausente, sem inventar descrição.
        codes = {p.code for p in products}
        missing = {r.product for r in (*balances, *closings, *sales)} - codes
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
    data = validate_data(
        InventoryData(
            as_of,
            path.name,
            source_hash,
            products,
            tuple(balances),
            tuple(closings),
            sales,
            branches,
            warehouses,
            notes,
        ),
        cancel,
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
