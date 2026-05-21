"""Utility functions for UI logic."""

from __future__ import annotations

from typing import Any


def safe_count_eap(reference: dict) -> int:
    """Count EAP items in reference."""
    if not isinstance(reference, dict):
        return 0
    # Priority 1: benchmark reference has cpus.itens_eap
    itens = (reference.get("cpus") or {}).get("itens_eap")
    if isinstance(itens, list):
        return len(itens)
    # Priority 2: inputs_escopo.eap
    inputs_escopo = reference.get("inputs_escopo")
    if isinstance(inputs_escopo, dict) and isinstance(inputs_escopo.get("eap"), list):
        return len(inputs_escopo["eap"])
    if isinstance(reference.get("eap"), list):
        return len(reference["eap"])
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


def build_team_adjustment_rows(reference: dict) -> list[dict[str, object]]:
    """Build team adjustment rows from cronograma reference."""
    activities = (reference.get("cronograma") or {}).get("atividades", []) if isinstance(reference, dict) else []
    rows: list[dict[str, object]] = []
    for activity in activities:
        semanas = activity.get("semanas", {}) or {}
        num_equipes = [int((semana or {}).get("num_equipes", 0) or 0) for semana in semanas.values()]
        base_avg = round(sum(num_equipes) / len(num_equipes), 2) if num_equipes else 0.0
        rows.append(
            {
                "item_id": activity.get("item_id") or activity.get("activity_id"),
                "descricao": activity.get("descricao", ""),
                "cpu_id": activity.get("cpu_id", ""),
                "num_equipes_base": base_avg,
                "num_equipes_maximo": base_avg,
                "start_week": activity.get("start_week"),
                "end_week": activity.get("end_week"),
                "duration_weeks": activity.get("duration_weeks"),
                "producao_diaria": activity.get("producao_diaria"),
                "quantitativo": activity.get("quantitativo"),
            }
        )
    return rows


def _bneo_get_rows(edited_rows: object) -> list[dict]:
    if hasattr(edited_rows, "to_dict") and hasattr(edited_rows, "columns"):
        return edited_rows.to_dict("records")  # type: ignore[union-attr]
    return list(edited_rows or [])  # type: ignore[call-overload]


def _bneo_build_week_map(semanas: dict, target: int) -> dict[str, int]:
    return {
        week_key: target
        for week_key, week_data in semanas.items()
        if int((week_data or {}).get("num_equipes", 0) or 0) > 0
    }


def build_num_equipes_override(reference: dict, edited_rows: object) -> dict[str, dict[str, int]]:
    """Build team override mapping from edited rows."""
    activities = (reference.get("cronograma") or {}).get("atividades", []) if isinstance(reference, dict) else []
    activity_lookup = {act.get("item_id") or act.get("activity_id"): act for act in activities}
    override: dict[str, dict[str, int]] = {}
    for row in _bneo_get_rows(edited_rows):
        item_id = str(row.get("item_id") or "").strip()
        if not item_id or item_id not in activity_lookup:
            continue
        target = max(1, int(round(float(row.get("num_equipes_maximo") or 0.0))))
        if target <= 0:
            continue
        week_map = _bneo_build_week_map(activity_lookup[item_id].get("semanas") or {}, target)
        if week_map:
            override[item_id] = week_map
    return override


def state_team_rows_key(project_id: str) -> str:
    """Generate session state key for team rows."""
    return f"team-rows-state-{project_id}"


def apply_global_team_adjustment(rows: list[dict[str, object]], pct: float) -> list[dict[str, object]]:
    """Apply global percentage adjustment to team rows."""
    fator = 1.0 + (pct / 100.0)
    adjusted: list[dict[str, object]] = []
    for row in rows:
        new_row = dict(row)
        base_value = float(new_row.get("num_equipes_base") or 0.0)  # type: ignore[arg-type]
        new_row["num_equipes_maximo"] = round(max(0.0, base_value * fator), 2)
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
    return skill_inputs


def collect_skill_candidates(reference: dict, current: dict[str, Any]) -> list[str]:
    """Collect list of available skill IDs."""
    candidates = {
        "04-cronograma",
        "05-equipes-e-produtividade",
        "06-precificacao-unitaria",
        "07-custos-indiretos",
        "08-consolidacao-financeira",
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


def extract_eap_items_for_policy(reference: dict) -> list[dict[str, Any]]:
    """Extract deduplicated EAP items with cpu_id from a benchmark reference.

    Tries two data paths:
    1. reference.cpus.itens_eap  — present in most current references
    2. reference.cronograma.atividades — legacy path (with cpu_id field)
    """
    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    cpus_block = reference.get("cpus") if isinstance(reference, dict) else None
    if isinstance(cpus_block, dict):
        for item in cpus_block.get("itens_eap", []):
            if not isinstance(item, dict):
                continue
            item_id = item.get("item_id") or item.get("activity_id")
            if item_id and item_id not in seen:
                items.append(item)
                seen.add(item_id)

    for act in (reference.get("cronograma") or {}).get("atividades", []):
        if not isinstance(act, dict) or not act.get("cpu_id"):
            continue
        item_id = act.get("item_id") or act.get("activity_id")
        if item_id and item_id not in seen:
            items.append(act)
            seen.add(item_id)

    return items


def extract_bdi_dict(inputs: dict[str, Any] | None) -> dict[str, float]:
    """Extract BDI percentages from inputs."""
    if not isinstance(inputs, dict):
        return {}
    raw = inputs.get("bdi_aplicado")
    if not isinstance(raw, dict):
        raw = inputs.get("bdi")
    if not isinstance(raw, dict):
        raw = inputs
    out: dict[str, float] = {}
    for key, value in raw.items():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            out[str(key)] = float(value)
    aliases = {
        "mo": "mao_obra",
        "eq": "equipamentos",
        "mat": "material",
        "ind": "indireto",
    }
    for alias, target in aliases.items():
        if target not in out and alias in out:
            out[target] = out[alias]
    return out
