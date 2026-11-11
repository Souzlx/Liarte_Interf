"""Fresh-process execution of the registered test modules, without retries."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import importlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import unittest


class VerificationProtocolError(RuntimeError):
    """A child did not demonstrate execution of its exact registered cases."""


@dataclass(frozen=True, slots=True)
class VerificationGroup:
    module: str
    cases: tuple[str, ...]
    expected_tests: int


COUNTERS = (
    "tests_run", "passed", "failures", "errors", "skipped",
    "expected_failures", "unexpected_successes",
)
NAME = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+")


def group_cases(cases):
    groups, seen = OrderedDict(), set()
    for case in cases:
        if not isinstance(case, type) or not issubclass(case, unittest.TestCase):
            raise VerificationProtocolError("O registro contém uma classe de teste inválida.")
        name = case.__module__ + "." + case.__qualname__
        if not NAME.fullmatch(name) or name in seen:
            raise VerificationProtocolError("O registro contém uma classe duplicada ou inválida: " + name)
        count = unittest.defaultTestLoader.loadTestsFromTestCase(case).countTestCases()
        if count <= 0:
            raise VerificationProtocolError("A classe registrada não contém testes: " + name)
        seen.add(name)
        names, counts = groups.setdefault(case.__module__, ([], []))
        names.append(name)
        counts.append(count)
    if not seen:
        raise VerificationProtocolError("O registro de testes está vazio.")
    return tuple(VerificationGroup(module, tuple(names), sum(counts))
                 for module, (names, counts) in groups.items())


class ReportingResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.passed = 0

    def addSuccess(self, test):
        super().addSuccess(test)
        self.passed += 1


def run_case_names(names, result_path):
    """Load only the requested classes; Qt runtime is configured by the caller."""
    if not names or len(set(names)) != len(names):
        raise VerificationProtocolError("A seleção do processo de teste está vazia ou duplicada.")
    suite = unittest.TestSuite()
    for name in names:
        if not NAME.fullmatch(name):
            raise VerificationProtocolError("Identificação de classe inválida.")
        module_name, class_name = name.rsplit(".", 1)
        case = getattr(importlib.import_module(module_name), class_name)
        if not isinstance(case, type) or not issubclass(case, unittest.TestCase):
            raise VerificationProtocolError("A seleção não identifica uma classe unittest: " + name)
        if case.__module__ + "." + case.__qualname__ != name:
            raise VerificationProtocolError("A classe carregada difere do registro: " + name)
        suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(case))
    if suite.countTestCases() <= 0:
        raise VerificationProtocolError("O processo não recebeu testes executáveis.")
    result = unittest.TextTestRunner(verbosity=2, resultclass=ReportingResult).run(suite)
    payload = {
        "schema": 1, "cases": list(names), "tests_run": result.testsRun,
        "passed": result.passed, "failures": len(result.failures), "errors": len(result.errors),
        "skipped": len(result.skipped), "expected_failures": len(result.expectedFailures),
        "unexpected_successes": len(result.unexpectedSuccesses),
        "successful": result.wasSuccessful(),
    }
    Path(result_path).write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0 if payload["successful"] else 1


def validate_module_report(report, group, returncode):
    if type(returncode) is not int or returncode not in (0, 1):
        raise VerificationProtocolError(f"O processo terminou de forma anormal (saída {returncode}).")
    if not isinstance(report, dict) or type(report.get("schema")) is not int or report["schema"] != 1:
        raise VerificationProtocolError("O processo não entregou um relatório reconhecido.")
    if report.get("cases") != list(group.cases):
        raise VerificationProtocolError("O processo executou outra seleção de classes.")
    if any(type(report.get(key)) is not int or report[key] < 0 for key in COUNTERS):
        raise VerificationProtocolError("Contadores de teste inválidos no relatório.")
    if report["tests_run"] != group.expected_tests or report["tests_run"] <= 0:
        raise VerificationProtocolError("A contagem executada difere dos testes registrados.")
    if report["passed"] > report["tests_run"] or type(report.get("successful")) is not bool:
        raise VerificationProtocolError("O resultado dos testes é inconsistente.")
    successful = not (report["failures"] or report["errors"] or report["unexpected_successes"])
    if report["successful"] != successful or (returncode == 0) != successful:
        raise VerificationProtocolError("O código de saída contradiz o relatório de testes.")
    if successful and sum(report[key] for key in ("passed", "skipped", "expected_failures")) != report["tests_run"]:
        raise VerificationProtocolError("Nem todos os testes executados possuem resultado.")
    return report


def run_isolated(cases, root, *, headless=False, executor=None, stream=None, environment=None):
    """Run each registered module once and fail on crashes or missing coverage."""
    groups = group_cases(cases)
    root = Path(root).resolve()
    executor = executor or subprocess.run
    stream = stream or sys.stderr
    env = dict(os.environ if environment is None else environment)
    if headless:
        env.setdefault("QT_QPA_PLATFORM", "offscreen")
        env.setdefault("QT_QUICK_BACKEND", "software")
    env.setdefault("PYTHONUTF8", "1")
    env["PYTHONUNBUFFERED"] = "1"
    totals = dict.fromkeys(COUNTERS, 0)
    totals.update(registered_tests=sum(group.expected_tests for group in groups), modules=len(groups))
    started = time.monotonic()
    print(f"Isolamento: {len(groups)} módulos, {totals['registered_tests']} testes registrados.", file=stream, flush=True)
    with tempfile.TemporaryDirectory(prefix="liarte-test-modules-") as temporary:
        for position, group in enumerate(groups):
            report_path = Path(temporary) / f"{position:03d}.json"
            command = [sys.executable, str(root / "verificar.py")]
            if headless:
                command.append("--headless")
            for name in group.cases:
                command.extend(("--case", name))
            command.extend(("--result-json", str(report_path)))
            print(f"Módulo {position + 1}/{len(groups)}: {group.module} ({group.expected_tests} testes)", file=stream, flush=True)
            try:
                process = executor(command, cwd=root, env=env, check=False)
                if not report_path.is_file() or report_path.stat().st_size > 1_048_576:
                    raise VerificationProtocolError(
                        f"Processo sem relatório final válido (saída {process.returncode})."
                    )
                report = json.loads(report_path.read_text(encoding="utf-8"))
                validate_module_report(report, group, process.returncode)
            except (OSError, ValueError, TypeError, subprocess.SubprocessError, VerificationProtocolError) as exc:
                totals["errors"] += 1
                print(f"ERROR: {group.module}: {exc}", file=stream, flush=True)
                continue
            for counter in COUNTERS:
                totals[counter] += report[counter]
    if totals["tests_run"] != totals["registered_tests"] and not totals["errors"]:
        totals["errors"] += 1
    totals["seconds"] = time.monotonic() - started
    totals["successful"] = not (totals["failures"] or totals["errors"] or totals["unexpected_successes"])
    print(f"\nRan {totals['tests_run']} tests in {totals['seconds']:.3f}s\n", file=stream)
    if totals["successful"]:
        print("OK" + (f" (skipped={totals['skipped']})" if totals["skipped"] else ""), file=stream, flush=True)
    else:
        print(f"FAILED (failures={totals['failures']}, errors={totals['errors']}, unexpected successes={totals['unexpected_successes']})", file=stream, flush=True)
    return totals
