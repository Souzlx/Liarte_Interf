"""Compila em área temporária e só publica um Setup novo após validar o resultado."""

from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools.preparation import child_environment  # noqa: E402 - execução direta pela TI


def release_version(root: Path = ROOT) -> str:
    """Lê o literal do aplicativo sem importar Qt ou executar código de projeto."""
    tree = ast.parse((root / "src/liarte_desktop/__init__.py").read_text(encoding="utf-8"))
    for statement in tree.body:
        if isinstance(statement, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "__version__"
            for target in statement.targets
        ):
            version = ast.literal_eval(statement.value)
            if isinstance(version, str) and re.fullmatch(r"\d+\.\d+\.\d+(?:-rc\.\d+)?", version):
                return version
    raise RuntimeError("A versão do aplicativo não é válida para gerar o instalador.")


def installer_name(version: str) -> str:
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-rc\.\d+)?", version):
        raise ValueError("Versão inválida do instalador.")
    return f"LIARTE_Desktop_{version}_Setup.exe"


def installer_compiler() -> Path:
    configured = os.environ.get("LIARTE_ISCC")
    if configured:
        configured_path = Path(configured)
        if configured_path.is_file():
            return configured_path
        raise RuntimeError("O compilador configurado em LIARTE_ISCC não foi encontrado.")
    candidates = []
    found = shutil.which("ISCC.exe")
    if found:
        candidates.append(Path(found))
    for variable in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        directory = os.environ.get(variable)
        if directory:
            candidates.extend(
                (
                    Path(directory) / "Inno Setup 6/ISCC.exe",
                    Path(directory) / "Programs/Inno Setup 6/ISCC.exe",
                )
            )
    for path in candidates:
        if path.is_file():
            return path
    raise RuntimeError(
        "Para criar o instalador, instale o Inno Setup 6.3 ou superior obtido em "
        "https://jrsoftware.org/isdl.php. Isso é necessário somente na máquina da TI. "
        "Quem receber o Setup não precisa instalar Python, Qt ou Inno Setup."
    )


def validate_installer(path: Path) -> str:
    if not path.is_file() or path.stat().st_size < 1_000_000:
        raise RuntimeError("O compilador não produziu um instalador completo nesta execução.")
    digest = hashlib.sha256()
    with path.open("rb") as source:
        dos = source.read(64)
        if len(dos) != 64 or dos[:2] != b"MZ":
            raise RuntimeError("O arquivo gerado não possui um cabeçalho Windows válido.")
        offset = struct.unpack_from("<I", dos, 60)[0]
        if not 64 <= offset <= path.stat().st_size - 26:
            raise RuntimeError("O cabeçalho do instalador está incompleto.")
        source.seek(offset)
        pe = source.read(26)
        if (
            pe[:4] != b"PE\0\0"
            or struct.unpack_from("<H", pe, 4)[0] not in (0x14C, 0x8664)
            or not 1 <= struct.unpack_from("<H", pe, 6)[0] <= 96
            or struct.unpack_from("<H", pe, 24)[0] not in (0x10B, 0x20B)
        ):
            raise RuntimeError("O arquivo gerado não é um executável Windows válido.")
        source.seek(0)
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    if sys.platform != "win32":
        raise SystemExit("O instalador Windows deve ser compilado no Windows.")
    compiler = installer_compiler()
    version = release_version(ROOT)
    name = installer_name(version)
    environment = child_environment()
    subprocess.run(
        [sys.executable, str(ROOT / "tools/build_windows.py")],
        cwd=ROOT,
        env=environment,
        check=True,
        timeout=1800,
    )
    smoke = json.loads((ROOT / "dist/LIARTE_Desktop/AUTOTESTE.json").read_text(encoding="utf-8"))
    if smoke.get("status") != "ok" or smoke.get("version") != version or smoke.get("qml_warnings"):
        raise RuntimeError("O executável desta versão ainda não passou na validação.")
    destination = ROOT / "instalador"
    destination.mkdir(exist_ok=True)
    # Nunca aceitar um EXE antigo deixado pela compilação de outra versão.
    # A área fica no mesmo volume; falha do compilador preserva o Setup anterior.
    with tempfile.TemporaryDirectory(prefix=".setup-", dir=destination) as temporary:
        staging = Path(temporary)
        subprocess.run(
            [
                str(compiler),
                "/Qp",
                f"/DAppVersion={version}",
                f"/O{staging}",
                f"/F{Path(name).stem}",
                str(ROOT / "INSTALADOR_LIARTE.iss"),
            ],
            cwd=ROOT,
            env=environment,
            check=True,
            timeout=600,
        )
        artifact = staging / name
        checksum = validate_installer(artifact)
        os.replace(artifact, destination / name)
    print("Instalador pronto: " + str(destination / name))
    print("SHA256: " + checksum)


if __name__ == "__main__":
    main()
