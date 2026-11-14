"""Fail when a pytest JUnit report exceeds documented time budgets (#24).

Stdlib only. Budgets keep conformance suites from silently becoming
impractical: a single test over --max-test-seconds or the whole report over
--max-total-seconds fails with the offending test names and times.
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def durations(report: Path) -> list[tuple[str, float]]:
    root = ET.parse(report).getroot()
    cases = root.iter("testcase")
    result = [(f"{case.get('classname', '')}::{case.get('name', '')}", float(case.get("time", "0"))) for case in cases]
    if not result:
        raise ValueError(f"{report} has no test cases")
    return result


def check(report: Path, max_test: float, max_total: float) -> list[str]:
    rows = durations(report)
    errors = [
        f"{name}: {seconds:.1f}s > {max_test:.0f}s per-test budget" for name, seconds in rows if seconds > max_test
    ]
    total = sum(seconds for _name, seconds in rows)
    if total > max_total:
        errors.append(f"total {total:.1f}s > {max_total:.0f}s suite budget ({len(rows)} tests)")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--max-test-seconds", type=float, required=True)
    parser.add_argument("--max-total-seconds", type=float, required=True)
    args = parser.parse_args(argv)
    try:
        errors = check(args.junit, args.max_test_seconds, args.max_total_seconds)
    except (OSError, ET.ParseError, ValueError) as exc:
        print(f"::error::Budget report unavailable; refusing to pass: {exc}")
        return 1
    for error in errors:
        print(f"::error::{error}")
    if not errors:
        print(f"Within budget: <= {args.max_test_seconds:.0f}s per test, <= {args.max_total_seconds:.0f}s total.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
