"""Seleção TLS do Windows e recusas HTTPS reais em servidor local efêmero."""

from __future__ import annotations

import ssl
import subprocess
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from liarte_engine import secure_http
from liarte_core.comex_open_data import OfficialFiles, OpenDataError


class SecureHttpTests(unittest.TestCase):
    def tearDown(self):
        secure_http.client_context.cache_clear()
        secure_http._origin_opener.cache_clear()

    def test_windows_uses_native_verification_without_global_ssl_injection(self):
        original = ssl.SSLContext
        context = ssl.create_default_context()
        calls = []

        def native(protocol):
            calls.append(protocol)
            return context

        with (
            patch.object(secure_http.sys, "platform", "win32"),
            patch.dict("sys.modules", truststore=SimpleNamespace(SSLContext=native)),
        ):
            result = secure_http.client_context()
            self.assertIs(result, context)
            self.assertEqual(calls, [ssl.PROTOCOL_TLS_CLIENT])
            self.assertTrue(result.check_hostname)
            self.assertEqual(result.verify_mode, ssl.CERT_REQUIRED)
            self.assertGreaterEqual(result.minimum_version, ssl.TLSVersion.TLSv1_2)
            self.assertEqual(secure_http.verify_transport()["policy"], secure_http.TLS_POLICY)
            self.assertIs(ssl.SSLContext, original)

    def test_missing_windows_dependency_never_falls_back_to_unverified_tls(self):
        with (
            patch.object(secure_http.sys, "platform", "win32"),
            patch.dict("sys.modules", truststore=None),
            patch.object(secure_http.urllib.request, "urlopen") as network,
            self.assertRaisesRegex(secure_http.SecureTransportError, "INICIAR_DESKTOP"),
        ):
            secure_http.urlopen("https://example.invalid", timeout=1)
        network.assert_not_called()

    def test_secure_handlers_preserve_no_proxy_and_redirect_policy(self):
        from liarte_engine.comex_gateway_client import NoRedirect

        context = ssl.create_default_context()
        with (
            patch.object(secure_http.sys, "platform", "win32"),
            patch.object(secure_http, "client_context", return_value=context),
        ):
            redirect = NoRedirect()
            opener = secure_http.build_opener(urllib.request.ProxyHandler({}), redirect)
        self.assertIn(redirect, opener.handlers)
        self.assertFalse(any(isinstance(h, urllib.request.ProxyHandler) for h in opener.handlers))
        self.assertEqual(
            sum(isinstance(h, urllib.request.HTTPSHandler) for h in opener.handlers), 1
        )

    def test_non_windows_keeps_the_standard_urlopen_contract(self):
        with (
            patch.object(secure_http.sys, "platform", "linux"),
            patch.object(secure_http.urllib.request, "urlopen", return_value="response") as opener,
        ):
            self.assertEqual(secure_http.urlopen("https://example.invalid", timeout=7), "response")
            opener.assert_called_once_with("https://example.invalid", timeout=7)

    def test_certificate_failure_is_distinct_from_http_status_and_plain_text(self):
        failure = ssl.SSLCertVerificationError(1, "unable to get local issuer certificate")
        self.assertTrue(secure_http.certificate_failure(urllib.error.URLError(failure)))
        self.assertFalse(
            secure_http.certificate_failure(urllib.error.URLError("CERTIFICATE_VERIFY_FAILED"))
        )
        error = urllib.error.HTTPError("https://x", 429, "", {}, None)
        try:
            self.assertFalse(secure_http.certificate_failure(error))
        finally:
            error.close()
        self.assertFalse(secure_http.certificate_failure(TimeoutError()))

    def test_tls_failure_preserves_the_previous_file_and_records_its_actual_kind(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tabelas" / "PAIS.csv"
            path.parent.mkdir()
            path.write_bytes(b"previous verified content")
            error = urllib.error.URLError(ssl.SSLCertVerificationError(1, "unknown issuer"))
            files = OfficialFiles(directory, opener=lambda *a, **k: (_ for _ in ()).throw(error))
            with self.assertRaisesRegex(OpenDataError, "certificado HTTPS"):
                files.fetch("tabelas/PAIS.csv", check=lambda: None, notify=lambda *a: None)
            self.assertEqual(path.read_bytes(), b"previous verified content")
            self.assertEqual(
                files._manifest(path.with_suffix(".csv.json"))["failure_kind"], "TLS_CERTIFICATE"
            )
            self.assertFalse(list(Path(directory).rglob("*.part")))


class LocalHttpsTests(unittest.TestCase):
    """Sem rede pública: certificado não confiável e nome divergente são rejeitados."""

    @classmethod
    def setUpClass(cls):
        import shutil

        if not shutil.which("openssl"):
            raise unittest.SkipTest("OpenSSL CLI ausente; ensaio HTTPS local indisponível")
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.key, cls.cert = cls.root / "key.pem", cls.root / "cert.pem"
        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-days",
                "1",
                "-subj",
                "/CN=localhost",
                "-addext",
                "subjectAltName=DNS:localhost",
                "-keyout",
                str(cls.key),
                "-out",
                str(cls.cert),
            ],
            check=True,
            capture_output=True,
            timeout=15,
        )

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                payload = b"validated HTTPS"
                self.send_response(200)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cls.cert, cls.key)
        cls.server.socket = context.wrap_socket(cls.server.socket, server_side=True)
        cls.thread = threading.Thread(
            target=cls.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
        )
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        cls.temp.cleanup()

    def tearDown(self):
        secure_http.client_context.cache_clear()
        secure_http._origin_opener.cache_clear()

    def opener(self, *, trust):
        context = ssl.create_default_context()
        if trust:
            context.load_verify_locations(cafile=str(self.cert))
        with (
            patch.object(secure_http.sys, "platform", "win32"),
            patch.object(secure_http, "client_context", return_value=context),
        ):
            return secure_http.build_opener(urllib.request.ProxyHandler({}))

    def test_valid_trusted_local_certificate_can_be_read(self):
        with self.opener(trust=True).open(
            f"https://localhost:{self.server.server_port}", timeout=2
        ) as reply:
            self.assertEqual(reply.read(), b"validated HTTPS")

    def test_unknown_issuer_is_actually_rejected_during_tls_handshake(self):
        with self.assertRaises(urllib.error.URLError) as failure:
            self.opener(trust=False).open(f"https://localhost:{self.server.server_port}", timeout=2)
        self.assertTrue(secure_http.certificate_failure(failure.exception))

    def test_wrong_hostname_is_rejected_even_when_issuer_is_trusted(self):
        with self.assertRaises(urllib.error.URLError) as failure:
            self.opener(trust=True).open(f"https://127.0.0.1:{self.server.server_port}", timeout=2)
        self.assertTrue(secure_http.certificate_failure(failure.exception))
