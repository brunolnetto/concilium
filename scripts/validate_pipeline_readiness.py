#!/usr/bin/env python3
"""Validate if benchmarks have sufficient data for pipeline execution."""

import json
from pathlib import Path
from typing import Any, Dict, List

def load_catalog(project_root: Path) -> Dict[str, Any]:
    """Load the catalog."""
    cat_path = project_root / "config/catalogos/mendeslobo/.catalog_bundle.json"
    if cat_path.exists():
        return json.loads(cat_path.read_text())
    return {}

def check_pipeline_readiness(slug: str, ref_path: Path, catalog: Dict) -> Dict[str, Any]:
    """Check if a benchmark has sufficient data for pipeline execution."""
    result = {
        "slug": slug,
        "ready": True,
        "issues": [],
        "checks": {}
    }

    if not ref_path.exists():
        result["ready"] = False
        result["issues"].append("referencia.json not found")
        return result

    try:
        ref = json.loads(ref_path.read_text())
    except json.JSONDecodeError as e:
        result["ready"] = False
        result["issues"].append(f"Invalid JSON: {e}")
        return result

    spec = ref.get("spec", {})
    meta = ref.get("meta", {})

    # Check 1: EAP has items
    eap = spec.get("eap", [])
    result["checks"]["eap_items"] = len(eap)
    if not eap:
        result["ready"] = False
        result["issues"].append("EAP is empty")

    # Check 2: All CPUs exist in catalog
    cpus = {cpu["codigo"]: cpu for cpu in catalog.get("cpus", [])}
    unmapped_cpus = []
    for item in eap:
        cpu_id = item.get("cpu_id")
        if cpu_id and cpu_id not in cpus:
            unmapped_cpus.append((item.get("item_id"), cpu_id))

    result["checks"]["unmapped_cpus"] = len(unmapped_cpus)
    if unmapped_cpus:
        result["ready"] = False
        for item_id, cpu_id in unmapped_cpus[:2]:
            result["issues"].append(f"CPU '{cpu_id}' not in catalog (item {item_id})")

    # Check 3: Cronograma has distributions
    cronograma = spec.get("cronograma", [])
    result["checks"]["cronograma_items"] = len(cronograma)

    cron_populated = 0
    for item in cronograma:
        semanas = item.get("semanas", {})
        if semanas:
            cron_populated += 1

    result["checks"]["cronograma_populated"] = cron_populated
    if cron_populated == 0 and cronograma:
        result["issues"].append("Cronograma is empty (no semanas distributions)")

    # Check 4: BDI structure
    bdi = spec.get("bdi", {})
    has_bdi = bool(bdi and any(isinstance(v, dict) for v in bdi.values()))
    result["checks"]["bdi_valid"] = has_bdi
    if not has_bdi:
        result["issues"].append("BDI is not properly populated")

    # Check 5: Meta has dates
    has_dates = meta.get("data_inicio") and meta.get("data_termino")
    result["checks"]["project_dates"] = has_dates
    if not has_dates:
        result["issues"].append("Project dates missing")

    # Check 6: All items have non-zero quantitativo
    zero_qty = [item.get("item_id") for item in eap if not item.get("quantitativo") or item.get("quantitativo") == 0]
    result["checks"]["items_with_zero_qty"] = len(zero_qty)
    if zero_qty:
        result["issues"].append(f"{len(zero_qty)} items have zero quantitativo")

    # Overall readiness
    result["ready"] = len(result["issues"]) == 0

    return result

def main():
    project_root = Path(__file__).resolve().parent.parent
    benchmarks_root = project_root / "benchmarks" / "data"
    catalog = load_catalog(project_root)

    print("\n" + "=" * 90)
    print("PIPELINE EXECUTION READINESS CHECK")
    print("=" * 90)

    ref_files = sorted(benchmarks_root.glob("*/referencia.json"))
    ready_count = 0
    all_results = []

    for ref_path in ref_files:
        slug = ref_path.parent.name
        result = check_pipeline_readiness(slug, ref_path, catalog)
        all_results.append(result)

        if result["ready"]:
            ready_count += 1
            status = "✓"
        else:
            status = "✗"

        print(f"\n{status} {slug:25}", end="")
        print(f"  EAP: {result['checks'].get('eap_items', 0):2} items", end="")
        print(f"  Cronograma: {result['checks'].get('cronograma_populated', 0):2}/{result['checks'].get('cronograma_items', 0)} populated")

        if result["issues"]:
            for issue in result["issues"]:
                print(f"    → {issue}")

    print("\n" + "=" * 90)
    print(f"READY FOR PIPELINE: {ready_count}/{len(all_results)}")
    print("=" * 90 + "\n")

    return all_results

if __name__ == "__main__":
    main()
