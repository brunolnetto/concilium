"""ADR-004: Optional MILP scheduler using PuLP/CBC.

This module provides an exact MILP formulation for activity scheduling.
PuLP is an *optional* dependency — the module degrades gracefully when it is
not installed, raising ``ImportError`` at schedule time rather than at import.

Formulation (Resource-Constrained Project Scheduling Problem — RCPSP):
  - Binary variable x[i,t] = 1 if activity i starts in week t.
  - Each activity must start exactly once within the planning horizon.
  - Precedence: successor start >= predecessor finish.
  - Resource capacity: total demand in any week <= pool capacity.
  - Objective: minimise makespan (= latest finish week).
"""

from __future__ import annotations

import math
from typing import Any

from .models import (
    Activity,
    ActivityDAG,
    ResourcePool,
    ScheduledActivity,
    ScheduleError,
    ScheduleMetrics,
    ScheduleOutput,
)

# Optional PuLP dependency — detected at module load time.
try:
    import pulp  # type: ignore[import-untyped]  # noqa: F401

    _HAS_PULP = True
except ImportError:
    _HAS_PULP = False


class MILPScheduler:
    """Exact MILP scheduler for small, high-criticality instances (ADR-004).

    Falls back gracefully when PuLP is not installed.
    Enforces a ``timeout_seconds`` limit via the CBC solver's ``timeLimit``
    parameter — the best feasible solution found within the timeout is returned.

    Args:
        timeout_seconds: Maximum solver wall-clock time (default: 30 s).
        verbose: Print CBC solver output when True.
    """

    def __init__(self, timeout_seconds: int = 30, verbose: bool = False) -> None:
        self.timeout_seconds = timeout_seconds
        self.verbose = verbose

    # ── public API ────────────────────────────────────────────────────────────

    def schedule(
        self,
        activities: list[Activity],
        dag: ActivityDAG,
        pool: ResourcePool,
        deadline_weeks: int,
    ) -> ScheduleOutput:
        """Solve the RCPSP exactly and return the best schedule found.

        Raises:
            ImportError:  PuLP is not installed.
            ScheduleError: Problem is infeasible or solver hit timeout with
                           no incumbent solution.
        """
        if not _HAS_PULP:
            raise ImportError("PuLP is required for MILP scheduling. Install with: pip install pulp")

        act_map = {a.activity_id: a for a in activities}
        topo = dag.topological_order()
        horizon = deadline_weeks

        earliest = _compute_earliest_starts(topo, dag, act_map)
        latest = _compute_latest_starts(topo, dag, act_map, horizon)

        min_makespan = max(earliest[aid] + act_map[aid].duration_weeks for aid in topo)
        if min_makespan > deadline_weeks:
            raise ScheduleError(f"Infeasible: minimum makespan {min_makespan}w exceeds deadline {deadline_weeks}w")

        prob = pulp.LpProblem("RCPSP", pulp.LpMinimize)
        makespan_var = pulp.LpVariable("makespan", lowBound=min_makespan, cat="Integer")
        prob += makespan_var

        x = _build_decision_vars(topo, earliest, latest, act_map, horizon)
        _add_start_once_constraints(prob, topo, x, earliest, latest)
        _add_precedence_constraints(prob, dag, act_map, x)
        _add_resource_constraints(prob, topo, act_map, pool, x, horizon)
        _add_makespan_constraints(prob, topo, act_map, x, makespan_var)

        msg = 1 if self.verbose else 0
        solver = pulp.getSolver("PULP_CBC_CMD", timeLimit=self.timeout_seconds, msg=msg)
        prob.solve(solver)

        status = pulp.LpStatus[prob.status]
        if prob.status not in (
            pulp.LpStatusNotSolved,
            pulp.constants.LpSolutionOptimal,
            pulp.constants.LpSolutionIntegerFeasible,
        ):
            raise ScheduleError(f"MILP solver returned status '{status}' — no feasible solution")

        start_weeks = _extract_start_weeks(topo, x)
        makespan_val = int(math.ceil(pulp.value(makespan_var) or 0))

        scheduled = [
            ScheduledActivity(
                activity_id=aid,
                start_week=start_weeks[aid],
                end_week=start_weeks[aid] + act_map[aid].duration_weeks,
                duration_weeks=act_map[aid].duration_weeks,
                assigned_resources=dict(act_map[aid].required_resources),
            )
            for aid in topo
        ]
        metrics = _compute_metrics(scheduled, pool, makespan_val, deadline_weeks)
        return ScheduleOutput(
            scheduled_activities=scheduled,
            makespan=makespan_val,
            feasible=True,
            metrics=metrics,
            heuristic="MILP",
        )


# ── helpers ───────────────────────────────────────────────────────────────────


def _compute_earliest_starts(topo: list[str], dag: ActivityDAG, act_map: dict) -> dict[str, int]:
    earliest: dict[str, int] = {}
    for aid in topo:
        preds = dag.predecessors(aid)
        if preds:
            earliest[aid] = max(earliest[p] + act_map[p].duration_weeks for p in preds)
        else:
            earliest[aid] = 0
    return earliest


def _compute_latest_starts(topo: list[str], dag: ActivityDAG, act_map: dict, horizon: int) -> dict[str, int]:
    latest_finish: dict[str, int] = {aid: horizon for aid in topo}
    for aid in reversed(topo):
        succs = dag.successors(aid)
        if succs:
            latest_finish[aid] = min(latest_finish[s] - act_map[s].duration_weeks for s in succs)
    return {aid: latest_finish[aid] - act_map[aid].duration_weeks for aid in topo}


def _build_decision_vars(
    topo: list[str], earliest: dict, latest: dict, act_map: dict, horizon: int
) -> dict[str, dict[int, Any]]:
    x: dict[str, dict[int, Any]] = {}
    for aid in topo:
        lo = earliest[aid]
        hi = min(latest[aid], horizon - act_map[aid].duration_weeks)
        x[aid] = {t: pulp.LpVariable(f"x_{aid}_{t}", cat="Binary") for t in range(lo, hi + 1)}
    return x


def _add_start_once_constraints(prob: Any, topo: list[str], x: dict, earliest: dict, latest: dict) -> None:
    for aid in topo:
        if x[aid]:
            prob += pulp.lpSum(x[aid].values()) == 1, f"start_once_{aid}"
        else:
            raise ScheduleError(f"Activity '{aid}' has no valid start time within [{earliest[aid]}, {latest[aid]}]")


def _add_precedence_constraints(prob: Any, dag: ActivityDAG, act_map: dict, x: dict) -> None:
    for pred_id, succ_id in dag.precedence:
        dur_pred = act_map[pred_id].duration_weeks
        if x[pred_id] and x[succ_id]:
            pred_finish = pulp.lpSum((t + dur_pred) * v for t, v in x[pred_id].items())
            succ_start = pulp.lpSum(t * v for t, v in x[succ_id].items())
            prob += succ_start >= pred_finish, f"prec_{pred_id}_{succ_id}"


def _add_resource_constraints(
    prob: Any, topo: list[str], act_map: dict, pool: ResourcePool, x: dict, horizon: int
) -> None:
    resource_types = set(pool.resources.keys())
    for res in resource_types:
        cap = pool.resources.get(res, 0)
        for t in range(horizon):
            demand = pulp.lpSum(
                act_map[aid].required_resources.get(res, 0) * x[aid][ts]
                for aid in topo
                for ts in x[aid]
                if ts <= t < ts + act_map[aid].duration_weeks
            )
            prob += demand <= cap, f"cap_{res}_{t}"


def _add_makespan_constraints(prob: Any, topo: list[str], act_map: dict, x: dict, makespan_var: Any) -> None:
    for aid in topo:
        dur = act_map[aid].duration_weeks
        if x[aid]:
            prob += makespan_var >= pulp.lpSum((t + dur) * v for t, v in x[aid].items()), f"mksp_{aid}"


def _extract_start_weeks(topo: list[str], x: dict) -> dict[str, int]:
    start_weeks: dict[str, int] = {}
    for aid in topo:
        chosen = [t for t, v in x[aid].items() if pulp.value(v) and pulp.value(v) > 0.5]
        if not chosen:
            raise ScheduleError(f"MILP: no start week assigned to activity '{aid}'")
        start_weeks[aid] = chosen[0]
    return start_weeks


def _build_usage_by_week(scheduled: list, makespan: int) -> list:
    usage_by_week: list[dict[str, int]] = [{} for _ in range(makespan)]
    for act in scheduled:
        for w in range(act.start_week, act.end_week):
            if w < makespan:
                for res, qty in act.assigned_resources.items():
                    usage_by_week[w][res] = usage_by_week[w].get(res, 0) + qty
    return usage_by_week


def _compute_weekly_loads(usage_by_week: list, makespan: int) -> list:
    result = []
    for w in range(makespan):
        result.append(sum(usage_by_week[w].values()))
    return result


def _compute_variance(weekly_loads: list, mean_load: float, makespan: int) -> float:
    if not makespan:
        return 0.0
    total = 0.0
    for wl in weekly_loads:
        total += (wl - mean_load) ** 2
    return total / makespan


def _compute_metrics(
    scheduled: list[ScheduledActivity],
    pool: ResourcePool,
    makespan: int,
    deadline_weeks: int,
) -> ScheduleMetrics:
    """Compute ScheduleMetrics from a solved schedule."""
    if makespan <= 0:
        return ScheduleMetrics(
            makespan=makespan,
            resource_leveling_score=1.0,
            idle_time=0,
            activity_fragmentation=0,
            critical_path_slack_min=0.0,
            resource_utilization_avg=0.0,
        )

    usage_by_week = _build_usage_by_week(scheduled, makespan)
    total_cap = sum(pool.resources.values()) or 1
    weekly_loads = _compute_weekly_loads(usage_by_week, makespan)
    mean_load = sum(weekly_loads) / makespan
    variance = _compute_variance(weekly_loads, mean_load, makespan)
    std_dev = variance**0.5
    leveling_score = max(0.0, 1.0 - std_dev / total_cap)
    idle_time = 0
    for w in range(makespan):
        idle_time += max(0, total_cap - sum(usage_by_week[w].values()))
    utilization_avg = mean_load / total_cap if total_cap else 0.0
    return ScheduleMetrics(
        makespan=makespan,
        resource_leveling_score=leveling_score,
        idle_time=idle_time,
        activity_fragmentation=0,
        critical_path_slack_min=float(max(0, deadline_weeks - makespan)),
        resource_utilization_avg=min(1.0, utilization_avg),
    )
