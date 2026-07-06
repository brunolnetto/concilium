"""ADR-110 — TDD: detector de oportunidades de compartilhamento paralelo.

Todos os testes escritos ANTES da implementação (fase red).

Cobertura:
  _cpm_early_start             — forward pass CPM sem recursos
  _detectar_oportunidades_paralelo — detector pós-RCPSP
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

from concilium.application.scheduling.models import (
    Activity,
    ActivityDAG,
    ResourcePool,
    ScheduledActivity,
    ScheduleMetrics,
    ScheduleOutput,
)

_HELPERS_PRE = (
    Path(__file__).parent.parent.parent
    / "src/concilium/application/skills/manifests/05-equipes-e-alocacao/_skill_helpers_pre.py"
)


def _load_helpers_pre() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_skill_helpers_pre", _HELPERS_PRE)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_skill_helpers_pre"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


@pytest.fixture(scope="module")
def helpers():
    return _load_helpers_pre()


# ─────────────────────────────────────────────────────────────────────────────
# Factories
# ─────────────────────────────────────────────────────────────────────────────


def _metrics() -> ScheduleMetrics:
    return ScheduleMetrics(
        makespan=0,
        resource_leveling_score=1.0,
        idle_time=0,
        activity_fragmentation=0,
        critical_path_slack_min=0.0,
        resource_utilization_avg=1.0,
    )


def _sched(activities: list[ScheduledActivity], makespan: int) -> ScheduleOutput:
    return ScheduleOutput(
        scheduled_activities=activities,
        makespan=makespan,
        feasible=True,
        metrics=_metrics(),
        heuristic="TEST",
    )


def _act(aid: str, dur: int, res: dict[str, int]) -> Activity:
    return Activity(activity_id=aid, description=aid, duration_weeks=dur, required_resources=res)


def _sa(aid: str, start: int, dur: int, res: dict[str, int]) -> ScheduledActivity:
    return ScheduledActivity(
        activity_id=aid,
        start_week=start,
        end_week=start + dur,
        duration_weeks=dur,
        assigned_resources=res,
    )


def _dag(activities: list[Activity], edges: list[tuple[str, str]] | None = None) -> ActivityDAG:
    return ActivityDAG(activities=activities, precedence=edges or [])


def _pool(res: dict[str, int]) -> ResourcePool:
    return ResourcePool(resources=res)


_COSTS_ESC = {
    "ESC-22T": {
        "custo_mob_unit": 50_000.0,
        "custo_demob_unit": 30_000.0,
        "custo_idle_semanal_unit": 5_000.0,
        "custo_contrato_semana_unit": 20_000.0,
        "unidade_faturamento": "mes",
    }
}


# ─────────────────────────────────────────────────────────────────────────────
# 1. _cpm_early_start
# ─────────────────────────────────────────────────────────────────────────────


class TestCpmEarlyStart:
    """_cpm_early_start(dag) → {activity_id: ES}"""

    def test_atividade_isolada_es_zero(self, helpers):
        a = _act("A", 4, {})
        dag = _dag([a])
        es = helpers._cpm_early_start(dag)
        assert es["A"] == 0

    def test_sequencia_linear_es_acumulado(self, helpers):
        a, b, c = _act("A", 3, {}), _act("B", 5, {}), _act("C", 2, {})
        dag = _dag([a, b, c], [("A", "B"), ("B", "C")])
        es = helpers._cpm_early_start(dag)
        assert es["A"] == 0
        assert es["B"] == 3  # após A (dur=3)
        assert es["C"] == 8  # após B (dur=5)

    def test_convergencia_usa_maximo(self, helpers):
        """C depende de A e B; ES(C) = max(EF(A), EF(B))."""
        a, b, c = _act("A", 4, {}), _act("B", 6, {}), _act("C", 2, {})
        dag = _dag([a, b, c], [("A", "C"), ("B", "C")])
        es = helpers._cpm_early_start(dag)
        assert es["C"] == 6  # EF(B)=6 > EF(A)=4

    def test_paralelas_sem_predecessores_es_zero(self, helpers):
        a, b = _act("A", 3, {}), _act("B", 5, {})
        dag = _dag([a, b])
        es = helpers._cpm_early_start(dag)
        assert es["A"] == 0
        assert es["B"] == 0

    def test_convergencia_segundo_predecessor_nao_sobrescreve(self, helpers):
        """Quando o EF do segundo predecessor processado é menor que o já
        registrado, ES(C) não é sobrescrito (branch 431->430 false)."""
        # A (dur=6) é processado primeiro (ordem de dag.activities) → ES(C)=6.
        # B (dur=4) processado depois: EF(B)=4 <= ES(C) atual (6) → não sobrescreve.
        a, b, c = _act("A", 6, {}), _act("B", 4, {}), _act("C", 2, {})
        dag = _dag([a, b, c], [("A", "C"), ("B", "C")])
        es = helpers._cpm_early_start(dag)
        assert es["C"] == 6


class TestGapCobertoPorRecurso:
    """_gap_coberto_por_recurso(sched, tipo_id, t_start, t_end) → bool"""

    def test_gap_vazio_retorna_true(self, helpers):
        sched = _sched([], 0)
        assert helpers._gap_coberto_por_recurso(sched, "ESC-22T", 4, 4) is True

    def test_atividade_de_outro_tipo_e_ignorada(self, helpers):
        """Atividade que não usa tipo_id não contribui para cobertura
        (branch 458->457 false: `if sa.assigned_resources.get(tipo_id, 0) > 0` falso)."""
        sched = _sched([_sa("X", 0, 4, {"OUTRO-TIPO": 1})], 4)
        assert helpers._gap_coberto_por_recurso(sched, "ESC-22T", 0, 4) is False

    def test_gap_coberto_por_atividade_do_mesmo_tipo(self, helpers):
        sched = _sched([_sa("X", 0, 4, {"ESC-22T": 1})], 4)
        assert helpers._gap_coberto_por_recurso(sched, "ESC-22T", 0, 4) is True


class TestCpmLateFinish:
    """_cpm_late_finish(dag, makespan) → {activity_id: LF}"""

    def test_folha_lf_igual_makespan(self, helpers):
        a = _act("A", 4, {})
        dag = _dag([a])
        lf = helpers._cpm_late_finish(dag, makespan=10)
        assert lf["A"] == 10

    def test_segundo_sucessor_nao_sobrescreve_quando_maior(self, helpers):
        """A tem dois sucessores folha C (dur=5) e B (dur=3), ambos com
        LF=makespan=10. dag.successors(A) retorna [C, B] (ordem de precedence);
        C é processado primeiro (LS=5) e reduz LF(A); B (LS=7) não sobrescreve
        pois 7 não é menor que o LF(A)=5 já definido (branch 447->445 false)."""
        a, b, c = _act("A", 2, {}), _act("B", 3, {}), _act("C", 5, {})
        dag = _dag([a, b, c], [("A", "C"), ("A", "B")])
        lf = helpers._cpm_late_finish(dag, makespan=10)
        assert lf["A"] == 5  # min(LS(C)=10-5=5, LS(B)=10-3=7) = 5


# ─────────────────────────────────────────────────────────────────────────────
# 2. _detectar_oportunidades_paralelo — critérios de candidatura
# ─────────────────────────────────────────────────────────────────────────────


class TestCriteriosCandidatura:
    """Testa os quatro critérios de §D1 do ADR-110."""

    def test_par_serializado_por_escassez_detectado(self, helpers):
        """Pool=1, sem precedência lógica, adjacentes → candidato."""
        a, b = _act("A", 4, {"ESC-22T": 1}), _act("B", 4, {"ESC-22T": 1})
        dag = _dag([a, b])  # sem aresta
        pool = _pool({"ESC-22T": 1})
        # Solver serializou: A[0,4) B[4,8)
        sched = _sched([_sa("A", 0, 4, {"ESC-22T": 1}), _sa("B", 4, 4, {"ESC-22T": 1})], 8)
        result = helpers._detectar_oportunidades_paralelo(sched, dag, pool, _COSTS_ESC, custo_indireto_semana=0.0)
        assert len(result) == 1
        opp = result[0]
        assert {opp.atividade_i, opp.atividade_j} == {"A", "B"}
        assert opp.tipo_recurso_id == "ESC-22T"

    def test_par_com_precedencia_logica_ignorado(self, helpers):
        """Pool=1 mas aresta A→B existe: serialização é lógica, não escassez."""
        a, b = _act("A", 4, {"ESC-22T": 1}), _act("B", 4, {"ESC-22T": 1})
        dag = _dag([a, b], [("A", "B")])  # precedência lógica
        pool = _pool({"ESC-22T": 1})
        sched = _sched([_sa("A", 0, 4, {"ESC-22T": 1}), _sa("B", 4, 4, {"ESC-22T": 1})], 8)
        result = helpers._detectar_oportunidades_paralelo(sched, dag, pool, _COSTS_ESC, custo_indireto_semana=0.0)
        assert result == []

    def test_par_com_pool_2_ignorado(self, helpers):
        """Pool=2: as duas atividades já poderiam rodar em paralelo; não há escassez."""
        a, b = _act("A", 4, {"ESC-22T": 1}), _act("B", 4, {"ESC-22T": 1})
        dag = _dag([a, b])
        pool = _pool({"ESC-22T": 2})  # pool suficiente
        sched = _sched([_sa("A", 0, 4, {"ESC-22T": 1}), _sa("B", 4, 4, {"ESC-22T": 1})], 8)
        result = helpers._detectar_oportunidades_paralelo(sched, dag, pool, _COSTS_ESC, custo_indireto_semana=0.0)
        assert result == []

    def test_sem_gap_entre_atividades_nao_adjacentes_ignorado(self, helpers):
        """A e B com gap de 2 semanas: não foram serializadas back-to-back pelo solver."""
        a, b = _act("A", 4, {"ESC-22T": 1}), _act("B", 4, {"ESC-22T": 1})
        dag = _dag([a, b])
        pool = _pool({"ESC-22T": 1})
        # Gap de 2 semanas entre elas → não foi escassez imediata
        sched = _sched([_sa("A", 0, 4, {"ESC-22T": 1}), _sa("B", 6, 4, {"ESC-22T": 1})], 10)
        result = helpers._detectar_oportunidades_paralelo(sched, dag, pool, _COSTS_ESC, custo_indireto_semana=0.0)
        assert result == []

    def test_par_sem_cpf_slack_suficiente_ignorado(self, helpers):
        """A e B back-to-back mas A tem folga CPM = 0: no window para estender duração."""
        # A e B são paralelas CPM (sem predecessor), mas C depende de A e começa
        # exatamente em EF(A) — A não tem slack.
        a = _act("A", 4, {"ESC-22T": 1})
        b = _act("B", 4, {"ESC-22T": 1})
        c = _act("C", 2, {})
        # C depende de A → EF(A)=4, A.slack = scheduled_start(A) - ES(A) = 0 - 0 = 0
        dag = _dag([a, b, c], [("A", "C")])
        pool = _pool({"ESC-22T": 1})
        # Solver: A[0,4), B[4,8), C[4,6)  — A tem slack=0, B tem slack=4
        sched = _sched(
            [_sa("A", 0, 4, {"ESC-22T": 1}), _sa("B", 4, 4, {"ESC-22T": 1}), _sa("C", 4, 2, {})],
            makespan=8,
        )
        result = helpers._detectar_oportunidades_paralelo(sched, dag, pool, _COSTS_ESC, custo_indireto_semana=0.0)
        # A tem slack=0 (schedulado em ES=0) → par descartado
        assert result == []

    def test_par_com_sucessor_com_folga_suficiente_aceito(self, helpers):
        """A tem sucessor C com float suficiente (tf_succ >= delay) → não rejeitado
        (branch 561->556 false: loop continua sem marcar `rejeitado`)."""
        a = _act("A", 4, {"ESC-22T": 1})
        b = _act("B", 4, {"ESC-22T": 1})
        c = _act("C", 1, {})
        # C depende de A; makespan bem maior que o necessário dá folga generosa a C.
        dag = _dag([a, b, c], [("A", "C")])
        pool = _pool({"ESC-22T": 1})
        sched = _sched(
            [_sa("A", 0, 4, {"ESC-22T": 1}), _sa("B", 4, 4, {"ESC-22T": 1})],
            makespan=30,
        )
        result = helpers._detectar_oportunidades_paralelo(sched, dag, pool, _COSTS_ESC, custo_indireto_semana=0.0)
        # C tem folga ampla (makespan=30 vs EF(A)=4) → delay de A não viola seu float → aceito
        assert len(result) == 1
        assert {result[0].atividade_i, result[0].atividade_j} == {"A", "B"}


# ─────────────────────────────────────────────────────────────────────────────
# 3. Cálculo do balanço custo × prazo
# ─────────────────────────────────────────────────────────────────────────────


class TestBalancoCustoPrazo:
    """Testa o cálculo de delta_* para candidatos válidos."""

    def test_recurso_gargalo_iguais_delta_makespan_zero(self, helpers):
        """d_i = d_j = 4, gargalo: calendar_paralelo = max(8,8) = 8 = serial(8) → delta=0."""
        a, b = _act("A", 4, {"ESC-22T": 1}), _act("B", 4, {"ESC-22T": 1})
        dag = _dag([a, b])
        pool = _pool({"ESC-22T": 1})
        sched = _sched([_sa("A", 0, 4, {"ESC-22T": 1}), _sa("B", 4, 4, {"ESC-22T": 1})], 8)
        result = helpers._detectar_oportunidades_paralelo(
            sched,
            dag,
            pool,
            _COSTS_ESC,
            custo_indireto_semana=10_000.0,
            limite_producao_por_tipo={"ESC-22T": "equipamento"},
        )
        assert len(result) == 1
        opp = result[0]
        assert opp.recurso_e_gargalo is True
        assert opp.delta_makespan_semanas == 0

    def test_recurso_gargalo_diferentes_delta_makespan_diferenca(self, helpers):
        """d_i=3, d_j=5, gargalo: calendar_paralelo=max(6,10)=10, serial=8 → delta=2."""
        a, b = _act("A", 3, {"ESC-22T": 1}), _act("B", 5, {"ESC-22T": 1})
        dag = _dag([a, b])
        pool = _pool({"ESC-22T": 1})
        # Solver serializa B então A (B mais longo primeiro — LPT)
        sched = _sched([_sa("B", 0, 5, {"ESC-22T": 1}), _sa("A", 5, 3, {"ESC-22T": 1})], 8)
        result = helpers._detectar_oportunidades_paralelo(
            sched,
            dag,
            pool,
            _COSTS_ESC,
            custo_indireto_semana=0.0,
            limite_producao_por_tipo={"ESC-22T": "equipamento"},
        )
        assert len(result) == 1
        assert result[0].delta_makespan_semanas == 2  # max(10,6) - 8 = 2

    def test_recurso_suporte_delta_makespan_zero(self, helpers):
        """Recurso de suporte: duração não muda → delta_makespan=0."""
        a, b = _act("A", 4, {"PIPA": 1}), _act("B", 4, {"PIPA": 1})
        dag = _dag([a, b])
        pool = _pool({"PIPA": 1})
        costs = {
            "PIPA": {
                "custo_mob_unit": 10_000.0,
                "custo_demob_unit": 5_000.0,
                "custo_idle_semanal_unit": 1_000.0,
                "custo_contrato_semana_unit": 3_000.0,
                "unidade_faturamento": "mes",
            }
        }
        sched = _sched([_sa("A", 0, 4, {"PIPA": 1}), _sa("B", 4, 4, {"PIPA": 1})], 8)
        result = helpers._detectar_oportunidades_paralelo(
            sched,
            dag,
            pool,
            costs,
            custo_indireto_semana=10_000.0,
            limite_producao_por_tipo={"PIPA": "mao_obra"},
        )
        assert len(result) == 1
        opp = result[0]
        assert opp.recurso_e_gargalo is False
        assert opp.delta_makespan_semanas == 0

    def test_delta_custo_frota_proporcional_ao_contrato(self, helpers):
        """delta_custo_frota = custo_contrato_semana × semanas_sobreposicao."""
        # Sobreposição = max(d_i, d_j) semanas = 4 (igual). custo_contrato = 20k/sem
        a, b = _act("A", 4, {"ESC-22T": 1}), _act("B", 4, {"ESC-22T": 1})
        dag = _dag([a, b])
        pool = _pool({"ESC-22T": 1})
        sched = _sched([_sa("A", 0, 4, {"ESC-22T": 1}), _sa("B", 4, 4, {"ESC-22T": 1})], 8)
        result = helpers._detectar_oportunidades_paralelo(sched, dag, pool, _COSTS_ESC, custo_indireto_semana=0.0)
        assert len(result) == 1
        # custo_contrato_semana_unit=20_000 × 4 semanas = 80_000
        assert result[0].delta_custo_frota == pytest.approx(80_000.0)

    def test_delta_liquido_positivo_e_viavel(self, helpers):
        """delta_custo_frota > delta_indiretos → delta_liquido > 0 → viável."""
        a, b = _act("A", 4, {"ESC-22T": 1}), _act("B", 4, {"ESC-22T": 1})
        dag = _dag([a, b])
        pool = _pool({"ESC-22T": 1})
        sched = _sched([_sa("A", 0, 4, {"ESC-22T": 1}), _sa("B", 4, 4, {"ESC-22T": 1})], 8)
        # d_i=d_j=4, gargalo, delta_makespan=0 → delta_indiretos=0
        # delta_custo_frota = 80_000 → delta_liquido = 80_000 > 0
        result = helpers._detectar_oportunidades_paralelo(
            sched,
            dag,
            pool,
            _COSTS_ESC,
            custo_indireto_semana=10_000.0,
            limite_producao_por_tipo={"ESC-22T": "equipamento"},
        )
        assert result[0].delta_liquido == pytest.approx(80_000.0)
        assert result[0].economicamente_viavel is True

    def test_delta_liquido_negativo_nao_viavel(self, helpers):
        """delta_indiretos > delta_custo_frota → delta_liquido < 0 → não viável."""
        # d_i=2, d_j=6 → gargalo → delta_makespan = max(4,12) - 8 = 4 semanas
        # delta_indiretos = 4 × 100_000 = 400_000
        # delta_custo_frota = 20_000 × 6 = 120_000 (max(d_i,d_j)=6)
        # delta_liquido = 120_000 - 400_000 < 0
        a, b = _act("A", 2, {"ESC-22T": 1}), _act("B", 6, {"ESC-22T": 1})
        dag = _dag([a, b])
        pool = _pool({"ESC-22T": 1})
        sched = _sched([_sa("A", 0, 2, {"ESC-22T": 1}), _sa("B", 2, 6, {"ESC-22T": 1})], 8)
        result = helpers._detectar_oportunidades_paralelo(
            sched,
            dag,
            pool,
            _COSTS_ESC,
            custo_indireto_semana=100_000.0,
            limite_producao_por_tipo={"ESC-22T": "equipamento"},
        )
        assert len(result) == 1
        assert result[0].delta_liquido < 0
        assert result[0].economicamente_viavel is False


# ─────────────────────────────────────────────────────────────────────────────
# 4. Múltiplos pares e tipos
# ─────────────────────────────────────────────────────────────────────────────


class TestMultiplosPares:
    def test_tres_atividades_gera_tres_pares(self, helpers):
        """A, B, C — mesmo recurso, sem precedências → 3 pares candidatos."""
        acts = [_act("A", 3, {"ESC-22T": 1}), _act("B", 3, {"ESC-22T": 1}), _act("C", 3, {"ESC-22T": 1})]
        dag = _dag(acts)
        pool = _pool({"ESC-22T": 1})
        sched = _sched(
            [_sa("A", 0, 3, {"ESC-22T": 1}), _sa("B", 3, 3, {"ESC-22T": 1}), _sa("C", 6, 3, {"ESC-22T": 1})],
            makespan=9,
        )
        result = helpers._detectar_oportunidades_paralelo(sched, dag, pool, _COSTS_ESC, custo_indireto_semana=0.0)
        assert len(result) == 3
        pares = [{r.atividade_i, r.atividade_j} for r in result]
        assert {"A", "B"} in pares
        assert {"B", "C"} in pares
        assert {"A", "C"} in pares

    def test_tipos_distintos_geram_oportunidades_separadas(self, helpers):
        """A usa ESC + PIPA, B usa ESC + PIPA → 2 oportunidades (uma por tipo)."""
        a = _act("A", 4, {"ESC-22T": 1, "PIPA": 1})
        b = _act("B", 4, {"ESC-22T": 1, "PIPA": 1})
        dag = _dag([a, b])
        pool = _pool({"ESC-22T": 1, "PIPA": 1})
        costs = {
            **_COSTS_ESC,
            "PIPA": {
                "custo_mob_unit": 5_000.0,
                "custo_demob_unit": 2_000.0,
                "custo_idle_semanal_unit": 500.0,
                "custo_contrato_semana_unit": 2_000.0,
                "unidade_faturamento": "mes",
            },
        }
        sched = _sched(
            [_sa("A", 0, 4, {"ESC-22T": 1, "PIPA": 1}), _sa("B", 4, 4, {"ESC-22T": 1, "PIPA": 1})],
            makespan=8,
        )
        result = helpers._detectar_oportunidades_paralelo(sched, dag, pool, costs, custo_indireto_semana=0.0)
        tipos = {r.tipo_recurso_id for r in result}
        assert tipos == {"ESC-22T", "PIPA"}

    def test_recurso_sem_resource_costs_ignorado(self, helpers):
        """Tipo não listado em resource_costs não gera oportunidade."""
        a, b = _act("A", 4, {"MOTOR": 1}), _act("B", 4, {"MOTOR": 1})
        dag = _dag([a, b])
        pool = _pool({"MOTOR": 1})
        sched = _sched([_sa("A", 0, 4, {"MOTOR": 1}), _sa("B", 4, 4, {"MOTOR": 1})], 8)
        result = helpers._detectar_oportunidades_paralelo(
            sched,
            dag,
            pool,
            _COSTS_ESC,  # MOTOR não está em _COSTS_ESC
            custo_indireto_semana=0.0,
        )
        assert result == []

    def test_sem_atividades_retorna_vazio(self, helpers):
        sched = _sched([], 0)
        dag = _dag([])
        pool = _pool({})
        result = helpers._detectar_oportunidades_paralelo(sched, dag, pool, {}, 0.0)
        assert result == []
