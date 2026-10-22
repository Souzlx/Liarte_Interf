"""Atalhos por usuário, com Known Folders (inclusive Área de Trabalho no OneDrive)."""

from __future__ import annotations
import base64
import ctypes
import json
import logging
from pathlib import Path
import subprocess
import sys
from uuid import UUID

from .identity import APP_TITLE, APP_USER_MODEL_ID, SHORTCUT_SCHEMA
from .windows_identity import identify_shortcuts

LOGGER = logging.getLogger("liarte.desktop")
FOLDERS = {
    "desktop": "B4BFCC3A-DB2C-424C-B029-7FE99A87C641",
    "programs": "A77F5D77-2E2B-44C3-A6A2-ABA601054A51",
}


def known_folder(name):
    if sys.platform != "win32":
        raise OSError("Recurso exclusivo do Windows.")
    identifier = (ctypes.c_ubyte * 16).from_buffer_copy(UUID(FOLDERS[name]).bytes_le)
    out = ctypes.c_void_p()
    shell = ctypes.WinDLL("shell32", winmode=0x800)
    ole = ctypes.WinDLL("ole32", winmode=0x800)
    function = shell.SHGetKnownFolderPath
    function.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    function.restype = ctypes.c_long
    ole.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    ole.CoTaskMemFree.restype = None
    result = function(ctypes.byref(identifier), 0, None, ctypes.byref(out))
    if result != 0:
        raise OSError(f"Pasta conhecida do Windows indisponível: {name} ({result}).")
    try:
        return Path(ctypes.wstring_at(out))
    finally:
        ole.CoTaskMemFree(out)


def ps_literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def shortcut_script(executable, paths, old_target=""):
    target = ps_literal(executable)
    lines = [
        "$ErrorActionPreference='Stop'",
        "$shell=New-Object -ComObject WScript.Shell",
        f"$target={target}",
        f"$old={ps_literal(old_target)}",
    ]
    for path in paths:
        lines += [
            f"$path={ps_literal(path)}",
            "[IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($path)) | Out-Null",
            "$link=$shell.CreateShortcut($path)",
            "if ((Test-Path -LiteralPath $path) -and $link.TargetPath -and $link.TargetPath -ne $target -and $link.TargetPath -ne $old) { throw 'Atalho existente pertence a outro destino.' }",
            "$link.TargetPath=$target",
            "$link.Arguments=''",
            "$link.WorkingDirectory=[IO.Path]::GetDirectoryName($target)",
            "$link.IconLocation=$target+',0'",
            f"$link.Description={ps_literal(APP_TITLE)}",
            "$link.Save()",
        ]
    return "\n".join(lines)


def ensure_shortcuts(executable: Path, directory: Path, *, force=False):
    if sys.platform != "win32":
        return False
    marker = Path(directory) / "atalhos.json"
    try:
        paths = (
            known_folder("desktop") / "LIARTE Desktop.lnk",
            known_folder("programs") / "LIARTE Desktop/Análise de importações.lnk",
        )
        executable = Path(executable).resolve()
        if not executable.is_file():
            raise OSError("Executável não encontrado para criar o atalho.")
        old = {}
        try:
            if marker.stat().st_size < 16 * 1024:
                old = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        if not isinstance(old, dict):
            old = {}
        fingerprint = str(executable)
        if (
            not force
            and old.get("schema") == SHORTCUT_SCHEMA
            and old.get("app_id") == APP_USER_MODEL_ID
            and old.get("target") == fingerprint
            and all(p.is_file() for p in paths)
        ):
            return True
        script = shortcut_script(executable, paths, old.get("target", ""))
        encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
        powershell = (
            Path(__import__("os").environ.get("SystemRoot", r"C:\Windows"))
            / "System32/WindowsPowerShell/v1.0/powershell.exe"
        )
        result = subprocess.run(
            [str(powershell), "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
            capture_output=True,
            timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode:
            raise OSError("O Windows não permitiu salvar os atalhos.")
        if not all(path.is_file() for path in paths):
            raise OSError("O Windows não confirmou a existência dos dois atalhos.")
        identify_shortcuts(paths)
        marker.parent.mkdir(parents=True, exist_ok=True)
        from liarte_engine.liarte_dados import atomic_json

        atomic_json(
            marker,
            {
                "schema": SHORTCUT_SCHEMA,
                "app_id": APP_USER_MODEL_ID,
                "target": fingerprint,
                "links": [str(p) for p in paths],
            },
        )
        return True
    except (OSError, ValueError, subprocess.SubprocessError):
        LOGGER.warning(
            "Não foi possível conferir/recriar os atalhos. O aplicativo continua disponível.",
            exc_info=True,
        )
        return False
