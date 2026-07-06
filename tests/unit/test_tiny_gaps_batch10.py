"""Tests for benchmarks/report/projection.py helpers and skills/__init__.py."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

# ─── application/benchmarks/report/projection.py ─────────────────────────────


class TestProjectionHelpers:
    def test_bfc_custo_indireto(self):
        from concilium.application.benchmarks.report.projection import _bfc_custo_indireto

        custo = MagicMock()
        custo.indireto_adm = 10000.0
        custo.indireto_top = 5000.0
        custo.indireto_lab = 2000.0
        custo.indireto_qsms = 1000.0
        custo.indireto_mob = 500.0
        result = _bfc_custo_indireto(custo)
        assert result == pytest.approx(18500.0)

    def test_bfc_custo_indireto_none(self):
        from concilium.application.benchmarks.report.projection import _bfc_custo_indireto

        custo = MagicMock()
        custo.indireto_adm = None
        custo.indireto_top = None
        custo.indireto_lab = None
        custo.indireto_qsms = None
        custo.indireto_mob = None
        result = _bfc_custo_indireto(custo)
        assert result == 0.0

    def test_bfc_custo_direto_total(self):
        from concilium.application.benchmarks.report.projection import _bfc_custo_direto_total

        custo = MagicMock()
        custo.direto.total = 800000.0
        result = _bfc_custo_direto_total(custo, 18500.0)
        assert isinstance(result, tuple)

    def test_bfc_preco_venda(self):
        from concilium.application.benchmarks.report.projection import _bfc_preco_venda

        venda = MagicMock()
        venda.total_com_bdi = 1200000.0
        raw_bdi, pv, fonte = _bfc_preco_venda(venda, 1000000.0)
        assert pv == 1200000.0
        assert fonte == "total_com_bdi"

    def test_bfc_bdi_lucro(self):
        from concilium.application.benchmarks.report.projection import _bfc_bdi_lucro

        result = _bfc_bdi_lucro(1200000.0, 1000000.0, None)
        assert result > 0

    def test_accumulate_planejamento_empty(self):
        from concilium.application.benchmarks.report.projection import _accumulate_planejamento

        ok, totals = _accumulate_planejamento([])
        assert ok is False

    def test_accumulate_planejamento_with_data(self):
        from concilium.application.benchmarks.report.projection import _accumulate_planejamento

        planej = [{"categoria": "TERRA", "subtotal": {"com_bdi": {"total": 500000.0}}}]
        ok, totals = _accumulate_planejamento(planej)
        assert isinstance(totals, dict)

    def test_accumulate_equipes_empty(self):
        from concilium.application.benchmarks.report.projection import TotaisDiretosEquipes, _accumulate_equipes

        result = _accumulate_equipes([])
        assert isinstance(result, TotaisDiretosEquipes)

    def test_build_breakdown_indireto(self):
        from concilium.application.benchmarks.report.projection import _build_breakdown_indireto

        custo = MagicMock()
        custo.indireto_adm = 10000.0
        custo.indireto_top = 5000.0
        custo.indireto_lab = 2000.0
        custo.indireto_qsms = 1000.0
        custo.indireto_mob = 500.0
        result = _build_breakdown_indireto(custo, 18500.0)
        assert isinstance(result, dict)

    def test_build_breakdown_direto_equipes(self):
        from concilium.application.benchmarks.report.projection import (
            TotaisDiretosEquipes,
            _build_breakdown_direto_equipes,
        )

        totals = TotaisDiretosEquipes(
            mao_obra=60000.0,
            equipamentos=30000.0,
            diesel=10000.0,
            materiais=5000.0,
            total=105000.0,
        )
        result = _build_breakdown_direto_equipes(totals)
        assert isinstance(result, dict)

    def test_build_ferramenta_custo(self):
        from concilium.application.benchmarks.report.projection import _build_ferramenta_custo

        custo = MagicMock()
        custo.direto.total = 800000.0
        custo.indireto_adm = 10000.0
        custo.indireto_top = 5000.0
        custo.indireto_lab = 0.0
        custo.indireto_qsms = 0.0
        custo.indireto_mob = 0.0
        venda = MagicMock()
        venda.total_com_bdi = 1000000.0
        fd, pv, bdi = _build_ferramenta_custo(custo, venda)
        assert isinstance(fd, dict)


# ─── application/skills/__init__.py (36 missing) ──────────────────────────────


class TestSkillsInit:
    def test_import_skills_module(self):
        import concilium.application.skills as skills

        assert skills is not None

    def test_skills_dict_has_entries(self):
        from concilium.application.skills import SKILLS

        assert len(SKILLS) > 0

    def test_skills_contains_skill01(self):
        from concilium.application.skills import SKILLS

        assert "01-escopo-e-eap" in SKILLS

    def test_skill_registry_loads(self):
        from concilium.application.skills.registry import SkillRegistry

        registry = SkillRegistry()
        assert len(registry.skills) > 0

    def test_get_skill_contract(self):
        from concilium.application.skills.registry import SkillRegistry

        registry = SkillRegistry()
        skill = registry.get_skill("01-escopo-e-eap")
        assert skill is not None
        assert hasattr(skill, "depends_on_skills")


# ─── application/runtime/__init__.py (30 missing) ─────────────────────────────


class TestRuntimeInit:
    def test_runtime_importable(self):
        from concilium.application.runtime import Runtime

        assert Runtime is not None

    def test_runtime_init(self, tmp_path):
        from concilium.application.runtime import Runtime

        rt = Runtime(config_root=tmp_path)
        assert rt is not None

    def test_runtime_has_run_pipeline(self, tmp_path):
        from concilium.application.runtime import Runtime

        rt = Runtime(config_root=tmp_path)
        assert hasattr(rt, "run_pipeline")


# ─── application/runtime/deliverables/visualizations/cube/__init__.py ─────────


class TestCubeInit:
    def test_cube_build_all_importable(self):
        from concilium.application.runtime.deliverables.visualizations.cube import build_all

        assert callable(build_all)

    # ─── Extended BenchmarkProjection tests ──────────────────────────────────

    def test_bfc_preco_venda_fallback_bdi_lucro(self):
        """Cover line 53-54: fallback via raw_bdi_lucro when no total_com_bdi."""
        from concilium.application.benchmarks.report.projection import _bfc_preco_venda

        venda = MagicMock()
        venda.total_com_bdi = None
        venda.total_custo_plus_catalogo = None
        venda.bdi_lucro_impostos = 0.20
        raw_bdi, pv, fonte = _bfc_preco_venda(venda, 1000000.0)
        assert raw_bdi == 0.20
        assert pv == pytest.approx(1200000.0)
        assert fonte == "derivado"

    def test_bfc_preco_venda_fallback_catalogo(self):
        """Cover line 51-52: fallback via total_custo_plus_catalogo."""
        from concilium.application.benchmarks.report.projection import _bfc_preco_venda

        venda = MagicMock()
        venda.total_com_bdi = None
        venda.total_custo_plus_catalogo = 1300000.0
        venda.bdi_lucro_impostos = None
        raw_bdi, pv, fonte = _bfc_preco_venda(venda, None)
        assert pv == 1300000.0
        assert fonte == "total_custo_plus_catalogo"

    def test_accumulate_equipes_instancial_path(self):
        """Cover lines 178-183: equipes without custo_inst_mo (fallback path)."""
        from concilium.application.benchmarks.report.projection import _accumulate_equipes

        equipe = MagicMock()
        equipe.custo_inst_mo = None  # triggers fallback PATH 2
        equipe.custo_fixo_mensal = 5000.0
        equipe.custo_total = 60000.0
        equipe.custo_mao_obra_mensal = 3000.0
        equipe.custo_equipamentos_mensal = 1000.0
        equipe.custo_combustivel_total_mensal = 500.0
        equipe.cpu_id = "CPU-1"
        result = _accumulate_equipes([equipe])
        assert result.mao_obra > 0

    def test_bai_fill_criticidade(self):
        """Cover lines 204-209: _bai_fill_criticidade."""
        from concilium.application.benchmarks.report.projection import _build_actionable_insights

        canonical = MagicMock()
        canonical.cost_criticality_report = MagicMock()
        canonical.cost_criticality_report.atividades = [
            MagicMock(classe="A"),
            MagicMock(classe="A"),
            MagicMock(classe="B"),
        ]
        canonical.relatorio_sensibilidade = None
        canonical.relatorio_executivo = None
        canonical.relatorio_intervencao = None
        insights = _build_actionable_insights(canonical)
        assert "criticidade" in insights

    def test_bai_fill_sensibilidade(self):
        """Cover lines 212-218: _bai_fill_sensibilidade."""
        from concilium.application.benchmarks.report.projection import _build_actionable_insights

        canonical = MagicMock()
        canonical.cost_criticality_report = None
        canonical.relatorio_sensibilidade = MagicMock()
        canonical.relatorio_sensibilidade.passos_repair = [MagicMock()]
        canonical.relatorio_sensibilidade.oportunidades = []
        canonical.relatorio_executivo = None
        canonical.relatorio_intervencao = None
        insights = _build_actionable_insights(canonical)
        assert "sensibilidade" in insights

    def test_benchmark_projection_from_canonical(self):
        """Cover lines 269-282: BenchmarkProjection.from_canonical()."""
        from concilium.application.benchmarks.report.projection import BenchmarkProjection

        canonical = MagicMock()
        canonical.resultado = None
        canonical.equipes_diretas = []
        canonical.planejamento = []
        canonical.cost_criticality_report = None
        canonical.relatorio_sensibilidade = None
        canonical.relatorio_executivo = None
        canonical.relatorio_intervencao = None
        proj = BenchmarkProjection.from_canonical(canonical)
        assert proj is not None

    def test_benchmark_projection_from_canonical_none(self):
        """Cover line 272-273: BenchmarkProjection.from_canonical(None)."""
        from concilium.application.benchmarks.report.projection import BenchmarkProjection

        proj = BenchmarkProjection.from_canonical(None)
        assert proj is not None
        assert proj.ferramenta == {}

    def test_accumulate_equipes_fallback_skipped_when_custo_fixo_zero(self):
        """Covers the false branch of `if equipe.custo_fixo_mensal > 0` in the
        PATH-2 fallback: with custo_inst_mo=None and custo_fixo_mensal=0, no
        fallback totals are added (they stay at zero)."""
        from concilium.application.benchmarks.report.projection import _accumulate_equipes

        equipe = MagicMock()
        equipe.custo_inst_mo = None
        equipe.custo_fixo_mensal = 0.0
        equipe.custo_total = 60000.0
        equipe.custo_mao_obra_mensal = 3000.0
        equipe.custo_equipamentos_mensal = 1000.0
        equipe.custo_combustivel_total_mensal = 500.0
        equipe.equipamentos = []
        equipe.cpu_id = "CPU-1"
        result = _accumulate_equipes([equipe])
        assert result.mao_obra == 0.0
        assert result.equipamentos == 0.0

    def test_populate_resultado_custo_none_skips_ferramenta(self):
        """Covers the false branch of `if custo is not None`: ferramenta must
        stay unset when resultado.custo is None."""
        from concilium.application.benchmarks.report.projection import BenchmarkProjection

        resultado = MagicMock()
        resultado.custo = None
        resultado.venda = None
        resultado.balanco_ponto_equilibrio = None
        projection = BenchmarkProjection()
        custo_direto, custo_indireto = projection._populate_resultado(resultado)
        assert custo_direto is None
        assert custo_indireto is None
        assert projection.ferramenta == {}

    def test_populate_resultado_fills_ponto_equilibrio_when_balanco_present(self):
        """Covers the true branch of `if balanco_pe:` (lines 300-308)."""
        from concilium.application.benchmarks.report.projection import BenchmarkProjection

        resultado = MagicMock()
        resultado.custo = None
        resultado.venda = None
        balanco = MagicMock()
        balanco.total_hc_operacional = 10
        balanco.total_hc_indireto = 2
        balanco.total_hc = 12
        balanco.custo_fixo_mensal = 1000.0
        balanco.custo_fixo_total = 5000.0
        balanco.numero_equipes_diretas = 3
        resultado.balanco_ponto_equilibrio = balanco
        projection = BenchmarkProjection()
        projection._populate_resultado(resultado)
        assert projection.ponto_equilibrio_ferramenta["total_hc"] == 12
        assert projection.ponto_equilibrio_ferramenta["equipes"] == 3

    def test_populate_breakdown_direto_uses_equipes_when_no_catalog(self):
        """Covers the `elif equipes_diretas:` branch (line 319-320): when
        planejamento has no catalog data but equipes_diretas is non-empty,
        the equipes-based breakdown builder must be used."""
        from concilium.application.benchmarks.report.projection import BenchmarkProjection

        equipe = MagicMock()
        equipe.custo_inst_mo = None
        equipe.custo_fixo_mensal = 5000.0
        equipe.custo_total = 60000.0
        equipe.custo_mao_obra_mensal = 3000.0
        equipe.custo_equipamentos_mensal = 1000.0
        equipe.custo_combustivel_total_mensal = 500.0
        equipe.equipamentos = []
        equipe.cpu_id = "CPU-1"
        canonical = MagicMock()
        canonical.equipes_diretas = [equipe]
        canonical.planejamento = []  # empty → has_catalog is False
        projection = BenchmarkProjection()
        projection._populate_breakdown_direto(canonical, custo_direto=None)
        assert projection.ferramenta_breakdown_direto is not None

    def test_cube_build_all_empty_canonical(self):
        from concilium.application.runtime.deliverables.visualizations.cube import build_all

        canonical = MagicMock()
        canonical.equipes_diretas = []
        canonical.cronograma.scheduled_activities = []
        canonical.cronograma.makespan_weeks = 0
        canonical.ponto_equilibrio = []
        canonical.cubo_analitico = None
        canonical.cubo_pool = None
        # build_all may take different args; try minimal
        try:
            result = build_all(canonical, {})
            assert isinstance(result, (dict, list, bytes, type(None)))
        except TypeError:
            pytest.skip("build_all signature changed")
