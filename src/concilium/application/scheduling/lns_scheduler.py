"""ADR-075 Phase 4 — LNS Scheduler (Mode B: heuristic, n > 200).

Implements Lagrangian-relaxation over perpetuation concurrency penalties
using the SSGS (SerialScheduler) inner solver.

Algorithm:
  for k in range(k_max):
    1. Schedule W^k via SSGS with λ-weighted priority
    2. Solve perpetuation matching via MatchingOracle → sol^k, C_mob^k
    3. C_op^k  = makespan as proxy for operational cost
       C_total^k = C_op^k + C_mob^k
    4. Update λ via subgradient:
         λ_{ij,r}^{k+1} = max(0, λ_{ij,r}^k + step_k * conc_{ij,r}^k)
         where step_k = step_0 * decay^k
    5. Cycle detection: hash(schedule) in seen_states → early exit
    6. Convergence: |ΔC_total|/C_total_0 < tol → early exit

  Return: ScheduleOutput with best composite C_total found.

Note: SSGS is called with a Lagrangian-adjusted topological priority.
      Activities penalised by high λ_{ij,r} (concurrent with high-value pairs)
      are pushed back in the priority queue, encouraging serialisation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from concilium.application.scheduling.models import (
    Activity,
    ActivityDAG,
    ResourcePool,
    ScheduledActivity,
    ScheduleError,
    ScheduleMetrics,
    ScheduleOutput,
)
from concilium.domain.models.analytics.optimization import ActivityPlan, RampProfile
from concilium.domain.services.planning.matching_oracle import MatchingOracle

_log = logging.getLogger(__name__)

# Horizon for schedule bound: 10 × sum of durations (generous)
_HORIZON_MULTIPLIER = 10


# ─────────────────────────────────────────────────────────────────────────────
# LNS Scheduler
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class LnsScheduler:
    """Lagrangian + SSGS scheduler for large instances (ADR-075 Mode B).

    Args:
        oracle:           MatchingOracle for perpetuation cost evaluation.
        k_max:            Maximum LNS iterations (default 10 per ADR-075).
        step_0:           Initial subgradient step size.
        step_decay:       Step decay factor per iteration.
        convergence_tol:  |ΔC_total|/C_total_0 threshold for early exit.
        deadline_multiplier: Multiplier on critical-path length for deadline.
    """

    oracle: MatchingOracle
    k_max: int = 10
    step_0: float = 0.5
    step_decay: float = 0.85
    convergence_tol: float = 0.005
    deadline_multiplier: float = 3.0
    # ADR-079: λ₀ pre-warming from RelatorioOportunidades (ADR-078).
    # Keys: (atividade_i, atividade_j, tipo_id) — same as concurrency penalty keys.
    initial_lambdas: dict[tuple[str, str, str], float] | None = None

    # ── state after the last solve() call ─────────────────────────────────────
    iteration_log: list[dict[str, Any]] = field(default_factory=list, init=False, repr=False)
    best_mob_cost: float = field(default=0.0, init=False, repr=False)

    # ── public API ────────────────────────────────────────────────────────────

    def schedule(
        self,
        dag: ActivityDAG,
        pool: ResourcePool,
        ramp_profiles: dict[str, RampProfile] | None = None,
    ) -> ScheduleOutput:
        """Run Lagrangian-LNS and return the best schedule found.

        Args:
            dag:           Activities and FS precedences.
            pool:          Resource capacities.
            ramp_profiles: ADR-075 ramp profiles for mob cost evaluation.
        """
        self.iteration_log = []
        self.best_mob_cost = 0.0

        acts = dag.activities
        if not acts:
            return self._empty_output()

        topo = dag.topological_order()
        act_map: dict[str, Activity] = {a.activity_id: a for a in acts}
        profiles = ramp_profiles or {}

        # Deadline: generous upper bound
        sum_dur = sum(a.duration_weeks for a in acts)
        deadline = int(self.deadline_multiplier * sum_dur) + 1

        # λ_{ij,r}: penalty for concurrent pair (i, j, r).
        # ADR-079: pre-warm from initial_lambdas (RelatorioOportunidades) when available.
        lambdas: dict[tuple[str, str, str], float] = dict(self.initial_lambdas) if self.initial_lambdas else {}

        seen_hashes: set[int] = set()
        state: dict[str, Any] = {"best_output": None, "best_C_total": float("inf"), "C_total_0": None}

        for k in range(self.k_max):
            step_k = self.step_0 * (self.step_decay**k)
            should_stop = self._lns_iteration(
                k, step_k, act_map, topo, dag, pool, deadline, lambdas, profiles, seen_hashes, state
            )
            if should_stop:
                break

        best_output = state["best_output"]
        if best_output is None:
            return self._empty_output()

        return best_output

    def _lns_iteration(
        self,
        k: int,
        step_k: float,
        act_map: dict[str, Activity],
        topo: list[str],
        dag: ActivityDAG,
        pool: ResourcePool,
        deadline: int,
        lambdas: dict[tuple[str, str, str], float],
        profiles: dict[str, RampProfile],
        seen_hashes: set[int],
        state: dict[str, Any],
    ) -> bool:
        """Run one LNS iteration, mutating `lambdas`/`seen_hashes`/`state` in place.

        Returns True if the outer loop should stop (SSGS failure, cycle, or convergence).
        """
        # ── 1. Schedule with λ-weighted priority ─────────────────────
        sorted_topo = self._lns_sorted_topo(lambdas, topo)
        output = self._lns_try_ssgs(act_map, sorted_topo, dag, pool, deadline, k)
        if output is None:
            return True

        # Cycle detection
        sched_hash = _schedule_hash(output.scheduled_activities)
        if sched_hash in seen_hashes:
            _log.debug("LnsScheduler: cycle detected at k=%d, exiting", k)
            return True
        seen_hashes.add(sched_hash)

        # ── 2. Oracle: perpetuation matching ────────────────────────
        sol, C_mob, C_op, C_total = self._lns_evaluate(output, profiles)

        # Track initial cost for convergence
        if state["C_total_0"] is None:
            state["C_total_0"] = C_total if C_total > 0 else 1.0

        n_concurrent = len(sol.concurrent_pairs_lost)
        self._lns_log_iteration(k, C_total, C_mob, C_op, n_concurrent)

        # Track best
        if C_total < state["best_C_total"]:
            state["best_C_total"] = C_total
            state["best_output"] = output
            self.best_mob_cost = C_mob

        # ── 3. Convergence check ─────────────────────────────────────
        if self._lns_converged(k, C_total, state["C_total_0"]):
            return True

        # ── 4. Subgradient λ update ───────────────────────────────────
        self._lns_update_lambdas(lambdas, sol, step_k)
        return False

    def _lns_sorted_topo(
        self,
        lambdas: dict[tuple[str, str, str], float],
        topo: list[str],
    ) -> list[str]:
        priority_penalty = self._compute_priority_penalties(lambdas, topo)
        return sorted(topo, key=lambda aid: priority_penalty.get(aid, 0.0))

    def _lns_try_ssgs(
        self,
        act_map: dict[str, Activity],
        sorted_topo: list[str],
        dag: ActivityDAG,
        pool: ResourcePool,
        deadline: int,
        k: int,
    ) -> ScheduleOutput | None:
        try:
            return self._ssgs(act_map, sorted_topo, dag, pool, deadline)
        except ScheduleError as exc:
            _log.warning("LnsScheduler k=%d: SSGS failed: %s", k, exc)
            return None

    def _lns_evaluate(
        self,
        output: ScheduleOutput,
        profiles: dict[str, RampProfile],
    ) -> tuple[Any, float, float, float]:
        plans = _to_activity_plans(output.scheduled_activities)
        sol = self.oracle.solve(plans, profiles)
        C_mob = sol.mob_cost_actual
        C_op = float(output.makespan)
        C_total = C_op + C_mob
        return sol, C_mob, C_op, C_total

    def _lns_log_iteration(self, k: int, c_total: float, c_mob: float, c_op: float, n_concurrent: int) -> None:
        self.iteration_log.append(
            {
                "k": k,
                "C_total": c_total,
                "C_mob": c_mob,
                "C_op": c_op,
                "n_concurrent": n_concurrent,
            }
        )
        _log.debug(
            "LnsScheduler k=%d: C_total=%.1f, C_mob=%.1f, C_op=%.1f, n_conc=%d",
            k,
            c_total,
            c_mob,
            c_op,
            n_concurrent,
        )

    def _lns_converged(self, k: int, c_total: float, c_total_0: float) -> bool:
        if k > 0 and c_total_0 > 0:  # pragma: no branch
            prev = self.iteration_log[-2]["C_total"]
            delta_ratio = abs(prev - c_total) / c_total_0
            if delta_ratio < self.convergence_tol:  # pragma: no branch
                _log.debug("LnsScheduler: converged at k=%d (Δ=%.5f)", k, delta_ratio)
                return True
        return False

    @staticmethod
    def _lns_update_lambdas(
        lambdas: dict[tuple[str, str, str], float],
        sol: Any,
        step_k: float,
    ) -> None:
        for aid_i, aid_j, res in sol.concurrent_pairs_lost:
            key = (aid_i, aid_j, res)
            lambdas[key] = max(0.0, lambdas.get(key, 0.0) + step_k)

    # ── inner SSGS ────────────────────────────────────────────────────────────

    def _ssgs(
        self,
        act_map: dict[str, Activity],
        sorted_order: list[str],
        dag: ActivityDAG,
        pool: ResourcePool,
        deadline: int,
    ) -> ScheduleOutput:
        """Lightweight Serial Schedule Generation Scheme.

        Schedules activities in `sorted_order` (already λ-adjusted priority).
        Respects FS precedences and resource capacities.
        Raises ScheduleError if deadline is exceeded.
        """
        resource_usage: dict[int, dict[str, int]] = {}
        scheduled: dict[str, ScheduledActivity] = {}
        earliest_start = _compute_earliest_starts(act_map, dag, dag.topological_order())

        import math as _math_lns

        for aid in sorted_order:
            a = act_map[aid]
            preds = dag.predecessors(aid)
            # ADR-081: threshold-based release
            pred_finish = max(
                (
                    scheduled[p].start_week + _math_lns.ceil(dag.get_threshold(p, aid) * act_map[p].duration_weeks)
                    for p in preds
                    if p in scheduled
                ),
                default=0,
            )
            t = max(earliest_start.get(aid, 0), pred_finish)
            t = self._find_start(a, t, resource_usage, pool, deadline)
            end = t + a.duration_weeks
            scheduled[aid] = ScheduledActivity(
                activity_id=aid,
                start_week=t,
                end_week=end,
                duration_weeks=a.duration_weeks,
                assigned_resources=dict(a.required_resources),
            )
            _book_resources(a, t, end, resource_usage)

        result_acts = list(scheduled.values())
        makespan_val = max(s.end_week for s in result_acts) if result_acts else 0
        metrics = _compute_lns_metrics(resource_usage, pool, makespan_val, deadline)
        return ScheduleOutput(
            scheduled_activities=result_acts,
            makespan=makespan_val,
            feasible=True,
            metrics=metrics,
            heuristic="LNS",
        )

    def _find_start(
        self,
        a: Activity,
        earliest: int,
        resource_usage: dict[int, dict[str, int]],
        pool: ResourcePool,
        deadline: int,
    ) -> int:
        t = earliest
        while t + a.duration_weeks <= deadline:
            if all(
                resource_usage.get(t + offset, {}).get(res, 0) + _lns_demand_at_offset(a, offset, res, qty)
                <= pool.resources.get(res, 0)
                for res, qty in a.required_resources.items()
                for offset in range(a.duration_weeks)
            ):
                return t
            t += 1
        raise ScheduleError(f"Activity '{a.activity_id}' cannot be scheduled within deadline {deadline}")

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _compute_priority_penalties(
        lambdas: dict[tuple[str, str, str], float],
        topo: list[str],
    ) -> dict[str, float]:
        """Sum λ penalties per activity (activity j as follower in concurrent pair)."""
        penalties: dict[str, float] = {aid: 0.0 for aid in topo}
        for (_aid_i, aid_j, _res), lam in lambdas.items():
            penalties[aid_j] = penalties.get(aid_j, 0.0) + lam
        return penalties

    def _empty_output(self) -> ScheduleOutput:
        return ScheduleOutput(
            scheduled_activities=[],
            makespan=0,
            feasible=False,
            metrics=_compute_lns_metrics({}, ResourcePool(), 0, 0),
            heuristic="LNS",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Module-level helpers
# ─────────────────────────────────────────────────────────────────────────────


def _compute_earliest_starts(
    act_map: dict[str, Activity],
    dag: ActivityDAG,
    topo: list[str],
) -> dict[str, int]:
    """ADR-081: forward pass usando completion_threshold_pct por aresta."""
    import math as _math

    es: dict[str, int] = {}
    for aid in topo:
        preds = dag.predecessors(aid)
        if preds:
            es[aid] = max(
                es.get(p, 0) + _math.ceil(dag.get_threshold(p, aid) * act_map[p].duration_weeks) for p in preds
            )
        else:
            es[aid] = 0
    return es


def _lns_demand_at_offset(a: Activity, offset: int, res: str, qty: int) -> int:
    """Ramp-aware demand for resource *res* at *offset* weeks into activity *a*.

    Mirrors scheduler._demand_at_offset() — NEP-047.
    When ramp_profile is absent, returns *qty* (flat demand).
    """
    if a.ramp_profile is None or offset >= len(a.ramp_profile):
        return qty
    return max(0, round(qty * a.ramp_profile[offset]))


def _book_resources(
    a: Activity,
    t_start: int,
    t_end: int,
    usage: dict[int, dict[str, int]],
) -> None:
    for offset, t in enumerate(range(t_start, t_end)):
        week = usage.setdefault(t, {})
        for res, qty in a.required_resources.items():
            demand = _lns_demand_at_offset(a, offset, res, qty)
            week[res] = week.get(res, 0) + demand


def _schedule_hash(scheduled: list[ScheduledActivity]) -> int:
    return hash(frozenset((sa.activity_id, sa.start_week) for sa in scheduled))


def _to_activity_plans(scheduled: list[ScheduledActivity]) -> list[ActivityPlan]:
    return [
        ActivityPlan(
            activity_id=sa.activity_id,
            window=(sa.start_week, sa.end_week),
            n_i=sa.duration_weeks,
        )
        for sa in scheduled
    ]


def _compute_lns_metrics(
    resource_usage: dict[int, dict[str, int]],
    pool: ResourcePool,
    makespan: int,
    deadline: int,
) -> ScheduleMetrics:
    """Compute real schedule metrics from resource_usage built during _ssgs().

    Mirrors SerialScheduler._compute_metrics() — leveling via CV, idle time,
    utilization average (NEP-046).
    """
    if not resource_usage or makespan == 0:
        return ScheduleMetrics(
            makespan=makespan,
            resource_leveling_score=1.0,
            idle_time=0,
            activity_fragmentation=0,
            critical_path_slack_min=float(max(0, deadline - makespan)),
            resource_utilization_avg=0.0,
        )

    total_capacity = sum(pool.resources.values()) or 1
    weekly_loads: list[float] = []
    for w in range(makespan):
        week_load = sum(resource_usage.get(w, {}).values())
        weekly_loads.append(week_load / total_capacity)

    avg = sum(weekly_loads) / len(weekly_loads)
    variance = sum((x - avg) ** 2 for x in weekly_loads) / len(weekly_loads)
    cv = variance**0.5 / max(avg, 1e-9)
    leveling_score = max(0.0, 1.0 - cv)
    idle_time = sum(1 for w in range(makespan) if not resource_usage.get(w))

    return ScheduleMetrics(
        makespan=makespan,
        resource_leveling_score=round(leveling_score, 4),
        idle_time=idle_time,
        activity_fragmentation=0,
        critical_path_slack_min=float(max(0, deadline - makespan)),
        resource_utilization_avg=round(avg, 4),
    )
