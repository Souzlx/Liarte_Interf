"""TLS restrito às conexões LIARTE, com confiança nativa no Windows.

CryptoAPI pode montar cadeias com intermediárias ausentes usando as políticas
do Windows. Certificados e nomes continuam obrigatórios. Não modifica ssl
globalmente, o repositório de certificados ou o comportamento de outros apps.
"""

from __future__ import annotations

import ssl
import sys
import urllib.request
from functools import lru_cache

TLS_POLICY = "windows-cryptoapi-v1"


class SecureTransportError(OSError):
    """Ambiente incompleto; nunca autoriza conexão sem certificado válido."""


@lru_cache(maxsize=1)
def client_context():
    if sys.platform == "win32":
        try:
            import truststore
        except ImportError as exc:
            repair = (
                "Reinstale a versão atual do aplicativo."
                if getattr(sys, "frozen", False)
                else "Abra INICIAR_DESKTOP.cmd para preparar esta versão do aplicativo."
            )
            raise SecureTransportError(
                "A validação de certificados do Windows não está disponível. " + repair
            ) from exc
        context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    else:
        context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.verify_mode = ssl.CERT_REQUIRED
    context.check_hostname = True
    context.set_alpn_protocols(["http/1.1"])
    return context


def build_opener(*handlers):
    """Preserva os handlers de proxy e redirecionamento de cada consumidor."""
    if sys.platform == "win32":
        handlers = (*handlers, urllib.request.HTTPSHandler(context=client_context()))
    return urllib.request.build_opener(*handlers)


def urlopen(request, *, timeout):
    # Linux/macOS conservam o transporte padrão e seus certificados de sistema.
    if sys.platform != "win32":
        return urllib.request.urlopen(request, timeout=timeout)
    return _origin_opener().open(request, timeout=timeout)


@lru_cache(maxsize=1)
def _origin_opener():
    return build_opener()


def certificate_failure(error):
    """Identifica a causa real de URLError sem confundi-la com HTTP 429/503."""
    current, visited = error, set()
    for _ in range(8):
        if id(current) in visited:
            break
        visited.add(id(current))
        if isinstance(current, ssl.SSLCertVerificationError):
            return True
        current = getattr(current, "reason", None) or getattr(current, "__cause__", None)
        if current is None:
            break
    return False


def verify_transport():
    """Verificação de empacotamento, sem DNS nem acesso à internet."""
    context = client_context()
    if not context.check_hostname or context.verify_mode != ssl.CERT_REQUIRED:
        raise SecureTransportError("A verificação de segurança HTTPS não está ativa.")
    return {"policy": TLS_POLICY if sys.platform == "win32" else "system-openssl-v1"}
