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
    from tests.test_runtime_profile import RuntimeProfileTests, RuntimeProfileUiTests
    from tests.test_qt import QtTests, VolumeTests
    from tests.test_build import DistributionTests
    from tests.test_release import ReleaseTests
    from tests.test_chart_imports import ChartImportsTests
    from tests.test_chart_inventory import StockChartResponsiveTests
    from tests.test_home_indicators import HomeIndicatorsTests
    from tests.test_chart_workspace import ChartWorkspaceTests
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
    from tests.test_inventory_monthly import InventoryMonthlyTests
    from tests.test_inventory_monthly_export import InventoryMonthlyExportTests
    from tests.test_inventory_monthly_ui import InventoryMonthlyUiTests
    from tests.test_ui_regressions import InventorySearchRegressionTests
    from tests.test_comex_access import ComexAccessTests, ComexCentralTests, ComexConnectionUiTests
    from tests.test_comex_automatic import AutomaticAccessTests, AutomaticAccessUiTests
    from tests.test_comex_open_data import OpenDataTests, SourceFallbackTests
    from tests.test_secure_http import SecureHttpTests, LocalHttpsTests
    from tests.test_comex_direct import DirectApiTests, DirectApiUiTests
    from tests.test_comex_api import NativeApiTests, ApiProtocolTests, NativeApiQtTests
    from tests.test_audit_build import BuildAuditTests
    from tests.test_audit_stock_core import AuditStockCoreTests
    from tests.test_audit_network import ProcessPauseTests, EndpointStatusTests
    from tests.test_audit_network_legacy import (
        LegacyWaitAuditTests, LeaseReleaseAuditTests, InterruptedReadAuditTests,
        MunicipalCliAuditTests, ExactJsonAuditTests,
    )
    from tests.test_audit_exports import (
        AuditInventoryExportTests, AuditSourceWorkbookTests, AuditExactTotalsTests,
    )
    from tests.test_audit_desktop import InventoryDesktopAuditTests
    from tests.test_audit_qml import AuditQmlTests
    from tests.test_inventory_backup import InventoryBackupTests
    from tests.test_inventory_backup_ui import InventoryBackupUiTests
    from tests.test_inventory_backup_qml import InventoryBackupQmlTests
    from tests.test_inventory_backup_smoke import InventoryBackupSmokeTests
    from tests.test_installer_package import InstallerPackageTests
    from tests.test_installer_smoke_contract import InstallerSmokeContractTests
    from tests.test_inventory_alerts import InventoryAlertTests
    from tests.test_inventory_alerts_export import InventoryAlertsExportTests
    from tests.test_inventory_alerts_ui import InventoryAlertsUiTests
    from tests.test_inventory_alerts_qml import InventoryAlertQmlTests
    from tests.test_inventory_compare import InventoryCompareTests
    from tests.test_inventory_compare_export import InventoryCompareExportTests
    from tests.test_inventory_compare_ui import InventoryComparisonUiTests
    from tests.test_inventory_compare_qml import InventoryComparisonQmlTests
    from tests.test_inventory_performance import InventoryPerformanceTests
    from tests.test_inventory_performance_export import InventoryPerformanceExportTests
    from tests.test_inventory_performance_ui import (
        InventoryPerformanceUiTests, InventoryPerformanceIntegrationTests,
    )
    from tests.test_inventory_performance_qml import (
        InventoryPerformanceQmlTests, InventoryPerformanceWorkspaceTests,
    )
    from tests.test_ux_chart_interactions import UXChartInteractionTests
    from tests.test_ux_stock_filters import UXStockFilterControllerTests, UXStockFilterDialogTests
    from tests.test_ux_navigation import (
        InventoryWorkspaceNavigationTests, ImportsWorkspaceNavigationTests,
    )

    suite = unittest.TestSuite()
    for case in (
        UXChartInteractionTests,
        UXStockFilterControllerTests,
        UXStockFilterDialogTests,
        InventoryWorkspaceNavigationTests,
        ImportsWorkspaceNavigationTests,
        InventoryPerformanceTests,
        InventoryPerformanceExportTests,
        InventoryPerformanceUiTests,
        InventoryPerformanceIntegrationTests,
        InventoryPerformanceQmlTests,
        InventoryPerformanceWorkspaceTests,
        InventoryCompareTests,
        InventoryCompareExportTests,
        InventoryComparisonUiTests,
        InventoryComparisonQmlTests,
        InventoryAlertTests,
        InventoryAlertsExportTests,
        InventoryAlertsUiTests,
        InventoryAlertQmlTests,
        RuntimeProfileTests,
        RuntimeProfileUiTests,
        InventoryBackupTests,
        InventoryBackupUiTests,
        InventoryBackupQmlTests,
        InventoryBackupSmokeTests,
        InstallerPackageTests,
        InstallerSmokeContractTests,
        BuildAuditTests,
        AuditStockCoreTests,
        ProcessPauseTests,
        EndpointStatusTests,
        LegacyWaitAuditTests,
        LeaseReleaseAuditTests,
        InterruptedReadAuditTests,
        MunicipalCliAuditTests,
        ExactJsonAuditTests,
        AuditInventoryExportTests,
        AuditSourceWorkbookTests,
        AuditExactTotalsTests,
        InventoryDesktopAuditTests,
        AuditQmlTests,
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
        InventoryMonthlyTests,
        InventoryMonthlyExportTests,
        InventoryMonthlyUiTests,
        InventorySearchRegressionTests,
        PowerBiTests,
        CoreTests,
        QtTests,
        BootstrapTests,
        ReviewCoreTests,
        ReviewQtTests,
        PreparationTests,
        DistributionTests,
        ReleaseTests,
        ChartImportsTests,
        StockChartResponsiveTests,
        HomeIndicatorsTests,
        ChartWorkspaceTests,
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
