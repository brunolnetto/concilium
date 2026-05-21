"""ADR-004: Serial Schedule Generation Resource (SGS) scheduler.

Implements a Serial Schedule Generation Scheme with pluggable priority rules:
  - MINSLK: Minimum Total Slack (critical-path aware)
  - LPT:    Longest Processing Time first
  - MAXRES: Maximum Resource Demand first
  - ES:     Earliest Start (precedence-driven)
  - GR:     Greedy — earliest feasible slot
"""

from __future__ import annotations

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

        # Earliest finish of each predecessor — determines earliest start
        earliest_start: dict[str, int] = {}
        for aid in topo_order:
            preds = dag.predecessors(aid)
            if preds:
                earliest_start[aid] = max(earliest_start.get(p, 0) + act_map[p].duration_weeks for p in preds)
            else:
                earliest_start[aid] = 0

        # Compute latest finish (LF) for slack calculation
        latest_finish = self._compute_latest_finish(act_map, dag, topo_order, deadline_weeks)

        # Total float (slack) per activity
        total_float: dict[str, float] = {}
        for aid in topo_order:
            a = act_map[aid]
            ef = earliest_start[aid] + a.duration_weeks
            lf = latest_finish.get(aid, deadline_weeks)
            total_float[aid] = lf - ef

        # Check feasibility: minimum project duration
        min_duration = max(earliest_start[aid] + act_map[aid].duration_weeks for aid in topo_order)
        if min_duration > deadline_weeks:
            raise ScheduleError(
                f"Infeasible: minimum project duration {min_duration}w exceeds deadline {deadline_weeks}w"
            )

        # SSGS main loop
        resource_usage: dict[int, dict[str, int]] = {}  # week -> {res: used}
        scheduled: dict[str, ScheduledActivity] = {}
        set(topo_order)

        # Sort activities by priority rule (stable sort, respect topo)
        ordered = self._sort_by_priority(topo_order, act_map, total_float, earliest_start)

        for aid in ordered:
            a = act_map[aid]
            preds = dag.predecessors(aid)

            # Earliest start from predecessor finish
            pred_finish = max(
                (scheduled[p].end_week for p in preds if p in scheduled),
                default=0,
            )
            t = max(earliest_start[aid], pred_finish)

            # Find first slot where resources are available for `duration_weeks`
            t = self._find_start(a, t, resource_usage, pool, deadline_weeks)
            end = t + a.duration_weeks

            scheduled[aid] = ScheduledActivity(
                activity_id=aid,
                start_week=t + 1,  # 1-based weeks
                end_week=end + 1,  # exclusive (end_week is first week NOT in use)
                duration_weeks=a.duration_weeks,
                assigned_resources=dict(a.required_resources),
            )

            # Book resources
            for w in range(t, end):
                if w not in resource_usage:
                    resource_usage[w] = {}
                for res, qty in a.required_resources.items():
                    resource_usage[w][res] = resource_usage[w].get(res, 0) + qty

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

    # ── internals ─────────────────────────────────────────────────────────────

    def _compute_latest_finish(
        self,
        act_map: dict[str, Activity],
        dag: ActivityDAG,
        topo_order: list[str],
        deadline_weeks: int,
    ) -> dict[str, int]:
        """Backward pass to compute Latest Finish times."""
        lf: dict[str, int] = {}
        for aid in reversed(topo_order):
            succs = dag.successors(aid)
            if succs:
                lf[aid] = (
                    min(lf.get(s, deadline_weeks) - act_map[s].duration_weeks for s in succs)
                    + act_map[aid].duration_weeks
                )
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
        """Find the earliest week >= earliest where resources are free for `duration_weeks`."""
        t = earliest
        while t + activity.duration_weeks <= deadline_weeks:
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
        """Check if resources are available for all weeks [start, start+duration)."""
        for w in range(start, start + activity.duration_weeks):
            week_usage = resource_usage.get(w, {})
            for res, qty in activity.required_resources.items():
                available = pool.resources.get(res, 0)
                used = week_usage.get(res, 0)
                if used + qty > available:
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
