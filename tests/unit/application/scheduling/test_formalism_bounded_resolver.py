"""Finite physical RCPSP falsifiers; calendar must be re-materialized."""
from __future__ import annotations

from fractions import Fraction as F

import pytest

from concilium.application.scheduling.physical_resolver import (
    resolve_bounded_physical_calendar,
)
from concilium.application.scheduling.physical_validator import (
    PhysicalActivity,
    PhysicalPrecedence,
)


def _a(
    name: str, start: int, *, productive_offset: int = 0,
    with_resource: bool = False,
) -> PhysicalActivity:
    week = start + productive_offset
    return PhysicalActivity(
        item_id=name,
        scope=F(1),
        start_week=start,
        end_week_exclusive=week + 1,
        deliveries=((week, F(1)),),
        demands=((week, "crane", F(1)),) if with_resource else (),
        weekly_capacities=((week, F(1)),),
    )


def test_re_materializes_climate_delayed_predecessor_and_fs_release() -> None:
    requested: list[tuple[str, int]] = []

    def materialize(name: str, start: int) -> PhysicalActivity:
        requested.append((name, start))
        # A has ZERO output during its first week and delivers at start+1.
        return _a(name, start, productive_offset=1 if name == "A" else 0)

    result = resolve_bounded_physical_calendar(
        ["B", "A"],
        {"A": [0], "B": [1, 2, 3]},
        materialize,
        [PhysicalPrecedence("A", "B", "FS", 0, F(1))],
        calendar_horizon_weeks=5,
        pool_capacity={},
    )
    assert result.status == "PASS"
    assert result.activities is not None
    assert [a.start_week for a in result.activities] == [0, 2]
    assert ("B", 1) in requested and ("B", 2) in requested
    assert result.attempts == 2
    assert not result.complete_search  # a feasible witness does not exhaust later starts


def test_exact_shared_resource_reallocation_in_multi_activity_calendar() -> None:
    result = resolve_bounded_physical_calendar(
        ("C", "B"),
        {"B": [1, 2], "C": [1, 2]},
        lambda item, start: _a(item, start, with_resource=True),
        (),
        calendar_horizon_weeks=3,
        pool_capacity={"crane": F(1)},
    )
    assert result.status == "PASS"
    assert result.attempts == 2
    assert [(a.item_id, a.start_week) for a in result.activities or ()] == [
        ("B", 1), ("C", 2)
    ]


def test_unknown_pool_cannot_become_pass_or_no_go_proof() -> None:
    result = resolve_bounded_physical_calendar(
        ("B",),
        {"B": [1]},
        lambda item, start: _a(item, start, with_resource=True),
        (),
        calendar_horizon_weeks=3,
        pool_capacity=None,
    )
    assert result.status == "UNKNOWN"
    assert not result.locally_admissible
    assert result.complete_search


def test_exhaustive_infeasible_calendar_has_fail_not_success() -> None:
    result = resolve_bounded_physical_calendar(
        ("B",),
        {"B": [0, 1]},
        lambda item, start: None,  # no productive calendar within the horizon
        (),
        calendar_horizon_weeks=3,
        pool_capacity={},
    )
    assert result.status == "FAIL"
    assert result.attempts == 2
    assert result.complete_search


def test_truncated_search_is_unknown_not_false_infeasibility() -> None:
    result = resolve_bounded_physical_calendar(
        ("A", "B"),
        {"A": [0], "B": [0, 1]},
        lambda item, start: _a(item, start, with_resource=True),
        (),
        calendar_horizon_weeks=3,
        pool_capacity={"crane": F(1)},
        max_states=1,
    )
    assert result.status == "UNKNOWN"
    assert not result.complete_search
    assert result.attempts == 1


def test_bad_materializer_cannot_move_quantity_between_weeks_silently() -> None:
    with pytest.raises(ValueError, match="mismatched"):
        resolve_bounded_physical_calendar(
            ("A",), {"A": [1]},
            lambda item, start: _a(item, start + 1),
            (), calendar_horizon_weeks=4, pool_capacity={},
        )


def test_invalid_search_parameters_are_rejected() -> None:
    def materialize(item: str, start: int) -> PhysicalActivity:
        return _a(item, start)

    with pytest.raises(ValueError):
        resolve_bounded_physical_calendar(
            ("A",), {"A": [-1]}, materialize, (),
            calendar_horizon_weeks=3, pool_capacity={},
        )
    with pytest.raises(ValueError):
        resolve_bounded_physical_calendar(
            ("A",), {"A": [0]}, materialize, (),
            calendar_horizon_weeks=3, pool_capacity={}, max_states=0,
        )
    with pytest.raises(ValueError):
        resolve_bounded_physical_calendar(
            ("A",), {"B": [0]}, materialize, (),
            calendar_horizon_weeks=3, pool_capacity={},
        )


def test_bounded_resolver_rejects_positive_q_without_capacity_witness() -> None:
    def materialize(item: str, start: int) -> PhysicalActivity:
        return PhysicalActivity(
            item_id=item, scope=F(1), start_week=start,
            end_week_exclusive=start + 1, deliveries=((start, F(1)),),
        )

    result = resolve_bounded_physical_calendar(
        ("A",), {"A": [0]}, materialize, (),
        calendar_horizon_weeks=2, pool_capacity={},
    )
    assert result.status == "UNKNOWN"
    assert not result.locally_admissible
    assert result.last_audit is not None
    assert any(
        violation.code == "V1_WEEKLY_CAPACITY_UNVERIFIED"
        for violation in result.last_audit.violations
    )


def test_bounded_resolver_rejects_q_above_calendar_limited_capacity() -> None:
    def materialize(item: str, start: int) -> PhysicalActivity:
        # Advertises full closure of Q=1 although weather/calendar allow 3/4.
        return PhysicalActivity(
            item_id=item, scope=F(1), start_week=start,
            end_week_exclusive=start + 1, deliveries=((start, F(1)),),
            weekly_capacities=((start, F(3, 4)),),
        )

    result = resolve_bounded_physical_calendar(
        ("A",), {"A": [0]}, materialize, (),
        calendar_horizon_weeks=2, pool_capacity={},
    )
    assert result.status == "FAIL"
    assert result.last_audit is not None
    assert any(
        violation.code == "V1_WEEKLY_CAPACITY_EXCEEDED"
        for violation in result.last_audit.violations
    )
