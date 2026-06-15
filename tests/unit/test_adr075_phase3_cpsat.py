"""ADR-075 Phase 3 — CP-SAT Scheduler: TDD test suite.

Tests for CpSatScheduler — exact RCPSP with SS/FF+lag via OR-Tools CP-SAT.
Uses the existing Activity / ActivityDAG / ResourcePool / ScheduleOutput API.
Written before implementation (red phase).
"""

from __future__ import annotations

from concilium.application.scheduling.cpsat_scheduler import (
    CpSatScheduler,
    ExtendedPrecedence,
)
from concilium.application.scheduling.models import (
    Activity,
    ActivityDAG,
    ResourcePool,
    ScheduleOutput,
)
from concilium.domain.models.analytics.optimization import RampProfile

# ── helpers ───────────────────────────────────────────────────────────────────


def _act(aid: str, dur: int, demand: int = 2, window: int | None = None) -> Activity:
    return Activity(
        activity_id=aid,
        description="",
        duration_weeks=dur,
        required_resources={"E": demand},
        window_weeks=window,
    )


def _dag_chain(n: int, duration: int = 4) -> tuple[ActivityDAG, list[Activity]]:
    """Linear FS chain of n activities."""
    activities = [_act(f"A{i}", duration, demand=2) for i in range(n)]
    precedence = [(f"A{i}", f"A{i + 1}") for i in range(n - 1)]
    dag = ActivityDAG(activities=activities, precedence=precedence)
    return dag, activities


def _pool(capacity: int = 10) -> ResourcePool:
    return ResourcePool(resources={"E": capacity})


def _ramps(activities: list[Activity], K: int = 2) -> dict[str, RampProfile]:
    return {
        a.activity_id: RampProfile.build(
            a.activity_id,
            K_max=K,
            r=0,
            d=0,
            n_i=a.duration_weeks,
            resources_per_team={"E": 1},
        )
        for a in activities
    }


def _get(result: ScheduleOutput, aid: str):
    return next(sa for sa in result.scheduled_activities if sa.activity_id == aid)


# ── Feasibility ───────────────────────────────────────────────────────────────


class TestCpSatSchedulerFeasibility:
    def test_single_activity_schedules(self):
        """Single activity with no constraints is trivially feasible."""
        acts = [_act("A", 4, 2)]
        dag = ActivityDAG(activities=acts, precedence=[])
        scheduler = CpSatScheduler(timeout_seconds=10.0)
        result = scheduler.schedule(dag, _pool(10), ramp_profiles=_ramps(acts))
        assert isinstance(result, ScheduleOutput)
        assert result.feasible
        assert len(result.scheduled_activities) == 1
        assert result.scheduled_activities[0].start_week >= 0

    def test_chain_respects_fs_precedences(self):
        """In A0->A1->A2 chain (FS), each activity must start after previous ends."""
        dag, acts = _dag_chain(3, duration=4)
        scheduler = CpSatScheduler(timeout_seconds=10.0)
        result = scheduler.schedule(dag, _pool(10), ramp_profiles=_ramps(acts))
        assert result.feasible
        assert _get(result, "A1").start_week >= _get(result, "A0").start_week + 4
        assert _get(result, "A2").start_week >= _get(result, "A1").start_week + 4

    def test_resource_capacity_respected(self):
        """With resource constraints, total demand never exceeds capacity."""
        activities = [_act(f"P{i}", 4, demand=4) for i in range(3)]
        dag = ActivityDAG(activities=activities, precedence=[])
        scheduler = CpSatScheduler(timeout_seconds=10.0)
        result = scheduler.schedule(dag, _pool(10), ramp_profiles=_ramps(activities, K=1))
        assert result.feasible
        usage: dict[int, int] = {}
        for sa in result.scheduled_activities:
            for t in range(sa.start_week, sa.end_week):
                usage[t] = usage.get(t, 0) + 4
        assert all(v <= 10 for v in usage.values()), f"Capacity violated: {usage}"

    def test_sequential_heavy_activities_feasible(self):
        """Two activities with demand=8 each and FS: must run sequentially."""
        activities = [_act("X", 4, demand=8), _act("Y", 4, demand=8)]
        dag = ActivityDAG(activities=activities, precedence=[("X", "Y")])
        scheduler = CpSatScheduler(timeout_seconds=5.0)
        result = scheduler.schedule(dag, _pool(10), ramp_profiles=_ramps(activities, K=1))
        assert result.feasible
        assert _get(result, "Y").start_week >= _get(result, "X").start_week + 4


# ── Extended precedences ───────────────────────────────────────────────────────


class TestCpSatSchedulerExtendedPrecedences:
    def test_ss_lag_constraint(self):
        """SS+lag=2: B must start at least 2 weeks after A starts."""
        activities = [_act("A", 8, demand=1), _act("B", 6, demand=1)]
        dag = ActivityDAG(activities=activities, precedence=[])
        ext_prec = [ExtendedPrecedence(pred="A", succ="B", tipo="SS", lag=2)]
        scheduler = CpSatScheduler(timeout_seconds=10.0)
        result = scheduler.schedule(dag, _pool(10), extended_precedences=ext_prec)
        assert result.feasible
        a_start = _get(result, "A").start_week
        b_start = _get(result, "B").start_week
        assert b_start >= a_start + 2, f"SS+2: {b_start} < {a_start} + 2"

    def test_ff_lag_constraint(self):
        """FF+lag=1: B must finish at least 1 week after A finishes."""
        activities = [_act("A", 6, demand=1), _act("B", 4, demand=1)]
        dag = ActivityDAG(activities=activities, precedence=[])
        ext_prec = [ExtendedPrecedence(pred="A", succ="B", tipo="FF", lag=1)]
        scheduler = CpSatScheduler(timeout_seconds=10.0)
        result = scheduler.schedule(dag, _pool(10), extended_precedences=ext_prec)
        assert result.feasible
        a_end = _get(result, "A").start_week + 6
        b_end = _get(result, "B").start_week + 4
        assert b_end >= a_end + 1, f"FF+1: {b_end} < {a_end} + 1"

    def test_fs_with_lag(self):
        """FS+lag=3: B must start at least 3 weeks after A finishes."""
        activities = [_act("A", 4, demand=1), _act("B", 4, demand=1)]
        dag = ActivityDAG(activities=activities, precedence=[])
        ext_prec = [ExtendedPrecedence(pred="A", succ="B", tipo="FS", lag=3)]
        scheduler = CpSatScheduler(timeout_seconds=10.0)
        result = scheduler.schedule(dag, _pool(10), extended_precedences=ext_prec)
        assert result.feasible
        a_end = _get(result, "A").start_week + 4
        b_start = _get(result, "B").start_week
        assert b_start >= a_end + 3


# ── Objective ──────────────────────────────────────────────────────────────────


class TestCpSatSchedulerObjective:
    def test_minimises_makespan_chain(self):
        """Unconstrained chain of 3 activities x 2 weeks: optimal makespan = 6."""
        dag, acts = _dag_chain(3, duration=2)
        scheduler = CpSatScheduler(timeout_seconds=10.0)
        result = scheduler.schedule(dag, _pool(100), ramp_profiles=_ramps(acts))
        assert result.feasible
        assert result.makespan == 6

    def test_window_constraint_respected(self):
        """Activity with window_weeks=10: must finish by week 10."""
        acts = [_act("W", 4, window=10)]
        dag = ActivityDAG(activities=acts, precedence=[])
        scheduler = CpSatScheduler(timeout_seconds=10.0)
        result = scheduler.schedule(dag, _pool(10))
        assert result.feasible
        sa = result.scheduled_activities[0]
        assert sa.end_week <= 10

    def test_timeout_returns_best_found(self):
        """With very short timeout, scheduler returns best found without raising."""
        dag, acts = _dag_chain(20, duration=4)
        scheduler = CpSatScheduler(timeout_seconds=0.1)
        result = scheduler.schedule(dag, _pool(10), ramp_profiles=_ramps(acts))
        assert result is not None
        assert isinstance(result.feasible, bool)
