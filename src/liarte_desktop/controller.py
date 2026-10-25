"""Estado da apresentação e ciclo de vida de uma tarefa Qt cancelável."""

from __future__ import annotations

import logging
import time
from dataclasses import replace
from decimal import Decimal
from datetime import date
from pathlib import Path
from threading import Event

from PySide6.QtCore import (
    QObject,
    Property,
    QSettings,
    QThread,
    QTimer,
    Signal,
    Slot,
    QUrl,
    QStandardPaths,
)
from PySide6.QtGui import QGuiApplication, QDesktopServices

from liarte_core.demo import (
    COUNTRIES,
    STATES,
    PORTS,
    DEMO_PERIOD,
    Cancelled,
    ImportProvider,
    QueryResult,
    catalog,
)
from liarte_core.domain import (
    Period,
    Selection,
    compact_money,
    money,
    number,
    period_label,
    period_value,
    selected_values,
    search_key,
)
from liarte_core.comex import ComexError
from liarte_core.exports import ExportRequest
from .jobs import MetadataWorker, ExportWorker
from .analytics import empty_analysis, present as present_procurement
from .table_model import HEADERS, MUNICIPAL_HEADERS, ImportTableModel, cells, port_label
from .preferences import ApplicationPreferences

LOGGER = logging.getLogger("liarte.desktop")


class QueryWorker(QObject):
    progress = Signal(int, str)
    succeeded = Signal(object)
    failed = Signal(str)
    cancelled = Signal()
    finished = Signal()

    def __init__(self, provider: ImportProvider, selection: Selection, cancel: Event):
        super().__init__()
        self.provider, self.selection, self.cancel = provider, selection, cancel

    @Slot()
    def run(self):
        last_emission = -float("inf")
        last_stage = ""

        def report(percent: int, stage: str):
            # Atualizações de progresso não devem disputar a thread visual com
            # centenas de notificações durante a preparação de bases grandes.
            nonlocal last_emission, last_stage
            # A demonstração é CPU-bound em Python. Um ponto de cooperação curto
            # libera o interpretador para os slots da janela entre os lotes.
            if self.cancel.wait(0.001):
                raise Cancelled()
            now = time.monotonic()
            if percent == 100 or stage != last_stage or now - last_emission >= 0.05:
                self.progress.emit(percent, stage)
                last_emission, last_stage = now, stage

        try:
            result = self.provider.query(self.selection, self.cancel, report)
            if self.cancel.is_set():
                self.cancelled.emit()
            else:
                self.succeeded.emit(result)
        except Cancelled:
            self.cancelled.emit()
        except ComexError as exc:
            LOGGER.warning("Consulta oficial não concluída: %s", exc)
            self.failed.emit(str(exc))
        except Exception:
            LOGGER.exception("Falha na consulta")
            self.failed.emit(
                "Não foi possível concluir a consulta. Tente novamente ou consulte o diagnóstico local."
            )
        finally:
            self.finished.emit()


class DesktopController(QObject):
    changed = Signal()
    presentationChanged = Signal()
    analysisChanged = Signal()
    readyToClose = Signal()
    filtersChanged = Signal()
    periodsChanged = Signal()

    def __init__(
        self,
        provider: ImportProvider | None = None,
        settings: QSettings | None = None,
        parent=None,
        *,
        preferences: ApplicationPreferences | None = None,
        profile=None,
    ):
        super().__init__(parent)
        self.table = ImportTableModel(self)
        if provider is None:
            from liarte_core.comex import ComexProvider

            provider = ComexProvider(
                profile.data_dir if profile is not None else (
                    Path(
                        QStandardPaths.writableLocation(
                            QStandardPaths.StandardLocation.AppLocalDataLocation
                        )
                    ) / "dados"
                )
            )
        self._provider = provider
        self._profile = profile
        self._settings = settings
        self.preferences = (
            preferences
            if preferences is not None
            else ApplicationPreferences(settings, self)
        )
        self._is_demo = getattr(self._provider, "is_demo", False)
        today = date.today()
        candidate = period_value(today.year * 12 + today.month - 2)
        self._limits = DEMO_PERIOD if self._is_demo else Period("1997-01", candidate)
        self._metadata_thread = self._metadata_worker = None
        self._metadata_cancel = Event()
        self._export_thread = self._export_worker = None
        self._export_cancel = Event()
        self._last_export = ""
        self._options_revision = None
        self._selection = Selection(
            Period("2026-04", "2026-09"), sort_column=9, descending=True
        )
        if not self._is_demo:
            self._selection = replace(
                self._selection, period=Period(candidate[:4] + "-01", candidate)
            )
        self._result: QueryResult | None = None
        self._procurement_source = None
        self._procurement_view = empty_analysis()
        self._thread: QThread | None = None
        self._worker: QueryWorker | None = None
        self._cancel = Event()
        self._pending: Selection | None = None
        self._pending_source_query = False
        self._running_source_query = False
        self._closing = False
        self._started = 0.0

        def preference(key, default=False):
            return self.preferences.value(key)

        self._state = {
            "busy": False,
            "localBusy": False,
            "demo": self._is_demo,
            "metadataBusy": False,
            "metadataError": "",
            "sourcePauseSeconds": 0,
            "sourceStatus": "Dados demonstrativos" if self._is_demo else "Comex Stat",
            "sourceUpdated": "",
            "cacheStatus": "",
            "defaultStart": self._selection.period.start,
            "defaultEnd": self._selection.period.end,
            "kind": "general",
            "appliedKind": "general",
            "cityFilter": "",
            "headers": list(HEADERS),
            "monthlySheets": preference("monthlySheets", True),
            "exportBusy": False,
            "exportProgress": 0,
            "exportStage": "",
            "exportError": "",
            "exportMessage": "",
            "lastExport": "",
            "sourceNotice": "",
            "waiting": False,
            "closing": False,
            "loaded": False,
            "progress": 0,
            "stage": "Escolha um período para começar.",
            "error": "",
            "dark": preference("dark"),
            "reducedMotion": preference("reducedMotion"),
            "compact": preference("compact"),
            "settingsNotice": "",
            "page": 1,
            "pages": 1,
            "pageSize": 50,
            "tableCount": "0",
            "scopeCount": "0",
            "selection": -1,
            "selectedText": "Selecione uma linha para ver os detalhes.",
            "selectedTitle": "",
            "copyMessage": "",
            "periodLabel": "",
            "elapsed": "",
            "sortColumn": 9,
            "descending": True,
            "monthly": [],
            "countries": [],
            "procurement": empty_analysis(),
            "search": "",
            "ncmFilter": "",
            "ncmValues": [],
            "countryValues": [],
            "stateValues": [],
            "portValues": [],
            "cityValues": [],
            "countryFilter": "",
            "stateFilter": "",
            "portFilter": "",
            "filterCount": 0,
            "appliedStart": "",
            "appliedEnd": "",
            "tableRange": "0 registros",
            "metrics": self._empty_metrics(),
            "datasetSize": "100.000",
            "filterSummary": "Todos os produtos e origens",
        }
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(240)
        self._debounce.timeout.connect(self._run_selection)
        self.preferences.valueChanged.connect(self._preference_changed)
        self.preferences.noticeChanged.connect(self._preference_notice_changed)
        self._access_timer = QTimer(self)
        self._access_timer.setInterval(1000)
        self._access_timer.timeout.connect(self._sync_access_status)
        if not self._is_demo:
            self._access_timer.start()

    @Slot()
    def _sync_access_status(self):
        status = getattr(self._provider, "access_status", None)
        if status is not None:
            seconds = status().get("pause_seconds", 0)
            self._update(sourcePauseSeconds=max(0, int(seconds)))

    @Slot(str, bool)
    def _preference_changed(self, key: str, value: bool):
        self._update(**{key: value, "settingsNotice": self.preferences.notice})

    @Slot()
    def _preference_notice_changed(self):
        self._update(settingsNotice=self.preferences.notice)

    @staticmethod
    def _empty_metrics():
        return [
            {
                "label": "Valor CIF",
                "value": "—",
                "detail": "FOB + frete + seguro",
                "full": "Sem consulta",
            },
            {
                "label": "Peso líquido",
                "value": "—",
                "detail": "Quilogramas no período",
                "full": "Sem consulta",
            },
            {
                "label": "Preço médio",
                "value": "—",
                "detail": "US$/kg · média ponderada",
                "full": "Sem consulta",
            },
            {
                "label": "NCMs ativos",
                "value": "—",
                "detail": "Códigos com registros",
                "full": "Sem consulta",
            },
        ]

    @Property("QVariantMap", notify=changed)
    def state(self):
        return dict(self._state, canExport=self._can_export())

    @Property("QVariantMap", notify=presentationChanged)
    def presentation(self):
        return {
            k: v
            for k, v in self.state.items()
            if k not in ("metrics", "monthly", "countries", "procurement")
        }

    @Property("QVariantMap", notify=analysisChanged)
    def analysis(self):
        return {
            k: self._state[k]
            for k in ("metrics", "monthly", "countries", "procurement")
        }

    @Property("QVariantList", notify=periodsChanged)
    def periods(self):
        return [{"label": period_label(m), "value": m} for m in self._limits.months]

    @Property("QVariantList", notify=filtersChanged)
    def products(self):
        if not self._is_demo and self._selection.kind == "municipal":
            return [{"label": "Todos os SH4", "value": ""}] + [
                {"label": f"{code} · {label}", "value": code}
                for code, label in self._provider.options("municipal")["headings"]
            ]
        return [{"label": "Todos os produtos", "value": ""}] + [
            {"label": f"{v['name']} · {v['ncm']}", "value": v["ncm"]}
            for v in sorted(
                catalog(), key=lambda item: (search_key(item["name"]), item["ncm"])
            )
        ]

    @Property("QVariantList", notify=filtersChanged)
    def countries(self):
        values = (
            sorted(COUNTRIES)
            if self._is_demo
            else self._provider.options(self._selection.kind)["countries"]
        )
        return self._option_items(
            values, selected_values(self._selection, "country"), "Todos os países"
        )

    @Property("QVariantList", notify=filtersChanged)
    def states(self):
        values = (
            sorted(STATES)
            if self._is_demo
            else self._provider.options(self._selection.kind)["states"]
        )
        return self._option_items(
            values, selected_values(self._selection, "state"), "Todas as UFs"
        )

    @Property("QVariantList", notify=filtersChanged)
    def ports(self):
        values = (
            sorted(PORTS)
            if self._is_demo
            else self._provider.options(self._selection.kind)["ports"]
        )
        options = self._option_items(
            values, selected_values(self._selection, "port"), "Todos os portos"
        )
        return [dict(option, label=port_label(option["label"])) for option in options]

    @Property("QVariantList", notify=filtersChanged)
    def cities(self):
        values = [] if self._is_demo else self._provider.options("municipal")["cities"]
        return self._option_items(
            values, selected_values(self._selection, "city"), "Todos os municípios"
        )

    @staticmethod
    def _option_items(values, selected, caption):
        available = set(values)
        all_values = available | (
            {selected} if isinstance(selected, str) and selected else set(selected)
        )
        return [{"label": caption, "value": ""}] + [
            {
                "label": v + (" · sem registros" if v not in available else ""),
                "value": v,
            }
            for v in sorted(all_values, key=search_key)
        ]

    @Property(str, constant=True)
    def reportsFolder(self):
        isolated = self._profile is not None and self._profile.development
        folder = self._profile.reports_dir if isolated else (
            Path(
                QStandardPaths.writableLocation(
                    QStandardPaths.StandardLocation.DocumentsLocation
                )
            )
            / "LIARTE"
            / "Relatorios_Comex"
        )
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError:
            folder = self._profile.root if isolated else Path.home()
        return QUrl.fromLocalFile(str(folder)).toString()

    @Slot()
    def refreshAvailability(self):
        if (
            self._is_demo
            or self._metadata_thread is not None
            or self._thread is not None
            or self._closing
        ):
            return
        self._metadata_cancel = Event()
        self._update(metadataBusy=True, metadataError="")
        thread = QThread(self)
        worker = MetadataWorker(self._provider, self._metadata_cancel)
        worker.moveToThread(thread)
        self._metadata_thread, self._metadata_worker = thread, worker
        thread.started.connect(worker.run)
        worker.succeeded.connect(self._metadata_succeeded)
        worker.failed.connect(self._metadata_failed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._metadata_finished)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    @Slot(str)
    def _metadata_failed(self, message):
        if not self._closing and not self._metadata_cancel.is_set():
            self._update(
                metadataError=message, sourceStatus="Disponibilidade não confirmada"
            )

    @Slot()
    def cancelAvailability(self):
        self._metadata_cancel.set()

    @Slot(object)
    def _metadata_succeeded(self, availability):
        if self._closing or self._metadata_cancel.is_set():
            return
        self._limits = Period("1997-01", availability.latest)
        if not self._state["loaded"]:
            self._selection = replace(
                self._selection,
                period=Period(availability.latest[:4] + "-01", availability.latest),
            )
            self._update(
                defaultStart=self._selection.period.start,
                defaultEnd=self._selection.period.end,
            )
        self._update(
            sourceUpdated=availability.updated,
            sourceStatus="Dados até " + period_label(availability.latest),
            sourceNotice="Disponibilidade em cache; conexão não confirmada."
            if availability.cached
            else "",
        )
        self.periodsChanged.emit()

    @Slot()
    def _metadata_finished(self):
        self._metadata_thread = self._metadata_worker = None
        self._update(metadataBusy=False)
        self._try_close()

    @Slot(str)
    def setDataset(self, kind):
        if (
            kind not in ("general", "municipal")
            or self._is_demo
            or kind == self._selection.kind
        ):
            return
        self._selection = replace(
            self._selection,
            kind=kind,
            ncm_values=(),
            country_values=(),
            state_values=(),
            port_values=(),
            city_values=(),
            ncm="",
            country="",
            state="",
            port="",
            city="",
            search="",
            page=1,
            sort_column=6 if kind == "municipal" else 9,
            descending=True,
        )
        self._sync_filters()
        self.filtersChanged.emit()
        if self._state["loaded"]:
            self._queue(self._selection)
        else:
            metrics = self._empty_metrics()
            if kind == "municipal":
                metrics[0].update(
                    label="Valor FOB", detail="Valor FOB da base municipal"
                )
                metrics[3].update(label="SH4 ativos", detail="Posições com registros")
            self.table.replace((), kind)
            self._update(
                appliedKind=kind, headers=list(self.table.headers), metrics=metrics
            )

    @Slot(str, bool)
    def setExportOption(self, key, value):
        if key == "monthlySheets":
            if key == "monthlySheets":
                self.setPreference(key, value)
            else:
                self._update(**{key: value})

    @Slot(str, str)
    def setDraftPeriod(self, edge, value):
        if value in {item["value"] for item in self.periods}:
            if edge in ("start", "end"):
                self._update(
                    **{"defaultStart" if edge == "start" else "defaultEnd": value}
                )

    @Slot(int)
    def setPeriodPreset(self, months):
        """Preenche meses publicados, sem disparar consulta ou descartar dados."""
        if (
            months not in (3, 6, 12)
            or self._state["busy"]
            or self._state["metadataBusy"]
        ):
            return
        available = self._limits.months
        self._update(
            defaultStart=available[max(0, len(available) - months)],
            defaultEnd=available[-1],
        )

    @Slot(str, result=bool)
    def copyTrendData(self, key):
        series = self._state["procurement"]["series"].get(key)
        if series is None:
            return False
        header = f"Mês\t{series['label']} ({series['tableUnit']})"
        with_rolling = bool(series["rollingLabel"])
        if with_rolling:
            header += f"\t{series['rollingLabel']} ({series['tableUnit']})"
        lines = [header]
        lines.extend(
            f"{p['period']}\t{p['tableValue']}"
            + (f"\t{p['tableMoving']}" if with_rolling else "")
            for p in series["points"]
        )
        QGuiApplication.clipboard().setText("\n".join(lines))
        return True

    @Slot()
    def openDiagnostics(self):
        directory = self._profile.log_dir if self._profile is not None else (
            Path(
                QStandardPaths.writableLocation(
                    QStandardPaths.StandardLocation.AppLocalDataLocation
                )
            )
            / "logs"
        )
        directory.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory)))

    @Slot(str, QUrl)
    def exportTo(self, kind, url):
        if not self._can_export() or self._export_thread is not None:
            self._update(exportError="Conclua a consulta antes de exportar.")
            return
        if not url.isLocalFile():
            self._update(exportError="Escolha um arquivo local.")
            return
        snapshot = self._provider.snapshot
        if snapshot is None or snapshot.period != self._result.selection.period:
            self._update(
                exportError="O período carregado mudou. Consulte novamente antes de exportar."
            )
            return
        request = ExportRequest(
            kind,
            Path(url.toLocalFile()),
            snapshot,
            self._result.selection,
            self._state["monthlySheets"],
        )
        self._export_cancel = Event()
        self._update(
            exportBusy=True,
            exportProgress=0,
            exportError="",
            exportMessage="",
            exportStage="Preparando documento",
        )
        thread = QThread(self)
        worker = ExportWorker(
            request, self._export_cancel, self._provider.directory / "exportacoes"
        )
        worker.moveToThread(thread)
        self._export_thread, self._export_worker = thread, worker
        thread.started.connect(worker.run)
        worker.progress.connect(self._export_progress)
        worker.succeeded.connect(self._export_succeeded)
        worker.failed.connect(self._export_failed)
        worker.cancelled.connect(self._export_cancelled)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._export_finished)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    @Slot(int, str)
    def _export_progress(self, percent, message):
        self._update(exportProgress=percent, exportStage=message)

    @Slot(str)
    def _export_failed(self, message):
        self._update(exportError=message)

    @Slot()
    def _export_cancelled(self):
        self._update(
            exportStage="Exportação cancelada. Nenhum arquivo incompleto foi publicado."
        )

    @Slot(object)
    def _export_succeeded(self, result):
        self._last_export = result["path"]
        self._update(
            lastExport=result["name"],
            exportProgress=100,
            exportStage="Arquivo salvo",
            exportMessage="",
        )

    @Slot()
    def _export_finished(self):
        self._export_thread = self._export_worker = None
        self._update(exportBusy=False)
        self._try_close()

    @Slot()
    def cancelExport(self):
        self._export_cancel.set()
        self._update(exportStage="Cancelando a exportação…")

    @Slot(bool)
    def openExport(self, folder=False):
        if self._last_export:
            path = Path(self._last_export)
            QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(path.parent if folder else path))
            )

    def _try_close(self):
        if self._closing and all(
            t is None
            for t in (self._thread, self._metadata_thread, self._export_thread)
        ):
            self.readyToClose.emit()

    def _can_export(self):
        return bool(
            not self._is_demo
            and self._result is not None
            and not self._state["busy"]
            and not self._state["waiting"]
            and not self._closing
            and not self._state["error"]
            and self._selection
            == replace(self._result.selection, page=self._result.page)
        )

    def _update(self, **changes):
        if QThread.currentThread() != self.thread():
            raise RuntimeError("Estado da interface alterado fora da thread visual.")
        changed = {k: v for k, v in changes.items() if self._state.get(k) != v}
        if not changed:
            return
        self._state.update(changed)
        if any(
            k in ("metrics", "monthly", "countries", "procurement") for k in changed
        ):
            self.analysisChanged.emit()
        if any(
            k not in ("metrics", "monthly", "countries", "procurement") for k in changed
        ):
            self.presentationChanged.emit()
        self.changed.emit()

    def _sync_filters(self):
        s = self._selection
        self._update(
            ncmFilter=s.ncm,
            cityFilter=s.city,
            kind=s.kind,
            countryFilter=s.country,
            stateFilter=s.state,
            portFilter=s.port,
            search=s.search,
            filterCount=sum(
                bool(selected_values(s, name))
                for name in ("ncm", "country", "state", "port", "city")
            ),
            pageSize=s.page_size,
            **{
                name + "Values": list(selected_values(s, name))
                for name in ("ncm", "country", "state", "port", "city")
            },
        )

    @Slot(str, str)
    def queryPeriod(self, start: str, end: str):
        try:
            self._sync_access_status()
            if self._state["sourcePauseSeconds"]:
                raise ValueError(
                    "O Comex Stat solicitou uma pausa. Aguarde o prazo indicado."
                )
            period = Period(start, end)
            if self._state["metadataBusy"]:
                raise ValueError("Aguarde a confirmação da disponibilidade da fonte.")
            if period.start < self._limits.start or period.end > self._limits.end:
                raise ValueError("Selecione um intervalo disponível na fonte.")
        except ValueError as exc:
            self._update(error=str(exc))
            return
        if not self._is_demo:
            self._provider.revalidate_next()
        self._selection = replace(self._selection, period=period, page=1)
        self._update(defaultStart=start, defaultEnd=end)
        self._debounce.stop()
        self._queue(self._selection, source_query=True)

    @Slot(str, str)
    def setFilter(self, key: str, value: str):
        if key not in ("ncm", "country", "state", "port", "city", "search"):
            self._update(error="Filtro não reconhecido.")
            return
        if getattr(self._selection, key) == value and (
            key == "search" or not getattr(self._selection, key + "_values")
        ):
            return
        try:
            selection = replace(
                self._selection,
                **{
                    key: value,
                    **({key + "_values": ()} if key != "search" else {}),
                    "page": 1,
                },
            )
            if self._is_demo:
                if (
                    key in ("country", "state", "port")
                    and value
                    and value
                    not in {"country": COUNTRIES, "state": STATES, "port": PORTS}[key]
                ):
                    raise ValueError("Filtro indisponível na demonstração.")
            elif key in ("country", "state", "port", "city") and value:
                available = self._provider.options(selection.kind)[
                    {
                        "country": "countries",
                        "state": "states",
                        "port": "ports",
                        "city": "cities",
                    }[key]
                ]
                if value not in available:
                    raise ValueError("Filtro indisponível no período carregado.")
            if (
                key == "ncm"
                and value
                and value not in {v["value"] for v in self.products}
            ):
                raise ValueError("O código não pertence ao cadastro desta análise.")
        except (ValueError, TypeError) as exc:
            self._update(error=str(exc))
            return
        if selection == self._selection:
            return
        self._selection = selection
        self._sync_filters()
        if self._state["loaded"] or self._state["busy"]:
            self._update(waiting=True, error="")
            self._debounce.start()

    @Slot(str, "QVariantList")
    def setFilters(self, key, values):
        if key not in ("ncm", "country", "state", "port", "city"):
            return
        try:
            values = tuple(sorted(set(values)))
            if values == selected_values(self._selection, key):
                return
            if len(values) <= 1:
                self.setFilter(key, values[0] if values else "")
                return
            allowed = {
                item["value"]
                for item in {
                    "ncm": self.products,
                    "country": self.countries,
                    "state": self.states,
                    "port": self.ports,
                    "city": self.cities,
                }[key]
            }
            if not set(values) <= allowed:
                raise ValueError("A seleção contém opções indisponíveis.")
            selection = replace(
                self._selection, **{key: "", key + "_values": values, "page": 1}
            )
        except (ValueError, TypeError):
            self._update(error="Seleção inválida. Escolha até 200 opções disponíveis.")
            return
        if selection == self._selection:
            return
        self._selection = selection
        self._sync_filters()
        if self._state["loaded"] or self._state["busy"]:
            self._update(waiting=True, error="")
            self._debounce.start()

    @Slot()
    def clearFilters(self):
        self._selection = replace(
            self._selection,
            ncm="",
            country="",
            state="",
            port="",
            city="",
            search="",
            page=1,
            ncm_values=(),
            country_values=(),
            state_values=(),
            port_values=(),
            city_values=(),
        )
        self._sync_filters()
        self._update(error="")
        if self._state["loaded"] or self._state["busy"]:
            self._update(waiting=True)
            self._debounce.start()

    @Slot(int)
    def setPage(self, value: int):
        if not 1 <= value <= self._state["pages"] or not self._state["loaded"]:
            return
        if value == self._selection.page:
            return
        self._selection = replace(self._selection, page=value)
        self._queue(self._selection)

    @Slot(int)
    def setPageSize(self, size: int):
        if size == self._selection.page_size:
            return
        try:
            self._selection = replace(self._selection, page_size=size, page=1)
        except ValueError as exc:
            self._update(error=str(exc))
            return
        self._update(pageSize=size)
        if self._state["loaded"]:
            self._queue(self._selection)

    @Slot(int)
    def sortByColumn(self, column: int):
        if column not in range(12):
            return
        descending = (
            not self._selection.descending
            if column == self._selection.sort_column
            else column >= 6
        )
        self._selection = replace(
            self._selection, sort_column=column, descending=descending, page=1
        )
        if self._state["loaded"]:
            self._queue(self._selection)

    @Slot()
    def _run_selection(self):
        self._queue(self._selection)

    def _queue(self, selection: Selection, *, source_query=False):
        if self._closing:
            return
        self._debounce.stop()
        if self._thread is not None:
            self._pending = selection
            self._pending_source_query = (
                source_query or self._running_source_query or self._pending_source_query
            )
            self._cancel.set()
            if not self._state["localBusy"]:
                self._update(stage="Atualizando os filtros…")
            return
        self._cancel = Event()
        self._pending = None
        self._pending_source_query = False
        self._started = time.perf_counter()
        local = bool(
            not source_query
            and self._result is not None
            and selection.period == self._result.selection.period
        )
        if local:
            cached_query = getattr(self._provider, "cached_query", None)
            try:
                cached = cached_query(selection) if cached_query else None
            except Exception:
                # Cache is optional; fall back to the cancellable query path.
                LOGGER.exception("Não foi possível reutilizar a página local")
                cached = None
            if cached is not None:
                self._update(error="", copyMessage="")
                self._succeeded(cached)
                self._update(busy=False, localBusy=False)
                return
        self._running_source_query = not local
        self._update(
            busy=True,
            localBusy=local,
            waiting=False,
            progress=0,
            stage="Preparando a demonstração"
            if self._is_demo
            else "Preparando a consulta ao Comex Stat",
            error="",
            copyMessage="",
        )
        thread = QThread(self)
        worker = QueryWorker(self._provider, selection, self._cancel)
        worker.moveToThread(thread)
        self._thread, self._worker = thread, worker
        thread.started.connect(worker.run)
        worker.progress.connect(self._progress)
        worker.succeeded.connect(self._succeeded)
        worker.failed.connect(self._failed)
        worker.cancelled.connect(self._cancelled)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._finished)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    @Slot(int, str)
    def _progress(self, percent: int, message: str):
        if not self._cancel.is_set() and not self._state["localBusy"]:
            self._update(
                progress=max(self._state["progress"], min(100, percent)), stage=message
            )

    @Slot(object)
    def _succeeded(self, result: QueryResult):
        try:
            self._present_result(result)
        except Exception:
            LOGGER.exception("Falha ao apresentar um resultado")
            self._failed(
                "Não foi possível apresentar o resultado. Os dados anteriores foram preservados."
            )

    def _present_result(self, result: QueryResult):
        if (
            self._cancel.is_set()
            or self._pending is not None
            or self._closing
            or result.selection != self._selection
        ):
            return
        t = result.totals
        if self._procurement_source is not result.procurement:
            self._procurement_view = present_procurement(result.procurement)
            self._procurement_source = result.procurement
        procurement = self._procurement_view
        price = result.procurement.total.unit_price
        metrics = [
            {
                "label": "Valor " + t.basis,
                "value": compact_money(t.value_cents),
                "detail": f"{t.countries} países de origem",
                "full": money(t.value_cents),
            },
            {
                "label": "Peso líquido",
                "value": number(t.kg),
                "detail": "kg no período",
                "full": number(t.kg) + " kg",
            },
            {
                "label": "Média da seleção"
                if t.ncms > 1
                else "Média " + t.basis + "/kg",
                "value": "US$ " + number(price, 3) if price is not None else "—",
                "detail": t.basis + "/kg · ponderada pelo peso",
                "issue": "Há importações com valor e 0 kg na fonte. A média usa os totais publicados pelo Comex Stat."
                if result.procurement.total.unweighed_cents
                else "",
                "full": t.basis
                + " total ÷ kg total. Referência histórica, sujeita ao mix e às condições das operações.",
            },
            {
                "label": "SH4 ativos"
                if result.selection.kind == "municipal"
                else "NCMs ativos",
                "value": str(t.ncms),
                "detail": f"{number(t.records)} registros agregados",
                "full": "Posições SH4 distintas"
                if result.selection.kind == "municipal"
                else "NCMs distintos, sem duplicar produtos relacionados",
            },
        ]
        active = []
        for name, label in (
            ("ncm", "códigos"),
            ("country", "países"),
            ("state", "UFs"),
            ("port", "URFs"),
            ("city", "municípios"),
        ):
            values = selected_values(result.selection, name)
            if values:
                active.append(
                    values[0] if len(values) == 1 else f"{len(values)} {label}"
                )
        changes = dict(
            loaded=True,
            waiting=False,
            progress=100,
            stage="Demonstração pronta"
            if self._is_demo
            else "Dados oficiais carregados",
            appliedKind=result.selection.kind,
            headers=list(
                MUNICIPAL_HEADERS if result.selection.kind == "municipal" else HEADERS
            ),
            metrics=metrics,
            procurement=procurement,
            page=result.page,
            pages=result.pages,
            pageSize=result.selection.page_size,
            tableCount=number(result.table_count),
            scopeCount=number(t.records),
            sortColumn=result.selection.sort_column,
            descending=result.selection.descending,
            selection=-1,
            selectedText="Selecione uma linha para ver os detalhes.",
            selectedTitle="",
            monthly=[
                {"period": m, "label": period_label(m), "value": cents / 100_000_000}
                for m, cents in result.monthly
            ],
            countries=[
                {
                    "label": name,
                    "value": cents / 100_000_000,
                    "share": f"{number(Decimal(100) * cents / t.value_cents, 1)}%"
                    if t.value_cents
                    else "0%",
                }
                for name, cents in result.countries
            ],
            periodLabel=f"{period_label(result.selection.period.start)} a {period_label(result.selection.period.end)}",
            datasetSize=number(result.dataset_size),
            appliedStart=result.selection.period.start,
            appliedEnd=result.selection.period.end,
            tableRange=(
                f"{number((result.page - 1) * result.selection.page_size + 1)}–{number(min(result.page * result.selection.page_size, result.table_count))} de {number(result.table_count)} registros"
                if result.table_count
                else "0 registros"
            ),
            filterSummary=" · ".join(active)
            if active
            else "Todos os produtos e origens",
            elapsed=number(Decimal(str(time.perf_counter() - self._started)), 2) + " s",
        )
        self.table.replace(result.rows, result.selection.kind)
        self._result = result
        self._selection = replace(self._selection, page=result.page)
        if not self._is_demo:
            snapshot = self._provider.snapshot
            changes["cacheStatus"] = (
                f"{snapshot.api_requests} consultas à API oficial"
                if getattr(self._provider, "direct_api", False)
                else (
                    f"{snapshot.cache_hits} parcelas reutilizadas · {snapshot.api_requests} consultas à fonte"
                    + (
                        f" · {snapshot.shared_cache_hits} respostas da central"
                        if snapshot.shared_cache_hits
                        else ""
                    )
                )
            )
            changes["sourceUpdated"] = snapshot.availability.updated
            changes["sourceStatus"] = (
                "Dados até " + period_label(snapshot.availability.latest)
                if snapshot.availability.confirmed
                else "Comex Stat · consulta concluída"
            )
            changes["metadataError"] = ""
            changes["sourceNotice"] = (
                "Disponibilidade em cache; conexão não confirmada."
                if snapshot.availability.cached
                else ""
            )
        self._update(**changes)
        revision = (
            (id(self._provider.snapshot), result.selection.kind)
            if not self._is_demo
            else None
        )
        if revision != self._options_revision:
            self._options_revision = revision
            self.filtersChanged.emit()

    @Slot(str)
    def _failed(self, message: str):
        stale = self._worker is not None and self._worker.selection != self._selection
        if (
            not self._cancel.is_set()
            and self._pending is None
            and not self._closing
            and not stale
        ):
            self._sync_access_status()
            self._update(
                error=message,
                waiting=False,
                stage="A consulta não foi concluída. Os resultados anteriores foram preservados.",
            )

    @Slot()
    def _cancelled(self):
        if self._pending is None:
            self._update(
                stage="Consulta cancelada. Os resultados anteriores foram preservados."
            )

    @Slot()
    def _finished(self):
        self._thread, self._worker = None, None
        pending, self._pending = self._pending, None
        source_query, self._pending_source_query = self._pending_source_query, False
        self._running_source_query = False
        if pending is not None and not self._closing:
            self._queue(pending, source_query=source_query)
        else:
            self._update(busy=False, localBusy=False)
            self._try_close()

    @Slot()
    def cancel(self):
        had_work = self._thread is not None or self._debounce.isActive()
        self._debounce.stop()
        self._pending = None
        self._pending_source_query = False
        self._cancel.set()
        if not self._is_demo:
            self._provider.cancel_pending_options()
        if self._result is not None:
            self._selection = replace(self._result.selection, page=self._result.page)
            self._sync_filters()
            self.filtersChanged.emit()
        self._update(
            waiting=False,
            stage="Cancelando a consulta…"
            if self._thread
            else "Consulta cancelada. Os resultados anteriores foram preservados."
            if had_work
            else "Nenhuma consulta em andamento.",
        )

    @Slot()
    def requestClose(self):
        self._closing = True
        self._update(closing=True, sourceStatus="Encerrando tarefas em andamento…")
        self.cancel()
        self._metadata_cancel.set()
        self._export_cancel.set()
        self._try_close()

    def shutdown(self):
        """Última proteção no encerramento do processo; nunca termina threads à força."""
        self._closing = True
        self._debounce.stop()
        self._access_timer.stop()
        self._cancel.set()
        self._metadata_cancel.set()
        self._export_cancel.set()
        for thread_name, worker_name in (
            ("_thread", "_worker"),
            ("_metadata_thread", "_metadata_worker"),
            ("_export_thread", "_export_worker"),
        ):
            thread = getattr(self, thread_name)
            if thread is not None:
                setattr(self, thread_name, None)
                thread.quit()
                thread.wait()
                setattr(self, worker_name, None)

    @Slot(int)
    def selectRow(self, row: int):
        if not self._result or not 0 <= row < len(self._result.rows):
            return
        record = self._result.rows[row]
        values = cells(record)
        self._update(
            selection=row,
            selectedTitle=record.product,
            selectedText="\n".join(
                f"{header}: {value}"
                for header, value in zip(self.table.headers, values, strict=True)
            ),
            copyMessage="",
        )

    @Slot()
    def copySelected(self):
        row = self._state["selection"]
        if not self._result or not 0 <= row < len(self._result.rows):
            return
        text = (
            (
                "DADOS DEMONSTRATIVOS LIARTE — NÃO OFICIAIS\n"
                if self._is_demo
                else "Fonte: MDIC/SECEX — Comex Stat\n"
            )
            + "\t".join(self.table.headers)
            + "\n"
            + "\t".join(cells(self._result.rows[row]))
        )
        QGuiApplication.clipboard().setText(text)
        self._update(
            copyMessage="Linha demonstrativa copiada."
            if self._is_demo
            else "Linha copiada."
        )

    @Slot(str, bool)
    def setPreference(self, key: str, value: bool):
        self.preferences.setPreference(key, value)
