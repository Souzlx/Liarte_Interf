"""Real Setup lifecycle gate on a disposable Windows CI account.

This tool refuses accounts with an existing LIARTE installation or profile.
It never executes on an ordinary desktop without the explicit CI flag.
"""

from __future__ import annotations

import argparse
import base64
import ctypes
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import time
from uuid import UUID, uuid4
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools.build_installer import (  # noqa: E402
    installer_compiler,
    installer_name,
    release_version,
    validate_installer,
    validate_portable_bundle,
)

APP_ID = "{67BEFD46-16AD-4EB1-B183-FB8D2A8CA4A2}"
SETTINGS_KEY = r"Software\LIARTE\LIARTE Desktop"
UNINSTALL_KEY = "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\" + APP_ID + "_is1"
BASELINE_VERSION = "5.3.0"
LIFECYCLE_CHECKS = (
    "fresh_install_and_shortcuts",
    "silent_uninstall_preserves_profile_and_exports",
    "upgrade_preserves_directory_settings_stock_backups_exports",
    "explicit_purge_removes_only_profile_and_settings",
)


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def require_disposable_ci(explicit, environment, platform):
    if not (
        explicit
        and platform == "win32"
        and environment.get("GITHUB_ACTIONS") == "true"
        and environment.get("RUNNER_OS") == "Windows"
        and environment.get("RUNNER_ENVIRONMENT") == "github-hosted"
    ):
        raise RuntimeError("O ensaio de instalação exige uma conta Windows descartável do CI.")


def require_pristine_profile(profile, install_directory, shortcuts, *, settings_exist, installed):
    if profile.exists() or install_directory.exists() or settings_exist or installed:
        raise RuntimeError("Já existe uma instalação ou perfil LIARTE; o ensaio foi interrompido.")
    if any(path.exists() for path in shortcuts):
        raise RuntimeError("Já existem atalhos LIARTE; o ensaio foi interrompido.")


def extract_baseline(archive, checksum, destination):
    """Check the published digest and reject escaping/duplicate ZIP paths."""
    filename = Path(archive).name
    entries = [line.split("  ", 1) for line in Path(checksum).read_text().splitlines()]
    expected = next((value for value, name in entries if name == filename), None)
    if expected is None or re.fullmatch(r"[0-9a-f]{64}", expected) is None:
        raise ValueError("O checksum publicado da versão anterior é inválido.")
    if digest(archive) != expected:
        raise ValueError("O pacote da versão anterior diverge do checksum publicado.")
    with zipfile.ZipFile(archive) as packed:
        seen = set()
        if sum(info.file_size for info in packed.infolist()) > 2 * 1024**3:
            raise ValueError("O pacote anterior excede o orçamento do ensaio.")
        for info in packed.infolist():
            path = PurePosixPath(info.filename)
            if (
                path.is_absolute()
                or ".." in path.parts
                or "\\" in info.filename
                or not path.parts
                or path.parts[0] != "LIARTE_Desktop"
                or info.filename.casefold() in seen
                or path.as_posix() != info.filename.rstrip("/")
                or ((info.external_attr >> 16) & 0o170000) == 0o120000
            ):
                raise ValueError("Caminho inválido no pacote da versão anterior.")
            seen.add(info.filename.casefold())
        packed.extractall(destination)
    return validate_portable_bundle(Path(destination) / "LIARTE_Desktop", BASELINE_VERSION)


def known_folder(identifier):
    raw = (ctypes.c_ubyte * 16).from_buffer_copy(UUID(identifier).bytes_le)
    output = ctypes.c_void_p()
    shell = ctypes.WinDLL("shell32", winmode=0x800)
    ole = ctypes.WinDLL("ole32", winmode=0x800)
    function = shell.SHGetKnownFolderPath
    function.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    function.restype = ctypes.c_long
    ole.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    if function(ctypes.byref(raw), 0, None, ctypes.byref(output)) != 0:
        raise OSError("Não foi possível localizar uma pasta de atalhos do Windows.")
    try:
        return Path(ctypes.wstring_at(output))
    finally:
        ole.CoTaskMemFree(output)


def registry_values(key):
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as handle:
            result = {}
            for index in range(winreg.QueryInfoKey(handle)[1]):
                name, value, kind = winreg.EnumValue(handle, index)
                result[name] = (value, kind)
            return result
    except FileNotFoundError:
        return None


def installed_location():
    values = registry_values(UNINSTALL_KEY)
    return (
        Path(values["InstallLocation"][0]).resolve()
        if values and "InstallLocation" in values
        else None
    )


def run_checked(command, *, timeout=180, cwd=None):
    result = subprocess.run(
        [str(value) for value in command], cwd=cwd, timeout=timeout, check=False
    )
    if result.returncode != 0:
        raise RuntimeError(f"O processo de validação terminou com código {result.returncode}.")


def wait_absent(path, *, timeout=20):
    deadline = time.monotonic() + timeout
    while Path(path).exists() and time.monotonic() < deadline:
        time.sleep(0.1)
    if Path(path).exists():
        raise RuntimeError("O Windows não confirmou a remoção do arquivo instalado.")


def install(setup, log, directory=None):
    command = [setup, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", f"/LOG={log}"]
    if directory is not None:
        command.append(f"/DIR={directory}")
    run_checked(command, timeout=240)


def uninstall(directory, log, *, purge=False):
    command = [
        Path(directory) / "unins000.exe",
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        f"/LOG={log}",
    ]
    if purge:
        command.append("/PURGEDATA=1")
    run_checked(command, timeout=180)
    wait_absent(Path(directory) / "LIARTE_Desktop.exe")
    wait_absent(Path(directory) / "unins000.exe")


def check_shortcuts(shortcuts, executable, *, working_directory=True):
    def literal(value):
        return "'" + str(value).replace("'", "''") + "'"

    script = "$ErrorActionPreference='Stop';[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding($false);$shell=New-Object -ComObject WScript.Shell;"
    script += "$items=@(" + ",".join(literal(path) for path in shortcuts) + ");"
    script += "@($items|ForEach-Object{$s=$shell.CreateShortcut($_);[pscustomobject]@{path=$_;target=$s.TargetPath;working=$s.WorkingDirectory}})|ConvertTo-Json -Compress"
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    result = subprocess.run(
        [str(powershell), "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
        capture_output=True,
        check=True,
        timeout=30,
    )
    entries = json.loads(result.stdout.decode("utf-8-sig"))
    if len(entries) != len(shortcuts) or not all(path.is_file() for path in shortcuts):
        raise RuntimeError("Os atalhos da instalação estão ausentes.")
    for entry in entries:
        if Path(entry["target"]).resolve() != Path(executable).resolve() or (
            working_directory
            and Path(entry["working"]).resolve() != Path(executable).parent.resolve()
        ):
            raise RuntimeError("Um atalho aponta para outra instalação.")


def verify_smoke_payload(payload, version):
    if not (
        payload.get("status") == "ok"
        and payload.get("version") == version
        and payload.get("platform") == "win32"
        and payload.get("frozen") is True
        and payload.get("qml_warnings") == []
        and payload.get("themes_checked") == ["light", "dark"]
        and all(
            payload.get("document_resources", {}).get(kind) == "ok"
            for kind in ("excel", "pdf", "powerbi")
        )
        and (
            version == BASELINE_VERSION
            or payload.get("document_resources", {}).get("inventory_backups") == "ok"
        )
    ):
        raise RuntimeError("O aplicativo instalado não passou no autoteste nativo desta versão.")


def smoke_installed(directory, output, version):
    run_checked(
        [Path(directory) / "LIARTE_Desktop.exe", "--smoke-test", output], timeout=60, cwd=directory
    )
    payload = json.loads(Path(output).read_text(encoding="utf-8"))
    verify_smoke_payload(payload, version)
    validate_portable_bundle(directory, version, allow_installer_files=True)
    return payload


def seed_profile(profile, bundle, external):
    import winreg

    token = uuid4().hex
    stock = profile / "estoque/base.liarte"
    stock.parent.mkdir(parents=True, exist_ok=True)
    source = Path(bundle) / "_internal/liarte_core/data/estoque.liarte"
    if not source.is_file():
        raise RuntimeError("A base integrada não foi incluída no aplicativo instalado.")
    shutil.copy2(source, stock)
    backup = profile / "estoque/backups/ci-preservation-marker.txt"
    backup.parent.mkdir()
    backup.write_text(token, encoding="utf-8")
    external.write_text("Relatório exportado do usuário: " + token, encoding="utf-8")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, SETTINGS_KEY) as key:
        winreg.SetValueEx(key, "InstallerSmokeMarker", 0, winreg.REG_SZ, token)
        winreg.SetValueEx(key, "dark", 0, winreg.REG_SZ, "true")
        winreg.SetValueEx(key, "compact", 0, winreg.REG_SZ, "true")
    return {path: digest(path) for path in (stock, backup, external)}, registry_values(SETTINGS_KEY)


def assert_preserved(files, settings):
    if any(not path.is_file() or digest(path) != expected for path, expected in files.items()):
        raise RuntimeError("A instalação alterou a base, backup ou relatório do usuário.")
    if registry_values(SETTINGS_KEY) != settings:
        raise RuntimeError("A instalação alterou as preferências existentes.")


def compile_baseline(archive, checksum, workspace, compiler):
    root = Path(workspace) / "baseline"
    root.mkdir()
    packed = root / "dist"
    packed.mkdir()
    extract_baseline(archive, checksum, packed)
    script = root / "INSTALADOR_LIARTE.iss"
    script.write_bytes(
        subprocess.check_output(["git", "show", "v5.3.0:INSTALADOR_LIARTE.iss"], cwd=ROOT)
    )
    icon = root / "src/liarte_desktop/assets/liarte.ico"
    icon.parent.mkdir(parents=True)
    icon.write_bytes(
        subprocess.check_output(
            ["git", "show", "v5.3.0:src/liarte_desktop/assets/liarte.ico"], cwd=ROOT
        )
    )
    output = root / "output"
    output.mkdir()
    run_checked(
        [compiler, "/Qp", "/DAppVersion=5.3.0", f"/O{output}", "/FBaseline_5.3.0", script],
        timeout=600,
        cwd=root,
    )
    setup = output / "Baseline_5.3.0.exe"
    validate_installer(setup)
    return setup


def prepare_preview_assets(bundle, setup, smoke_report, output):
    """Package only a verified prerelease after the real Setup lifecycle gate."""
    from tools.prepare_release import _publish_release_files

    version = release_version()
    if re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+-rc\.[0-9]+", version) is None:
        raise ValueError("Este fluxo publica somente prévias com sufixo RC.")
    bundle = validate_portable_bundle(Path(bundle), version)
    setup, output = Path(setup).resolve(), Path(output).resolve()
    if output == bundle or bundle in output.parents:
        raise ValueError("A saída da prévia deve ficar fora da pasta portátil.")
    setup_sha = validate_installer(setup)
    smoke = json.loads(Path(smoke_report).read_text(encoding="utf-8"))
    if not (
        setup.name == installer_name(version)
        and smoke.get("version") == version
        and smoke.get("status") == "ok"
        and smoke.get("setup_sha256") == setup_sha
        and isinstance(smoke.get("tests"), dict)
        and all(smoke["tests"].get(key) is True for key in LIFECYCLE_CHECKS)
    ):
        raise ValueError("O Setup não possui um ensaio completo e válido desta versão.")
    for key in ("fresh_installed_smoke", "upgraded_installed_smoke"):
        verify_smoke_payload(smoke.get(key, {}), version)
    names = (f"LIARTE_Desktop_{version}_Windows_x64.zip", setup.name, "SHA256SUMS.txt")
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".preview-", dir=output) as temporary:
        staged = tuple(Path(temporary) / name for name in names)
        with zipfile.ZipFile(staged[0], "w", zipfile.ZIP_DEFLATED, compresslevel=6) as packed:
            for path in sorted(bundle.rglob("*")):
                if path.is_file():
                    packed.write(path, "LIARTE_Desktop/" + path.relative_to(bundle).as_posix())
        shutil.copy2(setup, staged[1])
        if digest(staged[1]) != setup_sha:
            raise ValueError("O Setup mudou durante a preparação da prévia.")
        staged[2].write_text(
            "".join(digest(path) + "  " + path.name + "\n" for path in staged[:2]), encoding="utf-8"
        )
        _publish_release_files(staged, tuple(output / name for name in names))
    return {
        "tag": "v" + version,
        "archive": str(output / names[0]),
        "setup": str(output / names[1]),
        "checksum": str(output / names[2]),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--setup", required=True, type=Path)
    parser.add_argument("--baseline-archive", required=True, type=Path)
    parser.add_argument("--baseline-checksum", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--ci-profile", action="store_true")
    args = parser.parse_args()
    require_disposable_ci(args.ci_profile, os.environ, sys.platform)
    version = release_version()
    setup = args.setup.resolve()
    setup_sha = validate_installer(setup)
    workspace = args.workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=False)
    install_directory = workspace / "installed"
    profile = Path(os.environ["LOCALAPPDATA"]) / "LIARTE/LIARTE Desktop"
    default_directory = Path(os.environ["LOCALAPPDATA"]) / "Programs/LIARTE Desktop"
    shortcuts = (
        known_folder("B4BFCC3A-DB2C-424C-B029-7FE99A87C641") / "LIARTE Desktop.lnk",
        known_folder("A77F5D77-2E2B-44C3-A6A2-ABA601054A51")
        / "LIARTE Desktop/Análise de importações.lnk",
        known_folder("A77F5D77-2E2B-44C3-A6A2-ABA601054A51") / "LIARTE Desktop/Desinstalar.lnk",
    )
    require_pristine_profile(
        profile,
        default_directory,
        shortcuts,
        settings_exist=registry_values(SETTINGS_KEY) is not None,
        installed=registry_values(UNINSTALL_KEY) is not None,
    )
    baseline = compile_baseline(
        args.baseline_archive, args.baseline_checksum, workspace, installer_compiler()
    )
    external = workspace / "relatorio_exportado.txt"
    completed = False
    report = {
        "status": "running",
        "version": version,
        "baseline_version": BASELINE_VERSION,
        "setup_sha256": setup_sha,
        "tests": {},
    }
    try:
        install(setup, workspace / "install-fresh.log", install_directory)
        assert installed_location() == install_directory.resolve()
        check_shortcuts(shortcuts[:2], install_directory / "LIARTE_Desktop.exe")
        check_shortcuts(shortcuts[2:], install_directory / "unins000.exe", working_directory=False)
        report["fresh_installed_smoke"] = smoke_installed(
            install_directory, workspace / "fresh-smoke.json", version
        )
        report["tests"]["fresh_install_and_shortcuts"] = True
        files, settings = seed_profile(profile, install_directory, external)
        uninstall(install_directory, workspace / "uninstall-preserve.log")
        assert_preserved(files, settings)
        assert not any(path.exists() for path in shortcuts)
        assert registry_values(UNINSTALL_KEY) is None
        report["tests"]["silent_uninstall_preserves_profile_and_exports"] = True
        install(baseline, workspace / "install-baseline.log", install_directory)
        assert_preserved(files, settings)
        report["baseline_installed_smoke"] = smoke_installed(
            install_directory, workspace / "baseline-smoke.json", BASELINE_VERSION
        )
        # No /DIR: the new Setup must reuse the installation it finds in HKCU.
        install(setup, workspace / "upgrade.log")
        assert installed_location() == install_directory.resolve()
        assert_preserved(files, settings)
        check_shortcuts(shortcuts[:2], install_directory / "LIARTE_Desktop.exe")
        check_shortcuts(shortcuts[2:], install_directory / "unins000.exe", working_directory=False)
        report["upgraded_installed_smoke"] = smoke_installed(
            install_directory, workspace / "upgraded-smoke.json", version
        )
        assert_preserved(files, settings)
        report["tests"]["upgrade_preserves_directory_settings_stock_backups_exports"] = True
        uninstall(install_directory, workspace / "uninstall-purge.log", purge=True)
        assert not profile.exists() and registry_values(SETTINGS_KEY) is None
        assert not any(path.exists() for path in shortcuts)
        assert external.is_file() and digest(external) == files[external]
        assert registry_values(UNINSTALL_KEY) is None
        report["tests"]["explicit_purge_removes_only_profile_and_settings"] = True
        completed = True
        report["status"] = "ok"
    finally:
        if not completed:
            report["status"] = "failed"
            try:
                location = installed_location()
                if (
                    location in (install_directory.resolve(), default_directory.resolve())
                    and (location / "unins000.exe").is_file()
                ):
                    uninstall(location, workspace / "failure-cleanup.log", purge=True)
            except (OSError, RuntimeError, subprocess.SubprocessError) as error:
                report["cleanup_error"] = str(error)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print("Autoteste do instalador: " + json.dumps(report, ensure_ascii=True, sort_keys=True))


if __name__ == "__main__":
    main()
