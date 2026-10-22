"""Entrada para código-fonte e executável; a interface é inteiramente Qt."""

from __future__ import annotations

from pathlib import Path
import os
import traceback
import sys

ROOT = Path(__file__).resolve().parent
if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(ROOT / "src"))


def main():
    try:
        from liarte_desktop.qt_runtime import configure_windows_qt

        configure_windows_qt()
        from liarte_desktop.app import main as run

        return run()
    except Exception as exc:
        diagnostic = os.environ.get("LIARTE_STARTUP_LOG")
        if diagnostic:
            try:
                path = Path(diagnostic)
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("a", encoding="utf-8") as output:
                    output.write(traceback.format_exc() + "\n")
            except OSError:
                pass
        message = (
            "Não foi possível iniciar o Liarte.\n\n"
            "No código-fonte, utilize INICIAR_DESKTOP.cmd. "
            "No executável, extraia a pasta completa do pacote.\n\n" + str(exc)
        )
        if (
            sys.platform == "win32"
            and os.environ.get("LIARTE_STARTUP_PROBE") != "1"
            and "--smoke-test" not in sys.argv
            and "--startup-ready" not in sys.argv
        ):
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, message, "Liarte", 0x10)
        else:
            print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
