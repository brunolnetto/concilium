#!/usr/bin/env python3
"""Remove empty rcpsp_spec from benchmarks to allow proper auto-scheduling."""

import json
from pathlib import Path

def main():
    project_root = Path(__file__).parent.parent
    benchmarks_root = project_root / "benchmarks" / "data"

    print("\n" + "=" * 80)
    print("REMOVING EMPTY rcpsp_spec FROM BENCHMARKS")
    print("=" * 80)

    # Benchmarks with synthetic CPUs that were fixed
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
        rcpsp = spec.get("rcpsp_spec", {})

        # Remove empty rcpsp_spec
        if "rcpsp_spec" in spec:
            rcpsp = spec["rcpsp_spec"]
            if isinstance(rcpsp, dict) and not rcpsp:
                del spec["rcpsp_spec"]
                ref_path.write_text(json.dumps(ref, indent=2, ensure_ascii=False), encoding="utf-8")
                print(f"  ✓ {slug:25} removed empty rcpsp_spec")
                cleaned += 1
            else:
                print(f"  - {slug:25} rcpsp_spec has data (not removed)")
                skipped += 1
        else:
            print(f"  - {slug:25} no rcpsp_spec")
            skipped += 1

    print("\n" + "=" * 80)
    print(f"SUMMARY: {cleaned} cleaned, {skipped} skipped")
    print("=" * 80 + "\n")

if __name__ == "__main__":
    main()
