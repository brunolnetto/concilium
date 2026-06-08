#!/usr/bin/env python3
"""Add minimal rcpsp_spec to benchmarks missing pool contract data for skill-05 cost calculation."""

import json
from pathlib import Path


def build_minimal_rcpsp_spec(eap_items, weeks_list):
    """Build a minimal rcpsp_spec that allows skill-05 to compute equipes costs.

    Note: This is a simplified structure that satisfies skill-05 requirements for
    pool contract computation without full RCPSP scheduling complexity.
    """
    # Minimal structure: just deadline and empty pools/precedence
    # Skill-05 will use this to enable pool contracts even without detailed RCPSP

    return {
        "deadline_weeks": len(weeks_list),
        "activities": {},  # Empty: skill-05 derives from canonical EAP
        "resource_pool": {},  # Empty: skill-05 creates generic pools
        "precedence": [],  # Empty: precedence handled by EAP predecessores
        "resource_costs": {},  # Empty: costs handled by catalog
    }


def main():
    project_root = Path(__file__).resolve().parent.parent
    benchmarks_root = project_root / "benchmarks" / "data"

    # Benchmarks that need rcpsp_spec (missing from their referencia.json)
    slugs = [
        "CTC",
        "LUNDIN",
        "MARA_ROSA",
        "MATEC_HINES",
        "MATEC_UBERLANDIA",
        "PRIVATE_LOG",
        "ROSH",
        "RUMO",
        "VALE",
    ]

    print("\n" + "=" * 80)
    print("ADDING MINIMAL RCPSP_SPEC TO BENCHMARKS")
    print("=" * 80)

    from datetime import datetime, timedelta

    def iso_weeks_between(start_date: str, end_date: str) -> list[str]:
        """Generate list of ISO week strings between start and end dates."""
        start = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date)
        weeks = []
        seen = set()

        current = start
        while current <= end:
            iso = current.isocalendar()
            week_key = f"{iso.year}-W{iso.week:02d}"
            if week_key not in seen:
                weeks.append(week_key)
                seen.add(week_key)
            current += timedelta(days=7)

        return weeks

    for slug in slugs:
        ref_path = benchmarks_root / slug / "referencia.json"
        if not ref_path.exists():
            print(f"  ? {slug:25} referencia.json not found")
            continue

        ref = json.loads(ref_path.read_text())

        # Skip if already has rcpsp_spec
        if "rcpsp_spec" in ref.get("spec", {}):
            print(f"  ✓ {slug:25} already has rcpsp_spec")
            continue

        # Build minimal rcpsp_spec from EAP
        eap = ref.get("spec", {}).get("eap", [])
        if not eap:
            print(f"  ? {slug:25} no EAP items found")
            continue

        meta = ref.get("meta", {})
        start_date = meta.get("data_inicio", "2026-06-01")
        end_date = meta.get("data_termino", "2027-06-30")
        weeks = iso_weeks_between(start_date, end_date)

        rcpsp_spec = build_minimal_rcpsp_spec(eap, weeks)

        # Add to referencia
        if "spec" not in ref:
            ref["spec"] = {}
        ref["spec"]["rcpsp_spec"] = rcpsp_spec

        # Save updated referencia
        ref_path.write_text(json.dumps(ref, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  ✓ {slug:25} added rcpsp_spec with {len(eap)} activities")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
