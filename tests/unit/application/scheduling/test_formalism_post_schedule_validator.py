"""P15-A: falsifiers for post-transformation Q–FS/SS/FF and shared RCPSP pool."""
from __future__ import annotations

from fractions import Fraction as F

import pytest

from concilium.application.scheduling.physical_validator import (
    PhysicalActivity,
    PhysicalPrecedence,
    validate_materialized_calendar,
)


def _a(
    item_id: str,
    start: int,
    end: int,
    outputs: tuple[tuple[int, F], ...],
    *,
    q: F | None = None,
    resource: str | None = None,
    capacities: tuple[tuple[int, F], ...] = (),
) -> PhysicalActivity:
    demands = tuple((week, resource, F(1)) for week in range(start, end)) if resource else ()
    return PhysicalActivity(
        item_id=item_id,
        start_week=start,
        end_week_exclusive=end,
        scope=q if q is not None else sum((v for _, v in outputs), F()),
        deliveries=outputs,
        demands=demands,
        weekly_capacities=capacities,
    )


def _codes(audit: object) -> set[str]:
    return {violation.code for violation in audit.violations}  # type: ignore[attr-defined]


def test_fs_release_occurs_after_delivery_week_not_during_it() -> None:
    a = _a("A", 0, 2, ((0, F(0)), (1, F(10))))
    early = _a("B", 1, 2, ((1, F(1)),))
    late = _a("B", 2, 3, ((2, F(1)),))
    edge = PhysicalPrecedence("A", "B", completion_threshold=F(1))
    bad = validate_materialized_calendar((a, early), (edge,), calendar_horizon_weeks=3)
    good = validate_materialized_calendar((a, late), (edge,), calendar_horizon_weeks=3)
    assert bad.status == "FAIL"
    assert "V6_PREMATURE_FS" in _codes(bad)
    assert good.status == "PASS"


def test_zero_delivery_predecessor_week_never_releases_half_threshold() -> None:
    predecessor = _a("A", 0, 3, ((0, F(0)), (1, F(2)), (2, F(8))))
    successor = _a("B", 2, 3, ((2, F(1)),))
    edge = PhysicalPrecedence("A", "B", completion_threshold=F(1, 2))
    bad = validate_materialized_calendar((predecessor, successor), (edge,), calendar_horizon_weeks=3)
    assert "V6_PREMATURE_FS" in _codes(bad)


def test_exact_one_third_release_at_end_of_week() -> None:
    predecessor = _a("A", 0, 2, ((0, F(1)), (1, F(2))), q=F(3))
    successor = _a("B", 1, 2, ((1, F(1)),))
    edge = PhysicalPrecedence("A", "B", completion_threshold=F(1, 3))
    assert validate_materialized_calendar((predecessor, successor), (edge,), calendar_horizon_weeks=2).status == "PASS"


def test_zero_threshold_is_start_to_start_not_next_week() -> None:
    predecessor = _a("A", 0, 2, ((1, F(1)),))
    successor = _a("B", 0, 1, ((0, F(1)),))
    edge = PhysicalPrecedence("A", "B", completion_threshold=F(0))
    assert validate_materialized_calendar((predecessor, successor), (edge,), calendar_horizon_weeks=2).status == "PASS"


@pytest.mark.parametrize(
    ("kind", "start", "end", "code"),
    [
        ("SS", 0, 1, "V6_PREMATURE_SS"),
        ("FF", 0, 2, "V6_PREMATURE_FF"),
    ],
)
def test_non_fs_lags_are_verified_after_mutation(
    kind: str, start: int, end: int, code: str
) -> None:
    a = _a("A", 0, 3, ((2, F(3)),))
    b = _a("B", start, end, ((start, F(1)),))
    edge = PhysicalPrecedence("A", "B", kind=kind, lag_weeks=1)  # type: ignore[arg-type]
    assert code in _codes(validate_materialized_calendar((a, b), (edge,), calendar_horizon_weeks=4))


def test_climatic_delay_creates_detectable_shared_resource_collision() -> None:
    # After A is delayed, B releases in week 2, colliding with independent C.
    a = _a("A", 0, 2, ((0, F(0)), (1, F(10))))
    b = _a("B", 2, 3, ((2, F(1)),), resource="crane")
    c = _a("C", 2, 3, ((2, F(1)),), resource="crane")
    audit = validate_materialized_calendar(
        (a, b, c), (PhysicalPrecedence("A", "B"),),
        calendar_horizon_weeks=4, pool_capacity={"crane": F(1)},
    )
    assert audit.status == "FAIL"
    assert "V6_POOL_OVERBOOKED" in _codes(audit)
    assert audit.violations[-1].reason == "demand=2; capacity=1"


def test_shifting_successor_restores_pool_feasibility() -> None:
    a = _a("A", 0, 2, ((1, F(10)),))
    b = _a("B", 3, 4, ((3, F(1)),), resource="crane")
    c = _a("C", 2, 3, ((2, F(1)),), resource="crane")
    assert validate_materialized_calendar(
        (a, b, c), (PhysicalPrecedence("A", "B"),),
        calendar_horizon_weeks=4, pool_capacity={"crane": F(1)},
    ).status == "PASS"


def test_missing_pool_data_fails_to_unknown_not_go() -> None:
    a = _a("A", 0, 1, ((0, F(1)),), resource="crane")
    result = validate_materialized_calendar((a,), (), calendar_horizon_weeks=1)
    assert result.status == "UNKNOWN"
    assert "V6_POOL_UNVERIFIED" in _codes(result)
    assert not result.locally_admissible


def test_scope_nonclosure_and_short_horizon_are_failures() -> None:
    a = _a("A", 0, 3, ((0, F(2)), (2, F(1))), q=F(4))
    audit = validate_materialized_calendar((a,), (), calendar_horizon_weeks=2)
    assert {"V1_SCOPE_UNCLOSED", "V6_OUT_OF_HORIZON"} <= _codes(audit)


def test_missing_predecessor_and_invalid_edge_fail_closed() -> None:
    a = _a("A", 0, 1, ((0, F(1)),))
    missing = validate_materialized_calendar(
        (a,), (PhysicalPrecedence("Z", "A"),), calendar_horizon_weeks=1,
    )
    assert "V6_UNKNOWN_EDGE_ITEM" in _codes(missing)
    invalid = validate_materialized_calendar(
        (a,), (PhysicalPrecedence("A", "A", lag_weeks=-1),), calendar_horizon_weeks=1,
    )
    assert "V6_INVALID_EDGE" in _codes(invalid)


def test_calendar_reduced_weekly_capacity_enforces_single_productivity_law() -> None:
    from concilium.domain.services.planning.produtividade import produtividade_realizavel

    # F(2)=20 u/h; H=40h; practicability=.75; calendar=.80.
    available = F(str(40 * produtividade_realizavel(20.0, 0.75, 0.8)))
    assert available == F(480)
    admissible = _a("A", 0, 1, ((0, F(480)),), capacities=((0, available),))
    assert validate_materialized_calendar(
        (admissible,), (), calendar_horizon_weeks=1,
        require_weekly_capacity=True,
    ).status == "PASS"

    # Scope closes, but the claimed 481st unit cannot be produced on that calendar.
    impossible = _a("A", 0, 1, ((0, F(481)),), capacities=((0, available),))
    audit = validate_materialized_calendar(
        (impossible,), (), calendar_horizon_weeks=1,
        require_weekly_capacity=True,
    )
    assert audit.status == "FAIL"
    assert "V1_WEEKLY_CAPACITY_EXCEEDED" in _codes(audit)
    assert not audit.locally_admissible


def test_strict_schedule_without_calendar_capacity_is_unknown() -> None:
    a = _a("A", 0, 1, ((0, F(1)),))
    audit = validate_materialized_calendar(
        (a,), (), calendar_horizon_weeks=1, require_weekly_capacity=True
    )
    assert audit.status == "UNKNOWN"
    assert "V1_WEEKLY_CAPACITY_UNVERIFIED" in _codes(audit)


def test_partial_capacity_witness_is_not_accepted_as_full_evidence() -> None:
    a = _a("A", 0, 2, ((0, F(1)), (1, F(1))), capacities=((0, F(1)),))
    audit = validate_materialized_calendar((a,), (), calendar_horizon_weeks=2)
    assert audit.status == "UNKNOWN"
    assert "V1_WEEKLY_CAPACITY_UNVERIFIED" in _codes(audit)


def test_zero_calendar_availability_disallows_positive_output() -> None:
    a = _a("A", 0, 1, ((0, F(1)),), capacities=((0, F(0)),))
    audit = validate_materialized_calendar(
        (a,), (), calendar_horizon_weeks=1, require_weekly_capacity=True
    )
    assert audit.status == "FAIL"
    assert "V1_WEEKLY_CAPACITY_EXCEEDED" in _codes(audit)


def test_duplicate_or_out_of_weekly_capacities_fail_closed() -> None:
    a = _a("A", 0, 1, ((0, F(1)),), capacities=((0, F(2)), (0, F(2))))
    assert "V1_INVALID_WEEKLY_CAPACITY" in _codes(
        validate_materialized_calendar((a,), (), calendar_horizon_weeks=1)
    )
    b = _a("B", 0, 1, ((0, F(1)),), capacities=((1, F(2)),))
    assert validate_materialized_calendar((b,), (), calendar_horizon_weeks=2).status == "FAIL"
