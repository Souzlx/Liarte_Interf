"""Tarefas Qt de disponibilidade e documentos, independentes da thread visual."""

from __future__ import annotations
import logging
from PySide6.QtCore import QObject, Signal, Slot
from liarte_core.query import Cancelled, checkpoint
from liarte_core.exports import export_document
from liarte_core.comex import ComexError

LOGGER = logging.getLogger("liarte.desktop")


class MetadataWorker(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, provider, cancel):
        super().__init__()
        self.provider, self.cancel = provider, cancel

    @Slot()
    def run(self):
        try:
            result = self.provider.availability(self.cancel, force=True)
            checkpoint(self.cancel)
            self.succeeded.emit(result)
        except Cancelled:
            pass
        except Exception as exc:
            LOGGER.exception("Falha na disponibilidade do Comex Stat")
            self.failed.emit(
                str(exc)
                if isinstance(exc, ComexError)
                else "Não foi possível verificar a disponibilidade. Tente novamente."
            )
        finally:
            self.finished.emit()


class ExportWorker(QObject):
    progress = Signal(int, str)
    succeeded = Signal(object)
    failed = Signal(str)
    cancelled = Signal()
    finished = Signal()

    def __init__(self, request, cancel, audit_directory):
        super().__init__()
        self.request, self.cancel, self.audit_directory = request, cancel, audit_directory

    @Slot()
    def run(self):
        try:
            self.succeeded.emit(
                export_document(self.request, self.cancel, self.progress.emit, self.audit_directory)
            )
        except Cancelled:
            self.cancelled.emit()
        except PermissionError:
            self.failed.emit(
                "Não foi possível gravar o arquivo. Feche-o no Excel/Power BI e confira a permissão da pasta."
            )
        except (ValueError, RuntimeError) as exc:
            LOGGER.exception("Falha na exportação")
            self.failed.emit(str(exc)[:500])
        except Exception:
            LOGGER.exception("Falha na exportação")
            self.failed.emit(
                "Não foi possível concluir o arquivo. Nenhum arquivo incompleto foi publicado. Consulte o diagnóstico."
            )
        finally:
            self.finished.emit()
