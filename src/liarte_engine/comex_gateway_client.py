"""Protocolo da Central de Consultas. Sem fallback silencioso para a API oficial."""

from __future__ import annotations

import base64
import ctypes
from decimal import Decimal
from http.client import HTTPException
import json
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from .liarte_dados import atomic_json, json_bytes
from .secure_http import build_opener

PROTOCOL = "liarte.comex/1"
MAX_RESPONSE = 100 * 1024 * 1024
MAX_REQUEST = 2 * 1024 * 1024


class GatewayError(RuntimeError):
    pass


@dataclass(frozen=True)
class GatewayConnection:
    enabled: bool = False
    url: str = ""
    token: str = ""

    def __post_init__(self):
        if (
            type(self.enabled) is not bool
            or not isinstance(self.url, str)
            or not isinstance(self.token, str)
        ):
            raise ValueError("Modo de conexão inválido.")
        if self.enabled:
            try:
                parts = urllib.parse.urlsplit(self.url)
                valid = (
                    parts.scheme in {"http", "https"}
                    and parts.hostname
                    and parts.hostname not in {"0.0.0.0", "::"}
                    and parts.username is None
                    and parts.password is None
                    and not parts.query
                    and not parts.fragment
                    and parts.port != 0
                    and len(self.url) <= 512
                    and not any(c.isspace() or ord(c) < 32 for c in self.url)
                )
            except ValueError:
                valid = False
            if not valid:
                raise ValueError(
                    "Informe o endereço completo da central, como http://servidor:8767."
                )
            if not re.fullmatch(r"[A-Za-z0-9_\-]{32,256}", self.token):
                raise ValueError("Informe a chave fornecida pela Central de Consultas.")


def _dpapi(data: bytes, *, decode=False) -> bytes:
    class Blob(ctypes.Structure):
        _fields_ = [("size", ctypes.c_uint32), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    function = (
        ctypes.windll.crypt32.CryptUnprotectData
        if decode
        else ctypes.windll.crypt32.CryptProtectData
    )
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise OSError("Não foi possível proteger a chave neste usuário do Windows.")
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        ctypes.windll.kernel32.LocalFree(ctypes.cast(target.data, ctypes.c_void_p))


def protect_token(token):
    return (
        "dpapi:" + base64.b64encode(_dpapi(token.encode())).decode()
        if os.name == "nt"
        else "local:" + token
    )


def unprotect_token(value):
    if value.startswith("dpapi:"):
        if os.name != "nt":
            raise ValueError("Importe novamente a conexão neste computador.")
        return _dpapi(base64.b64decode(value[6:], validate=True), decode=True).decode("utf-8")
    if value.startswith("local:") and os.name != "nt":
        return value[6:]
    raise ValueError("A chave local está inválida. Importe novamente a conexão.")


def save_connection(path: Path, connection: GatewayConnection):
    atomic_json(
        path,
        {
            "format": PROTOCOL,
            "enabled": connection.enabled,
            "url": connection.url,
            "protected_token": protect_token(connection.token) if connection.token else "",
        },
    )
    if os.name != "nt":
        path.chmod(0o600)


def load_connection(path: Path) -> GatewayConnection:
    try:
        try:
            info = path.stat()
        except FileNotFoundError:
            return GatewayConnection()
        if info.st_size > 8192:
            raise ValueError("Configuração excessiva.")
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("format") != PROTOCOL:
            raise ValueError("Formato inválido.")
        token = unprotect_token(data["protected_token"]) if data.get("protected_token") else ""
        return GatewayConnection(data["enabled"], data["url"], token)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise GatewayError(
            "A configuração de acesso ao Comex está inválida. Revise a conexão em Preferências."
        ) from exc


def export_connection(path: Path, connection: GatewayConnection):
    # Arquivo de pareamento: contém a chave e deve ser entregue apenas aos usuários da central.
    atomic_json(path, {"format": PROTOCOL, "url": connection.url, "token": connection.token})
    if os.name != "nt":
        path.chmod(0o600)


def import_connection(path: Path) -> GatewayConnection:
    if path.stat().st_size > 8192:
        raise ValueError("Arquivo de conexão inválido.")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if value.get("format") != PROTOCOL:
            raise ValueError("Formato inválido.")
        return GatewayConnection(True, value["url"], value["token"])
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise ValueError("Selecione um arquivo de conexão exportado pela central.") from exc


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise GatewayError(
            "A central tentou redirecionar a conexão. Confira o endereço configurado."
        )


def central_http(connection, method, path, body, *, check=lambda: None, timeout=10):
    data = json_bytes(body) if body is not None else None
    if data is not None and len(data) > MAX_REQUEST:
        raise GatewayError("A consulta excedeu o tamanho permitido pela central.")
    request = urllib.request.Request(
        connection.url.rstrip("/") + path,
        data=data,
        method=method,
        headers={
            "Authorization": "Bearer " + connection.token,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Liarte-Protocol": PROTOCOL,
        },
    )
    # A conexão empresarial é direta: não enviar a chave para proxies configurados no ambiente.
    opener = build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    check()
    try:
        response = opener.open(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        response = exc
    except (urllib.error.URLError, OSError, HTTPException) as exc:
        raise GatewayError(
            "Não foi possível acessar a Central de Consultas. Verifique se ela está iniciada e se o endereço está correto."
        ) from exc
    with response:
        if response.headers.get("X-Liarte-Protocol") != PROTOCOL:
            raise GatewayError("O endereço não corresponde a uma Central de Consultas compatível.")
        deadline = time.monotonic() + 90
        output = bytearray()
        reader = getattr(response, "read1", response.read)
        while True:
            check()
            if time.monotonic() > deadline:
                raise GatewayError("A central demorou a enviar a resposta completa.")
            try:
                block = reader(min(256 * 1024, MAX_RESPONSE + 1 - len(output)))
            except (OSError, HTTPException) as exc:
                raise GatewayError(
                    "A conexão com a Central de Consultas foi interrompida; a resposta não foi utilizada."
                ) from exc
            if not block:
                break
            output.extend(block)
            if len(output) > MAX_RESPONSE:
                raise GatewayError("A resposta da central excedeu o tamanho permitido.")
        length = response.headers.get("Content-Length")
        if length is not None:
            try:
                expected_length = int(length)
            except (TypeError, ValueError) as exc:
                raise GatewayError("A central retornou um tamanho de resposta inválido.") from exc
            if expected_length != len(output):
                raise GatewayError("A central retornou uma resposta incompleta.")
        try:
            payload = json.loads(output, parse_float=Decimal)
        except (UnicodeError, ValueError) as exc:
            raise GatewayError("A central retornou uma resposta inválida.") from exc
        if not isinstance(payload, dict):
            raise GatewayError("A central retornou uma resposta inválida.")
        return response.status, payload, response.headers


def request_shared(
    connection,
    method,
    path,
    body,
    *,
    revision,
    refresh,
    check,
    wait,
    notify,
    connection_resolver=None,
):
    from .comexstat_importacoes import ComexRateLimitError, ComexStatError

    submission = {
        "protocol": PROTOCOL,
        "method": method,
        "path": path,
        "body": body,
        "revision": revision,
        "refresh": bool(refresh),
        "request_id": uuid4().hex,
    }
    ticket = None
    shared_result = False
    failures = 0
    restarts = 0
    deadline = time.monotonic() + 3600
    while time.monotonic() < deadline:
        check()
        try:
            if connection is None:
                connection = connection_resolver()
            status, payload, headers = central_http(
                connection,
                "GET" if ticket else "POST",
                "/v1/jobs/" + ticket if ticket else "/v1/query",
                None if ticket else submission,
                check=check,
            )
            failures = 0
        except (GatewayError, OSError, HTTPException) as exc:
            failures += 1
            if failures >= 3:
                raise ComexStatError(str(exc)) from exc
            if connection_resolver is not None:
                connection, ticket = None, None
            notify(None, "Reconectando à Central de Consultas")
            wait(float(failures))
            continue
        if status == 200:
            if payload.get("success") is False or payload.get("error"):
                raise ComexStatError("Consulta recusada pela fonte através da central.")
            return payload, shared_result or headers.get("X-Liarte-Cache") == "HIT"
        if status != 202:
            if status == 429 and payload.get("code") == "COMEX_RATE_LIMIT":
                delay = payload.get("retry_after")
                if (
                    type(delay) not in (int, float, Decimal)
                    or not math.isfinite(delay)
                    or delay < 0
                ):
                    raise ComexStatError("A central retornou uma pausa inválida.")
                raise ComexRateLimitError(
                    float(delay),
                    path,
                    str(payload.get("error", "")),
                    payload.get("observed_http_status"),
                )
            if connection_resolver is not None and payload.get("code") == "CENTRAL_STOPPED":
                connection, ticket = None, None
                restarts += 1
                if restarts < 3:
                    wait(float(restarts))
                    continue
            raise ComexStatError(
                str(payload.get("error") or "A Central de Consultas não concluiu a solicitação.")[
                    :500
                ]
            )
        candidate = payload.get("ticket")
        if not isinstance(candidate, str) or not re.fullmatch("[0-9a-f]{32}", candidate):
            raise ComexStatError("A central retornou um identificador de consulta inválido.")
        ticket = candidate
        shared_result = shared_result or payload.get("shared") is True
        delay = payload.get("poll_after", 1.0)
        if (
            isinstance(delay, bool)
            or not isinstance(delay, (int, float, Decimal))
            or not math.isfinite(delay)
        ):
            raise ComexStatError("A central retornou um intervalo de consulta inválido.")
        notify(None, str(payload.get("message") or "Aguardando a fila compartilhada")[:200])
        wait(float(max(0.2, min(3.0, delay))))
    raise ComexStatError(
        "A consulta permaneceu na central por mais de uma hora. Tente novamente após a pausa indicada pela fonte."
    )
