#!/usr/bin/env python3
"""Remove empty cronogramas from benchmarks to let skill 04 generate fresh ones."""

import json
from pathlib import Path

def main():
    project_root = Path(__file__).parent.parent
    benchmarks_root = project_root / "benchmarks" / "data"

    print("\n" + "=" * 80)
    print("REMOVING EMPTY CRONOGRAMAS FROM BENCHMARKS")
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

    cleaned = 0
    skipped = 0

    for slug in slugs:
        ref_path = benchmarks_root / slug / "referencia.json"
        if not ref_path.exists():
            print(f"  ? {slug:25} referencia.json not found")
            skipped += 1
            continue

        ref = json.loads(ref_path.read_text())
        spec = ref.get("spec", {})
        cronograma = spec.get("cronograma", [])

        # Check if cronograma is empty
        is_empty = True
        if isinstance(cronograma, list) and cronograma:
            # Check if any item has non-empty semanas
            for item in cronograma:
                if isinstance(item.get("semanas"), dict) and item["semanas"]:
                    is_empty = False
                    break

        if is_empty:
            # Remove the empty cronograma
            del spec["cronograma"]
            ref_path.write_text(json.dumps(ref, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"  ✓ {slug:25} removed empty cronograma")
            cleaned += 1
        else:
            print(f"  - {slug:25} cronograma has data (not removed)")
            skipped += 1

    print("\n" + "=" * 80)
    print(f"SUMMARY: {cleaned} cleaned, {skipped} skipped")
    print("=" * 80 + "\n")

if __name__ == "__main__":
    main()
