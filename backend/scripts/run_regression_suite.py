#!/usr/bin/env python3
"""Run regressions by severity instead of publishing a misleading pass rate."""
from __future__ import annotations

import json
import os
import sys
import unittest
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _category(test: unittest.TestCase) -> str:
    name = getattr(test, "_testMethodName", "")
    if name.startswith("test_efficiency_"):
        return "efficiency_warnings"
    if name.startswith("test_quality_"):
        return "retrieval_quality_gates"
    return "hard_gates"


class ClassifiedResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.outcomes: dict[str, dict[str, list[str]]] = defaultdict(
            lambda: defaultdict(list)
        )

    def addSuccess(self, test):
        super().addSuccess(test)
        self.outcomes[_category(test)]["passed"].append(test.id())

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.outcomes[_category(test)]["failed"].append(test.id())

    def addError(self, test, err):
        super().addError(test, err)
        self.outcomes[_category(test)]["failed"].append(test.id())

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.outcomes[_category(test)]["skipped"].append(f"{test.id()}: {reason}")


def main() -> None:
    os.chdir(ROOT)
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    runner = unittest.TextTestRunner(
        stream=sys.stderr,
        verbosity=2,
        resultclass=ClassifiedResult,
    )
    result: ClassifiedResult = runner.run(suite)
    report = {}
    for category in ("hard_gates", "retrieval_quality_gates", "efficiency_warnings"):
        outcomes = result.outcomes[category]
        report[category] = {
            "passed": len(outcomes["passed"]),
            "failed": outcomes["failed"],
            "skipped": outcomes["skipped"],
        }
    blocked = bool(
        report["hard_gates"]["failed"]
        or report["retrieval_quality_gates"]["failed"]
    )
    report["deployment_blocked"] = blocked
    report["efficiency_warning_count"] = len(report["efficiency_warnings"]["failed"])
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(1 if blocked else 0)


if __name__ == "__main__":
    main()
