"""ADR-004: Serial Schedule Generation Resource (SGS) scheduler.

Implements a Serial Schedule Generation Scheme with pluggable priority rules:
  - MINSLK: Minimum Total Slack (critical-path aware)
  - LPT:    Longest Processing Time first
  - MAXRES: Maximum Resource Demand first
  - ES:     Earliest Start (precedence-driven)
  - GR:     Greedy — earliest feasible slot
"""

from __future__ import annotations

import math

from .models import (
    Activity,
    ActivityDAG,
    ResourcePool,
    ScheduledActivity,
    ScheduleError,
    ScheduleMetrics,
    ScheduleOutput,
)

_SUPPORTED_RULES = {"MINSLK", "LPT", "MAXRES", "ES", "GR"}


def _pred_release(pred_id: str, succ_id: str, pred_start: int, dag: ActivityDAG, act_map: dict) -> int:
    """Semana em que o predecessor `pred_id` libera o sucessor `succ_id`.

    ADR-081: start_j ≥ start_i + ceil(θ × duration_i)
    θ=1.0 (default) → comportamento clássico FS (start + duration = end).
    θ=0.0 → sucessor pode iniciar quando predecessor inicia (SS-like).
    """
    θ = dag.get_threshold(pred_id, succ_id)
    duration = act_map[pred_id].duration_weeks
    return pred_start + math.ceil(θ * duration)


def _compute_earliest_starts(act_map: dict, dag: ActivityDAG, topo_order: list) -> dict:
    """ADR-081: usa completion_threshold_pct por aresta para calcular earliest start.

    ADR-181 F1: `readiness_weeks` (aquisição + mobilização) é um floor absoluto a
    partir de t=0 — combinado via max() com o earliest_start de precedência, nunca
    somado. Procurement pode ocorrer em paralelo com atividades anteriores do
    projeto; só passa a ser a restrição ativa quando a precedência sozinha
    permitiria um início mais cedo do que os recursos estarão prontos.
    """
    earliest_start: dict[str, int] = {}
    for aid in topo_order:
        preds = dag.predecessors(aid)
        if preds:
            precedence_earliest = max(
                _pred_release(p, aid, earliest_start.get(p, 0), dag, act_map) for p in preds
            )
        else:
            precedence_earliest = 0
        earliest_start[aid] = max(precedence_earliest, act_map[aid].readiness_weeks)
    return earliest_start


def _compute_total_float(
    act_map: dict, topo_order: list, earliest_start: dict, latest_finish: dict, deadline_weeks: int
) -> dict:
    total_float: dict[str, float] = {}
    for aid in topo_order:
        a = act_map[aid]
        ef = earliest_start[aid] + a.duration_weeks
        lf = latest_finish.get(aid, deadline_weeks)
        total_float[aid] = lf - ef
    return total_float


def _check_feasibility(act_map: dict, topo_order: list, earliest_start: dict, deadline_weeks: int) -> None:
    min_duration = max(earliest_start[aid] + act_map[aid].duration_weeks for aid in topo_order)
    if min_duration > deadline_weeks:
        raise ScheduleError(f"Infeasible: minimum project duration {min_duration}w exceeds deadline {deadline_weeks}w")


def _demand_at_offset(activity, offset: int, res: str, qty: int) -> int:
    """Return actual demand for resource `res` at week `offset` within the activity.

    ADR-074: When ``activity.ramp_profile`` is set, the demand is scaled by the
    fractional profile value (float in [0, 1]) relative to the peak ``qty``.
    Rounds to nearest integer; minimum is 0.
    """
    if activity.ramp_profile is None or offset >= len(activity.ramp_profile):
        return qty
    return max(0, round(qty * activity.ramp_profile[offset]))


def _book_resources(activity, t: int, end: int, resource_usage: dict) -> None:
    for offset, w in enumerate(range(t, end)):
        if w not in resource_usage:
            resource_usage[w] = {}
        for res, qty in activity.required_resources.items():
            demand = _demand_at_offset(activity, offset, res, qty)
            resource_usage[w][res] = resource_usage[w].get(res, 0) + demand


class SerialScheduler:
    """Serial Schedule Generation Scheme (SSGS) with pluggable priority rule."""

    def __init__(self, priority_rule: str = "MINSLK") -> None:
        if priority_rule not in _SUPPORTED_RULES:
            raise ValueError(f"Unknown priority_rule '{priority_rule}'. Supported: {sorted(_SUPPORTED_RULES)}")
        self.priority_rule = priority_rule

    # ── public API ────────────────────────────────────────────────────────────

    def schedule(
        self,
        activities: list[Activity],
        dag: ActivityDAG,
        pool: ResourcePool,
        deadline_weeks: int,
    ) -> ScheduleOutput:
        """Produce a feasible schedule via SSGS.

        Raises ScheduleError if no feasible schedule can be found within
        `deadline_weeks`.
        """
        act_map = {a.activity_id: a for a in activities}
        topo_order = dag.topological_order()
        earliest_start = _compute_earliest_starts(act_map, dag, topo_order)
        latest_finish = self._compute_latest_finish(act_map, dag, topo_order, deadline_weeks)
        total_float = _compute_total_float(act_map, topo_order, earliest_start, latest_finish, deadline_weeks)
        _check_feasibility(act_map, topo_order, earliest_start, deadline_weeks)
        resource_usage: dict[int, dict[str, int]] = {}
        scheduled: dict[str, ScheduledActivity] = {}
        in_degree, ready = self._ssgs_init_ready_list(dag, topo_order)

        while ready:
            # Ordena a ready list pela regra de prioridade (float, earliest, etc.)
            ready = self._sort_by_priority(ready, act_map, total_float, earliest_start)
            aid = ready.pop(0)
            self._ssgs_schedule_activity(
                aid, act_map, dag, scheduled, resource_usage, earliest_start, pool, deadline_weeks
            )
            self._ssgs_release_ready_successors(aid, dag, in_degree, ready)
        result_acts = list(scheduled.values())
        makespan_0 = max(s.end_week - 1 for s in result_acts) if result_acts else 0
        metrics = self._compute_metrics(result_acts, resource_usage, pool, makespan_0, deadline_weeks)
        return ScheduleOutput(
            scheduled_activities=result_acts,
            makespan=makespan_0,
            feasible=True,
            metrics=metrics,
            heuristic=self.priority_rule,
        )

    def _ssgs_init_ready_list(self, dag: ActivityDAG, topo_order: list[str]) -> tuple[dict[str, int], list[str]]:
        """ADR-081: inicializa in_degree e a ready list do SSGS — atividade só entra
        na fila quando todos os predecessores já foram agendados. Isso garante que o
        sort por priority nunca viola a ordem topológica, mesmo com thresholds θ < 1.0."""
        from collections import defaultdict as _ddict

        in_degree: dict[str, int] = _ddict(int)
        for _p, s in dag.precedence:
            in_degree[s] += 1
        ready = [aid for aid in topo_order if in_degree[aid] == 0]
        return in_degree, ready

    def _ssgs_schedule_activity(
        self,
        aid: str,
        act_map: dict[str, Activity],
        dag: ActivityDAG,
        scheduled: dict[str, ScheduledActivity],
        resource_usage: dict[int, dict[str, int]],
        earliest_start: dict[str, int],
        pool: ResourcePool,
        deadline_weeks: int,
    ) -> None:
        """Resolve o start/end da atividade `aid` e registra em `scheduled` + `resource_usage`."""
        a = act_map[aid]
        preds = dag.predecessors(aid)
        # Todos os predecessores estão em scheduled (invariante da ready list)
        pred_finish = max(
            (_pred_release(p, aid, scheduled[p].start_week - 1, dag, act_map) for p in preds),
            default=0,
        )
        t = max(earliest_start[aid], pred_finish)
        t = self._find_start(a, t, resource_usage, pool, deadline_weeks)
        end = t + a.duration_weeks
        scheduled[aid] = ScheduledActivity(
            activity_id=aid,
            start_week=t + 1,
            end_week=end + 1,
            duration_weeks=a.duration_weeks,
            assigned_resources=dict(a.required_resources),
            ramp_profile=a.ramp_profile,  # ADR-074: propagate for cost computation
        )
        _book_resources(a, t, end, resource_usage)

    def _ssgs_release_ready_successors(
        self, aid: str, dag: ActivityDAG, in_degree: dict[str, int], ready: list[str]
    ) -> None:
        """Adiciona sucessores de `aid` à ready list quando todos os seus predecessores
        já estiverem agendados."""
        for succ in dag.successors(aid):
            in_degree[succ] -= 1
            if in_degree[succ] == 0:
                ready.append(succ)

    # ── internals ─────────────────────────────────────────────────────────────

    def _compute_latest_finish(
        self,
        act_map: dict[str, Activity],
        dag: ActivityDAG,
        topo_order: list[str],
        deadline_weeks: int,
    ) -> dict[str, int]:
        """ADR-081: Backward pass para Latest Finish com threshold-aware.

        Fórmula correta (para FS com θ):
            LF[i] = min_j( LS[j] - ceil(θ_ij × d_i) + d_i )
                  = min_j( LF[j] - d_j - ceil(θ_ij × d_i) + d_i )

        Para θ=1.0 (FS clássico):
            LF[i] = min_j( LS[j] ) = min_j( LF[j] - d_j )
            (equivalente à fórmula clássica sem o `+ d_i` errado)
        """
        lf: dict[str, int] = {}
        for aid in reversed(topo_order):
            succs = dag.successors(aid)
            if succs:
                d_i = act_map[aid].duration_weeks
                lf[aid] = min(
                    lf.get(s, deadline_weeks)
                    - act_map[s].duration_weeks  # LS[s]
                    - math.ceil(dag.get_threshold(aid, s) * d_i)  # - ceil(θ × d_i)
                    + d_i  # + d_i → LF[i]
                    for s in succs
                )
                lf[aid] = max(lf[aid], act_map[aid].duration_weeks)  # LF ≥ d_i
            else:
                lf[aid] = deadline_weeks
        return lf

    def _sort_by_priority(
        self,
        topo_order: list[str],
        act_map: dict[str, Activity],
        total_float: dict[str, float],
        earliest_start: dict[str, int],
    ) -> list[str]:
        """Return activity IDs sorted by the chosen priority rule."""
        if self.priority_rule == "MINSLK":
            return sorted(topo_order, key=lambda a: (total_float[a], earliest_start[a]))
        if self.priority_rule == "LPT":
            return sorted(topo_order, key=lambda a: -act_map[a].duration_weeks)
        if self.priority_rule == "MAXRES":
            return sorted(topo_order, key=lambda a: -sum(act_map[a].required_resources.values()))
        if self.priority_rule == "ES":
            return sorted(topo_order, key=lambda a: earliest_start[a])
        # GR — greedy, preserve topological order
        return list(topo_order)

    def _find_start(
        self,
        activity: Activity,
        earliest: int,
        resource_usage: dict[int, dict[str, int]],
        pool: ResourcePool,
        deadline_weeks: int,
    ) -> int:
        """Find the earliest week >= earliest where resources are free for `duration_weeks`.

        ADR-072: When ``activity.window_weeks`` is set the activity must
        finish by ``window_weeks`` (relative to t=0), so the latest allowed
        start is ``window_weeks - duration_weeks``.
        """
        t = earliest
        # ADR-072: enforce per-activity corridor window constraint
        if activity.window_weeks is not None:
            max_start = min(deadline_weeks, activity.window_weeks) - activity.duration_weeks
        else:
            max_start = deadline_weeks - activity.duration_weeks
        while t <= max_start:
            if self._can_schedule(activity, t, resource_usage, pool):
                return t
            t += 1
        raise ScheduleError(f"Cannot schedule activity '{activity.activity_id}' within deadline {deadline_weeks}w")

    def _can_schedule(
        self,
        activity: Activity,
        start: int,
        resource_usage: dict[int, dict[str, int]],
        pool: ResourcePool,
    ) -> bool:
        """Check if resources are available for all weeks [start, start+duration).

        ADR-074: Uses ``ramp_profile`` to compute per-week demand when available,
        so weeks at the start/end of an activity (ramp-up/down phases) need fewer
        resources than the peak and may fit in windows that the flat model rejects.
        """
        for offset, w in enumerate(range(start, start + activity.duration_weeks)):
            week_usage = resource_usage.get(w, {})
            for res, qty in activity.required_resources.items():
                demand = _demand_at_offset(activity, offset, res, qty)
                available = pool.resources.get(res, 0)
                used = week_usage.get(res, 0)
                if used + demand > available:
                    return False
        return True

    def _compute_metrics(
        self,
        acts: list[ScheduledActivity],
        resource_usage: dict[int, dict[str, int]],
        pool: ResourcePool,
        makespan: int,
        deadline_weeks: int,
    ) -> ScheduleMetrics:
        """Compute schedule quality metrics."""
        if not acts:
            return ScheduleMetrics(
                makespan=0,
                resource_leveling_score=1.0,
                idle_time=0,
                activity_fragmentation=0,
                critical_path_slack_min=0.0,
                resource_utilization_avg=0.0,
            )

        # Resource leveling: coefficient of variation (lower = better = higher score)
        total_capacity = sum(pool.resources.values())
        weekly_loads: list[float] = []
        for w in range(makespan):
            week_load = sum(resource_usage.get(w, {}).values())
            weekly_loads.append(week_load / max(total_capacity, 1))

        if weekly_loads:
            avg = sum(weekly_loads) / len(weekly_loads)
            variance = sum((x - avg) ** 2 for x in weekly_loads) / len(weekly_loads)
            std = variance**0.5
            cv = std / max(avg, 1e-9)
            leveling_score = max(0.0, 1.0 - cv)
            utilization_avg = avg
        else:
            leveling_score = 1.0
            utilization_avg = 0.0

        # Idle time: weeks within makespan with no resource usage
        idle_time = sum(1 for w in range(makespan) if not resource_usage.get(w))

        # Slack = deadline - makespan
        slack = max(0.0, float(deadline_weeks - makespan))

        return ScheduleMetrics(
            makespan=makespan,
            resource_leveling_score=round(leveling_score, 4),
            idle_time=idle_time,
            activity_fragmentation=0,  # serial SGS never fragments
            critical_path_slack_min=slack,
            resource_utilization_avg=round(utilization_avg, 4),
        )
