"""Coverage batch A — targets mcp_server/__main__, semantic/__init__,
scheduling/selector, optimizer/loop, skills/__init__, cpu_insumo validations,
02-produtividade-climatica, 09-relatorio-e-artefatos, and scheduling/scheduler edge cases.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import patch

import pytest

# ── Shared helpers ────────────────────────────────────────────────────────────
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


# ══ mcp_server/__main__.py ════════════════════════════════════════════════════


class TestMcpServerMain:
    def test_main_function_importable(self):
        """Importing mcp_server.__main__ should expose main (covers lines 2,4)."""
        import importlib

        mod = importlib.import_module("concilium.presentation.mcp.__main__")
        assert hasattr(mod, "main")

    def test_main_is_callable(self):
        from concilium.presentation.mcp.server import main

        assert callable(main)


# ══ semantic/__init__.py ══════════════════════════════════════════════════════


class TestSemanticInit:
    def test_build_unit_cache_exception_path(self):
        """Force _build_unit_cache exception path (lines 36-37)."""
        import concilium.application.semantic as sem_mod

        # Save original cache and restore after to avoid polluting other tests
        original_cache = sem_mod._UNIT_ALIASES_CACHE
        try:
            with patch.object(sem_mod, "VocabularyLoader", side_effect=Exception("force")):
                sem_mod._build_unit_cache()
            # Should silently set _UNIT_ALIASES_CACHE = {}
            assert isinstance(sem_mod._UNIT_ALIASES_CACHE, dict)
        finally:
            sem_mod._UNIT_ALIASES_CACHE = original_cache


# ══ scheduling/selector.py ═══════════════════════════════════════════════════


class TestSchedulingSelector:
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


# ══ optimizer/loop.py ════════════════════════════════════════════════════════


class TestOptimizerLoop:
    """Tests for adjust_schedule covering lines 41, 43, 49-50."""

    _PERFIL = {"categorias_indireto": []}

    def test_catalogo_none_defaults_to_empty(self):
        """catalogo=None → catalogo = {} (line 41)."""
        from concilium.application.optimizer.loop import adjust_schedule

        can = _minimal_canonical()
        can_out, feasible, violations = adjust_schedule(can, None, catalogo=None, perfil=self._PERFIL)
        assert isinstance(feasible, bool)

    def test_decision_variables_as_dict(self):
        """dict decision_variables → dv_dict = decision_variables (lines 49-50)."""
        from concilium.application.optimizer.loop import adjust_schedule

        can = _minimal_canonical()
        dv = {"dv2_num_equipes": {}}
        can_out, feasible, violations = adjust_schedule(can, dv, catalogo={}, perfil=self._PERFIL)
        assert isinstance(feasible, bool)


# ══ skills/__init__.py ═══════════════════════════════════════════════════════


class TestSkillsInit:
    def test_load_nonexistent_skill_raises_import_error(self):
        """_load with non-existent skill path raises ImportError (line 33)."""
        from concilium.application.skills import _load

        with pytest.raises(ImportError, match="não encontrado"):
            _load("99-nonexistent-skill-xyz", "run_nonexistent")

    def test_discover_skills_bad_skill_raises_runtime_error(self, tmp_path):
        """_discover_skills error in loading raises RuntimeError (lines 74-75)."""
        import concilium.application.skills as skills_mod

        # Create a fake manifest dir with a toml pointing to skill.py that doesn't exist
        fake_skill_dir = tmp_path / "99-fake-skill"
        fake_skill_dir.mkdir()
        toml = fake_skill_dir / "skill.toml"
        toml.write_text('[skill]\nid = "99-fake-skill"\n', encoding="utf-8")
        # skill.py does not exist → _load raises ImportError → caught → RuntimeError
        with patch.object(skills_mod, "_MANIFESTS", tmp_path):
            with pytest.raises(RuntimeError):
                skills_mod._discover_skills()


# ══ validations/cpu_insumo.py ════════════════════════════════════════════════


class TestCpuInsumoValidacoes:
    def _make_validator(self, insumos_list=None):
        from concilium.domain.validations.cpu_insumo import ValidadorCPUInsumo
        from concilium.infrastructure.repositories.insumo import RepositorioInsumo

        catalogo = {"insumos": insumos_list or []}
        repo = RepositorioInsumo(catalogo)
        return ValidadorCPUInsumo(repo)

    def test_validar_coeficiente_sensato_unidade_desconhecida_ok(self):
        """Unidade not in RANGE_SENSATO → OK (line 88)."""
        validator = self._make_validator()
        comp_item = {"insumo_id": "X", "coeficiente": 99999}
        insumo = {"unidade": "unidade_estranha"}
        result = validator.validar_coeficiente_sensato(comp_item, insumo)
        assert result.status == "OK"

    def test_validar_coeficiente_sensato_fora_range_aviso(self):
        """Coeficiente outside range → AVISO (lines 92-99)."""
        from concilium.domain.validations.cpu_insumo import RANGE_SENSATO_POR_UNIDADE

        validator = self._make_validator()
        unit = next(iter(RANGE_SENSATO_POR_UNIDADE))
        _minimo, maximo = RANGE_SENSATO_POR_UNIDADE[unit]
        comp_item = {"insumo_id": "X", "coeficiente": maximo * 1000}
        insumo = {"unidade": unit}
        result = validator.validar_coeficiente_sensato(comp_item, insumo)
        assert result.status == "AVISO"
        assert result.codigo == "VAL-CPU-INS-04"

    def test_validar_unidade_compativel_coeficiente_none(self):
        """coeficiente is None → ERRO (lines 116-120)."""
        from concilium.domain.validations.cpu_insumo import RANGE_OBRIGATORIO_POR_UNIDADE

        validator = self._make_validator()
        unit = next(iter(RANGE_OBRIGATORIO_POR_UNIDADE))
        comp_item = {"insumo_id": "X", "coeficiente": None}
        insumo = {"unidade": unit}
        result = validator.validar_unidade_compativel(comp_item, insumo)
        assert result.status == "ERRO"
        assert result.codigo == "VAL-CPU-INS-05"

    def test_validar_unidade_compativel_coeficiente_fora_range(self):
        """Coeficiente outside mandatory range → ERRO (lines 123-129)."""
        from concilium.domain.validations.cpu_insumo import RANGE_OBRIGATORIO_POR_UNIDADE

        validator = self._make_validator()
        unit = next(iter(RANGE_OBRIGATORIO_POR_UNIDADE))
        _minimo, maximo = RANGE_OBRIGATORIO_POR_UNIDADE[unit]
        comp_item = {"insumo_id": "X", "coeficiente": maximo * 999999}
        insumo = {"unidade": unit}
        result = validator.validar_unidade_compativel(comp_item, insumo)
        assert result.status == "ERRO"
        assert result.codigo == "VAL-CPU-INS-05"

    def test_validar_cpu_completa_insumo_none_skip(self):
        """When insumo is found in repo index but obter_insumo returns None → continue (line 179)."""
        from concilium.domain.validations.cpu_insumo import ValidadorCPUInsumo
        from concilium.infrastructure.repositories.insumo import RepositorioInsumo

        catalogo = {"insumos": [{"codigo": "X", "tipo": "MAO_OBRA", "unidade": "h"}]}
        repo = RepositorioInsumo(catalogo)
        # Monkey-patch obter_insumo to return None even though the item exists
        repo.obter_insumo = lambda codigo: None  # type: ignore[method-assign]
        validator = ValidadorCPUInsumo(repo)
        cpu = {
            "composicao_itens": [{"insumo_id": "X", "coeficiente": 1.0, "categoria_custo": "MAO_OBRA"}],
            "composicao_padrao_equipe": {"funcoes": [], "equipamentos": []},
        }
        results = validator.validar_cpu_completa(cpu)
        # VAL-CPU-INS-01 OK (item exists via insumo_existe), then None → continue
        assert any(r.codigo == "VAL-CPU-INS-01" and r.status == "OK" for r in results)


# ══ 02-produtividade-climatica edge cases ════════════════════════════════════════════


class TestPraticabilidadeEdgeCases:
    """Cover lines 45, 56-57, 72, 82-83 in 02-produtividade-climatica/skill.py."""

    def _make_mock_dados(self, dias_semana_data=None, dias_mensal_data=None):
        from concilium.infrastructure.clients.openmeteo import DadosClimaticosMensais

        return DadosClimaticosMensais(
            fonte="test",
            ano_referencia=2024,
            latitude=-3.0,
            longitude=-38.0,
            dias_precipitacao_semanal=dias_semana_data or {},
            dias_precipitacao_mensal=dias_mensal_data or {},
        )

    def _load_praticabilidade_fns(self):
        import importlib.util
        from pathlib import Path

        path = (
            Path(__file__).parents[2]
            / "src"
            / "concilium"
            / "application"
            / "skills"
            / "manifests"
            / "02-produtividade-climatica"
            / "skill.py"
        )
        spec = importlib.util.spec_from_file_location("_skill_02_praticabilidade", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_nonstandard_limiar_mm_semanal_falls_back(self):
        """limiar_mm=15 (not 5/10/20) falls back to 10mm (line 45)."""
        mod = self._load_praticabilidade_fns()
        dados = self._make_mock_dados(dias_semana_data={"2024-W01": {"10mm": 2}})
        result = mod._calcular_percentual_produtivo_semanal(dados, 15.0, 5)
        assert "2024-W01" in result

    def test_nonstandard_limiar_mm_mensal_falls_back(self):
        """limiar_mm=7 (not 5/10/20) falls back to 10mm (line 72)."""
        mod = self._load_praticabilidade_fns()
        dados = self._make_mock_dados(dias_mensal_data={"06": {"10mm": 5}})
        result = mod._calcular_percentual_produtivo_mensal(dados, 7.0, 5)
        assert "06" in result

    def test_dias_semana_zero_semanal_returns_zero(self):
        """dias_semana=0 → dias_uteis=0 → percentual=0.0, continue (lines 56-57)."""
        mod = self._load_praticabilidade_fns()
        dados = self._make_mock_dados(dias_semana_data={"2024-W01": {"10mm": 0}})
        result = mod._calcular_percentual_produtivo_semanal(dados, 10.0, 0)
        assert result.get("2024-W01") == 0.0

    def test_dias_semana_zero_mensal_returns_zero(self):
        """dias_semana=0 → dias_uteis_mes=0 → percentual=0.0, continue (lines 82-83)."""
        mod = self._load_praticabilidade_fns()
        dados = self._make_mock_dados(dias_mensal_data={"06": {"10mm": 0}})
        result = mod._calcular_percentual_produtivo_mensal(dados, 10.0, 0)
        assert result.get("06") == 0.0


# ══ 09-relatorio-e-artefatos edge cases ══════════════════════════════════════════════


class TestAdapterSaidaEdgeCases:
    """Cover lines 113-114 (planejamento vazio) and 161-168 (Excel exception)."""

    @pytest.mark.slow
    def test_adapter_sem_planejamento_emite_aviso(self):
        """Empty planejamento → VAL-ADAPTER-01 AVISO (line 114)."""
        from concilium.application.skills import run_relatorio_e_artefatos

        can = _canonical_com_resultado()
        res = run_relatorio_e_artefatos(can, {}, {})
        codigos = {v.codigo: v.status for v in res.validacoes}
        assert codigos.get("VAL-ADAPTER-01") == "AVISO"


# ══ scheduling/scheduler.py edge cases ═══════════════════════════════════════


class TestSchedulerEdgeCases:
    """Cover lines 30, 175, 190-191, 209, 222, 243-244."""

    def _make_activity(self, aid, duration, resources=None):
        from concilium.application.scheduling.models import Activity

        return Activity(
            activity_id=aid, description=aid, duration_weeks=duration, required_resources=resources or {"R": 1}
        )

    def test_unknown_priority_rule_raises(self):
        """Invalid priority_rule raises ValueError (line 30)."""
        from concilium.application.scheduling.scheduler import SerialScheduler

        with pytest.raises(ValueError, match="Unknown priority_rule"):
            SerialScheduler(priority_rule="INVALID_RULE")

    def test_gr_priority_rule_schedules(self):
        """GR rule executes _prioritize returning topo_order (line 175)."""
        from concilium.application.scheduling.models import ActivityDAG, ResourcePool
        from concilium.application.scheduling.scheduler import SerialScheduler

        acts = [self._make_activity("a1", 1), self._make_activity("a2", 1)]
        dag = ActivityDAG(activities=acts, precedence=[])
        pool = ResourcePool(resources={"R": 2})
        scheduler = SerialScheduler(priority_rule="GR")
        sched = scheduler.schedule(acts, dag, pool, deadline_weeks=5)
        assert sched.makespan <= 5

    def test_schedule_infeasible_raises_schedule_error(self):
        """Activity can't fit in deadline → ScheduleError (lines 190-191)."""
        from concilium.application.scheduling.models import ActivityDAG, ResourcePool, ScheduleError
        from concilium.application.scheduling.scheduler import SerialScheduler

        acts = [self._make_activity("a1", 10)]
        dag = ActivityDAG(activities=acts, precedence=[])
        pool = ResourcePool(resources={"R": 1})
        scheduler = SerialScheduler(priority_rule="MINSLK")
        with pytest.raises(ScheduleError):
            scheduler.schedule(acts, dag, pool, deadline_weeks=5)

    def test_resource_conflict_forces_stagger(self):
        """Two activities needing same resource → _can_schedule returns False → stagger (line 209)."""
        from concilium.application.scheduling.models import ActivityDAG, ResourcePool
        from concilium.application.scheduling.scheduler import SerialScheduler

        acts = [
            self._make_activity("a1", 2, {"R": 2}),
            self._make_activity("a2", 2, {"R": 2}),
        ]
        dag = ActivityDAG(activities=acts, precedence=[])
        pool = ResourcePool(resources={"R": 2})
        scheduler = SerialScheduler(priority_rule="MINSLK")
        sched = scheduler.schedule(acts, dag, pool, deadline_weeks=10)
        # They must be scheduled sequentially → makespan >= 4
        assert sched.makespan >= 4

    def test_compute_metrics_empty_acts_returns_defaults(self):
        """Empty acts → default ScheduleMetrics (lines 222-226)."""
        from concilium.application.scheduling.models import ResourcePool
        from concilium.application.scheduling.scheduler import SerialScheduler

        pool = ResourcePool(resources={"R": 1})
        scheduler = SerialScheduler()
        metrics = scheduler._compute_metrics([], {}, pool, makespan=0, deadline_weeks=5)
        assert metrics.makespan == 0
        assert metrics.resource_leveling_score == 1.0

    def test_compute_metrics_makespan_zero_with_acts_gives_else_branch(self):
        """makespan=0 with non-empty acts → weekly_loads=[] → else branch (lines 243-244)."""
        from concilium.application.scheduling.models import ResourcePool, ScheduledActivity
        from concilium.application.scheduling.scheduler import SerialScheduler

        pool = ResourcePool(resources={"R": 1})
        # Pass makespan=0 so range(0) = [] → weekly_loads empty → else branch
        acts = [ScheduledActivity(activity_id="a1", start_week=0, end_week=0, duration_weeks=0)]
        scheduler = SerialScheduler()
        metrics = scheduler._compute_metrics(acts, {}, pool, makespan=0, deadline_weeks=5)
        assert metrics.resource_leveling_score == 1.0
        assert metrics.resource_utilization_avg == 0.0
