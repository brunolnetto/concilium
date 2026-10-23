"""P15-C: real Skill 04 weekly cells to P15-B bounded physical resolver."""
from __future__ import annotations

from fractions import Fraction as F

import pytest

from concilium.application.scheduling.physical_resolver import (
    resolve_bounded_physical_calendar,
)
from concilium.application.scheduling.physical_validator import (
    PhysicalPrecedence,
    validate_materialized_calendar,
)
from concilium.application.scheduling.skill04_physical_bridge import (
    materialize_skill04_physical_activity,
)
from concilium.domain.models.canonical import DistribuicaoSemanal

WEEKS = ("2026-W01", "2026-W02", "2026-W03", "2026-W04", "2026-W05")


def cell(q: float, cumulative: float, cap: float) -> DistribuicaoSemanal:
    return DistribuicaoSemanal(
        num_equipes=1, qtd_executada=q, qtd_acumulada=cumulative,
        pct=min(1.0, cumulative / 10), q_max_celula=10,
        capacidade_disponivel_semana=cap,
    )


def make(name: str, start: int):
    if name == "A":
        # First week has zero availability; Q=10 is delivered in next week.
        weeks = WEEKS[start:start + 2]
        if len(weeks) < 2:
            return None
        mapping = {weeks[0]: cell(0, 0, 0), weeks[1]: cell(10, 10, 10)}
        demand = {weeks[0]: {}, weeks[1]: {}}
        scope = 10
    else:
        week = WEEKS[start]
        mapping = {week: cell(1, 1, 1)}
        demand = {week: {"crane": F(1)}}
        scope = 1
    return materialize_skill04_physical_activity(
        item_id=name, scope=scope, calendar_weeks=WEEKS,
        distribution=mapping, demand_by_week=demand,
    )


def test_three_activities_recomputed_after_climate_delay_and_resource_collision() -> None:
    """B at week1 violates Q–FS, week2 collides with C, week3 succeeds."""
    resolved = resolve_bounded_physical_calendar(
        ("B", "C", "A"),
        {"A": [0], "B": [1, 2, 3], "C": [2]},
        make,
        (PhysicalPrecedence("A", "B", "FS", 0, F(1)),),
        calendar_horizon_weeks=len(WEEKS),
        pool_capacity={"crane": F(1)},
    )
    assert resolved.status == "PASS"
    assert resolved.attempts == 3
    assert [(a.item_id, a.start_week) for a in resolved.activities or ()] == [
        ("A", 0), ("B", 3), ("C", 2)
    ]
    assert resolved.last_audit is not None
    assert resolved.last_audit.status == "PASS"


def test_weekly_cell_without_independent_capacity_witness_is_rejected() -> None:
    entry = cell(1, 1, 1).model_copy(update={"capacidade_disponivel_semana": None})
    with pytest.raises(ValueError, match="capacity witness"):
        materialize_skill04_physical_activity(
            item_id="B", scope=1, calendar_weeks=WEEKS,
            distribution={WEEKS[0]: entry}, demand_by_week={WEEKS[0]: {}},
        )


def test_resource_demand_cannot_be_inferred_as_zero() -> None:
    with pytest.raises(ValueError, match="resource demand"):
        materialize_skill04_physical_activity(
            item_id="B", scope=1, calendar_weeks=WEEKS,
            distribution={WEEKS[0]: cell(1, 1, 1)}, demand_by_week=None,
        )


def test_missing_zero_productivity_week_is_not_silently_skipped() -> None:
    with pytest.raises(ValueError, match="missing physical activity week"):
        materialize_skill04_physical_activity(
            item_id="A", scope=10, calendar_weeks=WEEKS,
            distribution={WEEKS[0]: cell(0, 0, 0), WEEKS[2]: cell(10, 10, 10)},
            demand_by_week={WEEKS[0]: {}, WEEKS[2]: {}},
        )


def test_oversold_calendar_capacity_cannot_create_a_physical_witness() -> None:
    with pytest.raises(ValueError, match="physical F"):
        materialize_skill04_physical_activity(
            item_id="B", scope=1, calendar_weeks=WEEKS,
            distribution={WEEKS[0]: cell(1, 1, 0.75)},
            demand_by_week={WEEKS[0]: {}},
        )


def test_bridge_produces_local_audit_not_an_automatic_go_certificate() -> None:
    activity = make("B", 3)
    assert activity is not None
    assert activity.weekly_capacities == ((3, F(1)),)
    audit = validate_materialized_calendar(
        (activity,), (), calendar_horizon_weeks=5,
        pool_capacity={"crane": F(1)}, require_weekly_capacity=True,
    )
    assert audit.status == "PASS"
    # Audit is local V1/V6 only; it does not validate economic/governance GO.
    assert not hasattr(audit, "decision")
