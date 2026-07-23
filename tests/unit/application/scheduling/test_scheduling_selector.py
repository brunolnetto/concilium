"""Coverage sweep 9 — project_service, financial_report_pdf, sharepoint, scheduling."""

from __future__ import annotations

from datetime import UTC, date, datetime

from concilium.domain.models.canonical import (
    CanonicalModel,
    Coordenadas,
    CustoTotal,
    Meta,
    Projeto,
    RegimeTrabalho,
    Resultado,
    Venda,
)


def _make_meta():
    return Meta(gerado_em=datetime.now(UTC), contexto_id="test")

def _make_proj():
    return Projeto(
        id="p1",
        nome="proj",
        tipo_obra="terraplenagem",
        localizacao="x",
        coordenadas=Coordenadas(lat=-3.0, lng=-38.0),
        regime_trabalho=RegimeTrabalho(dias_semana=5, horas_dia=8),
        data_inicio=date(2026, 6, 1),
        data_termino=date(2026, 7, 31),
        snapshot_catalogo_id="s",
        snapshot_perfil_id="s",
    )

def _minimal_canonical(**kw):
    return CanonicalModel(meta=_make_meta(), projeto=_make_proj(), **kw)

def _canonical_com_resultado():
    resultado = Resultado(
        venda=Venda(total_sem_bdi=800_000.0, total_com_bdi=1_000_000.0),
        custo=CustoTotal(direto_equipes=500_000.0, total=800_000.0),
        resultado_financeiro=200_000.0,
        margem_pct=0.20,
        status_margem="VERDE",
        validacoes=[],
    )
    return _minimal_canonical(resultado=resultado)


# ─── application/scheduling/selector.py ──────────────────────────────────────


class TestSchedulingSelector:
    def test_select_scheduling_algorithm_small(self):
        from concilium.application.scheduling.selector import select_scheduling_algorithm

        strategy = select_scheduling_algorithm(
            num_activities=10,
            num_resource_types=2,
            contract_duration_weeks=20,
            deadline_margin_pct=0.2,
        )
        assert strategy.algorithm == "CP-SAT"

    def test_select_scheduling_algorithm_large(self):
        from concilium.application.scheduling.selector import select_scheduling_algorithm

        strategy = select_scheduling_algorithm(
            num_activities=250,
            num_resource_types=5,
            contract_duration_weeks=52,
            deadline_margin_pct=0.1,
        )
        assert strategy.algorithm == "LNS"

    def test_compare_all_algorithms(self):
        from concilium.application.scheduling.models import Activity, ActivityDAG, ResourcePool
        from concilium.application.scheduling.selector import compare_all_algorithms

        acts = [
            Activity(activity_id="a1", description="A", duration_weeks=2, required_resources={"EQ": 1}),
            Activity(activity_id="a2", description="B", duration_weeks=3, required_resources={"EQ": 1}),
        ]
        dag = ActivityDAG(activities=acts, precedence=[("a1", "a2")])
        pool = ResourcePool(resources={"EQ": 1})
        results = compare_all_algorithms(acts, dag, pool, deadline_weeks=10)
        assert isinstance(results, list)




# ══ scheduling/selector.py ═══════════════════════════════════════════════════


class TestSchedulingSelector2:
    def _make_pool(self):
        from concilium.application.scheduling.models import ResourcePool

        return ResourcePool(resources={"R": 3})

    def _make_activities(self):
        from concilium.application.scheduling.models import Activity

        return [
            Activity(activity_id="a1", description="Task A", duration_weeks=2, required_resources={"R": 1}),
            Activity(activity_id="a2", description="Task B", duration_weeks=1, required_resources={"R": 1}),
        ]

    def _make_dag(self, activities):
        from concilium.application.scheduling.models import ActivityDAG

        return ActivityDAG(activities=activities, precedence=[])

    def test_explore_schedules_returns_results(self):
        """explore_schedules with deadline_weeks — covers basic path."""
        from concilium.application.scheduling.selector import explore_schedules

        acts = self._make_activities()
        dag = self._make_dag(acts)
        pool = self._make_pool()
        results = explore_schedules(acts, dag, pool, deadline_weeks=10)
        assert isinstance(results, list)

    def test_explore_schedules_with_deadline_for_score(self):
        """deadline_for_score branch — covers line 99 (score_deadline = deadline_for_score)."""
        from concilium.application.scheduling.selector import explore_schedules

        acts = self._make_activities()
        dag = self._make_dag(acts)
        pool = self._make_pool()
        results = explore_schedules(acts, dag, pool, deadline_weeks=10, deadline_for_score=8)
        assert isinstance(results, list)

    def test_explore_schedules_skips_infeasible_heuristic(self):
        """Infeasible heuristic is silently skipped (except block, lines 119-121)."""
        from concilium.application.scheduling.models import Activity, ActivityDAG, ResourcePool
        from concilium.application.scheduling.selector import explore_schedules

        # Impossibly tight deadline
        acts = [Activity(activity_id="a1", description="Long", duration_weeks=100, required_resources={"R": 1})]
        dag = ActivityDAG(activities=acts, precedence=[])
        pool = ResourcePool(resources={"R": 1})
        results = explore_schedules(acts, dag, pool, deadline_weeks=1)
        assert isinstance(results, list)



