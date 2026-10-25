"""Navegação central: sem consultas, autenticação fictícia ou recarga dos módulos."""

from __future__ import annotations

from PySide6.QtCore import QObject, Property, Signal, Slot

from liarte_core.modules import ModuleRegistry
from .preferences import ApplicationPreferences
from .identity import APP_TITLE

MOUNTED_MODULES = frozenset({"imports", "inventory"})


class PlatformController(QObject):
    navigationChanged = Signal()
    startupChanged = Signal()

    def __init__(
        self,
        registry: ModuleRegistry,
        preferences: ApplicationPreferences,
        *,
        initial_module: str | None = None,
        parent=None,
        development=False,
    ):
        super().__init__(parent)
        if any(
            module.available and module.key not in MOUNTED_MODULES for module in registry.modules
        ):
            raise ValueError("Módulo disponível sem página registrada na composição do aplicativo")
        self.registry = registry
        self._development = development
        self._app_title = APP_TITLE + " [Desenvolvimento]" if development else APP_TITLE
        self.preferences = preferences
        self._active = "home"
        stored = preferences.text("platform/startupPage", "home")
        self._startup = stored if self._valid_page(stored) or stored == "last" else "home"
        initial = initial_module if initial_module is not None else self._startup
        if initial == "last":
            initial = preferences.text("platform/lastPage", "home")
        if self._valid_page(initial):
            self._active = initial
        if initial_module is None and preferences.text("platform/lastPage", "home") != self._active:
            preferences.remember_page("platform/lastPage", self._active)

    def _valid_page(self, key: str) -> bool:
        return key == "home" or self.registry.can_open(key)

    @Property(bool, constant=True)
    def development(self):
        return self._development

    @Property(str, notify=navigationChanged)
    def activeModule(self):
        return self._active

    @Property(str, notify=navigationChanged)
    def activeTitle(self):
        return "Início" if self._active == "home" else self.registry.get(self._active).title

    @Property(str, notify=navigationChanged)
    def windowTitle(self):
        return self._app_title if self._active == "home" else self._app_title + " " + self.activeTitle

    @Property("QVariantList", constant=True)
    def modules(self):
        return [
            {
                "key": m.key,
                "title": m.title,
                "description": m.description,
                "icon": m.icon,
                "available": m.available,
            }
            for m in self.registry.modules
        ]

    @Property(str, notify=startupChanged)
    def startupPage(self):
        return self._startup

    @Property("QVariantList", constant=True)
    def startupOptions(self):
        return (
            [{"value": "home", "label": "Início"}]
            + [{"value": m.key, "label": m.title} for m in self.registry.modules if m.available]
            + [{"value": "last", "label": "Última tela utilizada"}]
        )

    @Slot(str, result=bool)
    def openModule(self, key: str) -> bool:
        if not self._valid_page(key):
            return False
        if key != self._active:
            self._active = key
            self.preferences.remember_page("platform/lastPage", key)
            self.navigationChanged.emit()
        return True

    @Slot(str)
    def setStartupPage(self, key: str):
        if (key != "last" and not self._valid_page(key)) or key == self._startup:
            return
        self._startup = key
        if key == "last":
            self.preferences.remember_page("platform/lastPage", self._active)
        self.preferences.remember_page("platform/startupPage", key)
        self.startupChanged.emit()
