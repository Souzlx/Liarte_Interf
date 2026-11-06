"""Offline reconciliation commands preserve inputs and keep console output bounded."""

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tools import reconcile_inventory as cli


def cli_report(status="equal"):
    return {
        "format": "liarte.inventory.reconciliation/1",
        "source": {"sourceName": "source.pbix", "sourceHash": "a" * 64, "asOf": "2032-04-15"},
        "app": {"sourceName": "base.liarte", "sourceHash": "a" * 64, "asOf": "2032-04-15"},
        "context": {"scope": "all"},
        "comparable": status != "not_comparable",
        "status": status,
        "checks": {
            "total": 3,
            "passed": 3 if status == "equal" else 2,
            "different": int(status == "different"),
            "missing": 0,
            "extra": 0,
            "unknown": 0,
        },
        "sections": {},
        "differences": ()
        if status == "equal"
        else (
            {
                "section": "balances",
                "product": "EMPRESA-PRIVADA-937",
                "branch": "F1",
                "warehouse": "A1",
                "unit": "KG",
                "day": "",
                "period": "",
                "metric": "quantity",
                "scale": 1_000_000,
                "valueUnit": "KG",
                "sourceValue": 98765432123456789,
                "appValue": 0,
                "difference": -98765432123456789,
                "sourcePresent": True,
                "appPresent": True,
                "status": "different",
            },
        ),
    }


class InventoryReconciliationCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.pbix = self.directory / "source.pbix"
        self.pbix.write_bytes(b"synthetic source placeholder")
        self.base = self.directory / "base.liarte"
        self.base.write_bytes(b"synthetic snapshot placeholder")
        self.output = self.directory / "report.json"

    def run_main(self, arguments, *, status="equal", load_error=None, export_error=None):
        source, data = object(), object()
        out, err = io.StringIO(), io.StringIO()
        with (
            patch.object(cli, "read_pbix_reference", return_value=source) as reference,
            patch.object(cli, "read_pbix", return_value=data, side_effect=load_error) as load,
            patch.object(cli, "read_snapshot", return_value=data) as snapshot,
            patch.object(cli, "reconcile_inventory", return_value=cli_report(status)) as compare,
            patch.object(
                cli,
                "export_inventory_reconciliation",
                side_effect=export_error,
                return_value=self.output,
            ) as export,
            redirect_stdout(out),
            redirect_stderr(err),
        ):
            code = cli.main(arguments)
        return code, out.getvalue(), err.getvalue(), reference, load, snapshot, compare, export

    def arguments(self, *extra):
        return ["--pbix", str(self.pbix), "--output", str(self.output), *extra]

    def test_without_snapshot_imports_pbix_and_checks_against_independent_reference(self):
        code, out, err, reference, load, snapshot, compare, export = self.run_main(self.arguments())
        self.assertEqual(code, 0, err)
        reference.assert_called_once()
        load.assert_called_once()
        snapshot.assert_not_called()
        compare.assert_called_once()
        self.assertIs(compare.call_args.args[0], reference.return_value)
        self.assertIs(compare.call_args.args[1], load.return_value)
        export.assert_called_once()
        self.assertEqual(export.call_args.args[0]["status"], "equal")
        self.assertIn("report.json", out)
        self.assertEqual(err, "")

    def test_snapshot_option_does_not_import_pbix_again(self):
        result = self.run_main(self.arguments("--base", str(self.base)))
        code, _, err, reference, load, snapshot, compare, _ = result
        self.assertEqual(code, 0, err)
        reference.assert_called_once()
        load.assert_not_called()
        snapshot.assert_called_once()
        self.assertIs(compare.call_args.args[1], snapshot.return_value)

    def test_difference_and_incompatible_revision_have_distinct_machine_exit_codes(self):
        for status, expected in (("different", 1), ("not_comparable", 2)):
            with self.subTest(status=status):
                result = self.run_main(self.arguments(), status=status)
                self.assertEqual(result[0], expected, result[2])
                self.assertEqual(result[-1].call_args.args[0]["status"], status)

    def test_console_does_not_print_private_product_identifiers_or_numeric_rows(self):
        result = self.run_main(self.arguments(), status="different")
        rendered = result[1] + result[2]
        self.assertNotIn("EMPRESA-PRIVADA-937", rendered)
        self.assertNotIn("98765432123456789", rendered)
        self.assertLess(len(rendered), 1200)

    def test_load_failure_is_sanitized_and_does_not_publish_report(self):
        result = self.run_main(
            self.arguments(), load_error=ValueError("EMPRESA-PRIVADA-937 senha=segredo")
        )
        self.assertEqual(result[0], 2)
        self.assertNotIn("EMPRESA-PRIVADA-937", result[1] + result[2])
        self.assertNotIn("segredo", result[1] + result[2])
        result[-2].assert_not_called()
        result[-1].assert_not_called()
        self.assertFalse(self.output.exists())

    def test_export_failure_is_sanitized_without_overwriting_existing_report(self):
        self.output.write_bytes(b"previous valid report")
        result = self.run_main(
            self.arguments(), export_error=OSError("network-user-password-private")
        )
        self.assertEqual(result[0], 2)
        self.assertNotIn("network-user-password-private", result[1] + result[2])
        self.assertEqual(self.output.read_bytes(), b"previous valid report")

    def test_keyboard_interrupt_returns_cancel_code_without_publishing(self):
        result = self.run_main(self.arguments(), load_error=KeyboardInterrupt())
        self.assertEqual(result[0], 130)
        result[-1].assert_not_called()
        self.assertFalse(self.output.exists())

    def test_missing_source_and_unsupported_output_do_not_start_extraction(self):
        for pbix, output in (
            (self.directory / "absent.pbix", self.output),
            (self.pbix, self.directory / "report.csv"),
        ):
            with self.subTest(pbix=pbix, output=output):
                result = self.run_main(["--pbix", str(pbix), "--output", str(output)])
                self.assertEqual(result[0], 2)
                result[3].assert_not_called()
                result[4].assert_not_called()
                result[-1].assert_not_called()

    def test_output_symlink_to_either_input_is_rejected_before_extraction(self):
        for target in (self.pbix, self.base):
            with self.subTest(target=target):
                alias = self.directory / "alias.json"
                try:
                    alias.symlink_to(target)
                except OSError as error:
                    self.skipTest(f"Symlinks unavailable: {error}")
                original = target.read_bytes()
                result = self.run_main(
                    [
                        "--pbix",
                        str(self.pbix),
                        "--base",
                        str(self.base),
                        "--output",
                        str(alias),
                    ]
                )
                self.assertEqual(result[0], 2)
                self.assertEqual(target.read_bytes(), original)
                result[3].assert_not_called()
                result[-1].assert_not_called()
                alias.unlink()

    def test_output_hardlink_to_source_is_rejected_before_extraction(self):
        alias = self.directory / "alias.json"
        try:
            os.link(self.pbix, alias)
        except OSError as error:
            self.skipTest(f"Hardlinks unavailable: {error}")
        result = self.run_main(["--pbix", str(self.pbix), "--output", str(alias)])
        self.assertEqual(result[0], 2)
        self.assertEqual(self.pbix.read_bytes(), b"synthetic source placeholder")
        result[3].assert_not_called()
        result[-1].assert_not_called()

    def test_input_changed_during_calculation_does_not_publish_a_report(self):
        for changed in (self.pbix, self.base):
            with self.subTest(changed=changed):
                self.output.write_bytes(b"previous valid report")

                def compare(*_args, **_kwargs):
                    changed.write_bytes(changed.read_bytes() + b" changed revision")
                    return cli_report()

                with (
                    patch.object(cli, "read_pbix_reference", return_value=object()),
                    patch.object(cli, "read_pbix", return_value=object()),
                    patch.object(cli, "read_snapshot", return_value=object()),
                    patch.object(cli, "reconcile_inventory", side_effect=compare),
                    patch.object(cli, "export_inventory_reconciliation") as export,
                    redirect_stdout(io.StringIO()),
                    redirect_stderr(io.StringIO()),
                ):
                    code = cli.main(self.arguments("--base", str(self.base)))
                self.assertEqual(code, 2)
                export.assert_not_called()
                self.assertEqual(self.output.read_bytes(), b"previous valid report")

    def test_report_argument_remains_unchanged_by_cli(self):
        report = cli_report("different")
        before = deepcopy(report)
        with (
            patch.object(cli, "read_pbix_reference", return_value=object()),
            patch.object(cli, "read_pbix", return_value=object()),
            patch.object(cli, "reconcile_inventory", return_value=report),
            patch.object(cli, "export_inventory_reconciliation") as export,
            redirect_stdout(io.StringIO()),
            redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(cli.main(self.arguments()), 1)
        self.assertEqual(report, before)
        self.assertIs(export.call_args.args[0], report)

    def test_input_changed_during_real_serialization_is_rejected_before_publication(self):
        real_export = cli.export_inventory_reconciliation
        for changed in (self.pbix, self.base):
            with self.subTest(changed=changed):
                self.output.write_bytes(b"previous valid report")
                before = set(self.directory.iterdir())
                guards = []

                def export_after_source_change(report, path, *, cancel=None, before_publish=None):
                    self.assertTrue(callable(before_publish))

                    def changed_at_publication():
                        guards.append(True)
                        changed.write_bytes(changed.read_bytes() + b" changed during generation")
                        before_publish()

                    return real_export(
                        report, path, cancel=cancel, before_publish=changed_at_publication
                    )

                with (
                    patch.object(cli, "read_pbix_reference", return_value=object()),
                    patch.object(cli, "read_snapshot", return_value=object()),
                    patch.object(cli, "reconcile_inventory", return_value=cli_report()),
                    patch.object(
                        cli,
                        "export_inventory_reconciliation",
                        side_effect=export_after_source_change,
                    ),
                    redirect_stdout(io.StringIO()),
                    redirect_stderr(io.StringIO()),
                ):
                    code = cli.main(self.arguments("--base", str(self.base)))
                self.assertEqual(code, 2)
                self.assertEqual(guards, [True])
                self.assertEqual(self.output.read_bytes(), b"previous valid report")
                self.assertEqual(set(self.directory.iterdir()), before)
