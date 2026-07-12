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
from concilium.application.scheduling.precedence_repropagation import repropagate_precedence_delays
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
    """ADR-128 Fase 2b: o reparo por atraso agora repropaga o deslocamento para
    sucessores no DAG de precedências (`repropagate_precedence_delays`), fechando a
    lacuna original apontada pelo Copilot (PR #67) — uma precedência FS que o
    reparo de estoque quebraria sozinho passa a ser corrigida por uma segunda
    passada, e o cronograma final é `feasible=True` em vez de descartado."""

    def test_delay_that_would_break_fs_precedence_is_repropagated_and_feasible(self):
        acts = [
            Activity(activity_id="A", description="", duration_weeks=1, required_resources={}),
            Activity(activity_id="B", description="", duration_weeks=1, required_resources={}),
        ]
        # FS estrita, sem folga: start(B) >= end(A) — sem repropagação (Fase 2 original),
        # o CP-SAT resolve isso com A=[0,1) e B=[1,2), e o reparo de estoque atrasando A
        # sozinho quebraria essa precedência. Com Fase 2b, B é empurrado junto.
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
        assert act_a.start_week == 2 and act_a.end_week == 3  # atraso de estoque em A
        assert act_b.start_week >= act_a.end_week  # precedência FS preservada (repropagada)
        assert act_b.start_week == 3 and act_b.end_week == 4
        assert result.feasible is True

    def test_delay_cascades_transitively_through_chain_a_b_c(self):
        """A→B→C: atrasar A (estoque) deve cascatear para B e depois para C."""
        acts = [
            Activity(activity_id="A", description="", duration_weeks=1, required_resources={}),
            Activity(activity_id="B", description="", duration_weeks=1, required_resources={}),
            Activity(activity_id="C", description="", duration_weeks=1, required_resources={}),
        ]
        dag = ActivityDAG(activities=acts, precedence=[("A", "B"), ("B", "C")])
        pool = ResourcePool(resources={})
        scheduler = CpSatScheduler(timeout_seconds=10.0)

        resource = ReplenishableResource(
            resource_id="DIESEL",
            disponibilidade=DisponibilidadeConsumivel(estoque_inicial=0.0, taxa_reabastecimento_max=10.0),
            consumo_por_semana={"A": 30.0},
        )
        result = scheduler.schedule(dag, pool, replenishable_resources=[resource])

        by_id = {sa.activity_id: sa for sa in result.scheduled_activities}
        assert by_id["A"].start_week == 2 and by_id["A"].end_week == 3
        assert by_id["B"].start_week == 3 and by_id["B"].end_week == 4
        assert by_id["C"].start_week == 4 and by_id["C"].end_week == 5
        assert result.feasible is True

    def test_no_replenishable_resources_leaves_repair_loop_unused(self):
        """Regressão zero explícita: sem `replenishable_resources`, o laço de ponto
        fixo (reparo de estoque + repropagação) não roda — comportamento idêntico
        ao motor pré-ADR-128 (já coberto implicitamente por
        `TestCpSatSchedulerReplenishableRegressionZero`, aqui verificado também com
        um DAG que TEM precedência, para garantir que a repropagação realmente não
        é acionada quando não há recurso consumível nenhum)."""
        acts = [
            Activity(activity_id="A", description="", duration_weeks=2, required_resources={}),
            Activity(activity_id="B", description="", duration_weeks=2, required_resources={}),
        ]
        dag = ActivityDAG(activities=acts, precedence=[("A", "B")])
        pool = ResourcePool(resources={})
        scheduler = CpSatScheduler(timeout_seconds=10.0)

        without_replenishable = scheduler.schedule(dag, pool)
        with_none = scheduler.schedule(dag, pool, replenishable_resources=None)
        with_empty_list = scheduler.schedule(dag, pool, replenishable_resources=[])

        for result in (without_replenishable, with_none, with_empty_list):
            by_id = {sa.activity_id: sa for sa in result.scheduled_activities}
            assert by_id["A"].start_week == 0 and by_id["A"].end_week == 2
            assert by_id["B"].start_week == 2 and by_id["B"].end_week == 4
            assert result.feasible is True

    def test_two_round_fixed_point_needed_across_two_replenishable_resources(self):
        """Cenário onde uma única passada (reparo de estoque + repropagação de
        precedência, uma vez) NÃO basta: corrigir o estoque de DIESEL atrasa A, que
        via precedência FS empurra B — e essa nova posição de B faz B colidir, na
        mesma semana, com D (consumidor fixo de CIMENTO cuja posição vem de um
        outro ramo do DAG, H→D). O estoque de CIMENTO era viável com B na posição
        original; só fica inviável depois que a repropagação move B para cima de D
        (capacidade de armazenamento limitada — reabastecimento acumulado durante a
        espera é descartado acima do teto). Isso só é pego numa 2ª rodada do laço
        de ponto fixo."""
        acts = [
            Activity(activity_id="A", description="", duration_weeks=1, required_resources={}),
            Activity(activity_id="B", description="", duration_weeks=1, required_resources={}),
            Activity(activity_id="H", description="", duration_weeks=3, required_resources={}),
            Activity(activity_id="D", description="", duration_weeks=1, required_resources={}),
        ]
        dag = ActivityDAG(activities=acts, precedence=[("A", "B"), ("H", "D")])
        pool = ResourcePool(resources={})
        scheduler = CpSatScheduler(timeout_seconds=10.0)

        diesel = ReplenishableResource(
            resource_id="DIESEL",
            disponibilidade=DisponibilidadeConsumivel(estoque_inicial=0.0, taxa_reabastecimento_max=10.0),
            consumo_por_semana={"A": 30.0},
        )
        cimento = ReplenishableResource(
            resource_id="CIMENTO",
            disponibilidade=DisponibilidadeConsumivel(
                capacidade_armazenamento=20.0, estoque_inicial=20.0, taxa_reabastecimento_max=20.0
            ),
            consumo_por_semana={"D": 10.0, "B": 20.0},
        )

        # Prova de que uma única rodada NÃO resolve: reproduz manualmente o que uma
        # passada única faria (reparo de estoque de ambos os recursos + UMA
        # repropagação de precedência) e mostra que o CIMENTO ainda fica inviável.
        single_pass = [
            ScheduledActivity("A", 0, 1, 1),
            ScheduledActivity("B", 1, 2, 1),
            ScheduledActivity("H", 0, 3, 3),
            ScheduledActivity("D", 3, 4, 1),
        ]
        single_pass = apply_replenishable_delay(single_pass, diesel)
        single_pass = apply_replenishable_delay(single_pass, cimento)
        single_pass = repropagate_precedence_delays(single_pass, dag)
        niveis_single_pass = project_estoque_semanal(cimento, single_pass)
        assert has_estoque_negativo(niveis_single_pass), (
            "pré-condição do teste: uma única rodada deveria deixar CIMENTO inviável"
        )

        result = scheduler.schedule(dag, pool, replenishable_resources=[diesel, cimento])

        by_id = {sa.activity_id: sa for sa in result.scheduled_activities}
        assert by_id["A"].start_week == 2 and by_id["A"].end_week == 3
        assert by_id["D"].start_week == 3 and by_id["D"].end_week == 4
        # B foi empurrado por precedência para cima de D (rodada 1) e depois
        # empurrado de novo pelo reparo de CIMENTO (rodada 2) para não colidir.
        assert by_id["B"].start_week == 4 and by_id["B"].end_week == 5
        assert result.feasible is True
        niveis_final = project_estoque_semanal(cimento, result.scheduled_activities)
        assert not has_estoque_negativo(niveis_final)

    def test_irreconcilable_cascade_still_marks_infeasible_pool_capacity(self):
        """Rede de segurança final: quando o atraso repropagado faz duas atividades
        colidirem sobre a capacidade de um `ResourcePool` (recurso reutilizável, não
        consumível) — algo que nem o reparo de estoque nem a repropagação de
        precedência sabem avaliar — `_validate_repaired_schedule` ainda deve marcar
        `feasible=False` em vez de devolver um cronograma quebrado como válido."""
        acts = [
            Activity(activity_id="A", description="", duration_weeks=1, required_resources={}),
            Activity(activity_id="B", description="", duration_weeks=1, required_resources={"E": 1}),
            Activity(activity_id="H", description="", duration_weeks=3, required_resources={}),
            Activity(activity_id="X", description="", duration_weeks=1, required_resources={"E": 1}),
        ]
        dag = ActivityDAG(activities=acts, precedence=[("A", "B"), ("H", "X")])
        pool = ResourcePool(resources={"E": 1})
        scheduler = CpSatScheduler(timeout_seconds=10.0)

        resource = ReplenishableResource(
            resource_id="DIESEL",
            disponibilidade=DisponibilidadeConsumivel(estoque_inicial=0.0, taxa_reabastecimento_max=10.0),
            consumo_por_semana={"A": 30.0},
        )
        result = scheduler.schedule(dag, pool, replenishable_resources=[resource])

        by_id = {sa.activity_id: sa for sa in result.scheduled_activities}
        # A repropagação empurra B para cima de X — ambos exigem "E" (cap=1) na
        # mesma semana: violação de capacidade de pool que esta ADR não resolve.
        assert by_id["B"].start_week == by_id["X"].start_week
        assert result.feasible is False


class TestRepropagatePrecedenceDelays:
    """Testes unitários diretos de `repropagate_precedence_delays` (ADR-128 Fase 2b),
    isolados do CP-SAT — cobrem FS/SS/FF+lag e o requisito de nunca antecipar."""

    def test_fs_successor_pushed_forward_to_satisfy_precedence(self):
        dag = ActivityDAG(
            activities=[
                Activity(activity_id="A", description="", duration_weeks=1),
                Activity(activity_id="B", description="", duration_weeks=1),
            ],
            precedence=[("A", "B")],
        )
        scheduled = [
            ScheduledActivity("A", start_week=2, end_week=3, duration_weeks=1),
            ScheduledActivity("B", start_week=1, end_week=2, duration_weeks=1),
        ]
        result = repropagate_precedence_delays(scheduled, dag)
        by_id = {sa.activity_id: sa for sa in result}
        assert by_id["B"].start_week == 3
        assert by_id["B"].end_week == 4

    def test_no_violation_means_no_shift(self):
        dag = ActivityDAG(
            activities=[
                Activity(activity_id="A", description="", duration_weeks=1),
                Activity(activity_id="B", description="", duration_weeks=1),
            ],
            precedence=[("A", "B")],
        )
        scheduled = [
            ScheduledActivity("A", start_week=0, end_week=1, duration_weeks=1),
            ScheduledActivity("B", start_week=5, end_week=6, duration_weeks=1),
        ]
        result = repropagate_precedence_delays(scheduled, dag)
        by_id = {sa.activity_id: sa for sa in result}
        assert by_id["B"].start_week == 5  # já satisfazia a precedência com folga; não antecipa nem move
        assert by_id["A"].start_week == 0

    def test_never_shifts_backward(self):
        """Mesmo com folga grande, a atividade nunca é puxada para trás."""
        dag = ActivityDAG(
            activities=[
                Activity(activity_id="A", description="", duration_weeks=1),
                Activity(activity_id="B", description="", duration_weeks=1),
            ],
            precedence=[("A", "B")],
        )
        scheduled = [
            ScheduledActivity("A", start_week=0, end_week=1, duration_weeks=1),
            ScheduledActivity("B", start_week=10, end_week=11, duration_weeks=1),
        ]
        result = repropagate_precedence_delays(scheduled, dag)
        by_id = {sa.activity_id: sa for sa in result}
        assert by_id["B"].start_week == 10

    def test_ff_extended_precedence_shifts_start_and_end_together(self):
        """FF: finish(succ) >= finish(pred) + lag — mesmo violação só no fim, desloca
        também o início para preservar `duration_weeks`."""
        from concilium.application.scheduling.cpsat_scheduler import ExtendedPrecedence

        dag = ActivityDAG(
            activities=[
                Activity(activity_id="A", description="", duration_weeks=1),
                Activity(activity_id="B", description="", duration_weeks=2),
            ],
            precedence=[],
        )
        scheduled = [
            ScheduledActivity("A", start_week=5, end_week=6, duration_weeks=1),
            ScheduledActivity("B", start_week=0, end_week=2, duration_weeks=2),
        ]
        ext = [ExtendedPrecedence(pred="A", succ="B", tipo="FF", lag=0)]
        result = repropagate_precedence_delays(scheduled, dag, extended_precedences=ext)
        by_id = {sa.activity_id: sa for sa in result}
        # finish(B) >= finish(A) = 6 -> déficit de fim = 6-2=4 -> desloca ambos por 4
        assert by_id["B"].end_week == 6
        assert by_id["B"].start_week == 4
        assert by_id["B"].duration_weeks == 2

    def test_max_shift_taken_across_multiple_predecessors(self):
        """Quando uma atividade tem múltiplos predecessores, o deslocamento aplicado
        é o máximo exigido entre todos eles, não a soma nem o primeiro encontrado."""
        dag = ActivityDAG(
            activities=[
                Activity(activity_id="A", description="", duration_weeks=1),
                Activity(activity_id="B", description="", duration_weeks=1),
                Activity(activity_id="C", description="", duration_weeks=1),
            ],
            precedence=[("A", "C"), ("B", "C")],
        )
        scheduled = [
            ScheduledActivity("A", start_week=1, end_week=2, duration_weeks=1),  # exige C.start >= 2
            ScheduledActivity("B", start_week=5, end_week=6, duration_weeks=1),  # exige C.start >= 6
            ScheduledActivity("C", start_week=0, end_week=1, duration_weeks=1),
        ]
        result = repropagate_precedence_delays(scheduled, dag)
        by_id = {sa.activity_id: sa for sa in result}
        assert by_id["C"].start_week == 6
        assert by_id["C"].end_week == 7

    def test_does_not_mutate_input_list(self):
        dag = ActivityDAG(
            activities=[
                Activity(activity_id="A", description="", duration_weeks=1),
                Activity(activity_id="B", description="", duration_weeks=1),
            ],
            precedence=[("A", "B")],
        )
        original_b = ScheduledActivity("B", start_week=1, end_week=2, duration_weeks=1)
        scheduled = [
            ScheduledActivity("A", start_week=2, end_week=3, duration_weeks=1),
            original_b,
        ]
        repropagate_precedence_delays(scheduled, dag)
        assert original_b.start_week == 1  # instância original não foi mutada
        assert original_b.end_week == 2
