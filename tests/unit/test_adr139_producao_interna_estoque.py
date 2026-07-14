"""ADR-139 F3 — Produção interna no balanço de estoque do RCPSP: TDD.

Cobre:
  - D4: `ReplenishableResource.producao_por_semana` (activity_id → taxa gerada por
    semana ativa da produtora), com a mesma validação fail-loud de `consumo_por_semana`.
  - D4: balanço `estoque[t] = estoque[t-1] + reabastecimento_externo[t] +
    producao_interna[t] − consumo[t]` em `project_estoque_semanal`.
  - D4: recurso 100% interno (`taxa_reabastecimento_max=None`) — consumidora agendada
    cedo demais recebe delay até a produção acumulada viabilizar o consumo.
  - VAL-ESTOQUE-CAP-01 (AVISO): produção projetada acima de `capacidade_armazenamento`
    (excedente descartado — pilha/bota-espera limitada), sem gerar delay.
  - VAL-ESTOQUE-PROD-01 (ERRO): `producao_por_semana` referenciando atividade fora do DAG.
  - Convergência do laço de ponto fixo (Fase 2b) com cadeia produtora→consumidora
    também ligada por precedência.
  - Regressão zero: recurso sem `producao_por_semana` preserva o comportamento ADR-128.

Escrito antes da implementação (red phase).
"""

from __future__ import annotations

import pytest

from concilium.application.scheduling.cpsat_scheduler import CpSatScheduler
from concilium.application.scheduling.models import (
    Activity,
    ActivityDAG,
    ReplenishableResource,
    ResourcePool,
    ScheduledActivity,
)
from concilium.application.scheduling.replenishable import (
    apply_replenishable_delay,
    has_estoque_negativo,
    project_estoque_semanal,
    project_overflow_semanal,
    violation_estoque_acima_capacidade,
)
from concilium.domain.models.catalog.disponibilidade_consumivel import DisponibilidadeConsumivel


def _sa(activity_id: str, start: int, end: int) -> ScheduledActivity:
    return ScheduledActivity(
        activity_id=activity_id,
        start_week=start,
        end_week=end,
        duration_weeks=end - start,
    )


# ── D4: modelo ────────────────────────────────────────────────────────────────


class TestProducaoPorSemanaModelo:
    def test_default_dict_vazio(self):
        resource = ReplenishableResource(
            resource_id="MA-SOLO-CORTE",
            disponibilidade=DisponibilidadeConsumivel(estoque_inicial=0.0),
        )
        assert resource.producao_por_semana == {}

    @pytest.mark.parametrize("taxa", [-1.0, float("nan"), float("inf")])
    def test_taxa_invalida_falha_alto(self, taxa):
        with pytest.raises(ValueError, match="producao_por_semana"):
            ReplenishableResource(
                resource_id="MA-SOLO-CORTE",
                disponibilidade=DisponibilidadeConsumivel(estoque_inicial=0.0),
                producao_por_semana={"corte": taxa},
            )


# ── D4: balanço com produção interna ─────────────────────────────────────────


class TestBalancoComProducaoInterna:
    def test_producao_acumula_enquanto_produtora_ativa(self):
        resource = ReplenishableResource(
            resource_id="MA-SOLO-CORTE",
            disponibilidade=DisponibilidadeConsumivel(estoque_inicial=0.0),
            producao_por_semana={"corte": 10.0},
        )
        niveis = project_estoque_semanal(resource, [_sa("corte", 0, 4)])
        assert niveis == {0: 10.0, 1: 20.0, 2: 30.0, 3: 40.0}

    def test_producao_para_quando_produtora_termina(self):
        resource = ReplenishableResource(
            resource_id="MA-SOLO-CORTE",
            disponibilidade=DisponibilidadeConsumivel(estoque_inicial=0.0),
            producao_por_semana={"corte": 10.0},
            consumo_por_semana={"aterro": 10.0},
        )
        niveis = project_estoque_semanal(resource, [_sa("corte", 0, 2), _sa("aterro", 2, 5)])
        # t0/t1: produção sem consumo; t2..t4: só consumo.
        assert niveis == {0: 10.0, 1: 20.0, 2: 10.0, 3: 0.0, 4: -10.0}
        assert has_estoque_negativo(niveis)

    def test_producao_soma_com_reabastecimento_externo(self):
        resource = ReplenishableResource(
            resource_id="MA-BRITA",
            disponibilidade=DisponibilidadeConsumivel(estoque_inicial=0.0, taxa_reabastecimento_max=5.0),
            producao_por_semana={"usina": 10.0},
        )
        niveis = project_estoque_semanal(resource, [_sa("usina", 0, 2)])
        assert niveis == {0: 15.0, 1: 30.0}

    def test_sem_producao_comportamento_adr128_preservado(self):
        resource = ReplenishableResource(
            resource_id="DIESEL",
            disponibilidade=DisponibilidadeConsumivel(estoque_inicial=100.0, taxa_reabastecimento_max=10.0),
            consumo_por_semana={"escav": 30.0},
        )
        niveis = project_estoque_semanal(resource, [_sa("escav", 0, 3)])
        assert niveis == {0: 80.0, 1: 60.0, 2: 40.0}


# ── D4: reparo por delay com recurso 100% interno ─────────────────────────────


class TestDelayConsumidoraRecursoInterno:
    def test_consumidora_adiada_ate_producao_acumular(self):
        resource = ReplenishableResource(
            resource_id="MA-SOLO-CORTE",
            disponibilidade=DisponibilidadeConsumivel(estoque_inicial=0.0),
            producao_por_semana={"corte": 10.0},
            consumo_por_semana={"aterro": 20.0},
        )
        scheduled = [_sa("corte", 0, 4), _sa("aterro", 0, 2)]
        repaired = apply_replenishable_delay(scheduled, resource)
        by_id = {sa.activity_id: sa for sa in repaired}
        # Produtora não se move; consumidora adiada até s=2 (primeiro início viável).
        assert by_id["corte"].start_week == 0
        assert by_id["aterro"].start_week == 2
        niveis = project_estoque_semanal(resource, repaired)
        assert not has_estoque_negativo(niveis)

    def test_produtora_nunca_e_adiada(self):
        resource = ReplenishableResource(
            resource_id="MA-SOLO-CORTE",
            disponibilidade=DisponibilidadeConsumivel(estoque_inicial=0.0),
            producao_por_semana={"corte": 5.0},
            consumo_por_semana={"aterro": 50.0},
        )
        scheduled = [_sa("corte", 0, 2), _sa("aterro", 0, 1)]
        repaired = apply_replenishable_delay(scheduled, resource)
        by_id = {sa.activity_id: sa for sa in repaired}
        assert by_id["corte"].start_week == 0


# ── VAL-ESTOQUE-CAP-01: excedente sobre capacidade de armazenamento ───────────


class TestOverflowCapacidade:
    def _resource_com_pilha_limitada(self) -> ReplenishableResource:
        return ReplenishableResource(
            resource_id="MA-SOLO-CORTE",
            disponibilidade=DisponibilidadeConsumivel(estoque_inicial=0.0, capacidade_armazenamento=15.0),
            producao_por_semana={"corte": 10.0},
        )

    def test_overflow_detectado_por_semana(self):
        overflow = project_overflow_semanal(self._resource_com_pilha_limitada(), [_sa("corte", 0, 4)])
        assert overflow == {1: 5.0, 2: 10.0, 3: 10.0}

    def test_sem_capacidade_declarada_sem_overflow(self):
        resource = ReplenishableResource(
            resource_id="MA-SOLO-CORTE",
            disponibilidade=DisponibilidadeConsumivel(estoque_inicial=0.0),
            producao_por_semana={"corte": 10.0},
        )
        assert project_overflow_semanal(resource, [_sa("corte", 0, 4)]) == {}

    def test_violation_aviso_quando_ha_overflow(self):
        violation = violation_estoque_acima_capacidade(self._resource_com_pilha_limitada(), [_sa("corte", 0, 4)])
        assert violation is not None
        assert violation.code == "VAL-ESTOQUE-CAP-01"
        assert violation.status == "AVISO"

    def test_violation_none_sem_overflow(self):
        resource = ReplenishableResource(
            resource_id="DIESEL",
            disponibilidade=DisponibilidadeConsumivel(estoque_inicial=10.0, capacidade_armazenamento=100.0),
            consumo_por_semana={"escav": 1.0},
        )
        assert violation_estoque_acima_capacidade(resource, [_sa("escav", 0, 2)]) is None

    def test_overflow_nao_gera_delay(self):
        """Excedente é descartado (AVISO), não é motivo de reparo de cronograma."""
        resource = self._resource_com_pilha_limitada()
        scheduled = [_sa("corte", 0, 4)]
        repaired = apply_replenishable_delay(scheduled, resource)
        assert [(sa.start_week, sa.end_week) for sa in repaired] == [(0, 4)]


# ── VAL-ESTOQUE-PROD-01 + integração CP-SAT ───────────────────────────────────


def _dag_corte_aterro(precedence: bool = False) -> ActivityDAG:
    activities = [
        Activity(activity_id="corte", description="Corte", duration_weeks=4, required_resources={"EQ": 1}),
        Activity(activity_id="aterro", description="Aterro", duration_weeks=2, required_resources={"EQ": 1}),
    ]
    return ActivityDAG(activities=activities, precedence=[("corte", "aterro")] if precedence else [])


class TestIntegracaoCpSat:
    def test_val_estoque_prod_01_atividade_fora_do_dag(self):
        resource = ReplenishableResource(
            resource_id="MA-SOLO-CORTE",
            disponibilidade=DisponibilidadeConsumivel(estoque_inicial=0.0),
            producao_por_semana={"fantasma": 10.0},
        )
        scheduler = CpSatScheduler(horizon_weeks=20, timeout_seconds=5)
        with pytest.raises(ValueError, match="VAL-ESTOQUE-PROD-01"):
            scheduler.schedule(
                _dag_corte_aterro(), ResourcePool(resources={"EQ": 2}), replenishable_resources=[resource]
            )

    def test_ponto_fixo_converge_produtora_consumidora(self):
        resource = ReplenishableResource(
            resource_id="MA-SOLO-CORTE",
            disponibilidade=DisponibilidadeConsumivel(estoque_inicial=0.0),
            producao_por_semana={"corte": 10.0},
            consumo_por_semana={"aterro": 20.0},
        )
        scheduler = CpSatScheduler(horizon_weeks=20, timeout_seconds=10)
        output = scheduler.schedule(
            _dag_corte_aterro(), ResourcePool(resources={"EQ": 2}), replenishable_resources=[resource]
        )
        assert output.feasible
        niveis = project_estoque_semanal(resource, output.scheduled_activities)
        assert not has_estoque_negativo(niveis)

    def test_ponto_fixo_converge_com_precedencia_encadeada(self):
        resource = ReplenishableResource(
            resource_id="MA-SOLO-CORTE",
            disponibilidade=DisponibilidadeConsumivel(estoque_inicial=0.0),
            producao_por_semana={"corte": 10.0},
            consumo_por_semana={"aterro": 20.0},
        )
        scheduler = CpSatScheduler(horizon_weeks=20, timeout_seconds=10)
        output = scheduler.schedule(
            _dag_corte_aterro(precedence=True),
            ResourcePool(resources={"EQ": 2}),
            replenishable_resources=[resource],
        )
        assert output.feasible
        by_id = {sa.activity_id: sa for sa in output.scheduled_activities}
        assert by_id["aterro"].start_week >= by_id["corte"].end_week
        niveis = project_estoque_semanal(resource, output.scheduled_activities)
        assert not has_estoque_negativo(niveis)


# ── Catálogo de códigos de validação ──────────────────────────────────────────


class TestValidationCodes:
    def test_codigos_adr139_registrados(self):
        from concilium.domain.validations.catalog import ValidationCode

        assert ValidationCode.VAL_ESTOQUE_PROD_01.value == "VAL-ESTOQUE-PROD-01"
        assert ValidationCode.VAL_ESTOQUE_CAP_01.value == "VAL-ESTOQUE-CAP-01"
