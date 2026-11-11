"""Coleta retomável do Comex; consultas usam a versão local já aceita."""

from __future__ import annotations

from contextlib import nullcontext
from datetime import date, datetime, timezone
import logging
import math
import time

from liarte_engine import comexstat_importacoes as engine

from .comex_history import HistoryCheckpointError, HistoryError, HistoryStagingError
from .domain import Period
from .query import Cancelled, checkpoint

LOGGER = logging.getLogger("liarte.desktop")
_METADATA_TTL = 86400.0
_METADATA_SCHEMA = "liarte.comex-metadata/1"


class HistorySyncError(HistoryError):
    """Uma aquisição não satisfez o contrato da publicação oficial."""


def _seconds(value, name):
    if type(value) not in (int, float):
        raise ValueError(f"{name} deve ser um intervalo finito e não negativo.")
    try:
        result = float(value)
    except (OverflowError, ValueError):
        raise ValueError(f"{name} deve ser um intervalo finito e não negativo.") from None
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{name} deve ser um intervalo finito e não negativo.")
    return result


class HistorySynchronizer:
    """Um escritor por arquivo; etapas aceitas sobrevivem entre execuções.

    O prazo de auditoria é uma política técnica explícita. Metadados iguais não
    demonstram que todos os registros antigos continuam iguais.
    """

    def __init__(
        self, store, client_factory, validate, *, publication_guard=nullcontext,
        audit_interval=86400.0, check_interval=300.0, first_month="1997-01",
        clock=time.time,
    ):
        first_month = Period(first_month, first_month).start
        if first_month < "1997-01":
            raise ValueError("O histórico NCM começa em 1997; NBM exige outro contrato.")
        self.store = store
        self.client_factory = client_factory
        self.validate = validate
        self.publication_guard = publication_guard
        self.audit_interval = _seconds(audit_interval, "Auditoria integral")
        self.check_interval = _seconds(check_interval, "Verificação de publicação")
        self.first_month = first_month
        self.clock = clock

    def _now(self):
        return datetime.fromtimestamp(self.clock(), timezone.utc).isoformat(timespec="seconds")

    @staticmethod
    def _recent(epoch, now, interval):
        if type(epoch) not in (int, float):
            return False
        try:
            elapsed = now - float(epoch)
        except (OverflowError, ValueError):
            return False
        return bool(epoch > 0 and math.isfinite(elapsed) and 0 <= elapsed < interval)

    def _validate_metadata(self, latest, updated):
        try:
            today = datetime.fromtimestamp(self.clock(), timezone.utc).date()
            Period("1997-01", latest)
            if latest > today.strftime("%Y-%m"):
                raise ValueError("Mês futuro")
            if not isinstance(updated, str) or len(updated) > 128:
                raise ValueError("Data de publicação ausente")
            date.fromisoformat(updated)
        except (TypeError, ValueError, OverflowError) as exc:
            raise HistorySyncError("As datas da publicação oficial são inválidas.") from exc

    def _validate_publication(self, publication):
        if not isinstance(publication, dict) or set(publication) != {
            "latest", "updated", "municipal_latest", "municipal_updated",
        }:
            raise HistorySyncError("A revisão da publicação não foi reconhecida.")
        self._validate_metadata(publication["latest"], publication["updated"])
        self._validate_metadata(publication["municipal_latest"], publication["municipal_updated"])

    def _checkpoint_metadata(self, key):
        try:
            raw = self.store.get_checkpoint(key)
        except HistoryCheckpointError:
            # This optional progress record is not an accepted dataset. Only
            # its own corruption is recoverable here; SQLite/IO errors remain
            # fatal and must not be reinterpreted as a cache miss.
            self.store.clear_checkpoint(key)
            raw = None
        saved = {"schema": _METADATA_SCHEMA}
        if isinstance(raw, dict) and raw.get("schema") == _METADATA_SCHEMA:
            for base in ("general", "municipal"):
                item = raw.get(base)
                if not isinstance(item, dict):
                    continue
                try:
                    self._validate_metadata(item.get("latest"), item.get("updated"))
                    epoch = item["received_epoch"]
                    stamp = item["received_at"]
                    if not self._recent(epoch, self.clock(), _METADATA_TTL):
                        continue
                    if not isinstance(stamp, str) or len(stamp) > 128:
                        continue
                    parsed = datetime.fromisoformat(stamp)
                    if parsed.utcoffset() is None or abs(parsed.timestamp() - epoch) > 1:
                        continue
                    saved[base] = {
                        "latest": item["latest"], "updated": item["updated"],
                        "received_epoch": epoch, "received_at": stamp,
                    }
                except (HistorySyncError, KeyError, TypeError, ValueError, OverflowError):
                    continue
        return saved

    def _publication(self, client, cancel, *, key):
        """Resume each metadata endpoint too; a 429 never replays its peer.

        A completed checkpoint is consumed, so a later independent check or a
        failed commit cannot relabel an old completed check as a new request.
        """
        saved = self._checkpoint_metadata(key)
        self.store.put_checkpoint(key, saved)
        for base in ("general", "municipal"):
            checkpoint(cancel)
            if base in saved:
                continue
            if base == "general":
                latest, updated = client.latest_published_period()
            else:
                response = client.request_json("GET", "/cities/dates/updated")
                data = response.get("data") if isinstance(response, dict) else None
                if not isinstance(data, dict):
                    raise HistorySyncError("A publicação municipal não retornou metadados válidos.")
                latest = f"{data.get('year', '')}-{str(data.get('monthNumber', '')).zfill(2)}"
                updated = data.get("updated")
            checkpoint(cancel)
            self._validate_metadata(latest, updated)
            saved[base] = {
                "latest": latest, "updated": updated,
                "received_epoch": self.clock(), "received_at": self._now(),
            }
            self.store.put_checkpoint(key, saved)
        checkpoint(cancel)
        self.store.clear_checkpoint(key)
        return {
            "latest": saved["general"]["latest"], "updated": saved["general"]["updated"],
            "municipal_latest": saved["municipal"]["latest"],
            "municipal_updated": saved["municipal"]["updated"],
        }

    def _unchanged(self, before, *, status):
        after = self.store.status()
        return {
            **after,
            "status": status,
            "changed": after.get("local_revision", "") != before.get("local_revision", ""),
        }

    def _covered_plan(self, status, publication):
        if not isinstance(publication, dict):
            return False
        latest, municipal = publication.get("latest"), publication.get("municipal_latest")
        if not isinstance(latest, str) or not isinstance(municipal, str) or not latest or not municipal:
            return False
        return (
            status.get("complete")
            and status.get("coverage_start") == self.first_month
            and status.get("coverage_end") == min(latest, municipal)
        )

    @staticmethod
    def _completed_progress(progress, message):
        # The commit (or finished metadata check) is the linearization point.
        # A later UI cancellation cannot turn it into a reported rollback.
        try:
            progress(100, message)
        except Exception:
            LOGGER.warning("Não foi possível apresentar o progresso final da atualização Comex.")

    def synchronize(self, cancel, progress, *, force=False, audit=False):
        """Verifique publicação e extraia o histórico quando sua revisão exigir.

        ``force`` ignora o intervalo da verificação; ``audit`` também exige
        reextração. Nenhum deles encurta as pausas do cliente da API.
        """
        def check():
            checkpoint(cancel)

        check()
        # Entering this lock must fail before changing the state of a writer
        # that is already working. It never surrounds a reader transaction.
        with self.store.writer_lock(check):
            before = self.store.status()
            client = None
            run = None
            try:
                now = self.clock()
                pending = self.store.pending_run_info()
                audit_recent = self._recent(before.get("last_full_sync_epoch"), now, self.audit_interval)
                stable = before.get("sync_state") in ("ready", "idle", "complete", "unchanged")
                if (
                    pending is None and not force and not audit
                    and not before.get("reextract_required", False)
                    and self._covered_plan(before, before.get("publication")) and stable and audit_recent
                    and self._recent(before.get("last_check_epoch"), now, self.check_interval)
                ):
                    return self._unchanged(before, status="throttled")

                self.store.record_state("checking")
                progress(0, "Verificando publicação do Comex Stat")
                current_progress = 0

                def api_progress(fraction, message):
                    check()
                    # The source callback may provide None, never convert it
                    # to a speculative percentage of the historical download.
                    progress(current_progress, message)

                client = self.client_factory(cancel, api_progress)
                if pending is not None:
                    publication = pending["publication"]
                    self._validate_publication(publication)
                    end = min(publication["latest"], publication["municipal_latest"])
                    if pending["start"] != self.first_month or pending["end"] != end:
                        self.store.abandon_run(pending["run_id"])
                        self.store.clear_checkpoint("metadata:final:" + pending["run_id"])
                        pending = None
                if pending is None:
                    publication = self._publication(client, cancel, key="metadata:initial")
                    self.store.record_check(publication)
                    end = min(publication["latest"], publication["municipal_latest"])
                    if end < self.first_month:
                        raise HistorySyncError("A publicação oficial ainda não cobre o início solicitado.")
                    if (
                        not audit and not before.get("reextract_required", False)
                        and self._covered_plan(before, publication) and audit_recent
                        and before.get("publication") == publication
                    ):
                        check()
                        self.store.record_state("ready")
                        self._completed_progress(progress, "A base local corresponde à última publicação verificada")
                        return self._unchanged(before, status="unchanged")
                    run = self.store.begin_run(publication, self.first_month, end, check=check)
                else:
                    run = pending["run_id"]
                self.store.record_state("syncing")
                started_at = self._now()
                years = range(int(self.first_month[:4]), int(end[:4]) + 1)
                stages = len(years) * 2
                completed = 0
                for year in years:
                    start = max(self.first_month, f"{year:04d}-01")
                    stop = min(end, f"{year:04d}-12")
                    for municipal in (False, True):
                        check()
                        current_progress = 5 + int(90 * completed / stages)
                        name = "municipal" if municipal else "geral"
                        progress(current_progress, f"Atualizando histórico · {year} · base {name}")
                        if not self.store.has_stage(run, municipal, start, stop):
                            query = client.query_municipal_imports if municipal else client.query_imports
                            rows = query(self.store.codes, start, stop)
                            check()
                            self.validate((), rows, cancel) if municipal else self.validate(rows, (), cancel)
                            check()
                            self.store.write_stage(
                                run, municipal, start, stop, rows, check=check,
                                received_at=self._now(), acquisition_started_at=started_at,
                            )
                            del rows
                        completed += 1
                current_progress = 97
                progress(current_progress, "Conferindo a publicação antes de concluir a atualização")
                final_key = "metadata:final:" + run
                if self._publication(client, cancel, key=final_key) != publication:
                    self.store.abandon_run(run)
                    self.store.clear_checkpoint("metadata:initial")
                    self.store.clear_checkpoint(final_key)
                    raise HistorySyncError(
                        "A publicação mudou durante a aquisição. A base aceita foi preservada."
                    )
                self.store.record_check(publication)
                check()
                self.store.publish_run(run, check=check, guard=self.publication_guard)
                self._completed_progress(progress, "Histórico local atualizado")
                return self._unchanged(before, status="updated")
            except HistoryStagingError as exc:
                # Reusing a corrupt completed stage would make every retry
                # repeat only the final metadata checks and fail forever.
                # Discard this unfinished run, keeping the accepted manifest
                # and other catalogues untouched. The next attempt reextracts.
                if run is not None:
                    self.store.abandon_run(run, corrupt=True)
                    self.store.clear_checkpoint("metadata:final:" + run)
                if cancel.is_set():
                    self.store.record_state("cancelled")
                    raise Cancelled() from exc
                self.store.record_state("failed", str(exc)[:500])
                raise
            except Cancelled:
                self.store.record_state("cancelled")
                raise
            except Exception as exc:
                if cancel.is_set():
                    self.store.record_state("cancelled")
                    raise Cancelled() from exc
                self.store.record_state(
                    "paused" if isinstance(exc, engine.ComexRateLimitError) else "failed",
                    str(exc)[:500],
                )
                raise
            finally:
                if client is not None:
                    try:
                        client.close()
                    except Exception:
                        # Cleanup does not turn an already committed accepted
                        # version into a failed acquisition.
                        LOGGER.warning("Não foi possível encerrar o cliente de atualização Comex.")
