#!/usr/bin/env python3
"""Check status of all benchmarks from their reports."""

import json
from pathlib import Path

def main():
    """Check status of all benchmarks."""
    project_root = Path(__file__).parent.parent
    benchmarks_root = project_root / "benchmarks" / "data"

    print("\n" + "=" * 80)
    print("BENCHMARK STATUS")
    print("=" * 80)

    passed = 0
    failed = 0
    blocked = 0
    inviavel = 0
    missing = []

    # List all benchmark directories
    benchmark_dirs = sorted([d for d in benchmarks_root.iterdir() if d.is_dir()])

    for bench_dir in benchmark_dirs:
        slug = bench_dir.name

        # Try to find report
        report_path = bench_dir / "artifacts" / "audit" / "benchmark_report.json"

        if not report_path.exists():
            missing.append(slug)
            print(f"  ? {slug:25} NO REPORT")
            failed += 1
            continue

        try:
            report = json.loads(report_path.read_text())
            status = report.get("status_final", "UNKNOWN")

            if status == "APROVADO_COM_RESSALVAS":
                print(f"  ✓ {slug:25} PASSED")
                passed += 1
            elif status == "BLOQUEADO":
                print(f"  ⚠ {slug:25} BLOCKED")
                blocked += 1
            elif status == "INVIAVEL":
                print(f"  ✗ {slug:25} INVIAVEL")
                inviavel += 1
            else:
                print(f"  ? {slug:25} {status}")
                failed += 1
        except Exception as e:
            print(f"  ✗ {slug:25} ERROR: {str(e)[:40]}")
            failed += 1

    total = passed + failed + blocked + inviavel
    print("\n" + "=" * 80)
    print(f"SUMMARY: {passed}/{total} passed")
    print(f"  ✓ Passed:  {passed}")
    print(f"  ⚠ Blocked: {blocked}")
    print(f"  ✗ Inviavel: {inviavel}")
    print(f"  ✗ Failed:  {failed}")
    print("=" * 80 + "\n")

if __name__ == "__main__":
    main()
