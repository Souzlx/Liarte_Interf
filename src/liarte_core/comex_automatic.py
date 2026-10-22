"""Fila local automática, restrita ao perfil do usuário e à interface de loopback.

Uma instância hospeda o broker; as demais reutilizam seu endereço protegido.
A eleição é serializada em disco local. A janela hospedeira encerra seus recursos
normalmente; outro cliente pode assumir quando ela sair, sem acessar a API fora
da fila. Nenhum arquivo de pareamento ou serviço Windows é necessário.
"""

from __future__ import annotations

import ctypes
import json
import logging
import os
import secrets
from pathlib import Path
from threading import Event, RLock, Thread
from urllib.parse import urlsplit

from liarte_engine.comex_access import AccessError, RequestCoordinator
from liarte_engine.comex_gateway_client import (
    GatewayConnection,
    GatewayError,
    PROTOCOL,
    central_http,
    load_connection,
    request_shared,
    save_connection,
)
from liarte_engine.liarte_dados import atomic_json

from .comex_central import CentralBroker, CentralServer
from .comex_managed import read_managed

LOGGER = logging.getLogger("liarte.desktop")


def process_alive(pid):
    """PID é só proteção contra criar outra fila enquanto o dono ainda responde."""
    if type(pid) is not int or pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if os.name == "nt":
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = (ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32)
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.GetExitCodeProcess.argtypes = (ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32))
        kernel.GetExitCodeProcess.restype = ctypes.c_int
        kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return ctypes.get_last_error() == 5  # Acesso negado não prova que o dono saiu.
        try:
            code = ctypes.c_uint32()
            return not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


class AutomaticAccess:
    def __init__(self, directory: Path, *, broker_factory=CentralBroker):
        self.directory = Path(directory)
        self.registry = self.directory / "acesso-automatico" / "conexao-local.json"
        self.access_path = self.directory / "acesso_comex.sqlite3"
        self.broker_factory = broker_factory
        self.lock = RLock()
        self.closed = Event()
        self.server = None
        self.connection = None
        self._warmup = None

    def gateway(self, configured):
        if not configured.enabled:
            return self
        # Só o dono local de uma configuração anteriormente salva pode retomá-la.
        # Um cliente de outro PC conserva a conexão remota, sem acesso direto à API.
        managed = read_managed(self.directory)
        return self if managed is not None and managed.matches(configured) else configured

    def start_managed(self):
        """Sem janela extra e sem acesso à fonte; uma máquina nova continua privada."""
        try:
            managed = read_managed(self.directory)
        except (GatewayError, OSError):
            LOGGER.exception("Não foi possível conferir a configuração local da central.")
            return
        if managed is None or self._warmup is not None:
            return

        def start():
            try:
                self.resolve(check=lambda: None, wait=self.closed.wait)
            except (GatewayError, OSError, ValueError):
                if not self.closed.is_set():
                    LOGGER.exception("Não foi possível retomar a central local automaticamente.")

        self._warmup = Thread(target=start, name="liarte-acesso-integrado", daemon=True)
        self._warmup.start()

    def _registered(self, managed=None):
        try:
            connection = load_connection(self.registry)
            if not connection.enabled:
                return None, 0
            parts = urlsplit(connection.url)
            owned = managed is not None and connection == managed.local_connection
            if not owned and (
                parts.scheme != "http" or parts.hostname != "127.0.0.1" or parts.path
            ):
                raise GatewayError("O registro automático contém um endereço que não é local.")
            data = json.loads(self.registry.read_text(encoding="utf-8"))
            return connection, data.get("pid", 0)
        except FileNotFoundError:
            return None, 0

    def resolve(self, *, check, wait):
        try:
            return self._resolve(check=check, wait=wait)
        except (AccessError, OSError) as exc:
            raise GatewayError(
                "Não foi possível preparar o acesso automático local. Consulte o diagnóstico."
            ) from exc

    def _resolve(self, *, check, wait):
        def inspect():
            if self.closed.is_set():
                raise GatewayError("O acesso local está sendo encerrado.")
            check()

        inspect()
        with self.lock:
            election = RequestCoordinator(
                self.directory / "acesso-automatico" / "inicializacao.sqlite3"
            )
            with election.acquire(0, 35, check=inspect, wait=wait):
                inspect()
                managed = read_managed(self.directory)
                if managed is not None:
                    candidate = managed.local_connection
                    try:
                        status, payload, _ = central_http(
                            candidate, "GET", "/v1/health", None, check=inspect, timeout=1.5
                        )
                        if (
                            status == 200
                            and payload.get("protocol") == PROTOCOL
                            and not payload.get("stopping")
                        ):
                            return candidate
                    except (GatewayError, OSError, ValueError):
                        pass
                connection, pid = self._registered(managed)
                if connection is not None:
                    try:
                        status, payload, _ = central_http(
                            connection,
                            "GET",
                            "/v1/health",
                            None,
                            check=inspect,
                            timeout=1.5,
                        )
                        if (
                            status == 200
                            and payload.get("protocol") == PROTOCOL
                            and not payload.get("stopping")
                            and (managed is None or connection == managed.local_connection)
                        ):
                            return connection
                    except (GatewayError, OSError, ValueError):
                        pass
                    own_stopped = connection == self.connection and (
                        self.server is None or not self.server.thread.is_alive()
                    )
                    if process_alive(pid) and not own_stopped:
                        raise GatewayError(
                            "A fila local está ocupada ou sendo encerrada. Aguarde alguns instantes."
                        )
                inspect()
                broker = self.broker_factory(
                    managed.directory
                    if managed
                    else self.directory / "acesso-automatico" / "dados",
                    access_path=self.access_path,
                    **({"interval": managed.interval} if managed else {}),
                )
                server = None
                try:
                    token = managed.connection.token if managed else secrets.token_urlsafe(32)
                    server = CentralServer(
                        broker,
                        token,
                        host=managed.host if managed else "127.0.0.1",
                        port=managed.port if managed else 0,
                    )
                    server.start()
                    connection = (
                        managed.local_connection
                        if managed
                        else GatewayConnection(True, f"http://127.0.0.1:{server.port}", token)
                    )
                    save_connection(self.registry, connection)
                    data = json.loads(self.registry.read_text(encoding="utf-8"))
                    data.update(pid=os.getpid(), managed=managed is not None)
                    atomic_json(self.registry, data)
                    inspect()
                    self.server, self.connection = server, connection
                    return connection
                except Exception:
                    if server is not None:
                        server.close()
                    else:
                        broker.close()
                    raise

    def request_json(self, method, path, body, *, revision, refresh, check, wait, notify):
        return request_shared(
            None,
            method,
            path,
            body,
            revision=revision,
            refresh=refresh,
            check=check,
            wait=wait,
            notify=notify,
            connection_resolver=lambda: self.resolve(check=check, wait=wait),
        )

    def close(self):
        self.closed.set()
        with self.lock:
            if self.server is not None:
                self.server.close()
                self.server = None
                try:
                    registered, _ = self._registered(read_managed(self.directory))
                    if registered == self.connection:
                        self.registry.unlink(missing_ok=True)
                except (GatewayError, OSError, ValueError):
                    pass
