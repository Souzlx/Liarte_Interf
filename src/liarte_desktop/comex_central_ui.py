"""Gerenciador nativo da central; aberto por Preferências, sem console ou comandos."""

from __future__ import annotations

import argparse
import ipaddress
import json
import logging
import secrets
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from threading import Thread

from PySide6.QtCore import QObject, QStandardPaths, QTimer, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtNetwork import QNetworkInterface
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from liarte_core.comex_central import CentralBroker, CentralServer
from liarte_engine.comex_gateway_client import (
    GatewayConnection,
    export_connection,
    load_connection,
    save_connection,
)
from liarte_engine.liarte_dados import atomic_json

ASSETS = Path(__file__).resolve().parent / "assets"


def local_address():
    for entry in QNetworkInterface.allAddresses():
        try:
            address = ipaddress.ip_address(entry.toString())
            if (
                address.version == 4
                and address.is_private
                and not address.is_loopback
                and not address.is_link_local
            ):
                return str(address)
        except ValueError:
            pass
    return "127.0.0.1"


class StopSignal(QObject):
    finished = Signal()


class CentralWindow(QMainWindow):
    def __init__(self, directory):
        super().__init__()
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.config = self.directory / "central.json"
        self.server = None
        self.closing = self.stopping = False
        self.signal = StopSignal(self)
        self.signal.finished.connect(self._stopped)
        self.setWindowTitle("Liarte · Central de Consultas")
        self.setWindowIcon(QIcon(str(ASSETS / "liarte.ico")))
        self.resize(660, 680)
        self.setMinimumSize(500, 550)
        root = QWidget()
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setWidget(root)
        self.setCentralWidget(area)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(26, 24, 26, 24)
        layout.setSpacing(16)
        heading = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(QPixmap(str(ASSETS / "liarte-logo-transparente.png")).scaledToWidth(115))
        heading.addWidget(logo)
        heading.addStretch()
        self.status_label = QLabel("Parada")
        self.status_label.setMinimumWidth(180)
        self.status_label.setWordWrap(True)
        self.status_label.setObjectName("status")
        heading.addWidget(self.status_label)
        layout.addLayout(heading)
        title = QLabel("Central de Consultas")
        title.setObjectName("heading")
        layout.addWidget(title)
        description = QLabel(
            "Uma central para toda a equipe. Mantenha esta janela aberta no servidor ou computador que atenderá aos demais."
        )
        description.setWordWrap(True)
        description.setObjectName("muted")
        layout.addWidget(description)
        form = QFormLayout()
        form.setVerticalSpacing(12)
        self.host = QLineEdit(local_address())
        self.host.setObjectName("centralHost")
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        self.port.setValue(8767)
        self.interval = QSpinBox()
        self.interval.setRange(65, 300)
        self.interval.setValue(65)
        self.interval.setSuffix(" s")
        self.address = QLineEdit(f"http://{self.host.text()}:8767")
        self.address.setObjectName("centralPublishedAddress")
        self.key = QLineEdit(secrets.token_urlsafe(32))
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setObjectName("centralSecret")
        form.addRow("IP de escuta", self.host)
        form.addRow("Porta", self.port)
        form.addRow("Intervalo mínimo da API", self.interval)
        form.addRow("Endereço para a equipe", self.address)
        form.addRow("Chave de acesso", self.key)
        layout.addLayout(form)
        self._read_settings()
        self._default_address = f"http://{self.host.text()}:{self.port.value()}"
        self.host.textChanged.connect(self._suggest_address)
        self.port.valueChanged.connect(self._suggest_address)
        self.error = QLabel()
        self.error.setObjectName("error")
        self.error.setWordWrap(True)
        self.error.hide()
        layout.addWidget(self.error)
        self.progress = QLabel("Aguardando início.")
        self.progress.setObjectName("muted")
        self.progress.setWordWrap(True)
        layout.addWidget(self.progress)
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(divider)
        self.stats = QLabel("Fila: 0     Concluídas: 0     Reaproveitadas: 0")
        self.stats.setWordWrap(True)
        layout.addWidget(self.stats)
        layout.addStretch()
        row = QHBoxLayout()
        self.toggle = QPushButton("Iniciar central")
        self.toggle.setObjectName("primary")
        self.toggle.clicked.connect(self._toggle)
        self.export = QPushButton("Exportar conexão")
        self.export.setEnabled(False)
        self.export.clicked.connect(self._export)
        row.addWidget(self.toggle)
        row.addWidget(self.export)
        layout.addLayout(row)
        hint = QLabel(
            "Use o arquivo exportado em Preferências → Acesso ao Comex Stat nos demais computadores."
        )
        hint.setWordWrap(True)
        hint.setObjectName("muted")
        layout.addWidget(hint)
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #F5F7FA; color: #153451; font-family: 'Segoe UI'; font-size: 13px; }
            QLabel#heading { font-size: 24px; font-weight: 600; }
            QLabel#muted { color: #60758A; font-size: 12px; }
            QLabel#status { color: #087E8B; background: #E4F2F3; padding: 6px 12px; border-radius: 8px; }
            QLabel#error { color: #A63042; }
            QLineEdit, QSpinBox { background: white; border: 1px solid #D5DFEA; border-radius: 6px; padding: 9px; }
            QLineEdit:focus, QSpinBox:focus { border-color: #008BA0; }
            QPushButton { background: white; border: 1px solid #D5DFEA; border-radius: 6px; padding: 12px; }
            QPushButton:hover { background: #EAF1F6; }
            QPushButton#primary { background: #103F70; color: white; border-color: #103F70; font-weight: 600; }
            QPushButton:disabled { color: #8B9BA9; }
        """)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._update_status)
        self.timer.start()

    def _read_settings(self):
        if not self.config.exists():
            return
        try:
            connection = load_connection(self.config)
            value = json.loads(self.config.read_text(encoding="utf-8"))
            self.host.setText(value.get("host", self.host.text()))
            self.port.setValue(value.get("port", 8767))
            self.interval.setValue(value.get("interval", 15))
            self.address.setText(connection.url)
            self.key.setText(connection.token)
        except (ValueError, OSError, TypeError, RuntimeError):
            logging.getLogger("liarte.desktop").warning(
                "Configuração inválida da central; informe novamente os dados."
            )

    def _connection(self):
        return GatewayConnection(
            True, self.address.text().strip().rstrip("/"), self.key.text().strip()
        )

    def _suggest_address(self):
        host = self.host.text().strip()
        suggested = f"http://{local_address() if host == '0.0.0.0' else host}:{self.port.value()}"
        if self.address.text() == self._default_address:
            self.address.setText(suggested)
        self._default_address = suggested

    def _toggle(self):
        self._stop() if self.server is not None else self._start()

    def _start(self):
        broker = None
        server = None
        try:
            host = ipaddress.ip_address(self.host.text().strip())
            if host.version != 4 or not (
                host.is_private or host.is_loopback or host.is_unspecified
            ):
                raise ValueError("Utilize um IP da rede interna ou 127.0.0.1.")
            connection = self._connection()
            broker = CentralBroker(
                self.directory / "dados",
                interval=self.interval.value(),
                access_path=self.directory.parent / "dados" / "acesso_comex.sqlite3",
            )
            server = CentralServer(broker, connection.token, host=str(host), port=self.port.value())
            save_connection(self.config, connection)
            value = json.loads(self.config.read_text(encoding="utf-8"))
            value.update(host=str(host), port=self.port.value(), interval=self.interval.value())
            atomic_json(self.config, value)
            server.start()
            self.server = server
            for field in (self.host, self.port, self.interval, self.address, self.key):
                field.setEnabled(False)
            self.error.hide()
            self.toggle.setText("Parar central")
            self.export.setEnabled(True)
            self._update_status()
        except (ValueError, OSError, RuntimeError) as exc:
            if server is not None:
                server.close()
            elif broker is not None:
                broker.close()
            self.error.setText("Não foi possível iniciar a central. " + str(exc)[:240])
            self.error.show()

    def _stop(self):
        if self.server is None or self.stopping:
            return
        self.stopping = True
        self.export.setEnabled(False)
        self.toggle.setEnabled(False)
        self.status_label.setText("Encerrando…")
        server = self.server

        def stop():
            try:
                server.close()
            except Exception:
                logging.getLogger("liarte.desktop").exception("Falha ao encerrar a central")
            finally:
                self.signal.finished.emit()

        Thread(target=stop, name="liarte-central-encerrar", daemon=True).start()

    def _stopped(self):
        self.server, self.stopping = None, False
        for field in (self.host, self.port, self.interval, self.address, self.key):
            field.setEnabled(True)
        self.toggle.setEnabled(True)
        self.toggle.setText("Iniciar central")
        self.status_label.setText("Parada")
        self.progress.setText("Aguardando início.")
        if self.closing:
            self.close()

    def _update_status(self):
        if self.server is None or self.stopping:
            return
        if not self.server.thread.is_alive():
            self.error.setText(
                "O atendimento da central foi interrompido. Consulte o diagnóstico e inicie novamente."
            )
            self.error.show()
            self._stop()
            return
        try:
            state = self.server.broker.status()
            pause = state["pause_seconds"]
            self.status_label.setText(f"Pausa da fonte · {pause} s" if pause else "Em execução")
            self.stats.setText(
                f"Fila: {state['queued']}     Concluídas: {state['completed']}     Reaproveitadas: {state['cache_hits'] + state['joined']}"
            )
            with self.server.broker.lock:
                messages = [
                    j.message for j in self.server.broker.inflight.values() if j.state == "running"
                ]
            self.progress.setText(
                messages[0] if messages else "Pronta para receber consultas da equipe."
            )
        except Exception:
            self.error.setText("Não foi possível ler o estado da central. Consulte o diagnóstico.")
            self.error.show()

    def _export(self):
        try:
            connection = self._connection()
            path, _ = QFileDialog.getSaveFileName(
                self,
                "Exportar conexão",
                "LIARTE_COMEX.liarte-conexao",
                "Conexão LIARTE (*.liarte-conexao)",
            )
            if path:
                target = Path(path)
                if target.suffix != ".liarte-conexao":
                    target = target.with_suffix(".liarte-conexao")
                export_connection(target, connection)
                self.error.hide()
        except (ValueError, OSError) as exc:
            self.error.setText(str(exc))
            self.error.show()

    def closeEvent(self, event):
        if self.server is not None:
            self.closing = True
            event.ignore()
            self._stop()
        else:
            event.accept()


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--central-comex", action="store_true")
    parser.add_argument("--central-smoke", type=Path)
    args = parser.parse_args(argv)
    from .windows_identity import set_process_identity
    from .installation_guard import hold_installation_mutex

    set_process_identity()
    hold_installation_mutex()
    app = QApplication(sys.argv[:1])
    app.setOrganizationName("LIARTE")
    app.setApplicationName("LIARTE Desktop")
    app.setWindowIcon(QIcon(str(ASSETS / "liarte.ico")))
    directory = (
        Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))
        / "central-comex"
    )
    if args.central_smoke:
        directory = args.central_smoke.parent / "central-teste"
    directory.mkdir(parents=True, exist_ok=True)
    log = RotatingFileHandler(
        directory / "central.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    log.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    for name in ("liarte.desktop", "liarte-comex-intelligence"):
        logging.getLogger(name).addHandler(log)
        logging.getLogger(name).setLevel(logging.INFO)
    window = CentralWindow(directory)
    window.show()
    if args.central_smoke:

        def check():
            from liarte_engine.comex_gateway_client import central_http

            window.host.setText("127.0.0.1")
            # Find a free local port; the normal UI keeps the company-selected port.
            import socket

            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                port = probe.getsockname()[1]
            window.port.setValue(port)
            window.address.setText(f"http://127.0.0.1:{port}")
            window._start()
            status = 0
            if window.server is not None:
                status, _, _ = central_http(window._connection(), "GET", "/v1/health", None)
            assert window.grab().save(str(args.central_smoke.with_suffix(".png")))
            atomic_json(
                args.central_smoke,
                {"status": "ok" if status == 200 else "failed", "api_requests": 0},
            )
            window.close()

        QTimer.singleShot(150, check)
    return app.exec()
