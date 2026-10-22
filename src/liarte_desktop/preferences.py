"""Preferências locais compartilhadas, com as chaves históricas preservadas."""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Property, QSettings, Signal, Slot

LOGGER = logging.getLogger("liarte.desktop")
BOOL_DEFAULTS = {"dark": False, "compact": False, "reducedMotion": False, "monthlySheets": True}


class ApplicationPreferences(QObject):
    changed = Signal()
    valueChanged = Signal(str, bool)
    noticeChanged = Signal()

    def __init__(self, settings: QSettings | None = None, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._notice = ""
        self._values = {}
        for key, default in BOOL_DEFAULTS.items():
            try:
                self._values[key] = (
                    bool(settings.value(key, default, type=bool))
                    if settings is not None
                    else default
                )
            except (TypeError, ValueError, OSError):
                LOGGER.warning("Preferência inválida ignorada: %s", key)
                self._values[key] = default
        self._session_text: dict[str, str] = {}

    @Property("QVariantMap", notify=changed)
    def state(self):
        return dict(self._values)

    @Property(str, notify=noticeChanged)
    def notice(self):
        return self._notice

    def value(self, key: str) -> bool:
        return self._values[key]

    def text(self, key: str, default: str) -> str:
        if key in self._session_text:
            return self._session_text[key]
        try:
            value = self._settings.value(key, default) if self._settings is not None else default
            return value if isinstance(value, str) else default
        except (TypeError, ValueError, OSError):
            LOGGER.warning("Preferência inválida ignorada: %s", key)
            return default

    def _save(self, key: str, value: bool | str):
        notice = ""
        if self._settings is not None:
            try:
                self._settings.setValue(key, value)
                self._settings.sync()
                if self._settings.status() != QSettings.Status.NoError:
                    notice = "Ajuste aplicado nesta sessão; não foi possível salvar a preferência."
            except (TypeError, ValueError, OSError):
                LOGGER.warning("Não foi possível salvar a preferência %s", key, exc_info=True)
                notice = "Ajuste aplicado nesta sessão; não foi possível salvar a preferência."
        if notice != self._notice:
            self._notice = notice
            self.noticeChanged.emit()

    def remember_page(self, key: str, value: str):
        """Uso interno do navegador; sem gravação de chaves arbitrárias pelo QML."""
        if key not in {"platform/startupPage", "platform/lastPage"}:
            raise ValueError("Chave de navegação inválida")
        self._session_text[key] = value
        self._save(key, value)

    @Slot(str, bool)
    def setPreference(self, key: str, value: bool):
        if key not in BOOL_DEFAULTS or type(value) is not bool:
            return
        self._values[key] = value
        self._save(key, value)
        self.valueChanged.emit(key, value)
        self.changed.emit()
