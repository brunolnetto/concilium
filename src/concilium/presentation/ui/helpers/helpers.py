"""Utility functions for UI logic."""

from __future__ import annotations

import math
from numbers import Integral, Real
from typing import Any


def dataframe_selected_rows(result: object) -> list[int]:
    """Extract selection.rows from a st.dataframe(on_select=...) result.

    The result is a DeltaGenerator (no selection support) or a DataframeState
    TypedDict — a dict at runtime, accessed here via .get() rather than
    attribute access since TypedDict has no attribute-access at the type level.
    """
    if not isinstance(result, dict):
        return []
    selection = result.get("selection")
    if not isinstance(selection, dict):
        return []
    rows = selection.get("rows")
    return [r for r in rows if isinstance(r, int)] if isinstance(rows, list) else []


def safe_count_eap(reference: dict) -> int:
    """Count EAP items using canonical benchmark reference contract."""
    if not isinstance(reference, dict):
        return 0

    # Canonical contract: reference.cpus.itens_eap
    itens = (reference.get("cpus") or {}).get("itens_eap")
    if isinstance(itens, list):
        return len(itens)
    return 0


def safe_count_extra_inputs(reference: dict) -> int:
    """Count extra inputs in reference."""
    if not isinstance(reference, dict):
        return 0
    extra_inputs = reference.get("extra_inputs")
    if isinstance(extra_inputs, dict):
        return len(extra_inputs)
    return 0


def stringify_table_value(value: object) -> object:
    """Convert value to JSON-serializable format for display."""
    if isinstance(value, (dict, list)):
        import json

        return json.dumps(value, ensure_ascii=False, default=str)
    return value


def _require_integral_team_count(value: object, field: str) -> int:
    """Accept only finite, nonnegative integer-valued physical team counts."""
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a nonnegative integer team count")
    if isinstance(value, Integral):
        count = int(value)
    elif (
        isinstance(value, Real)
        and math.isfinite(float(value))
        and abs(float(value)) <= 2**53
        and float(value).is_integer()
    ):
        count = int(value)
    else:
        raise ValueError(f"{field} must be a nonnegative integer team count")
    if count < 0:
        raise ValueError(f"{field} must be a nonnegative integer team count")
    return count


def build_team_adjustment_rows(reference: dict) -> list[dict[str, object]]:
    """Build team adjustment rows from cronograma reference."""
    activities = (reference.get("cronograma") or {}).get("atividades", []) if isinstance(reference, dict) else []
    rows: list[dict[str, object]] = []
    for activity in activities:
        semanas = activity.get("semanas", {}) or {}
        item_label = activity.get("item_id") or activity.get("activity_id")
        num_equipes = []
        for week, semana in semanas.items():
            raw_count = (semana or {}).get("num_equipes", 0)
            raw_count = 0 if raw_count is None else raw_count
            num_equipes.append(
                _require_integral_team_count(raw_count, f"{item_label}/{week}")
            )
        base_avg = round(sum(num_equipes) / len(num_equipes), 2) if num_equipes else 0.0
        rows.append(
            {
                "item_id": activity.get("item_id") or activity.get("activity_id"),
                "descricao": activity.get("descricao", ""),
                "cpu_id": activity.get("cpu_id", ""),
                # Average occupancy is an analytic statistic. The editable
                # count is seeded from that baseline but kept integral.
                "num_equipes_base": base_avg,
                "num_equipes_maximo": max(0, int(round(base_avg))),
                "start_week": activity.get("start_week"),
                "end_week": activity.get("end_week"),
                "duration_weeks": activity.get("duration_weeks"),
                "producao_diaria": activity.get("producao_diaria"),
                "quantitativo": activity.get("quantitativo"),
            }
        )
    return rows


def _bneo_get_rows(edited_rows: object) -> list[dict]:
    if isinstance(edited_rows, list):
        return [row for row in edited_rows if isinstance(row, dict)]
    to_dict = getattr(edited_rows, "to_dict", None)
    if callable(to_dict) and hasattr(edited_rows, "columns"):
        records = to_dict("records")
        return [row for row in records if isinstance(row, dict)] if isinstance(records, list) else []
    return []


def _bneo_build_week_map(semanas: dict, target: int) -> dict[str, int]:
    count = _require_integral_team_count(target, "num_equipes_maximo")
    result: dict[str, int] = {}
    for week_key, week_data in semanas.items():
        raw_count = (week_data or {}).get("num_equipes", 0)
        raw_count = 0 if raw_count is None else raw_count
        if _require_integral_team_count(raw_count, f"num_equipes[{week_key}]") > 0:
            result[week_key] = count
    return result


def _bneo_process_row(row: dict, activity_lookup: dict) -> tuple[str, dict[str, int]] | None:
    item_id = str(row.get("item_id") or "").strip()
    if not item_id or item_id not in activity_lookup:
        return None
    raw_target = row.get("num_equipes_maximo", 0)
    target = max(1, _require_integral_team_count(raw_target, "num_equipes_maximo"))
    week_map = _bneo_build_week_map(activity_lookup[item_id].get("semanas") or {}, target)
    return (item_id, week_map) if week_map else None


def build_num_equipes_override(reference: dict, edited_rows: object) -> dict[str, dict[str, int]]:
    """Build team override mapping from edited rows."""
    activities = (reference.get("cronograma") or {}).get("atividades", []) if isinstance(reference, dict) else []
    activity_lookup = {act.get("item_id") or act.get("activity_id"): act for act in activities}
    override: dict[str, dict[str, int]] = {}
    for row in _bneo_get_rows(edited_rows):
        result = _bneo_process_row(row, activity_lookup)
        if result is not None:
            override[result[0]] = result[1]
    return override


def state_team_rows_key(project_id: str) -> str:
    """Generate session state key for team rows."""
    return f"team-rows-state-{project_id}"


def apply_global_team_adjustment(rows: list[dict[str, object]], pct: float) -> list[dict[str, object]]:
    """Apply global percentage adjustment to team rows."""
    if isinstance(pct, bool) or not isinstance(pct, Real) or not math.isfinite(float(pct)):
        raise ValueError("team adjustment percentage must be finite")
    fator = 1.0 + (float(pct) / 100.0)
    adjusted: list[dict[str, object]] = []
    for row in rows:
        new_row = dict(row)
        raw_base = new_row.get("num_equipes_base")
        if isinstance(raw_base, bool) or not isinstance(raw_base, Real):
            base_value = 0.0
        else:
            base_value = float(raw_base)
        if not math.isfinite(base_value):
            raise ValueError("base team occupancy must be finite")
        # Preserve the established non-compounding adjustment from the analytic
        # average; only the editable physical ceiling is rounded to an integer.
        new_row["num_equipes_maximo"] = max(0, int(round(base_value * fator)))
        adjusted.append(new_row)
    return adjusted


def extract_skill_base_inputs(reference: dict, skill_id: str) -> dict[str, Any]:
    """Extract base inputs for a specific skill."""
    if not isinstance(reference, dict):
        return {}
    direct = reference.get("skill_inputs")
    if isinstance(direct, dict) and isinstance(direct.get(skill_id), dict):
        return dict(direct[skill_id])
    extra = reference.get("extra_inputs")
    if isinstance(extra, dict):
        nested = extra.get("skill_inputs")
        if isinstance(nested, dict) and isinstance(nested.get(skill_id), dict):
            return dict(nested[skill_id])
        if isinstance(extra.get(skill_id), dict):
            return dict(extra[skill_id])
    return {}


def extract_inputs_escopo(reference: dict) -> dict[str, Any]:
    """Extract escopo inputs from reference."""
    if not isinstance(reference, dict):
        return {}
    if isinstance(reference.get("inputs_escopo"), dict):
        return dict(reference["inputs_escopo"])
    if isinstance(reference.get("escopo"), dict):
        return dict(reference["escopo"])
    if isinstance(reference.get("eap"), list):
        return {"eap": list(reference.get("eap") or [])}
    return {}


def _easi_merge_extra(extra: dict, skill_inputs: dict) -> None:
    nested = extra.get("skill_inputs")
    if isinstance(nested, dict):
        for key, val in nested.items():
            if isinstance(val, dict):
                skill_inputs[str(key)] = dict(val)
    for key, val in extra.items():
        if key == "skill_inputs":
            continue
        if isinstance(val, dict):
            skill_inputs[str(key)] = dict(val)


def extract_all_skill_inputs(reference: dict) -> dict[str, dict[str, Any]]:
    """Extract all skill inputs from reference."""
    if not isinstance(reference, dict):
        return {}
    skill_inputs: dict[str, dict[str, Any]] = {}
    direct = reference.get("skill_inputs")
    if isinstance(direct, dict):
        for key, val in direct.items():
            if isinstance(val, dict):
                skill_inputs[str(key)] = dict(val)
    extra = reference.get("extra_inputs")
    if isinstance(extra, dict):
        _easi_merge_extra(extra, skill_inputs)
    return skill_inputs


def collect_skill_candidates(reference: dict, current: dict[str, Any]) -> list[str]:
    """Collect list of available skill IDs."""
    candidates = {
        "04-cronograma",
        "05-equipes-e-produtividade",
        "06-resultado-financeiro",  # NEP-041 F4
    }
    candidates.update(extract_all_skill_inputs(reference).keys())
    if isinstance(current, dict):
        candidates.update([k for k, v in current.items() if isinstance(v, dict)])
    return sorted(candidates)


def flatten_numeric_paths(value: Any, prefix: str = "") -> list[tuple[str, float]]:
    """Flatten nested dict/list to dotted paths with numeric values."""
    rows: list[tuple[str, float]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            rows.extend(flatten_numeric_paths(child, next_prefix))
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        rows.append((prefix, float(value)))
    return rows


def set_path(target: dict[str, Any], dotted_path: str, value: float) -> None:
    """Set value in nested dict using dotted path."""
    keys = [k for k in dotted_path.split(".") if k]
    if not keys:
        return
    cursor = target
    for key in keys[:-1]:
        child = cursor.get(key)
        if not isinstance(child, dict):
            child = {}
            cursor[key] = child
        cursor = child
    cursor[keys[-1]] = float(value)


def _eaip_collect_cpus(reference: dict, items: list, seen: set) -> None:
    cpus_block = reference.get("cpus")
    if not isinstance(cpus_block, dict):
        return
    for item in cpus_block.get("itens_eap", []):
        if not isinstance(item, dict):
            continue
        item_id = item.get("item_id") or item.get("activity_id")
        if item_id and item_id not in seen:
            items.append(item)
            seen.add(item_id)


def extract_eap_items_for_policy(reference: dict) -> list[dict[str, Any]]:
    """Extract deduplicated EAP items with cpu_id from canonical contract."""
    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    if isinstance(reference, dict):
        _eaip_collect_cpus(reference, items, seen)
    return items


def extract_bdi_dict(inputs: dict[str, Any] | None) -> dict[str, float]:
    """Extract BDI percentages from canonical inputs only."""
    if not isinstance(inputs, dict):
        return {}
    raw = inputs.get("bdi_aplicado")
    if not isinstance(raw, dict):
        raw = inputs.get("bdi")
    if not isinstance(raw, dict):
        raw = inputs
    out: dict[str, float] = {}
    blocked_short_keys = {"mo", "eq", "mat", "ind"}
    for key, value in raw.items():
        if str(key) in blocked_short_keys:
            continue
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            out[str(key)] = float(value)
    return out
