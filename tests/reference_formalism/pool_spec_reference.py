"""Independent oracle: per-resource rcpsp_spec of a project from its own data (N8.1).

For each activity: required units per front = the production's standard team;
nominal one-front duration = ceil(Q / (rho * d * h)) weeks. The pool is the
explicitly configured physical availability restricted to the resource types
the activities use, and it must cover at least one front of every activity.
Nothing is inferred when data is missing. Stdlib only; written from the rule.
"""

from __future__ import annotations

from fractions import Fraction as F
from typing import Any

VERSION = "formalism-pool-spec/1"


class PoolSpecError(ValueError):
    pass


def evaluate_pool_spec(case: dict[str, Any]) -> dict[str, Any]:
    hours = F(case["dias_semana"]) * F(case["horas_dia"])
    pool = case.get("configured_pool") or {}
    if not pool:
        raise PoolSpecError("no configured physical pool")
    activities: dict[str, Any] = {}
    used: set[str] = set()
    for activity in case["activities"]:
        team = activity.get("team") or {}
        if not team:
            raise PoolSpecError(f"{activity['id']}: no standard team composition")
        rate, quantity = F(activity["rho"]), F(activity["Q"])
        if rate <= 0 or quantity <= 0:
            raise PoolSpecError(f"{activity['id']}: rate and quantity must be positive")
        if any(pool.get(resource, 0) < units for resource, units in team.items()):
            raise PoolSpecError(f"{activity['id']}: pool does not cover one front")
        weeks = quantity / (rate * hours)
        duration = int(weeks) if weeks == int(weeks) else int(weeks) + 1
        activities[activity["id"]] = {
            "duration_weeks": max(1, duration),
            "required_resources": dict(sorted(team.items())),
        }
        used.update(team)
    return {"activities": activities, "resource_pool": {g: pool[g] for g in sorted(used)}}
