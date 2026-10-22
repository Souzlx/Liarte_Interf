"""Política explícita dos módulos QML necessários à prova técnica."""

from __future__ import annotations

from pathlib import PurePosixPath

ALLOWED_QUICK = {"Controls", "Templates", "Window", "Layouts", "Dialogs"}
ALLOWED_QML = {"Models", "WorkerScript"}


def allowed_destination(destination: str) -> bool:
    parts = PurePosixPath(destination.replace("\\", "/")).parts
    if "qml" not in parts:
        return False
    relative = parts[parts.index("qml") + 1 :]
    if not relative:
        return False
    if relative[0] == "QtQuick":
        if len(relative) >= 3 and relative[1] == "Controls":
            return relative[2] in {"Basic", "impl"}
        return len(relative) == 1 or relative[1] in ALLOWED_QUICK
    if relative[0] == "QtQml":
        return len(relative) == 1 or relative[1] in ALLOWED_QML
    return False
