"""Sincronização do histórico, independente das consultas locais do desktop."""

from __future__ import annotations

import logging
import time
from threading import Event

from PySide6.QtCore import QObject, Property, QThread, QTimer, Signal, Slot

from liarte_core.query import Cancelled

LOGGER = logging.getLogger("liarte.desktop")


class HistorySyncWorker(QObject):
    progress = Signal(int, str)
    succeeded = Signal(object)
    failed = Signal(str)
    cancelled = Signal()
    finished = Signal()
    backupNotice = Signal(str)

    def __init__(self, provider, cancel, *, force=False):
        super().__init__()
        self.provider, self.cancel, self.force = provider, cancel, force

    @Slot()
    def run(self):
        last_emission, last_stage = -float("inf"), ""

        def report(percent, stage):
            nonlocal last_emission, last_stage
            if self.cancel.is_set():
                raise Cancelled()
            now = time.monotonic()
            if stage != last_stage or percent == 100 or now - last_emission >= 0.1:
                self.progress.emit(max(0, min(100, int(percent or 0))), str(stage))
                last_emission, last_stage = now, stage

        try:
            result = self.provider.synchronize(self.cancel, report, force=self.force)
            if self.cancel.is_set():
                self.cancelled.emit()
            else:
                self.succeeded.emit(result)
        except Cancelled:
            self.cancelled.emit()
        except (RuntimeError, ValueError, OSError) as exc:
            LOGGER.warning("Atualização do histórico não concluída: %s", exc)
            self.failed.emit(str(exc)[:600] or "A atualização não foi concluída.")
        except Exception:
            LOGGER.exception("Falha na atualização do histórico Comex")
            self.failed.emit("Não foi possível atualizar o histórico. A base local aceita foi preservada.")
        finally:
            if not self.cancel.is_set():
                self._backup()
            self.finished.emit()

    def _backup(self):
        from liarte_core.comex_history import HistoryStore
        from liarte_core.comex_history_backup import create_backup

        store = getattr(self.provider, "history", None)
        if not isinstance(store, HistoryStore):
            return
        try:
            status = store.status()
            revision = status.get("local_revision")
            if revision and status.get("complete"):
                target = store.path.parent / "backups-comex" / (store.catalog_key[:16] + "-" + revision)
                if not target.is_dir():
                    create_backup(store, self.cancel)
                self.backupNotice.emit("Cópia local do histórico disponível nesta instalação.")
        except Cancelled:
            pass
        except Exception:
            LOGGER.warning("Não foi possível criar a cópia local do histórico", exc_info=True)
            self.backupNotice.emit("A base está preservada; não foi possível criar sua cópia de segurança.")


class HistorySyncOwner(QObject):
    """Uma tarefa de escrita; leitores e exportações continuam independentes.

    O construtor não agenda rede. A composição inicia o modo automático ao
    entrar em Importações; uma consulta também solicita uma verificação.
    """

    changed = Signal()
    updated = Signal()
    readyToClose = Signal()

    def __init__(self, provider, parent=None, *, clock=time.monotonic, check_interval=300.0):
        super().__init__(parent)
        self.provider, self.clock = provider, clock
        self.check_interval = max(1.0, float(check_interval))
        self.enabled = bool(getattr(provider, "is_historical", False))
        self._thread = self._worker = None
        self._cancel = Event()
        self._closing = self._automatic = self._stopped = False
        self._next_attempt = 0.0
        self._last_revision = ""
        self._stage = ""
        self._error = ""
        self._pause_status = 0
        self._state = {
            "backupNotice": "",
            "enabled": self.enabled, "busy": False, "progress": 0,
            "message": "", "error": "", "coverageStart": "", "coverageEnd": "",
            "completeMonths": 0, "complete": False, "checkedAt": "", "baseUpdatedAt": "",
            "pauseSeconds": 0, "stopped": False,
        }
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        if self.enabled:
            self.refresh()

    @Property("QVariantMap", notify=changed)
    def state(self):
        return dict(self._state)

    @property
    def running(self):
        return self._thread is not None

    def _update(self, **changes):
        if QThread.currentThread() != self.thread():
            raise RuntimeError("Estado do histórico alterado fora da thread visual.")
        if any(self._state.get(key) != value for key, value in changes.items()):
            self._state.update(changes)
            self.changed.emit()

    @Slot()
    def refresh(self):
        if not self.enabled or self._closing:
            return
        try:
            status = self.provider.history_status()
            access = self.provider.access_status()
            pause = max(0, int(access.get("pause_seconds", 0)))
            self._pause_status = int(access.get("pause_status", 0)) if pause else 0
            first, last = status.get("coverage_start", ""), status.get("coverage_end", "")
            complete = bool(status.get("complete", False))
            if self._stopped:
                message = "Atualização interrompida. Os períodos já carregados permanecem disponíveis."
            elif self.running:
                message = self._stage or "Verificando atualizações do histórico…"
            elif pause:
                message = "A atualização aguarda a pausa da fonte."
            elif self._error:
                message = "A atualização não foi concluída. Os dados aceitos foram preservados."
            elif complete:
                message = "Base local pronta para consulta."
            elif first and last:
                message = "Carga inicial incompleta. Consulte os períodos já carregados."
            else:
                message = "Histórico ainda não carregado. A primeira carga ocorre em segundo plano."
            self._update(
                coverageStart=first or "", coverageEnd=last or "",
                completeMonths=int(status.get("complete_months", 0)), complete=complete,
                checkedAt=status.get("checked_at", "") or "",
                baseUpdatedAt=status.get("last_full_sync_at", "") or "",
                pauseSeconds=pause, stopped=self._stopped, message=message, error=self._error,
            )
            revision = str(status.get("local_revision", "") or "")
            if revision != self._last_revision:
                self._last_revision = revision
                self.updated.emit()
        except Exception:
            LOGGER.exception("Não foi possível ler o estado do histórico")
            self._update(error="Não foi possível ler o estado da base local.")

    @Slot()
    def startAutomatic(self):
        if self.enabled and not self._closing:
            self._automatic = True
            self._timer.start()
            self.request_check(resume=False)

    def request_check(self, *, force=False, resume=False):
        if not self.enabled or self._closing:
            return
        if resume:
            self._stopped = False
        if self._stopped:
            return
        self._automatic = True
        self._timer.start()
        self.refresh()
        if self.running or self._state["pauseSeconds"]:
            return
        if not force and self.clock() < self._next_attempt:
            return
        self._cancel = Event()
        self._error, self._stage = "", "Verificando atualizações do histórico…"
        thread = QThread(self)
        worker = HistorySyncWorker(self.provider, self._cancel, force=force)
        worker.moveToThread(thread)
        self._thread, self._worker = thread, worker
        self._update(busy=True, progress=0, error="", stopped=False, message=self._stage)
        thread.started.connect(worker.run)
        worker.progress.connect(self._progress)
        worker.backupNotice.connect(self._backup_notice)
        worker.succeeded.connect(self._succeeded)
        worker.failed.connect(self._failed)
        worker.cancelled.connect(self._cancelled)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._finished)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    @Slot()
    def check(self):
        self.request_check(force=True, resume=True)

    @Slot(str)
    def _backup_notice(self, message):
        if not self._closing:
            self._update(backupNotice=message)

    @Slot(int, str)
    def _progress(self, percent, stage):
        if self._closing or self._cancel.is_set():
            return
        self._stage = stage
        self._update(progress=max(self._state["progress"], percent), message=stage)
        self.refresh()

    @Slot(object)
    def _succeeded(self, result):
        if not self._closing and not self._cancel.is_set():
            self._error = ""
            self._update(progress=100)
            self.refresh()

    @Slot(str)
    def _failed(self, message):
        if not self._closing and not self._cancel.is_set():
            self._error = message
            self.refresh()

    @Slot()
    def _cancelled(self):
        if not self._closing:
            self.refresh()

    @Slot()
    def _finished(self):
        self._thread = self._worker = None
        self._stage = ""
        self._next_attempt = self.clock() + self.check_interval
        if self._error and self._pause_status == 429 and self._state["pauseSeconds"]:
            # The persisted source deadline already gates request_check().
            # Adding the normal check cooldown here would leave an initial
            # download idle after its displayed rate-limit pause has ended.
            self._next_attempt = self.clock()
        self._update(busy=False)
        if self._closing:
            self.readyToClose.emit()
        else:
            self.refresh()

    @Slot()
    def cancel(self):
        self._stopped = True
        self._cancel.set()
        self.refresh()

    @Slot()
    def _tick(self):
        if self._closing:
            return
        self.refresh()
        if self._automatic and not self._stopped and not self.running:
            self.request_check()

    def request_close(self):
        self._closing = True
        self._timer.stop()
        self._cancel.set()
        if not self.running:
            self.readyToClose.emit()

    def shutdown(self):
        self.request_close()
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
            self._thread = self._worker = None
