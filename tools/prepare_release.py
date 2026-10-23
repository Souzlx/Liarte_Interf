"""Verifica a pasta portátil e prepara os arquivos de uma release estável."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools.build_installer import release_version  # noqa: E402

MANIFEST = "CHECKSUMS_SHA256.txt"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def prepare_release(bundle: Path, output: Path) -> dict[str, str]:
    version = release_version()
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise ValueError("A publicação estável exige uma versão sem sufixo RC.")
    bundle, output = Path(bundle).resolve(), Path(output).resolve()
    if output == bundle or bundle in output.parents:
        raise ValueError("A saída da release deve ficar fora da pasta portátil.")
    if not bundle.is_dir():
        raise ValueError("A pasta portátil não existe.")

    files = {}
    for path in bundle.rglob("*"):
        if path.is_symlink():
            raise ValueError("A pasta portátil contém um link simbólico.")
        if path.is_file():
            files[path.relative_to(bundle).as_posix()] = path
    if not {MANIFEST, "AUTOTESTE.json", "LIARTE_Desktop.exe"} <= files.keys():
        raise ValueError("Executável, autoteste ou manifesto da pasta portátil ausente.")

    listed = {}
    for line in files[MANIFEST].read_text(encoding="utf-8").splitlines():
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
            or name == MANIFEST
            or name in listed
        ):
            raise ValueError("O manifesto da pasta portátil é inválido.")
        listed[name] = digest
    if set(files) != set(listed) | {MANIFEST}:
        raise ValueError("Há arquivos ausentes ou não listados no manifesto.")
    for name, digest in listed.items():
        if sha256(files[name]) != digest:
            raise ValueError("Checksum divergente na pasta portátil: " + name)

    smoke = json.loads(files["AUTOTESTE.json"].read_text(encoding="utf-8"))
    if not isinstance(smoke, dict) or not (
        smoke.get("status") == "ok"
        and smoke.get("version") == version
        and smoke.get("platform") == "win32"
        and smoke.get("frozen") is True
        and smoke.get("qml_warnings") == []
    ):
        raise ValueError("O autoteste não confirma o executável Windows desta versão.")

    output.mkdir(parents=True, exist_ok=True)
    filename = f"LIARTE_Desktop_{version}_Windows_x64.zip"
    archive, checksum = output / filename, output / "SHA256SUMS.txt"
    with tempfile.TemporaryDirectory(prefix=".release-", dir=output) as temporary:
        staged_archive = Path(temporary) / filename
        with zipfile.ZipFile(staged_archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as packed:
            for name, path in sorted(files.items()):
                packed.write(path, "LIARTE_Desktop/" + name)
        staged_checksum = Path(temporary) / checksum.name
        staged_checksum.write_text(sha256(staged_archive) + "  " + filename + "\n", encoding="utf-8")
        os.replace(staged_archive, archive)
        os.replace(staged_checksum, checksum)
    return {
        "tag": "v" + version,
        "title": "LIARTE " + version,
        "archive": str(archive),
        "checksum": str(checksum),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = prepare_release(args.bundle, args.output)
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        if any("\n" in value or "\r" in value for value in result.values()):
            raise ValueError("Os caminhos de saída contêm caracteres inválidos.")
        with Path(github_output).open("a", encoding="utf-8") as destination:
            for key, value in result.items():
                destination.write(f"{key}={value}\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
