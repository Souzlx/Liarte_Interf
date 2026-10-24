"""Regressions for stock worker publication, exact text, and Qt shutdown."""

from dataclasses import replace
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import patch

from PySide6.QtCore import QObject, Qt, QThread, QTimer, QUrl
from PySide6.QtTest import QSignalSpy

from liarte_core.inventory import Balance, Closing, Product, SCALE, Sale, analyze_inventory
from liarte_core.inventory_io import write_snapshot
from liarte_core.query import checkpoint
from liarte_desktop import inventory as desktop
from liarte_desktop.app import _finish_inventory_shutdown
from tests.test_inventory import sample, selection
from tests.test_qt import APP, pump


def expanded(count=120):
    original = sample()
    products = tuple(Product(f"P{i:06}", f"Produto {i:06}", "G", "PA", "UN") for i in range(count))
    return replace(
        original,
        products=products,
        balances=tuple(
            Balance(p.code, "01", "01", "UN", (i + 1) * SCALE, (count - i) * 100)
            for i, p in enumerate(products)
        ),
        closings=tuple(
            Closing(p.code, "01", "01", "UN", "2026-03", SCALE, 100, 1.0, 30.0) for p in products
        ),
        sales=tuple(Sale(p.code, "01", "UN", date(2026, 1, 1), SCALE, 100) for p in products),
    )


class InventoryDesktopAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.c = desktop.InventoryController()
        self.addCleanup(self.c.shutdown)

    def idle(self):
        self.assertTrue(
            pump(lambda: not self.c.state["busy"] and not self.c._debounce.isActive(), 10),
            self.c.state,
        )

    def load(self, data=None):
        source = Path(self.temp.name) / "source.liarte"
        write_snapshot(data or sample(), source)
        self.c.openFile(QUrl.fromLocalFile(str(source)))
        self.idle()
        self.assertTrue(self.c.state["loaded"], self.c.state["error"])

    def test_source_sized_presentation_runs_on_worker_and_page_commit_on_gui(self):
        threads = {}

        def observed(name, function):
            def invoke(*args, **kwargs):
                threads.setdefault(name, []).append(QThread.currentThread() == APP.thread())
                return function(*args, **kwargs)

            return invoke

        with (
            patch.object(
                desktop, "ProductSearch", side_effect=observed("search", desktop.ProductSearch)
            ),
            patch.object(
                desktop.InventoryController,
                "_build_options",
                side_effect=observed("options", self.c._build_options),
            ),
            patch.object(
                desktop, "_order_rows", side_effect=observed("ordering", desktop._order_rows)
            ),
            patch.object(
                desktop,
                "_monthly_presentation",
                side_effect=observed("monthly", desktop._monthly_presentation),
            ),
            patch.object(desktop, "stock_cells", side_effect=observed("page", desktop.stock_cells)),
        ):
            self.load(expanded())
        for name in ("search", "options", "ordering", "monthly"):
            self.assertTrue(threads[name], name)
            self.assertFalse(any(threads[name]), name)
        self.assertEqual(len(threads["page"]), 50)
        self.assertTrue(all(threads["page"]))
        self.assertEqual(self.c.state["count"], 120)
        self.assertEqual(self.c.searchProducts("P000119")["items"][0]["code"], "P000119")

    def test_pagination_uses_cached_order_without_visiting_analysis_rows(self):
        self.load(expanded())
        order = self.c._ordered

        class ForbiddenRows:
            def __iter__(self):
                raise AssertionError("A page change must not visit the full analysis")

        self.c._analysis = replace(self.c._analysis, rows=ForbiddenRows())
        self.c.selectRow(0)
        with patch.object(
            desktop, "_order_rows", side_effect=AssertionError("Unexpected ordering")
        ):
            self.c.setPage(2)
        self.assertIs(self.c._ordered, order)
        self.assertEqual(self.c.table.rows, order[50:100])
        self.assertEqual(self.c.state["selectedRow"], -1)
        self.assertEqual(self.c.detail, {})

    def test_large_sort_is_prepared_on_worker_and_published_in_numeric_order(self):
        self.load(expanded())
        was_gui = []
        original = desktop._order_rows

        def observe(*args, **kwargs):
            was_gui.append(QThread.currentThread() == APP.thread())
            return original(*args, **kwargs)

        with patch.object(desktop, "_order_rows", side_effect=observe):
            self.c.sortByColumn(5)
            self.assertTrue(self.c.state["busy"])
            self.idle()
        self.assertEqual(was_gui, [False])
        self.assertEqual(self.c.table.rows[0].balance.quantity, 120 * SCALE)
        self.c.setPage(3)
        self.assertEqual(self.c.table.rows[-1].balance.quantity, SCALE)

    def test_cancelling_sort_keeps_previous_rows_and_applied_header(self):
        self.load(expanded())
        before = self.c.table.rows
        header = (self.c.state["sortColumn"], self.c.state["descending"])
        entered = Event()

        def cancellable(rows, column, descending, cancel=None):
            entered.set()
            self.assertTrue(cancel.wait(3), "Cancel event was not forwarded")
            checkpoint(cancel)

        with patch.object(desktop, "_order_rows", side_effect=cancellable):
            self.c.sortByColumn(5)
            self.assertTrue(pump(entered.is_set))
            self.c.cancel()
            self.idle()
        self.assertEqual(self.c.table.rows, before)
        self.assertEqual((self.c.state["sortColumn"], self.c.state["descending"]), header)

    def test_sort_cannot_commit_rows_for_pending_filter(self):
        self.load(expanded())
        header = self.c.state["sortColumn"]
        self.c.setFilter("unit", "UN")
        with patch.object(desktop, "_order_rows", side_effect=AssertionError("Pending sort")):
            self.c.sortByColumn(5)
        self.assertEqual(self.c.state["sortColumn"], header)
        self.c.cancel()

    def test_obsolete_analysis_receives_cancel_and_latest_filter_finishes(self):
        self.load()
        entered, cancelled = Event(), Event()
        calls = []
        original = desktop.analyze_inventory

        def first_waits(data, selected, *, cancel=None):
            calls.append(selected.unit)
            if len(calls) == 1:
                entered.set()
                if not cancel.wait(3):
                    raise AssertionError("An obsolete generation was left running")
                cancelled.set()
                checkpoint(cancel)
            return original(data, selected, cancel=cancel)

        with patch.object(desktop, "analyze_inventory", side_effect=first_waits):
            self.c.setFilter("unit", "KG")
            self.assertTrue(pump(entered.is_set))
            self.c.setFilter("unit", "L")
            self.assertTrue(pump(cancelled.is_set, 1))
            self.idle()
        self.assertEqual(calls, ["KG", "L"])
        self.assertEqual({r.balance.unit for r in self.c.table.rows}, {"L"})
        self.assertTrue(self.c.state["current"])

    def test_visible_monthly_rankings_are_bounded_but_export_facts_are_complete(self):
        self.load(expanded())
        raw = next(m for m in self.c._monthly_data if m["period"] == "2026-03")
        self.assertEqual(len(raw["stockRows"]), 120)
        self.assertEqual(len(raw["lowTurnover"]), 120)
        self.assertEqual(len(raw["slow"]), 120)
        self.assertEqual(len(self.c.monthly["lowTurnover"]), 12)
        self.assertEqual(len(self.c.monthly["slow"]), 12)
        self.assertIsInstance(self.c.monthly["slow"], list)
        self.c.setMonthlyPeriod("2026-01")
        self.c.setMonthlyPeriod("2026-03")
        self.assertEqual(len(raw["stockRows"]), 120)
        self.assertEqual(len(self.c.monthly["slow"]), 12)

    def test_half_decimal_quantities_are_exact_in_table_details_and_series(self):
        original = sample()
        data = replace(
            original,
            balances=(replace(original.balances[0], quantity=5500),),
            closings=(replace(original.closings[1], quantity=5500),),
            sales=(replace(original.sales[1], quantity=7500),),
        )
        self.load(data)
        self.assertEqual(desktop.stock_cells(self.c.table.rows[0])[5], "0,006")
        self.c.selectRow(0)
        self.assertEqual(self.c.detail["balance"], "0,006 KG")
        self.assertEqual(self.c.detail["sold"], "0,008 KG · filial inteira")
        march = next(p for p in self.c.detail["salesTrend"] if p["period"] == "2026-03")
        self.assertEqual(march["display"], "0,008 KG")
        self.c.setMonthlyUnit("KG")
        self.assertEqual(self.c.monthly["metrics"][1]["value"], "0,006 KG")

    def test_missing_sales_source_never_creates_zero_in_detail_series(self):
        self.load(replace(sample(), sales=()))
        self.c.selectRow(0)
        self.assertTrue(self.c.detail["salesTrend"])
        self.assertTrue(all(p["value"] is None for p in self.c.detail["salesTrend"]))
        self.assertTrue(all(p["display"] == "Sem dados" for p in self.c.detail["salesTrend"]))

    def test_table_formats_each_visible_row_once(self):
        rows = analyze_inventory(sample(), selection()).rows
        with patch.object(desktop, "stock_cells", wraps=desktop.stock_cells) as formatter:
            self.c.table.setRows(rows)
            for row in range(self.c.table.rowCount()):
                for column in range(self.c.table.columnCount()):
                    self.assertIsInstance(self.c.table.data(self.c.table.index(row, column)), str)
        self.assertEqual(formatter.call_count, len(rows))

    def test_timed_out_shutdown_retains_thread_and_staging_until_finished(self):
        parent = QObject()
        self.c.setParent(parent)
        staged = Path(self.temp.name) / ".base-pending.liarte"
        staged.write_bytes(b"unfinished staging")
        self.c._staged_cache = staged
        entered, release = Event(), Event()
        completed = QSignalSpy(self.c.shutdownFinished)

        def blocked(cancel, progress):
            entered.set()
            release.wait(3)
            return ("export",)

        try:
            self.c._start(blocked, "load")
            self.assertTrue(pump(entered.is_set))
            self.assertFalse(self.c.shutdown(wait_ms=1))
            self.assertIsNone(self.c.parent())
            self.assertIn(self.c, desktop._SHUTTING_DOWN)
            self.assertTrue(self.c._thread.isRunning())
            self.assertTrue(staged.exists())
            self.assertFalse(self.c.shutdown(wait_ms=0))
            release.set()
            self.assertTrue(pump(lambda: completed.count() == 1))
            self.assertIsNone(self.c._thread)
            self.assertFalse(staged.exists())
            self.assertNotIn(self.c, desktop._SHUTTING_DOWN)
            self.assertTrue(self.c.shutdown(wait_ms=0))
            self.assertEqual(completed.count(), 1)
        finally:
            release.set()
            self.c.shutdown()

    def test_application_shutdown_helper_drives_qt_until_worker_finished(self):
        entered, release = Event(), Event()
        native_cleanup = Event()

        def blocked(cancel, progress):
            entered.set()
            release.wait(3)
            return ("export",)

        self.c._start(blocked, "load")
        self.assertTrue(pump(entered.is_set))
        thread = self.c._thread

        def finishing_native_thread():
            # A direct finished callback still executes on the native worker.
            # Model a thread-local destructor that outlives queued notification.
            Event().wait(0.05)
            native_cleanup.set()

        thread.finished.connect(finishing_native_thread, Qt.ConnectionType.DirectConnection)
        original = self.c.shutdown
        QTimer.singleShot(20, release.set)
        try:
            with patch.object(self.c, "shutdown", side_effect=lambda **kwargs: original(wait_ms=0)):
                _finish_inventory_shutdown(self.c)
            self.assertTrue(
                native_cleanup.is_set(), "Shutdown returned before the native thread joined"
            )
            self.assertTrue(self.c._shutdown_complete)
            self.assertIsNone(self.c._thread)
        finally:
            release.set()
            native_cleanup.wait(1)
            self.c.shutdown()
