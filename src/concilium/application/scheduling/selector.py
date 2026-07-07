"""ADR-004 / ADR-075: Algorithm selection and multi-heuristic exploration.

ADR-075 updates the dispatch thresholds:
  - n ≤ 200  → CP-SAT exact RCPSP (Mode A)
  - n > 200  → LNS Lagrangian + SSGS (Mode B)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from types import ModuleType

from .models import (
    Activity,
    ActivityDAG,
    ResourcePool,
    ScheduleError,
    ScheduleOutput,
    SchedulingStrategy,
)
from .scheduler import SerialScheduler

_log = logging.getLogger(__name__)

# ADR-121 D5: OTel span events — lazy import para não bloquear ambientes sem SDK
try:
    from opentelemetry import trace as _otel_trace

    trace: ModuleType | None = _otel_trace
    _OTEL_AVAILABLE = True
except ImportError:  # pragma: no cover
    trace = None
    _OTEL_AVAILABLE = False


def _span_event(name: str, attrs: dict) -> None:
    """Emite span.add_event() no span OTel ativo. No-op se SDK ausente ou fora de span."""
    if not _OTEL_AVAILABLE or trace is None:  # pragma: no branch
        return
    try:
        span = trace.get_current_span()
        if span and span.is_recording():
            span.add_event(name, attrs)
    except Exception:  # pragma: no cover
        pass


# ADR-075 threshold separating exact (CP-SAT) from heuristic (LNS) regime
_CPSAT_MAX_ACTIVITIES = 200


def select_scheduling_algorithm(
    num_activities: int,
    num_resource_types: int,
    contract_duration_weeks: int,
    deadline_margin_pct: float,
    criticality: str = "medium",
) -> SchedulingStrategy:
    """Select the best scheduling algorithm based on problem characteristics.

    Decision rules (ADR-075, supersedes ADR-004):
      - num_activities <= 200  → CP-SAT exact RCPSP (Mode A, 60s timeout)
      - num_activities >  200  → LNS Lagrangian + SSGS (Mode B)
    """
    if num_activities <= _CPSAT_MAX_ACTIVITIES:
        return SchedulingStrategy(
            algorithm="CP-SAT",
            heuristics=[],
            timeout_seconds=60,
            leveling_pass=False,
            rationale=(
                f"n={num_activities} ≤ {_CPSAT_MAX_ACTIVITIES} — CP-SAT exact RCPSP "
                f"(ADR-075 Mode A, {criticality} criticality)."
            ),
        )

    # n > 200: LNS heuristic
    return SchedulingStrategy(
        algorithm="LNS",
        heuristics=[],
        timeout_seconds=0,
        leveling_pass=False,
        rationale=(f"n={num_activities} > {_CPSAT_MAX_ACTIVITIES} — LNS Lagrangian+SSGS heuristic (ADR-075 Mode B)."),
    )


@dataclass
class ExploreResult:
    """One ranked candidate from explore_schedules() / compare_all_algorithms()."""

    heuristic: str
    schedule: ScheduleOutput
    quality_score: float
    # Set when the algorithm failed or produced an infeasible schedule.
    error: str | None = None


def _explore_cpsat(
    dag: ActivityDAG,
    pool: ResourcePool,
    deadline_weeks: int,
    score_deadline: int,
    strategy: SchedulingStrategy | None,
) -> list[ExploreResult]:
    try:
        from .cpsat_scheduler import CpSatScheduler  # lazy — avoids import cost

        timeout = float(strategy.timeout_seconds) if strategy and strategy.timeout_seconds else 60.0
        # Horizonte generoso: deadline é META (avaliada via quality_score), não
        # restrição rígida. Σ durações garante viabilidade para qualquer DAG;
        # caminho crítico que excede o deadline é reportado, não causa INFEASIBLE.
        _sum_dur = sum(int(getattr(a, "duration_weeks", 0) or 0) for a in dag.activities)
        horizon = max(deadline_weeks, _sum_dur + deadline_weeks)
        cpsat = CpSatScheduler(timeout_seconds=timeout, horizon_weeks=horizon)
        sched = cpsat.schedule(dag=dag, pool=pool)
        if sched.feasible:
            score = sched.metrics.quality_score(deadline_weeks=score_deadline)
            _log.info(
                "explore_schedules: CP-SAT feasible makespan=%dw quality=%.4f",
                sched.makespan,
                score,
            )
            _span_event(
                "scheduling.solution.found",
                {
                    "algorithm": "CP-SAT",
                    "makespan_weeks": sched.makespan,
                    "quality_score": round(score, 4),
                },
            )
            return [ExploreResult("CP-SAT", sched, score)]
        _span_event("scheduling.solution.failed", {"algorithm": "CP-SAT", "reason": "infeasible"})
        raise ScheduleError(
            "CP-SAT solver não encontrou solução viável dentro do horizonte configurado. "
            f"Verifique restrições de precedência e disponibilidade do pool "
            f"(deadline={deadline_weeks}w, horizon={horizon}w)."
        )
    except ScheduleError:
        raise
    except Exception as exc:
        _log.warning("CP-SAT solver falhou com erro inesperado", exc_info=True)
        raise ScheduleError(f"CP-SAT solver falhou com erro inesperado: {exc}") from exc


def _explore_lns(
    dag: ActivityDAG,
    pool: ResourcePool,
    score_deadline: int,
    initial_lambdas: dict | None,
) -> list[ExploreResult]:
    try:
        from concilium.domain.services.planning.matching_oracle import MatchingOracle

        from .lns_scheduler import LnsScheduler  # lazy import

        oracle = MatchingOracle(mob_costs={})
        lns = LnsScheduler(oracle=oracle, initial_lambdas=initial_lambdas or None)
        sched = lns.schedule(dag=dag, pool=pool)
        if sched.feasible:
            score = sched.metrics.quality_score(deadline_weeks=score_deadline)
            _log.info(
                "explore_schedules: LNS feasible makespan=%dw quality=%.4f",
                sched.makespan,
                score,
            )
            _span_event(
                "scheduling.solution.found",
                {
                    "algorithm": "LNS",
                    "makespan_weeks": sched.makespan,
                    "quality_score": round(score, 4),
                },
            )
            return [ExploreResult("LNS", sched, score)]
        raise ScheduleError(
            "LNS solver não encontrou solução viável. Verifique restrições de precedência e disponibilidade do pool."
        )
    except ScheduleError:
        raise
    except Exception as exc:
        raise ScheduleError(f"LNS solver falhou com erro inesperado: {exc}") from exc


def _explore_serial(
    activities: list[Activity],
    dag: ActivityDAG,
    pool: ResourcePool,
    deadline_weeks: int,
    score_deadline: int,
    heuristics: list[str] | None,
    top_n: int,
) -> list[ExploreResult]:
    if heuristics is None:
        heuristics = ["MINSLK", "LPT", "MAXRES", "ES", "GR"]

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
        except Exception as e:
            _log.warning("Heurística %s falhou (infeasible ou erro): %s", heuristic, e, exc_info=True)

    results.sort(key=lambda r: (-r.quality_score, r.schedule.makespan))
    return results[:top_n]


def explore_schedules(
    activities: list[Activity],
    dag: ActivityDAG,
    pool: ResourcePool,
    deadline_weeks: int,
    heuristics: list[str] | None = None,
    top_n: int = 3,
    deadline_for_score: int | None = None,
    strategy: SchedulingStrategy | None = None,
    initial_lambdas: dict | None = None,
) -> list[ExploreResult]:
    """Run scheduling and return top-N ranked results.

    Dispatches to the algorithm specified by *strategy*:
      - "CP-SAT":  exact RCPSP via OR-Tools CP-SAT (ADR-075 Mode A, n ≤ 200)
      - "LNS":     Lagrangian + SSGS heuristic (ADR-075 Mode B, n > 200)
    - any other: SerialScheduler multi-heuristic SGS (historical / explicit override)

    Args:
        activities:         List of activities to schedule (used by SerialScheduler path).
        dag:                Precedence DAG (used by all paths).
        pool:               Resource pool.
        deadline_weeks:     Hard deadline (horizon for CP-SAT; not used by LNS).
        heuristics:         Heuristic names for SerialScheduler path (default: all 5).
        top_n:              Maximum number of results to return.
        deadline_for_score: Deadline used for quality scoring (defaults to deadline_weeks).
        strategy:           SchedulingStrategy from select_scheduling_algorithm().
                            If None, falls back to SerialScheduler.
        initial_lambdas:    ADR-079 — pre-warming dict from RelatorioOportunidades (ADR-078).
                            Keys: (atividade_i, atividade_j, tipo_id); values: λ₀.
                            Passed to LnsScheduler when algorithm=="LNS".
    """
    score_deadline = deadline_for_score or deadline_weeks
    algorithm = (strategy.algorithm if strategy else None) or "SerialScheduler"

    _log.debug(
        "explore_schedules: algorithm=%s n_activities=%d deadline=%dw",
        algorithm,
        len(dag.activities) if dag else 0,
        deadline_weeks,
    )
    # ADR-121 D5: registra decisão de algoritmo como span event
    _span_event(
        "scheduling.algorithm.selected",
        {
            "algorithm": algorithm,
            "n_activities": len(dag.activities) if dag else 0,
            "deadline_weeks": deadline_weeks,
        },
    )

    # ── CP-SAT exact solver (ADR-075 Mode A) ─────────────────────────────────
    if algorithm == "CP-SAT":
        return _explore_cpsat(dag, pool, deadline_weeks, score_deadline, strategy)

    # ── LNS Lagrangian + SSGS (ADR-075 Mode B) ───────────────────────────────
    elif algorithm == "LNS":
        return _explore_lns(dag, pool, score_deadline, initial_lambdas)

    # ── SerialScheduler SGS ───────────────────────────────────────────────────
    # Reached only when algorithm is neither CP-SAT nor LNS (direct SerialScheduler
    # invocation or explicit heuristic override). CP-SAT/LNS failures raise ScheduleError
    # and never fall through here.
    if algorithm not in ("CP-SAT", "LNS", "SerialScheduler"):
        # Explicit non-standard algorithm name — treat as priority rule
        _log.debug("explore_schedules: SerialScheduler path (algorithm=%s)", algorithm)
    return _explore_serial(activities, dag, pool, deadline_weeks, score_deadline, heuristics, top_n)


# Default algorithms exposed by compare_all_algorithms().
# Order matters: CP-SAT (exact) → LNS (heuristic large) → MINSLK (serial baseline).
_COMPARISON_ALGORITHMS: list[str] = ["CP-SAT", "LNS", "MINSLK"]


def compare_all_algorithms(
    activities: list[Activity],
    dag: ActivityDAG,
    pool: ResourcePool,
    deadline_weeks: int,
    algorithms: list[str] | None = None,
    deadline_for_score: int | None = None,
) -> list[ExploreResult]:
    """Run multiple scheduling algorithms on the same instance and return all results.

    This is a **development / comparison utility** — the pipeline itself runs a
    single algorithm selected by ``select_scheduling_algorithm()``.  Call this
    function to understand the trade-offs between solvers before committing to
    one for a given project class.

    Args:
        activities:         Activity list (used by serial-SGS algorithms).
        dag:                Precedence DAG (used by all algorithms).
        pool:               Resource-capacity pool.
        deadline_weeks:     Hard deadline / horizon.
        algorithms:         Algorithms to try.  Defaults to
                            ``["CP-SAT", "LNS", "MINSLK"]``.
                            Any SSGS priority rule name (LPT, MAXRES, ES, GR …)
                            is also accepted.
        deadline_for_score: Deadline used for quality-score computation
                            (defaults to ``deadline_weeks``).

    Returns:
        One ``ExploreResult`` per algorithm, feasible first, then sorted by
        ``quality_score`` descending.  Failed / infeasible entries have
        ``error`` set and ``quality_score == 0.0``.
    """
    algos = algorithms if algorithms is not None else _COMPARISON_ALGORITHMS
    score_deadline = deadline_for_score or deadline_weeks
    results: list[ExploreResult] = []

    for algorithm in algos:
        if algorithm == "CP-SAT":
            results.append(_compare_cpsat(dag, pool, deadline_weeks, score_deadline))
        elif algorithm == "LNS":
            results.append(_compare_lns(dag, pool, score_deadline))
        else:
            results.append(_compare_serial(activities, dag, pool, deadline_weeks, score_deadline, algorithm))

    # Feasible results first, then by quality_score desc, then makespan asc.
    results.sort(key=lambda r: (r.error is not None, -r.quality_score, r.schedule.makespan))
    return results


def _compare_cpsat(dag: ActivityDAG, pool: ResourcePool, deadline_weeks: int, score_deadline: int) -> ExploreResult:
    try:
        from .cpsat_scheduler import CpSatScheduler  # lazy

        cpsat = CpSatScheduler(timeout_seconds=60.0, horizon_weeks=deadline_weeks)
        sched = cpsat.schedule(dag=dag, pool=pool)
        if sched.feasible:
            score = sched.metrics.quality_score(deadline_weeks=score_deadline)
            return ExploreResult("CP-SAT", sched, score)
        return ExploreResult("CP-SAT", sched, 0.0, error="infeasible")
    except Exception as exc:
        _log.warning("CP-SAT falhou em compare_all_algorithms", exc_info=True)
        return ExploreResult("CP-SAT", _empty_output("CP-SAT"), 0.0, error=str(exc))


def _compare_lns(dag: ActivityDAG, pool: ResourcePool, score_deadline: int) -> ExploreResult:
    try:
        from concilium.domain.services.planning.matching_oracle import MatchingOracle

        from .lns_scheduler import LnsScheduler  # lazy

        oracle = MatchingOracle(mob_costs={})
        lns = LnsScheduler(oracle=oracle)
        sched = lns.schedule(dag=dag, pool=pool)
        if sched.feasible:
            score = sched.metrics.quality_score(deadline_weeks=score_deadline)
            return ExploreResult("LNS", sched, score)
        return ExploreResult("LNS", sched, 0.0, error="infeasible")
    except Exception as exc:
        _log.warning("LNS falhou em compare_all_algorithms", exc_info=True)
        return ExploreResult("LNS", _empty_output("LNS"), 0.0, error=str(exc))


def _compare_serial(
    activities: list[Activity],
    dag: ActivityDAG,
    pool: ResourcePool,
    deadline_weeks: int,
    score_deadline: int,
    algorithm: str,
) -> ExploreResult:
    # SerialScheduler SGS — any valid priority rule name.
    try:
        from .scheduler import SerialScheduler

        scheduler = SerialScheduler(priority_rule=algorithm)
        sched = scheduler.schedule(
            activities=activities,
            dag=dag,
            pool=pool,
            deadline_weeks=deadline_weeks,
        )
        score = sched.metrics.quality_score(deadline_weeks=score_deadline)
        return ExploreResult(algorithm, sched, score)
    except Exception as exc:
        return ExploreResult(algorithm, _empty_output(algorithm), 0.0, error=str(exc))


def _empty_output(heuristic: str) -> ScheduleOutput:
    """Return a dummy infeasible ScheduleOutput for error cases."""
    from .models import ScheduleMetrics

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
        heuristic=heuristic,
    )
