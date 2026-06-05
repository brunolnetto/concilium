#!/usr/bin/env python
"""Migration script for NEP-039: Initialize benchmark metadata from existing data.

Usage:
    python scripts/migrate_benchmarks_to_nep039.py

This script:
1. Discovers all benchmarks in benchmarks/data/
2. Creates BenchmarkMetadata for each based on referencia.json or defaults
3. Stores metadata in benchmarks/data/.nep039/metadata/ (JSON format)
4. Prints summary of initialized benchmarks
"""

import json
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.concilium.domain.benchmark.models import BenchmarkMetadata
from src.concilium.infrastructure.storage.benchmark_store import FileSystemBenchmarkStore


def extract_metadata_from_referencia(ref_path: Path) -> dict:
    """Extract metadata fields from referencia.json if it exists."""
    defaults = {
        "nome": None,
        "origem": None,
        "tags": [],
    }

    if not ref_path.exists():
        return defaults

    try:
        data = json.loads(ref_path.read_text(encoding="utf-8"))
    except Exception:
        return defaults

    # Try to extract from v2 schema (meta block)
    if isinstance(data, dict) and "meta" in data:
        meta = data["meta"]
        if isinstance(meta, dict):
            defaults["nome"] = meta.get("projeto", None)
            defaults["origem"] = meta.get("projeto", None)
            defaults["tags"] = ["real", "benchmark"]

    # Fallback: try to use projeto field at root if exists
    if not defaults["nome"] and isinstance(data, dict):
        defaults["nome"] = data.get("projeto_nome", data.get("projeto", None))
        if "obra_type" in data:
            defaults["tags"].append(data["obra_type"])

    return defaults


def get_file_mtime(path: Path) -> datetime:
    """Get file modification time or current time if file doesn't exist."""
    try:
        return datetime.fromtimestamp(path.stat().st_mtime)
    except FileNotFoundError:
        return datetime.now()


def migrate_benchmarks():
    """Discover and migrate all benchmarks."""
    benchmarks_root = project_root / "benchmarks" / "data"
    if not benchmarks_root.exists():
        print(f"[ERROR] Benchmarks root not found: {benchmarks_root}")
        return False

    # List all benchmark directories
    benchmark_dirs = sorted([
        d for d in benchmarks_root.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    ])

    if not benchmark_dirs:
        print(f"[WARNING] No benchmarks found in {benchmarks_root}")
        return True

    # Initialize benchmark store (creates .nep039/metadata/ if needed)
    nep039_root = benchmarks_root / ".nep039"
    store = FileSystemBenchmarkStore(root=nep039_root)

    print(f"[*] Discovered {len(benchmark_dirs)} benchmarks")
    print(f"[*] Storing metadata in: {nep039_root / 'metadata'}")
    print()

    successful = []
    errors = []

    for bench_dir in benchmark_dirs:
        benchmark_id = bench_dir.name
        print(f"[.] Processing: {benchmark_id}", end=" ... ")

        # Try to find referencia.json
        ref_path = bench_dir / "referencia.json"
        if not ref_path.exists():
            ref_path = bench_dir / "artifacts" / "inputs" / "referencia.json"

        # Extract metadata
        extracted = extract_metadata_from_referencia(ref_path)
        nome = extracted["nome"] or f"{benchmark_id} — Benchmark"
        origem = extracted["origem"] or f"{benchmark_id} — Obra real"
        tags = extracted["tags"] or ["benchmark", benchmark_id.lower()]

        # Get creation date from referencia.json or current time
        criado_em = get_file_mtime(ref_path)

        try:
            # Create metadata
            meta = BenchmarkMetadata(
                benchmark_id=benchmark_id,
                nome=nome,
                origem=origem,
                tags=tags,
                criado_em=criado_em,
                versao=1,
                imutavel=False,  # Start mutable; mark immutable after first execution
            )

            # Save to store
            store.save_metadata(meta)
            successful.append(benchmark_id)
            print("[OK] v1 saved")

        except Exception as e:
            errors.append((benchmark_id, str(e)))
            print(f"[ERROR] {type(e).__name__}: {e}")

    print()
    print("=" * 60)
    print("MIGRATION SUMMARY")
    print("=" * 60)
    print(f"[OK] Successful: {len(successful)}/{len(benchmark_dirs)}")
    for bid in successful:
        print(f"   * {bid}")

    if errors:
        print()
        print(f"[ERROR] Errors: {len(errors)}")
        for bid, err in errors:
            print(f"   * {bid}: {err}")

    print()
    metadata_dir = nep039_root / "metadata"
    if metadata_dir.exists():
        metadata_files = list(metadata_dir.glob("*.json"))
        print(f"[*] Metadata files created: {len(metadata_files)}")
        print(f"[*] Location: {metadata_dir}")

    print()
    success = len(errors) == 0
    if success:
        print("[SUCCESS] Migration completed successfully!")
    else:
        print("[WARNING] Migration completed with errors")

    return success


if __name__ == "__main__":
    try:
        success = migrate_benchmarks()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"[ERROR] Fatal error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
