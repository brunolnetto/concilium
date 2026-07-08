"""ADR-128 D2 — Restrição de disponibilidade de recursos consumíveis no motor RCPSP: TDD.

Cobre:
  - `ReplenishableResource`: modelo paralelo a `ResourcePool`, com semântica de fluxo/estoque.
  - `project_estoque_semanal`: projeção `estoque[t] = estoque[t-1] + reabastecimento[t] - consumo[t]`.
  - `has_estoque_negativo`: detecção de inviabilidade de estoque projetado.
  - `apply_replenishable_delay`: atraso da atividade consumidora até o reabastecimento
    acumulado tornar o consumo viável (ADR-128 D2).
  - Regressão zero: `CpSatScheduler.schedule()` sem `replenishable_resources` reproduz
    exatamente o comportamento atual.

Escrito antes da implementação (red phase).
"""

from __future__ import annotations

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
)
from concilium.domain.models.catalog.disponibilidade_consumivel import DisponibilidadeConsumivel

# ── project_estoque_semanal ───────────────────────────────────────────────────


class TestProjectEstoqueSemanal:
    def test_no_activities_returns_empty(self):
        resource = ReplenishableResource(
            resource_id="DIESEL",
            disponibilidade=DisponibilidadeConsumivel(estoque_inicial=100.0),
            consumo_por_semana={},
        )
        assert project_estoque_semanal(resource, []) == {}

    def test_stock_never_negative_when_sufficient(self):
        resource = ReplenishableResource(
            resource_id="DIESEL",
            disponibilidade=DisponibilidadeConsumivel(
                capacidade_armazenamento=1000.0, estoque_inicial=500.0, taxa_reabastecimento_max=0.0
            ),
            consumo_por_semana={"A1": 100.0},
        )
        scheduled = [ScheduledActivity("A1", start_week=0, end_week=3, duration_weeks=3)]
        niveis = project_estoque_semanal(resource, scheduled)
        # estoque[0]=500-100=400; estoque[1]=400-100=300; estoque[2]=300-100=200
        assert niveis == {0: 400.0, 1: 300.0, 2: 200.0}
        assert not has_estoque_negativo(niveis)

    def test_stock_goes_negative_without_enough_replenishment(self):
        resource = ReplenishableResource(
            resource_id="DIESEL",
            disponibilidade=DisponibilidadeConsumivel(estoque_inicial=0.0, taxa_reabastecimento_max=10.0),
            consumo_por_semana={"A1": 30.0},
        )
        scheduled = [ScheduledActivity("A1", start_week=0, end_week=1, duration_weeks=1)]
        niveis = project_estoque_semanal(resource, scheduled)
        # estoque[0] = 0 + 10 (reabastecimento) - 30 (consumo) = -20
        assert niveis[0] == -20.0
        assert has_estoque_negativo(niveis)

    def test_replenishment_capped_by_capacidade_armazenamento(self):
        resource = ReplenishableResource(
            resource_id="DIESEL",
            disponibilidade=DisponibilidadeConsumivel(
                capacidade_armazenamento=50.0, estoque_inicial=45.0, taxa_reabastecimento_max=100.0
            ),
            consumo_por_semana={"A1": 20.0},
        )
        scheduled = [ScheduledActivity("A1", start_week=0, end_week=1, duration_weeks=1)]
        niveis = project_estoque_semanal(resource, scheduled)
        # reabastecimento levaria a 145, mas é limitado à capacidade (50); depois consome 20 -> 30
        assert niveis[0] == 30.0


# ── apply_replenishable_delay ─────────────────────────────────────────────────


class TestApplyReplenishableDelay:
    def test_delays_activity_until_stock_accumulates(self):
        """Sem estoque inicial e taxa de reabastecimento baixa, a atividade precisa esperar
        o reabastecimento acumular o suficiente para viabilizar o consumo (D2)."""
        resource = ReplenishableResource(
            resource_id="DIESEL",
            disponibilidade=DisponibilidadeConsumivel(estoque_inicial=0.0, taxa_reabastecimento_max=10.0),
            consumo_por_semana={"A1": 30.0},
        )
        scheduled = [ScheduledActivity("A1", start_week=0, end_week=1, duration_weeks=1)]
        result = apply_replenishable_delay(scheduled, resource)
        act = next(sa for sa in result if sa.activity_id == "A1")
        # estoque acumulado (sem consumo) até a semana t (inclusive): 10*(t+1);
        # precisa 10*(t+1) >= 30 -> t>=2 (em t=2, nível chega a exatamente 0, viável)
        assert act.start_week == 2
        assert act.end_week == 3
        niveis = project_estoque_semanal(resource, result)
        assert not has_estoque_negativo(niveis)

    def test_no_delay_needed_when_stock_sufficient(self):
        resource = ReplenishableResource(
            resource_id="DIESEL",
            disponibilidade=DisponibilidadeConsumivel(estoque_inicial=500.0),
            consumo_por_semana={"A1": 100.0},
        )
        scheduled = [ScheduledActivity("A1", start_week=0, end_week=2, duration_weeks=2)]
        result = apply_replenishable_delay(scheduled, resource)
        act = next(sa for sa in result if sa.activity_id == "A1")
        assert act.start_week == 0
        assert act.end_week == 2

    def test_activity_not_consuming_resource_is_untouched(self):
        resource = ReplenishableResource(
            resource_id="DIESEL",
            disponibilidade=DisponibilidadeConsumivel(estoque_inicial=0.0, taxa_reabastecimento_max=10.0),
            consumo_por_semana={"A1": 30.0},
        )
        scheduled = [
            ScheduledActivity("A1", start_week=0, end_week=1, duration_weeks=1),
            ScheduledActivity("A2", start_week=0, end_week=1, duration_weeks=1),
        ]
        result = apply_replenishable_delay(scheduled, resource)
        act2 = next(sa for sa in result if sa.activity_id == "A2")
        assert act2.start_week == 0
        assert act2.end_week == 1


# ── Regressão zero: CpSatScheduler sem replenishable_resources ───────────────


class TestCpSatSchedulerReplenishableRegressionZero:
    def test_default_behaviour_unchanged_without_replenishable_resources(self):
        acts = [Activity(activity_id="A", description="", duration_weeks=4, required_resources={"E": 2})]
        dag = ActivityDAG(activities=acts, precedence=[])
        pool = ResourcePool(resources={"E": 10})
        scheduler = CpSatScheduler(timeout_seconds=10.0)

        baseline = scheduler.schedule(dag, pool)
        with_none = scheduler.schedule(dag, pool, replenishable_resources=None)

        assert baseline.makespan == with_none.makespan
        assert baseline.feasible == with_none.feasible
        assert [sa.start_week for sa in baseline.scheduled_activities] == [
            sa.start_week for sa in with_none.scheduled_activities
        ]

    def test_replenishable_resource_delays_activity_end_to_end(self):
        acts = [Activity(activity_id="A", description="", duration_weeks=1, required_resources={})]
        dag = ActivityDAG(activities=acts, precedence=[])
        pool = ResourcePool(resources={})
        scheduler = CpSatScheduler(timeout_seconds=10.0)

        resource = ReplenishableResource(
            resource_id="DIESEL",
            disponibilidade=DisponibilidadeConsumivel(estoque_inicial=0.0, taxa_reabastecimento_max=10.0),
            consumo_por_semana={"A": 30.0},
        )
        result = scheduler.schedule(dag, pool, replenishable_resources=[resource])
        act = next(sa for sa in result.scheduled_activities if sa.activity_id == "A")
        assert act.start_week >= 2
        assert result.makespan >= act.end_week


class TestCpSatSchedulerReplenishableRevalidation:
    """Comentário do Copilot (PR #67): o reparo por atraso não repropaga para
    sucessores — a revalidação pós-reparo deve marcar `feasible=False` quando isso
    quebra uma precedência FS que o CP-SAT havia garantido na solução original."""

    def test_delay_that_breaks_fs_precedence_marks_infeasible(self):
        acts = [
            Activity(activity_id="A", description="", duration_weeks=1, required_resources={}),
            Activity(activity_id="B", description="", duration_weeks=1, required_resources={}),
        ]
        # FS estrita, sem folga: start(B) >= end(A) — o CP-SAT resolve isso com
        # A=[0,1) e B=[1,2), sem espaço para A atrasar sem violar a precedência.
        dag = ActivityDAG(activities=acts, precedence=[("A", "B")])
        pool = ResourcePool(resources={})
        scheduler = CpSatScheduler(timeout_seconds=10.0)

        resource = ReplenishableResource(
            resource_id="DIESEL",
            disponibilidade=DisponibilidadeConsumivel(estoque_inicial=0.0, taxa_reabastecimento_max=10.0),
            consumo_por_semana={"A": 30.0},  # força ao menos 1 semana de atraso em A
        )
        result = scheduler.schedule(dag, pool, replenishable_resources=[resource])

        act_a = next(sa for sa in result.scheduled_activities if sa.activity_id == "A")
        act_b = next(sa for sa in result.scheduled_activities if sa.activity_id == "B")
        assert act_a.end_week > act_b.start_week  # precedência FS de fato quebrada
        assert result.feasible is False
