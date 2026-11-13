"""ADR-072 window = corridor span counted from the activity's release (owner decision 2026-11-13).

finish <= release + window_weeks, release = earliest start allowed by predecessors
(FS end, FS with theta, SS/FS+lag) and readiness. With no predecessors the release
is 0, so the old absolute behaviour is unchanged.
"""

from __future__ import annotations

import pytest

from concilium.application.scheduling import Activity, ActivityDAG, ResourcePool
from concilium.application.scheduling.cpsat_scheduler import CpSatScheduler
from concilium.application.scheduling.scheduler import SerialScheduler


def _chain(window: int | None) -> ActivityDAG:
    """A -> (theta 0.5) -> B -> C, productive 1 week each, window 2 each."""
    acts = [
        Activity(activity_id=i, description=i, duration_weeks=1, required_resources={"R": 1}, window_weeks=window)
        for i in ("A", "B", "C")
    ]
    return ActivityDAG(activities=acts, precedence=[("A", "B"), ("B", "C")], thresholds={("A", "B"): 0.5})


def _cpsat(dag: ActivityDAG, cap: int = 2):
    return CpSatScheduler(timeout_seconds=10.0, horizon_weeks=23).schedule(
        dag=dag, pool=ResourcePool(resources={"R": cap})
    )


def _sgs(dag: ActivityDAG, cap: int = 2):
    return SerialScheduler().schedule(dag.activities, dag, ResourcePool(resources={"R": cap}), deadline_weeks=20)


@pytest.mark.parametrize("solve", [_cpsat, _sgs], ids=["cpsat", "sgs"])
def test_chained_activities_with_windows_are_feasible(solve) -> None:
    """Was INFEASIBLE: C (window 2 from t = 0) could not start before week 2."""
    out = solve(_chain(window=2))
    assert out.feasible
    by_id = {s.activity_id: s for s in out.scheduled_activities}
    assert by_id["C"].start_week >= by_id["B"].end_week


def test_window_still_bounds_slack_after_release_cpsat() -> None:
    """B released at week 1 (A's start + ceil(0.5*1)); window 1 forces B to finish by
    week 2, so the shared single unit of R cannot delay it: C absorbs the wait."""
    acts = [
        Activity(activity_id="A", description="A", duration_weeks=1, required_resources={"R": 1}),
        Activity(activity_id="B", description="B", duration_weeks=1, required_resources={"R": 1}, window_weeks=1),
        Activity(activity_id="X", description="X", duration_weeks=3, required_resources={"R": 1}),
    ]
    dag = ActivityDAG(activities=acts, precedence=[("A", "B")], thresholds={("A", "B"): 0.5})
    out = _cpsat(dag, cap=1)
    by_id = {s.activity_id: s for s in out.scheduled_activities}
    release = by_id["A"].start_week + 1
    assert by_id["B"].end_week <= release + 1


def test_root_activity_window_is_unchanged_absolute() -> None:
    acts = [Activity(activity_id="A", description="A", duration_weeks=2, required_resources={"R": 1}, window_weeks=2)]
    out = _cpsat(ActivityDAG(activities=acts, precedence=[]))
    assert out.scheduled_activities[0].end_week <= 2


def test_sgs_window_relative_to_release_rejects_when_resources_push_past_it() -> None:
    acts = [
        Activity(activity_id="A", description="A", duration_weeks=1, required_resources={"R": 1}),
        Activity(activity_id="X", description="X", duration_weeks=3, required_resources={"R": 1}),
        Activity(activity_id="B", description="B", duration_weeks=1, required_resources={"R": 1}, window_weeks=1),
    ]
    dag = ActivityDAG(activities=acts, precedence=[("A", "B"), ("X", "B")])
    out = _sgs(dag, cap=1)
    by_id = {s.activity_id: s for s in out.scheduled_activities}
    release = max(by_id["A"].end_week, by_id["X"].end_week)
    assert by_id["B"].end_week <= release + 1
