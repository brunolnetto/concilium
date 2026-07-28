"""Coverage batch 11 — campanha_equipamento_builder, diagnostico_pe_builder, conversor_unidades, equipe_custo_engine."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# diagnostico_pe_builder.py lines 103-104: _compute_f1_quantizacao normal path
# diagnostico_pe_builder.py line 194: _resolve_cubo_analitico returns cubo directly
# diagnostico_pe_builder.py lines 199-200: _resolve_cubo_analitico build success
# diagnostico_pe_builder.py line 205: _resolve_cubo_analitico except → None
# diagnostico_pe_builder.py line 213: _build_activity_week_map(None) → {}
# diagnostico_pe_builder.py line 254: _build_explicacao_natureza_periodo(None, ...) → {}
# diagnostico_pe_builder.py line 319: _process_pe_item when active=[] → None, False
# diagnostico_pe_builder.py lines 439, 445: _build_relatorio_summary validacoes
# ---------------------------------------------------------------------------


class TestComputeF1Quantizacao:
    def test_normal_path_returns_positive_value(self):
        """Lines 103-104: gap_escala > 0 → proj_total and return abs(gap_total)*gap_escala/proj_total."""
        from concilium.domain.services.analytics.diagnostico_pe_builder import _compute_f1_quantizacao

        pe = SimpleNamespace(gap_escala_abs=5.0)
        canonical = SimpleNamespace(ponto_equilibrio=[pe])
        resultado = SimpleNamespace(custo=SimpleNamespace(total=100_000.0))
        result = _compute_f1_quantizacao(canonical, resultado, -10_000.0)
        assert result > 0.0

    def test_zero_gap_escala_returns_zero(self):
        """Line 101-102: gap_escala <= 0 → return 0.0."""
        from concilium.domain.services.analytics.diagnostico_pe_builder import _compute_f1_quantizacao

        canonical = SimpleNamespace(ponto_equilibrio=[])
        result = _compute_f1_quantizacao(canonical, MagicMock(), 5000.0)
        assert result == 0.0


class TestResolveCuboAnalitico:
    def test_returns_existing_cubo_directly(self):
        """Line 194: cubo_analitico is not None → return cubo without building."""
        from concilium.domain.services.analytics.diagnostico_pe_builder import _resolve_cubo_analitico

        sentinel = object()
        canonical = SimpleNamespace(cubo_analitico=sentinel)
        result = _resolve_cubo_analitico(canonical)
        assert result is sentinel

    def test_builds_cubo_when_none_and_builder_succeeds(self):
        """Lines 199-200: cubo_analitico=None, CuboAnaliticoBuilder.build succeeds → return built cubo."""
        from concilium.domain.services.analytics.diagnostico_pe_builder import _resolve_cubo_analitico

        mock_mod = MagicMock()
        built = object()
        mock_mod.CuboAnaliticoBuilder.return_value.build.return_value = built
        with patch.dict(
            sys.modules,
            {"concilium.domain.services.analytics.cubo_analitico_builder": mock_mod},
        ):
            canonical = SimpleNamespace(cubo_analitico=None)
            result = _resolve_cubo_analitico(canonical)
        assert result is built

    def test_returns_none_when_builder_raises(self):
        """Line 205: cubo_analitico=None, build raises Exception → return None."""
        from concilium.domain.services.analytics.diagnostico_pe_builder import _resolve_cubo_analitico

        mock_mod = MagicMock()
        mock_mod.CuboAnaliticoBuilder.return_value.build.side_effect = RuntimeError("build failed")
        with patch.dict(
            sys.modules,
            {"concilium.domain.services.analytics.cubo_analitico_builder": mock_mod},
        ):
            canonical = SimpleNamespace(cubo_analitico=None)
            result = _resolve_cubo_analitico(canonical)
        assert result is None


class TestBuildActivityWeekMap:
    def test_returns_empty_dict_when_cubo_is_none(self):
        """Line 213: cubo=None → return {}."""
        from concilium.domain.services.analytics.diagnostico_pe_builder import _build_activity_week_map

        assert _build_activity_week_map(None) == {}

    def test_celula_com_atividade_ou_semana_vazia_e_ignorada(self):
        """Branch 211->212: célula sem atividade_id ou sem semana_iso é pulada
        (não contribui para o mapa), enquanto uma célula válida é agregada."""
        from types import SimpleNamespace

        from concilium.domain.services.analytics.diagnostico_pe_builder import _build_activity_week_map

        cubo = SimpleNamespace(
            celulas=[
                SimpleNamespace(componente_bdi="custo_direto", atividade_id="", semana_iso="S001", valor_rs=100.0),
                SimpleNamespace(componente_bdi="custo_direto", atividade_id="eap-01", semana_iso="", valor_rs=50.0),
                SimpleNamespace(
                    componente_bdi="custo_direto", atividade_id="eap-01", semana_iso="S001", valor_rs=200.0
                ),
            ]
        )
        result = _build_activity_week_map(cubo)
        assert list(result.keys()) == ["eap-01"]
        assert result["eap-01"]["S001"]["direto"] == 200.0


class TestBuildExplicacaoNaturezaPeriodo:
    def test_returns_empty_dict_when_cubo_is_none(self):
        """Line 254: cubo=None → return {}."""
        from concilium.domain.services.analytics.diagnostico_pe_builder import _build_explicacao_natureza_periodo

        assert _build_explicacao_natureza_periodo(None, {}, []) == {}

    def test_item_sem_hint_no_activity_week_map_e_ignorado(self):
        """Branch 258->256: item cujo atividade_id não está em activity_week_map
        gera hint vazio e não entra em `itens` (mas o loop continua para os demais)."""
        from types import SimpleNamespace

        from concilium.domain.models.analytics.diagnostico_pe import DiagnosticoPEItem, FatorPE
        from concilium.domain.services.analytics.diagnostico_pe_builder import _build_explicacao_natureza_periodo

        fator = FatorPE(codigo="F_RESIDUAL", gap_rs=100.0, pct_gap=1.0)

        def _item(aid: str) -> DiagnosticoPEItem:
            return DiagnosticoPEItem(
                atividade_id=aid,
                cpu_id="CPU-01",
                descricao="Escavação",
                preco_venda=10_000.0,
                custo_realizado=10_100.0,
                gap_rs=-100.0,
                pct_gap_sobre_venda=-0.01,
                eta_real=0.85,
                p_medio_uniforme=0.90,
                cov_n_p=0.0,
                eps_cross=0.0,
                validez_aproximacao=True,
                n_total=10.0,
                fatores=(fator,),
                l_aplicado=0.09,
                l_requerido=0.12,
                delta_l=0.03,
            )

        cubo = SimpleNamespace(
            resumo_por_natureza=lambda: {},
            resumo_por_natureza_temporal=lambda _periodo: {},
        )
        activity_week_map = {"eap-com-dados": {"S001": {"direto": 100.0, "indireto": 0.0, "total": 100.0}}}
        itens_diag = [_item("eap-sem-dados"), _item("eap-com-dados")]
        result = _build_explicacao_natureza_periodo(cubo, activity_week_map, itens_diag)
        assert "eap-sem-dados" not in result["itens"]
        assert "eap-com-dados" in result["itens"]


class TestProcessPeItemEmptyActive:
    def test_returns_none_when_no_active_distribuicao(self):
        """Line 319: distribuicao_semanal all have num_equipes=0 → active=[] → return None, False."""
        from concilium.domain.services.analytics.diagnostico_pe_builder import _process_pe_item

        dist = SimpleNamespace(num_equipes=0, eficiencia=0.9, fator_total=None)
        sa = SimpleNamespace(distribuicao_semanal={"2024-W01": dist})
        equipe = SimpleNamespace(
            custo_mao_obra_mensal=5000.0,
            custo_equipamentos_mensal=2000.0,
        )
        pe = SimpleNamespace(
            item_id="A1",
            custo_venda_cpu=10_000.0,
            custo_operacional_real=8_000.0,
            custo_fixo_equipe=7_000.0,
        )
        item, cross = _process_pe_item(
            pe,
            equipe_lookup={"A1": equipe},
            sched_lookup={"A1": sa},
            plan_lookup={},
            ca_lookup={},
            eap_lookup={},
            L_aplicado=0.09,
            T_efetivo=0.1338,
            canonical_in=SimpleNamespace(ponto_equilibrio=[]),
            resultado=None,
        )
        assert item is None
        assert cross is False


class TestResolvePePrices:
    """ADR-162: preco_venda deve usar sem_bdi — PE compara custo×custo, BDI é margem
    deliberada aplicada depois do equilíbrio (mesma convenção de _ponto_equilibrio.py e
    de _compute_recalibracao_l, no mesmo módulo, que já usava sem_bdi para C_cat)."""

    def _plan(self, sem_bdi_total: float, com_bdi_total: float):
        subtotal = SimpleNamespace(
            sem_bdi=SimpleNamespace(total=sem_bdi_total),
            com_bdi=SimpleNamespace(total=com_bdi_total),
        )
        return SimpleNamespace(subtotal=subtotal)

    def test_usa_sem_bdi_nao_com_bdi(self):
        from concilium.domain.services.analytics.diagnostico_pe_builder import _resolve_pe_prices

        plan = self._plan(sem_bdi_total=73_000.0, com_bdi_total=94_900.0)
        pe = SimpleNamespace(custo_venda_cpu=0.0, custo_operacional_real=8_000.0, custo_fixo_equipe=7_000.0)
        preco_venda, _custo_real = _resolve_pe_prices(pe, plan, ca=None)
        assert preco_venda == 73_000.0

    def test_fallback_pe_custo_venda_cpu_quando_sem_plano(self):
        from concilium.domain.services.analytics.diagnostico_pe_builder import _resolve_pe_prices

        pe = SimpleNamespace(custo_venda_cpu=12_345.0, custo_operacional_real=8_000.0, custo_fixo_equipe=7_000.0)
        preco_venda, _custo_real = _resolve_pe_prices(pe, plan=None, ca=None)
        assert preco_venda == 12_345.0


class TestBuildRelatorioSummaryValidacoes:
    def _make_item(self, gap_rs: float, fator_gap_rs: float):
        from concilium.domain.models.analytics.diagnostico_pe import DiagnosticoPEItem, FatorPE

        fator = FatorPE(codigo="F_RESIDUAL", gap_rs=fator_gap_rs, pct_gap=1.0)
        return DiagnosticoPEItem(
            atividade_id="A1",
            cpu_id="CPU-01",
            descricao="Escavação",
            preco_venda=10_000.0,
            custo_realizado=abs(gap_rs) + 10_000.0,
            gap_rs=gap_rs,
            pct_gap_sobre_venda=gap_rs / 10_000.0,
            eta_real=0.85,
            p_medio_uniforme=0.90,
            cov_n_p=0.0,
            eps_cross=0.0,
            validez_aproximacao=True,
            n_total=10.0,
            fatores=(fator,),
            l_aplicado=0.09,
            l_requerido=0.12,
            delta_l=0.03,
        )

    def test_cross_term_presente_adds_validation_code(self):
        """Line 439: cross_term_presente=True → 'VAL-PE-CROSS-TERM' in validacoes_emitidas."""
        from concilium.domain.services.analytics.diagnostico_pe_builder import _build_relatorio_summary

        item = self._make_item(gap_rs=-1000.0, fator_gap_rs=1000.0)
        result = _build_relatorio_summary("proj-01", [item], cross_term_presente=True, norm_tol_pct=0.02)
        assert "VAL-PE-CROSS-TERM" in result.validacoes_emitidas

    def test_inconsistency_adds_norm_fail_validation(self):
        """Line 445: sum_fatores significantly != abs(gap_total) → 'VAL-PE-NORM-FAIL'."""
        from concilium.domain.services.analytics.diagnostico_pe_builder import _build_relatorio_summary

        # gap_rs=-1000 but fator only covers 100 → |900/1000|=0.9 > 0.02 → not consistent
        item = self._make_item(gap_rs=-1000.0, fator_gap_rs=100.0)
        result = _build_relatorio_summary("proj-01", [item], cross_term_presente=False, norm_tol_pct=0.02)
        assert "VAL-PE-NORM-FAIL" in result.validacoes_emitidas


# ---------------------------------------------------------------------------

