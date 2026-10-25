"""Configuração nativa do ponto comum de acesso, sem alterar filtros ou documentos."""

from pathlib import Path
import sys
from threading import Event, Thread

from PySide6.QtCore import QObject, Property, QProcess, QUrl, Signal, Slot

from liarte_engine.comex_gateway_client import (
    GatewayConnection,
    GatewayError,
    PROTOCOL,
    central_http,
    import_connection,
    load_connection,
    save_connection,
)


class ComexConnectionController(QObject):
    changed = Signal()
    tested = Signal(bool, str)

    def __init__(self, provider, controller, parent=None, *, profile=None):
        super().__init__(parent)
        self.provider, self.controller = provider, controller
        self._profile = profile
        directory = getattr(provider, "directory", None)
        self.path = (
            Path(directory) / "conexao_comex.json"
            if directory is not None and not getattr(provider, "direct_api", False)
            else None
        )
        self.connection = GatewayConnection()
        self.message = ""
        self.error = False
        self.testing = False
        self._test_cancel = Event()
        stop_event = self._test_cancel
        self.destroyed.connect(lambda *_: stop_event.set())
        if self.path is not None:
            try:
                self.connection = load_connection(self.path)
            except GatewayError as exc:
                self.message, self.error = str(exc), True
        self.tested.connect(self._tested)

    @Property("QVariantMap", notify=changed)
    def state(self):
        return {
            "available": self.path is not None,
            "enabled": self.connection.enabled,
            "url": self.connection.url,
            "token": self.connection.token,
            "message": self.message,
            "error": self.error,
            "testing": self.testing,
        }

    @Slot()
    def prepare(self):
        # A verificação de disponibilidade pode ser refeita depois de configurar a conexão.
        # Uma geração de relatório solicitada pelo usuário continua intacta.
        if not self.controller.state["busy"]:
            self.controller._metadata_cancel.set()
        self.message = ""
        self.error = False
        self.changed.emit()

    def _idle(self):
        state = self.controller.state
        return not state["busy"] and not state["metadataBusy"] and not self.testing

    @Slot(str, str, bool, result=bool)
    def save(self, url, token, enabled):
        if self.path is None or not self._idle():
            self.message, self.error = (
                "Aguarde a consulta em andamento antes de alterar a conexão.",
                True,
            )
            self.changed.emit()
            return False
        try:
            connection = GatewayConnection(enabled, url.strip().rstrip("/"), token.strip())
            save_connection(self.path, connection)
            self.connection = connection
            self.provider.connection_changed()
            self.message, self.error = "Conexão salva.", False
        except (ValueError, GatewayError, OSError) as exc:
            self.message, self.error = str(exc), True
            self.changed.emit()
            return False
        self.changed.emit()
        return True

    @Slot(QUrl, result=bool)
    def importFile(self, url):
        if not url.isLocalFile():
            return False
        try:
            connection = import_connection(Path(url.toLocalFile()))
            return self.save(connection.url, connection.token, True)
        except (ValueError, OSError) as exc:
            self.message, self.error = str(exc), True
            self.changed.emit()
            return False

    @Slot(str, str)
    def test(self, url, token):
        if self.testing or self._test_cancel.is_set():
            return
        try:
            connection = GatewayConnection(True, url.strip().rstrip("/"), token.strip())
        except ValueError as exc:
            self.message, self.error = str(exc), True
            self.changed.emit()
            return
        self.testing = True
        self.message = "Verificando conexão com a central…"
        self.error = False
        self.changed.emit()

        def action():
            try:
                status, payload, _ = central_http(connection, "GET", "/v1/health", None)
                if status != 200 or payload.get("protocol") != PROTOCOL:
                    raise GatewayError(payload.get("error") or "Central incompatível.")
                if not self._test_cancel.is_set():
                    self.tested.emit(True, "Conexão com a central confirmada.")
            except (ValueError, GatewayError, OSError) as exc:
                if not self._test_cancel.is_set():
                    self.tested.emit(False, str(exc))

        Thread(target=action, name="liarte-teste-central", daemon=True).start()

    @Slot(bool, str)
    def _tested(self, success, message):
        self.testing = False
        self.message, self.error = message, not success
        self.changed.emit()

    @Slot()
    def shutdown(self):
        self._test_cancel.set()
        close = getattr(self.provider, "close", None)
        if close is not None:
            close()

    @Slot()
    def openCentral(self):
        if getattr(self.provider, "direct_api", False):
            return
        executable = Path(sys.executable)
        arguments = ["--central-comex"]
        if self._profile is not None and self._profile.development:
            arguments.extend(["--profile-dir", str(self._profile.root)])
        if not getattr(sys, "frozen", False):
            arguments.insert(0, str(Path(__file__).resolve().parents[2] / "iniciar.py"))
            if sys.platform == "win32" and executable.with_name("pythonw.exe").is_file():
                executable = executable.with_name("pythonw.exe")
        ok, _ = QProcess.startDetached(str(executable), arguments)
        if not ok:
            self.message, self.error = "Não foi possível abrir a Central de Consultas.", True
            self.changed.emit()
