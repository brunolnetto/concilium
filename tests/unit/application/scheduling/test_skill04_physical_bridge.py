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
    _quantity,
    audit_skill04_skill05_physical_snapshot,
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


@pytest.mark.parametrize(
    ("q_first", "cum_first", "q_second", "cum_second"),
    [
        (0, 4, 10, 10),    # fictitious predecessor progress in a no-output week
        (3, 3, 7, 12),    # fabricated cumulative progress at the end
        (3, 4, 7, 10),    # later Q closes, but the first week's evidence is forged
    ],
)
def test_bridge_rejects_cumulative_progress_not_backed_by_deliveries(
    q_first: float, cum_first: float, q_second: float, cum_second: float
) -> None:
    with pytest.raises(ValueError, match="cumulative quantity does not reconcile"):
        materialize_skill04_physical_activity(
            item_id="A",
            scope=10,
            calendar_weeks=WEEKS,
            distribution={
                WEEKS[0]: cell(q_first, cum_first, 10),
                WEEKS[1]: cell(q_second, cum_second, 10),
            },
            demand_by_week={WEEKS[0]: {}, WEEKS[1]: {}},
        )


def test_joint_skill04_skill05_audit_fails_shared_resource_collision() -> None:
    # Two individually admissible Skill 04 schedules have overlapping
    # *real* Skill 05 resource reservations in the same absolute week.
    audit = audit_skill04_skill05_physical_snapshot(
        calendar_weeks=WEEKS,
        distributions_by_item={
            "A": {WEEKS[0]: cell(1, 1, 1)},
            "B": {WEEKS[0]: cell(1, 1, 1)},
        },
        scopes_by_item={"A": 1, "B": 1},
        demand_by_item={
            "A": {WEEKS[0]: {"crane": 1}},
            "B": {WEEKS[0]: {"crane": 1}},
        },
        precedences=(),
        pool_capacity={"crane": F(1)},
    )
    assert audit.status == "FAIL"
    assert any(v.code == "V6_POOL_OVERBOOKED" and v.week == 0 for v in audit.violations)


def test_joint_skill04_skill05_audit_passes_only_with_recomputed_weekly_demand() -> None:
    audit = audit_skill04_skill05_physical_snapshot(
        calendar_weeks=WEEKS,
        distributions_by_item={
            "A": {WEEKS[0]: cell(1, 1, 1)},
            "B": {WEEKS[1]: cell(1, 1, 1)},
        },
        scopes_by_item={"A": 1, "B": 1},
        demand_by_item={
            "A": {WEEKS[0]: {"crane": 1}},
            "B": {WEEKS[1]: {"crane": 1}},
        },
        precedences=(PhysicalPrecedence("A", "B", "FS", 0, F(1)),),
        pool_capacity={"crane": F(1)},
    )
    assert audit.status == "PASS"
    assert not audit.violations


def test_joint_skill04_skill05_audit_must_not_infer_missing_skill05_data() -> None:
    kwargs = dict(
        calendar_weeks=WEEKS,
        distributions_by_item={"A": {WEEKS[0]: cell(1, 1, 1)}},
        scopes_by_item={"A": 1},
        precedences=(),
        pool_capacity={"crane": F(1)},
    )
    with pytest.raises(ValueError, match="demand provenance"):
        audit_skill04_skill05_physical_snapshot(**kwargs, demand_by_item=None)
    with pytest.raises(ValueError, match="resource demand must explicitly cover"):
        audit_skill04_skill05_physical_snapshot(**kwargs, demand_by_item={"A": {}})


def test_joint_skill04_skill05_audit_marks_unknown_shared_pool() -> None:
    audit = audit_skill04_skill05_physical_snapshot(
        calendar_weeks=WEEKS,
        distributions_by_item={"A": {WEEKS[0]: cell(1, 1, 1)}},
        scopes_by_item={"A": 1},
        demand_by_item={"A": {WEEKS[0]: {"crane": 1}}},
        precedences=(),
        pool_capacity=None,
    )
    assert audit.status == "UNKNOWN"
    assert any(v.code == "V6_POOL_UNVERIFIED" for v in audit.violations)


def test_exact_quantity_conversion_does_not_round_through_binary_float() -> None:
    # Crossing a binary float boundary must not turn a finite physical
    # witness into infinity or truncate very large exact integers.
    big = 10**400
    assert _quantity(str(big), "Q") == F(big)
    with pytest.raises(ValueError, match="finite"):
        _quantity("Infinity", "Q")


def test_exact_residual_from_exhausted_skill04_calendar_fails_independent_physical_audit() -> None:
    """P14's best real-calendar delivery must remain infeasible in P15's bridge."""
    weeks = WEEKS[:3]
    distribution = {
        weeks[0]: cell(10, 10, 10),
        weeks[1]: cell(10, 20, 10),
        weeks[2]: cell(10, 30, 10),
    }
    audit = audit_skill04_skill05_physical_snapshot(
        calendar_weeks=weeks,
        distributions_by_item={"A": distribution},
        scopes_by_item={"A": 50},
        demand_by_item={"A": {week: {} for week in weeks}},
        precedences=(),
        pool_capacity={},
    )
    assert audit.status == "FAIL"
    failure = next(v for v in audit.violations if v.code == "V1_SCOPE_UNCLOSED")
    assert failure.item_id == "A"
    assert "Q=50" in failure.detail
    assert "sum_q=30" in failure.detail
    assert "absolute_error=20" in failure.detail
