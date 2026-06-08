#!/usr/bin/env python3
"""Add minimal cronograma template to benchmarks for skill 04 to populate."""

import json
from pathlib import Path

def main():
    project_root = Path(__file__).parent.parent
    benchmarks_root = project_root / "benchmarks" / "data"

    print("\n" + "=" * 80)
    print("ADDING MINIMAL CRONOGRAMA TEMPLATES")
    print("=" * 80)

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

    added = 0

    for slug in slugs:
        ref_path = benchmarks_root / slug / "referencia.json"
        if not ref_path.exists():
            print(f"  ? {slug:25} referencia.json not found")
            continue

        ref = json.loads(ref_path.read_text())
        spec = ref.get("spec", {})
        eap = spec.get("eap", [])

        # Only add if cronograma doesn't exist
        if "cronograma" not in spec or not spec["cronograma"]:
            # Create minimal cronograma structure
            cronograma = []
            for item in eap:
                cronograma.append({
                    "item_id": item["item_id"],
                    "producao_diaria": 0.0,  # Will be filled by skill 04
                    "semanas": {}  # Will be filled by skill 04
                })

            spec["cronograma"] = cronograma
            ref_path.write_text(json.dumps(ref, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"  ✓ {slug:25} added minimal cronograma template ({len(cronograma)} items)")
            added += 1
        else:
            print(f"  - {slug:25} already has cronograma")

    print("\n" + "=" * 80)
    print(f"SUMMARY: {added} benchmarks updated")
    print("=" * 80 + "\n")

if __name__ == "__main__":
    main()
