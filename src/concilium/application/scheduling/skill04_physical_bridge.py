"""P15-C: strict bridge from Skill 04 ISO-week cells to a physical RCPSP witness.

This bridge does NOT infer resource demand, invent weather/productivity, round
away quantities, or issue GO. The calendar validator/solver still owns local
feasibility and P23 owns formal financial certification.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from fractions import Fraction

from concilium.domain.models.canonical import DistribuicaoSemanal

from .physical_validator import (
    PhysicalActivity,
    PhysicalCalendarAudit,
    PhysicalPrecedence,
    validate_materialized_calendar,
)


def _quantity(value: int | float | str | Fraction, label: str) -> Fraction:
    if isinstance(value, bool):
        raise ValueError(f"{label} cannot be boolean")
    try:
        result = Fraction(str(value))
    except (TypeError, ValueError, ZeroDivisionError) as exc:
        raise ValueError(f"{label} must be a finite physical quantity") from exc
    return result


def _iso_start(iso_week: str) -> date:
    try:
        year, week = iso_week.split("-W", 1)
        if len(year) != 4 or len(week) != 2:
            raise ValueError("ISO week must use YYYY-Www")
        return date.fromisocalendar(int(year), int(week), 1)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"invalid ISO calendar week {iso_week!r}") from exc


def materialize_skill04_physical_activity(
    *,
    item_id: str,
    scope: int | float | str | Fraction,
    calendar_weeks: Sequence[str],
    distribution: Mapping[str, DistribuicaoSemanal],
    demand_by_week: Mapping[str, Mapping[str, int | float | str | Fraction]] | None,
) -> PhysicalActivity:
    """Produce a local physical witness from real Skill 04 weekly cell fields.

    calendar_weeks maps absolute project weeks 0..H-1. Each active week,
    including zero-output weather/standby weeks, MUST be materialized.
    Physical resource demand per week must be explicitly supplied by the
    caller (ultimately the Skill 05 assignment). None means missing evidence,
    not zero demand. Do not pass this result as a globally certified schedule.
    """
    if not item_id:
        raise ValueError("item_id must be nonempty")
    if not calendar_weeks or len(set(calendar_weeks)) != len(calendar_weeks):
        raise ValueError("calendar weeks must be nonempty and unique")
    dates = tuple(_iso_start(w) for w in calendar_weeks)
    if any((next_week - previous_week).days != 7
           for previous_week, next_week in zip(dates, dates[1:], strict=False)):
        raise ValueError("calendar must contain consecutive ISO weeks")
    if not distribution or not set(distribution).issubset(set(calendar_weeks)):
        raise ValueError("Skill 04 distribution must belong to the declared calendar")
    if demand_by_week is None or set(demand_by_week) != set(distribution):
        raise ValueError("resource demand must explicitly cover every materialized week")

    indexes = {week: index for index, week in enumerate(calendar_weeks)}
    ordered = sorted(distribution, key=indexes.__getitem__)
    start, end = indexes[ordered[0]], indexes[ordered[-1]] + 1
    if [indexes[week] for week in ordered] != list(range(start, end)):
        raise ValueError("missing physical activity week, including zero-output weeks")

    deliveries: list[tuple[int, Fraction]] = []
    capacities: list[tuple[int, Fraction]] = []
    demands: list[tuple[int, str, Fraction]] = []
    last_cumulative = Fraction(0)

    for week in ordered:
        index = indexes[week]
        cell = distribution[week]
        if cell.capacidade_disponivel_semana is None:
            raise ValueError(f"{week}: missing F(m)/calendar weekly capacity witness")
        q = _quantity(cell.qtd_executada, f"{week}.qtd_executada")
        available = _quantity(cell.capacidade_disponivel_semana, f"{week}.capacity")
        nominal = _quantity(cell.q_max_celula, f"{week}.nominal_capacity")
        cumulative = _quantity(cell.qtd_acumulada, f"{week}.cumulative")
        if q < 0 or available < 0 or nominal < 0 or q > available or available > nominal:
            raise ValueError(f"{week}: quantity violates the physical F(m)/calendar envelope")
        expected_cumulative = last_cumulative + q
        if cumulative != expected_cumulative:
            raise ValueError(
                f"{week}: cumulative quantity does not reconcile with actual "
                f"weekly delivery (expected {expected_cumulative}, observed {cumulative})"
            )
        last_cumulative = cumulative
        deliveries.append((index, q))
        capacities.append((index, available))

        for resource, quantity in sorted(demand_by_week[week].items()):
            if not resource:
                raise ValueError("resource type must be nonempty")
            amount = _quantity(quantity, f"{week}.{resource}")
            if amount < 0:
                raise ValueError("resource demand cannot be negative")
            if amount:
                demands.append((index, resource, amount))

    physical_scope = _quantity(scope, "scope")
    if physical_scope <= 0:
        raise ValueError("scope must be strictly positive")
    return PhysicalActivity(
        item_id=item_id, scope=physical_scope, start_week=start, end_week_exclusive=end,
        deliveries=tuple(deliveries), demands=tuple(demands),
        weekly_capacities=tuple(capacities),
    )


def audit_skill04_skill05_physical_snapshot(
    *,
    calendar_weeks: Sequence[str],
    distributions_by_item: Mapping[str, Mapping[str, DistribuicaoSemanal]],
    scopes_by_item: Mapping[str, int | float | str | Fraction],
    demand_by_item: Mapping[
        str, Mapping[str, Mapping[str, int | float | str | Fraction]]
    ] | None,
    precedences: Sequence[PhysicalPrecedence],
    pool_capacity: Mapping[str, Fraction] | None,
) -> PhysicalCalendarAudit:
    """Reconcile real Skill 04 cells against explicit Skill 05 weekly demand.

    This is a local *post-materialization* witness, not an optimizer, cost
    snapshot or GO certificate. Missing per-item/per-week evidence is an
    error, not inferred zero resource demand. Supplied capacities are checked
    together across all activities in each absolute ISO calendar week.
    The caller must rematerialize both Skill 04 and Skill 05 evidence after
    any shift of start dates, workforce profiles or activity duration.
    """
    ids = set(distributions_by_item)
    if not ids or not all(isinstance(item, str) and item for item in ids):
        raise ValueError("physical audit requires nonempty activity identifiers")
    if set(scopes_by_item) != ids:
        raise ValueError("physical audit requires the exact scope for every activity")
    if demand_by_item is None or set(demand_by_item) != ids:
        raise ValueError("Skill 05 demand provenance is required for every activity")

    activities = tuple(
        materialize_skill04_physical_activity(
            item_id=item,
            scope=scopes_by_item[item],
            calendar_weeks=calendar_weeks,
            distribution=distributions_by_item[item],
            demand_by_week=demand_by_item[item],
        )
        for item in sorted(ids)
    )
    return validate_materialized_calendar(
        activities,
        precedences,
        calendar_horizon_weeks=len(calendar_weeks),
        pool_capacity=pool_capacity,
        require_weekly_capacity=True,
    )
