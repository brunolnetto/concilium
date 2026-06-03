"""Gera um cenário 'escala unitária' a partir do referencia.json do AGIS.

Transforma o cronograma para que cada item use no máximo 1 equipe por semana,
estendendo o prazo proporcionalmente. O total de 'team-weeks' permanece idêntico,
apenas a distribuição muda: de N equipes × K semanas → 1 equipe × N×K semanas.

Uso:
    python3 tools/generate_escala_unitaria_scenario.py [--dry-run]

Saída:
    benchmarks/data/AGIS/referencia_escala_unitaria.json
"""
from __future__ import annotations

import json
import sys
from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = ROOT / "benchmarks" / "data" / "AGIS" / "referencia.json"
DST_PATH = ROOT / "benchmarks" / "data" / "AGIS" / "referencia_escala_unitaria.json"


# ── ISO week helpers ──────────────────────────────────────────────────────────

def _week_to_date(week_key: str) -> date:
    """Converte '2026-W23' → date (segunda-feira da ISO week)."""
    year_str, w_str = week_key.split("-W")
    # %G = ISO year, %V = ISO week, %u = ISO weekday (1=Mon)
    return datetime.strptime(f"{year_str}-{int(w_str):02d}-1", "%G-%V-%u").date()


def _date_to_week(d: date) -> str:
    """Converte date → '2026-W23'."""
    iso = d.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _advance_weeks(week_key: str, n: int) -> str:
    """Retorna a chave da ISO week n semanas após week_key."""
    return _date_to_week(_week_to_date(week_key) + timedelta(weeks=n))


# ── Cronograma stats ──────────────────────────────────────────────────────────

def _item_stats(semanas: dict[str, dict]) -> tuple[int, str, date]:
    """Retorna (team_weeks, start_week_key, start_date) de um item."""
    by_date = sorted(semanas.items(), key=lambda kv: _week_to_date(kv[0]))
    team_weeks = sum(v.get("num_equipes", 0) for _, v in by_date)
    start_key = by_date[0][0]
    start_date = _week_to_date(start_key)
    return team_weeks, start_key, start_date


# ── Transformation ────────────────────────────────────────────────────────────

def transform(ref: dict) -> dict:
    """Aplica a transformação escala-unitária e retorna novo referencia dict."""
    out = deepcopy(ref)
    spec = out["spec"]
    cronograma = spec.get("cronograma") or []
    activities = spec.get("rcpsp_spec", {}).get("activities") or []

    # Build item_id → team_weeks map (from cronograma)
    item_team_weeks: dict[str, int] = {}
    item_start_week: dict[str, str] = {}

    new_cronograma = []
    for item in cronograma:
        item_id = item["item_id"]
        semanas = item.get("semanas") or {}
        if not semanas:
            new_cronograma.append(item)
            continue

        team_weeks, start_key, _start_date = _item_stats(semanas)
        item_team_weeks[item_id] = team_weeks
        item_start_week[item_id] = start_key

        # Build new semanas: team_weeks consecutive weeks with num_equipes=1
        new_semanas: dict[str, dict] = {}
        for i in range(team_weeks):
            wk = _advance_weeks(start_key, i)
            new_semanas[wk] = {"num_equipes": 1}

        new_item = deepcopy(item)
        new_item["semanas"] = new_semanas
        new_cronograma.append(new_item)

    spec["cronograma"] = new_cronograma

    # Remove rcpsp_spec entirely: skill-04 must use MANUAL_ALLOCATION mode
    # (reading num_equipes directly from cronograma.semanas).  When rcpsp_spec
    # is present it triggers AUTO_SCHEDULE/CpSat which fails because the
    # solver cannot fit the extended activities within any feasible deadline.
    spec.pop("rcpsp_spec", None)

    # Compute data_termino from the ACTUAL last semana week across all items
    # in the new cronograma (not from activity-level offsets which can be off).
    all_semana_keys: list[str] = []
    for item in new_cronograma:
        all_semana_keys.extend((item.get("semanas") or {}).keys())

    if all_semana_keys:
        last_semana_date = max(_week_to_date(k) for k in all_semana_keys)
        # Add 2 weeks of buffer so iso_weeks() covers the last active week
        new_termino = last_semana_date + timedelta(weeks=2)
        out["meta"]["data_termino"] = new_termino.isoformat()

    out["spec"] = spec
    out["meta"]["projeto"] = out["meta"]["projeto"].replace(
        "(Supressao e Terraplanagem)",
        "(Supressao e Terraplanagem - Cenário Escala Unitária)",
    )
    return out


def _print_summary(original: dict, transformed: dict) -> None:
    orig_cron = {c["item_id"]: c for c in (original["spec"].get("cronograma") or [])}
    print()
    print("=" * 68)
    print("  TRANSFORMAÇÃO: Escala Unitária vs. Baseline")
    print("=" * 68)
    print(f"  {'Item':<12} {'TW(orig)':>8} {'Ativas(orig)':>12} {'n_ef(orig)':>10} {'TW(novo)':>9} {'Ativas(novo)':>12} {'n_ef(novo)':>10}")
    print("  " + "-" * 66)
    for item in (transformed["spec"].get("cronograma") or []):
        item_id = item["item_id"]
        new_sem = item.get("semanas") or {}
        new_tw = sum(v.get("num_equipes", 0) for v in new_sem.values())
        new_active = sum(1 for v in new_sem.values() if v.get("num_equipes", 0) > 0)
        new_nef = new_tw / new_active if new_active else 0

        orig_item = orig_cron.get(item_id, {})
        orig_sem = orig_item.get("semanas") or {}
        orig_tw = sum(v.get("num_equipes", 0) for v in orig_sem.values())
        orig_active = sum(1 for v in orig_sem.values() if v.get("num_equipes", 0) > 0)
        orig_nef = orig_tw / orig_active if orig_active else 0

        changed = " <--" if orig_nef > 1.05 else ""
        print(
            f"  {item_id:<12} {orig_tw:>8} {orig_active:>12} {orig_nef:>10.2f} "
            f"{new_tw:>9} {new_active:>12} {new_nef:>10.2f}{changed}"
        )

    orig_rcpsp = original["spec"].get("rcpsp_spec") or {}
    orig_dl = orig_rcpsp.get("deadline_weeks", "?")
    orig_end = original["meta"].get("data_termino", "?")
    new_end = transformed["meta"].get("data_termino", "?")
    print("  " + "-" * 66)
    print(f"  Prazo orig (semanas): {orig_dl}")
    print(f"  Data término   : {orig_end}  ->  {new_end}")
    print("  (rcpsp_spec removido do cenário para uso de MANUAL_ALLOCATION)")
    print("=" * 68)
    print()


def main(argv: list[str] | None = None) -> int:
    args = argv or sys.argv[1:]
    dry_run = "--dry-run" in args

    ref = json.loads(SRC_PATH.read_text(encoding="utf-8"))
    transformed = transform(ref)

    if dry_run:
        _print_summary(ref, transformed)
        print("  [DRY-RUN] Nenhum arquivo gravado.")
        return 0

    DST_PATH.write_text(
        json.dumps(transformed, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  [OK] Gravado: {DST_PATH.relative_to(ROOT)}")
    _print_summary(ref, transformed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
