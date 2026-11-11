"""Capture the real Qt application with isolated, explicitly synthetic fixtures.

Development evidence only: this tool never changes production data or starts
availability refreshes. Run with --source-root to capture an unchanged checkout.
"""

from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--width", default=1600, type=int)
    parser.add_argument("--height", default=900, type=int)
    parser.add_argument("--dark", action="store_true")
    parser.add_argument("--empty", action="store_true")
    parser.add_argument("--keyboard", action="store_true")
    return parser.parse_args()


def run(args):
    root = args.source_root.resolve()
    def qml_revision():
        digest = hashlib.sha256()
        for path in sorted((root / "src/liarte_desktop/qml").rglob("*.qml")):
            digest.update(str(path.relative_to(root)).encode("utf-8") + b"\0")
            digest.update(path.read_bytes())
        return digest.hexdigest()

    source_before = qml_revision()
    sys.path[:0] = [str(root / "src"), str(root)]
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("QT_QUICK_BACKEND", "software")
    cache = args.output.resolve() / "runtime-cache"
    cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("XDG_CACHE_HOME", str(cache))

    from liarte_desktop.qt_runtime import configure_windows_qt

    configure_windows_qt()

    from PySide6.QtCore import Q_ARG, QCoreApplication, QEvent, QMetaObject, QObject, QPointF, Qt, QUrl
    from PySide6.QtTest import QTest

    from liarte_core.inventory import SCALE, Balance, Closing, InventoryData, Product, Sale
    from liarte_core.inventory_io import write_snapshot
    from liarte_desktop.app import _finish_inventory_shutdown, create_bundle
    from liarte_desktop.runtime_profile import RuntimeProfile
    from tests.test_comex_history_ui import SyntheticHistoricalProvider
    from tests.test_qt import APP, pump, settled

    class CaptureProvider(SyntheticHistoricalProvider):
        """Deterministic numeric test data, no network or production cache."""

        def __init__(self, directory, available):
            super().__init__(directory, available=available)
            general, municipal = [], []
            for month in range(1, 10):
                for index, country in enumerate(("China", "Alemanha", "Estados Unidos")):
                    fob = 43000 + month * 3719 + index * 6403 + (month % 3) * 2147
                    freight, insurance = 1270 + month * 177, 19 + index * 7
                    general.append({
                        "coNcm": "29161220", "ncm": "Produto sintético de teste",
                        "year": "2026", "monthNumber": f"{month:02}",
                        "state": "São Paulo", "urf": "0817800 - PORTO DE SANTOS",
                        "country": country, "metricFOB": str(fob),
                        "metricFreight": str(freight), "metricInsurance": str(insurance),
                        "metricCIF": str(fob + freight + insurance),
                        "metricKG": str(19000 + month * 641 + index * 1703),
                    })
                    municipal.append({
                        "headingCode": "2916", "heading": "Grupo sintético de teste",
                        "year": "2026", "monthNumber": f"{month:02}",
                        "state": "São Paulo", "noMunMinsgUf": "Campinas - SP",
                        "country": country, "metricFOB": str(fob * 2 + 331),
                        "metricKG": str(12000 + month * 517 + index * 1831),
                    })
            self.transport.general, self.transport.municipal = general, municipal

        def has_local_period(self, start, end):
            return self.available and "2026-01" <= start <= end <= "2026-09"

        def history_status(self):
            state = super().history_status()
            if self.available:
                state.update(coverage_start="2026-01", complete_months=9)
            return state

    def stock_fixture():
        products, balances, closings, sales = [], [], [], []
        for index, (name, unit) in enumerate((
            ("Produto sintético Alfa", "KG"), ("Produto sintético Beta", "KG"),
            ("Produto sintético Gama", "KG"), ("Embalagem sintética", "UN"),
            ("Produto sintético Delta", "KG"), ("Produto sintético Épsilon", "KG"),
        )):
            code = f"TEST-{index + 1:03}"
            products.append(Product(code, name, "Grupo sintético", "MP", unit))
            quantity = 320 + index * 97
            balances.append(Balance(code, "01", "01", unit, quantity * SCALE, quantity * (327 + index * 49)))
            for month in range(1, 10):
                amount = 230 + index * 73 + month * 21 + (month % 3) * 37
                closings.append(Closing(code, "01", "01", unit, f"2026-{month:02}",
                                        amount * SCALE, amount * (327 + index * 49),
                                        1.2 + month / 7 + index / 11, 39 - month * 2 + index))
                sales.append(Sale(code, "01", unit, date(2026, month, 1),
                                  (29 + index * 13 + month * 7) * SCALE, (2900 + index * 1100 + month * 317)))
        return InventoryData(date(2026, 10, 1), "Base sintética de validação visual.pbix", "b" * 64,
                             tuple(products), tuple(balances), tuple(closings), tuple(sales),
                             (("01", "Filial sintética"),), (("01", "Armazém sintético"),))

    args.output.mkdir(parents=True, exist_ok=True)
    evidence = {
        "source_root": str(root), "data": "SYNTHETIC TEST FIXTURES — NOT COMPANY DATA",
        "platform": sys.platform, "qt_platform": os.environ["QT_QPA_PLATFORM"],
        "logical_size": [args.width, args.height], "dark": args.dark,
        "empty": args.empty, "scale_factor": os.environ.get("QT_SCALE_FACTOR", "1"),
        "qml_sha256_before": source_before,
        "screenshots": [], "geometry": [], "keyboard": {},
    }
    with tempfile.TemporaryDirectory(prefix="liarte-visual-") as scratch:
        profile = RuntimeProfile(Path(scratch) / "profile", development=True)
        provider = CaptureProvider(Path(scratch) / "history", not args.empty)
        with patch("liarte_engine.secure_http.urlopen", side_effect=AssertionError("Visual capture must not use network")):
            bundle = create_bundle(provider=provider, profile=profile)
            window = bundle.engine.rootObjects()[0]
            window.resize(args.width, args.height)
            bundle.inventory._cache = bundle.inventory._bundled = None
            bundle.preferences.setPreference("reducedMotion", True)
            bundle.preferences.setPreference("dark", args.dark)

            def item(name):
                result = window.findChild(QObject, name)
                pending = [window.contentItem()]
                while result is None and pending:
                    child = pending.pop()
                    if child.objectName() == name:
                        result = child
                        break
                    pending.extend(child.childItems())
                return result

            def settle():
                window.update()
                pump(timeout=0.12)

            def navigate(module, section=None):
                bundle.platform.openModule(module)
                settle()
                if section is not None:
                    target = item("inventoryWorkspace" if module == "inventory" else "importsWorkspace")
                    QMetaObject.invokeMethod(target, "navigate", Qt.ConnectionType.DirectConnection, Q_ARG("QVariant", section))
                settle()
                scroll = item({"home": "homeScroll", "imports": "contentScroll", "inventory": "stockScroll"}[module])
                scroll.setProperty("contentY", 0)
                settle()

            def capture(name):
                settle()
                path = args.output / (name + ".png")
                picture = window.grabWindow()
                if picture.isNull() or not picture.save(str(path)):
                    raise AssertionError(f"Qt could not capture {name}")
                evidence["screenshots"].append({"name": name, "path": str(path),
                                                "pixels": [picture.width(), picture.height()],
                                                "device_pixel_ratio": window.devicePixelRatio()})
                # A complete page may scroll vertically. These containers must
                # nevertheless remain inside their native horizontal viewport.
                for child_name, parent_name in (
                    ("homePage", "moduleStack"), ("importsWorkspace", "moduleStack"),
                    ("inventoryWorkspace", "moduleStack"), ("monthlyChart", "trendPanel"),
                    ("stockTrend", "stockHistoryCard"), ("stockMonthlyPlot", "stockMonthlyChartCard"),
                ):
                    child, parent = item(child_name), item(parent_name)
                    if child is None or parent is None or not child.isVisible():
                        continue
                    point = child.mapToItem(parent, QPointF())
                    fits = point.x() >= -1 and point.x() + child.width() <= parent.width() + 1
                    evidence["geometry"].append({"screen": name, "child": child_name, "parent": parent_name,
                                                 "x": round(point.x(), 2), "width": round(child.width(), 2),
                                                 "parent_width": round(parent.width(), 2), "horizontal_fit": fits})
                    if not fits:
                        raise AssertionError(evidence["geometry"][-1])

            try:
                if not args.empty:
                    bundle.controller.queryPeriod("2026-01", "2026-09")
                    settled(bundle.controller)
                    if not bundle.controller.state["loaded"]:
                        raise AssertionError(bundle.controller.state["error"])
                    base = Path(scratch) / "base-sintetica.liarte"
                    write_snapshot(stock_fixture(), base)
                    bundle.inventory.openFile(QUrl.fromLocalFile(str(base)))
                    if not pump(lambda: not bundle.inventory.state["busy"], 20):
                        raise AssertionError("Synthetic stock fixture timed out")
                    if not bundle.inventory.state["loaded"]:
                        raise AssertionError(bundle.inventory.state["error"])
                navigate("home")
                capture("home")
                navigate("imports", "summary")
                capture("imports-general")
                if not args.empty:
                    imports_workspace, imports_scroll = item("importsWorkspace"), item("contentScroll")
                    trend = item("trendPanel")
                    position = trend.mapToItem(imports_scroll, QPointF())
                    imports_scroll.setProperty("contentY", max(0, imports_scroll.property("contentY") + position.y() - 12))
                    settle()
                    capture("imports-general-chart")
                    imports_workspace.setProperty("primaryVisual", "origins")
                    settle()
                    origins = item("originsPanel")
                    position = origins.mapToItem(imports_scroll, QPointF())
                    imports_scroll.setProperty("contentY", max(0, imports_scroll.property("contentY") + position.y() - 12))
                    settle()
                    capture("imports-origins")
                    imports_workspace.setProperty("primaryVisual", "trend")
                    bundle.controller.setDataset("municipal")
                    settled(bundle.controller)
                    navigate("imports", "summary")
                    capture("imports-municipal")
                    bundle.controller.setDataset("general")
                    settled(bundle.controller)
                    navigate("imports", "records")
                    capture("imports-records")
                navigate("inventory", "overview")
                capture("stock")
                if not args.empty:
                    stock_scroll = item("stockScroll")
                    position = item("stockHistoryCard").mapToItem(stock_scroll, QPointF())
                    stock_scroll.setProperty("contentY", max(0, stock_scroll.property("contentY") + position.y() - 12))
                    settle()
                    capture("stock-chart")
                    navigate("inventory", "monthly")
                    capture("monthly")
                    stock_scroll = item("stockScroll")
                    position = item("stockMonthlyChartCard").mapToItem(stock_scroll, QPointF())
                    stock_scroll.setProperty("contentY", max(0, stock_scroll.property("contentY") + position.y() - 12))
                    settle()
                    capture("monthly-chart")
                    navigate("inventory", "products")
                    workspace = item("inventoryWorkspace")
                    workspace.setProperty("productView", "positions")
                    settle()
                    capture("stock-positions")
                if args.keyboard:
                    window.requestActivate()
                    settle()
                    for key, expected in ((Qt.Key.Key_1, "home"), (Qt.Key.Key_2, "imports"), (Qt.Key.Key_3, "inventory")):
                        QTest.keyClick(window, key, Qt.KeyboardModifier.ControlModifier)
                        settle()
                        actual = bundle.platform.activeModule
                        evidence["keyboard"][f"Ctrl+{int(key) - int(Qt.Key.Key_0)}"] = actual
                        if actual != expected:
                            raise AssertionError(f"Shortcut did not open {expected}")
                        focused = window.activeFocusItem()
                        if focused is None or not focused.isVisible():
                            raise AssertionError(f"Shortcut opened {expected} without visible focus")
                        position = focused.mapToItem(window.contentItem(), QPointF())
                        focus_fits = (position.x() >= -1 and position.y() >= -1
                                      and position.x() + focused.width() <= window.width() + 1
                                      and position.y() + focused.height() <= window.height() + 1)
                        evidence["keyboard"][f"focus/{expected}"] = {
                            "item": focused.objectName(), "visible_in_window": focus_fits,
                        }
                        if not focus_fits:
                            raise AssertionError(f"Shortcut {expected} focused outside viewport")
                    if not args.empty:
                        for module, expected in (("imports", "searchBox"), ("inventory", "stockSearch")):
                            navigate(module)
                            QTest.keyClick(window, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
                            settle()
                            focused = window.activeFocusItem()
                            evidence["keyboard"][f"Ctrl+F/{module}"] = focused.objectName() if focused else None
                            if focused is None or focused.objectName() != expected:
                                raise AssertionError(f"Contextual find did not focus {expected}")
                            QTest.keyClick(window, Qt.Key.Key_Tab)
                            settle()
                            QTest.keyClick(window, Qt.Key.Key_Backtab)
                            settle()
                            focused = window.activeFocusItem()
                            if focused is None or not focused.isVisible():
                                raise AssertionError("Tab/Backtab lost visible focus")
                evidence["qml_warnings"] = bundle.messages
                if bundle.messages:
                    raise AssertionError(bundle.messages)
                evidence["qml_sha256_after"] = qml_revision()
                if evidence["qml_sha256_after"] != source_before:
                    raise AssertionError("QML source changed during capture; repeat with stable source")
                evidence["status"] = "ok"
            finally:
                evidence.setdefault("qml_warnings", bundle.messages)
                (args.output / "evidence.json").write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
                bundle.controller.shutdown()
                _finish_inventory_shutdown(bundle.inventory)
                window.close()
                window.deleteLater()
                QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                APP.processEvents()
                bundle.engine.deleteLater()
                QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                APP.processEvents()
                bundle.services.deleteLater()
                QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                APP.processEvents()
        provider.close()
    print(json.dumps({"status": evidence["status"], "screenshots": len(evidence["screenshots"]),
                      "output": str(args.output), "qml_warnings": evidence["qml_warnings"]}))


if __name__ == "__main__":
    run(arguments())
