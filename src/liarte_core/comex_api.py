"""Cliente direto do desktop: períodos mensais e recuperação verificável.

Não inicia serviços nem lê respostas de consultas em disco. A única informação
persistida pelo transporte é a pausa de recuperação decorrente de uma recusa da
fonte. Validações de negócio permanecem nas funções comuns dos geradores.
"""

from __future__ import annotations

from contextlib import contextmanager
from argparse import ArgumentTypeError
from datetime import datetime, timezone
from decimal import Decimal
from email.utils import parsedate_to_datetime
import errno
import http.client
import json
import math
import os
from pathlib import Path
import re
from threading import RLock
import time
import urllib.error
import urllib.request
import zlib

if os.name == "nt":
    import msvcrt
else:
    import fcntl

from liarte_engine import comexstat_importacoes as contract
from liarte_engine.liarte_dados import atomic_json
from liarte_engine.secure_http import build_opener, certificate_failure

API = "https://api-comexstat.mdic.gov.br"
MAX_BYTES = 100 * 1024 * 1024
PATHS = {
    ("POST", "/general?language=pt"),
    ("POST", "/cities?language=pt"),
    ("GET", "/general/dates/updated"),
    ("GET", "/cities/dates/updated"),
}


def _try_file_lock(handle):
    """Trava nativa sem espera; o sistema a libera se o processo terminar."""
    try:
        if os.name == "nt":
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
            raise
        return False
    return True


@contextmanager
def _process_lock(path, *, check=None, wait=None, notify=None):
    """Arquivo estável: nunca remover/trocar o inode que carrega a trava."""
    if path is None:
        yield
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        # msvcrt trava um byte a partir da posição corrente e permite uma
        # região além do EOF. Não escrever aqui evita uma corrida na criação
        # do arquivo no Windows. Não há lease nem prazo preventivo.
        started, last_notice = time.monotonic(), None
        while True:
            if check is not None:
                check()
            if _try_file_lock(handle):
                break
            elapsed = time.monotonic() - started
            if elapsed > 45:
                raise contract.ComexStatError(
                    "Outra operação desta instalação ainda está em andamento."
                )
            if notify is not None and (last_notice is None or elapsed - last_notice >= 1):
                notify("Aguardando outra consulta desta instalação")
                last_notice = elapsed
            (wait or time.sleep)(0.05)
        try:
            if check is not None:
                check()
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def retry_delay(headers, text, *, now=None):
    """Retry-After prevalece; mensagem do MDIC só é usada sem cabeçalho válido."""
    value = headers.get("Retry-After")
    if value is not None:
        try:
            seconds = float(value)
        except (ValueError, TypeError, OverflowError):
            try:
                target = parsedate_to_datetime(value)
                if target.tzinfo is None:
                    target = target.replace(tzinfo=timezone.utc)
                try:
                    origin = parsedate_to_datetime(headers.get("Date"))
                    if origin.tzinfo is None:
                        origin = origin.replace(tzinfo=timezone.utc)
                except (ValueError, TypeError, OverflowError):
                    origin = datetime.fromtimestamp(
                        time.time() if now is None else now, timezone.utc
                    )
                seconds = max(0.0, (target - origin).total_seconds())
            except (ValueError, TypeError, OverflowError):
                seconds = -1
        if math.isfinite(seconds) and seconds >= 0:
            return seconds + 0.5
    match = re.search(r"\b([0-9]{1,6})\s*segundos?\b", text, re.IGNORECASE)
    return float(match[1]) + 0.5 if match else 30.0


class ApiPause:
    """Estado local pequeno; sem fila SQLite, servidor ou cache de dados."""

    _registry_lock = RLock()
    _locks = {}

    def __init__(self, path=None, *, clock=time.time):
        self.path = Path(path) if path is not None else None
        self.state_lock_path = (
            self.path.with_name(self.path.name + ".pause.lock") if self.path else None
        )
        self.request_lock_path = (
            self.path.with_name(self.path.name + ".request.lock") if self.path else None
        )
        self.clock = clock
        self.until = 0.0
        self.status = 429
        with self._registry_lock:
            self.lock = (
                self._locks.setdefault(str(self.path.resolve()), RLock()) if self.path else RLock()
            )

    def remaining(self):
        if self.path is not None:
            try:
                if self.path.stat().st_size > 8192:
                    raise ValueError("Estado excessivo")
                data = json.loads(self.path.read_text(encoding="utf-8"))
                until = data["until"]
                if type(until) not in (int, float) or not math.isfinite(until):
                    raise ValueError("Prazo inválido")
                if until > self.until:
                    self.until, self.status = until, int(data.get("status", 429))
            except (OSError, ValueError, TypeError, KeyError, OverflowError):
                pass
        return max(0.0, self.until - self.clock())

    def defer(self, seconds, status, *, cancel_check=None, cancel_wait=None):
        deadline = self.clock() + seconds
        if not math.isfinite(seconds) or seconds < 0 or not math.isfinite(deadline):
            raise contract.ComexStatError("A fonte retornou um prazo de espera inválido.")
        with self.lock:
            self.remaining()
            if deadline > self.until:
                self.until, self.status = deadline, status
            if self.path is not None:
                try:
                    # Trava distinta da operação HTTP: nenhum leitor da pausa
                    # precisa aguardar a rede. Reabrir DENTRO da trava torna
                    # indivisível a comparação/gravação entre processos.
                    with _process_lock(self.state_lock_path, check=cancel_check, wait=cancel_wait):
                        self.remaining()
                        atomic_json(self.path, {"until": self.until, "status": self.status})
                except OSError:
                    pass  # A pausa continua ativa na memória desta instalação.


class ApiRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        raise contract.ComexStatError("A API redirecionou a consulta; o pedido não foi reenviado.")


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("Campo JSON repetido")
        result[key] = value
    return result


def _constant(value):
    raise ValueError("Número JSON não finito")


class ApiClient:
    """Transporte exclusivo da API, independente do cliente legado dos geradores."""

    def __init__(
        self,
        timeout=120,
        min_interval=0,
        max_attempts=2,
        *,
        rate_limit_attempts=None,
        use_cache=False,
        coordinator_path=None,
        pause_state=None,
        gateway=None,
        cancel_check=None,
        cancel_wait=None,
        progress_callback=None,
        failure_callback=None,
        verify_official_totals=False,
        window_months=None,
    ):
        if isinstance(timeout, bool) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Tempo limite inválido.")
        if type(max_attempts) is not int or not 1 <= max_attempts <= 2:
            raise ValueError("Use uma ou duas tentativas por pedido.")
        if rate_limit_attempts is None:
            rate_limit_attempts = max_attempts
        if type(rate_limit_attempts) is not int or not 1 <= rate_limit_attempts <= 4:
            raise ValueError("Use de uma a quatro tentativas para pausas da fonte.")
        if (
            min_interval != 0
            or use_cache
            or gateway is not None
            or verify_official_totals
            or window_months is not None
        ):
            raise ValueError("Este cliente utiliza somente consultas diretas da API.")
        self.timeout = float(timeout)
        self.max_attempts = max_attempts
        self.rate_limit_attempts = rate_limit_attempts
        self.pause = pause_state or ApiPause(coordinator_path)
        self.cancel_check, self.cancel_wait = cancel_check, cancel_wait
        self.progress_callback, self.failure_callback = progress_callback, failure_callback
        self.network_requests = 0
        self.cache = None
        self.shared_cache_hits = 0
        self.control_requests = 0
        self._opener = None

    def close(self):
        pass  # Cada resposta é fechada por seu próprio gerenciador de contexto.

    def _check(self):
        if self.cancel_check is not None:
            self.cancel_check()

    def _notify(self, message, fraction=None):
        self._check()
        if self.progress_callback is not None:
            self.progress_callback(fraction, message)

    def _sleep(self, seconds):
        end = time.monotonic() + seconds
        while (remaining := end - time.monotonic()) > 0:
            self._check()
            (self.cancel_wait or time.sleep)(min(0.2, remaining))
        self._check()

    def _pause_wait(self, budget, path, previous_error=None):
        remaining = self.pause.remaining()
        if remaining > budget:
            if previous_error is not None:
                raise previous_error
            if self.pause.status == 429:
                raise contract.ComexRateLimitError(remaining, path)
            raise contract.ComexStatError(
                "O Comex Stat está temporariamente indisponível. Tente novamente após a pausa indicada."
            )
        started = time.monotonic()
        last = None
        while (remaining := self.pause.remaining()) > 0:
            if time.monotonic() - started >= budget:
                if previous_error is not None:
                    raise previous_error
                if self.pause.status != 429:
                    raise contract.ComexStatError(
                        "O Comex Stat continua temporariamente indisponível."
                    )
                raise contract.ComexRateLimitError(remaining, path)
            seconds = math.ceil(remaining)
            if seconds != last:
                self._notify(f"Aguardando o Comex Stat · nova tentativa em {seconds} s")
                last = seconds
            self._sleep(min(0.2, remaining))
        return max(0.0, budget - (time.monotonic() - started))

    @contextmanager
    def _serial(self):
        started = time.monotonic()
        while not self.pause.lock.acquire(timeout=0.1):
            self._check()
            self._notify("Aguardando outra consulta desta instalação")
            if time.monotonic() - started > 45:
                raise contract.ComexStatError(
                    "Outra consulta desta instalação ainda está em andamento."
                )
        try:
            self._check()
            try:
                with _process_lock(
                    self.pause.request_lock_path,
                    check=self._check,
                    wait=self.cancel_wait,
                    notify=self._notify,
                ):
                    yield
            except OSError as exc:
                raise contract.ComexStatError(
                    "Não foi possível coordenar as consultas desta instalação."
                ) from exc
        finally:
            self.pause.lock.release()

    def _open(self, request, *, timeout):
        if self._opener is None:
            self._opener = build_opener(ApiRedirects())
        return self._opener.open(request, timeout=timeout)

    def _receive(self, request):
        self._check()
        self.network_requests += 1
        try:
            response = getattr(self, "_network_opener", self._open)(request, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            status, headers = int(response.status), response.headers
            if status != 200:
                try:
                    raw = response.read(64 * 1024)
                    if str(headers.get("Content-Encoding", "")).lower() == "gzip":
                        raw = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(raw, 4096)
                except (OSError, http.client.HTTPException, zlib.error):
                    raw = b""
                return status, headers, raw[:4096].decode("utf-8", errors="replace")
            raw_length = headers.get("Content-Length")
            try:
                expected = int(raw_length) if raw_length is not None else None
            except (ValueError, TypeError, OverflowError) as exc:
                raise contract.ComexStatError(
                    "A API informou um tamanho de resposta inválido."
                ) from exc
            if expected is not None and not 0 <= expected <= MAX_BYTES:
                raise contract.ComexStatError("O tamanho da resposta excedeu o limite de 100 MiB.")
            encoding = str(headers.get("Content-Encoding", "identity")).lower().strip()
            if encoding not in ("identity", "gzip"):
                raise contract.ComexStatError(
                    "A API retornou uma codificação de resposta não suportada."
                )
            decoder = zlib.decompressobj(16 + zlib.MAX_WBITS) if encoding == "gzip" else None
            received, buffer = 0, bytearray()
            deadline = time.monotonic() + 240
            read = getattr(response, "read1", response.read)
            while True:
                self._check()
                if time.monotonic() > deadline:
                    raise contract.ComexStatError("O Comex Stat excedeu o tempo limite de leitura.")
                block = read(256 * 1024)
                if not block:
                    break
                received += len(block)
                if received > MAX_BYTES:
                    raise contract.ComexStatError("A resposta excedeu o limite de 100 MiB.")
                try:
                    decoded = (
                        decoder.decompress(block, MAX_BYTES + 1 - len(buffer)) if decoder else block
                    )
                except zlib.error as exc:
                    raise contract.ComexStatError(
                        "A API retornou um arquivo compactado inválido."
                    ) from exc
                buffer.extend(decoded)
                if len(buffer) > MAX_BYTES or (decoder and decoder.unconsumed_tail):
                    raise contract.ComexStatError(
                        "A resposta descompactada excedeu o limite de 100 MiB."
                    )
            if expected is not None and expected != received:
                raise contract.ComexStatError(
                    "A API interrompeu a resposta. Nenhum dado parcial foi utilizado."
                )
            if decoder and (not decoder.eof or decoder.unused_data):
                raise contract.ComexStatError(
                    "A resposta compactada está incompleta ou possui dados adicionais."
                )
            try:
                text = buffer.decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                raise contract.ComexStatError("A API retornou texto inválido.") from exc
            return status, headers, text

    def _diagnose(self, path, status, effective, headers, text):
        if self.failure_callback is not None:
            try:
                self.failure_callback(
                    {
                        "endpoint": path,
                        "observed_http_status": status,
                        "http_status": effective,
                        "captured_at": time.time(),
                        "retry_after_header": str(headers.get("Retry-After") or "")[:200],
                        "response_excerpt": text[:1500],
                        "response_headers": {
                            key: str(headers.get(key))[:200]
                            for key in (
                                "Date",
                                "Server",
                                "Content-Type",
                                "Age",
                                "X-Cache",
                                "X-Request-ID",
                            )
                            if headers.get(key) is not None
                        },
                    }
                )
            except Exception:
                pass

    def request_json(self, method, path, json_body=None):
        if (method, path) not in PATHS or (method == "GET" and json_body is not None):
            raise ValueError("Pedido fora dos endpoints oficiais desta aplicação.")
        data = (
            json.dumps(json_body, ensure_ascii=False, allow_nan=False).encode("utf-8")
            if json_body is not None
            else None
        )
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Accept-Encoding": "gzip",
            "User-Agent": "LIARTE-Desktop/5.3.1-rc.1",
        }
        attempt, wait_budget, previous_error = 0, 90.0, None
        transient_failures, previous_rate_delay = 0, 0.0
        attempt_limit = max(self.max_attempts, self.rate_limit_attempts)
        while attempt < attempt_limit:
            wait_budget = self._pause_wait(wait_budget, path, previous_error)
            transient = None
            rate_limited = False
            with self._serial():
                if self.pause.remaining() > 0:
                    continue
                attempt += 1
                self._notify(f"Acessando o Comex Stat · tentativa {attempt}/{attempt_limit}")
                try:
                    status, response_headers, text = self._receive(
                        urllib.request.Request(
                            API + path, data=data, headers=headers, method=method
                        )
                    )
                except (
                    urllib.error.URLError,
                    TimeoutError,
                    OSError,
                    http.client.HTTPException,
                ) as exc:
                    if certificate_failure(exc):
                        raise contract.ComexStatError(
                            "Não foi possível validar o certificado HTTPS do Comex Stat. A conexão foi interrompida com segurança."
                        ) from exc
                    transient = contract.ComexStatError(
                        "Não foi possível concluir a conexão com o Comex Stat. Verifique a rede e tente novamente."
                    )
                    transient.__cause__ = exc
                    payload = None
                else:
                    payload = None
                    if status == 200:
                        try:
                            payload = json.loads(
                                text,
                                parse_float=Decimal,
                                parse_constant=_constant,
                                object_pairs_hook=_pairs,
                            )
                            if not isinstance(payload, dict):
                                raise ValueError("Raiz inválida")
                        except (ValueError, TypeError, RecursionError) as exc:
                            self._diagnose(path, status, status, response_headers, text)
                            raise contract.ComexStatError(
                                "A API retornou uma resposta JSON inválida. Os resultados anteriores foram preservados."
                            ) from exc
                    error = payload.get("error") if payload else None
                    code = (
                        payload.get("code", error.get("code") if isinstance(error, dict) else None)
                        if payload
                        else None
                    )
                    effective = (
                        429
                        if (error or (payload and payload.get("success") is False))
                        and str(code) == "429"
                        else status
                    )
                    if effective != 200:
                        self._diagnose(path, status, effective, response_headers, text)
                    if effective in (429, 500, 502, 503, 504):
                        delay = retry_delay(response_headers, text)
                        rate_limited = effective == 429
                        if rate_limited and self.rate_limit_attempts > self.max_attempts:
                            # A short generic pause can repeat while the origin is
                            # still busy. Never shorten its deadline; back off on
                            # subsequent refusals within this endpoint operation.
                            delay = max(delay, previous_rate_delay * 2)
                            previous_rate_delay = delay
                        self.pause.defer(
                            delay,
                            effective,
                            cancel_check=self._check,
                            cancel_wait=self.cancel_wait,
                        )
                        transient = (
                            contract.ComexRateLimitError(delay, path, text, status)
                            if effective == 429
                            else contract.ComexStatError(
                                f"O Comex Stat está temporariamente indisponível (HTTP {effective})."
                            )
                        )
                    elif effective != 200:
                        raise contract.ComexStatError(
                            f"O Comex Stat recusou a consulta (HTTP {effective}). Verifique o período selecionado."
                        )
                    elif payload.get("success") is False or error:
                        raise contract.ComexStatError(
                            "O Comex Stat recusou os parâmetros da consulta. Verifique o período selecionado."
                        )
                    else:
                        return payload
            if rate_limited:
                can_retry = attempt < self.rate_limit_attempts
            else:
                transient_failures += 1
                can_retry = transient_failures < self.max_attempts and attempt < attempt_limit
            if not can_retry:
                raise transient
            previous_error = transient
            if self.pause.remaining() == 0:
                if wait_budget < 2:
                    raise transient
                self._notify("Aguardando o Comex Stat · reconectando em 2 s")
                self._sleep(2)
                wait_budget -= 2
        raise contract.ComexStatError("A consulta não foi concluída.")

    def latest_published_period(self):
        data = self.request_json("GET", "/general/dates/updated").get("data")
        if not isinstance(data, dict):
            raise contract.ComexStatError("Metadados de publicação inválidos.")
        try:
            period = contract.validate_period(
                f"{data.get('year', '')}-{str(data.get('monthNumber', '')).zfill(2)}"
            )
        except (ValueError, ArgumentTypeError) as exc:
            raise contract.ComexStatError("Mês de publicação inválido.") from exc
        return period, data.get("updated")

    def _query(self, ncms, start, end, *, municipal):
        if isinstance(ncms, (str, bytes)):
            raise ValueError("Informe uma sequência de NCMs.")
        codes = {contract.normalize_ncm(code) for code in ncms}
        if None in codes or not codes or len(codes) > 200:
            raise ValueError("Informe entre 1 e 200 NCMs válidos.")
        start, end = contract.validate_period(start), contract.validate_period(end)
        if not "1997-01" <= start <= end:
            raise ValueError("Período inválido.")
        if municipal:
            codes = {code[:4] for code in codes}
        self._notify("Baixando a base municipal" if municipal else "Baixando a base geral")
        body = {
            "flow": "import",
            "monthDetail": True,
            "filters": [
                {
                    "filter": "heading" if municipal else "ncm",
                    "values": sorted(codes) if municipal else sorted(map(int, codes)),
                }
            ],
            "details": list(contract.MUNICIPAL_DETAILS if municipal else contract.DEFAULT_DETAILS),
            "metrics": list(contract.MUNICIPAL_METRICS if municipal else contract.DEFAULT_METRICS),
        }
        path = "/cities?language=pt" if municipal else "/general?language=pt"
        validate = contract.validate_municipal_api_row if municipal else contract.validate_api_row
        identity = contract.municipal_row_identity if municipal else contract.api_row_identity
        signature = (
            contract.municipal_metric_signature if municipal else contract.api_metric_signature
        )
        unique = {}
        # The source returned an empty cross-year interval containing a known
        # nonempty month. Keep each request inside one calendar year, including
        # partial first/last years, without gaps or overlaps.
        for year in range(int(start[:4]), int(end[:4]) + 1):
            self._check()
            window_start, window_end = max(start, f"{year:04d}-01"), min(end, f"{year:04d}-12")
            body["period"] = {"from": window_start, "to": window_end}
            payload = self.request_json("POST", path, body)
            data = payload.get("data")
            rows = data.get("list") if isinstance(data, dict) else None
            if not isinstance(rows, list):
                raise contract.ComexStatError("A resposta não contém uma lista de registros válida.")
            for index, row in enumerate(rows):
                if index % 256 == 0:
                    self._check()
                if not isinstance(row, dict):
                    raise contract.ComexStatError("A API retornou um registro inválido.")
                validate(row, codes, window_start, window_end, f"registro {index + 1}")
                key = identity(row)
                previous = unique.get(key)
                if previous is not None and signature(previous) != signature(row):
                    raise contract.ComexStatError(
                        "A API retornou registros duplicados com valores divergentes."
                    )
                unique[key] = row
        self._notify("Base municipal validada" if municipal else "Base geral validada", 1.0)
        return list(unique.values())

    def query_imports(self, ncms, start_period, end_period, chunk_size=50):
        return self._query(ncms, start_period, end_period, municipal=False)

    def query_municipal_imports(self, ncms, start_period, end_period, chunk_size=50):
        return self._query(ncms, start_period, end_period, municipal=True)
