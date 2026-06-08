#!/usr/bin/env python3
"""Fix synthetic CPUs by mapping to real catalog CPUs based on descriptions.

Strategy: For each item with a synthetic CPU, find the best matching real CPU
from the catalog using semantic similarity of descriptions.
"""

import json
import sys
from pathlib import Path
from collections import defaultdict


def search_cpus_by_description(query: str, catalog: dict) -> list:
    """Search for CPUs in catalog matching query description.

    Args:
        query: Description to search for
        catalog: Catalog dict with CPUs

    Returns:
        List of matching CPUs sorted by relevance
    """
    query_lower = query.lower()
    cpus = catalog.get("cpus", [])
    matches = []

    for cpu in cpus:
        desc = str(cpu.get("descricao", "")).lower()
        codigo = str(cpu.get("codigo", "")).lower()

        score = 0
        if query_lower in desc:
            score += 100
        if query_lower in codigo:
            score += 50

        for word in query_lower.split():
            if len(word) > 2 and word in desc:
                score += 10

        if score > 0:
            matches.append((score, cpu))

    matches.sort(key=lambda x: x[0], reverse=True)
    return [cpu for score, cpu in matches]


def fix_benchmark_cpus(slug: str, benchmarks_root: Path, catalog: dict) -> dict:
    """Fix synthetic CPUs in a benchmark by mapping to real catalog CPUs.

    Args:
        slug: Benchmark slug
        benchmarks_root: Path to benchmarks/data
        catalog: Catalog dict with CPUs

    Returns:
        Dict with results: {fixed: int, unfixed: int, errors: list}
    """
    ref_path = benchmarks_root / slug / "referencia.json"
    if not ref_path.exists():
        return {"error": f"referencia.json not found for {slug}"}

    ref = json.loads(ref_path.read_text())
    spec = ref.get("spec", {})
    eap = spec.get("eap", [])

    if not eap:
        return {"error": f"No EAP found for {slug}"}

    # Get existing catalog CPUs
    existing_cpus = {cpu["codigo"] for cpu in catalog.get("cpus", [])}

    fixed_count = 0
    unfixed_count = 0
    errors = []

    # Try to fix each synthetic CPU
    for item in eap:
        cpu_id = item.get("cpu_id", "")
        descricao = item.get("descricao", "")

        # Check if CPU is synthetic (not in catalog)
        if cpu_id not in existing_cpus:
            # Try to map using description
            matches = search_cpus_by_description(descricao, catalog)

            if matches:
                mapped_cpu = matches[0]["codigo"]
                old_cpu = cpu_id
                item["cpu_id"] = mapped_cpu
                fixed_count += 1
            else:
                unfixed_count += 1
                errors.append(f"{item['item_id']}: Could not map '{descricao}'")

    # Save updated referencia if any fixes were made
    if fixed_count > 0:
        ref_path.write_text(json.dumps(ref, indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        "slug": slug,
        "fixed": fixed_count,
        "unfixed": unfixed_count,
        "errors": errors,
    }


def main():
    """Fix synthetic CPUs for all benchmarks."""
    project_root = Path(__file__).parent.parent
    benchmarks_root = project_root / "benchmarks" / "data"

    # Load catalog
    cat_path = project_root / "config" / "catalogos" / "mendeslobo" / ".catalog_bundle.json"
    if not cat_path.exists():
        print(f"❌ Catalog not found at {cat_path}")
        return

    catalog = json.loads(cat_path.read_text())

    # Benchmarks to fix (those with synthetic CPUs)
    slugs = [
        "MARA_ROSA",
        "MATEC_HINES",
        "ODFJELL",
        "ROSH",
        "RUMO",
        "CTC",
        "LUNDIN",
        "MATEC_GUARULHOS",
        "MATEC_UBERLANDIA",
        "PRIVATE_LOG",
        "VALE",
    ]

    print("=" * 70)
    print("FIXING SYNTHETIC CPUs WITH CATALOG MAPPINGS")
    print("=" * 70)

    results = {}
    total_fixed = 0
    total_unfixed = 0

    for slug in slugs:
        result = fix_benchmark_cpus(slug, benchmarks_root, catalog)

        if "error" in result:
            print(f"❌ {slug}: {result['error']}")
            results[slug] = result
        else:
            fixed = result.get("fixed", 0)
            unfixed = result.get("unfixed", 0)
            total_fixed += fixed
            total_unfixed += unfixed

            if fixed > 0 or unfixed == 0:
                status = "✓ OK" if unfixed == 0 else f"⚠ {fixed} fixed, {unfixed} unfixed"
            else:
                status = f"✗ FAILED - {unfixed} items could not be mapped"

            print(f"{slug:25} {status}")
            if result.get("errors"):
                for err in result["errors"][:2]:  # Show first 2 errors
                    print(f"  {err}")

            results[slug] = result

    print("\n" + "=" * 70)
    print(f"SUMMARY: {total_fixed} CPUs fixed, {total_unfixed} unresolved")
    print("=" * 70)

    return results


if __name__ == "__main__":
    main()
