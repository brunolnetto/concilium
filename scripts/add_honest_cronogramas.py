#!/usr/bin/env python3
"""Add honest cronogramas with default team allocation (1 team/week) based on project duration."""

import json
from datetime import datetime, timedelta
from pathlib import Path

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

def main():
    project_root = Path(__file__).parent.parent
    benchmarks_root = project_root / "benchmarks" / "data"

    print("\n" + "=" * 80)
    print("ADDING HONEST CRONOGRAMAS WITH DEFAULT TEAM ALLOCATION")
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

    for slug in slugs:
        ref_path = benchmarks_root / slug / "referencia.json"
        if not ref_path.exists():
            print(f"  ? {slug:25} referencia.json not found")
            continue

        ref = json.loads(ref_path.read_text())
        spec = ref.get("spec", {})
        meta = ref.get("meta", {})
        eap = spec.get("eap", [])

        if not eap:
            print(f"  ? {slug:25} no EAP")
            continue

        # Get project duration
        start_date = meta.get("data_inicio", "2026-01-01")
        end_date = meta.get("data_termino", "2027-12-31")

        try:
            weeks = iso_weeks_between(start_date, end_date)
        except:
            weeks = [f"2026-W{i:02d}" for i in range(1, 53)]

        # Create honest cronograma with calculated producao_diaria
        cronograma = []
        for item in eap:
            # Distribute weeks evenly across item
            weeks_per_item = max(1, len(weeks) // len(eap))  # Rough division

            # Calculate producao_diaria = quantitativo / (weeks_per_item * 5 working days)
            # Assumes 5 working days per week
            quantitativo = item.get("quantitativo", 1.0)
            production_days = weeks_per_item * 5
            producao_diaria = quantitativo / max(production_days, 1) if production_days > 0 else 1.0

            item_cronograma = {
                "item_id": item["item_id"],
                "producao_diaria": round(producao_diaria, 2),  # Honest: calculated from quantitativo
                "semanas": {}
            }

            start_week_idx = (eap.index(item) * weeks_per_item) % len(weeks)

            for week_offset in range(weeks_per_item):
                week_idx = (start_week_idx + week_offset) % len(weeks)
                if week_idx < len(weeks):
                    week_key = weeks[week_idx]
                    item_cronograma["semanas"][week_key] = {
                        "num_equipes": 1  # Honest: 1 team per week as baseline
                    }

            cronograma.append(item_cronograma)

        spec["cronograma"] = cronograma
        ref_path.write_text(json.dumps(ref, indent=2, ensure_ascii=False), encoding="utf-8")

        print(f"  ✓ {slug:25} added cronograma with {len(weeks)} weeks, 1 team/week")

    print("\n" + "=" * 80)

if __name__ == "__main__":
    main()
