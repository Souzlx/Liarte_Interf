"""Central autenticada: uma fila de origem, deduplicação e cache em disco local.

As requisições HTTP da LAN retornam tickets imediatamente; esperas e downloads
ocorrem em um único worker. Nenhuma requisição pode escolher outro servidor de origem.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import queue
import re
import sqlite3
import time
import zlib
from contextlib import closing
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from threading import Event, RLock, Thread
from uuid import uuid4

from liarte_engine import comexstat_importacoes as engine
from liarte_engine.comex_access import RequestCoordinator
from liarte_engine.comex_gateway_client import MAX_REQUEST, MAX_RESPONSE, PROTOCOL
from liarte_engine.liarte_dados import json_bytes
from .catalog import catalog

LOGGER = logging.getLogger("liarte.desktop")


def validate_submission(value):
    if not isinstance(value, dict) or value.get("protocol") != PROTOCOL:
        raise ValueError("Protocolo de consulta inválido.")
    if not isinstance(value.get("request_id"), str) or not re.fullmatch(
        "[0-9a-f]{32}", value["request_id"]
    ):
        raise ValueError("Identificador de consulta inválido.")
    method, path, body = value.get("method"), value.get("path"), value.get("body")
    metadata = path in {"/general/dates/updated", "/cities/dates/updated"}
    if metadata:
        if method != "GET" or body is not None:
            raise ValueError("Consulta de disponibilidade inválida.")
    else:
        if method != "POST" or path not in {"/general?language=pt", "/cities?language=pt"}:
            raise ValueError("A central permite apenas consultas oficiais de importação.")
        if (
            not isinstance(body, dict)
            or body.get("flow") != "import"
            or body.get("monthDetail") is not True
        ):
            raise ValueError("Contrato da consulta inválido.")
        if set(body) != {"flow", "monthDetail", "period", "filters", "details", "metrics"}:
            raise ValueError("Contrato da consulta inválido.")
        municipal = path.startswith("/cities")
        permitted = {p["ncm"][:4] if municipal else p["ncm"] for p in catalog()}
        filters = body.get("filters")
        if not isinstance(filters, list) or len(filters) != 1 or not isinstance(filters[0], dict):
            raise ValueError("Filtro de produtos inválido.")
        chosen = filters[0].get("values")
        normalize = engine.normalize_heading if municipal else engine.normalize_ncm
        if (
            filters[0].get("filter") != ("heading" if municipal else "ncm")
            or not isinstance(chosen, list)
            or not 1 <= len(chosen) <= 200
            or any(normalize(code) not in permitted for code in chosen)
        ):
            raise ValueError("Produto fora do catálogo da LIARTE.")
        for key, allowed in (
            ("details", engine.MUNICIPAL_DETAILS if municipal else engine.DEFAULT_DETAILS),
            ("metrics", engine.MUNICIPAL_METRICS if municipal else engine.DEFAULT_METRICS),
        ):
            items = body.get(key)
            if (
                not isinstance(items, list)
                or not items
                or not all(isinstance(v, str) and v in allowed for v in items)
                or len(items) != len(set(items))
            ):
                raise ValueError("Dimensões ou métricas inválidas.")
        period = body.get("period")
        if not isinstance(period, dict):
            raise ValueError("Período inválido.")
        try:
            start, end = (
                engine.validate_period(period.get("from")),
                engine.validate_period(period.get("to")),
            )
        except Exception as exc:
            raise ValueError("Período inválido.") from exc
        if (
            not "1997-01" <= start <= end <= date.today().strftime("%Y-%m")
            or engine.period_index(end) - engine.period_index(start) >= 12
        ):
            raise ValueError("A central recebe lotes de até 12 meses publicados por vez.")
    if not metadata:
        full = engine.MUNICIPAL_DETAILS if path.startswith("/cities") else engine.DEFAULT_DETAILS
        metrics = engine.MUNICIPAL_METRICS if path.startswith("/cities") else engine.DEFAULT_METRICS
        control = "heading" if path.startswith("/cities") else "ncm"
        if (set(body["details"]) != set(full) and body["details"] != [control]) or set(
            body["metrics"]
        ) != set(metrics):
            raise ValueError(
                "A central utiliza o contrato completo de importações e sua conferência de totais."
            )
    revision = value.get("revision")
    if revision is not None and not isinstance(revision, dict):
        raise ValueError("Revisão da fonte inválida.")
    if len(json_bytes(revision)) > 8192 or type(value.get("refresh")) is not bool:
        raise ValueError("Revisão ou atualização inválida.")
    contract = {
        "protocol": PROTOCOL,
        "method": method,
        "path": path,
        "body": body,
        "revision": revision,
    }
    return hashlib.sha256(json_bytes(contract)).hexdigest(), metadata


def validate_reply(document, submission, check):
    data = document.get("data")
    if not isinstance(data, dict):
        raise engine.ComexStatError(
            "A fonte retornou dados incompletos; a resposta não foi armazenada."
        )
    if submission["metadata"]:
        try:
            period = engine.validate_period(
                str(data.get("year", "")) + "-" + str(data.get("monthNumber", "")).zfill(2)
            )
            if not "1997-01" <= period <= date.today().strftime("%Y-%m"):
                raise ValueError("Mês inválido.")
            if data.get("updated"):
                date.fromisoformat(str(data["updated"]))
        except Exception as exc:
            raise engine.ComexStatError(
                "A disponibilidade oficial retornou um formato inválido."
            ) from exc
        return
    rows = data.get("list")
    if not isinstance(rows, list):
        raise engine.ComexStatError("A fonte não retornou a lista de importações.")
    body = submission["body"]
    municipal = submission["path"].startswith("/cities")
    normalize = engine.normalize_heading if municipal else engine.normalize_ncm
    requested = {normalize(value) for value in body["filters"][0]["values"]}
    start, end = body["period"]["from"], body["period"]["to"]
    full = set(body["details"]) == set(
        engine.MUNICIPAL_DETAILS if municipal else engine.DEFAULT_DETAILS
    )
    for i, row in enumerate(rows):
        if i % 256 == 0:
            check()
        if not isinstance(row, dict):
            raise engine.ComexStatError("A fonte retornou um registro inválido.")
        if full:
            if municipal:
                engine.validate_municipal_api_row(row, requested, start, end, "central")
            else:
                engine.validate_api_row(row, requested, start, end, "central")
        else:
            code = normalize(row.get("headingCode" if municipal else "coNcm"))
            if code not in requested or not start <= engine.row_period(row) <= end:
                raise engine.ComexStatError("O total de conferência não corresponde à consulta.")
            for metric in body["metrics"]:
                engine.validate_metric(row.get(metric), metric, "conferência da central")


class SharedResponses:
    def __init__(self, path: Path, *, budget=256 * 1024 * 1024, clock=time.time):
        self.path, self.budget, self.clock = Path(path), budget, clock
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db, db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute(
                "CREATE TABLE IF NOT EXISTS replies (key TEXT PRIMARY KEY, expires REAL NOT NULL, touched REAL NOT NULL, sha TEXT NOT NULL, body BLOB NOT NULL)"
            )

    def connect(self):
        return sqlite3.connect(self.path, timeout=2)

    def get(self, key, *, allow_expired=False):
        with closing(self.connect()) as db, db:
            row = db.execute(
                "SELECT expires, sha, body FROM replies WHERE key=?", (key,)
            ).fetchone()
            if row is None or not allow_expired and row[0] <= self.clock():
                return None
            try:
                unpack = zlib.decompressobj()
                body = unpack.decompress(row[2], MAX_RESPONSE + 1)
                if (
                    len(body) > MAX_RESPONSE
                    or not unpack.eof
                    or unpack.unused_data
                    or hashlib.sha256(body).hexdigest() != row[1]
                ):
                    raise ValueError("Integridade inválida.")
            except (ValueError, zlib.error):
                db.execute("DELETE FROM replies WHERE key=?", (key,))
                LOGGER.warning(
                    "Resposta compartilhada inválida removida; será consultada novamente."
                )
                return None
            db.execute("UPDATE replies SET touched=? WHERE key=?", (self.clock(), key))
            return body

    def put(self, key, body, ttl):
        if len(body) > MAX_RESPONSE:
            raise ValueError("Resposta excessiva.")
        packed = zlib.compress(body, 3)
        now = self.clock()
        with closing(self.connect()) as db, db:
            db.execute("DELETE FROM replies WHERE expires < ?", (now - 3600,))
            db.execute(
                "INSERT OR REPLACE INTO replies VALUES(?,?,?,?,?)",
                (key, now + ttl, now, hashlib.sha256(body).hexdigest(), packed),
            )
            total = db.execute("SELECT COALESCE(SUM(LENGTH(body)),0) FROM replies").fetchone()[0]
            if total > self.budget:
                for old_key, size in db.execute(
                    "SELECT key,LENGTH(body) FROM replies ORDER BY touched"
                ).fetchall():
                    if total <= self.budget:
                        break
                    db.execute("DELETE FROM replies WHERE key=?", (old_key,))
                    total -= size


@dataclass
class CentralJob:
    ticket: str
    key: str
    submission: dict
    touched: float
    state: str = "queued"
    message: str = "Aguardando a fila compartilhada"
    error: str = ""
    error_kind: str = ""
    retry_at: float = 0
    observed_http_status: int | None = None
    finished: float = 0


class CentralBroker:
    def __init__(
        self,
        directory: Path,
        *,
        interval=65.0,
        client_factory=None,
        access_path=None,
    ):
        self.directory = Path(directory)
        self.cache = SharedResponses(self.directory / "respostas.sqlite3")
        self.access_path = (
            Path(access_path) if access_path is not None else self.directory / "acesso.sqlite3"
        )
        self.coordinator = RequestCoordinator(self.access_path)
        self._official_source = client_factory is None
        self.interval = max(65.0, interval) if self._official_source else interval
        if client_factory is None:
            from .comex_source import source_factory

            client_factory = source_factory(self.directory)
        self.client_factory = client_factory
        self.stop_event = Event()
        self.lock = RLock()
        self.pending = queue.Queue(maxsize=128)
        self.jobs, self.inflight, self.requests = {}, {}, {}
        self.api_jobs = self.cache_hits = self.joins = 0
        self.worker = Thread(target=self._run, name="liarte-central-fila", daemon=True)
        self.worker.start()

    def _record_failure(self, event):
        from liarte_engine.liarte_dados import atomic_json

        record = dict(event)
        record["excerpt_sha256"] = hashlib.sha256(
            record.get("response_excerpt", "").encode()
        ).hexdigest()
        try:
            atomic_json(self.directory / "ultima_falha_comex.json", record)
        except OSError:
            LOGGER.warning("Não foi possível salvar o diagnóstico da fonte.")
        LOGGER.warning(
            "Comex Stat HTTP %s em %s. Retry-After: %s. Resposta: %s",
            record.get("http_status"),
            record.get("endpoint"),
            record.get("retry_after_header", ""),
            record.get("response_excerpt", ""),
        )

    def _pending_reply(self, job, *, shared=False):
        return (
            202,
            json_bytes(
                {"ticket": job.ticket, "message": job.message, "poll_after": 1, "shared": shared}
            ),
            {},
        )

    def submit(self, submission):
        key, metadata = validate_submission(submission)
        now = time.time()
        with self.lock:
            if self.stop_event.is_set():
                return 503, json_bytes({"error": "A central está sendo encerrada."}), {}
            self._prune(now)
            previous = self.requests.get(submission["request_id"])
            if previous:
                if previous[1] != key:
                    raise ValueError("O identificador já pertence a outra consulta.")
                return self.job(previous[0])
            job = self.inflight.get(key)
            if job is not None:
                self.requests[submission["request_id"]] = (job.ticket, key, now)
                job.touched = now
                self.joins += 1
                return self._pending_reply(job, shared=True)
            cached = None if submission["refresh"] else self.cache.get(key)
            if cached is not None:
                self.cache_hits += 1
                return 200, cached, {"X-Liarte-Cache": "HIT"}
            if self.pending.full() or len(self.jobs) >= 512:
                return (
                    503,
                    json_bytes(
                        {
                            "error": "A fila da central está cheia. Aguarde as consultas em andamento."
                        }
                    ),
                    {},
                )
            job = CentralJob(uuid4().hex, key, {**submission, "metadata": metadata}, now)
            self.inflight[key] = self.jobs[job.ticket] = job
            self.requests[submission["request_id"]] = (job.ticket, key, now)
            self.pending.put_nowait(job)
            return self._pending_reply(job)

    def job(self, ticket):
        with self.lock:
            job = self.jobs.get(ticket)
            if job is None:
                return (
                    410,
                    json_bytes(
                        {"error": "A consulta expirou na central. Solicite o período novamente."}
                    ),
                    {},
                )
            job.touched = time.time()
            if job.state == "failed":
                if job.error_kind == "COMEX_RATE_LIMIT":
                    return (
                        429,
                        json_bytes(
                            {
                                "error": job.error,
                                "code": job.error_kind,
                                "retry_after": max(0, job.retry_at - time.time()),
                                "observed_http_status": job.observed_http_status,
                            }
                        ),
                        {},
                    )
                return 502, json_bytes({"error": job.error, "code": job.error_kind}), {}
            if job.state == "done":
                payload = self.cache.get("job:" + job.ticket, allow_expired=True)
                if payload is not None:
                    return 200, payload, {"X-Liarte-Cache": "ORIGIN"}
                return (
                    410,
                    json_bytes(
                        {"error": "A resposta não está mais disponível. Solicite novamente."}
                    ),
                    {},
                )
            return self._pending_reply(job)

    def _prune(self, now):
        expired = [
            key for key, job in self.jobs.items() if job.finished and now - job.finished > 900
        ]
        for key in expired:
            self.jobs.pop(key, None)
        self.requests = {
            key: value
            for key, value in self.requests.items()
            if value[0] in self.jobs and now - value[2] <= 3600
        }

    def _run(self):
        while not self.stop_event.is_set():
            try:
                job = self.pending.get(timeout=0.2)
            except queue.Empty:
                continue
            client = None
            try:
                with self.lock:
                    job.state = "running"

                def check():
                    if self.stop_event.is_set():
                        raise RuntimeError("A central foi encerrada.")
                    if time.time() - job.touched > 45:
                        raise RuntimeError(
                            "A consulta deixou de ser acompanhada pelos computadores."
                        )

                def notify(fraction, message):
                    with self.lock:
                        job.message = str(message)[:200]

                options = dict(
                    timeout=25,
                    min_interval=self.interval,
                    max_attempts=3,
                    coordinator_path=self.access_path,
                    cancel_check=check,
                    cancel_wait=self.stop_event.wait,
                    progress_callback=notify,
                    failure_callback=self._record_failure,
                )
                if self._official_source:
                    options["source_revision"] = job.submission["revision"]
                    options["refresh_cache"] = job.submission["refresh"]
                client = self.client_factory(**options)
                check()
                document = client.request_json(
                    job.submission["method"], job.submission["path"], job.submission["body"]
                )
                data = document.get("data")
                if not isinstance(data, dict) or (
                    not job.submission["metadata"] and not isinstance(data.get("list"), list)
                ):
                    raise engine.ComexStatError(
                        "A fonte retornou dados incompletos; a resposta não foi armazenada."
                    )
                validate_reply(document, job.submission, check)
                raw = json_bytes(document)
                check()
                self.cache.put("job:" + job.ticket, raw, 900)
                revision = job.submission.get("revision") or {}
                # Keep completed detail downloads across a failed control,
                # scoped to the publication revision. Only the engine may
                # publish a fully reconciled snapshot.
                ttl = (
                    60 if job.submission["metadata"] else 86400 if revision.get("updated") else 300
                )
                self.cache.put(job.key, raw, ttl)
                with self.lock:
                    self.api_jobs += 1
                    job.state = "done"
            except Exception as exc:
                LOGGER.warning(
                    "Consulta da central não concluída: %s: %s", type(exc).__name__, str(exc)[:1500]
                )
                if isinstance(exc, engine.ComexRateLimitError):
                    LOGGER.warning("Resposta do Comex Stat em %s: %s", exc.endpoint, exc.detail)
                    try:
                        from liarte_engine.liarte_dados import atomic_json

                        atomic_json(
                            self.directory / "ultima_falha_comex.json",
                            {
                                "http_status": 429,
                                "observed_http_status": exc.observed_http_status,
                                "endpoint": exc.endpoint,
                                "retry_at": exc.retry_at,
                                "retry_after": exc.retry_after,
                                "response_excerpt": exc.detail,
                                "excerpt_sha256": hashlib.sha256(exc.detail.encode()).hexdigest(),
                                "captured_at": time.time(),
                            },
                        )
                    except OSError:
                        LOGGER.warning("Não foi possível salvar o diagnóstico da fonte.")
                with self.lock:
                    job.state = "failed"
                    job.error_kind = (
                        "COMEX_RATE_LIMIT"
                        if isinstance(exc, engine.ComexRateLimitError)
                        else "CENTRAL_STOPPED"
                        if self.stop_event.is_set()
                        else "SOURCE_ERROR"
                    )
                    job.retry_at = getattr(exc, "retry_at", 0)
                    job.observed_http_status = getattr(exc, "observed_http_status", None)
                    job.error = (
                        str(exc)[:500]
                        if isinstance(exc, (engine.ComexStatError, RuntimeError))
                        else "A central não conseguiu concluir a consulta. Consulte o diagnóstico do servidor."
                    )
            finally:
                if client is not None:
                    client.close()
                with self.lock:
                    job.finished = time.time()
                    self.inflight.pop(job.key, None)
                self.pending.task_done()

    def status(self):
        with self.lock:
            return {
                "protocol": PROTOCOL,
                "stopping": self.stop_event.is_set(),
                "queued": self.pending.qsize(),
                "active": sum(j.state == "running" for j in self.inflight.values()),
                "completed": self.api_jobs,
                "cache_hits": self.cache_hits,
                "joined": self.joins,
                **self.coordinator.status(),
            }

    def close(self):
        self.stop_event.set()
        self.worker.join(timeout=2)


class CentralApplication:
    def __init__(self, broker: CentralBroker, token: str):
        if not re.fullmatch(r"[A-Za-z0-9_\-]{32,256}", token):
            raise ValueError("Chave da central inválida.")
        self.broker, self.token = broker, token

    def __call__(self, env, start_response):
        status, payload, extra = 500, json_bytes({"error": "Falha na central."}), {}
        try:
            auth = env.get("HTTP_AUTHORIZATION", "")
            if not hmac.compare_digest(
                auth.encode("utf-8"), ("Bearer " + self.token).encode("utf-8")
            ):
                status, payload = 401, json_bytes({"error": "Chave de acesso à central inválida."})
            elif env.get("REQUEST_METHOD") == "GET" and env.get("PATH_INFO") == "/v1/health":
                status, payload = 200, json_bytes(self.broker.status())
            elif env.get("REQUEST_METHOD") == "GET" and re.fullmatch(
                r"/v1/jobs/[0-9a-f]{32}", env.get("PATH_INFO", "")
            ):
                status, payload, extra = self.broker.job(env["PATH_INFO"].rsplit("/", 1)[1])
            elif env.get("REQUEST_METHOD") == "POST" and env.get("PATH_INFO") == "/v1/query":
                length = int(env.get("CONTENT_LENGTH") or 0)
                if (
                    not 0 < length <= MAX_REQUEST
                    or env.get("CONTENT_TYPE", "").split(";", 1)[0] != "application/json"
                ):
                    raise ValueError("Formato ou tamanho da consulta inválido.")
                raw = env["wsgi.input"].read(length)
                if len(raw) != length:
                    raise ValueError("Consulta incompleta.")
                status, payload, extra = self.broker.submit(json.loads(raw))
            else:
                status, payload = 404, json_bytes({"error": "Operação não encontrada na central."})
        except (ValueError, KeyError, TypeError, AttributeError):
            status, payload = 422, json_bytes({"error": "A consulta enviada à central é inválida."})
        except Exception:
            LOGGER.exception("Falha no atendimento da Central de Consultas")
        reason = {
            200: "OK",
            202: "Accepted",
            401: "Unauthorized",
            404: "Not Found",
            410: "Gone",
            422: "Unprocessable Content",
            429: "Too Many Requests",
            500: "Internal Server Error",
            502: "Bad Gateway",
            503: "Service Unavailable",
        }[status]
        start_response(
            f"{status} {reason}",
            [
                ("Content-Type", "application/json; charset=utf-8"),
                ("Content-Length", str(len(payload))),
                ("Cache-Control", "no-store"),
                ("X-Content-Type-Options", "nosniff"),
                ("X-Liarte-Protocol", PROTOCOL),
                *extra.items(),
            ],
        )
        return [payload]


class CentralServer:
    def __init__(self, broker, token, *, host="127.0.0.1", port=8767):
        from waitress import create_server

        self.broker = broker
        self._channels = {}
        self._close_lock = RLock()
        self._closed = False
        self.server = create_server(
            CentralApplication(broker, token),
            host=host,
            port=port,
            threads=12,
            connection_limit=64,
            channel_timeout=30,
            max_request_body_size=MAX_REQUEST,
            max_request_header_size=16384,
            expose_tracebacks=False,
            clear_untrusted_proxy_headers=True,
            asyncore_loop_timeout=0.5,
            map=self._channels,
        )
        self.port = self.server.effective_port
        self.thread = Thread(target=self._serve, name="liarte-central-http", daemon=True)

    def _serve(self):
        try:
            self.server.run()
        except Exception:
            if not self._closed:
                LOGGER.exception("Falha no atendimento HTTP da Central de Consultas")
                self.broker.stop_event.set()

    def start(self):
        if self._closed:
            raise RuntimeError("A central já foi encerrada.")
        self.thread.start()

    def close(self):
        with self._close_lock:
            if self._closed:
                return
            self._closed = True
            self.broker.stop_event.set()
            # Os workers ainda sinalizam o event loop ao concluir uma resposta.
            # Encerrá-los antes do trigger evita escrita em um descritor já fechado.
            self.server.task_dispatcher.shutdown(cancel_pending=True, timeout=10)
            self.server.close()
            # O socket de escuta não encerra conexões persistentes já aceitas.
            for channel in list(self._channels.values()):
                try:
                    channel.close()
                except OSError:
                    LOGGER.debug("Conexão já encerrada na central", exc_info=True)
            if self.thread.is_alive():
                self.thread.join(timeout=2)
            self.broker.close()
