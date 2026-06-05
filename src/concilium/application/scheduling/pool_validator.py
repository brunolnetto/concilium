"""ADR-006 — Standalone ResourcePoolValidator.

Validates that weekly team allocations do not exceed global pool capacity.
Can be called from Skill 02 (scheduling) and Skill 03 (equipes-diretas).
"""

from __future__ import annotations

from collections import defaultdict

from concilium.domain.models.constraint_violation import ConstraintViolation


def _collect_schedule_weeks(schedule: dict) -> set:
    weeks: set[int] = set()
    for info in schedule.values():
        start = info.get("start_week", 0)
        end = info.get("end_week", 0)
        for w in range(start, end + 1):
            weeks.add(w)
    return weeks


def _compute_week_demand(week: int, schedule: dict, team_allocations: dict) -> dict:
    demand: dict[str, int] = defaultdict(int)
    for activity_id, info in schedule.items():
        start = info.get("start_week", 0)
        end = info.get("end_week", 0)
        if start <= week <= end:
            for role, count in team_allocations.get(activity_id, {}).items():
                demand[role] += count
    return demand


class ResourcePoolValidator:
    """Per-week aggregation of role/equipment demand vs. pool capacity."""

    def validate_schedule(
        self,
        schedule: dict[str, dict],
        team_allocations: dict[str, dict[str, int]],
        pool_capacity: dict[str, int],
    ) -> list[ConstraintViolation]:
        """Check resource demand vs. capacity for every active week.

        Args:
            schedule: dict[activity_id, {"start_week": int, "end_week": int}]
            team_allocations: dict[activity_id, dict[role_or_equip_id, count]]
            pool_capacity: dict[tipo_id, max_count]

        Returns:
            List of ConstraintViolation (empty if no violations).
        """
        if not pool_capacity:
            return []

        # Collect all week numbers across the schedule
        weeks = _collect_schedule_weeks(schedule)
        violations: list[ConstraintViolation] = []
        for week in sorted(weeks):
            demand = _compute_week_demand(week, schedule, team_allocations)
            for role, demanded in demand.items():
                capacity = pool_capacity.get(role)
                if capacity is None or demanded <= capacity:
                    continue
                violations.append(
                    ConstraintViolation(
                        code="VAL-POOL-TEAM-01",
                        status="ERRO",
                        magnitude=float(demanded - capacity),
                        affected_items=[f"week_{week}_{role}"],
                        remediation_hint=(
                            f"Reduzir {demanded - capacity} '{role}' na semana {week}, "
                            f"ou estender prazo, ou aumentar pool para '{role}'"
                        ),
                    )
                )
        return violations

    def validate_week_allocations(
        self,
        week: int,
        week_allocations: dict[str, int],
        pool_capacity: dict[str, int],
    ) -> list[ConstraintViolation]:
        """Validate a single week's aggregated allocations against pool capacity."""
        violations: list[ConstraintViolation] = []
        for role, demanded in week_allocations.items():
            capacity = pool_capacity.get(role)
            if capacity is None or demanded <= capacity:
                continue
            violations.append(
                ConstraintViolation(
                    code="VAL-POOL-TEAM-01",
                    status="ERRO",
                    magnitude=float(demanded - capacity),
                    affected_items=[f"week_{week}_{role}"],
                    remediation_hint=(f"Reduzir {demanded - capacity} '{role}' na semana {week}"),
                )
            )
        return violations
