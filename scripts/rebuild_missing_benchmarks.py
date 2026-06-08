#!/usr/bin/env python3
"""Rebuild ODFJELL and MATEC_GUARULHOS EAP from planejamento.txt."""

import json
import re
from pathlib import Path

def parse_planejamento_txt(path: Path) -> list[dict]:
    """Extract items from planejamento.txt TSV format."""
    items = []
    lines = path.read_text().split("\n")

    # Skip header lines (3 lines)
    for line in lines[3:]:
        if not line.strip() or line.startswith("-"):
            continue

        parts = line.split("\t", 3)  # Take first 4 columns
        if len(parts) < 2:
            continue

        item_id = parts[0].strip()
        descricao = parts[1].strip() if len(parts) > 1 else ""

        # Skip if not a valid item ID
        if not item_id or not item_id[0].isdigit():
            continue

        # Skip section headers (like "SUPRESSÃO")
        if len(item_id) == 1 and not descricao:
            continue

        # For section items (1, 2, 3), use as grouping header, skip
        if "." not in item_id:
            continue

        # Extract quantitativo and other fields if available
        quant_str = parts[2].strip() if len(parts) > 2 else "0"
        try:
            quantitativo = float(quant_str.replace(",", ".").replace(".", ""))
        except:
            quantitativo = 0.0

        items.append({
            "item_id": item_id,
            "descricao": descricao,
            "quantitativo": quantitativo,
            "cpu_id": ""  # Will be mapped later
        })

    return items


def map_cpu_for_item(descricao: str, item_id: str, catalog_cpus: dict) -> str:
    """Find best matching CPU from catalog for item description."""
    desc_lower = descricao.lower()
    best_cpu = None
    best_score = 0

    for cpu_codigo, cpu in catalog_cpus.items():
        cpu_desc = str(cpu.get("descricao", "")).lower()

        # Score based on keyword matching
        score = 0

        # Full match is best
        if desc_lower == cpu_desc:
            score += 1000

        # Substring match
        if desc_lower in cpu_desc or cpu_desc in desc_lower:
            score += 100

        # Keyword matching
        keywords = [w for w in desc_lower.split() if len(w) > 3]
        for kw in keywords:
            if kw in cpu_desc:
                score += 10

        if score > best_score:
            best_score = score
            best_cpu = cpu_codigo

    return best_cpu or "CPU-UNKNOWN"


def rebuild_benchmark(slug: str, project_root: Path):
    """Rebuild EAP for a single benchmark."""
    benchmarks_root = project_root / "benchmarks" / "data" / slug
    planejamento_path = benchmarks_root / "artifacts" / "raw" / "planejamento.txt"
    referencia_path = benchmarks_root / "referencia.json"

    if not planejamento_path.exists():
        print(f"  ✗ {slug}: planejamento.txt not found")
        return False

    # Load catalog for CPU mapping
    cat_path = project_root / "config" / "catalogos" / "mendeslobo" / ".catalog_bundle.json"
    catalog = json.loads(cat_path.read_text())
    catalog_cpus = {c["codigo"]: c for c in catalog.get("cpus", [])}

    # Parse planejamento
    items = parse_planejamento_txt(planejamento_path)
    if not items:
        print(f"  ✗ {slug}: no items parsed from planejamento.txt")
        return False

    # Map CPUs
    for item in items:
        item["cpu_id"] = map_cpu_for_item(item["descricao"], item["item_id"], catalog_cpus)

    # Load existing referencia to preserve meta and bdi
    if referencia_path.exists():
        ref = json.loads(referencia_path.read_text())
    else:
        ref = {"meta": {}, "spec": {}}

    # Update spec.eap and spec.cronograma
    ref["spec"]["eap"] = items
    ref["spec"]["cronograma"] = [
        {
            "item_id": item["item_id"],
            "producao_diaria": 0.0,
            "semanas": {}
        }
        for item in items
    ]

    # Save updated referencia
    referencia_path.write_text(json.dumps(ref, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"  ✓ {slug}: rebuilt with {len(items)} items")
    return True


def main():
    project_root = Path(__file__).parent.parent

    print("\n" + "=" * 80)
    print("REBUILDING MISSING BENCHMARKS FROM PLANEJAMENTO.TXT")
    print("=" * 80)

    for slug in ["ODFJELL", "MATEC_GUARULHOS"]:
        rebuild_benchmark(slug, project_root)

    print("\n" + "=" * 80)

if __name__ == "__main__":
    main()
