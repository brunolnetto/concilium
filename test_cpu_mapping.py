#!/usr/bin/env python3
"""Test script to enrich all benchmarks with semantic CPU mapping."""

from pathlib import Path
from src.concilium.application.benchmarks.referencia_enricher import enrich_benchmark_referencia

# Get all benchmark directories
benchmarks_dir = Path("benchmarks/data")
benchmark_dirs = sorted([d for d in benchmarks_dir.iterdir() if d.is_dir()])

print(f"Found {len(benchmark_dirs)} benchmarks\n")

results = {}
for benchmark_dir in benchmark_dirs:
    benchmark_name = benchmark_dir.name
    print(f"Processing {benchmark_name}...", end=" ", flush=True)

    try:
        success = enrich_benchmark_referencia(benchmark_dir)
        results[benchmark_name] = "✓" if success else "✗"
        print()
    except Exception as e:
        results[benchmark_name] = f"❌ {str(e)[:50]}"
        print(f"Error: {e}")

print("\n" + "="*60)
print("Summary:")
print("="*60)
for name, status in results.items():
    print(f"{name:20} {status}")
