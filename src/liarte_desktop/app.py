"""Composição do cliente modular Qt com Importações e Estoque."""

# ruff: noqa: E402  # Windows DLL paths must be configured before importing Qt.
from __future__ import annotations

import argparse
import logging
import json
import os
import sys
import time
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .qt_runtime import configure_windows_qt

configure_windows_qt()

from PySide6.QtCore import (
    QCoreApplication,
    QEvent,
    QEventLoop,
    QSettings,
    QMetaObject,
    QObject,
    QStandardPaths,
    QTimer,
    QUrl,
    qVersion,
)
from PySide6.QtGui import QFont, QGuiApplication, QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle

from liarte_core.demo import DemoProvider
from liarte_core.modules import default_registry
from . import __version__
from .identity import APP_TITLE
from .installation_guard import hold_installation_mutex
from .windows_identity import set_process_identity
from .controller import DesktopController
from .inventory import InventoryController
from .branding import BrandProvider
from .platform import PlatformController
from .preferences import ApplicationPreferences
from .comex_connection import ComexConnectionController

PACKAGE = Path(__file__).resolve().parent


def _finish_inventory_shutdown(inventory: InventoryController) -> None:
    """Keep Qt and its controllers alive until a cancelled worker has stopped."""
    if inventory.shutdown():
        return
    loop = QEventLoop()
    inventory.shutdownFinished.connect(loop.quit)
    try:
        # Completion can race with connecting the signal. Recheck after the
        # connection, without a second blocking wait on the GUI thread.
        if not inventory.shutdown(wait_ms=0):
            loop.exec()
    finally:
        inventory.shutdownFinished.disconnect(loop.quit)


@dataclass
class ApplicationBundle:
    engine: QQmlApplicationEngine
    controller: DesktopController
    messages: list[str]
    platform: PlatformController
    preferences: ApplicationPreferences
    services: QObject
    inventory: InventoryController


def create_bundle(
    *, size=None, settings=None, provider=None, initial_module=None
) -> ApplicationBundle:
    """Abre a tela configurada; sem preferência, a plataforma começa em Início."""
    if provider is None:
        if size is not None:
            provider = DemoProvider(size)
        else:
            from liarte_core.comex import ComexProvider

            provider = ComexProvider(
                Path(
                    QStandardPaths.writableLocation(
                        QStandardPaths.StandardLocation.AppLocalDataLocation
                    )
                )
                / "dados"
            )
    services = QObject()
    preferences = ApplicationPreferences(settings, services)
    controller = DesktopController(
        provider, settings, services, preferences=preferences
    )
    comex_access = ComexConnectionController(provider, controller, services)
    services.comex_access = comex_access
    inventory = InventoryController(
        settings,
        services,
        cache_path=(
            Path(
                QStandardPaths.writableLocation(
                    QStandardPaths.StandardLocation.AppLocalDataLocation
                )
            )
            / "estoque"
            / "base.liarte"
        )
        if settings is not None
        else None,
        bundled_path=(
            Path(__file__).resolve().parent.parent / "liarte_core/data/estoque.liarte"
        )
        if not isinstance(provider, DemoProvider)
        else None,
    )
    platform = PlatformController(
        default_registry(), preferences, initial_module=initial_module, parent=services
    )
    engine = QQmlApplicationEngine()
    engine.addImageProvider(
        "liarte", BrandProvider(PACKAGE / "assets" / "liarte-logo-transparente.png")
    )
    messages = []
    engine.warnings.connect(lambda warnings: messages.extend(str(w) for w in warnings))
    engine.rootContext().setContextProperty("controller", controller)
    engine.rootContext().setContextProperty("recordModel", controller.table)
    engine.rootContext().setContextProperty("appVersion", __version__)
    engine.rootContext().setContextProperty("platform", platform)
    engine.rootContext().setContextProperty("preferences", preferences)
    engine.rootContext().setContextProperty("comexAccess", comex_access)
    engine.rootContext().setContextProperty("inventory", inventory)
    engine.rootContext().setContextProperty("stockModel", inventory.table)
    engine.rootContext().setContextProperty(
        "stockDefaultFolder", QUrl.fromLocalFile(str(PACKAGE.parents[1]))
    )
    engine.load(QUrl.fromLocalFile(str(PACKAGE / "qml" / "Main.qml")))
    if not engine.rootObjects():
        raise RuntimeError(
            "A interface Qt não pôde ser carregada. " + "; ".join(messages[-5:])
        )
    window = engine.rootObjects()[0]
    window.setIcon(QIcon(str(PACKAGE / "assets" / "liarte.ico")))
    window.show()
    return ApplicationBundle(
        engine, controller, messages, platform, preferences, services, inventory
    )


def install_availability_refresh(bundle: ApplicationBundle):
    """Confirma a fonte uma vez ao entrar em Importações, sem consultar por Início/Estoque."""
    if getattr(bundle.controller._provider, "direct_api", False):
        # Abrir o módulo não precisa de acesso à rede. A ação Consultar vai
        # diretamente aos dados; Verificar fonte permanece disponível à parte.
        return
    timer = QTimer(bundle.services)
    timer.setSingleShot(True)
    timer.setInterval(200)
    attempted = False

    def refresh():
        nonlocal attempted
        if attempted or bundle.platform.activeModule != "imports":
            return
        attempted = True
        state = bundle.controller.state
        if not state["loaded"] and not state["busy"] and not state["metadataBusy"]:
            bundle.controller.refreshAvailability()

    def schedule():
        if not attempted and bundle.platform.activeModule == "imports":
            timer.start()
        else:
            timer.stop()

    timer.timeout.connect(refresh)
    bundle.platform.navigationChanged.connect(schedule)
    bundle.services.availability_timer = timer
    schedule()


def configure_log() -> Path:
    directory = (
        Path(
            QStandardPaths.writableLocation(
                QStandardPaths.StandardLocation.AppLocalDataLocation
            )
        )
        / "logs"
    )
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "desktop.log"
    handler = RotatingFileHandler(
        path, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    logger = logging.getLogger("liarte.desktop")
    logger.setLevel(logging.INFO)
    for previous in tuple(logger.handlers):
        if getattr(previous, "_liarte_file_handler", False):
            logger.removeHandler(previous)
            previous.close()
    handler._liarte_file_handler = True
    logger.addHandler(handler)
    engine_logger = logging.getLogger("liarte-comex-intelligence")
    for previous in tuple(engine_logger.handlers):
        if getattr(previous, "_liarte_file_handler", False):
            engine_logger.removeHandler(previous)
    engine_logger.addHandler(handler)
    return path


def _smoke_inventory_backups(directory: Path) -> bool:
    """Exercise packaged stock backup/restore using a fresh synthetic directory."""
    from dataclasses import replace
    from datetime import date
    import hashlib

    from liarte_core.inventory import SCALE, Balance, InventoryData, Product
    from liarte_core.inventory_backup import backup_previous, list_backups, load_backup
    from liarte_core.inventory_io import read_snapshot, write_snapshot

    # A caller must supply a new scratch directory. Never reuse a profile path
    # or silently overwrite files left by another operation.
    directory.mkdir(parents=True, exist_ok=False)
    cache, staged = directory / "base.liarte", directory / "nova.liarte"
    original = InventoryData(
        date(2026, 1, 31),
        "Autoteste sintético A",
        "a" * 64,
        (Product("AUTOTESTE1", "Produto sintético", "Teste", "MP", "UN"),),
        (Balance("AUTOTESTE1", "01", "01", "UN", SCALE, 100),),
        (),
        (),
    )
    replacement = replace(
        original,
        as_of=date(2026, 2, 28),
        source_name="Autoteste sintético B",
        source_hash="b" * 64,
        balances=(Balance("AUTOTESTE1", "01", "01", "UN", 2 * SCALE, 250),),
    )
    write_snapshot(original, cache)
    original_sha = hashlib.sha256(cache.read_bytes()).hexdigest()
    write_snapshot(replacement, staged)
    previous = backup_previous(cache, staged)
    if previous is None or previous.sha256 != original_sha:
        return False
    os.replace(staged, cache)
    if read_snapshot(cache) != replacement:
        return False
    replacement_sha = hashlib.sha256(cache.read_bytes()).hexdigest()

    restored = load_backup(cache, previous.id)
    if restored != original:
        return False
    write_snapshot(restored, staged)
    current = backup_previous(cache, staged)
    if current is None or current.sha256 != replacement_sha:
        return False
    os.replace(staged, cache)
    copies = list_backups(cache)
    return (
        read_snapshot(cache) == original
        and {copy.id for copy in copies} == {previous.id, current.id}
        and load_backup(cache, current.id) == replacement
    )


def smoke_check(app: QGuiApplication, bundle: ApplicationBundle, output: Path):
    """Autoteste do mesmo aplicativo após congelamento, antes de publicá-lo."""
    deadline = time.monotonic() + 25
    timer = QTimer(app)
    timer.setInterval(60)
    themes_checked = []
    dialog_phase = []

    def inspect_result():
        state = bundle.controller.state
        if state["busy"] and time.monotonic() < deadline:
            return
        timer.stop()
        window = bundle.engine.rootObjects()[0]
        ok = (
            state["loaded"]
            and not state["busy"]
            and not state["error"]
            and bundle.controller.table.rowCount() > 0
            and not bundle.messages
            and not window.grabWindow().isNull()
            and window.title() == bundle.platform.windowTitle
            and not window.icon().pixmap(32, 32).isNull()
        )
        if ok and not themes_checked:
            themes_checked.append("light")
            bundle.controller.setPreference("dark", True)
            timer.start()
            return
        if ok and len(themes_checked) < 2:
            themes_checked.append("dark")
        dialog = window.findChild(QObject, "exportDialog")
        if ok and not dialog_phase:
            QMetaObject.invokeMethod(dialog, "open")
            dialog_phase.append("opened")
            timer.start()
            return
        if ok and dialog_phase == ["opened"]:
            ok = bool(dialog.property("visible"))
            QMetaObject.invokeMethod(dialog, "close")
            dialog_phase.append("closed")
            if ok:
                timer.start()
                return
        document_checks = {}
        transport_checks = {}
        if ok:
            try:
                from liarte_core.package_checks import verify_document_resources

                document_checks = verify_document_resources()
                ok = document_checks.get("pdf") == "ok"
                from tempfile import TemporaryDirectory

                document_checks["inventory_backups"] = "failed"
                with TemporaryDirectory(prefix="liarte-autoteste-estoque-") as scratch:
                    if _smoke_inventory_backups(Path(scratch) / "base-sintetica"):
                        document_checks["inventory_backups"] = "ok"
                ok = ok and document_checks["inventory_backups"] == "ok"
                from liarte_engine.secure_http import verify_transport

                transport_checks = verify_transport()
            except Exception:
                logging.getLogger("liarte.desktop").exception(
                    "Falha no autoteste dos documentos"
                )
                ok = False
        document = {
            "status": "ok" if ok else "failed",
            "version": __version__,
            "qt": qVersion(),
            "window_title": window.title(),
            "window_icon_checked": not window.icon().pixmap(32, 32).isNull(),
            "frozen": bool(getattr(sys, "frozen", False)),
            "platform": sys.platform,
            "synthetic": True,
            "document_resources": document_checks,
            "https_transport": transport_checks,
            "save_dialog_checked": dialog_phase == ["opened", "closed"],
            "api_network_test": False,
            "rows_in_page": bundle.controller.table.rowCount(),
            "qml_warnings": bundle.messages,
            "error": state["error"],
            "themes_checked": themes_checked,
        }
        try:
            output.parent.mkdir(parents=True, exist_ok=True)
            temporary = output.with_suffix(output.suffix + ".tmp")
            temporary.write_text(
                json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            os.replace(temporary, output)
        except OSError:
            logging.getLogger("liarte.desktop").exception("Falha ao gravar o autoteste")
            ok = False
        bundle.controller.shutdown()
        app.exit(0 if ok else 1)

    timer.timeout.connect(inspect_result)
    bundle.controller.queryPeriod("2026-04", "2026-09")
    timer.start()


def main(argv=None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if "--central-comex" in arguments:
        from .comex_central_ui import main as central_main

        return central_main(arguments)
    parser = argparse.ArgumentParser(
        description="LIARTE: Importações Comex Stat e análise de Estoque em uma plataforma nativa."
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Somente demonstração sintética; não consulta a rede.",
    )
    parser.add_argument(
        "--data-dir", type=Path, help="Diretório local de cache e auditoria."
    )
    parser.add_argument(
        "--no-settings", action="store_true", help="Não grava preferências locais."
    )
    parser.add_argument(
        "--smoke-test",
        type=Path,
        help="Autoteste local para validar o executável compilado.",
    )
    parser.add_argument(
        "--startup-ready",
        type=Path,
        help="Confirmação interna para o assistente de abertura.",
    )
    args = parser.parse_args(argv)
    set_process_identity()
    QQuickStyle.setStyle("Basic")
    app = QGuiApplication(sys.argv[:1])
    app.setOrganizationName("LIARTE")
    app.setApplicationName("LIARTE Desktop")  # Preserve preferences, cache and reports.
    app.setApplicationDisplayName(APP_TITLE)
    app.setApplicationVersion(__version__)
    app.setWindowIcon(QIcon(str(PACKAGE / "assets" / "liarte.ico")))
    app.setFont(QFont("Segoe UI" if sys.platform == "win32" else "DejaVu Sans", 10))
    try:
        configure_log()
        if not args.smoke_test:
            hold_installation_mutex()
        settings = None if args.no_settings or args.smoke_test else QSettings()
        provider = None
        if not args.demo and not args.smoke_test:
            from liarte_core.comex import ComexProvider

            directory = (
                args.data_dir
                or Path(
                    QStandardPaths.writableLocation(
                        QStandardPaths.StandardLocation.AppLocalDataLocation
                    )
                )
                / "dados"
            )
            provider = ComexProvider(directory)
        if settings is not None and not settings.contains("dark"):
            previous = QSettings("LIARTE", "LIARTE Desktop F1")
            for key in ("dark", "compact", "reducedMotion"):
                if previous.contains(key):
                    settings.setValue(key, previous.value(key, False, type=bool))
        bundle = create_bundle(
            size=2000 if args.smoke_test else 100_000,
            settings=settings,
            provider=provider,
            initial_module="imports" if args.smoke_test else None,
        )
    except Exception:
        logging.getLogger("liarte.desktop").exception("Falha ao iniciar a interface")
        raise
    if (
        sys.platform == "win32"
        and getattr(sys, "frozen", False)
        and not args.smoke_test
    ):
        from threading import Thread
        from .windows_shell import ensure_shortcuts

        directory = Path(
            QStandardPaths.writableLocation(
                QStandardPaths.StandardLocation.AppLocalDataLocation
            )
        )
        Thread(
            target=ensure_shortcuts,
            args=(Path(sys.executable), directory),
            daemon=True,
            name="liarte-atalhos",
        ).start()
    app.aboutToQuit.connect(bundle.controller.shutdown)
    app.aboutToQuit.connect(bundle.inventory.shutdown)
    app.aboutToQuit.connect(bundle.services.comex_access.shutdown)
    window = bundle.engine.rootObjects()[0]
    screen = app.primaryScreen()
    if screen is not None:
        available = screen.availableGeometry()
        window.setMinimumWidth(min(500, available.width()))
        window.setMinimumHeight(min(400, available.height()))
        window.resize(
            min(1380, round(available.width() * 0.96)),
            min(900, round(available.height() * 0.92)),
        )
        window.setPosition(
            available.x() + (available.width() - window.width()) // 2,
            available.y() + (available.height() - window.height()) // 2,
        )
    if not args.demo and not args.smoke_test:
        install_availability_refresh(bundle)
    if args.smoke_test:
        smoke_check(app, bundle, args.smoke_test)
    if args.startup_ready:

        def ready():
            try:
                status = (
                    "ready" if window.isVisible() and not bundle.messages else "failed"
                )
                temp = args.startup_ready.with_suffix(".tmp")
                temp.write_text(
                    json.dumps({"status": status, "version": __version__}),
                    encoding="utf-8",
                )
                os.replace(temp, args.startup_ready)
                if status != "ready":
                    app.exit(1)
            except OSError:
                logging.getLogger("liarte.desktop").exception(
                    "Falha na confirmação de abertura"
                )
                app.exit(1)

        QTimer.singleShot(120, ready)
    try:
        return app.exec()
    finally:
        bundle.services.comex_access.shutdown()
        bundle.controller.shutdown()
        _finish_inventory_shutdown(bundle.inventory)
        # Libera primeiro os bindings QML, enquanto seus objetos Python ainda
        # existem. Evita referências nulas durante a finalização do processo.
        bundle.engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


if __name__ == "__main__":
    raise SystemExit(main())
