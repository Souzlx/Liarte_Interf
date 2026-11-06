"""Independent numeric reference from the data already saved inside a PBIX.

This reader never invokes the application's PBIX importer, its normalizer or
its calculations. It deliberately projects only stock facts and aggregated
sales; no model expressions, connections or SQL are executed. Integer scales
and per-row rounding follow the documented stock contract through a separate
implementation so import/conversion regressions can be detected.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Context, Decimal, InvalidOperation, Overflow, ROUND_HALF_UP, localcontext
import hashlib
import math
from pathlib import Path
from threading import Event
from typing import TYPE_CHECKING
import zipfile

from .inventory import Balance, Closing, Sale
from .query import checkpoint

if TYPE_CHECKING:
    from .inventory_reconciliation import InventoryReference

MAX_PBIX_BYTES = 512 * 1024 * 1024
REFERENCE_LIMITS = {"balances": 200_000, "closings": 2_000_000, "sales": 2_000_000}
_QUANTITY_SCALE = 1_000_000
_MONEY_SCALE = 100
_MAX_INTEGER = 10**23
_ACTIVE = {"", "0", "0.0", "false"}
_DELETED = {"*", "1", "1.0", "true"}
_COLUMNS = {
    "Dim_Atualizacao": ("Data Atualizacao",),
    "Fato_EstoqueAtual": (
        "Produto", "Filial", "Armazem", "UnidadeMedida", "SaldoFechamento", "CustoTotal",
        "DELETED",
    ),
    "Fact_Estoque": (
        "Produto", "Filial", "Armazem", "UnidadeMedida", "DataFechamento", "SaldoFechamento",
        "CustoTotal", "GiroEstoqueMensalQtd", "DiasEstoqueQtd", "DELETED",
    ),
    "Fato_DocumentoSaida": (
        "Produto", "Filial", "UnidadeMedida", "DataEmissao", "Quantidade", "CustoTotal",
        "DELETED",
    ),
}


def _digest(path: Path, cancel: Event) -> str:
    result = hashlib.sha256()
    count = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            checkpoint(cancel)
            count += len(chunk)
            if count > MAX_PBIX_BYTES:
                raise ValueError("O PBIX ultrapassa o limite de 512 MB para a referência.")
            result.update(chunk)
    checkpoint(cancel)
    return result.hexdigest()


def _identifier(value) -> str:
    if not isinstance(value, str) or len(value) > 1000 or not value.strip():
        raise ValueError("Identificador ausente ou inválido na referência PBIX.")
    if any(
        not (
            char in "\t\n\r"
            or " " <= char <= "\ud7ff"
            or "\ue000" <= char <= "\ufffd"
            or "\U00010000" <= char <= "\U0010ffff"
        )
        for char in value
    ):
        raise ValueError("Identificador contém caractere inválido na referência PBIX.")
    return value.strip()


def _scaled_reference(value, factor: int) -> int:
    """Independent HALF_UP rounding, unaffected by the caller's Decimal context."""
    try:
        parsed = Decimal(str(value))
        if not parsed.is_finite() or parsed.copy_abs() > Decimal("1e16"):
            raise ValueError("Valor numérico fora do limite na referência PBIX.")
        context = Context(
            prec=max(40, len(parsed.as_tuple().digits) + len(str(factor)) + 2),
            rounding=ROUND_HALF_UP, Emin=-999999, Emax=999999,
            traps=[InvalidOperation, Overflow],
        )
        with localcontext(context):
            result = int((parsed * factor).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    except (InvalidOperation, Overflow, TypeError, OverflowError) as exc:
        raise ValueError("Valor numérico inválido na referência PBIX.") from exc
    if abs(result) > _MAX_INTEGER:
        raise ValueError("Valor escalado fora do limite na referência PBIX.")
    return result


def _date_reference(value, is_missing) -> date:
    if is_missing(value) or not isinstance(value, date):
        raise ValueError("Data de fato ausente ou inválida na referência PBIX.")
    # Retain the source's calendar day. A PBIX timestamp has no demonstrated
    # timezone contract; this reader must not silently reinterpret it as UTC.
    return date(value.year, value.month, value.day)


def _stamp_reference(value) -> date:
    for pattern in (
        "%m/%d/%Y %I:%M:%S %p", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(str(value), pattern).date()
        except ValueError:
            continue
    raise ValueError("Data de atualização ausente ou inválida na referência PBIX.")


def _indicator_reference(value, is_missing) -> float | None:
    from pandas.api.types import is_bool

    if is_missing(value):
        return None
    if is_bool(value):
        raise ValueError("Indicador inválido na referência PBIX.")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Indicador inválido na referência PBIX.") from exc
    if not math.isfinite(number) or abs(number) > 10**24:
        raise ValueError("Indicador inválido na referência PBIX.")
    return number


def read_pbix_reference(
    path: Path, cancel: Event | None = None, progress=lambda value, label: None
) -> InventoryReference:
    """Read one independent, bounded and hash-guarded numeric source revision.

    Balances and closings preserve their complete position keys. Sales are
    rounded per item and aggregated daily by product/branch/unit; the presence
    of a positive quantity remains true even when returns produce net zero.
    ``counts`` records raw, accepted, deleted and output rows by source table.
    This is not an evaluation of DAX measures or Power BI visual filters.
    """
    from .inventory_reconciliation import InventoryReference

    cancel = cancel if cancel is not None else Event()
    checkpoint(cancel)
    path = Path(path)
    if path.suffix.casefold() != ".pbix" or not path.is_file():
        raise ValueError("Selecione um arquivo PBIX existente para a referência.")
    if path.stat().st_size > MAX_PBIX_BYTES:
        raise ValueError("O PBIX ultrapassa o limite de 512 MB para a referência.")
    try:
        with zipfile.ZipFile(path) as archive:
            models = [info for info in archive.infolist() if info.filename == "DataModel"]
            if len(models) != 1:
                raise ValueError("A referência exige um único DataModel gravado no PBIX.")
            if models[0].file_size > MAX_PBIX_BYTES:
                raise ValueError("O DataModel ultrapassa o limite de 512 MB para a referência.")
    except zipfile.BadZipFile as exc:
        raise ValueError("Arquivo PBIX inválido para a referência numérica.") from exc

    progress(5, "Conferindo a versão da referência PBIX")
    original_hash = _digest(path, cancel)
    from pandas import isna
    from pbixray import PBIXRay

    counts = {}
    balances, closings, daily = [], [], {}
    balance_keys, closing_keys = set(), set()
    with PBIXRay(str(path)) as model:
        if not set(_COLUMNS).issubset(model.tables):
            raise ValueError("Tabelas quantitativas obrigatórias ausentes no PBIX.")

        def rows(name):
            checkpoint(cancel)
            columns = _COLUMNS[name]
            frame = model.get_table(name, columns=list(columns))
            if any(list(frame.columns).count(column) != 1 for column in columns):
                raise ValueError(f"Colunas quantitativas ausentes ou duplicadas em {name}.")
            stats = {"rows": len(frame), "accepted": 0, "deleted": 0, "output": 0}
            counts[name] = stats
            for index, row in enumerate(
                frame.loc[:, list(columns)].itertuples(index=False, name=None)
            ):
                if index % 512 == 0:
                    checkpoint(cancel)
                if columns[-1] == "DELETED":
                    flag = "" if isna(row[-1]) else str(row[-1]).strip().casefold()
                    if flag in _DELETED:
                        stats["deleted"] += 1
                        continue
                    if flag not in _ACTIVE:
                        raise ValueError(f"Marcador de exclusão não reconhecido em {name}.")
                stats["accepted"] += 1
                yield row
            checkpoint(cancel)

        stamps = list(rows("Dim_Atualizacao"))
        if len(stamps) != 1:
            raise ValueError("A referência exige uma única data de atualização.")
        as_of = _stamp_reference(stamps[0][0])
        counts["Dim_Atualizacao"]["output"] = 1

        progress(20, "Lendo saldos da referência PBIX")
        for product, branch, warehouse, unit, quantity, cost, _ in rows("Fato_EstoqueAtual"):
            key = tuple(_identifier(value) for value in (product, branch, warehouse, unit))
            if key in balance_keys:
                raise ValueError("Posição de saldo duplicada na referência PBIX.")
            balance_keys.add(key)
            if len(balance_keys) > REFERENCE_LIMITS["balances"]:
                raise ValueError("A referência PBIX ultrapassa o limite de saldos.")
            balances.append(Balance(
                *key, _scaled_reference(quantity, _QUANTITY_SCALE),
                _scaled_reference(cost, _MONEY_SCALE),
            ))
        counts["Fato_EstoqueAtual"]["output"] = len(balances)

        progress(45, "Lendo fechamentos da referência PBIX")
        for product, branch, warehouse, unit, stamp, quantity, cost, turnover, days, _ in rows(
            "Fact_Estoque"
        ):
            position = tuple(_identifier(value) for value in (product, branch, warehouse, unit))
            closing_day = _date_reference(stamp, isna)
            if date(closing_day.year, closing_day.month, 1) > as_of:
                raise ValueError("Fechamento posterior à referência comercial do PBIX.")
            period = closing_day.isoformat()[:7]
            key = (*position, period)
            if key in closing_keys:
                raise ValueError("Posição de fechamento duplicada na referência PBIX.")
            closing_keys.add(key)
            if len(closing_keys) > REFERENCE_LIMITS["closings"]:
                raise ValueError("A referência PBIX ultrapassa o limite de fechamentos.")
            closings.append(Closing(
                *position, period, _scaled_reference(quantity, _QUANTITY_SCALE),
                _scaled_reference(cost, _MONEY_SCALE), _indicator_reference(turnover, isna),
                _indicator_reference(days, isna),
            ))
        counts["Fact_Estoque"]["output"] = len(closings)

        progress(70, "Agregando vendas da referência PBIX")
        for product, branch, unit, stamp, quantity, cost, _ in rows("Fato_DocumentoSaida"):
            day = _date_reference(stamp, isna)
            if day > as_of:
                raise ValueError("Venda posterior à referência comercial do PBIX.")
            key = (*(_identifier(value) for value in (product, branch, unit)), day)
            amount = _scaled_reference(quantity, _QUANTITY_SCALE)
            amount_cost = _scaled_reference(cost, _MONEY_SCALE)
            values = daily.setdefault(key, [0, 0, False])
            values[0] += amount
            values[1] += amount_cost
            values[2] = values[2] or amount > 0
            if len(daily) > REFERENCE_LIMITS["sales"]:
                raise ValueError("A referência PBIX ultrapassa o limite de vendas diárias.")
        counts["Fato_DocumentoSaida"]["output"] = len(daily)

    progress(95, "Validando a versão lida da referência PBIX")
    if _digest(path, cancel) != original_hash:
        raise ValueError("O PBIX foi alterado durante a leitura da referência.")
    sales = []
    ordering_count = 0

    def order(entry):
        nonlocal ordering_count
        if ordering_count % 512 == 0:
            checkpoint(cancel)
        ordering_count += 1
        return entry[0]

    for index, (key, values) in enumerate(sorted(daily.items(), key=order)):
        if index % 512 == 0:
            checkpoint(cancel)
        if abs(values[0]) > _MAX_INTEGER or abs(values[1]) > _MAX_INTEGER:
            raise ValueError("Agregado diário fora do limite na referência PBIX.")
        sales.append(Sale(*key, *values))
    checkpoint(cancel)
    result = InventoryReference(
        as_of=as_of, source_name=path.name, source_hash=original_hash,
        balances=tuple(balances), closings=tuple(closings), sales=tuple(sales), counts=counts,
    )
    progress(100, "Referência quantitativa preparada")
    checkpoint(cancel)
    return result
