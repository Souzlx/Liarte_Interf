"""Gera e verifica a pasta portátil; a homologação de uso ocorre no Windows."""

from __future__ import annotations

import hashlib
import os
from importlib import metadata
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent


def publish_bundle(bundle: Path, destination: Path):
    destination.parent.mkdir(exist_ok=True)
    backup = None
    if destination.exists():
        backup = destination.with_name(
            destination.name + "_anterior_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        )
        destination.rename(backup)
    try:
        shutil.move(str(bundle), str(destination))
    except Exception:
        if backup is not None:
            if destination.exists():
                incomplete = destination.with_name(
                    destination.name + "_incompleto_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                )
                destination.rename(incomplete)
            backup.rename(destination)
        raise
    return backup


def build_arguments(output: Path, work: Path) -> list[str]:
    assets = ROOT / "src/liarte_desktop/assets"
    args = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--onedir",
        "--name",
        "LIARTE_Desktop",
        "--paths",
        str(ROOT / "src"),
        "--additional-hooks-dir",
        str(ROOT / "tools/hooks"),
        "--icon",
        str(assets / "liarte.ico"),
        "--distpath",
        str(output),
        "--workpath",
        str(work / "work"),
        "--specpath",
        str(work),
    ]
    for source, destination in (
        (ROOT / "src/liarte_desktop/qml", "liarte_desktop/qml"),
        (assets, "liarte_desktop/assets"),
        (ROOT / "src/liarte_core/catalog.json", "liarte_core"),
        (ROOT / "src/liarte_core/data", "liarte_core/data"),
    ):
        args += [
            "--add-data",
            str(source) + (";" if sys.platform == "win32" else ":") + destination,
        ]
    for module in (
        "PySide6.QtCharts",
        "PySide6.QtGraphs",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineQuick",
        "PySide6.QtWebEngineWidgets",
        "PyQt5",
        "PyQt6",
        "PySide2",
        "matplotlib",
        "scipy",
        "IPython",
        "tkinter",
        "_tkinter",
    ):
        args += ["--exclude-module", module]
    for package in ("pbixray", "xpress8", "xpress9", "xmhuffman", "apsw", "truststore"):
        args += ["--collect-all", package]
    if sys.platform == "win32":
        args += ["--version-file", str(ROOT / "versao_windows.txt")]
    return args + [str(ROOT / "iniciar.py")]


def write_notices(destination: Path):
    destination.mkdir(parents=True)
    for name in (
        "PySide6-Essentials",
        "shiboken6",
        "pyinstaller",
        "pyinstaller-hooks-contrib",
        "openpyxl",
        "et-xmlfile",
        "reportlab",
        "pypdf",
        "pillow",
        "charset-normalizer",
        "pbixray",
        "xpress8",
        "xpress9",
        "xmhuffman",
        "kaitaistruct",
        "numpy",
        "pandas",
        "apsw",
        "python-dateutil",
        "six",
        "pytz",
        "tzdata",
        "waitress",
        "truststore",
    ):
        dist = metadata.distribution(name)
        directory = destination / dist.metadata["Name"]
        directory.mkdir()
        (directory / "METADATA.txt").write_text(
            dist.read_text("METADATA") or str(dist.metadata), encoding="utf-8"
        )
        for file in dist.files or ():
            if any(v in file.name.lower() for v in ("license", "licence", "copying", "notice")):
                source = Path(dist.locate_file(file))
                if source.is_file():
                    target = directory / (
                        hashlib.sha256(str(file).encode()).hexdigest()[:10] + "_" + file.name
                    )
                    shutil.copy2(source, target)
    source = ROOT / "third_party"
    for name in ("LGPL-3.0.txt", "GPL-2.0.txt", "GPL-3.0.txt"):
        if not (source / name).is_file():
            raise RuntimeError("Texto de licença ausente: " + name)
    shutil.copytree(source, destination / "textos", dirs_exist_ok=True)
    bases = {Path(sys.base_prefix), Path(sys.base_exec_prefix)}
    if getattr(sys, "_base_executable", None):
        bases.add(Path(sys._base_executable).parent)
    for base in bases:
        for name in ("LICENSE.txt", "LICENSE", "LICENSE.rst"):
            source = base / name
            if source.is_file():
                shutil.copy2(source, destination / "PYTHON_LICENSE.txt")
                return
    # Some Python distributions do not install LICENSE beside the executable.
    # Keep vendor-original, version-specific PSF texts as an auditable fallback.
    fallback = (
        ROOT
        / "third_party"
        / f"PYTHON_LICENSE_{sys.version_info.major}.{sys.version_info.minor}.txt"
    )
    if fallback.is_file():
        shutil.copy2(fallback, destination / "PYTHON_LICENSE.txt")
        return
    raise RuntimeError("Licença do Python não encontrada; o pacote não será publicado.")


def main():
    if sys.platform != "win32":
        raise SystemExit("A compilação do executável Windows deve ser realizada no Windows.")
    sys.path.insert(0, str(ROOT / "src"))
    from liarte_core.inventory_assets import bundled_inventory_path, verify_bundled_inventory

    verify_bundled_inventory(bundled_inventory_path())
    subprocess.run(
        [sys.executable, str(ROOT / "verificar.py"), "--headless", "--volume"],
        cwd=ROOT,
        check=True,
        # The full suite includes real Qt, local servers and subprocesses. On
        # Windows/Python 3.14 reached test 581 of 587 at 297 s on the hosted runner.
        timeout=600,
    )
    with tempfile.TemporaryDirectory(prefix=".desktop-build-", dir=ROOT) as temp:
        stage = Path(temp)
        subprocess.run(build_arguments(stage / "dist", stage), cwd=ROOT, check=True, timeout=1200)
        bundle = stage / "dist/LIARTE_Desktop"
        write_notices(bundle / "LICENCAS")
        result = stage / "frozen-smoke.json"
        subprocess.run(
            [str(bundle / "LIARTE_Desktop.exe"), "--smoke-test", str(result)],
            cwd=bundle,
            check=True,
            timeout=40,
            env=dict(
                os.environ,
                LIARTE_STARTUP_PROBE="1",
                LIARTE_STARTUP_LOG=str(ROOT / "logs/preparacao-desktop.log"),
            ),
        )
        import json

        if json.loads(result.read_text(encoding="utf-8")).get("status") != "ok":
            raise RuntimeError("O executável não passou no autoteste de recursos e consulta Qt.")
        shutil.copy2(result, bundle / "AUTOTESTE.json")
        shutil.copy2(ROOT / "LEIA_PRIMEIRO.txt", bundle / "LEIA_PRIMEIRO.txt")
        files = sorted(p for p in bundle.rglob("*") if p.is_file())
        (bundle / "CHECKSUMS_SHA256.txt").write_text(
            "".join(
                hashlib.sha256(p.read_bytes()).hexdigest()
                + "  "
                + p.relative_to(bundle).as_posix()
                + "\n"
                for p in files
            ),
            encoding="utf-8",
        )
        destination = ROOT / "dist/LIARTE_Desktop"
        publish_bundle(bundle, destination)
        print("Executável: " + str(destination / "LIARTE_Desktop.exe"))


if __name__ == "__main__":
    main()
