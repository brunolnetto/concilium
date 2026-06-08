#!/usr/bin/env python3
"""
Migration script for ADR-105 implementation.
Converts benchmarks to use new MOB (Mobilização/Desmobilização) 3-phase structure.

Usage:
    python scripts/migrate_adr105.py [--benchmark ODFJELL] [--dry-run]
"""

import json
import sys
from pathlib import Path
from datetime import date
from typing import Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from concilium.application.scheduling.mob_scheduling import infer_mob_windows
from concilium.domain.models.canonical import CanonicalModel


def load_referencia(benchmark_path: str) -> dict:
    """Load referencia.json from benchmark."""
    ref_file = Path(benchmark_path) / "referencia.json"
    if not ref_file.exists():
        raise FileNotFoundError(f"referencia.json not found in {benchmark_path}")
    with open(ref_file) as f:
        return json.load(f)


def save_referencia(data: dict, benchmark_path: str) -> None:
    """Save referencia.json to benchmark."""
    ref_file = Path(benchmark_path) / "referencia.json"
    with open(ref_file, "w") as f:
        json.dump(data, f, indent=2, default=str)


def migrate_benchmark(benchmark_name: str, dry_run: bool = False) -> bool:
    """Migrate a single benchmark to ADR-105 structure."""
    benchmark_path = f"benchmarks/data/{benchmark_name}"

    print(f"\n{'='*70}")
    print(f"Migrating {benchmark_name}...")
    print(f"{'='*70}")

    try:
        # Load data
        referencia = load_referencia(benchmark_path)
        meta = referencia.get("meta", {})
        spec = referencia.get("spec", {})

        # Extract EAP
        spec_eap = spec.get("eap", [])
        if not spec_eap:
            print(f"⚠️  No EAP found, skipping {benchmark_name}")
            return False

        # Build meta dict for infer_mob_windows
        meta_dict = {
            "data_inicio": meta.get("data_inicio"),
            "data_termino": meta.get("data_termino"),
        }

        # Build EAP list
        eap_list = [
            {
                "item_id": item.get("item_id"),
                "predecessores": [
                    {"item_id": p.get("item_id")}
                    for p in item.get("predecessores", [])
                ]
            }
            for item in spec_eap
        ]

        # Infer MOB windows
        mob_windows = infer_mob_windows(meta_dict, eap_list)
        print(f"✓ MOB windows inferred:")
        for fase, window in mob_windows.items():
            print(f"  {fase}: {window['inicio']} → {window['fim']}")

        # Add mob_schedule to referencia (for demonstration)
        # In production, this would be handled by Skill-04
        mob_schedule_serializable = {
            fase: {
                "inicio": window["inicio"].isoformat() if isinstance(window["inicio"], date) else window["inicio"],
                "fim": window["fim"].isoformat() if isinstance(window["fim"], date) else window["fim"],
            }
            for fase, window in mob_windows.items()
        }
        referencia["mob_schedule"] = mob_schedule_serializable

        if dry_run:
            print(f"✓ Dry-run: Would update {benchmark_name}")
            print(f"  mob_schedule keys: {list(mob_schedule_serializable.keys())}")
            return True

        # Save updated referencia
        save_referencia(referencia, benchmark_path)
        print(f"✓ Successfully migrated {benchmark_name}")
        return True

    except Exception as e:
        print(f"✗ Error migrating {benchmark_name}: {e}")
        return False


def main():
    """Run migration for one or all benchmarks."""
    import argparse

    parser = argparse.ArgumentParser(description="Migrate benchmarks to ADR-105")
    parser.add_argument("--benchmark", type=str, default=None,
                       help="Single benchmark to migrate (default: all)")
    parser.add_argument("--dry-run", action="store_true",
                       help="Show what would be done without modifying files")
    parser.add_argument("--list", action="store_true",
                       help="List all available benchmarks")

    args = parser.parse_args()

    # Get list of benchmarks
    benchmarks_dir = Path("benchmarks/data")
    all_benchmarks = [
        d.name for d in benchmarks_dir.iterdir()
        if d.is_dir() and (d / "referencia.json").exists()
    ]
    all_benchmarks.sort()

    if args.list:
        print("Available benchmarks:")
        for b in all_benchmarks:
            print(f"  - {b}")
        return 0

    if args.benchmark:
        # Single benchmark
        if args.benchmark not in all_benchmarks:
            print(f"Benchmark not found: {args.benchmark}")
            return 1
        success = migrate_benchmark(args.benchmark, dry_run=args.dry_run)
        return 0 if success else 1

    # All benchmarks
    print(f"Migrating {len(all_benchmarks)} benchmarks...")
    print(f"Dry-run: {args.dry_run}")

    results = []
    for benchmark in all_benchmarks:
        try:
            success = migrate_benchmark(benchmark, dry_run=args.dry_run)
            results.append((benchmark, success))
        except Exception as e:
            print(f"Fatal error in {benchmark}: {e}")
            results.append((benchmark, False))

    # Summary
    successful = sum(1 for _, success in results if success)
    total = len(results)

    print(f"\n{'='*70}")
    print(f"Migration Summary: {successful}/{total} successful")
    print(f"{'='*70}")

    if successful < total:
        print("\nFailed benchmarks:")
        for name, success in results:
            if not success:
                print(f"  - {name}")
        return 1

    if not args.dry_run:
        print("\n✓ All benchmarks migrated successfully!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
