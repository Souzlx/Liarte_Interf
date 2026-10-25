"""Compila em área temporária e só publica um Setup novo após validar o resultado."""

from __future__ import annotations

import ast
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
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


def validate_portable_bundle(
    bundle: Path, version: str, *, allow_installer_files: bool = False
) -> Path:
    """Require the exact verified portable build before collecting it into Setup.

    This is a byte-integrity and build-result check. It does not authenticate a
    bundle supplied by an untrusted party or replace the native smoke itself.
    """
    bundle = Path(bundle).resolve()
    if not bundle.is_dir():
        raise RuntimeError("A pasta portátil não existe.")
    files = {}
    for path in bundle.rglob("*"):
        if path.is_symlink():
            raise RuntimeError("A pasta portátil contém um link simbólico.")
        if path.is_file():
            files[path.relative_to(bundle).as_posix()] = path
    manifest_name = "CHECKSUMS_SHA256.txt"
    if not {manifest_name, "AUTOTESTE.json", "LIARTE_Desktop.exe"} <= files.keys():
        raise RuntimeError("Executável, autoteste ou manifesto da pasta portátil ausente.")
    listed = {}
    for line in files[manifest_name].read_text(encoding="utf-8").splitlines():
        digest, separator, name = line.partition("  ")
        relative = PurePosixPath(name)
        if (
            not separator
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
            or not name
            or "\\" in name
            or relative.is_absolute()
            or ".." in relative.parts
            or relative.as_posix() != name
            or name == manifest_name
            or name in listed
        ):
            raise RuntimeError("O manifesto da pasta portátil é inválido.")
        listed[name] = digest
    extras = set(files) - set(listed) - {manifest_name}
    if allow_installer_files:
        extras = {
            name for name in extras if not re.fullmatch(r"unins[0-9]{3}\.(exe|dat|msg)", name, re.I)
        }
    if set(listed) - set(files) or extras:
        raise RuntimeError("Há arquivos ausentes ou não listados no manifesto.")
    for name, expected in listed.items():
        actual = hashlib.sha256()
        with files[name].open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                actual.update(block)
        if actual.hexdigest() != expected:
            raise RuntimeError("Checksum divergente na pasta portátil: " + name)
    try:
        smoke = json.loads(files["AUTOTESTE.json"].read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise RuntimeError("O autoteste da pasta portátil é inválido.") from exc
    if not isinstance(smoke, dict) or not (
        smoke.get("status") == "ok"
        and smoke.get("version") == version
        and smoke.get("platform") == "win32"
        and smoke.get("frozen") is True
        and smoke.get("qml_warnings") == []
    ):
        raise RuntimeError("O executável desta versão ainda não passou na validação nativa.")
    return bundle


def compile_installer(
    bundle: Path,
    destination: Path,
    *,
    compiler: Path,
    version: str,
    root: Path = ROOT,
) -> Path:
    """Compile one verified bundle; a failed compiler keeps the prior Setup."""
    name = installer_name(version)
    bundle = Path(bundle).resolve()
    destination = Path(destination).resolve()
    if destination == bundle or bundle in destination.parents:
        raise RuntimeError("A saída do instalador deve ficar fora da pasta portátil.")
    bundle = validate_portable_bundle(bundle, version)
    environment = child_environment()
    destination.mkdir(parents=True, exist_ok=True)
    # Nunca aceitar um EXE antigo deixado pela compilação de outra versão.
    # A área fica no mesmo volume; falha do compilador preserva o Setup anterior.
    with tempfile.TemporaryDirectory(prefix=".setup-", dir=destination) as temporary:
        staging = Path(temporary)
        # A separate TI build may replace the supplied portable folder while
        # ISCC is collecting files. Freeze its complete input before compilation
        # and validate that copy, including rejecting symlinks introduced during
        # copying. The compiler never reads from the caller's mutable directory.
        frozen_bundle = staging / "portable"
        shutil.copytree(bundle, frozen_bundle, symlinks=True)
        validate_portable_bundle(frozen_bundle, version)
        subprocess.run(
            [
                str(compiler),
                "/Qp",
                f"/DAppVersion={version}",
                f"/DBundleDir={frozen_bundle}",
                f"/O{staging}",
                f"/F{Path(name).stem}",
                str(root / "INSTALADOR_LIARTE.iss"),
            ],
            cwd=root,
            env=environment,
            check=True,
            timeout=600,
        )
        artifact = staging / name
        validate_installer(artifact)
        os.replace(artifact, destination / name)
    return destination / name


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bundle", type=Path, help="Reutiliza uma pasta portátil já compilada e validada."
    )
    parser.add_argument(
        "--output", type=Path, help="Diretório de saída; padrão: instalador/ no projeto."
    )
    args = parser.parse_args(argv)
    if sys.platform != "win32":
        raise SystemExit("O instalador Windows deve ser compilado no Windows.")
    compiler = installer_compiler()
    version = release_version(ROOT)
    if args.bundle is None:
        subprocess.run(
            [sys.executable, str(ROOT / "tools/build_windows.py")],
            cwd=ROOT,
            env=child_environment(),
            check=True,
            timeout=1800,
        )
    result = compile_installer(
        args.bundle or ROOT / "dist/LIARTE_Desktop",
        args.output or ROOT / "instalador",
        compiler=compiler,
        version=version,
        root=ROOT,
    )
    print("Instalador pronto: " + str(result))
    print("SHA256: " + validate_installer(result))


if __name__ == "__main__":
    main()
