"""Assistente em português para preparar o aplicativo em ambiente Python isolado."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tempfile
import traceback
import tkinter as tk
from tkinter import messagebox, ttk

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools.preparation import (  # noqa: E402 - execução direta do assistente fora do pacote
    PreparationLock,
    child_environment,
    launch_verified,
    probe_fingerprint,
    probe_is_current,
    requirements_satisfied,
    ensure_environment,
    validate_python_runtime,
    save_probe,
)

ENVIRONMENT = ROOT / ".liarte-desktop-env"
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def install_dependencies(interpreter: Path, mode: str, logfile: Path, *, repair=False):
    requirement = ROOT / ("requirements-build.txt" if mode == "build" else "requirements.txt")
    command = [str(interpreter), "-m", "pip", "install", "--disable-pip-version-check"]
    if repair:
        command += ["--force-reinstall", "--no-cache-dir"]
    command += ["-r", str(requirement)]
    with logfile.open("a", encoding="utf-8") as output:
        result = subprocess.run(
            command,
            cwd=ROOT,
            stdout=output,
            stderr=subprocess.STDOUT,
            timeout=600,
            creationflags=CREATE_NO_WINDOW,
            env=child_environment(),
        )
    if result.returncode:
        raise RuntimeError(f"Não foi possível preparar as dependências. Consulte {logfile}.")


def check_interface(interpreter: Path, logfile: Path) -> bool:
    """Executa o aplicativo completo, nos dois temas, no mesmo ambiente instalado.

    O processo separado evita contaminar o assistente Tk com Qt e permite
    reinstalação segura após uma falha, sem DLLs Qt abertas no próprio assistente.
    """
    environment = child_environment(
        QT_QPA_PLATFORM="offscreen",
        QT_QUICK_BACKEND="software",
        LIARTE_STARTUP_PROBE="1",
        LIARTE_STARTUP_LOG=str(logfile),
    )
    with tempfile.TemporaryDirectory(prefix="liarte-qt-") as directory:
        result_file = Path(directory) / "resultado.json"
        with logfile.open("a", encoding="utf-8") as output:
            try:
                process = subprocess.run(
                    [str(interpreter), str(ROOT / "iniciar.py"), "--smoke-test", str(result_file)],
                    cwd=ROOT,
                    env=environment,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    timeout=40,
                    creationflags=CREATE_NO_WINDOW,
                )
            except subprocess.TimeoutExpired:
                output.write("\nO teste Qt excedeu 40 segundos.\n")
                (logfile.parent / "validacao-qt.json").write_text(
                    json.dumps({"status": "failed", "reason": "timeout", "seconds": 40}),
                    encoding="utf-8",
                )
                return False
        try:
            document = json.loads(result_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            (logfile.parent / "validacao-qt.json").write_text(
                json.dumps(
                    {
                        "status": "failed",
                        "reason": "no_valid_report",
                        "exit_code": process.returncode,
                    }
                ),
                encoding="utf-8",
            )
            return False
        (logfile.parent / "validacao-qt.json").write_text(
            json.dumps(document, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return (
            isinstance(document, dict)
            and process.returncode == 0
            and document.get("status") == "ok"
            and not document.get("qml_warnings")
            and document.get("themes_checked") == ["light", "dark"]
        )


def _prepare(mode: str, events: queue.Queue, *, repair=False):
    logfile = ROOT / "logs/preparacao-desktop.log"
    stamp = ROOT / "logs/ambiente-verificado.json"
    try:
        if mode not in ("run", "build", "installer"):
            raise ValueError("Opção de preparação inválida.")
        validate_python_runtime()
        if mode == "installer":
            # Detectar uma ferramenta ausente antes de baixar ou compilar tudo.
            from tools.build_installer import installer_compiler

            events.put(("phase", {"step": 1, "label": "Conferindo as ferramentas de instalação…"}))
            installer_compiler()
        events.put(("phase", {"step": 1, "label": "Preparando o aplicativo…"}))
        events.put(("status", "Preparando o ambiente isolado do aplicativo…"))
        interpreter, recreated = ensure_environment(ENVIRONMENT, creationflags=CREATE_NO_WINDOW)
        logs = ROOT / "logs"
        logs.mkdir(exist_ok=True)
        logfile = logs / "preparacao-desktop.log"
        events.put(("status", "Conferindo Python e Qt. A primeira preparação precisa de internet…"))
        installed = (
            repair
            or recreated
            or not requirements_satisfied(
                interpreter, ROOT, "build" if mode == "installer" else mode, CREATE_NO_WINDOW
            )
        )
        if installed:
            stamp.unlink(missing_ok=True)
            install_dependencies(
                interpreter, "build" if mode == "installer" else mode, logfile, repair=repair
            )
        fingerprint = probe_fingerprint(interpreter, ROOT)
        reusable = mode == "run" and not installed and probe_is_current(stamp, fingerprint)
        events.put(("phase", {"step": 2, "label": "Verificando o aplicativo…"}))
        events.put(
            (
                "status",
                "Conferindo a verificação recente…"
                if reusable
                else "Testando a interface e os documentos…",
            )
        )
        verified = reusable or check_interface(interpreter, logfile)
        if not verified and not repair:
            stamp.unlink(missing_ok=True)
            events.put(("status", "Reparando o Qt no ambiente isolado e repetindo a verificação…"))
            install_dependencies(
                interpreter, "build" if mode == "installer" else mode, logfile, repair=True
            )
            verified = check_interface(interpreter, logfile)
        if not verified:
            raise RuntimeError(
                "A interface Qt não passou na verificação de inicialização. "
                "O reparo do ambiente não resolveu o carregamento. "
                "Use Abrir diagnóstico para consultar o erro detalhado."
            )
        if not reusable:
            try:
                save_probe(stamp, fingerprint)
            except OSError:
                # A otimização é opcional; uma abertura válida não depende dela.
                with logfile.open("a", encoding="utf-8") as output:
                    output.write("\nNão foi possível guardar a verificação recente.\n")
        if mode in ("build", "installer"):
            events.put(("phase", {"step": 3, "label": "Criando a distribuição…"}))
            events.put(
                (
                    "status",
                    "Verificando o projeto e compilando o executável. Isso pode levar alguns minutos…",
                )
            )
            with logfile.open("a", encoding="utf-8") as output:
                result = subprocess.run(
                    [
                        str(interpreter),
                        str(
                            ROOT
                            / "tools"
                            / ("build_installer.py" if mode == "installer" else "build_windows.py")
                        ),
                    ],
                    cwd=ROOT,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    timeout=2400,
                    creationflags=CREATE_NO_WINDOW,
                    env=child_environment(),
                )
            if result.returncode:
                raise RuntimeError(f"A compilação não foi concluída. Consulte {logfile}.")
            events.put(
                (
                    "output",
                    str(ROOT / ("instalador" if mode == "installer" else "dist/LIARTE_Desktop")),
                )
            )
            events.put(
                (
                    "success",
                    "Instalador criado na pasta instalador."
                    if mode == "installer"
                    else "Executável criado na pasta dist. Mantenha todos os arquivos da pasta juntos.",
                )
            )
        else:
            target = (
                interpreter.with_name("pythonw.exe") if sys.platform == "win32" else interpreter
            )
            if not target.is_file():
                target = interpreter
            events.put(("phase", {"step": 3, "label": "Abrindo Liarte…"}))
            events.put(("status", "Abrindo a janela LIARTE…"))
            launch_verified(
                [str(target), str(ROOT / "iniciar.py")],
                ROOT,
                logfile,
                creationflags=CREATE_NO_WINDOW,
            )
            events.put(("launched", "Aplicação iniciada."))
    except Exception as exc:
        try:
            stamp.unlink(missing_ok=True)
        except OSError:
            pass
        try:
            logfile.parent.mkdir(exist_ok=True)
            with logfile.open("a", encoding="utf-8") as output:
                output.write(traceback.format_exc() + "\n")
        except OSError:
            pass
        events.put(("error", str(exc)))


def prepare(mode: str, events: queue.Queue, *, repair=False):
    try:
        with PreparationLock(ROOT / "logs/preparacao.lock"):
            _prepare(mode, events, repair=repair)
    except (OSError, RuntimeError) as exc:
        events.put(("error", str(exc)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("run", "build", "installer"), default="run")
    parser.add_argument(
        "--repair", action="store_true", help="Reinstala o Qt no ambiente do aplicativo."
    )
    args = parser.parse_args()
    events: queue.Queue = queue.Queue()
    root = tk.Tk()
    root.title("Liarte · Preparação")
    root.geometry("640x380")
    root.minsize(580, 360)
    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)
    try:
        root.iconbitmap(str(ROOT / "src/liarte_desktop/assets/liarte.ico"))
    except tk.TclError:
        pass
    style = ttk.Style(root)
    if sys.platform == "win32" and "vista" in style.theme_names():
        style.theme_use("vista")
    frame = ttk.Frame(root, padding=24)
    frame.grid(sticky="nsew")
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(5, weight=1)
    ttk.Label(frame, text="Liarte", font=("Segoe UI", 19, "bold")).grid(sticky="w")
    purpose = {
        "run": "O aplicativo abrirá assim que estiver pronto.",
        "build": "Preparar a versão portátil para distribuição.",
        "installer": "Criar o instalador para a equipe da LIARTE.",
    }[args.mode]
    subtitle = ttk.Label(frame, text=purpose, wraplength=570)
    subtitle.grid(sticky="w", pady=(6, 24))
    phase = tk.StringVar(value="Preparando o aplicativo…")
    ttk.Label(frame, textvariable=phase, font=("Segoe UI", 12, "bold")).grid(sticky="w")
    status = tk.StringVar(value="A primeira preparação pode levar alguns minutos.")
    status_label = ttk.Label(frame, textvariable=status, wraplength=570)
    status_label.grid(sticky="w", pady=(8, 0))
    bar = ttk.Progressbar(frame, mode="indeterminate")
    bar.grid(sticky="ew", pady=18)
    bar.start(16)
    finished = False
    result_folder = ""
    actions = ttk.Frame(frame)
    actions.columnconfigure(0, weight=1)
    actions.columnconfigure(1, weight=1)
    completion = ttk.Frame(frame)

    def wrap_labels(event):
        if event.widget is frame:
            subtitle.configure(wraplength=max(300, event.width - 48))
            status_label.configure(wraplength=max(300, event.width - 48))

    frame.bind("<Configure>", wrap_labels)

    def open_diagnostic():
        path = ROOT / "logs/preparacao-desktop.log"
        if sys.platform == "win32" and path.is_file():
            try:
                os.startfile(str(path))
            except OSError as exc:
                messagebox.showerror("Diagnóstico", f"Abra o arquivo {path}.\n{exc}", parent=root)
        else:
            messagebox.showinfo("Diagnóstico", str(path), parent=root)

    def start(*, repair=False):
        nonlocal finished, result_folder
        finished = False
        result_folder = ""
        actions.grid_remove()
        completion.grid_remove()
        phase.set("Reparando o aplicativo…" if repair else "Preparando o aplicativo…")
        status.set("Aguarde um momento.")
        bar.configure(mode="indeterminate")
        bar.start(16)
        threading.Thread(
            target=prepare, args=(args.mode, events), kwargs={"repair": repair}, daemon=True
        ).start()
        root.after(100, poll)

    def open_result():
        if result_folder and Path(result_folder).is_dir() and sys.platform == "win32":
            try:
                os.startfile(result_folder)
            except OSError as exc:
                messagebox.showerror("Abrir pasta", str(exc), parent=root)

    ttk.Button(actions, text="Reparar e tentar novamente", command=lambda: start(repair=True)).grid(
        row=0, column=0, sticky="ew", padx=(0, 8), pady=(0, 8)
    )
    ttk.Button(actions, text="Abrir diagnóstico", command=open_diagnostic).grid(
        row=0, column=1, sticky="ew", pady=(0, 8)
    )
    ttk.Button(actions, text="Fechar", command=root.destroy).grid(row=1, column=1, sticky="e")
    ttk.Button(completion, text="Abrir pasta", command=open_result).pack(side="left", padx=(0, 12))
    ttk.Button(completion, text="Concluir", command=root.destroy).pack(side="left")

    def close():
        if finished:
            root.destroy()
        else:
            messagebox.showinfo(
                "Preparação em andamento",
                "Aguarde a preparação terminar. Nenhum dado da versão atual será alterado.",
                parent=root,
            )

    root.protocol("WM_DELETE_WINDOW", close)

    def poll():
        nonlocal finished, result_folder
        try:
            while True:
                kind, message = events.get_nowait()
                if kind == "phase":
                    phase.set(message["label"])
                    continue
                if kind == "output":
                    result_folder = message
                    continue
                status.set(message)
                if kind in ("success", "error", "launched"):
                    finished = True
                    bar.stop()
                    if kind == "error":
                        phase.set("Não foi possível concluir")
                        actions.grid(row=6, column=0, sticky="ew", pady=(8, 0))
                        return
                    if kind == "success":
                        phase.set(
                            "Instalador pronto"
                            if args.mode == "installer"
                            else "Versão portátil pronta"
                        )
                        bar.configure(mode="determinate", value=100)
                        completion.grid(row=6, column=0, sticky="w", pady=(8, 0))
                        return
                    root.destroy()
                    return
        except queue.Empty:
            root.after(120, poll)

    start(repair=args.repair)
    root.mainloop()


if __name__ == "__main__":
    main()
