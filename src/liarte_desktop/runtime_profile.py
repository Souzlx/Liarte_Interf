"""Explicit development storage; the default keeps the installed application's paths."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from PySide6.QtCore import QCoreApplication, QSettings, QStandardPaths, Qt

DEVELOPMENT_APP_NAME = "LIARTE Desktop Desenvolvimento"
DEVELOPMENT_APP_ID = "LIARTE.Desktop.Development"


@dataclass(frozen=True)
class RuntimeProfile:
    root: Path
    development: bool = False

    def __post_init__(self):
        object.__setattr__(self, "root", Path(self.root).expanduser().resolve())

    @property
    def data_dir(self):
        return self.root / "dados"

    @property
    def inventory_cache(self):
        return self.root / "estoque" / "base.liarte"

    @property
    def log_dir(self):
        return self.root / "logs"

    @property
    def settings_file(self):
        return self.root / "settings.ini"

    @property
    def reports_dir(self):
        return self.root / "relatorios"

    @property
    def central_dir(self):
        return self.root / "central-comex"

    @property
    def qml_cache_dir(self):
        return self.root / "cache" / "qmlcache"

    def prepare(self):
        """Reject linked storage outside the profile before creating anything."""
        if self.development:
            pending, visited = [self.root], set()
            while pending:
                directory = pending.pop()
                resolved = directory.resolve()
                if not resolved.is_relative_to(self.root):
                    raise ValueError("O perfil de desenvolvimento contém um link para fora da sua pasta.")
                if resolved in visited or not directory.is_dir():
                    continue
                visited.add(resolved)
                for child in directory.iterdir():
                    if not child.resolve().is_relative_to(self.root):
                        raise ValueError("O perfil de desenvolvimento contém um link para fora da sua pasta.")
                    if child.is_dir():
                        pending.append(child)
        self.root.mkdir(parents=True, exist_ok=True)


def resolve_profile(profile_dir: Path | None, *, default_root: Path | None = None):
    installed = Path(default_root) if default_root is not None else Path(
        QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
    )
    installed = installed.expanduser().resolve()
    if profile_dir is None:
        return RuntimeProfile(installed)
    candidate = Path(profile_dir).expanduser().resolve()
    if candidate.is_relative_to(installed) or installed.is_relative_to(candidate):
        raise ValueError("Escolha um perfil de desenvolvimento separado da pasta de dados em uso.")
    return RuntimeProfile(candidate, development=True)


def open_settings(profile: RuntimeProfile, *, no_settings=False):
    if no_settings:
        return None
    if not profile.development:
        return QSettings()
    profile.prepare()
    settings = QSettings(str(profile.settings_file), QSettings.Format.IniFormat)
    settings.setFallbacksEnabled(False)
    return settings


def configure_development_cache(profile_dir: Path):
    """Set before constructing Qt/its QML engine; do not alter the Windows profile."""
    root = Path(profile_dir).expanduser().resolve()
    os.environ["QML_DISK_CACHE_PATH"] = str(root / "cache" / "qmlcache")
    # Explicit RHI filenames override Qt's automatic-cache disable flag.
    for key in ("QSG_RHI_PIPELINE_CACHE_LOAD", "QSG_RHI_PIPELINE_CACHE_SAVE"):
        os.environ.pop(key, None)
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_DisableShaderDiskCache, True)
