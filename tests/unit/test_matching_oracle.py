"""Coverage batch 37 — 08-avaliacao-intervencoes, producao repo, compression_analysis, matching_oracle."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_skill(rel_path: str, name: str):
    p = Path(rel_path).resolve()
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def _make_schedule_metrics(makespan: int = 4):
    from concilium.application.scheduling.models import ScheduleMetrics

    return ScheduleMetrics(
        makespan=makespan,
        resource_leveling_score=1.0,
        idle_time=0,
        activity_fragmentation=0,
        critical_path_slack_min=0.0,
        resource_utilization_avg=1.0,
    )


# matching_oracle.py — lines 80, 112, 121
# ===========================================================================


def _make_ramp_profile(
    activity_id: str,
    resources: dict[str, int],
    supply: dict[str, int] | None = None,
    demand: dict[str, int] | None = None,
):
    from concilium.domain.models.analytics.optimization import RampProfile

    return RampProfile(
        activity_id=activity_id,
        K_max=1,
        r=0,
        d=0,
        n_i=2,
        n_0=1,
        resources_per_team=resources,
        m=(1, 1),
        boundary_supply=supply or {},
        boundary_demand=demand or {},
    )


class TestMatchingOracleGuards:
    def test_line80_res_not_in_mob_costs_skipped(self):
        """Line 80: resource 'COMP' in resource_ids but not in mob_costs → continue → no solution edges."""
        from concilium.domain.models.analytics.optimization import ActivityPlan
        from concilium.domain.services.planning.matching_oracle import MatchingOracle

        oracle = MatchingOracle(mob_costs={"ESCAV": (1000.0, 500.0)}, delta_max=2)
        # Profile uses COMP, which is not in oracle.mob_costs → continue at line 80
        rp = _make_ramp_profile("A", resources={"COMP": 1}, supply={"COMP": 1}, demand={"COMP": 1})
        plans = [ActivityPlan(activity_id="A", window=(0, 2), n_i=2)]
        profiles = {"A": rp}

        result = oracle.solve(plans, profiles)
        assert result.mob_cost_actual == 0.0
        assert result.edges == []

    def test_line112_rp_none_for_plan_skipped(self):
        """Line 112: plan 'A' not in profiles → rp=None → continue; empty supply/demand → line 121."""
        from concilium.domain.models.analytics.optimization import ActivityPlan
        from concilium.domain.services.planning.matching_oracle import MatchingOracle

        oracle = MatchingOracle(mob_costs={"ESCAV": (1000.0, 500.0)}, delta_max=2)
        # Profile for "B" makes ESCAV appear in resource_ids (so _solve_resource is called)
        # but plan is for "A" which has no profile → rp=None → continue at 112
        rp_b = _make_ramp_profile("B", resources={"ESCAV": 1}, supply={"ESCAV": 1}, demand={"ESCAV": 1})
        plans = [ActivityPlan(activity_id="A", window=(0, 2), n_i=2)]
        profiles = {"B": rp_b}  # "A" not in profiles

        result = oracle.solve(plans, profiles)
        # A's rp was None → supply/demand empty → line 121 hit → edges empty
        assert result.edges == []
        assert result.mob_cost_actual == 0.0

    def test_line121_no_supply_no_demand_returns_empty(self):
        """Line 121: plan in profiles but boundary_{supply,demand} for ESCAV are zero → return []."""
        from concilium.domain.models.analytics.optimization import ActivityPlan
        from concilium.domain.services.planning.matching_oracle import MatchingOracle

        oracle = MatchingOracle(mob_costs={"ESCAV": (1000.0, 500.0)}, delta_max=2)
        # resources_per_team has ESCAV (so resource_ids contains ESCAV, mob_costs has it)
        # but boundary_supply/demand don't have ESCAV → s_val=0, d_val=0 → not added → line 121
        rp = _make_ramp_profile("A", resources={"ESCAV": 1}, supply={}, demand={})
        plans = [ActivityPlan(activity_id="A", window=(0, 2), n_i=2)]
        profiles = {"A": rp}

        result = oracle.solve(plans, profiles)
        assert result.edges == []
        assert result.mob_cost_actual == 0.0

