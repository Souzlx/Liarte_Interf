"""Executa testes reais do domínio e do Qt, sem rede e sem dados da empresa."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import unittest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Qt offscreen para automação; não equivale à homologação Windows.",
    )
    parser.add_argument(
        "--volume", action="store_true", help="Inclui o ensaio com 100 mil registros."
    )
    args = parser.parse_args()
    if args.headless:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        os.environ.setdefault("QT_QUICK_BACKEND", "software")
    root = Path(__file__).resolve().parent
    sys.path.insert(0, str(root / "src"))
    from liarte_desktop.qt_runtime import configure_windows_qt

    configure_windows_qt()
    from tests.test_core import CoreTests
    from tests.test_qt import QtTests, VolumeTests
    from tests.test_build import DistributionTests
    from tests.test_bootstrap import BootstrapTests
    from tests.test_review import ReviewCoreTests, ReviewQtTests
    from tests.test_preparation import PreparationTests
    from tests.test_windows_shell import WindowsShellTests
    from tests.test_comex import ComexTests, ExportTests, RealQtTests
    from tests.test_interface import InterfaceTests, PaletteTests
    from tests.test_procurement import ProcurementTests
    from tests.test_identity import IdentityTests, IdentityQtTests
    from tests.test_procurement_ui import ProcurementUiTests
    from tests.test_usability import DescriptiveTests, UsabilityTests
    from tests.test_refinement import InstallationTests, BrandedPdfTests, MotionRefinementTests

    from tests.test_powerbi import PowerBiTests
    from tests.test_workspace import WorkspaceDataTests, WorkspaceUiTests
    from tests.test_accuracy import AccuracyTests, AccuracyExportTests
    from tests.test_python_runtime import PythonRuntimeTests
    from tests.test_platform import PlatformTests, PlatformUiTests
    from tests.test_navigation import (
        NavigationCoreTests,
        NavigationModelTests,
        NavigationQtTests,
        NavigationComexTests,
        NavigationMunicipalTests,
    )

    from tests.test_inventory import InventoryMathTests, InventoryFileTests, InventoryUiTests
    from tests.test_comex_access import ComexAccessTests, ComexCentralTests, ComexConnectionUiTests
    from tests.test_comex_automatic import AutomaticAccessTests, AutomaticAccessUiTests
    from tests.test_comex_open_data import OpenDataTests, SourceFallbackTests
    from tests.test_secure_http import SecureHttpTests, LocalHttpsTests
    from tests.test_comex_direct import DirectApiTests, DirectApiUiTests
    from tests.test_comex_api import NativeApiTests, ApiProtocolTests, NativeApiQtTests

    suite = unittest.TestSuite()
    for case in (
        NativeApiTests,
        ApiProtocolTests,
        NativeApiQtTests,
        DirectApiTests,
        DirectApiUiTests,
        SecureHttpTests,
        LocalHttpsTests,
        OpenDataTests,
        SourceFallbackTests,
        AutomaticAccessTests,
        AutomaticAccessUiTests,
        ComexAccessTests,
        ComexCentralTests,
        ComexConnectionUiTests,
        InventoryMathTests,
        InventoryFileTests,
        InventoryUiTests,
        PowerBiTests,
        CoreTests,
        QtTests,
        BootstrapTests,
        ReviewCoreTests,
        ReviewQtTests,
        PreparationTests,
        DistributionTests,
        ComexTests,
        ExportTests,
        RealQtTests,
        WindowsShellTests,
        InterfaceTests,
        PaletteTests,
        ProcurementTests,
        IdentityTests,
        IdentityQtTests,
        ProcurementUiTests,
        DescriptiveTests,
        UsabilityTests,
        InstallationTests,
        BrandedPdfTests,
        MotionRefinementTests,
        WorkspaceDataTests,
        WorkspaceUiTests,
        AccuracyTests,
        AccuracyExportTests,
        PythonRuntimeTests,
        PlatformTests,
        PlatformUiTests,
        NavigationCoreTests,
        NavigationModelTests,
        NavigationQtTests,
        NavigationComexTests,
        NavigationMunicipalTests,
        *((VolumeTests,) if args.volume else ()),
    ):
        suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(case))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
