"""P12-B: differential falsifiers of calendar / Q-FS / resource contention."""
from __future__ import annotations

from dataclasses import replace
from fractions import Fraction

import pytest

from tests.reference_formalism.calendar_rcpsp_oracle import (
    Release,
    SmallScenario,
    Task,
    feasible_schedule,
)


def _f(n: int, d: int = 1) -> Fraction:
    return Fraction(n, d)


def _scenario(
    practicability: tuple[Fraction, ...],
    *,
    horizon: int | None = None,
    theta: Fraction = Fraction(1, 2),
    lag: int = 0,
    successors: int = 2,
) -> SmallScenario:
    n = len(practicability) if horizon is None else horizon
    successors_spec = tuple(
        Task(
            name=f"S{idx}",
            scope=_f(10),
            nominal_weekly_capacity=_f(10),
            demand=(("crane", 1),),
            predecessors=(Release("P", theta, lag),),
        )
        for idx in range(1, successors + 1)
    )
    return SmallScenario(
        tasks=(
            Task("P", _f(100), _f(60)),
            *successors_spec,
        ),
        practicability=practicability[:n],
        calendar=(_f(1),) * n,
        pool={"crane": (1,) * n},
    )


def test_delayed_predecessor_moves_two_successors_without_pool_conflict() -> None:
    dry = _scenario((_f(1),) * 5)
    rain = _scenario((_f(0), _f(1), _f(1), _f(1), _f(1)))
    before = feasible_schedule(dry)
    after = feasible_schedule(rain)
    assert before is not None and after is not None
    assert before["P"].output == ((1, _f(60)), (2, _f(40)))
    assert (before["S1"].start, before["S2"].start) == (2, 3)
    assert after["P"].output == ((1, _f(0)), (2, _f(60)), (3, _f(40)))
    assert (after["S1"].start, after["S2"].start) == (3, 4)
    assert after["S1"].end < after["S2"].start


def test_end_of_week_full_scope_release_with_lag() -> None:
    scenario = _scenario(
        (_f(0), _f(1), _f(1), _f(1), _f(1), _f(1)),
        theta=_f(1), lag=1, successors=1,
    )
    scheduled = feasible_schedule(scenario)
    assert scheduled is not None
    assert scheduled["P"].end == 3
    assert scheduled["S1"].start == 5


def test_pool_conflict_yields_proved_small_horizon_infeasible() -> None:
    scenario = _scenario((_f(0), _f(1), _f(1)))
    assert feasible_schedule(scenario) is None


def test_no_calendar_productivity_does_not_release_a_successor() -> None:
    scenario = _scenario((_f(0),) * 5, successors=1)
    assert feasible_schedule(scenario) is None


def test_zero_practicability_does_not_reduce_intrinsic_installed_productivity() -> None:
    task = Task("A", _f(300), _f(800))
    s = SmallScenario(
        tasks=(task,),
        practicability=(_f(3, 4),),
        calendar=(_f(4, 5),),
        pool={},
    )
    result = feasible_schedule(s)
    assert result is not None
    assert result["A"].output == ((1, _f(300)),)
    assert task.nominal_weekly_capacity == 800


def test_unknown_physical_resource_fails_closed() -> None:
    scenario = SmallScenario(
        tasks=(Task("A", _f(10), _f(10), demand=(("unknown", 1),)),),
        practicability=(_f(1),),
        calendar=(_f(1),),
        pool={},
    )
    with pytest.raises(ValueError, match="undeclared"):
        feasible_schedule(scenario)


def test_negative_or_nonrational_availability_is_rejected() -> None:
    ok = _scenario((_f(1),) * 4)
    with pytest.raises(ValueError, match="exact rational"):
        feasible_schedule(replace(ok, practicability=(-_f(1, 2),) * 4))
    with pytest.raises(ValueError, match="exact rational"):
        feasible_schedule(replace(ok, calendar=(0.5, _f(1), _f(1), _f(1))))


def test_cyclic_predecessors_are_rejected() -> None:
    s = SmallScenario(
        tasks=(
            Task("A", _f(10), _f(10), predecessors=(Release("B", _f(1)),)),
            Task("B", _f(10), _f(10), predecessors=(Release("A", _f(1)),)),
        ),
        practicability=(_f(1), _f(1)),
        calendar=(_f(1), _f(1)),
        pool={},
    )
    with pytest.raises(ValueError, match="cyclic"):
        feasible_schedule(s)
