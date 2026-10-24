"""Resumo inicial reutiliza os resultados e mantém seus contextos separados."""

from threading import Event
import unittest
from unittest.mock import patch

from PySide6.QtCore import QPointF, QUrl
from PySide6.QtTest import QSignalSpy

from liarte_core.inventory_io import write_snapshot
from tests import test_platform
from tests.test_inventory import sample
from tests.test_qt import click, pump, settled


def variant(value):
    return value.toVariant() if hasattr(value, "toVariant") else value


class HomeIndicatorsTests(unittest.TestCase):
    item = test_platform.PlatformUiTests.item
    load = test_platform.PlatformUiTests.load

    def setUp(self):
        test_platform.PlatformUiTests.setUp(self)
        self.inventory = self.bundle.inventory
        self.inventory._cache = None
        self.inventory._bundled = None

    def tearDown(self):
        self.inventory.shutdown()
        test_platform.PlatformUiTests.tearDown(self)

    def inventory_idle(self):
        self.assertTrue(pump(lambda: not self.inventory.state["busy"]
                            and not self.inventory._debounce.isActive()))

    def load_inventory(self):
        path = self.directory / "stock.liarte"
        write_snapshot(sample(), path)
        self.inventory.openFile(QUrl.fromLocalFile(str(path)))
        self.inventory_idle()
        self.assertTrue(self.inventory.state["loaded"], self.inventory.state["error"])

    def render(self):
        rendered = QSignalSpy(self.window.frameSwapped)
        self.window.update()
        self.assertTrue(pump(lambda: rendered.count() > 0))

    def test_home_does_not_load_or_invent_indicators_before_a_query(self):
        home = self.item("homePage")
        self.assertEqual(variant(home.property("summaryCards")), [])
        self.assertFalse(self.item("homeSummary").isVisible())
        self.assertFalse(self.controller.state["loaded"])
        self.assertFalse(self.inventory.state["loaded"])
        self.assertEqual(self.transport.calls, [])
        self.assertEqual(self.bundle.messages, [])

    def test_import_summary_matches_applied_filters_and_municipal_basis_without_new_calls(self):
        self.load()
        self.platform.openModule("home")
        calls = list(self.transport.calls)
        home = self.item("homePage")
        summary = variant(home.property("summaryCards"))[0]
        self.assertEqual(summary["metrics"], self.controller.analysis["metrics"][:2])
        self.assertIn("NCM / CIF", summary["basis"])
        self.assertEqual(self.item("homeMetric_imports_0Value").property("text"),
                         self.controller.analysis["metrics"][0]["value"])
        self.controller.setDataset("municipal")
        settled(self.controller)
        self.controller.setFilters("country", ["China"])
        settled(self.controller)
        summary = variant(home.property("summaryCards"))[0]
        self.assertIn("SH4 / FOB", summary["basis"])
        self.assertEqual(summary["scope"], self.controller.state["filterSummary"])
        self.assertEqual(summary["period"], self.controller.state["periodLabel"])
        self.assertEqual(summary["metrics"], self.controller.analysis["metrics"][:2])
        self.assertEqual(self.transport.calls, calls)
        self.assertEqual(self.bundle.messages, [])

    def test_stock_summary_preserves_last_completed_result_while_filter_is_running(self):
        from liarte_desktop.inventory import analyze_inventory

        self.load_inventory()
        before = self.inventory.analysis["metrics"]
        home = self.item("homePage")
        summary = variant(home.property("summaryCards"))[0]
        self.assertEqual(summary["metrics"], [before[0], before[4]])
        self.assertIn(self.inventory.state["asOf"], summary["period"])
        self.assertIn("R$", summary["basis"])
        entered, release = Event(), Event()

        def delayed(*args, **kwargs):
            entered.set()
            if not release.wait(4):
                raise RuntimeError("Teste não liberou o recorte de estoque")
            return analyze_inventory(*args, **kwargs)

        try:
            with patch("liarte_desktop.inventory.analyze_inventory", side_effect=delayed):
                self.inventory.setFilter("unit", "KG")
                self.assertTrue(pump(entered.is_set))
                self.assertIn("último resultado", self.item("homeSummaryStatus_inventory").property("text"))
                self.assertEqual(variant(home.property("summaryCards"))[0]["metrics"],
                                 [before[0], before[4]])
                release.set()
                self.inventory_idle()
        finally:
            release.set()
        summary = variant(home.property("summaryCards"))[0]
        after = self.inventory.analysis["metrics"]
        self.assertEqual(summary["metrics"], [after[0], after[4]])
        self.assertNotEqual(after[0]["value"], before[0]["value"])
        self.assertEqual(self.transport.calls, [])
        self.assertEqual(self.bundle.messages, [])

    def test_summary_reflows_and_opening_a_card_preserves_the_applied_query(self):
        self.load()
        self.load_inventory()
        self.platform.openModule("home")
        calls = list(self.transport.calls)
        result = self.controller._result
        home = self.item("homePage")
        for width, height in ((500, 400), (760, 600), (1380, 900), (1920, 1080)):
            self.window.resize(width, height)
            self.render()
            imports = self.item("homeSummaryCard_imports")
            stock = self.item("homeSummaryCard_inventory")
            for card in (imports, stock):
                point = card.mapToItem(home, QPointF())
                self.assertGreaterEqual(point.x(), 0)
                self.assertLessEqual(point.x() + card.width(), home.width() + 1)
            if self.item("homeSummary").property("columns") == 1:
                self.assertGreaterEqual(stock.y(), imports.y() + imports.height())
            else:
                self.assertGreaterEqual(stock.x(), imports.x() + imports.width())
        self.window.resize(1380, 900)
        self.render()
        click(self.window, self.item("homeSummaryOpen_imports"))
        self.assertEqual(self.platform.activeModule, "imports")
        self.assertIs(self.controller._result, result)
        self.assertEqual(self.transport.calls, calls)
        self.assertEqual(self.bundle.messages, [])
