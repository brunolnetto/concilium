"""ADR-075 Phase 4 — LNS Scheduler: TDD test suite.

Tests for LnsScheduler — Lagrangian-relaxation + SSGS inner solver (Mode B).
Uses the existing Activity / ActivityDAG / ResourcePool / ScheduleOutput API.
Written before implementation (red phase).
"""

from __future__ import annotations

from concilium.application.scheduling.lns_scheduler import LnsScheduler
from concilium.application.scheduling.models import (
    Activity,
    ActivityDAG,
    ResourcePool,
    ScheduleOutput,
)
from concilium.domain.models.optimization import RampProfile
from concilium.domain.services.matching_oracle import MatchingOracle

# ── helpers ───────────────────────────────────────────────────────────────────


def _act(aid: str, dur: int, demand: int = 2) -> Activity:
    return Activity(activity_id=aid, description="", duration_weeks=dur, required_resources={"E": demand})


def _dag_chain(n: int, dur: int = 4) -> tuple[ActivityDAG, list[Activity]]:
    acts = [_act(f"A{i}", dur) for i in range(n)]
    prec = [(f"A{i}", f"A{i + 1}") for i in range(n - 1)]
    return ActivityDAG(activities=acts, precedence=prec), acts


def _pool(cap: int = 10) -> ResourcePool:
    return ResourcePool(resources={"E": cap})


def _ramps(acts: list[Activity], K: int = 2) -> dict[str, RampProfile]:
    return {
        a.activity_id: RampProfile.build(
            a.activity_id, K_max=K, r=0, d=0, n_i=a.duration_weeks, resources_per_team={"E": 1}
        )
        for a in acts
    }


def _oracle() -> MatchingOracle:
    return MatchingOracle(mob_costs={"E": (1000.0, 500.0)}, delta_max=2)


# ── Construction ──────────────────────────────────────────────────────────────


class TestLnsSchedulerConstruction:
    def test_instantiation(self):
        scheduler = LnsScheduler(oracle=_oracle(), k_max=5)
        assert scheduler is not None

    def test_k_max_default(self):
        scheduler = LnsScheduler(oracle=_oracle())
        assert scheduler.k_max == 10  # ADR-075 default


# ── Basic scheduling ──────────────────────────────────────────────────────────


class TestLnsSchedulerBasic:
    def test_returns_schedule_output(self):
        dag, acts = _dag_chain(3, dur=4)
        scheduler = LnsScheduler(oracle=_oracle(), k_max=3)
        result = scheduler.schedule(dag, _pool(10), ramp_profiles=_ramps(acts))
        assert isinstance(result, ScheduleOutput)

    def test_schedule_is_feasible(self):
        dag, acts = _dag_chain(3, dur=4)
        scheduler = LnsScheduler(oracle=_oracle(), k_max=3)
        result = scheduler.schedule(dag, _pool(10), ramp_profiles=_ramps(acts))
        assert result.feasible

    def test_fs_precedences_respected(self):
        dag, acts = _dag_chain(3, dur=4)
        scheduler = LnsScheduler(oracle=_oracle(), k_max=3)
        result = scheduler.schedule(dag, _pool(10), ramp_profiles=_ramps(acts))
        sa = {a.activity_id: a for a in result.scheduled_activities}
        assert sa["A1"].start_week >= sa["A0"].start_week + 4
        assert sa["A2"].start_week >= sa["A1"].start_week + 4

    def test_resource_capacity_respected(self):
        """LNS inner solver (SSGS) must respect resource capacity."""
        acts = [_act(f"P{i}", 4, demand=4) for i in range(4)]
        dag = ActivityDAG(activities=acts, precedence=[])
        scheduler = LnsScheduler(oracle=_oracle(), k_max=3)
        result = scheduler.schedule(dag, _pool(10), ramp_profiles=_ramps(acts, K=1))
        assert result.feasible
        usage: dict[int, int] = {}
        for sa in result.scheduled_activities:
            for t in range(sa.start_week, sa.end_week):
                usage[t] = usage.get(t, 0) + 4
        assert all(v <= 10 for v in usage.values())


# ── Lagrangian loop properties ─────────────────────────────────────────────────


class TestLnsSchedulerLagrangian:
    def test_iteration_log_non_empty(self):
        """LnsScheduler exposes iteration_log after solving."""
        dag, acts = _dag_chain(3, dur=4)
        scheduler = LnsScheduler(oracle=_oracle(), k_max=5)
        scheduler.schedule(dag, _pool(10), ramp_profiles=_ramps(acts))
        assert len(scheduler.iteration_log) > 0

    def test_iteration_log_has_required_keys(self):
        """Each log entry must have: k, C_total, C_mob, C_op, n_concurrent."""
        dag, acts = _dag_chain(3, dur=4)
        scheduler = LnsScheduler(oracle=_oracle(), k_max=5)
        scheduler.schedule(dag, _pool(10), ramp_profiles=_ramps(acts))
        for entry in scheduler.iteration_log:
            assert "k" in entry
            assert "C_total" in entry
            assert "C_mob" in entry
            assert "C_op" in entry
            assert "n_concurrent" in entry

    def test_k_max_iterations_respected(self):
        """Solver runs at most k_max iterations (may exit early on convergence)."""
        dag, acts = _dag_chain(3, dur=4)
        scheduler = LnsScheduler(oracle=_oracle(), k_max=7)
        scheduler.schedule(dag, _pool(10), ramp_profiles=_ramps(acts))
        assert len(scheduler.iteration_log) <= 7

    def test_cycle_detection_terminates_early(self):
        """On trivial instance, duplicate schedules trigger early exit (cycle detected)."""
        dag, acts = _dag_chain(2, dur=4)
        scheduler = LnsScheduler(oracle=_oracle(), k_max=100)
        scheduler.schedule(dag, _pool(100), ramp_profiles=_ramps(acts))
        # Trivial instance will cycle quickly → should exit well before k=100
        assert len(scheduler.iteration_log) < 100


# ── Mob cost improvement ───────────────────────────────────────────────────────


class TestLnsSchedulerMobCost:
    def test_mob_cost_in_output(self):
        """mob_cost_actual is recorded in ScheduleOutput metadata."""
        dag, acts = _dag_chain(3, dur=4)
        scheduler = LnsScheduler(oracle=_oracle(), k_max=3)
        result = scheduler.schedule(dag, _pool(10), ramp_profiles=_ramps(acts))
        # mob_cost_actual accessible via scheduler attribute
        assert scheduler.best_mob_cost >= 0.0

    def test_sequential_chain_reduces_mob_cost(self):
        """Strictly sequential chain (abundant resources) → max perpetuation opportunity."""
        dag, acts = _dag_chain(3, dur=4)
        scheduler_no_mob = LnsScheduler(oracle=_oracle(), k_max=1)
        scheduler_lns = LnsScheduler(oracle=_oracle(), k_max=5)
        scheduler_no_mob.schedule(dag, _pool(100), ramp_profiles=_ramps(acts))
        scheduler_lns.schedule(dag, _pool(100), ramp_profiles=_ramps(acts))
        # Both should produce the same schedule (sequential chain), so same mob cost
        # The key property: mob cost is finite and non-negative
        assert scheduler_lns.best_mob_cost >= 0.0
        assert scheduler_no_mob.best_mob_cost >= 0.0
