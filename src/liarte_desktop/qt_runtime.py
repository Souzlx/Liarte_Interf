"""Busca de DLLs Qt no Windows, antes de importar suas extensões nativas.

Os diretórios são do PySide6/shiboken6 do próprio interpretador. Nenhuma DLL
é obtida de sites avulsos e nenhuma variável do sistema é modificada.
"""

from __future__ import annotations

import ctypes
import importlib.util
import os
from pathlib import Path
import sys

_DIRECTORIES: list[object] = []
_LIBRARIES: list[object] = []
_CONFIGURED = False


def package_directory(name: str) -> Path:
    specification = importlib.util.find_spec(name)
    if specification is None or specification.origin is None:
        raise RuntimeError(f"O pacote {name} não está instalado neste ambiente Python.")
    return Path(specification.origin).resolve().parent


def configure_windows_qt() -> None:
    """Registra diretórios e mantém seus handles durante toda a execução.

    A carga absoluta com DLL_LOAD_DIR + DEFAULT_DIRS resolve as dependências
    do estilo QML mesmo quando a busca usada pelo carregador Qt difere da
    busca de extensões Python. Não usa o diretório de trabalho como fallback.
    """
    global _CONFIGURED
    if sys.platform != "win32" or _CONFIGURED:
        return
    package = package_directory("PySide6")
    shiboken = package_directory("shiboken6")
    candidates = [package, shiboken]
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root and (Path(frozen_root) / "Qt6Core.dll").is_file():
        candidates.append(Path(frozen_root).resolve())
    dll_root = next((p for p in candidates if (p / "Qt6Core.dll").is_file()), None)
    if dll_root is None:
        raise RuntimeError("Qt6Core.dll não foi encontrada no pacote da aplicação.")
    qml = next((p for p in (package / "qml", package / "Qt/qml") if p.is_dir()), None)
    if qml is None:
        raise RuntimeError("Os componentes QML do Qt não foram encontrados.")
    required = [
        dll_root / "Qt6QuickControls2Basic.dll",
        dll_root / "Qt6QuickLayouts.dll",
        qml / "QtQuick/Controls/Basic/qtquickcontrols2basicstyleplugin.dll",
    ]
    for path in required:
        if not path.is_file():
            raise RuntimeError(f"Arquivo do Qt ausente: {path}. Repare o ambiente da prévia.")

    # Manter os objetos evita remover os diretórios antes da carga dos plugins.
    registered, libraries = [], []
    try:
        for directory in dict.fromkeys(candidates):
            registered.append(os.add_dll_directory(str(directory)))
        for path in required:
            try:
                libraries.append(ctypes.WinDLL(str(path), winmode=0x00001100))
            except OSError as exc:
                code = getattr(exc, "winerror", None)
                raise RuntimeError(
                    f"O Windows não conseguiu carregar {path.name} "
                    f"(erro {code}): {exc}. O arquivo existe; uma dependência pode estar "
                    "ausente, incompatível ou bloqueada. Consulte o diagnóstico de inicialização."
                ) from exc
        # Somente o ambiente deste processo; impede mistura com outro Qt instalado.
        plugins = next(
            (p for p in (package / "plugins", package / "Qt/plugins") if p.is_dir()), None
        )
        if plugins is not None:
            os.environ["QT_PLUGIN_PATH"] = str(plugins)
        os.environ["QML_IMPORT_PATH"] = str(qml)
        os.environ["QML2_IMPORT_PATH"] = str(qml)
    except Exception:
        for handle in reversed(registered):
            handle.close()
        raise
    _DIRECTORIES.extend(registered)
    _LIBRARIES.extend(libraries)
    _CONFIGURED = True
