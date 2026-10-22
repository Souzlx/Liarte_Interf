"""Sinaliza ao Setup que há um processo aberto, sem encerrar tarefas do usuário."""

from __future__ import annotations

import ctypes
import logging
import sys

from .identity import APPLICATION_MUTEX

_HANDLE = None


def hold_installation_mutex() -> bool:
    """Mantém o handle até o fim do processo; o Windows o libera mesmo após falha.

    Não restringe múltiplas janelas. Cada processo mantém uma referência; o Setup
    só pode atualizar/desinstalar depois que todas as janelas forem encerradas.
    """
    global _HANDLE
    if sys.platform != "win32":
        return False
    if _HANDLE is not None:
        return True
    try:
        kernel = ctypes.WinDLL("kernel32", winmode=0x800, use_last_error=True)
        create = kernel.CreateMutexW
        create.argtypes = (ctypes.c_void_p, ctypes.c_int32, ctypes.c_wchar_p)
        create.restype = ctypes.c_void_p
        handle = create(None, 0, APPLICATION_MUTEX)
        if not handle:
            raise OSError(ctypes.get_last_error(), "CreateMutexW")
        _HANDLE = handle
        return True
    except (OSError, AttributeError):
        logging.getLogger("liarte.desktop").exception("Não foi possível sinalizar o uso ao Setup")
        return False
