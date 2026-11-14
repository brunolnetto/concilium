"""Budget checker for the nightly golden E2E suite (#24)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / "scripts/check_test_budget.py"
spec = importlib.util.spec_from_file_location("check_test_budget", SCRIPT)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def _report(tmp_path: Path, *times: float) -> Path:
    cases = "".join(f'<testcase classname="m" name="t{i}" time="{t}"/>' for i, t in enumerate(times))
    path = tmp_path / "junit.xml"
    path.write_text(f'<testsuites><testsuite name="s">{cases}</testsuite></testsuites>', encoding="utf-8")
    return path


def test_within_budget_passes(tmp_path: Path) -> None:
    assert (
        module.main(
            ["--junit", str(_report(tmp_path, 10, 20)), "--max-test-seconds", "30", "--max-total-seconds", "60"]
        )
        == 0
    )


def test_slow_test_and_total_are_named(tmp_path: Path) -> None:
    errors = module.check(_report(tmp_path, 10, 45), 30, 50)
    assert errors == ["m::t1: 45.0s > 30s per-test budget", "total 55.0s > 50s suite budget (2 tests)"]


def test_missing_or_empty_report_fails_closed(tmp_path: Path) -> None:
    assert (
        module.main(["--junit", str(tmp_path / "absent.xml"), "--max-test-seconds", "1", "--max-total-seconds", "1"])
        == 1
    )
    assert module.main(["--junit", str(_report(tmp_path)), "--max-test-seconds", "1", "--max-total-seconds", "1"]) == 1
