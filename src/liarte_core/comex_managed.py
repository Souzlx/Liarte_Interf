"""Retoma somente uma central que este usuário já configurou neste computador.

Não descobre computadores na LAN, não copia chaves e não transforma um cliente
remoto em servidor. A configuração existente, protegida por DPAPI no Windows,
é a autorização para conservar endereço, porta, chave e diretório de dados.
"""

from __future__ import annotations

import hmac
import ipaddress
import json
import math
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from liarte_engine.comex_gateway_client import GatewayConnection, GatewayError, load_connection


@dataclass(frozen=True)
class ManagedCentral:
    connection: GatewayConnection
    host: str
    port: int
    interval: float
    directory: Path

    @property
    def local_connection(self):
        host = "127.0.0.1" if self.host == "0.0.0.0" else self.host
        return GatewayConnection(True, f"http://{host}:{self.port}", self.connection.token)

    def matches(self, connection):
        return connection.url == self.connection.url and hmac.compare_digest(
            connection.token, self.connection.token
        )


def read_managed(directory):
    path = Path(directory).parent / "central-comex" / "central.json"
    if not path.is_file():
        return None
    connection = load_connection(path)  # Inclui tamanho máximo e proteção da chave.
    if not connection.enabled:
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        host = ipaddress.ip_address(value["host"])
        port, interval = value["port"], value.get("interval", 65)
        parts = urlsplit(connection.url)
        if (
            host.version != 4
            or host.is_multicast
            or not (host.is_private or host.is_loopback or host.is_unspecified)
            or type(port) is not int
            or not 1 <= port <= 65535
            or type(interval) not in (int, float)
            or not math.isfinite(interval)
            or not 0 <= interval <= 3600
            or parts.scheme != "http"
            or (parts.port or 80) != port
            or parts.path not in ("", "/")
        ):
            raise ValueError("Endereço ou intervalo inválido.")
        return ManagedCentral(connection, str(host), port, float(interval), path.parent / "dados")
    except (ValueError, KeyError, TypeError) as exc:
        raise GatewayError("A configuração da central deste computador está inválida.") from exc
