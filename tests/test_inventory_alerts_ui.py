"""Qt alert settings and publication preserve the current stock session."""

from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import patch

from PySide6.QtCore import QSettings, QUrl

from liarte_core.inventory_io import write_snapshot
from liarte_desktop import inventory as desktop
from tests.test_audit_desktop import expanded
from tests.test_inventory import sample
from tests.test_qt import pump


LIMITS_KEY = "inventory/alerts/limits"


class InventoryAlertsUiTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.settings = QSettings(
            str(self.directory / "preferences.ini"), QSettings.Format.IniFormat
        )
        self.controllers = []
        self.addCleanup(self.close_controllers)
        self.c = self.controller(self.settings)

    def close_controllers(self):
        for controller in reversed(self.controllers):
            controller.shutdown()

    def controller(self, settings=None):
        controller = desktop.InventoryController(settings)
        self.controllers.append(controller)
        return controller

    def idle(self, controller=None):
        controller = self.c if controller is None else controller
        self.assertTrue(
            pump(
                lambda: not controller.state["busy"]
                and not controller._debounce.isActive(),
                10,
            ),
            controller.state,
        )

    def load(self, data=None, controller=None):
        controller = self.c if controller is None else controller
        path = self.directory / f"source-{len(self.controllers)}.liarte"
        write_snapshot(sample() if data is None else data, path)
        controller.openFile(QUrl.fromLocalFile(str(path)))
        self.idle(controller)
        self.assertTrue(controller.state["loaded"], controller.state["error"])
        self.assertTrue(controller.state["current"], controller.state)

    def category(self, key, controller=None):
        controller = self.c if controller is None else controller
        return next(entry for entry in controller.alerts["categories"] if entry["key"] == key)

    def saved_limits(self):
        self.settings.sync()
        value = self.settings.value(LIMITS_KEY)
        return json.loads(value) if value is not None else None

    def test_limits_persist_as_one_setting_and_reopen_without_changing_other_preferences(self):
        self.settings.setValue("reports/path", "preserved")
        self.load()
        self.c.setAlertThresholds(30, 300)
        self.idle()
        self.assertTrue(self.c.state["current"])
        self.assertEqual(self.saved_limits(), {"staleDays": 30, "coverageDays": 300})
        self.assertEqual(self.settings.value("reports/path"), "preserved")
        reopened = self.controller(QSettings(
            str(self.directory / "preferences.ini"), QSettings.Format.IniFormat
        ))
        self.assertEqual(reopened.alertSettings["staleDays"], 30)
        self.assertEqual(reopened.alertSettings["coverageDays"], 300)
        self.load(controller=reopened)
        self.assertEqual(self.category("stale", reopened)["count"], 1)

    def test_invalid_saved_limits_fall_back_without_rewriting_the_unrelated_profile(self):
        for stored in (
            "not json",
            '[]',
            '{"staleDays":true,"coverageDays":30}',
            '{"staleDays":90,"coverageDays":0}',
            '{"staleDays":90}',
        ):
            with self.subTest(stored=stored):
                self.settings.setValue(LIMITS_KEY, stored)
                self.settings.sync()
                controller = self.controller(self.settings)
                self.assertEqual(controller.alertSettings["staleDays"], 90)
                self.assertEqual(controller.alertSettings["coverageDays"], 30)
                self.assertTrue(controller.alertSettings["notice"])
                self.assertEqual(self.settings.value(LIMITS_KEY), stored)

    def test_invalid_requested_limits_keep_the_applied_result_and_preferences(self):
        self.load()
        before = self.c.alerts
        for stale, coverage in ((0, 30), (90, 3651), (-1, 30), (True, 30), (90, 1.5)):
            with self.subTest(stale=stale, coverage=coverage):
                self.c.setAlertThresholds(stale, coverage)
                self.idle()
                self.assertEqual(self.c.alertSettings["staleDays"], 90)
                self.assertEqual(self.c.alertSettings["coverageDays"], 30)
                self.assertEqual(self.c.alerts, before)
                self.assertTrue(self.c.alertSettings["error"])
                self.assertTrue(self.c.state["current"])
        self.assertIsNone(self.saved_limits())

    def test_explicit_apply_repairs_invalid_saved_limits_without_recalculating_alerts(self):
        self.settings.setValue(LIMITS_KEY, "invalid saved limits")
        self.settings.setValue("reports/path", "preserved")
        self.settings.sync()
        self.c = self.controller(self.settings)
        self.load()
        before = self.c.alerts
        self.assertTrue(self.c.alertSettings["notice"])
        self.assertEqual(self.settings.value(LIMITS_KEY), "invalid saved limits")
        with patch.object(
            desktop, "analyze_stock_alerts", side_effect=AssertionError("Unchanged alerts recalculated")
        ):
            self.c.setAlertThresholds(90, 30)
            self.idle()
        self.assertEqual(self.saved_limits(), {"staleDays": 90, "coverageDays": 30})
        self.assertEqual(self.c.alertSettings["notice"], "")
        self.assertEqual(self.settings.value("reports/path"), "preserved")
        self.assertEqual(self.c.alerts, before)
        self.assertTrue(self.c.state["current"])

    def test_without_settings_limits_work_only_in_this_session(self):
        controller = self.controller()
        self.load(controller=controller)
        controller.setAlertThresholds(30, 300)
        self.idle(controller)
        self.assertEqual(controller.alertSettings["staleDays"], 30)
        self.assertEqual(self.category("stale", controller)["count"], 1)
        self.assertTrue(controller.alertSettings["notice"])
        self.assertIsNone(self.saved_limits())
        self.assertEqual(self.controller().alertSettings["staleDays"], 90)

    def test_failed_preference_save_keeps_new_alerts_and_reports_session_only_persistence(self):
        self.load()
        with patch.object(self.settings, "sync", side_effect=OSError("read-only profile")):
            self.c.setAlertThresholds(30, 300)
            self.idle()
        self.assertEqual(self.c.alertSettings["staleDays"], 30)
        self.assertEqual(self.category("stale")["count"], 1)
        self.assertTrue(self.c.alertSettings["notice"])
        self.assertTrue(self.c.state["current"])
        self.assertFalse(self.c.state["error"])

    def test_limit_change_reuses_loaded_analysis_and_preserves_page_detail_and_month(self):
        self.load(expanded(70))
        self.c.setPage(2)
        self.c.selectRow(0)
        self.c.setMonthlyPeriod("2026-01")
        before_rows = self.c.table.rows
        before_detail = self.c.detail
        before_month = self.c.monthly
        with (
            patch.object(desktop, "analyze_inventory", side_effect=AssertionError("reloaded stock")),
            patch.object(
                desktop, "analyze_monthly_inventory", side_effect=AssertionError("reloaded history")
            ),
        ):
            self.c.setAlertThresholds(120, 200)
            self.idle()
        self.assertEqual(self.c.state["page"], 2)
        self.assertEqual(self.c.state["selectedRow"], 0)
        self.assertEqual(self.c.table.rows, before_rows)
        self.assertEqual(self.c.detail, before_detail)
        self.assertEqual(self.c.monthly, before_month)
        self.assertEqual(self.category("stale")["count"], 0)
        self.assertEqual(self.category("low_coverage")["count"], 1)
        self.assertFalse(self.c.state["error"])
        self.assertTrue(self.c.state["current"])

    def test_explicit_apply_retries_saving_unchanged_limits_after_storage_recovers(self):
        self.load()
        with patch.object(self.settings, "setValue", side_effect=OSError("read-only profile")):
            self.c.setAlertThresholds(30, 300)
            self.idle()
        before = self.c.alerts
        self.assertTrue(self.c.alertSettings["notice"])
        self.assertIsNone(self.saved_limits())
        with patch.object(
            desktop, "analyze_stock_alerts", side_effect=AssertionError("Unchanged alerts recalculated")
        ):
            self.c.setAlertThresholds(30, 300)
            self.idle()
        self.assertEqual(self.saved_limits(), {"staleDays": 30, "coverageDays": 300})
        self.assertEqual(self.c.alertSettings["notice"], "")
        self.assertEqual(self.c.alerts, before)
        self.assertTrue(self.c.state["current"])

    def test_cancelled_threshold_change_restores_applied_limits_without_saving_pending_values(self):
        self.load()
        before = self.c.alerts
        entered, release = Event(), Event()
        original = desktop.analyze_stock_alerts

        def delayed(*args, **kwargs):
            result = original(*args, **kwargs)
            entered.set()
            if not release.wait(5):
                raise RuntimeError("Test did not release the alerts worker")
            return result

        try:
            with patch.object(desktop, "analyze_stock_alerts", side_effect=delayed):
                self.c.setAlertThresholds(30, 300)
                self.assertTrue(pump(entered.is_set))
                self.assertFalse(self.c.state["current"])
                self.assertEqual(self.c.alerts, before)
                self.assertIsNone(self.saved_limits())
                self.c.cancel()
                release.set()
                self.idle()
            self.assertEqual(self.c.alertSettings["staleDays"], 90)
            self.assertEqual(self.c.alertSettings["coverageDays"], 30)
            self.assertEqual(self.c.alerts, before)
            self.assertIsNone(self.saved_limits())
            self.assertTrue(self.c.state["current"])
        finally:
            release.set()

    def test_latest_threshold_change_wins_over_an_older_worker(self):
        self.load()
        entered, release = Event(), Event()
        original = desktop.analyze_stock_alerts

        def first_waits(*args, **kwargs):
            result = original(*args, **kwargs)
            if not entered.is_set():
                entered.set()
                if not release.wait(5):
                    raise RuntimeError("Test did not release the alerts worker")
            return result

        try:
            with patch.object(desktop, "analyze_stock_alerts", side_effect=first_waits):
                self.c.setAlertThresholds(30, 300)
                self.assertTrue(pump(entered.is_set))
                self.c.setAlertThresholds(120, 400)
                release.set()
                self.idle()
            self.assertEqual(self.saved_limits(), {"staleDays": 120, "coverageDays": 400})
            self.assertEqual(self.c.alertSettings["staleDays"], 120)
            self.assertEqual(self.category("stale")["count"], 0)
            self.assertEqual(self.category("low_coverage")["count"], 2)
            self.assertTrue(self.c.state["current"])
        finally:
            release.set()

    def test_failed_alert_update_preserves_previous_result_until_cancel_restores_currentness(self):
        self.load()
        before_rows, before_alerts = self.c.table.rows, self.c.alerts
        with patch.object(desktop, "analyze_stock_alerts", side_effect=ValueError("synthetic failure")):
            self.c.setAlertThresholds(30, 300)
            self.idle()
        self.assertEqual(self.c.table.rows, before_rows)
        self.assertEqual(self.c.alerts, before_alerts)
        self.assertIn("synthetic failure", self.c.state["error"])
        self.assertFalse(self.c.state["current"])
        self.assertIsNone(self.saved_limits())
        destination = self.directory / "previous-export.xlsx"
        destination.write_bytes(b"previous user export")
        with patch.object(desktop, "export_inventory") as export:
            self.c.exportExcel(QUrl.fromLocalFile(str(destination)))
            self.idle()
            export.assert_not_called()
        self.assertEqual(destination.read_bytes(), b"previous user export")
        self.c.cancel()
        self.idle()
        self.assertTrue(self.c.state["current"])
        self.assertEqual(self.c.alertSettings["staleDays"], 90)

    def test_filter_change_and_threshold_change_publish_one_consistent_scope(self):
        self.load()
        entered, release = Event(), Event()
        original = desktop.analyze_inventory

        def delayed(*args, **kwargs):
            entered.set()
            if not release.wait(5):
                raise RuntimeError("Test did not release the stock worker")
            return original(*args, **kwargs)

        try:
            with patch.object(desktop, "analyze_inventory", side_effect=delayed):
                self.c.setFilter("unit", "L")
                self.assertTrue(pump(entered.is_set))
                self.c.setAlertThresholds(30, 300)
                release.set()
                self.idle()
            self.assertEqual(self.c.state["selection"]["unit"], "L")
            self.assertEqual(self.c.alertSettings["staleDays"], 30)
            for category in self.c.alerts["categories"]:
                self.assertTrue(all(item["unit"] == "L" for item in category["items"]))
            self.assertEqual(self.category("stale")["count"], 1)
            self.assertTrue(self.c.state["current"])
        finally:
            release.set()

    def test_warehouse_filter_marks_coverage_unavailable_without_empty_success(self):
        self.load()
        self.c.setAlertThresholds(30, 300)
        self.idle()
        self.c.setFilter("warehouse", "01")
        self.idle()
        category = self.category("low_coverage")
        self.assertFalse(category["available"])
        self.assertTrue(category["notice"])
        self.assertEqual(category["items"], [])
        self.assertEqual(self.category("stale")["count"], 1)
        self.assertTrue(self.c.state["current"])

    def test_no_observed_sales_is_unknown_coverage_and_a_separate_information_category(self):
        self.load(replace(sample(), sales=()))
        coverage = self.category("low_coverage")
        self.assertFalse(coverage["available"])
        self.assertIn("não representam cobertura zero", coverage["notice"])
        self.assertEqual(coverage["items"], [])
        self.assertEqual(self.category("stale")["count"], 0)
        unobserved = self.category("no_sale")
        self.assertEqual(unobserved["count"], 2)
        self.assertEqual({item["code"] for item in unobserved["items"]}, {"0001", "0002"})
        for item in unobserved["items"]:
            self.assertEqual(item["days"], "Prazo desconhecido")
            self.assertEqual(item["coverage"], "Indisponível")
        self.assertTrue(self.c.state["current"])

    def test_month_without_sales_does_not_erase_previously_observed_sales_or_imply_zero_coverage(self):
        self.load()
        self.c.setFilter("start", "2026-02")
        self.c.setFilter("end", "2026-02")
        self.idle()
        coverage = self.category("low_coverage")
        self.assertFalse(coverage["available"])
        self.assertIn("não representam cobertura zero", coverage["notice"])
        self.assertEqual(coverage["items"], [])
        self.assertEqual(self.category("no_sale")["count"], 0)
        self.assertEqual(self.category("stale")["count"], 0)
        self.assertTrue(self.c.state["current"])

    def test_alert_summary_counts_all_groups_while_presentation_is_bounded(self):
        self.load(expanded(70))
        category = self.category("stale")
        self.assertEqual(category["count"], 70)
        self.assertEqual(len(category["items"]), 8)
        self.assertEqual(len(self.c._alerts.stale), 70)
        self.assertEqual(len({
            (item["code"], item["branch"], item["unit"]) for item in category["items"]
        }), 8)

    def test_focus_alert_selects_product_branch_and_unit_at_once_and_preserves_other_filters(self):
        self.load()
        self.c.setFilter("group", "Solventes")
        self.c.setFilter("warehouse", "01")
        self.c.setFilter("search", "solvente")
        self.idle()
        self.c.setAlertThresholds(30, 300)
        self.idle()
        self.assertEqual(self.category("stale")["count"], 1)
        original = desktop.analyze_inventory
        with patch.object(desktop, "analyze_inventory", wraps=original) as analyze:
            self.c.focusAlertProduct("0002", "01", "L")
            self.idle()
        selected = self.c.state["selection"]
        self.assertEqual(selected["product"], "0002")
        self.assertEqual(selected["branch"], "01")
        self.assertEqual(selected["unit"], "L")
        self.assertEqual(selected["search"], "")
        self.assertEqual(selected["group"], "Solventes")
        self.assertEqual(selected["warehouse"], "01")
        self.assertEqual(analyze.call_count, 1)
        self.assertTrue(self.c.state["current"])

    def test_arbitrary_or_stale_alert_drilldown_does_not_change_selection(self):
        self.load()
        before = self.c.state["selection"]
        self.c.focusAlertProduct("0001", "01", "KG")
        self.assertEqual(self.c.state["selection"], before)
        self.c.focusAlertProduct("invented", "99", "BAD")
        self.assertEqual(self.c.state["selection"], before)
        self.c.setAlertThresholds(30, 300)
        pending = self.c.state["selection"]
        self.c.focusAlertProduct("0002", "01", "L")
        self.assertEqual(self.c.state["selection"], pending)
        self.idle()

    def test_export_in_progress_refuses_rule_changes_and_keeps_the_exported_policy(self):
        self.load()
        entered, release = Event(), Event()
        observed = []

        def delayed(*args, **kwargs):
            observed.append(kwargs["alerts"].policy)
            entered.set()
            if not release.wait(5):
                raise RuntimeError("Test did not release the export worker")

        try:
            with patch.object(desktop, "export_inventory", side_effect=delayed):
                self.c.exportExcel(QUrl.fromLocalFile(str(self.directory / "alerts.xlsx")))
                self.assertTrue(pump(entered.is_set))
                self.c.setAlertThresholds(30, 300)
                self.assertEqual(self.c.alertSettings["staleDays"], 90)
                self.assertEqual(self.c.alertSettings["coverageDays"], 30)
                release.set()
                self.idle()
            self.assertEqual(observed[0].stale_days, 90)
            self.assertEqual(observed[0].coverage_days, 30)
            self.assertIsNone(self.saved_limits())
        finally:
            release.set()
