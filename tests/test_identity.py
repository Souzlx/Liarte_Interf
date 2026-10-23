"""Contratos do Shell com APIs simuladas; não substituem homologação Windows."""

import ctypes
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import UUID

from liarte_desktop import windows_identity as identity
from liarte_desktop.identity import APP_TITLE, APP_USER_MODEL_ID
from liarte_desktop.app import PACKAGE
from tests import test_comex


class IdentityTests(unittest.TestCase):
    def test_process_uses_stable_id_with_typed_windows_api(self):
        function = Mock(return_value=0)
        with (
            patch.object(identity.sys, "platform", "win32"),
            patch.object(
                identity.ctypes,
                "WinDLL",
                create=True,
                return_value=SimpleNamespace(SetCurrentProcessExplicitAppUserModelID=function),
            ),
        ):
            self.assertTrue(identity.set_process_identity())
        function.assert_called_once_with(APP_USER_MODEL_ID)
        self.assertEqual(function.restype, ctypes.c_int32)
        self.assertEqual(function.argtypes, [ctypes.c_wchar_p])

    def test_process_identity_failure_does_not_prevent_startup(self):
        with (
            patch.object(identity.sys, "platform", "win32"),
            patch.object(
                identity.ctypes, "WinDLL", create=True, side_effect=OSError("shell unavailable")
            ),
            self.assertLogs("liarte.desktop", level="WARNING"),
        ):
            self.assertFalse(identity.set_process_identity())

    def test_other_platforms_do_not_load_windows_libraries(self):
        with (
            patch.object(identity.sys, "platform", "linux"),
            patch.object(identity.ctypes, "WinDLL", create=True) as load,
        ):
            self.assertFalse(identity.set_process_identity())
            identity.identify_shortcuts([Path("example.lnk")])
            load.assert_not_called()

    def test_propvariant_abi_and_shell_key_match_windows_sdk(self):
        self.assertEqual(
            ctypes.sizeof(identity.PropVariant), 24 if ctypes.sizeof(ctypes.c_void_p) == 8 else 16
        )
        self.assertEqual(identity.PropVariant.value.offset, 8)
        self.assertEqual(ctypes.sizeof(identity.PropertyKey), 20)
        calls = []

        @ctypes.CFUNCTYPE(ctypes.c_uint32, ctypes.c_void_p)
        def release(_):
            calls.append("release")
            return 0

        @ctypes.CFUNCTYPE(
            identity.HRESULT,
            ctypes.c_void_p,
            ctypes.POINTER(identity.PropertyKey),
            ctypes.POINTER(identity.PropVariant),
        )
        def set_value(_, key, variant):
            calls.append(
                (
                    UUID(bytes_le=bytes(key.contents.fmtid)),
                    key.contents.pid,
                    variant.contents.vt,
                    ctypes.wstring_at(variant.contents.value.pointer),
                )
            )
            return 0

        @ctypes.CFUNCTYPE(identity.HRESULT, ctypes.c_void_p)
        def commit(_):
            calls.append("commit")
            return 0

        table = (ctypes.c_void_p * 8)()
        for index, callback in ((2, release), (6, set_value), (7, commit)):
            table[index] = ctypes.cast(callback, ctypes.c_void_p)
        interface = ctypes.pointer(ctypes.cast(table, ctypes.POINTER(ctypes.c_void_p)))
        with patch.object(identity.ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE, create=True):
            identity._commit_appid(ctypes.cast(interface, ctypes.c_void_p))
        self.assertEqual(
            calls,
            [
                (UUID("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"), 5, 31, APP_USER_MODEL_ID),
                "commit",
                "release",
            ],
        )

    def test_shortcut_com_apartment_lifetime_and_store_access(self):
        for init in (0, 1, -2147417850):
            with self.subTest(init=init):
                ole = SimpleNamespace(CoInitializeEx=Mock(return_value=init), CoUninitialize=Mock())

                def get_store(path, binding, flags, iid, output):
                    self.assertEqual(flags, 2)
                    self.assertEqual(path, str(Path("Área de Trabalho/Liarte.lnk")))
                    ctypes.cast(output, ctypes.POINTER(ctypes.c_void_p)).contents.value = 123
                    return 0

                shell = SimpleNamespace(
                    SHGetPropertyStoreFromParsingName=Mock(side_effect=get_store)
                )
                with (
                    patch.object(identity.sys, "platform", "win32"),
                    patch.object(
                        identity.ctypes,
                        "WinDLL",
                        create=True,
                        side_effect=lambda name, **_: ole if name == "ole32" else shell,
                    ),
                    patch.object(identity, "_commit_appid") as commit,
                ):
                    identity.identify_shortcuts([Path("Área de Trabalho/Liarte.lnk")])
                    self.assertEqual(commit.call_args.args[0].value, 123)
                self.assertEqual(ole.CoUninitialize.call_count, 1 if init in (0, 1) else 0)

    def test_shortcut_failure_uninitializes_its_apartment(self):
        ole = SimpleNamespace(CoInitializeEx=Mock(return_value=0), CoUninitialize=Mock())
        shell = SimpleNamespace(SHGetPropertyStoreFromParsingName=Mock(return_value=-2147024891))
        with (
            patch.object(identity.sys, "platform", "win32"),
            patch.object(
                identity.ctypes,
                "WinDLL",
                create=True,
                side_effect=lambda name, **_: ole if name == "ole32" else shell,
            ),
            self.assertRaises(OSError),
        ):
            identity.identify_shortcuts([Path("Liarte.lnk")])
        ole.CoUninitialize.assert_called_once()

    def test_installer_uses_the_same_appid_on_both_links(self):
        root = Path(__file__).resolve().parents[1]
        script = (root / "INSTALADOR_LIARTE.iss").read_text(encoding="utf-8-sig")
        links = [
            line
            for line in script.splitlines()
            if line.startswith('Name: "{auto') and "IconFilename:" in line
        ]
        self.assertEqual(len(links), 2)
        self.assertTrue(all(f'AppUserModelID: "{APP_USER_MODEL_ID}"' in line for line in links))
        self.assertIn("AppName=" + APP_TITLE, script)


class IdentityQtTests(unittest.TestCase):
    setUp = test_comex.RealQtTests.setUp
    tearDown = test_comex.RealQtTests.tearDown

    def test_window_has_original_multisize_icon_and_short_title_before_use(self):
        self.assertEqual(self.window.title(), self.bundle.platform.windowTitle)
        self.assertEqual(self.window.title(), "Liarte Importações")
        self.assertTrue(self.window.isVisible())
        icon = self.window.icon()
        self.assertFalse(icon.isNull())
        for size in (16, 32, 48, 128, 256):
            pixmap = icon.pixmap(size, size)
            self.assertFalse(pixmap.isNull())
        from PySide6.QtGui import QIcon

        expected = QIcon(str(PACKAGE / "assets/liarte.ico"))
        self.assertEqual(icon.pixmap(32, 32).toImage(), expected.pixmap(32, 32).toImage())
        self.assertEqual(self.bundle.messages, [])
