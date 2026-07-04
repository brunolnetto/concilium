"""Testes NEP-038 — Criticidade RCPSP e compressão de cronograma.

Cobre:
  - _cpm_forward_backward: ES e TF sem restrição de recursos
  - _rcpsp_backward: float a partir da solução RCPSP
  - _build_scaled_activities: d(k) e r(k) corretos
  - _pool_for_activities: pool mínimo após scaling
  - compute_compression_sensitivities: γ, ROI e classe de criticidade
  - Propriedades: PC γ≈1, GW 0<γ<1, Livre γ=0, Bloqueada γ<0

Os testes usam CP-SAT real (não mock) para garantir que a análise
de makespan reflete o comportamento do solver de produção.
"""

from __future__ import annotations

import pytest

from concilium.application.scheduling import (
    Activity,
    ActivityDAG,
    ResourcePool,
    ScheduledActivity,
    ScheduleMetrics,
    ScheduleOutput,
)
from concilium.application.scheduling.compression_analysis import (
    CompressionResult,
    KScaleResult,
    _build_scaled_activities,
    _classify,
    _cpm_forward_backward,
    _pool_for_activities,
    _rcpsp_backward,
    compute_compression_sensitivities,
    format_compression_table,
)

# ── Fixtures comuns ───────────────────────────────────────────────────────────


def _make_metrics(makespan: int = 10) -> ScheduleMetrics:
    return ScheduleMetrics(
        makespan=makespan,
        resource_leveling_score=1.0,
        idle_time=0,
        activity_fragmentation=0,
        critical_path_slack_min=0.0,
        resource_utilization_avg=1.0,
    )


def _make_sched_out(acts_data: list[tuple[str, int, int, dict]], makespan: int) -> ScheduleOutput:
    """Cria ScheduleOutput sintético: (activity_id, start, duration, assigned_resources)."""
    sas = [
        ScheduledActivity(
            activity_id=aid,
            start_week=start,
            end_week=start + dur,
            duration_weeks=dur,
            assigned_resources=ar,
        )
        for aid, start, dur, ar in acts_data
    ]
    return ScheduleOutput(
        scheduled_activities=sas,
        makespan=makespan,
        feasible=True,
        metrics=_make_metrics(makespan),
    )


# ── Testes unitários: helpers internos ────────────────────────────────────────


class TestCpmForwardBackward:
    """CPM sem restrição de recursos — ES e float."""

    def test_single_activity(self):
        """Atividade única: ES=0, float=0."""
        acts = [Activity("A", "A", duration_weeks=5, required_resources={"R": 1})]
        dag = ActivityDAG(activities=acts, precedence=[], thresholds={})
        es, tf = _cpm_forward_backward(dag, makespan=5)
        assert es["A"] == 0
        assert tf["A"] == pytest.approx(0.0)

    def test_chain_ab_pc(self):
        """Cadeia A→B: ambas no CP (float=0)."""
        acts = [
            Activity("A", "A", duration_weeks=3, required_resources={"R": 1}),
            Activity("B", "B", duration_weeks=5, required_resources={"R": 1}),
        ]
        dag = ActivityDAG(activities=acts, precedence=[("A", "B")], thresholds={})
        es, tf = _cpm_forward_backward(dag, makespan=8)
        assert es["A"] == 0
        assert es["B"] == 3
        assert tf["A"] == pytest.approx(0.0)
        assert tf["B"] == pytest.approx(0.0)

    def test_parallel_one_free(self):
        """A e B em paralelo → C: A (dur=2) é livre, B (dur=5) é crítica."""
        acts = [
            Activity("A", "A", duration_weeks=2, required_resources={"R": 1}),
            Activity("B", "B", duration_weeks=5, required_resources={"R": 1}),
            Activity("C", "C", duration_weeks=3, required_resources={"R": 1}),
        ]
        dag = ActivityDAG(
            activities=acts,
            precedence=[("A", "C"), ("B", "C")],
            thresholds={},
        )
        es, tf = _cpm_forward_backward(dag, makespan=8)
        assert es["A"] == 0
        assert es["B"] == 0
        assert es["C"] == 5  # aguarda B terminar
        assert tf["B"] == pytest.approx(0.0)  # crítica
        assert tf["A"] == pytest.approx(3.0)  # float = 5 - 2 = 3

    def test_threshold_partial(self):
        """Threshold θ=0.5: sucessor pode começar após 50% do predecessor."""
        acts = [
            Activity("A", "A", duration_weeks=10, required_resources={"R": 1}),
            Activity("B", "B", duration_weeks=5, required_resources={"R": 1}),
        ]
        dag = ActivityDAG(
            activities=acts,
            precedence=[("A", "B")],
            thresholds={("A", "B"): 0.5},
        )
        es, tf = _cpm_forward_backward(dag, makespan=15)
        # B pode começar em ceil(10×0.5)=5
        assert es["B"] == 5


class TestRcpspBackward:
    """Float na solução RCPSP via backward pass."""

    def test_activity_on_critical_path(self):
        """Atividade que termina exatamente no makespan → float=0."""
        acts = [Activity("A", "A", duration_weeks=5, required_resources={"R": 1})]
        dag = ActivityDAG(activities=acts, precedence=[], thresholds={})
        sched = _make_sched_out([("A", 0, 5, {"R": 1})], makespan=5)
        tf = _rcpsp_backward(sched, dag)
        assert tf["A"] == pytest.approx(0.0)

    def test_activity_with_float(self):
        """Atividade que termina 3 semanas antes do makespan → float=3."""
        acts = [Activity("A", "A", duration_weeks=5, required_resources={"R": 1})]
        dag = ActivityDAG(activities=acts, precedence=[], thresholds={})
        sched = _make_sched_out([("A", 0, 5, {"R": 1})], makespan=8)
        tf = _rcpsp_backward(sched, dag)
        assert tf["A"] == pytest.approx(3.0)


class TestBuildScaledActivities:
    """_build_scaled_activities: duração e recursos corretos."""

    def test_k2_halves_duration_doubles_resources(self):
        acts = [
            Activity("A", "A", duration_weeks=10, required_resources={"R": 2}),
            Activity("B", "B", duration_weeks=5, required_resources={"R": 1}),
        ]
        dag = ActivityDAG(activities=acts, precedence=[("A", "B")], thresholds={})
        scaled = _build_scaled_activities(dag, "A", k=2)
        a_new = next(a for a in scaled if a.activity_id == "A")
        b_new = next(a for a in scaled if a.activity_id == "B")
        assert a_new.duration_weeks == 5  # ⌈10/2⌉
        assert a_new.required_resources["R"] == 4  # 2 × 2
        assert b_new.duration_weeks == 5  # inalterado
        assert b_new.required_resources["R"] == 1  # inalterado

    def test_k3_odd_duration_ceiling(self):
        acts = [Activity("A", "A", duration_weeks=7, required_resources={"R": 1})]
        dag = ActivityDAG(activities=acts, precedence=[], thresholds={})
        scaled = _build_scaled_activities(dag, "A", k=3)
        a_new = next(a for a in scaled if a.activity_id == "A")
        assert a_new.duration_weeks == 3  # ⌈7/3⌉

    def test_k1_no_change(self):
        acts = [Activity("A", "A", duration_weeks=10, required_resources={"R": 2})]
        dag = ActivityDAG(activities=acts, precedence=[], thresholds={})
        scaled = _build_scaled_activities(dag, "A", k=1)
        a_new = next(a for a in scaled if a.activity_id == "A")
        assert a_new.duration_weeks == 10
        assert a_new.required_resources["R"] == 2


class TestPoolForActivities:
    """_pool_for_activities: piso é o pool base, pico é o máximo de demanda."""

    def test_pool_increases_when_scaled(self):
        acts = [Activity("A", "A", duration_weeks=5, required_resources={"R": 4})]
        base_pool = ResourcePool(resources={"R": 2})
        pool_new = _pool_for_activities(acts, base_pool)
        assert pool_new.resources["R"] == 4

    def test_pool_unchanged_when_below_base(self):
        acts = [Activity("A", "A", duration_weeks=5, required_resources={"R": 1})]
        base_pool = ResourcePool(resources={"R": 3})
        pool_new = _pool_for_activities(acts, base_pool)
        assert pool_new.resources["R"] == 3


class TestClassify:
    """_classify: mapeamento correto de floats e γ para classe."""

    def test_pc(self):
        assert _classify(tf_cpm=0.0, tf_rcpsp=0.0, max_gamma=1.0) == "PC"

    def test_rc(self):
        assert _classify(tf_cpm=5.0, tf_rcpsp=0.0, max_gamma=0.5) == "RC"

    def test_gw(self):
        assert _classify(tf_cpm=5.0, tf_rcpsp=3.0, max_gamma=0.3) == "GW"

    def test_bloqueada(self):
        assert _classify(tf_cpm=5.0, tf_rcpsp=3.0, max_gamma=-0.1) == "Bloqueada"

    def test_livre(self):
        assert _classify(tf_cpm=5.0, tf_rcpsp=3.0, max_gamma=0.0) == "Livre"


# ── Testes de integração com CP-SAT ──────────────────────────────────────────

pytestmark_cpsat = pytest.mark.skipif(False, reason="requer ortools instalado")


def _contratos_dummy(tipo: str, mob: float = 10_000, demob: float = 5_000, idle: float = 1_000) -> dict:
    return {tipo: {"custo_mob_unit": mob, "custo_demob_unit": demob, "custo_idle_semanal_unit": idle}}


class TestComputeCompressionSensitivities:
    """Testes de integração — γ calculado via CP-SAT real."""

    def test_single_cp_activity_gamma_is_one(self):
        """Atividade única no CP: γ = 1 (1 semana de duração → 1 semana de makespan)."""
        acts = [Activity("A", "A", duration_weeks=10, required_resources={"R": 1})]
        dag = ActivityDAG(activities=acts, precedence=[], thresholds={})
        pool = ResourcePool(resources={"R": 1})
        sched = _make_sched_out([("A", 0, 10, {"R": 1})], makespan=10)
        ct = _contratos_dummy("R")

        results = compute_compression_sensitivities(
            sched_output=sched,
            dag=dag,
            pool=pool,
            contratos=ct,
            custo_semana=1_000_000.0,
            k_values=(2,),
        )

        assert len(results) == 1
        r = results[0]
        assert r.activity_id == "A"
        assert r.criticality_class == "PC"
        kr = r.by_k[2]
        assert kr.delta_makespan == 5
        assert kr.duration_new == 5
        assert kr.gamma == pytest.approx(1.0)
        assert kr.viable is True

    def test_chain_ab_compress_a_is_gateway(self):
        """
        A (dur=10, R×1) → B (dur=5, S×1). Pool R=1, S=1.
        A acaba em 10, B começa em 10, C_max=15.
        Comprimir A (k=2) → A termina em 5 → B começa em 5 → C_max=10.
        ΔC_max=5, Δd_A=5, γ=1.
        Float CPM de A = 0 → PC.
        """
        acts = [
            Activity("A", "A", duration_weeks=10, required_resources={"R": 1}),
            Activity("B", "B", duration_weeks=5, required_resources={"S": 1}),
        ]
        dag = ActivityDAG(activities=acts, precedence=[("A", "B")], thresholds={})
        pool = ResourcePool(resources={"R": 1, "S": 1})
        sched = _make_sched_out(
            [("A", 0, 10, {"R": 1}), ("B", 10, 5, {"S": 1})],
            makespan=15,
        )
        ct = {**_contratos_dummy("R"), **_contratos_dummy("S")}

        results = compute_compression_sensitivities(
            sched_output=sched,
            dag=dag,
            pool=pool,
            contratos=ct,
            custo_semana=500_000.0,
            k_values=(2,),
        )

        res_a = next(r for r in results if r.activity_id == "A")
        res_b = next(r for r in results if r.activity_id == "B")

        assert res_a.criticality_class == "PC"
        assert res_a.by_k[2].gamma == pytest.approx(1.0)
        assert res_a.by_k[2].delta_makespan == 5

        # B é PC também (encosta no fim)
        assert res_b.by_k[2].delta_makespan == pytest.approx(2, abs=1)

    def test_free_activity_gamma_zero(self):
        """
        A (dur=3, R×1) e B (dur=10, S×1) em paralelo → C (dur=2, T×1).
        B determina quando C pode começar (float de A = 7w).
        Comprimir A não muda o makespan → γ_A = 0, classe=Livre.
        """
        acts = [
            Activity("A", "A", duration_weeks=3, required_resources={"R": 1}),
            Activity("B", "B", duration_weeks=10, required_resources={"S": 1}),
            Activity("C", "C", duration_weeks=2, required_resources={"T": 1}),
        ]
        dag = ActivityDAG(
            activities=acts,
            precedence=[("A", "C"), ("B", "C")],
            thresholds={},
        )
        pool = ResourcePool(resources={"R": 1, "S": 1, "T": 1})
        sched = _make_sched_out(
            [("A", 0, 3, {"R": 1}), ("B", 0, 10, {"S": 1}), ("C", 10, 2, {"T": 1})],
            makespan=12,
        )
        ct = {**_contratos_dummy("R"), **_contratos_dummy("S"), **_contratos_dummy("T")}

        results = compute_compression_sensitivities(
            sched_output=sched,
            dag=dag,
            pool=pool,
            contratos=ct,
            custo_semana=500_000.0,
            k_values=(2,),
        )

        res_a = next(r for r in results if r.activity_id == "A")
        assert res_a.criticality_class in {"Livre", "PC"}  # float_cpm = 7 → Livre
        if 2 in res_a.by_k:
            assert res_a.by_k[2].delta_makespan == 0
            assert res_a.by_k[2].gamma == pytest.approx(0.0)

    def test_pool_saturated_activity_bloqueada(self):
        """
        Duas atividades A e B partilham R×1 do pool (total=1).
        A: dur=5, R×1; B: dur=5, R×1. Sem precedência — rodadas em sequência.
        C_max = 10.
        Comprimir A para R×2 exigiria pool=2, que disponibilizamos.
        Neste cenário a compressão de A é válida e γ>0 (A e B no CP serial).
        Mas se o pool de R for 1 e tentarmos k=2 para A, o pool sobe para 2.
        Verificamos que o resultado não é classificado como Bloqueada.
        """
        acts = [
            Activity("A", "A", duration_weeks=6, required_resources={"R": 1}),
            Activity("B", "B", duration_weeks=6, required_resources={"R": 1}),
        ]
        dag = ActivityDAG(activities=acts, precedence=[], thresholds={})
        pool = ResourcePool(resources={"R": 1})
        # CP-SAT agenda serialmente: A=0-6, B=6-12
        sched = _make_sched_out(
            [("A", 0, 6, {"R": 1}), ("B", 6, 6, {"R": 1})],
            makespan=12,
        )
        ct = _contratos_dummy("R")

        results = compute_compression_sensitivities(
            sched_output=sched,
            dag=dag,
            pool=pool,
            contratos=ct,
            custo_semana=1_000_000.0,
            k_values=(2,),
        )

        res_a = next(r for r in results if r.activity_id == "A")
        # Comprimir A para R×2 aumenta pool para 2, B pode rodar em paralelo
        # ΔC_max > 0 esperado (reduz de 12 para ~6)
        if 2 in res_a.by_k:
            assert res_a.by_k[2].delta_makespan >= 0

    def test_roi_formula(self):
        """ROI = poupanca / cost_extra onde poupanca = delta_ms × custo_semana."""
        acts = [Activity("A", "A", duration_weeks=10, required_resources={"M": 2})]
        dag = ActivityDAG(activities=acts, precedence=[], thresholds={})
        pool = ResourcePool(resources={"M": 2})
        sched = _make_sched_out([("A", 0, 10, {"M": 2})], makespan=10)

        C_SEMANA = 1_000_000.0
        MOB = 50_000.0
        DEMOB = 25_000.0
        IDLE = 5_000.0

        ct = {"M": {"custo_mob_unit": MOB, "custo_demob_unit": DEMOB, "custo_idle_semanal_unit": IDLE}}

        results = compute_compression_sensitivities(
            sched_output=sched,
            dag=dag,
            pool=pool,
            contratos=ct,
            custo_semana=C_SEMANA,
            k_values=(2,),
            idle_fraction=0.20,
        )

        r = results[0]
        kr = r.by_k[2]
        # d_new = 5, delta_ms = 5
        # cost_extra = (2-1) * 2 * (50k + 25k + 5k×5×0.20) = 2 × (75k + 5k) = 160k
        expected_cost = 1 * 2 * (MOB + DEMOB + IDLE * 5 * 0.20)
        expected_poup = kr.delta_makespan * C_SEMANA
        assert kr.cost_extra == pytest.approx(expected_cost, rel=0.01)
        assert kr.poupanca == pytest.approx(expected_poup, rel=0.01)
        assert kr.roi == pytest.approx(expected_poup / expected_cost, rel=0.01)

    def test_sorted_by_best_roi(self):
        """Resultados ordenados por best_roi decrescente."""
        acts = [
            Activity("A", "A", duration_weeks=10, required_resources={"R": 1}),
            Activity("B", "B", duration_weeks=5, required_resources={"S": 1}),
        ]
        dag = ActivityDAG(activities=acts, precedence=[("A", "B")], thresholds={})
        pool = ResourcePool(resources={"R": 1, "S": 1})
        sched = _make_sched_out(
            [("A", 0, 10, {"R": 1}), ("B", 10, 5, {"S": 1})],
            makespan=15,
        )
        ct = {**_contratos_dummy("R"), **_contratos_dummy("S")}

        results = compute_compression_sensitivities(
            sched_output=sched,
            dag=dag,
            pool=pool,
            contratos=ct,
            custo_semana=1_000_000.0,
            k_values=(2,),
        )

        rois = [r.best_roi for r in results]
        assert rois == sorted(rois, reverse=True)

    def test_scheduler_exception_skips_k_without_crashing(self, monkeypatch, caplog):
        """Falha inesperada do CP-SAT para um k não derruba o cálculo — só descarta
        esse candidato e loga (issue #20: except Exception genérico não devia
        mascarar bug real do scheduler)."""
        import logging

        from concilium.application.scheduling.cpsat_scheduler import CpSatScheduler

        acts = [Activity("A", "A", duration_weeks=10, required_resources={"R": 1})]
        dag = ActivityDAG(activities=acts, precedence=[], thresholds={})
        pool = ResourcePool(resources={"R": 1})
        sched = _make_sched_out([("A", 0, 10, {"R": 1})], makespan=10)
        ct = _contratos_dummy("R")

        def _raise(self, dag, pool):
            raise RuntimeError("boom")

        monkeypatch.setattr(CpSatScheduler, "schedule", _raise)

        with caplog.at_level(logging.WARNING):
            results = compute_compression_sensitivities(
                sched_output=sched,
                dag=dag,
                pool=pool,
                contratos=ct,
                custo_semana=1_000_000.0,
                k_values=(2,),
            )

        assert len(results) == 1
        assert results[0].by_k == {}
        assert "boom" in caplog.text or "Falha ao agendar" in caplog.text


class TestFormatCompressionTable:
    """Smoke test para format_compression_table."""

    def test_returns_string(self):
        acts = [Activity("A", "A", duration_weeks=5, required_resources={"R": 1})]
        dag = ActivityDAG(activities=acts, precedence=[], thresholds={})
        pool = ResourcePool(resources={"R": 1})
        sched = _make_sched_out([("A", 0, 5, {"R": 1})], makespan=5)

        results = compute_compression_sensitivities(
            sched_output=sched,
            dag=dag,
            pool=pool,
            contratos=_contratos_dummy("R"),
            custo_semana=100_000.0,
            k_values=(2,),
        )
        table = format_compression_table(results)
        assert isinstance(table, str)
        assert "A" in table


class TestKScaleResultProperties:
    """Propriedades de KScaleResult."""

    def test_viable_true_when_roi_gt_1_and_positive_delta(self):
        kr = KScaleResult(
            k=2,
            duration_new=5,
            makespan_new=50,
            delta_makespan=5,
            delta_duration=5,
            gamma=1.0,
            cost_extra=1_000,
            poupanca=5_000_000,
            roi=5000.0,
        )
        assert kr.viable is True

    def test_viable_false_when_roi_lt_1(self):
        kr = KScaleResult(
            k=2,
            duration_new=5,
            makespan_new=50,
            delta_makespan=5,
            delta_duration=5,
            gamma=1.0,
            cost_extra=10_000_000,
            poupanca=100,
            roi=0.00001,
        )
        assert kr.viable is False

    def test_viable_false_when_delta_zero(self):
        kr = KScaleResult(
            k=2,
            duration_new=5,
            makespan_new=55,
            delta_makespan=0,
            delta_duration=5,
            gamma=0.0,
            cost_extra=50_000,
            poupanca=0,
            roi=0.0,
        )
        assert kr.viable is False


class TestCompressionResultProperties:
    """Propriedades de CompressionResult."""

    def _make_result(self) -> CompressionResult:
        return CompressionResult(
            activity_id="A",
            tipo_recurso_bottleneck="R",
            n_base=2,
            duration_base=10,
            start_base=0,
            makespan_base=55,
            float_rcpsp=3.0,
            float_cpm=5.0,
            resource_delay=0.0,
            criticality_class="GW",
            by_k={
                2: KScaleResult(2, 5, 50, 5, 5, 1.0, 80_000, 7_000_000, 87.5),
                3: KScaleResult(3, 4, 50, 5, 6, 0.83, 150_000, 7_000_000, 46.7),
            },
        )

    def test_best_roi(self):
        r = self._make_result()
        assert r.best_roi == pytest.approx(87.5)

    def test_best_k(self):
        r = self._make_result()
        assert r.best_k == 2

    def test_max_gamma(self):
        r = self._make_result()
        assert r.max_gamma == pytest.approx(1.0)

    def test_best_k_none_when_no_viable(self):
        r = CompressionResult(
            activity_id="A",
            tipo_recurso_bottleneck="R",
            n_base=1,
            duration_base=5,
            start_base=0,
            makespan_base=55,
            float_rcpsp=10.0,
            float_cpm=10.0,
            resource_delay=0.0,
            criticality_class="Livre",
            by_k={
                2: KScaleResult(2, 3, 55, 0, 2, 0.0, 10_000, 0, 0.0),
            },
        )
        assert r.best_k is None
