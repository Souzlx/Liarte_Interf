"""Preparação serial do ambiente e confirmação de abertura; somente biblioteca padrão."""

from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import subprocess
import shutil
import struct
import sys
import sysconfig
import tempfile
import time
import uuid
import venv

PROBE_SCHEMA = 1
PROBE_MAX_AGE = 7 * 24 * 60 * 60
SUPPORTED_PYTHON = "Python 3.11, 3.12, 3.13 ou 3.14"


def validate_python_runtime():
    """Reject unsupported runtimes before downloading packages or changing files."""
    if not (3, 11) <= sys.version_info[:2] <= (3, 14):
        raise RuntimeError(f"Utilize {SUPPORTED_PYTHON} para preparar este aplicativo.")
    if sys.implementation.name != "cpython" or sysconfig.get_config_var("Py_GIL_DISABLED"):
        raise RuntimeError(f"Utilize a edição padrão do {SUPPORTED_PYTHON}, com GIL.")
    if sys.platform == "win32" and struct.calcsize("P") != 8:
        raise RuntimeError("A versão Windows requer Python de 64 bits.")


def runtime_signature():
    # base_prefix is shared by python/pythonw and by venvs of the same runtime.
    # Comparing executable names would unnecessarily rebuild on every GUI start.
    return {
        "version": list(sys.version_info[:3]),
        "base_prefix": os.path.normcase(str(Path(sys.base_prefix).resolve())),
        "bits": struct.calcsize("P") * 8,
        "implementation": sys.implementation.name,
        "free_threaded": bool(sysconfig.get_config_var("Py_GIL_DISABLED")),
    }


def environment_matches(interpreter: Path, *, creationflags=0):
    if not interpreter.is_file():
        return False
    script = (
        "import json,os,sys,struct,sysconfig;from pathlib import Path;"
        "print(json.dumps({'version':list(sys.version_info[:3]),"
        "'base_prefix':os.path.normcase(str(Path(sys.base_prefix).resolve())),"
        "'bits':struct.calcsize('P')*8,'implementation':sys.implementation.name,"
        "'free_threaded':bool(sysconfig.get_config_var('Py_GIL_DISABLED'))}))"
    )
    try:
        result = subprocess.run(
            [str(interpreter), "-I", "-c", script],
            env=child_environment(),
            capture_output=True,
            text=True,
            timeout=12,
            creationflags=creationflags,
            check=False,
        )
        return result.returncode == 0 and json.loads(result.stdout) == runtime_signature()
    except (OSError, ValueError, subprocess.SubprocessError):
        return False


def ensure_environment(environment: Path, *, creationflags=0):
    """Reuse the selected runtime or rebuild only the generated venv.

    Previous environments remain in a uniquely named sibling folder. If venv
    creation fails, the original is restored. Reports and preferences are never
    stored here and are not touched. Caller holds PreparationLock throughout.
    """
    validate_python_runtime()
    environment = Path(environment)
    is_junction = getattr(environment, "is_junction", lambda: False)
    if environment.is_symlink() or is_junction():
        raise RuntimeError(
            "A pasta do ambiente Python não pode ser um link. Extraia o projeto em uma pasta própria."
        )
    interpreter = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if environment_matches(interpreter, creationflags=creationflags):
        return interpreter, False
    backup = None
    if environment.exists():
        if not environment.is_dir():
            raise RuntimeError(
                "A pasta reservada para o ambiente Python está ocupada por um arquivo."
            )
        backup = environment.with_name(environment.name + ".anterior-" + uuid.uuid4().hex[:12])
        try:
            environment.rename(backup)
        except PermissionError as exc:
            raise RuntimeError(
                "Feche a LIARTE e tente novamente para atualizar o ambiente Python."
            ) from exc
    try:
        venv.EnvBuilder(with_pip=True).create(environment)
        if not environment_matches(interpreter, creationflags=creationflags):
            raise RuntimeError("O novo ambiente Python não passou na verificação. Tente Reparar.")
    except Exception:
        if environment.is_dir():
            shutil.rmtree(environment)
        if backup is not None:
            backup.rename(environment)
        raise
    return interpreter, True


def probe_fingerprint(interpreter: Path, root: Path) -> str:
    """Identifica código, recursos, runtime e requisitos desta preparação.

    A reutilização poupa o autoteste completo em aberturas idênticas. A checagem
    de versões e o sinal de abertura Qt continuam obrigatórios em cada abertura.
    """
    digest = hashlib.sha256()
    runtime = interpreter.stat()
    digest.update(
        json.dumps(
            [
                PROBE_SCHEMA,
                str(interpreter.resolve()),
                runtime.st_size,
                runtime.st_mtime_ns,
                list(sys.version_info[:3]),
                sys.platform,
            ],
            separators=(",", ":"),
        ).encode("utf-8")
    )
    paths = [root / "requirements.txt", root / "requirements-build.txt", root / "iniciar.py"]
    for name in ("src", "tools"):
        paths.extend(
            path
            for path in (root / name).rglob("*")
            if path.is_file()
            and path.suffix.lower() in (".py", ".qml", ".json", ".png", ".ico")
            and "__pycache__" not in path.parts
        )
    for path in sorted(paths):
        digest.update(path.relative_to(root).as_posix().encode("utf-8") + b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def probe_is_current(path: Path, fingerprint: str, *, now: float | None = None) -> bool:
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        verified = report["verified_at"]
        if isinstance(verified, bool) or not isinstance(verified, (int, float)):
            return False
        age = (time.time() if now is None else now) - verified
        return (
            report.get("schema") == PROBE_SCHEMA
            and report.get("fingerprint") == fingerprint
            and 0 <= age < PROBE_MAX_AGE
        )
    except (OSError, ValueError, TypeError, KeyError):
        return False


def save_probe(path: Path, fingerprint: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # PreparationLock serializa gravadores; substituir nunca deixa JSON parcial.
    temporary = path.with_suffix(".tmp")
    try:
        temporary.write_text(
            json.dumps(
                {"schema": PROBE_SCHEMA, "fingerprint": fingerprint, "verified_at": time.time()}
            ),
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def child_environment(**extra):
    environment = dict(os.environ)
    for key in (
        "PYTHONPATH",
        "PYTHONHOME",
        "QT_PLUGIN_PATH",
        "QML_IMPORT_PATH",
        "QML2_IMPORT_PATH",
    ):
        environment.pop(key, None)
    environment.update(extra)
    return environment


class PreparationLock:
    """O sistema operacional libera a trava ao fechar ou terminar o processo."""

    def __init__(self, path: Path):
        self.path = path
        self.file = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open("a+b")
        self.file.seek(0, 2)
        if self.file.tell() == 0:
            self.file.write(b"1")
            self.file.flush()
        self.file.seek(0)
        try:
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.file.close()
            self.file = None
            raise RuntimeError(
                "Outra preparação da LIARTE está em andamento. Aguarde essa janela terminar."
            ) from exc
        return self

    def __exit__(self, *_):
        if self.file is not None:
            self.file.close()
            self.file = None


def launch_verified(command, root, logfile, *, timeout=25, creationflags=0):
    """Só confirma abertura após um sinal do próprio loop de eventos Qt."""
    with tempfile.TemporaryDirectory(prefix="liarte-abertura-") as directory:
        report = Path(directory) / "abertura.json"
        logfile.parent.mkdir(parents=True, exist_ok=True)
        # Pythonw has no console. Keep native Qt errors in the same diagnostic
        # file as Python failures; the child retains its own output handle.
        with logfile.open("a", encoding="utf-8") as output:
            process = subprocess.Popen(
                [*command, "--startup-ready", str(report)],
                cwd=root,
                env=child_environment(LIARTE_STARTUP_LOG=str(logfile), PYTHONIOENCODING="utf-8"),
                creationflags=creationflags,
                stdout=output,
                stderr=subprocess.STDOUT,
            )
        deadline = time.monotonic() + timeout
        try:
            while time.monotonic() < deadline:
                if report.is_file():
                    try:
                        document = json.loads(report.read_text(encoding="utf-8"))
                    except (OSError, ValueError):
                        document = {}
                    if (
                        isinstance(document, dict)
                        and document.get("status") == "ready"
                        and process.poll() is None
                    ):
                        return process
                    if isinstance(document, dict) and document.get("status") == "failed":
                        raise RuntimeError(
                            "A janela não abriu. Consulte o diagnóstico de inicialização."
                        )
                if process.poll() is not None:
                    raise RuntimeError(
                        "A aplicação encerrou durante a abertura. Use Abrir diagnóstico."
                    )
                time.sleep(0.04)
            raise RuntimeError(
                "A aplicação não confirmou a abertura em 25 segundos. Consulte o diagnóstico."
            )
        except Exception:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            raise


def pinned_requirements(root, mode):
    names = (
        ("requirements.txt", "requirements-build.txt") if mode == "build" else ("requirements.txt",)
    )
    pins = {}
    for name in names:
        for line in (root / name).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith(("#", "-r ")):
                continue
            package, version = line.split("==", 1)
            pins[package] = version
    return pins


def requirements_satisfied(interpreter, root, mode, creationflags=0):
    try:
        pins = pinned_requirements(root, mode)
        script = "import importlib.metadata as m,json,sys; pins=json.loads(sys.argv[1]); print(json.dumps({k:m.version(k) for k in pins}))"
        result = subprocess.run(
            [str(interpreter), "-I", "-c", script, json.dumps(pins)],
            cwd=root,
            env=child_environment(),
            capture_output=True,
            text=True,
            timeout=12,
            creationflags=creationflags,
        )
        return result.returncode == 0 and json.loads(result.stdout) == pins
    except (OSError, ValueError, subprocess.SubprocessError):
        return False
