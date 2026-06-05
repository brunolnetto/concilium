"""ADR-075 Phase 1 — Foundation: TDD test suite.

Tests for RampProfile, ActivityPlan, PerpetuationSolution.
Written before implementation (red phase).
"""

from __future__ import annotations

import pytest

from concilium.domain.models.optimization import ActivityPlan, PerpetuationSolution, RampProfile


# ── RampProfile.build() ───────────────────────────────────────────────────────


class TestRampProfileBuild:
    """RampProfile.build() factory — computes m vector and boundary values."""

    def test_flat_profile_no_ramp(self):
        """r=0, d=0: all plateau weeks at K_max."""
        rp = RampProfile.build("A", K_max=4, r=0, d=0, n_i=3, resources_per_team={"E": 1})
        assert rp.m == (4, 4, 4)
        assert rp.boundary_supply == {"E": 4}
        assert rp.boundary_demand == {"E": 4}

    def test_ramp_up_only(self):
        """r=3, d=0: linear ramp-up over 3 weeks, then plateau."""
        rp = RampProfile.build("A", K_max=4, r=3, d=0, n_i=5, resources_per_team={"E": 1}, n_0=1)
        # t=0: ramp-up => 1+floor(0*(4-1)/3)=1
        # t=1: 1+floor(1*(3)/3)=2
        # t=2: 1+floor(2*(3)/3)=3
        # t=3: plateau => 4
        # t=4: plateau => 4
        assert rp.m == (1, 2, 3, 4, 4)
        assert rp.boundary_demand == {"E": 1}
        assert rp.boundary_supply == {"E": 4}

    def test_ramp_down_only(self):
        """r=0, d=3: plateau then ramp-down over 3 weeks."""
        rp = RampProfile.build("A", K_max=4, r=0, d=3, n_i=5, resources_per_team={"E": 2})
        # t=0: plateau => 4; t=1: plateau => 4
        # t=2: ramp-down, j=0 => 4; t=3: j=1 => 4-floor(4/3*1)=4-1=3; t=4: j=2 => 4-floor(8/3)=4-2=2
        assert rp.m[0] == 4
        assert rp.m[-1] <= rp.m[0]
        assert rp.boundary_demand == {"E": 8}  # m[0]=4, 4*2=8
        assert rp.boundary_supply["E"] < 8  # ramp-down reduces supply

    def test_ramp_up_and_down_with_plateau(self):
        """r=2, d=2, n_i=7: ramp-up, plateau, ramp-down."""
        rp = RampProfile.build("A", K_max=4, r=2, d=2, n_i=7, resources_per_team={"E": 1}, n_0=1)
        assert len(rp.m) == 7
        assert rp.m[0] == 1               # first week: n_0
        assert rp.m[2] == 4               # plateau (t=r=2 is first plateau week... wait t=2 is ramp-up end)
        assert rp.m[-1] < rp.m[2]        # ramp-down brings it below K_max
        assert rp.boundary_demand == {"E": 1}
        assert rp.boundary_supply["E"] >= 0

    def test_zero_plateau_when_r_plus_d_equals_n_i(self):
        """r+d=n_i: no plateau weeks, ramp-up then immediate ramp-down."""
        rp = RampProfile.build("A", K_max=4, r=2, d=2, n_i=4, resources_per_team={"E": 1}, n_0=1)
        assert len(rp.m) == 4
        assert rp.m[0] == 1  # n_0
        assert max(rp.m) == 4  # K_max reached somewhere

    def test_resources_per_team_scaling(self):
        """boundary values scale with resources_per_team."""
        rp = RampProfile.build("A", K_max=3, r=0, d=0, n_i=4, resources_per_team={"E": 2, "T": 3})
        assert rp.boundary_supply == {"E": 6, "T": 9}
        assert rp.boundary_demand == {"E": 6, "T": 9}

    def test_multiple_resources(self):
        """Boundary values computed independently per resource type."""
        rp = RampProfile.build("A", K_max=2, r=1, d=1, n_i=4, resources_per_team={"E": 1, "T": 2}, n_0=1)
        assert rp.boundary_demand["T"] == 2 * rp.boundary_demand["E"]
        assert rp.boundary_supply["T"] == 2 * rp.boundary_supply["E"]

    def test_m_length_equals_n_i(self):
        """m vector always has exactly n_i elements."""
        for n_i in [1, 5, 10, 52]:
            rp = RampProfile.build("A", K_max=4, r=0, d=0, n_i=n_i, resources_per_team={})
            assert len(rp.m) == n_i

    def test_m_values_capped_at_K_max(self):
        """No element of m exceeds K_max."""
        rp = RampProfile.build("A", K_max=5, r=4, d=2, n_i=10, resources_per_team={"E": 1}, n_0=1)
        assert all(v <= 5 for v in rp.m)

    def test_m_values_non_negative(self):
        """All elements of m are >= 0."""
        rp = RampProfile.build("A", K_max=4, r=2, d=3, n_i=8, resources_per_team={"E": 1}, n_0=1)
        assert all(v >= 0 for v in rp.m)


# ── RampProfile validation ────────────────────────────────────────────────────


class TestRampProfileValidation:
    """Validation rules from ADR-075 D1."""

    def test_rejects_r_plus_d_greater_than_n_i(self):
        """r+d > n_i: ramp phases exceed activity duration → ValueError."""
        with pytest.raises(Exception, match=r"r .* d .* n_i"):
            RampProfile.build("A", K_max=4, r=3, d=3, n_i=5, resources_per_team={})

    def test_rejects_K_max_less_than_n_0(self):
        """K_max < n_0: impossible ramp-up → ValueError."""
        with pytest.raises(Exception):
            RampProfile.build("A", K_max=2, r=1, d=0, n_i=3, resources_per_team={}, n_0=5)

    def test_accepts_r_plus_d_equals_n_i(self):
        """r+d == n_i: no plateau weeks — boundary case is valid."""
        rp = RampProfile.build("A", K_max=4, r=2, d=2, n_i=4, resources_per_team={"E": 1}, n_0=1)
        assert rp is not None

    def test_accepts_zero_resources_per_team(self):
        """Empty resources_per_team is valid — boundary values are empty dicts."""
        rp = RampProfile.build("A", K_max=4, r=1, d=0, n_i=3, resources_per_team={})
        assert rp.boundary_supply == {}
        assert rp.boundary_demand == {}

    def test_boundary_supply_reduced_by_ramp_down(self):
        """Ramp-down reduces boundary_supply below K_max.

        K_max=2, d=2, n_i=4:
          t=2: j=0 → 2 - floor(0*1.0)=2
          t=3: j=1 → 2 - floor(1*1.0)=1   ← m[-1]=1, not K_max=2
        """
        rp = RampProfile.build("A", K_max=2, r=0, d=2, n_i=4, resources_per_team={"E": 1})
        # m[-1] should be 1 (reduced by ramp-down, but not zero)
        assert rp.m[-1] == 1
        assert rp.boundary_supply == {"E": 1}
        assert rp.boundary_supply["E"] < rp.K_max

    def test_activity_id_preserved(self):
        rp = RampProfile.build("activity-XYZ", K_max=3, r=0, d=0, n_i=2, resources_per_team={})
        assert rp.activity_id == "activity-XYZ"

    def test_frozen_rejects_direct_assignment(self):
        """frozen=True: field re-assignment raises TypeError/ValidationError."""
        rp = RampProfile.build("A", K_max=4, r=0, d=0, n_i=3, resources_per_team={})
        with pytest.raises(Exception):
            rp.K_max = 99  # type: ignore[misc]


# ── ActivityPlan ──────────────────────────────────────────────────────────────


class TestActivityPlan:
    def test_creation(self):
        ap = ActivityPlan(activity_id="A", window=(5, 10), n_i=5)
        assert ap.activity_id == "A"
        assert ap.window == (5, 10)
        assert ap.n_i == 5

    def test_duration_matches_window(self):
        ap = ActivityPlan(activity_id="B", window=(0, 8), n_i=8)
        assert ap.window[1] - ap.window[0] == ap.n_i


# ── PerpetuationSolution ──────────────────────────────────────────────────────


class TestPerpetuationSolution:
    def test_creation(self):
        ps = PerpetuationSolution(
            edges=[("A", "B", "E", 2)],
            mob_cost_actual=500.0,
            mob_events_by_resource={"E": 1},
            concurrent_pairs_lost=[("A", "C", "E")],
        )
        assert len(ps.edges) == 1
        assert ps.mob_cost_actual == 500.0
        assert ps.mob_events_by_resource["E"] == 1
        assert len(ps.concurrent_pairs_lost) == 1

    def test_empty_perpetuation(self):
        """Zero perpetuation: all mob costs are baseline, no edges."""
        ps = PerpetuationSolution(
            edges=[],
            mob_cost_actual=1000.0,
            mob_events_by_resource={"E": 5},
            concurrent_pairs_lost=[],
        )
        assert ps.edges == []
        assert ps.mob_cost_actual == 1000.0
