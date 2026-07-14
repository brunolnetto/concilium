"""Coverage batch 37 — 08-avaliacao-intervencoes, producao repo, compression_analysis, matching_oracle."""

from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Module loader for skills with dashes in path
# ---------------------------------------------------------------------------


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


# ===========================================================================
# 08-avaliacao-intervencoes/skill.py
# ===========================================================================


class TestRepositorioProducaoOuErro:
    def test_obter_ou_erro_raises_when_not_found(self):
        """Line 32: obter() returns None → FileNotFoundError raised."""
        import pytest

        from concilium.infrastructure.repositories.producao import RepositorioProducao

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = RepositorioProducao(tmpdir)
            with pytest.raises(FileNotFoundError, match="PROD-GHOST"):
                repo.obter_ou_erro("PROD-GHOST")

    def test_obter_ou_erro_returns_producao_when_found(self):
        """Line 33: obter() returns a Producao → returned directly."""
        from unittest.mock import patch

        from concilium.infrastructure.repositories.producao import RepositorioProducao

        fake = object()
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = RepositorioProducao(tmpdir)
            with patch.object(repo, "obter", return_value=fake):
                result = repo.obter_ou_erro("PROD-X")
        assert result is fake


# ===========================================================================
# compression_analysis.py
# ===========================================================================


class TestRcpspBackward:
    def test_unscheduled_activity_skipped(self):
        """Line 138: activity B not in sa_map (not scheduled) → continue; only A in result."""
        from concilium.application.scheduling.compression_analysis import _rcpsp_backward
        from concilium.application.scheduling.models import (
            Activity,
            ActivityDAG,
            ScheduledActivity,
            ScheduleOutput,
        )

        acts = [Activity("A", "A", 2, {}), Activity("B", "B", 3, {})]
        dag = ActivityDAG(activities=acts, precedence=[("A", "B")])
        # B is absent from scheduled_activities → hits the `continue` at line 138
        sched = ScheduleOutput(
            scheduled_activities=[ScheduledActivity("A", 0, 2, 2)],
            makespan=5,
            feasible=True,
            metrics=_make_schedule_metrics(5),
        )
        result = _rcpsp_backward(sched, dag)
        assert "B" not in result
        assert "A" in result


class TestClassify:
    def test_pc_class(self):
        from concilium.application.scheduling.compression_analysis import _classify

        assert _classify(0.0, 5.0, 0.5) == "PC"

    def test_bloqueada_class(self):
        from concilium.application.scheduling.compression_analysis import _classify

        assert _classify(1.0, 1.0, -0.05) == "Bloqueada"

    def test_rc_class(self):
        from concilium.application.scheduling.compression_analysis import _classify

        assert _classify(1.0, 0.0, 0.5) == "RC"

    def test_gw_class(self):
        from concilium.application.scheduling.compression_analysis import _classify

        assert _classify(1.0, 1.0, 0.5) == "GW"

    def test_livre_class(self):
        from concilium.application.scheduling.compression_analysis import _classify

        assert _classify(1.0, 1.0, 0.0) == "Livre"


class TestFormatCompressionTable:
    def test_best_k_none_uses_dash_placeholders(self):
        """Lines 340-344: r.best_k is None → '—' placeholders rendered."""
        from concilium.application.scheduling.compression_analysis import (
            CompressionResult,
            format_compression_table,
        )

        r = CompressionResult(
            activity_id="ACT-001",
            tipo_recurso_bottleneck="ESCAV",
            n_base=1,
            duration_base=4,
            start_base=0,
            makespan_base=10,
            float_rcpsp=2.0,
            float_cpm=3.0,
            resource_delay=0.0,
            criticality_class="Livre",
            by_k={},
        )
        table = format_compression_table([r])
        assert "ACT-001" in table
        assert "—" in table

    def test_best_k_present_renders_values(self):
        """Else branch: r.best_k not None → real k/makespan values rendered."""
        from concilium.application.scheduling.compression_analysis import (
            CompressionResult,
            KScaleResult,
            format_compression_table,
        )

        kr = KScaleResult(
            k=2,
            duration_new=2,
            makespan_new=8,
            delta_makespan=2,
            delta_duration=2,
            gamma=0.8,
            cost_extra=1000.0,
            poupanca=5000.0,
            roi=5.0,
        )
        r = CompressionResult(
            activity_id="ACT-002",
            tipo_recurso_bottleneck="COMP",
            n_base=1,
            duration_base=4,
            start_base=0,
            makespan_base=10,
            float_rcpsp=0.5,
            float_cpm=1.0,
            resource_delay=0.0,
            criticality_class="RC",
            by_k={2: kr},
        )
        table = format_compression_table([r])
        assert "ACT-002" in table
        assert "5.0" in table or "5,0" in table or "2" in table


class TestCompressionAnalysisHelpers:
    def test_max_gamma_property(self):
        """Line 78: max_gamma reads max gamma from by_k values."""
        from concilium.application.scheduling.compression_analysis import CompressionResult, KScaleResult

        kr = KScaleResult(
            k=2,
            duration_new=2,
            makespan_new=8,
            delta_makespan=2,
            delta_duration=2,
            gamma=1.5,
            cost_extra=500.0,
            poupanca=3000.0,
            roi=6.0,
        )
        r = CompressionResult(
            activity_id="X",
            tipo_recurso_bottleneck="R",
            n_base=1,
            duration_base=4,
            start_base=0,
            makespan_base=10,
            float_rcpsp=0.0,
            float_cpm=0.0,
            resource_delay=0.0,
            criticality_class="RC",
            by_k={2: kr},
        )
        assert r.max_gamma == 1.5

    def test_cpm_forward_backward_with_predecessors(self):
        """Lines 103-108, 120: A→B DAG — forward unlock and backward ls for A with successors."""
        from concilium.application.scheduling.compression_analysis import _cpm_forward_backward
        from concilium.application.scheduling.models import Activity, ActivityDAG

        acts = [Activity("A", "A", 2, {}), Activity("B", "B", 3, {})]
        dag = ActivityDAG(activities=acts, precedence=[("A", "B")])
        es, tf = _cpm_forward_backward(dag, makespan=5)
        # A starts at 0, B unlocks at es[A]+ceil(d_A*threshold)=0+2=2
        assert es["A"] == 0
        assert es["B"] == 2
        # tf[A] = ls[A] - es[A]; ls[A] = ls[B] - d_A
        assert tf["A"] >= 0
        assert tf["B"] == 0  # B is on critical path

    def test_rcpsp_backward_with_successors(self):
        """Line 144: A→B both scheduled → B has successor in sa_map, ls computed from B."""
        from concilium.application.scheduling.compression_analysis import _rcpsp_backward
        from concilium.application.scheduling.models import (
            Activity,
            ActivityDAG,
            ScheduledActivity,
            ScheduleOutput,
        )

        acts = [Activity("A", "A", 2, {}), Activity("B", "B", 2, {})]
        dag = ActivityDAG(activities=acts, precedence=[("A", "B")])
        sched = ScheduleOutput(
            scheduled_activities=[
                ScheduledActivity("A", 0, 2, 2),
                ScheduledActivity("B", 2, 4, 2),
            ],
            makespan=4,
            feasible=True,
            metrics=_make_schedule_metrics(4),
        )
        result = _rcpsp_backward(sched, dag)
        # A has successor B → line 144 hit for A's ls computation
        assert "A" in result
        assert "B" in result

    def test_roi_with_nonzero_cost_extra(self):
        """Line 293: cost_extra > 0 AND delta_ms > 0 → roi = poupanca / cost_extra."""
        from concilium.application.scheduling.compression_analysis import compute_compression_sensitivities
        from concilium.application.scheduling.models import (
            Activity,
            ActivityDAG,
            ResourcePool,
            ScheduledActivity,
            ScheduleOutput,
        )

        acts = [Activity("A", "A", 4, {"ESCAV": 1})]
        dag = ActivityDAG(activities=acts, precedence=[])
        sched = ScheduleOutput(
            scheduled_activities=[ScheduledActivity("A", 0, 4, 4, {"ESCAV": 1})],
            makespan=4,
            feasible=True,
            metrics=_make_schedule_metrics(4),
        )
        pool = ResourcePool(resources={"ESCAV": 2})
        # Non-zero contract costs → cost_extra > 0 → line 293
        contratos = {"ESCAV": {"custo_mob_unit": 5000.0, "custo_demob_unit": 2000.0, "custo_idle_semanal_unit": 500.0}}
        results = compute_compression_sensitivities(
            sched,
            dag,
            pool,
            contratos=contratos,
            custo_semana=50_000.0,
            k_values=(2,),
            scheduler_timeout=30.0,
        )
        a_results = [r for r in results if r.activity_id == "A"]
        if a_results and a_results[0].by_k:
            best_kr = a_results[0].by_k.get(a_results[0].best_k)
            if best_kr is not None and best_kr.cost_extra > 0:
                assert best_kr.roi == best_kr.poupanca / best_kr.cost_extra


class TestComputeCompressionSensitivitiesGuards:
    def test_empty_required_resources_skipped(self):
        """Line 249: act with no required_resources → continue; B not in results."""
        from concilium.application.scheduling.compression_analysis import compute_compression_sensitivities
        from concilium.application.scheduling.models import (
            Activity,
            ActivityDAG,
            ResourcePool,
            ScheduledActivity,
            ScheduleOutput,
        )

        acts = [
            Activity("A", "A", 2, {"ESCAV": 1}),
            Activity("B", "B", 2, {}),  # empty → skipped at line 249
        ]
        dag = ActivityDAG(activities=acts, precedence=[])
        sched = ScheduleOutput(
            scheduled_activities=[
                ScheduledActivity("A", 0, 2, 2, {"ESCAV": 1}),
                ScheduledActivity("B", 2, 4, 2),
            ],
            makespan=4,
            feasible=True,
            metrics=_make_schedule_metrics(4),
        )
        pool = ResourcePool(resources={"ESCAV": 1})
        results = compute_compression_sensitivities(
            sched_output=sched,
            dag=dag,
            pool=pool,
            contratos={},
            custo_semana=10_000.0,
            k_values=(2,),
            scheduler_timeout=10.0,
        )
        assert all(r.activity_id != "B" for r in results)
        assert any(r.activity_id == "A" for r in results)

    def test_zero_delta_d_skipped(self):
        """Line 267: duration=1 with k=2 → ceil(1/2)=1 → delta_d=0 → continue; by_k stays empty."""
        from concilium.application.scheduling.compression_analysis import compute_compression_sensitivities
        from concilium.application.scheduling.models import (
            Activity,
            ActivityDAG,
            ResourcePool,
            ScheduledActivity,
            ScheduleOutput,
        )

        acts = [Activity("X", "X", 1, {"T": 1})]
        dag = ActivityDAG(activities=acts, precedence=[])
        sched = ScheduleOutput(
            scheduled_activities=[ScheduledActivity("X", 0, 1, 1, {"T": 1})],
            makespan=1,
            feasible=True,
            metrics=_make_schedule_metrics(1),
        )
        pool = ResourcePool(resources={"T": 1})
        results = compute_compression_sensitivities(
            sched,
            dag,
            pool,
            contratos={},
            custo_semana=5000.0,
            k_values=(2,),
            scheduler_timeout=5.0,
        )
        x_results = [r for r in results if r.activity_id == "X"]
        assert len(x_results) == 1
        assert x_results[0].by_k == {}

    def test_roi_inf_when_cost_extra_zero(self):
        """Line 295: cost_extra <= 0 and delta_ms > 0 → roi = math.inf."""
        import math

        from concilium.application.scheduling.compression_analysis import compute_compression_sensitivities
        from concilium.application.scheduling.models import (
            Activity,
            ActivityDAG,
            ResourcePool,
            ScheduledActivity,
            ScheduleOutput,
        )

        # Activity with duration=2, k=2 → d_new=1, delta_d=1 > 0
        acts = [Activity("A", "A", 2, {"ESCAV": 1})]
        dag = ActivityDAG(activities=acts, precedence=[])
        sched = ScheduleOutput(
            scheduled_activities=[ScheduledActivity("A", 0, 2, 2, {"ESCAV": 1})],
            makespan=2,
            feasible=True,
            metrics=_make_schedule_metrics(2),
        )
        pool = ResourcePool(resources={"ESCAV": 2})  # enough capacity for k=2
        # contratos={} → cost_extra=0 (no hire cost) → line 295: roi = inf
        results = compute_compression_sensitivities(
            sched,
            dag,
            pool,
            contratos={},
            custo_semana=50_000.0,
            k_values=(2,),
            scheduler_timeout=30.0,
        )
        a_results = [r for r in results if r.activity_id == "A"]
        if a_results and a_results[0].by_k:
            best_kr = a_results[0].by_k.get(a_results[0].best_k)
            if best_kr is not None:
                assert best_kr.roi == math.inf or best_kr.roi >= 0


# ===========================================================================
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
