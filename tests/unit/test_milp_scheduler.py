"""Tests for the MILP scheduler (ADR-004).

PuLP 2.9.0 is a declared production dependency. These tests exercise the
actual CBC solver — no mocking of PuLP.
"""

from __future__ import annotations

import pytest

from concilium.application.scheduling.milp import MILPScheduler, _compute_metrics
from concilium.application.scheduling.models import (
    Activity,
    ActivityDAG,
    ResourcePool,
    ScheduledActivity,
    ScheduleError,
)

# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def two_serial_activities():
    """A → B chain, 1 week each, single resource with capacity 1."""
    acts = [
        Activity(activity_id="A", description="Task A", duration_weeks=1, required_resources={"workers": 1}),
        Activity(activity_id="B", description="Task B", duration_weeks=1, required_resources={"workers": 1}),
    ]
    dag = ActivityDAG(activities=acts, precedence=[("A", "B")])
    pool = ResourcePool(resources={"workers": 1})
    return acts, dag, pool


@pytest.fixture
def three_parallel_activities():
    """Three independent activities, each needing 1 resource, pool = 2 → must serialize one."""
    acts = [
        Activity(activity_id="X", description="X", duration_weeks=2, required_resources={"machine": 1}),
        Activity(activity_id="Y", description="Y", duration_weeks=2, required_resources={"machine": 1}),
        Activity(activity_id="Z", description="Z", duration_weeks=2, required_resources={"machine": 1}),
    ]
    dag = ActivityDAG(activities=acts, precedence=[])
    pool = ResourcePool(resources={"machine": 2})
    return acts, dag, pool


# ── basic functionality ────────────────────────────────────────────────────────


def test_milp_scheduler_instantiates():
    s = MILPScheduler()
    assert s.timeout_seconds == 30
    assert s.verbose is False


def test_milp_scheduler_custom_params():
    s = MILPScheduler(timeout_seconds=10, verbose=True)
    assert s.timeout_seconds == 10
    assert s.verbose is True


def test_milp_solves_two_serial(two_serial_activities):
    acts, dag, pool = two_serial_activities
    scheduler = MILPScheduler(timeout_seconds=30)
    result = scheduler.schedule(activities=acts, dag=dag, pool=pool, deadline_weeks=5)

    assert result.feasible is True
    assert result.heuristic == "MILP"
    assert result.makespan == 2  # A at week 0, B at week 1 → finish at 2

    ids = {a.activity_id for a in result.scheduled_activities}
    assert ids == {"A", "B"}

    # Precedence respected: B starts after A finishes
    starts = {a.activity_id: a.start_week for a in result.scheduled_activities}
    assert starts["B"] >= starts["A"] + 1


def test_milp_respects_resource_capacity(three_parallel_activities):
    acts, dag, pool = three_parallel_activities
    scheduler = MILPScheduler(timeout_seconds=30)
    result = scheduler.schedule(activities=acts, dag=dag, pool=pool, deadline_weeks=10)

    assert result.feasible is True
    # With machine capacity=2 and 3 activities needing 1 each, at least 2 time slots needed
    # (two can run in parallel, third must wait)
    assert result.makespan >= 4  # each takes 2 weeks; at most 2 at once

    # No week should have more than 2 machines running simultaneously
    usage_by_week: dict[int, int] = {}
    for act in result.scheduled_activities:
        for w in range(act.start_week, act.end_week):
            usage_by_week[w] = usage_by_week.get(w, 0) + act.assigned_resources.get("machine", 0)
    for week, usage in usage_by_week.items():
        assert usage <= 2, f"Resource capacity violated in week {week}: {usage} > 2"


def test_milp_single_activity_no_precedence():
    acts = [Activity(activity_id="solo", description="Solo task", duration_weeks=3)]
    dag = ActivityDAG(activities=acts, precedence=[])
    pool = ResourcePool(resources={})
    scheduler = MILPScheduler(timeout_seconds=10)
    result = scheduler.schedule(activities=acts, dag=dag, pool=pool, deadline_weeks=5)
    assert result.feasible is True
    assert result.makespan == 3


def test_milp_metrics_populated(two_serial_activities):
    acts, dag, pool = two_serial_activities
    scheduler = MILPScheduler(timeout_seconds=30)
    result = scheduler.schedule(activities=acts, dag=dag, pool=pool, deadline_weeks=5)
    m = result.metrics
    assert m.makespan >= 1
    assert 0.0 <= m.resource_leveling_score <= 1.0
    assert m.idle_time >= 0
    assert 0.0 <= m.resource_utilization_avg <= 1.0


def test_milp_infeasible_deadline_too_tight():
    """Minimum makespan > deadline → must raise ScheduleError."""
    acts = [
        Activity(activity_id="A", description="A", duration_weeks=3, required_resources={}),
        Activity(activity_id="B", description="B", duration_weeks=3, required_resources={}),
    ]
    dag = ActivityDAG(activities=acts, precedence=[("A", "B")])
    pool = ResourcePool(resources={})
    scheduler = MILPScheduler(timeout_seconds=5)
    with pytest.raises(ScheduleError, match="Infeasible"):
        scheduler.schedule(activities=acts, dag=dag, pool=pool, deadline_weeks=4)


def test_milp_no_resource_constraint():
    """Activities with no resource requirements can all run in parallel."""
    acts = [Activity(activity_id=f"act{i}", description=f"Act {i}", duration_weeks=2) for i in range(4)]
    dag = ActivityDAG(activities=acts, precedence=[])
    pool = ResourcePool(resources={})
    scheduler = MILPScheduler(timeout_seconds=30)
    result = scheduler.schedule(activities=acts, dag=dag, pool=pool, deadline_weeks=10)
    assert result.feasible is True
    # All can start at week 0 — makespan == 2
    assert result.makespan == 2


def test_milp_chain_of_four():
    """4-activity serial chain: makespan = sum of durations."""
    acts = [
        Activity(activity_id="A", description="A", duration_weeks=1),
        Activity(activity_id="B", description="B", duration_weeks=2),
        Activity(activity_id="C", description="C", duration_weeks=1),
        Activity(activity_id="D", description="D", duration_weeks=1),
    ]
    dag = ActivityDAG(activities=acts, precedence=[("A", "B"), ("B", "C"), ("C", "D")])
    pool = ResourcePool(resources={})
    scheduler = MILPScheduler(timeout_seconds=30)
    result = scheduler.schedule(activities=acts, dag=dag, pool=pool, deadline_weeks=10)
    assert result.feasible is True
    assert result.makespan == 5


def test_milp_activity_resource_assignment_in_output(two_serial_activities):
    """Assigned resources in output match the activity's required_resources."""
    acts, dag, pool = two_serial_activities
    scheduler = MILPScheduler(timeout_seconds=30)
    result = scheduler.schedule(activities=acts, dag=dag, pool=pool, deadline_weeks=5)
    for sched_act in result.scheduled_activities:
        orig = next(a for a in acts if a.activity_id == sched_act.activity_id)
        assert sched_act.assigned_resources == orig.required_resources


# ── _compute_metrics helper ───────────────────────────────────────────────────


def test_compute_metrics_zero_makespan():
    """_compute_metrics with makespan=0 returns safe defaults."""
    pool = ResourcePool(resources={"w": 2})
    metrics = _compute_metrics([], pool, makespan=0, deadline_weeks=5)
    assert metrics.makespan == 0
    assert metrics.resource_leveling_score == 1.0
    assert metrics.idle_time == 0


def test_compute_metrics_single_activity():
    scheduled = [
        ScheduledActivity(
            activity_id="A",
            start_week=0,
            end_week=2,
            duration_weeks=2,
            assigned_resources={"w": 1},
        )
    ]
    pool = ResourcePool(resources={"w": 2})
    metrics = _compute_metrics(scheduled, pool, makespan=2, deadline_weeks=5)
    assert metrics.makespan == 2
    assert metrics.resource_leveling_score >= 0.0
    assert metrics.idle_time >= 0


def test_compute_metrics_quality_score():
    scheduled = [
        ScheduledActivity(
            activity_id="A",
            start_week=0,
            end_week=1,
            duration_weeks=1,
            assigned_resources={"w": 1},
        )
    ]
    pool = ResourcePool(resources={"w": 1})
    metrics = _compute_metrics(scheduled, pool, makespan=1, deadline_weeks=5)
    q = metrics.quality_score(deadline_weeks=5)
    assert 0.0 < q <= 1.0
