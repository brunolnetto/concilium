#!/usr/bin/env python3
"""Run all benchmarks and generate reports."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from concilium.application.runtime import Runtime
from concilium.application.benchmarks.runner import BenchmarkRunner
from concilium.application.benchmarks.spec_loader import load_spec_from_json
from concilium.application.benchmarks.report_builder import BenchmarkReportBuilder
from concilium.application.benchmarks.report_printer import BenchmarkReportPrinter

def main():
    project_root = Path(__file__).parent.parent
    config_root = project_root / "config"
    benchmarks_root = project_root / "benchmarks" / "data"
    projects_root = project_root / "benchmarks" / "projects"  # Store project state separately from reference data

    # Initialize runner
    builder = BenchmarkReportBuilder()
    printer = BenchmarkReportPrinter()
    runner = BenchmarkRunner(
        config_root=config_root,
        projects_root=projects_root,
        report_builder=builder,
        report_printer=printer,
    )

    # Load specs
    benchmarks = sorted([d.name for d in benchmarks_root.iterdir() if d.is_dir() and (d / "referencia.json").exists()])

    print(f"\n{'='*80}")
    print(f"RUNNING {len(benchmarks)} BENCHMARKS")
    print(f"{'='*80}\n")

    for i, slug in enumerate(benchmarks, 1):
        try:
            ref_path = benchmarks_root / slug / "referencia.json"
            spec = load_spec_from_json(ref_path)

            print(f"[{i:2d}/{len(benchmarks)}] {slug:25} ", end="", flush=True)
            result = runner.run(spec, reset=False)
            print("✓ OK")
        except Exception as e:
            print(f"✗ ERROR: {str(e)[:40]}")

    print(f"\n{'='*80}\n")

if __name__ == "__main__":
    main()
