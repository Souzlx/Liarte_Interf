"""Identificação oficial do Shell, sem dependência de pywin32 ou do registro.

O mesmo AppUserModelID identifica processo e atalhos. O ícone da janela é
atribuído pelo Qt antes de mostrá-la; o ícone do .exe continua no recurso PE.
"""

from __future__ import annotations

import ctypes
import logging
import sys
from uuid import UUID

from .identity import APP_USER_MODEL_ID

LOGGER = logging.getLogger("liarte.desktop")
HRESULT = ctypes.c_int32
GUID = ctypes.c_ubyte * 16


class PropertyKey(ctypes.Structure):
    _fields_ = [("fmtid", GUID), ("pid", ctypes.c_uint32)]


class _VariantValue(ctypes.Union):
    # PROPVARIANT includes a two-pointer record on x64 (24 bytes in total).
    _fields_ = [
        ("pointer", ctypes.c_void_p),
        ("integer", ctypes.c_int64),
        ("record", ctypes.c_void_p * 2),
    ]


class PropVariant(ctypes.Structure):
    _fields_ = [
        ("vt", ctypes.c_uint16),
        ("reserved1", ctypes.c_uint16),
        ("reserved2", ctypes.c_uint16),
        ("reserved3", ctypes.c_uint16),
        ("value", _VariantValue),
    ]


def _check(result, operation):
    if result < 0:
        raise OSError(f"{operation}: HRESULT 0x{result & 0xFFFFFFFF:08X}.")


def set_process_identity():
    """Chamar antes de QGuiApplication, inclusive na entrada instalada por pip."""
    if sys.platform != "win32":
        return False
    try:
        function = ctypes.WinDLL("shell32", winmode=0x800).SetCurrentProcessExplicitAppUserModelID
        function.argtypes = [ctypes.c_wchar_p]
        function.restype = HRESULT
        _check(function(APP_USER_MODEL_ID), "Identificação do aplicativo")
        return True
    except OSError:
        LOGGER.warning(
            "Não foi possível identificar o processo na barra de tarefas.", exc_info=True
        )
        return False


def _commit_appid(store):
    """IPropertyStore::SetValue, Commit e Release; buffer válido até SetValue retornar."""
    vtable = ctypes.cast(store, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    call = ctypes.WINFUNCTYPE
    release = call(ctypes.c_uint32, ctypes.c_void_p)(vtable[2])
    try:
        set_value = call(
            HRESULT, ctypes.c_void_p, ctypes.POINTER(PropertyKey), ctypes.POINTER(PropVariant)
        )(vtable[6])
        commit = call(HRESULT, ctypes.c_void_p)(vtable[7])
        key = PropertyKey(
            GUID.from_buffer_copy(UUID("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3").bytes_le), 5
        )
        buffer = ctypes.create_unicode_buffer(APP_USER_MODEL_ID)
        variant = PropVariant()
        variant.vt = 31  # VT_LPWSTR; Python owns this buffer, so do not PropVariantClear it.
        variant.value.pointer = ctypes.cast(buffer, ctypes.c_void_p)
        _check(set_value(store, ctypes.byref(key), ctypes.byref(variant)), "AppID do atalho")
        _check(commit(store), "Gravação do AppID")
    finally:
        release(store)


def identify_shortcuts(paths):
    """Atualiza apenas os .lnk que ensure_shortcuts já verificou como próprios.

    A thread de atalhos inicializa seu próprio apartamento COM. Falhas não geram
    marcador de sucesso, permitindo tentar novamente na próxima abertura.
    """
    if sys.platform != "win32":
        return
    ole = ctypes.WinDLL("ole32", winmode=0x800)
    ole.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    ole.CoInitializeEx.restype = HRESULT
    ole.CoUninitialize.argtypes = []
    ole.CoUninitialize.restype = None
    initialized = ole.CoInitializeEx(None, 2)
    if initialized not in (0, 1, -2147417850):  # RPC_E_CHANGED_MODE: use existing apartment.
        _check(initialized, "Inicialização do Shell")
    try:
        function = ctypes.WinDLL("shell32", winmode=0x800).SHGetPropertyStoreFromParsingName
        function.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(GUID),
            ctypes.POINTER(ctypes.c_void_p),
        ]
        function.restype = HRESULT
        iid = GUID.from_buffer_copy(UUID("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99").bytes_le)
        for path in paths:
            store = ctypes.c_void_p()
            _check(
                function(str(path), None, 2, ctypes.byref(iid), ctypes.byref(store)),
                "Acesso ao atalho",
            )
            if not store.value:
                raise OSError("O Shell não retornou o repositório de propriedades do atalho.")
            _commit_appid(store)
    finally:
        if initialized in (0, 1):
            ole.CoUninitialize()
