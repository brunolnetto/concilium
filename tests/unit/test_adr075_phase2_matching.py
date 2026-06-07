"""ADR-075 Phase 2 — Matching Oracle: TDD test suite.

Tests for MatchingOracle using OR-Tools SimpleMinCostFlow.
Written before implementation (red phase).
"""

from __future__ import annotations

import pytest

from concilium.domain.models.optimization import (
    ActivityPlan,
    RampProfile,
)
from concilium.domain.services.matching_oracle import MatchingOracle

# ── helpers ───────────────────────────────────────────────────────────────────


def _plan(aid: str, s: int, f: int) -> ActivityPlan:
    return ActivityPlan(activity_id=aid, window=(s, f), n_i=f - s)


def _ramp_flat(aid: str, K: int, n_i: int, res: dict[str, int]) -> RampProfile:
    return RampProfile.build(aid, K_max=K, r=0, d=0, n_i=n_i, resources_per_team=res)


# ── Construction ──────────────────────────────────────────────────────────────


class TestMatchingOracleConstruction:
    def test_instantiation(self):
        oracle = MatchingOracle(mob_costs={"E": (1000.0, 500.0)}, delta_max=2)
        assert oracle is not None

    def test_empty_solve_returns_zero_cost(self):
        oracle = MatchingOracle(mob_costs={"E": (1000.0, 500.0)}, delta_max=2)
        sol = oracle.solve(plans=[], profiles={})
        assert sol.mob_cost_actual == 0.0
        assert sol.edges == []

    def test_single_activity_no_perpetuation(self):
        """Single activity: demand met by fresh hire, supply dismissed."""
        rp = _ramp_flat("A", K=2, n_i=4, res={"E": 1})
        plan = _plan("A", s=0, f=4)
        oracle = MatchingOracle(mob_costs={"E": (1000.0, 500.0)}, delta_max=2)
        sol = oracle.solve([plan], {"A": rp})
        # 2 teams hired = 2000 R$; 2 teams dismissed = 1000 R$
        assert sol.mob_cost_actual == pytest.approx(3000.0)
        assert sol.edges == []


# ── Perpetuation ──────────────────────────────────────────────────────────────


class TestMatchingOraclePerpetuation:
    def test_two_sequential_activities_full_perpetuation(self):
        """A ends week 4, B starts week 4 — same resource — perfect perpetuation."""
        rp_a = _ramp_flat("A", K=2, n_i=4, res={"E": 1})
        rp_b = _ramp_flat("B", K=2, n_i=4, res={"E": 1})
        plans = [_plan("A", 0, 4), _plan("B", 4, 8)]
        oracle = MatchingOracle(mob_costs={"E": (1000.0, 500.0)}, delta_max=2)
        sol = oracle.solve(plans, {"A": rp_a, "B": rp_b})
        # All 2 teams perpetuated: zero mob + zero demob inside sequence
        # Only B's supply at end (2 demob) and A's demand at start (2 mob)
        assert ("A", "B", "E") in [(e[0], e[1], e[2]) for e in sol.edges]
        # With full perpetuation A→B:
        #   A's boundary_demand (start) still hired: 2×1000 = 2000
        #   B's boundary_supply (end)  still dismissed: 2×500 = 1000
        #   Perpetuated 2 units (cost=0)  ← the saving
        # Total = 3000  vs. no-perpetuation = 6000
        assert sol.mob_cost_actual == 3000.0
        assert sol.mob_cost_actual < 6000.0  # cheaper than no perpetuation

    def test_gap_within_delta_still_perpetuates(self):
        """B starts 1 week after A ends (gap=1 <= delta_max=2): perpetuate."""
        rp_a = _ramp_flat("A", K=2, n_i=4, res={"E": 1})
        rp_b = _ramp_flat("B", K=2, n_i=4, res={"E": 1})
        plans = [_plan("A", 0, 4), _plan("B", 5, 9)]  # gap=1
        oracle = MatchingOracle(mob_costs={"E": (1000.0, 500.0)}, delta_max=2)
        sol = oracle.solve(plans, {"A": rp_a, "B": rp_b})
        perpetuated = sum(e[3] for e in sol.edges if e[2] == "E")
        assert perpetuated > 0, "Should perpetuate within delta_max gap"

    def test_gap_exceeds_delta_no_perpetuation(self):
        """B starts 5 weeks after A ends (gap=5 > delta_max=2): no perpetuation."""
        rp_a = _ramp_flat("A", K=2, n_i=4, res={"E": 1})
        rp_b = _ramp_flat("B", K=2, n_i=4, res={"E": 1})
        plans = [_plan("A", 0, 4), _plan("B", 9, 13)]  # gap=5
        oracle = MatchingOracle(mob_costs={"E": (1000.0, 500.0)}, delta_max=2)
        sol = oracle.solve(plans, {"A": rp_a, "B": rp_b})
        assert sol.edges == []

    def test_partial_perpetuation_supply_exceeds_demand(self):
        """A supplies 3 units, B demands 2 — perpetuate 2, dismiss 1."""
        rp_a = _ramp_flat("A", K=3, n_i=4, res={"E": 1})
        rp_b = _ramp_flat("B", K=2, n_i=4, res={"E": 1})
        plans = [_plan("A", 0, 4), _plan("B", 4, 8)]
        oracle = MatchingOracle(mob_costs={"E": (1000.0, 500.0)}, delta_max=2)
        sol = oracle.solve(plans, {"A": rp_a, "B": rp_b})
        qty = sum(e[3] for e in sol.edges if e[2] == "E")
        assert qty == 2

    def test_partial_perpetuation_demand_exceeds_supply(self):
        """A supplies 2 units, B demands 3 — perpetuate 2, hire 1 fresh."""
        rp_a = _ramp_flat("A", K=2, n_i=4, res={"E": 1})
        rp_b = _ramp_flat("B", K=3, n_i=4, res={"E": 1})
        plans = [_plan("A", 0, 4), _plan("B", 4, 8)]
        oracle = MatchingOracle(mob_costs={"E": (1000.0, 500.0)}, delta_max=2)
        sol = oracle.solve(plans, {"A": rp_a, "B": rp_b})
        qty = sum(e[3] for e in sol.edges if e[2] == "E")
        assert qty == 2


# ── Concurrent pairs ─────────────────────────────────────────────────────────


class TestMatchingOracleConcurrentPairs:
    def test_overlapping_activities_reported_as_concurrent_lost(self):
        """A=[0,6) B=[3,9): they overlap, perpetuation A→B is blocked."""
        rp_a = _ramp_flat("A", K=2, n_i=6, res={"E": 1})
        rp_b = _ramp_flat("B", K=2, n_i=6, res={"E": 1})
        plans = [_plan("A", 0, 6), _plan("B", 3, 9)]
        oracle = MatchingOracle(mob_costs={"E": (1000.0, 500.0)}, delta_max=2)
        sol = oracle.solve(plans, {"A": rp_a, "B": rp_b})
        # A ends at 6, B starts at 3 → f_A=6 > s_B=3 → blocked
        # gap if serialized = 6-3=3 > delta_max=2 → NOT in concurrent_lost
        assert ("A", "B", "E") not in sol.concurrent_pairs_lost

    def test_close_overlap_reported(self):
        """A=[0,5) B=[4,9): overlap by 1 week; gap if serialized = f_A-s_B = 5-4 = 1 <= delta_max=2."""
        rp_a = _ramp_flat("A", K=2, n_i=5, res={"E": 1})
        rp_b = _ramp_flat("B", K=2, n_i=5, res={"E": 1})
        plans = [_plan("A", 0, 5), _plan("B", 4, 9)]
        oracle = MatchingOracle(mob_costs={"E": (1000.0, 500.0)}, delta_max=2)
        sol = oracle.solve(plans, {"A": rp_a, "B": rp_b})
        # f_A=5 > s_B=4, overlap=1 <= delta_max=2 → should be in concurrent_lost
        assert ("A", "B", "E") in sol.concurrent_pairs_lost


# ── Cost correctness ──────────────────────────────────────────────────────────


class TestMatchingOracleCostModel:
    def test_zero_mob_cost_no_charge(self):
        """If mob costs are zero, total cost is zero regardless of flow."""
        rp = _ramp_flat("A", K=3, n_i=4, res={"E": 1})
        plan = _plan("A", s=0, f=4)
        oracle = MatchingOracle(mob_costs={"E": (0.0, 0.0)}, delta_max=2)
        sol = oracle.solve([plan], {"A": rp})
        assert sol.mob_cost_actual == 0.0

    def test_multiple_resources_independent_cost(self):
        """Mob cost is summed over all resources independently."""
        rp = _ramp_flat("A", K=2, n_i=4, res={"E": 1, "T": 1})
        plan = _plan("A", s=0, f=4)
        oracle = MatchingOracle(mob_costs={"E": (1000.0, 500.0), "T": (2000.0, 1000.0)}, delta_max=2)
        sol = oracle.solve([plan], {"A": rp})
        # E: 2 mob = 2000, 2 demob = 1000 => 3000
        # T: 2 mob = 4000, 2 demob = 2000 => 6000
        assert sol.mob_cost_actual == pytest.approx(9000.0)

    def test_mob_events_by_resource_counted(self):
        """mob_events_by_resource counts net mob events (hire/dismiss) per resource."""
        rp_a = _ramp_flat("A", K=2, n_i=4, res={"E": 1})
        rp_b = _ramp_flat("B", K=2, n_i=4, res={"E": 1})
        plans = [_plan("A", 0, 4), _plan("B", 4, 8)]  # perfect perpetuation possible
        oracle = MatchingOracle(mob_costs={"E": (1000.0, 500.0)}, delta_max=0)
        sol = oracle.solve(plans, {"A": rp_a, "B": rp_b})
        assert "E" in sol.mob_events_by_resource
