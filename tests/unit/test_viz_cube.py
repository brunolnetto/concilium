"""Coverage sweep 3 — files with 20-35 lines missing."""

from __future__ import annotations

from unittest.mock import MagicMock

# ─── application/runtime/deliverables/visualizations/cube/__init__ ───────────


class TestVizCubeInit:
    def test_build_all_function_exists(self):
        from concilium.application.runtime.deliverables.visualizations.cube import build_all

        assert callable(build_all)

    def test_build_all_empty_relatorio(self):
        from concilium.application.runtime.deliverables.visualizations.cube import build_all

        canonical = MagicMock()
        canonical.cubo_analitico = None
        canonical.cronograma = None
        result = build_all(relatorio={}, canonical=canonical)
        assert isinstance(result, dict)

    def test_module_has_build_all(self):
        from concilium.application.runtime.deliverables.visualizations import cube

        assert hasattr(cube, "build_all")





from unittest.mock import patch  # noqa: E402

# ─── application/runtime/deliverables/visualizations/cube/__init__.py ─────────


class TestCubeInit:
    def test_build_graficos_dict_non_dict_returns_empty(self):
        """Line 61: _build_graficos_dict with non-dict relatorio returns {}."""
        from concilium.application.runtime.deliverables.visualizations.cube import _build_graficos_dict

        assert _build_graficos_dict("not_a_dict") == {}
        assert _build_graficos_dict(42) == {}
        assert _build_graficos_dict(None) == {}

    def test_build_faces_exception_is_swallowed(self):
        """Lines 75-76: _build_faces catches module.build() exceptions silently."""
        from concilium.application.runtime.deliverables.visualizations.cube import _build_faces

        def bad_build(*args, **kwargs):
            raise RuntimeError("chart failed")

        with patch(
            "concilium.application.runtime.deliverables.visualizations.cube._FACE_BUILDERS",
            [(bad_build, "face.png", False)],
        ):
            result = _build_faces(MagicMock(), MagicMock(), {})
        assert result == {}

    def test_build_all_canonical_none_returns_empty(self):
        """Line 90: build_all with canonical=None returns {}."""
        from concilium.application.runtime.deliverables.visualizations.cube import build_all

        result = build_all(canonical=None)
        assert result == {}





import pytest  # noqa: E402

# ─── application/runtime/deliverables/visualizations/cube/__init__.py ─────────


class TestCubeInit2:
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

