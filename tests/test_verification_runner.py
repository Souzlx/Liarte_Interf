"""The isolated runner never approves missing tests, failed children or retries."""

from copy import deepcopy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools.verification_runner import (
    VerificationGroup,
    VerificationProtocolError,
    group_cases,
    run_isolated,
    validate_module_report,
)


ROOT = Path(__file__).resolve().parent.parent


def synthetic_case(name, module, count=1):
    return type(name, (unittest.TestCase,), {
        "__module__": module,
        **{f"test_{index}": lambda self: None for index in range(count)},
    })


def successful_report(cases, count):
    return {
        "schema": 1, "cases": list(cases), "tests_run": count,
        "passed": count, "failures": 0, "errors": 0, "skipped": 0,
        "expected_failures": 0, "unexpected_successes": 0, "successful": True,
    }


def command_cases(command):
    return tuple(command[index + 1] for index, value in enumerate(command[:-1]) if value == "--case")


def write_report(command, report):
    destination = Path(command[command.index("--result-json") + 1])
    destination.write_text(json.dumps(report), encoding="utf-8")


class VerificationRunnerTests(unittest.TestCase):
    def setUp(self):
        self.first = synthetic_case("FirstCase", "verification_fake_first", 2)
        self.second = synthetic_case("SecondCase", "verification_fake_second", 1)
        self.other_first = synthetic_case("OtherCase", "verification_fake_first", 3)
        self.volume = synthetic_case("VolumeTests", "verification_fake_second", 1)

    def test_registry_classes_are_grouped_once_in_module_and_class_order_including_volume(self):
        groups = group_cases((self.first, self.second, self.other_first, self.volume))
        self.assertEqual(groups, (
            VerificationGroup("verification_fake_first", (
                "verification_fake_first.FirstCase", "verification_fake_first.OtherCase",
            ), 5),
            VerificationGroup("verification_fake_second", (
                "verification_fake_second.SecondCase", "verification_fake_second.VolumeTests",
            ), 2),
        ))

    def test_duplicate_class_names_and_empty_registry_cannot_produce_a_successful_plan(self):
        alias = synthetic_case("FirstCase", "verification_fake_first", 1)
        empty = synthetic_case("EmptyCase", "verification_fake_empty", 0)
        for cases in ((), (empty,), (self.first, self.first), (self.first, alias)):
            with self.subTest(cases=cases), self.assertRaises(VerificationProtocolError):
                group_cases(cases)

    def test_successful_skip_and_expected_failure_reports_preserve_counts(self):
        group = group_cases((self.other_first,))[0]
        report = successful_report(group.cases, 3)
        report.update(passed=1, skipped=1, expected_failures=1)
        checked = validate_module_report(report, group, 0)
        self.assertEqual(checked, report)

    def test_boolean_negative_missing_counts_and_wrong_schema_are_not_accepted(self):
        group = group_cases((self.first,))[0]
        original = successful_report(group.cases, 2)
        mutations = [
            {"schema": True}, {"schema": 2}, {"tests_run": True}, {"tests_run": 0},
            {"tests_run": 1}, {"passed": -1}, {"passed": 3}, {"errors": False},
            {"skipped": 1.0}, {"successful": 1}, {"passed": 1},
        ]
        for change in mutations:
            with self.subTest(change=change), self.assertRaises(VerificationProtocolError):
                validate_module_report({**original, **change}, group, 0)
        for key in original:
            report = dict(original)
            report.pop(key)
            with self.subTest(missing=key), self.assertRaises(VerificationProtocolError):
                validate_module_report(report, group, 0)

    def test_wrong_classes_success_flags_and_exit_codes_cannot_hide_a_failure(self):
        group = group_cases((self.first,))[0]
        report = successful_report(group.cases, 2)
        for change, exit_code in (
            ({"cases": []}, 0),
            ({"cases": list(group.cases) * 2}, 0),
            ({"cases": ["verification_fake_other.FirstCase"]}, 0),
            ({"failures": 1}, 0),
            ({"errors": 1}, 0),
            ({"unexpected_successes": 1}, 0),
            ({}, 1),
            ({"successful": False, "failures": 1, "passed": 1}, 0),
        ):
            with self.subTest(change=change, exit_code=exit_code), self.assertRaises(VerificationProtocolError):
                validate_module_report({**report, **change}, group, exit_code)

    def test_failed_test_report_is_valid_and_remains_a_failed_module(self):
        group = group_cases((self.first,))[0]
        report = successful_report(group.cases, 2)
        report.update(successful=False, failures=1, passed=1)
        self.assertEqual(validate_module_report(report, group, 1), report)

    def test_parent_aggregates_success_skip_and_failed_modules_without_retry(self):
        calls = []

        def execute(command, **kwargs):
            calls.append(command)
            cases = command_cases(command)
            if cases[0].startswith("verification_fake_first"):
                report = successful_report(cases, 2)
                report.update(passed=1, skipped=1)
                exit_code = 0
            else:
                report = successful_report(cases, 1)
                report.update(passed=0, failures=1, successful=False)
                exit_code = 1
            write_report(command, report)
            return SimpleNamespace(returncode=exit_code)

        output = io.StringIO()
        total = run_isolated((self.first, self.second), ROOT, executor=execute, stream=output)
        self.assertFalse(total["successful"])
        self.assertEqual(total["tests_run"], 3)
        self.assertEqual(total["registered_tests"], 3)
        self.assertEqual(total["passed"], 1)
        self.assertEqual(total["skipped"], 1)
        self.assertEqual(total["failures"], 1)
        self.assertEqual(total["errors"], 0)
        self.assertEqual(total["modules"], 2)
        self.assertEqual(len(calls), 2)
        self.assertIn("FAILED", output.getvalue())

    def test_child_crash_missing_corrupt_and_incomplete_reports_fail_without_skipping_next_module(self):
        for damage in ("crash", "missing", "corrupt", "count", "zero"):
            calls = []

            def execute(command, **kwargs):
                calls.append(command)
                cases = command_cases(command)
                if len(calls) == 1:
                    if damage == "crash":
                        return SimpleNamespace(returncode=3221225477)
                    destination = Path(command[command.index("--result-json") + 1])
                    if damage == "corrupt":
                        destination.write_text("not JSON", encoding="utf-8")
                    elif damage in ("count", "zero"):
                        write_report(command, successful_report(cases, 1 if damage == "count" else 0))
                    return SimpleNamespace(returncode=0)
                write_report(command, successful_report(cases, 1))
                return SimpleNamespace(returncode=0)

            with self.subTest(damage=damage):
                total = run_isolated((self.first, self.second), ROOT, executor=execute, stream=io.StringIO())
                self.assertFalse(total["successful"])
                self.assertGreaterEqual(total["errors"], 1)
                self.assertEqual(total["registered_tests"], 3)
                self.assertEqual(len(calls), 2)
                self.assertEqual(command_cases(calls[1]), ("verification_fake_second.SecondCase",))

    def test_spawn_failure_is_reported_and_the_other_module_still_runs_once(self):
        calls = []

        def execute(command, **kwargs):
            calls.append(command)
            if len(calls) == 1:
                raise OSError("controlled process startup failure")
            write_report(command, successful_report(command_cases(command), 1))
            return SimpleNamespace(returncode=0)

        total = run_isolated((self.first, self.second), ROOT, executor=execute, stream=io.StringIO())
        self.assertFalse(total["successful"])
        self.assertGreaterEqual(total["errors"], 1)
        self.assertEqual(len(calls), 2)

    def test_child_receives_headless_environment_without_mutating_the_callers_environment(self):
        calls = []
        original = {
            **os.environ,
            "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software",
            "PYTHONPATH": "synthetic-existing-path", "SYNTHETIC_RUNNER_OPTION": "preserved",
        }
        untouched = deepcopy(original)

        def execute(command, **kwargs):
            calls.append((command, kwargs))
            write_report(command, successful_report(command_cases(command), 2))
            return SimpleNamespace(returncode=0)

        with patch.dict(os.environ, {"SYNTHETIC_PARENT_OPTION": "inherited"}):
            total = run_isolated((self.first,), ROOT, headless=True, executor=execute,
                                 stream=io.StringIO(), environment=original)
        self.assertTrue(total["successful"])
        self.assertEqual(original, untouched)
        command, options = calls[0]
        self.assertIn("--headless", command)
        self.assertEqual(Path(options["cwd"]), ROOT)
        self.assertFalse(options["check"])
        self.assertEqual(options["env"]["QT_QPA_PLATFORM"], "offscreen")
        self.assertEqual(options["env"]["QT_QUICK_BACKEND"], "software")
        self.assertEqual(options["env"]["SYNTHETIC_RUNNER_OPTION"], "preserved")
        self.assertIn("synthetic-existing-path", options["env"]["PYTHONPATH"])
        self.assertFalse(options.get("shell", False))

    def test_real_child_loads_only_requested_classes_and_preserves_a_skip(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "verification_fixture_only.py").write_text(
                "import sys, unittest\n"
                "class SelectedCase(unittest.TestCase):\n"
                "    def test_registry_is_not_imported(self):\n"
                "        self.assertNotIn('tests.test_inventory', sys.modules)\n"
                "    @unittest.skip('synthetic platform condition')\n"
                "    def test_known_skip(self): pass\n",
                encoding="utf-8",
            )
            result = root / "result.json"
            process = subprocess.run(
                [sys.executable, str(ROOT / "verificar.py"), "--headless", "--case",
                 "verification_fixture_only.SelectedCase", "--result-json", str(result)],
                cwd=ROOT, env={**os.environ, "PYTHONPATH": str(root)},
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
            payload = json.loads(result.read_text(encoding="utf-8"))
            self.assertEqual(payload["cases"], ["verification_fixture_only.SelectedCase"])
            self.assertEqual(payload["tests_run"], 2)
            self.assertEqual(payload["passed"], 1)
            self.assertEqual(payload["skipped"], 1)
            self.assertTrue(payload["successful"])

    def test_real_failed_child_reports_failure_and_a_crash_cannot_write_a_success_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "verification_fixture_failure.py").write_text(
                "import os, unittest\n"
                "class FailedCase(unittest.TestCase):\n"
                "    def test_failure(self): self.fail('controlled assertion')\n"
                "class CrashedCase(unittest.TestCase):\n"
                "    def test_crash(self): os._exit(19)\n",
                encoding="utf-8",
            )
            for case, code in (("FailedCase", 1), ("CrashedCase", 19)):
                report = root / (case + ".json")
                with self.subTest(case=case):
                    process = subprocess.run(
                        [sys.executable, str(ROOT / "verificar.py"), "--headless", "--case",
                         "verification_fixture_failure." + case, "--result-json", str(report)],
                        cwd=ROOT, env={**os.environ, "PYTHONPATH": str(root)},
                        capture_output=True, text=True, timeout=30,
                    )
                    self.assertEqual(process.returncode, code, process.stdout + process.stderr)
                    if case == "FailedCase":
                        payload = json.loads(report.read_text(encoding="utf-8"))
                        self.assertFalse(payload["successful"])
                        self.assertEqual(payload["failures"], 1)
                        self.assertEqual(payload["passed"], 0)
                    else:
                        self.assertFalse(report.exists())
