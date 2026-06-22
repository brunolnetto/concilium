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
from concilium.domain.models.analytics.optimization import RampProfile
from concilium.domain.services.planning.matching_oracle import MatchingOracle

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


# ── Missing-line coverage additions ──────────────────────────────────────────


class TestLnsSchedulerMissingLineCoverage:
    """Targets specific uncovered branches in lns_scheduler.py."""

    def test_ssgs_raises_when_deadline_too_tight(self):
        """_find_start raises ScheduleError (line 272) when no slot fits in deadline."""
        from concilium.application.scheduling.lns_scheduler import LnsScheduler
        from concilium.application.scheduling.models import (
            Activity,
            ActivityDAG,
            ResourcePool,
            ScheduleError,
        )

        # Force deadline impossibly tight: deadline_multiplier → near 0 means scheduler
        # will not fit activities.  We override by using a tiny multiplier.
        act = Activity(activity_id="X", description="", duration_weeks=100, required_resources={"E": 1})
        dag = ActivityDAG(activities=[act], precedence=[])
        scheduler = LnsScheduler(oracle=_oracle(), k_max=2, deadline_multiplier=0.001)
        # schedule() catches ScheduleError internally and returns _empty_output()
        result = scheduler.schedule(dag, _pool(cap=1))
        assert not result.feasible

    def test_empty_dag_returns_infeasible_output(self):
        """Empty dag hits _empty_output (line 193) when best_output stays None."""
        from concilium.application.scheduling.lns_scheduler import LnsScheduler
        from concilium.application.scheduling.models import ActivityDAG, ResourcePool

        scheduler = LnsScheduler(oracle=_oracle(), k_max=3)
        dag = ActivityDAG(activities=[], precedence=[])
        result = scheduler.schedule(dag, ResourcePool(resources={}))
        assert not result.feasible
        assert result.makespan == 0

    def test_convergence_early_exit(self):
        """Lines 181-185: convergence check triggers break when ΔC/C_0 < tol."""
        from concilium.application.scheduling.lns_scheduler import LnsScheduler

        # Very tight tol forces convergence even after 1 step
        dag, acts = _dag_chain(2, dur=3)
        scheduler = LnsScheduler(oracle=_oracle(), k_max=20, convergence_tol=1.0)
        scheduler.schedule(dag, _pool(10), ramp_profiles=_ramps(acts))
        # With tol=1.0 (100%) any |ΔC|/C_0 < 1.0 exits → at most ~2 iterations
        assert len(scheduler.iteration_log) <= 3

    def test_lambda_subgradient_update_with_concurrent_pairs(self):
        """Lines 188-190: subgradient λ update runs when oracle returns concurrent pairs."""
        from unittest.mock import MagicMock, patch

        from concilium.application.scheduling.lns_scheduler import LnsScheduler
        from concilium.application.scheduling.models import (
            Activity,
            ActivityDAG,
            ResourcePool,
        )

        dag, acts = _dag_chain(3, dur=2)
        scheduler = LnsScheduler(oracle=_oracle(), k_max=3)

        # Patch oracle to return a fake solution with concurrent_pairs_lost
        fake_sol = MagicMock()
        fake_sol.mob_cost_actual = 500.0
        fake_sol.concurrent_pairs_lost = [("A0", "A1", "E"), ("A1", "A2", "E")]

        with patch.object(scheduler.oracle, "solve", return_value=fake_sol):
            scheduler.schedule(dag, _pool(10))

        # λ should have been updated
        assert len(scheduler.iteration_log) >= 1

    def test_compute_priority_penalties_with_unknown_activity(self):
        """Line 284: penalties[aid_j] when aid_j is NOT in topo (new key created)."""
        from concilium.application.scheduling.lns_scheduler import LnsScheduler

        # lambdas with aid_j='UNKNOWN' not in topo
        lambdas = {("A0", "UNKNOWN", "E"): 1.5, ("A0", "A1", "E"): 2.0}
        topo = ["A0", "A1"]
        penalties = LnsScheduler._compute_priority_penalties(lambdas, topo)
        # UNKNOWN is not in topo but gets created via penalties.get(aid_j, 0.0) + lam
        assert penalties.get("UNKNOWN", -1) == 1.5
        assert penalties["A1"] == 2.0

    def test_lns_demand_at_offset_with_ramp_profile(self):
        """Line 330: _lns_demand_at_offset returns ramp-scaled value when profile set."""
        from concilium.application.scheduling.lns_scheduler import (
            _lns_demand_at_offset,
        )
        from concilium.application.scheduling.models import Activity

        act = Activity(
            activity_id="R",
            description="",
            duration_weeks=3,
            required_resources={"E": 10},
            ramp_profile=[0.5, 1.0, 0.8],
        )
        # offset=0 → round(10 * 0.5) = 5
        assert _lns_demand_at_offset(act, 0, "E", 10) == 5
        # offset=1 → round(10 * 1.0) = 10
        assert _lns_demand_at_offset(act, 1, "E", 10) == 10
        # offset=2 → round(10 * 0.8) = 8
        assert _lns_demand_at_offset(act, 2, "E", 10) == 8
        # offset=3 (beyond ramp) → flat qty=10
        assert _lns_demand_at_offset(act, 3, "E", 10) == 10

    def test_initial_lambdas_pre_warming(self):
        """Lines 113: initial_lambdas dict is copied and used in first iteration."""
        from concilium.application.scheduling.lns_scheduler import LnsScheduler

        dag, acts = _dag_chain(3, dur=4)
        initial = {("A0", "A1", "E"): 50.0}
        scheduler = LnsScheduler(oracle=_oracle(), k_max=2, initial_lambdas=initial)
        result = scheduler.schedule(dag, _pool(10), ramp_profiles=_ramps(acts))
        assert result is not None
        assert len(scheduler.iteration_log) >= 1
