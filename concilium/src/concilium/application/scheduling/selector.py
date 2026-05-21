"""ADR-004: Algorithm selection and multi-heuristic exploration."""

from __future__ import annotations

from dataclasses import dataclass

from .models import (
    Activity,
    ActivityDAG,
    ResourcePool,
    ScheduleOutput,
    SchedulingStrategy,
)
from .scheduler import SerialScheduler


def select_scheduling_algorithm(
    num_activities: int,
    num_resource_types: int,
    contract_duration_weeks: int,
    deadline_margin_pct: float,
    criticality: str = "medium",
) -> SchedulingStrategy:
    """Select the best scheduling algorithm based on problem characteristics.

    Decision rules (ADR-004):
      - num_activities <= 50 AND criticality == "high" -> MILP (exact, 30s timeout)
      - 50 < num_activities <= 150                    -> SerialScheduler, multi-heuristic
      - num_activities > 150                          -> SerialScheduler + leveling pass
    """
    heuristics_all = ["MINSLK", "LPT", "MAXRES", "ES", "GR"]

    if num_activities <= 50 and criticality == "high":
        return SchedulingStrategy(
            algorithm="MILP",
            heuristics=["MINSLK"],
            timeout_seconds=30,
            leveling_pass=False,
            rationale=(
                f"Small problem ({num_activities} activities) with high criticality "
                "— exact MILP feasible within timeout."
            ),
        )

    if num_activities > 150:
        return SchedulingStrategy(
            algorithm="SerialScheduler+Leveling",
            heuristics=heuristics_all,
            timeout_seconds=120,
            leveling_pass=True,
            rationale=(f"Large problem ({num_activities} activities) — heuristic SGS with post-hoc resource leveling."),
        )

    # Default: medium-size
    return SchedulingStrategy(
        algorithm="SerialScheduler",
        heuristics=heuristics_all[:4],  # MINSLK, LPT, MAXRES, ES
        timeout_seconds=60,
        leveling_pass=False,
        rationale=(
            f"Medium problem ({num_activities} activities, {criticality} criticality) "
            "— multi-heuristic SGS exploration."
        ),
    )


@dataclass
class ExploreResult:
    """One ranked candidate from explore_schedules()."""

    heuristic: str
    schedule: ScheduleOutput
    quality_score: float


def explore_schedules(
    activities: list[Activity],
    dag: ActivityDAG,
    pool: ResourcePool,
    deadline_weeks: int,
    heuristics: list[str] | None = None,
    top_n: int = 3,
    deadline_for_score: int | None = None,
) -> list[ExploreResult]:
    """Run each heuristic, rank by quality score, return top-N results.

    Args:
        activities:         List of activities to schedule.
        dag:                Precedence DAG.
        pool:               Resource pool.
        deadline_weeks:     Hard deadline.
        heuristics:         List of heuristic names to try (default: all 5).
        top_n:              Maximum number of results to return.
        deadline_for_score: Deadline used for quality scoring (defaults to deadline_weeks).
    """
    if heuristics is None:
        heuristics = ["MINSLK", "LPT", "MAXRES", "ES", "GR"]

    score_deadline = deadline_for_score or deadline_weeks
    results: list[ExploreResult] = []

    for heuristic in heuristics:
        try:
            scheduler = SerialScheduler(priority_rule=heuristic)
            sched = scheduler.schedule(
                activities=activities,
                dag=dag,
                pool=pool,
                deadline_weeks=deadline_weeks,
            )
            score = sched.metrics.quality_score(deadline_weeks=score_deadline)
            results.append(
                ExploreResult(
                    heuristic=heuristic,
                    schedule=sched,
                    quality_score=score,
                )
            )
        except Exception:
            # Infeasible or error for this heuristic — skip
            pass

    # Sort by quality score descending (tie-break: lower makespan)
    results.sort(key=lambda r: (-r.quality_score, r.schedule.makespan))
    return results[:top_n]
