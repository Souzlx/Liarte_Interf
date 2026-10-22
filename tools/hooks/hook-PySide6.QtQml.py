"""Preserva o hook oficial e limita sua coleta QML aos módulos utilizados."""

from pathlib import Path
import sys

from PyInstaller.utils.hooks.qt import add_qt6_dependencies, pyside6_library_info

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qt_qml_policy import allowed_destination

hiddenimports, binaries, datas = add_qt6_dependencies(__file__)
qml_binaries, qml_datas = pyside6_library_info.collect_qtqml_files()
binaries += [entry for entry in qml_binaries if allowed_destination(entry[1])]
datas += [entry for entry in qml_datas if allowed_destination(entry[1])]
