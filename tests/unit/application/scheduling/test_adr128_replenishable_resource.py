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

import concilium.application.scheduling.replenishable as replenishable_mod
from concilium.application.scheduling.cpsat_scheduler import CpSatScheduler, ExtendedPrecedence
from concilium.application.scheduling.models import (
    Activity,
    ActivityDAG,
    EstoqueDelayCause,
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


class TestProjectEstoqueSemanalDeficitProvisionado:
    """ADR-151: `deficit_provisionado_externamente` é injetado just-in-time — na
    primeira semana em que faria falta, nunca antes. Não é equivalente a somá-lo a
    `estoque_inicial` (que entraria em t=0): a atividade consumidora costuma começar
    bem depois de t=0, e injetar cedo demais desperdiçaria parte do provisionamento
    contra `capacidade_armazenamento` antes de ele ser necessário — o "intervalo de
    conforto/relaxação" é justamente não fixar a semana de chegada, só a garantia de
    que chega a tempo (no mais tardar, quando o estoque zeraria)."""

    def test_nao_injeta_quando_nao_faz_falta(self):
        """Estoque nunca fica negativo sem o déficit — o campo não deve alterar nada."""
        resource = ReplenishableResource(
            resource_id="ROCHA",
            disponibilidade=DisponibilidadeConsumivel(estoque_inicial=100.0, deficit_provisionado_externamente=50.0),
            consumo_por_semana={"A1": 30.0},
        )
        scheduled = [ScheduledActivity("A1", start_week=0, end_week=2, duration_weeks=2)]
        niveis = project_estoque_semanal(resource, scheduled)
        # 100-30=70; 70-30=40 — nunca precisou do déficit
        assert niveis == {0: 70.0, 1: 40.0}

    def test_injeta_na_primeira_semana_que_faz_falta_no_valor_exato(self):
        """Sem o déficit: 0-30=-30 já na semana 0. Com deficit=50: -30+50=20."""
        resource = ReplenishableResource(
            resource_id="ROCHA",
            disponibilidade=DisponibilidadeConsumivel(estoque_inicial=0.0, deficit_provisionado_externamente=50.0),
            consumo_por_semana={"A1": 30.0},
        )
        scheduled = [ScheduledActivity("A1", start_week=0, end_week=1, duration_weeks=1)]
        niveis = project_estoque_semanal(resource, scheduled)
        assert niveis[0] == 20.0
        assert not has_estoque_negativo(niveis)

    def test_injecao_tardia_evita_desperdicio_por_capacidade(self):
        """Cenário motivador (ADR-151): se o déficit fosse somado a estoque_inicial
        (t=0), a produção inicial já lotaria a pilha (cap) antes do consumo começar,
        descartando parte do provisionamento por bota-fora — nunca chegaria a ser
        usado. Injetando just-in-time (só quando falta), o provisionamento nunca
        colide com o teto de capacidade."""
        resource = ReplenishableResource(
            resource_id="ROCHA",
            disponibilidade=DisponibilidadeConsumivel(
                capacidade_armazenamento=100.0, estoque_inicial=0.0, deficit_provisionado_externamente=50.0
            ),
            producao_por_semana={"PRODUTORA": 100.0},
            consumo_por_semana={"CONSUMIDORA": 130.0},
        )
        scheduled = [
            # Produtora ativa só na semana 0 (enche a pilha até o teto: 100).
            ScheduledActivity("PRODUTORA", start_week=0, end_week=1, duration_weeks=1),
            # Consumidora só começa na semana 3 — se o déficit tivesse sido somado em
            # t=0, a pilha já estaria no teto (100) e o excedente (deficit) seria
            # descartado por bota-fora antes de a consumidora sequer existir.
            ScheduledActivity("CONSUMIDORA", start_week=3, end_week=4, duration_weeks=1),
        ]
        niveis = project_estoque_semanal(resource, scheduled)
        # semana 0: 0+100=100 (no teto, sem sobra); semanas 1-2: sem produção/consumo,
        # estoque continua 100; semana 3: 100-130=-30, deficit injetado -> -30+50=20.
        assert niveis[3] == 20.0
        assert not has_estoque_negativo(niveis)

    def test_deficit_insuficiente_ainda_deixa_estoque_negativo_pelo_residual(self):
        resource = ReplenishableResource(
            resource_id="ROCHA",
            disponibilidade=DisponibilidadeConsumivel(estoque_inicial=0.0, deficit_provisionado_externamente=10.0),
            consumo_por_semana={"A1": 30.0},
        )
        scheduled = [ScheduledActivity("A1", start_week=0, end_week=1, duration_weeks=1)]
        niveis = project_estoque_semanal(resource, scheduled)
        # -30 + 10 (todo o deficit usado, só uma vez) = -20 — ainda negativo.
        assert niveis[0] == -20.0
        assert has_estoque_negativo(niveis)

    def test_deficit_e_usado_uma_unica_vez_nao_repetido_a_cada_semana_negativa(self):
        resource = ReplenishableResource(
            resource_id="ROCHA",
            disponibilidade=DisponibilidadeConsumivel(estoque_inicial=0.0, deficit_provisionado_externamente=10.0),
            consumo_por_semana={"A1": 30.0},
        )
        scheduled = [ScheduledActivity("A1", start_week=0, end_week=3, duration_weeks=3)]
        niveis = project_estoque_semanal(resource, scheduled)
        # semana 0: -30+10=-20 (deficit usado aqui); semana 1: -20-30=-50 (não injeta de novo); semana 2: -80.
        assert niveis == {0: -20.0, 1: -50.0, 2: -80.0}

    def test_deficit_reservado_para_o_ultimo_trecho_negativo_nao_o_primeiro(self):
        """Cenário real que motivou a correção (AGIS/ADR-151): um déficit inicial,
        transitório, é resolvido pelo próprio mecanismo de atraso do ADR-128 (fora
        de `_project`); o provisionamento externo não deve ser "gasto" nele — deve
        ficar reservado para o segundo trecho negativo, mais tardio, que representa
        o déficit estrutural genuíno (atividade consumidora sem produtora pareada).
        Duas atividades consumidoras isoladas por semanas de reabastecimento
        positivo entre elas: A1 (semana 0, trecho negativo cedo e transitório) e A2
        (semana 5, trecho negativo tardio e maior, isolado do primeiro)."""
        resource = ReplenishableResource(
            resource_id="ROCHA",
            disponibilidade=DisponibilidadeConsumivel(
                estoque_inicial=0.0, taxa_reabastecimento_max=20.0, deficit_provisionado_externamente=100.0
            ),
            consumo_por_semana={"A1": 30.0, "A2": 200.0},
        )
        scheduled = [
            ScheduledActivity("A1", start_week=0, end_week=1, duration_weeks=1),
            ScheduledActivity("A2", start_week=5, end_week=6, duration_weeks=1),
        ]
        niveis = project_estoque_semanal(resource, scheduled)
        # semana 0: 0+20-30=-10 (primeiro trecho negativo — isolado, deficit NÃO usado aqui).
        assert niveis[0] == -10.0
        # semanas 1-4: só reabastecimento (20/semana), sem consumo — reergue e fica positivo.
        assert niveis[1] == 10.0
        assert niveis[2] == 30.0
        assert niveis[3] == 50.0
        assert niveis[4] == 70.0
        # semana 5: 70+20-200=-110 (segundo/último trecho negativo) + deficit(100) = -10.
        assert niveis[5] == -10.0


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

    def test_delay_causes_accumulates_weeks_per_resource_and_activity(self):
        """ADR-128 F5: parâmetro opcional que reporta causalmente qual recurso
        atrasou qual atividade, e quantas semanas — sem quebrar o call site antigo
        (2 args posicionais, sem delay_causes)."""
        resource = ReplenishableResource(
            resource_id="DIESEL",
            disponibilidade=DisponibilidadeConsumivel(estoque_inicial=0.0, taxa_reabastecimento_max=10.0),
            consumo_por_semana={"A1": 30.0},
        )
        scheduled = [ScheduledActivity("A1", start_week=0, end_week=1, duration_weeks=1)]
        delay_causes: dict[tuple[str, str], int] = {}
        result = apply_replenishable_delay(scheduled, resource, delay_causes)
        act = next(sa for sa in result if sa.activity_id == "A1")
        assert act.start_week == 2  # mesmo delay de test_delays_activity_until_stock_accumulates
        assert delay_causes == {("DIESEL", "A1"): 2}

    def test_delay_causes_none_default_matches_legacy_call(self):
        resource = ReplenishableResource(
            resource_id="DIESEL",
            disponibilidade=DisponibilidadeConsumivel(estoque_inicial=0.0, taxa_reabastecimento_max=10.0),
            consumo_por_semana={"A1": 30.0},
        )
        scheduled = [ScheduledActivity("A1", start_week=0, end_week=1, duration_weeks=1)]
        legacy = apply_replenishable_delay(scheduled, resource)
        explicit_none = apply_replenishable_delay(scheduled, resource, None)
        assert [sa.start_week for sa in legacy] == [sa.start_week for sa in explicit_none]

    def test_no_candidates_break_when_deficit_precedes_any_consumer(self):
        """Cobre o `break` de "sem candidatas" (linha 190): o déficit já existe ANTES
        de qualquer atividade consumidora entrar em atividade — só é alcançável com um
        `estoque_inicial` negativo, valor que `DisponibilidadeConsumivel.__post_init__`
        proíbe na construção normal (ADR-128 §D1). Constrói a instância via
        `object.__new__` para contornar a validação e exercitar deliberadamente o
        estado inválido que o `break` defensivo trata sem lançar exceção."""
        disp = object.__new__(DisponibilidadeConsumivel)
        disp.capacidade_armazenamento = None
        disp.estoque_inicial = -10.0
        disp.taxa_reabastecimento_max = 0.0
        disp.lead_time_reabastecimento_dias = None

        resource = ReplenishableResource(resource_id="DIESEL", disponibilidade=disp, consumo_por_semana={"A1": 5.0})
        # A1 só começa na semana 3 — na semana 0 (primeira com estoque negativo,
        # herdado do estoque_inicial inválido) nenhuma atividade está ativa/consumindo.
        scheduled = [ScheduledActivity("A1", start_week=3, end_week=4, duration_weeks=1)]

        result = apply_replenishable_delay(scheduled, resource)

        act = next(sa for sa in result if sa.activity_id == "A1")
        assert act.start_week == 3  # sem candidata para atrasar -> break imediato, sem reparo
        assert act.end_week == 4

    def test_exhausts_max_delay_iterations_without_converging(self, monkeypatch):
        """Cobre o branch "176->204" (loop `for` esgotado sem nunca dar `break`):
        com reabastecimento pequeno e positivo, o déficit projetado melhora
        estritamente a cada iteração (nunca repete o mesmo (atividade, offset,
        déficit) — o novo detector de ponto fixo nunca dispara), mas a convergência
        real exige mais rodadas do que `_MAX_DELAY_ITERATIONS` permite. Reduz a cota
        via monkeypatch para forçar o esgotamento dentro de poucas iterações."""
        monkeypatch.setattr(replenishable_mod, "_MAX_DELAY_ITERATIONS", 3)

        resource = ReplenishableResource(
            resource_id="DIESEL",
            disponibilidade=DisponibilidadeConsumivel(estoque_inicial=0.0, taxa_reabastecimento_max=1.0),
            consumo_por_semana={"A1": 10.0},
        )
        scheduled = [ScheduledActivity("A1", start_week=0, end_week=1, duration_weeks=1)]

        result = replenishable_mod.apply_replenishable_delay(scheduled, resource)

        # Convergência real precisaria de 10 rodadas (déficit = i - 10); com a cota
        # reduzida para 3, o laço esgota as iterações sem nunca convergir nem travar
        # no detector de ponto fixo — o cronograma retornado ainda tem estoque negativo.
        act = next(sa for sa in result if sa.activity_id == "A1")
        assert act.start_week == 3  # 3 iterações, cada uma atrasando 1 semana
        niveis = project_estoque_semanal(resource, result)
        assert has_estoque_negativo(niveis)


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

    def test_estoque_delays_reports_resource_and_activity_cause(self):
        """ADR-128 F5: ScheduleOutput.estoque_delays nomeia causalmente o recurso e a
        atividade atrasados, em vez de só um booleano feasible."""
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
        assert result.estoque_delays == [EstoqueDelayCause(resource_id="DIESEL", activity_id="A", delay_weeks=2)]

    def test_estoque_delays_empty_without_replenishable_resources(self):
        acts = [Activity(activity_id="A", description="", duration_weeks=4, required_resources={"E": 2})]
        dag = ActivityDAG(activities=acts, precedence=[])
        pool = ResourcePool(resources={"E": 10})
        scheduler = CpSatScheduler(timeout_seconds=10.0)
        result = scheduler.schedule(dag, pool)
        assert result.estoque_delays == []


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

    def test_stock_permanently_negative_after_repair_rounds_exhausted_marks_infeasible(self):
        """ADR-128 F5: correção de uma lacuna encontrada durante a pesquisa —
        `_validate_repaired_schedule` só checava precedência/pool/horizonte, nunca
        estoque negativo residual. Quando `capacidade_armazenamento` é menor que o
        consumo de uma única semana, nenhum atraso jamais resolve o déficit (o
        estoque é sempre limitado ao teto antes de consumir) — o laço de ponto fixo
        esgota `_MAX_REPAIR_ROUNDS` sem convergir e sem violar horizonte/pool/
        precedência, então sem a checagem nova o resultado seria incorretamente
        `feasible=True` com estoque ainda negativo."""
        acts = [Activity(activity_id="A", description="", duration_weeks=1, required_resources={})]
        dag = ActivityDAG(activities=acts, precedence=[])
        pool = ResourcePool(resources={})
        scheduler = CpSatScheduler(timeout_seconds=10.0, horizon_weeks=6000)

        resource = ReplenishableResource(
            resource_id="DIESEL",
            disponibilidade=DisponibilidadeConsumivel(
                capacidade_armazenamento=5.0, estoque_inicial=0.0, taxa_reabastecimento_max=10.0
            ),
            consumo_por_semana={"A": 30.0},  # > capacidade_armazenamento: nunca satisfazível
        )
        result = scheduler.schedule(dag, pool, replenishable_resources=[resource])

        assert result.feasible is False
        assert has_estoque_negativo(project_estoque_semanal(resource, result.scheduled_activities))

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


class TestPoolDeficitReporting:
    """ADR-128 F7 — quando o reparo de estoque cria uma colisão de `ResourcePool` que
    `_validate_repaired_schedule` rejeita (mesmo cenário de
    `test_irreconcilable_cascade_still_marks_infeasible_pool_capacity`), `ScheduleOutput`
    deve reportar causalmente qual recurso faltou e quanto — não só `feasible=False` sem
    explicação. Isso permite ao chamador (skill-04) recalcular o pool exato necessário em
    vez de tentar relaxar às cegas (issue #117)."""

    def _scheduler_irreconcilable_pool_scenario(self):
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
        return dag, pool, scheduler, resource

    def test_pool_deficit_reports_exact_peak_demand_needed(self):
        dag, pool, scheduler, resource = self._scheduler_irreconcilable_pool_scenario()
        result = scheduler.schedule(dag, pool, replenishable_resources=[resource])

        assert result.feasible is False
        # B e X colidem sobre "E" (cap=1): pico real de demanda é 2 (1+1) — não a
        # capacidade atual, nem um percentual arbitrário dela.
        assert result.pool_deficit == {"E": 2}

    def test_pool_deficit_empty_when_feasible(self):
        """Regressão zero: schedule feasible não reporta deficit nenhum."""
        acts = [Activity(activity_id="A", description="", duration_weeks=1, required_resources={"E": 1})]
        dag = ActivityDAG(activities=acts, precedence=[])
        pool = ResourcePool(resources={"E": 10})
        scheduler = CpSatScheduler(timeout_seconds=10.0)

        result = scheduler.schedule(dag, pool)

        assert result.feasible is True
        assert result.pool_deficit == {}

    def test_pool_deficit_empty_when_infeasible_for_non_pool_reason(self):
        """Deficit só é reportado quando a causa é capacidade de pool — precedência/
        horizonte quebrados não têm "quantidade que faltou", não devem popular
        pool_deficit."""
        acts = [
            Activity(activity_id="A", description="", duration_weeks=1, required_resources={}),
            Activity(activity_id="B", description="", duration_weeks=1, required_resources={}),
        ]
        dag = ActivityDAG(activities=acts, precedence=[("A", "B")])
        pool = ResourcePool(resources={})
        scheduler = CpSatScheduler(timeout_seconds=10.0)

        scheduled = [
            ScheduledActivity(activity_id="A", start_week=5, end_week=6, duration_weeks=1),
            ScheduledActivity(activity_id="B", start_week=0, end_week=1, duration_weeks=1),
        ]
        # Chamada direta ao validador (não end-to-end) — violação de precedência pura,
        # sem nenhum ReplenishableResource envolvido.
        ok = scheduler._validate_repaired_schedule(scheduled, dag, None, pool, 100)
        assert ok is False
        deficit = scheduler._compute_pool_deficit(scheduled, pool)
        assert deficit == {}

    def test_pool_deficit_peak_not_overwritten_by_smaller_later_week(self):
        """Cobre o branch em que uma semana posterior reporta o MESMO recurso com
        qty <= ao pico já registrado: `peak[res]` não deve ser sobrescrito, o pico
        continua sendo a maior demanda semanal observada (não a última)."""
        pool = ResourcePool(resources={"E": 1})
        scheduler = CpSatScheduler(timeout_seconds=5.0)
        scheduled = [
            ScheduledActivity(
                activity_id="A", start_week=0, end_week=1, duration_weeks=1, assigned_resources={"E": 3}
            ),
            ScheduledActivity(
                activity_id="B", start_week=1, end_week=2, duration_weeks=1, assigned_resources={"E": 2}
            ),
        ]
        deficit = scheduler._compute_pool_deficit(scheduled, pool)
        assert deficit == {"E": 3}

    # ── `_validate_repaired_schedule` unitário direto ────────────────────────
    #
    # As checagens abaixo testam `CpSatScheduler._validate_repaired_schedule` chamando-o
    # diretamente com um `scheduled`/`dag` montados à mão, em vez de tentar reproduzir
    # cada violação via `schedule()` fim-a-fim: como o laço de reparo sempre roda
    # `repropagate_precedence_delays` como último passo de cada rodada, ele já corrige
    # qualquer violação de precedência clássica/estendida que o próprio grafo consiga
    # resolver em uma passada — só um DAG genuinamente cíclico (ver
    # `TestRepropagatePrecedenceDelays.test_genuine_cycle_across_combined_edges_falls_back_to_original_order`)
    # produziria uma violação residual fim-a-fim, e mesmo esse cenário é frágil/indireto
    # demais para testar contrato específico de cada `return False`. Chamar o validador
    # diretamente é uma forma direta e legítima de testar cada ramo do seu contrato:
    # ele é uma função pura de (scheduled, dag, extended_precedences, pool, horizon),
    # independente de como esses valores foram produzidos.

    def test_validate_skips_precedence_edge_dangling_outside_scheduled(self):
        """Cobre a linha 234: `dag.precedence` referencia um `succ_id` ausente de
        `scheduled` — a checagem é pulada (`continue`) e, sem outra violação, o
        resultado permanece `True`."""
        scheduler = CpSatScheduler(timeout_seconds=5.0)
        pool = ResourcePool(resources={})
        dag = ActivityDAG(activities=[Activity("A", "", 1)], precedence=[("A", "GHOST")])
        scheduled = [ScheduledActivity("A", 0, 1, 1)]
        assert scheduler._validate_repaired_schedule(scheduled, dag, None, pool, 100) is True

    def test_validate_returns_false_when_classic_fs_threshold_1_violated(self):
        """Cobre a linha 239: precedência FS clássica (theta implícito 1.0) violada
        após o reparo — `succ.start_week < pred.end_week`."""
        scheduler = CpSatScheduler(timeout_seconds=5.0)
        pool = ResourcePool(resources={})
        dag = ActivityDAG(
            activities=[Activity("A", "", 1), Activity("B", "", 1)],
            precedence=[("B", "A")],
        )
        scheduled = [ScheduledActivity("A", 0, 1, 1), ScheduledActivity("B", 0, 1, 1)]
        assert scheduler._validate_repaired_schedule(scheduled, dag, None, pool, 100) is False

    def test_validate_returns_false_when_partial_threshold_fs_violated(self):
        """Cobre as linhas 241-243: `completion_threshold_pct` < 1.0 (ADR-081) usa
        `lag = ceil(theta * duration_predecessora)`; violado quando
        `succ.start_week < pred.start_week + lag`."""
        scheduler = CpSatScheduler(timeout_seconds=5.0)
        pool = ResourcePool(resources={})
        dag = ActivityDAG(
            activities=[Activity("A", "", 1), Activity("B", "", 4)],
            precedence=[("B", "A")],
            thresholds={("B", "A"): 0.5},
        )
        # required_start = 0 + ceil(0.5 * 4) = 2; A.start_week=1 viola.
        scheduled = [ScheduledActivity("A", 1, 2, 1), ScheduledActivity("B", 0, 4, 4)]
        assert scheduler._validate_repaired_schedule(scheduled, dag, None, pool, 100) is False

    def test_validate_returns_true_when_partial_threshold_fs_satisfied(self):
        """Cobre o branch "242->232" (condição falsa: sem violação, o `for` segue para
        a próxima precedência em vez de retornar `False`) — contraparte do teste
        anterior com `A.start_week` satisfazendo o `required_start`."""
        scheduler = CpSatScheduler(timeout_seconds=5.0)
        pool = ResourcePool(resources={})
        dag = ActivityDAG(
            activities=[Activity("A", "", 1), Activity("B", "", 4)],
            precedence=[("B", "A")],
            thresholds={("B", "A"): 0.5},
        )
        # required_start = 0 + ceil(0.5 * 4) = 2; A.start_week=2 satisfaz (sem violação).
        scheduled = [ScheduledActivity("A", 2, 3, 1), ScheduledActivity("B", 0, 4, 4)]
        assert scheduler._validate_repaired_schedule(scheduled, dag, None, pool, 100) is True

    def test_validate_skips_extended_precedence_dangling_outside_scheduled(self):
        """Cobre as linhas 249-250: uma precedência estendida cujo predecessor não
        está em `scheduled` é pulada; sem outra violação, o resultado é `True`."""
        scheduler = CpSatScheduler(timeout_seconds=5.0)
        pool = ResourcePool(resources={})
        dag = ActivityDAG(activities=[Activity("A", "", 1), Activity("B", "", 1)], precedence=[])
        scheduled = [ScheduledActivity("A", 0, 1, 1), ScheduledActivity("B", 1, 2, 1)]
        ext = [
            ExtendedPrecedence(pred="GHOST", succ="B", tipo="FS", lag=0),
            ExtendedPrecedence(pred="A", succ="B", tipo="FS", lag=0),
        ]
        assert scheduler._validate_repaired_schedule(scheduled, dag, ext, pool, 100) is True

    def test_validate_returns_false_when_extended_fs_violated(self):
        """Cobre a linha 252 (`ep.tipo == "FS"` violado)."""
        scheduler = CpSatScheduler(timeout_seconds=5.0)
        pool = ResourcePool(resources={})
        dag = ActivityDAG(activities=[Activity("A", "", 1), Activity("B", "", 1)], precedence=[])
        scheduled = [ScheduledActivity("A", 0, 1, 1), ScheduledActivity("B", 0, 1, 1)]
        ext = [ExtendedPrecedence(pred="A", succ="B", tipo="FS", lag=0)]
        assert scheduler._validate_repaired_schedule(scheduled, dag, ext, pool, 100) is False

    def test_validate_returns_false_when_extended_ss_violated(self):
        """Cobre a linha 254 (`ep.tipo == "SS"` violado)."""
        scheduler = CpSatScheduler(timeout_seconds=5.0)
        pool = ResourcePool(resources={})
        dag = ActivityDAG(activities=[Activity("A", "", 1), Activity("B", "", 1)], precedence=[])
        scheduled = [ScheduledActivity("A", 0, 1, 1), ScheduledActivity("B", 1, 2, 1)]
        ext = [ExtendedPrecedence(pred="A", succ="B", tipo="SS", lag=2)]
        assert scheduler._validate_repaired_schedule(scheduled, dag, ext, pool, 100) is False

    def test_validate_returns_false_when_extended_ff_violated(self):
        """Cobre a linha 256 (`ep.tipo == "FF"` violado)."""
        scheduler = CpSatScheduler(timeout_seconds=5.0)
        pool = ResourcePool(resources={})
        dag = ActivityDAG(activities=[Activity("A", "", 2), Activity("B", "", 2)], precedence=[])
        scheduled = [ScheduledActivity("A", 0, 2, 2), ScheduledActivity("B", 0, 2, 2)]
        ext = [ExtendedPrecedence(pred="A", succ="B", tipo="FF", lag=1)]
        assert scheduler._validate_repaired_schedule(scheduled, dag, ext, pool, 100) is False


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

    def test_dangling_precedence_edge_referencing_activity_outside_dag_is_skipped(self):
        """Cobre a linha 52 de `_topological_order_with_extended`: uma aresta de
        `dag.precedence` referenciando um activity_id fora de `dag.activities` é
        ignorada na construção da ordem topológica, sem quebrar o cálculo da aresta
        válida remanescente."""
        dag = ActivityDAG(
            activities=[
                Activity(activity_id="A", description="", duration_weeks=1),
                Activity(activity_id="B", description="", duration_weeks=1),
            ],
            precedence=[("A", "B"), ("A", "GHOST")],  # GHOST não está em dag.activities
        )
        scheduled = [
            ScheduledActivity("A", start_week=2, end_week=3, duration_weeks=1),
            ScheduledActivity("B", start_week=1, end_week=2, duration_weeks=1),
        ]
        result = repropagate_precedence_delays(scheduled, dag)
        by_id = {sa.activity_id: sa for sa in result}
        assert by_id["B"].start_week == 3  # aresta válida (A->B) ainda é respeitada
        assert by_id["B"].end_week == 4

    def test_genuine_cycle_across_combined_edges_falls_back_to_original_order(self):
        """Cobre as linhas 72-73: um ciclo formado pela COMBINAÇÃO de `dag.precedence`
        (B->A) e uma precedência estendida (A->B, SS) impede que o Kahn's algorithm
        ordene todos os nós — o fallback devolve os nós restantes na ordem original
        de `dag.activities` em vez de travar."""
        dag = ActivityDAG(
            activities=[
                Activity(activity_id="A", description="", duration_weeks=1),
                Activity(activity_id="B", description="", duration_weeks=1),
            ],
            precedence=[("B", "A")],
            thresholds={("B", "A"): 0.0},
        )
        ext = [ExtendedPrecedence(pred="A", succ="B", tipo="SS", lag=0)]
        scheduled = [
            ScheduledActivity("A", start_week=0, end_week=1, duration_weeks=1),
            ScheduledActivity("B", start_week=0, end_week=1, duration_weeks=1),
        ]
        # Não deve lançar exceção mesmo com o ciclo — devolve os dois IDs, ainda que a
        # repropagação resultante possa ficar incompleta (rede de segurança final é
        # `CpSatScheduler._validate_repaired_schedule`, não esta função).
        result = repropagate_precedence_delays(scheduled, dag, extended_precedences=ext)
        assert sorted(sa.activity_id for sa in result) == ["A", "B"]

    def test_dag_activity_not_present_in_scheduled_activities_is_skipped(self):
        """Cobre a linha 120: `dag.activities` inclui uma atividade ("C") que não está
        na lista `scheduled_activities` passada — `succ` é `None` e a iteração pula
        para a próxima atividade sem lançar exceção."""
        dag = ActivityDAG(
            activities=[
                Activity(activity_id="A", description="", duration_weeks=1),
                Activity(activity_id="C", description="", duration_weeks=1),
            ],
            precedence=[],
        )
        scheduled = [ScheduledActivity("A", start_week=0, end_week=1, duration_weeks=1)]
        result = repropagate_precedence_delays(scheduled, dag)
        assert [sa.activity_id for sa in result] == ["A"]

    def test_classic_fs_predecessor_missing_from_scheduled_is_skipped(self):
        """Cobre a linha 130: `dag.precedence` referencia um predecessor ("GHOST") que
        está em `dag.activities` mas não foi agendado (fora de `scheduled_activities`)
        — `pred` é `None` e essa precedência é ignorada, sem deslocar o sucessor."""
        dag = ActivityDAG(
            activities=[
                Activity(activity_id="GHOST", description="", duration_weeks=1),
                Activity(activity_id="B", description="", duration_weeks=1),
            ],
            precedence=[("GHOST", "B")],
        )
        scheduled = [ScheduledActivity("B", start_week=0, end_week=1, duration_weeks=1)]
        result = repropagate_precedence_delays(scheduled, dag)
        by_id = {sa.activity_id: sa for sa in result}
        assert by_id["B"].start_week == 0  # predecessor ausente -> nenhuma exigência aplicada
        assert by_id["B"].end_week == 1

    def test_partial_threshold_classic_fs_pushes_by_ceil_theta_times_duration(self):
        """Cobre as linhas 135-138: `completion_threshold_pct` (ADR-081) < 1.0 usa
        `required_start = pred.start_week + ceil(theta * pred_duration)` em vez do FS
        clássico (`pred.end_week`)."""
        dag = ActivityDAG(
            activities=[
                Activity(activity_id="A", description="", duration_weeks=4),
                Activity(activity_id="B", description="", duration_weeks=1),
            ],
            precedence=[("A", "B")],
            thresholds={("A", "B"): 0.5},
        )
        scheduled = [
            ScheduledActivity("A", start_week=0, end_week=4, duration_weeks=4),
            ScheduledActivity("B", start_week=0, end_week=1, duration_weeks=1),
        ]
        result = repropagate_precedence_delays(scheduled, dag)
        by_id = {sa.activity_id: sa for sa in result}
        assert by_id["B"].start_week == 2  # ceil(0.5 * 4) = 2
        assert by_id["B"].end_week == 3

    def test_extended_precedence_predecessor_missing_from_scheduled_is_skipped(self):
        """Cobre a linha 145: uma precedência estendida referencia um predecessor
        ("GHOST2") ausente de `scheduled_activities` — `pred` é `None` e é ignorada."""
        dag = ActivityDAG(activities=[Activity(activity_id="B", description="", duration_weeks=1)], precedence=[])
        scheduled = [ScheduledActivity("B", start_week=0, end_week=1, duration_weeks=1)]
        ext = [ExtendedPrecedence(pred="GHOST2", succ="B", tipo="FS", lag=0)]
        result = repropagate_precedence_delays(scheduled, dag, extended_precedences=ext)
        by_id = {sa.activity_id: sa for sa in result}
        assert by_id["B"].start_week == 0
        assert by_id["B"].end_week == 1

    def test_extended_fs_precedence_pushes_start_by_lag_after_predecessor_finish(self):
        """Cobre a linha 147 (`ep.tipo == "FS"`) diretamente — testes anteriores desta
        classe só exercitavam FF; este cobre FS estendido (com lag) isoladamente."""
        dag = ActivityDAG(
            activities=[
                Activity(activity_id="A", description="", duration_weeks=1),
                Activity(activity_id="B", description="", duration_weeks=1),
            ],
            precedence=[],
        )
        scheduled = [
            ScheduledActivity("A", start_week=3, end_week=4, duration_weeks=1),
            ScheduledActivity("B", start_week=0, end_week=1, duration_weeks=1),
        ]
        ext = [ExtendedPrecedence(pred="A", succ="B", tipo="FS", lag=1)]
        result = repropagate_precedence_delays(scheduled, dag, extended_precedences=ext)
        by_id = {sa.activity_id: sa for sa in result}
        assert by_id["B"].start_week == 5  # end(A)=4 + lag=1
        assert by_id["B"].end_week == 6

    def test_extended_ss_precedence_pushes_start_by_lag_after_predecessor_start(self):
        """Cobre a linha 149 (`ep.tipo == "SS"`) diretamente."""
        dag = ActivityDAG(
            activities=[
                Activity(activity_id="A", description="", duration_weeks=1),
                Activity(activity_id="B", description="", duration_weeks=1),
            ],
            precedence=[],
        )
        scheduled = [
            ScheduledActivity("A", start_week=3, end_week=4, duration_weeks=1),
            ScheduledActivity("B", start_week=0, end_week=1, duration_weeks=1),
        ]
        ext = [ExtendedPrecedence(pred="A", succ="B", tipo="SS", lag=2)]
        result = repropagate_precedence_delays(scheduled, dag, extended_precedences=ext)
        by_id = {sa.activity_id: sa for sa in result}
        assert by_id["B"].start_week == 5  # start(A)=3 + lag=2
        assert by_id["B"].end_week == 6

    def test_unrecognized_extended_precedence_type_is_silently_skipped(self):
        """Cobre o branch "150->142": um `tipo` não reconhecido (a dataclass
        `ExtendedPrecedence` não valida `Literal` em runtime) não casa com nenhum dos
        `if`/`elif` FS/SS/FF — a iteração cai direto de volta ao topo do `for`, sem
        deslocar a atividade, análogo ao aviso defensivo em
        `_add_extended_precedence_constraints` do `cpsat_scheduler`."""
        dag = ActivityDAG(
            activities=[
                Activity(activity_id="A", description="", duration_weeks=1),
                Activity(activity_id="B", description="", duration_weeks=1),
            ],
            precedence=[],
        )
        scheduled = [
            ScheduledActivity("A", start_week=3, end_week=4, duration_weeks=1),
            ScheduledActivity("B", start_week=0, end_week=1, duration_weeks=1),
        ]
        ext = [ExtendedPrecedence(pred="A", succ="B", tipo="XX", lag=2)]  # type: ignore[arg-type]
        result = repropagate_precedence_delays(scheduled, dag, extended_precedences=ext)
        by_id = {sa.activity_id: sa for sa in result}
        assert by_id["B"].start_week == 0  # tipo desconhecido -> nenhuma exigência aplicada
        assert by_id["B"].end_week == 1
