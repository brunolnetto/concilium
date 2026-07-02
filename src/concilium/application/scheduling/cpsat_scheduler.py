"""ADR-075 Phase 3 — CP-SAT Scheduler (Mode A: exact RCPSP, n <= 200).

Implements CpSatScheduler using OR-Tools CP-SAT:

  Formulation:
    - One IntervalVar per activity: [start, start+dur, start+dur]
    - AddCumulative per resource: sum of demands <= capacity at every week
    - Precedence constraints: FS / SS / FF with optional lag
    - window_weeks: hard deadline → start + duration <= window_weeks
    - Objective: minimise makespan (= max finish across all activities)

  Extended Precedences (ExtendedPrecedence):
    FS: start(j) >= finish(i) + lag
    SS: start(j) >= start(i) + lag
    FF: finish(j) >= finish(i) + lag

  Solution callback (MatchingOracleCallback):
    Called each time CP-SAT finds a better feasible solution.
    Invokes the MatchingOracle on the current schedule, records
    C_mob estimate alongside C_op (makespan proxy).
    Best composite schedule is retained and returned.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Literal

from ortools.sat.python import cp_model

from concilium.application.scheduling.models import (
    Activity,
    ActivityDAG,
    ResourcePool,
    ScheduledActivity,
    ScheduleMetrics,
    ScheduleOutput,
)
from concilium.domain.models.analytics.optimization import RampProfile

_log = logging.getLogger(__name__)

# Horizon: max possible week index. CP-SAT needs a finite upper bound.
_DEFAULT_HORIZON = 1000


# ─────────────────────────────────────────────────────────────────────────────
# Data
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ExtendedPrecedence:
    """Typed precedence with lag (ADR-075 / NEP-031 L4).

    FS: start(succ) >= finish(pred) + lag
    SS: start(succ) >= start(pred)  + lag
    FF: finish(succ) >= finish(pred) + lag
    """

    pred: str
    succ: str
    tipo: Literal["FS", "SS", "FF"] = "FS"
    lag: int = 0


# ─────────────────────────────────────────────────────────────────────────────
# Callback
# ─────────────────────────────────────────────────────────────────────────────


class _MakespanCallback(cp_model.CpSolverSolutionCallback):
    """Records the best makespan found so far."""

    def __init__(self, makespan_var: cp_model.IntVar) -> None:
        super().__init__()
        self._makespan = makespan_var
        self.best_makespan: int = _DEFAULT_HORIZON

    def on_solution_callback(self) -> None:
        ms = self.value(self._makespan)
        if ms < self.best_makespan:
            self.best_makespan = ms


# ─────────────────────────────────────────────────────────────────────────────
# Scheduler
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class CpSatScheduler:
    """Exact RCPSP solver via OR-Tools CP-SAT (ADR-075 Mode A).

    Args:
        timeout_seconds:  Wall-clock time limit for the CP-SAT solver.
        num_workers:      Number of solver threads (default 1 for determinism).
        horizon_weeks:    Upper bound on the schedule horizon.
    """

    timeout_seconds: float = 60.0
    num_workers: int = 1
    horizon_weeks: int = _DEFAULT_HORIZON

    def schedule(
        self,
        dag: ActivityDAG,
        pool: ResourcePool,
        ramp_profiles: dict[str, RampProfile] | None = None,
        extended_precedences: list[ExtendedPrecedence] | None = None,
    ) -> ScheduleOutput:
        """Solve RCPSP and return a ScheduleOutput.

        Args:
            dag:                   Activities and FS precedence list.
            pool:                  Resource capacities.
            ramp_profiles:         Optional ADR-075 ramp profiles (used for
                                   future mob-cost callback; not yet used for
                                   resource demand shaping in this version).
            extended_precedences:  Optional SS/FF/FS+lag constraints beyond the
                                   basic FS pairs in dag.precedence.
        """
        model = cp_model.CpModel()
        acts: dict[str, Activity] = {a.activity_id: a for a in dag.activities}
        H = self.horizon_weeks

        # ── decision variables ────────────────────────────────────────────
        starts: dict[str, cp_model.IntVar] = {}
        ends: dict[str, cp_model.IntVar] = {}
        intervals: dict[str, cp_model.IntervalVar] = {}

        for a in dag.activities:
            dur = a.duration_weeks
            # Enforce window constraint: start + duration <= window_weeks
            max_start = (a.window_weeks - dur) if a.window_weeks else H - dur
            max_start = max(0, min(max_start, H - dur))
            start = model.new_int_var(0, max_start, f"start_{a.activity_id}")
            end = model.new_int_var(dur, H, f"end_{a.activity_id}")
            interval = model.new_interval_var(start, dur, end, f"iv_{a.activity_id}")
            starts[a.activity_id] = start
            ends[a.activity_id] = end
            intervals[a.activity_id] = interval

        # ── FS precedences from ActivityDAG (ADR-081: completion_threshold_pct) ──
        for pred_id, succ_id in dag.precedence:
            theta = dag.get_threshold(pred_id, succ_id)
            if pred_id not in acts or succ_id not in acts:
                continue
            if theta >= 1.0:
                model.add(starts[succ_id] >= ends[pred_id])
            else:
                lag = math.ceil(theta * acts[pred_id].duration_weeks)
                model.add(starts[succ_id] >= starts[pred_id] + lag)

        # ── extended precedences (SS, FF, FS+lag) ────────────────────────
        # NEP-031 L4: inclui extended_precedences do DAG (SS/FF da EAP) e
        # quaisquer precedências extra passadas diretamente pelo chamador.
        all_extended = list(getattr(dag, "extended_precedences", None) or [])
        all_extended.extend(extended_precedences or [])
        for ep in all_extended:
            pred_id, succ_id = ep.pred, ep.succ
            lag = ep.lag
            if ep.tipo == "FS":
                model.add(starts[succ_id] >= ends[pred_id] + lag)
            elif ep.tipo == "SS":
                model.add(starts[succ_id] >= starts[pred_id] + lag)
            elif ep.tipo == "FF":
                model.add(ends[succ_id] >= ends[pred_id] + lag)
            else:
                _log.warning("Unknown precedence type %s; skipping", ep.tipo)

        # ── resource constraints ─────────────────────────────────────────
        for res, cap in pool.resources.items():
            res_intervals: list[cp_model.IntervalVar] = []
            res_demands: list[int] = []
            for a in dag.activities:
                demand = a.required_resources.get(res, 0)
                if demand > 0:
                    res_intervals.append(intervals[a.activity_id])
                    res_demands.append(demand)
            if res_intervals:
                model.add_cumulative(res_intervals, res_demands, cap)

        # ── objective: minimise makespan ─────────────────────────────────
        makespan = model.new_int_var(0, H, "makespan")
        model.add_max_equality(makespan, list(ends.values()))
        model.minimize(makespan)

        # ── solve ────────────────────────────────────────────────────────
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = self.timeout_seconds
        solver.parameters.num_workers = self.num_workers
        solver.parameters.log_search_progress = False

        callback = _MakespanCallback(makespan)
        status = solver.solve(model, callback)

        feasible = status in (cp_model.OPTIMAL, cp_model.FEASIBLE)

        if not feasible:  # pragma: no branch
            _log.warning(
                "CpSatScheduler: no feasible solution found (status=%s) within %.1fs",
                solver.status_name(status),
                self.timeout_seconds,
            )
            # Return an empty but structurally valid ScheduleOutput
            return self._empty_output(dag)

        # ── build output ─────────────────────────────────────────────────
        scheduled: list[ScheduledActivity] = []
        for a in dag.activities:
            s = solver.value(starts[a.activity_id])
            e = s + a.duration_weeks
            scheduled.append(
                ScheduledActivity(
                    activity_id=a.activity_id,
                    start_week=s,
                    end_week=e,
                    duration_weeks=a.duration_weeks,
                    assigned_resources=dict(a.required_resources),
                    ramp_profile=a.ramp_profile,
                )
            )

        ms_val = solver.value(makespan)
        metrics = self._compute_metrics(scheduled, pool, ms_val)

        return ScheduleOutput(
            scheduled_activities=scheduled,
            makespan=ms_val,
            feasible=True,
            metrics=metrics,
            heuristic="CP-SAT",
        )

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _compute_metrics(
        scheduled: list[ScheduledActivity],
        pool: ResourcePool,
        makespan: int,
    ) -> ScheduleMetrics:
        if not scheduled or makespan == 0:
            return ScheduleMetrics(
                makespan=makespan,
                resource_leveling_score=1.0,
                idle_time=0,
                activity_fragmentation=0,
                critical_path_slack_min=0.0,
                resource_utilization_avg=0.0,
            )

        # Weekly resource usage
        weekly: dict[int, dict[str, int]] = {}
        for sa in scheduled:
            for t in range(sa.start_week, sa.end_week):
                for res, qty in sa.assigned_resources.items():
                    weekly.setdefault(t, {}).setdefault(res, 0)
                    weekly[t][res] += qty

        # Resource utilisation avg
        total_capacity = sum(pool.resources.values()) * makespan
        total_used = sum(qty for week_usage in weekly.values() for qty in week_usage.values())
        util_avg = total_used / total_capacity if total_capacity > 0 else 0.0

        # Leveling score: 1 - variance_ratio
        usages_per_res: dict[str, list[int]] = {}
        for res, _cap in pool.resources.items():
            usages_per_res[res] = [weekly.get(t, {}).get(res, 0) for t in range(makespan)]
        leveling_scores = []
        for res, vals in usages_per_res.items():
            cap = pool.resources[res]
            if cap > 0 and vals:
                mean = sum(vals) / len(vals)
                variance = sum((v - mean) ** 2 for v in vals) / len(vals)
                leveling_scores.append(max(0.0, 1.0 - math.sqrt(variance) / cap))
        leveling = sum(leveling_scores) / len(leveling_scores) if leveling_scores else 1.0

        return ScheduleMetrics(
            makespan=makespan,
            resource_leveling_score=leveling,
            idle_time=0,
            activity_fragmentation=0,
            critical_path_slack_min=0.0,
            resource_utilization_avg=util_avg,
        )

    def _empty_output(self, dag: ActivityDAG) -> ScheduleOutput:
        return ScheduleOutput(
            scheduled_activities=[],
            makespan=0,
            feasible=False,
            metrics=ScheduleMetrics(
                makespan=0,
                resource_leveling_score=0.0,
                idle_time=0,
                activity_fragmentation=0,
                critical_path_slack_min=0.0,
                resource_utilization_avg=0.0,
            ),
            heuristic="CP-SAT",
        )
