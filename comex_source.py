"""Fonte oficial com duas vias independentes e sem repetição agressiva.

Arquivos MDIC conferidos são a primeira opção. A API documentada é uma
alternativa com até três tentativas espaçadas, sujeita à fila persistente.
Uma falha de download nunca autoriza publicar linhas parciais nem ignorar 429.
"""

from __future__ import annotations

import logging
from pathlib import Path

from liarte_engine import comexstat_importacoes as engine
from .comex_open_data import OpenDataError, OpenDataRepository

LOGGER = logging.getLogger("liarte.desktop")


class OfficialSourceClient:
    def __init__(self, *, repository, source_revision=None, **kwargs):
        self.repository = repository
        self.revision = source_revision
        self.refresh = kwargs.get("refresh_cache", False)
        self.check = kwargs.get("cancel_check") or (lambda: None)
        self.notify = kwargs.get("progress_callback") or (lambda *args: None)
        kwargs["max_attempts"] = min(3, kwargs.get("max_attempts", 3))
        self.api = engine.ComexStatClient(source_revision=source_revision, **kwargs)

    def close(self):
        self.api.close()

    def request_json(self, method, path, body=None):
        self.check()
        metadata = path in ("/general/dates/updated", "/cities/dates/updated")
        try:
            if metadata and method == "GET" and body is None:
                return {
                    "success": True,
                    "data": self.repository.availability(
                        self.check,
                        self.notify,
                        force=self.refresh,
                        municipal=path.startswith("/cities"),
                    ),
                }
            if method != "POST" or path not in ("/general?language=pt", "/cities?language=pt"):
                raise engine.ComexStatError("Consulta fora do contrato oficial de importações.")
            return self.repository.query(
                body,
                path.startswith("/cities"),
                self.check,
                self.notify,
                revision=self.revision,
                refresh=self.refresh,
            )
        except OpenDataError as file_error:
            self.check()
            LOGGER.warning("Arquivos MDIC indisponíveis: %s", str(file_error))
            coordinator = self.api._coordinator
            pause = coordinator.status()["pause_seconds"] if coordinator is not None else 0
            if pause:
                raise engine.ComexRateLimitError(
                    pause,
                    path,
                    "Os arquivos oficiais não puderam ser conferidos e a API continua na pausa solicitada. "
                    "Os dados anteriores foram preservados.",
                    None,
                ) from file_error
            self.notify(None, "Consultando a API oficial alternativa")
            try:
                return self.api.request_json(method, path, body)
            except engine.ComexRateLimitError:
                # Preserve the exact wire body/status for diagnosis. The file
                # failure is logged separately and is not an API response.
                raise
            except engine.ComexStatError as api_error:
                raise engine.ComexStatError(
                    "Nenhuma das duas fontes oficiais concluiu a consulta: arquivos MDIC indisponíveis "
                    "ou não conferidos; API: " + str(api_error)[:250]
                ) from api_error


def source_factory(directory: Path):
    # One repository per broker, shared by jobs for different users and periods.
    # No network request is made by constructing it.
    repository = OpenDataRepository(Path(directory) / "dados_abertos")

    def create(**kwargs):
        return OfficialSourceClient(repository=repository, **kwargs)

    return create
