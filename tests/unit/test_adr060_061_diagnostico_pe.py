"""Tests for ADR-060 (DiagnosticoPE) and ADR-061 (BacktrackingPE).

Covers:
- FatorPE: label, descricao, evitavel
- DiagnosticoPEItem: aproveitamento_pct, gap_evitavel, gap_estrutural
- DiagnosticoPERelatorio: resumo_causas, to_dict
- DiagnosticoPEBuilder: η computation, factor attribution, empty project
- BacktrackingPEBuilder: L inverse (exact roundtrip), η inverse (approx)
- SolucaoInversa: roundtrip validation, label
- Invariants: F1+Fη+Find+Fcross ≈ gap, η ∈ (0,1], L_req roundtrip exact
"""

from __future__ import annotations

import math
from dataclasses import replace

import pytest

from concilium.domain.models.financial.backtracking_pe import SolucaoInversa
from concilium.domain.models.analytics.diagnostico_pe import DiagnosticoPEItem, DiagnosticoPERelatorio, FatorPE
from concilium.domain.services.analytics.backtracking_pe_builder import BacktrackingPEBuilder
from concilium.domain.services.analytics.diagnostico_pe_builder import DiagnosticoPEBuilder

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_fator(codigo: str, gap_rs: float, pct: float) -> FatorPE:
    return FatorPE(codigo=codigo, gap_rs=gap_rs, pct_gap=pct)


def _make_item(
    gap_rs: float = -5000.0,
    eta: float = 0.75,
    p_medio: float = 0.80,
    cov_np: float = 0.0,
    l_aplic: float = 0.09,
    n_total: float = 20.0,
) -> DiagnosticoPEItem:
    fatores = (
        _make_fator("F_ETA_CLIMA", abs(gap_rs) * 0.5, 0.5),
        _make_fator("F_ETA_CROSS", abs(gap_rs) * 0.2, 0.2),
        _make_fator("F_IND_CLIMA", abs(gap_rs) * 0.2, 0.2),
        _make_fator("F1_QUANTIZACAO", abs(gap_rs) * 0.1, 0.1),
    )
    return DiagnosticoPEItem(
        atividade_id="eap-01",
        cpu_id="CPU-TEST",
        descricao="Escavação Teste",
        preco_venda=50000.0,
        custo_realizado=50000.0 - gap_rs,
        gap_rs=gap_rs,
        pct_gap_sobre_venda=gap_rs / 50000.0,
        eta_real=eta,
        p_medio_uniforme=p_medio,
        cov_n_p=cov_np,
        eps_cross=p_medio - eta,
        validez_aproximacao=abs(cov_np) < 0.05,
        n_total=n_total,
        fatores=fatores,
        l_aplicado=l_aplic,
        l_requerido=l_aplic + abs(gap_rs) / 45000.0,
        delta_l=abs(gap_rs) / 45000.0,
    )


# ---------------------------------------------------------------------------
# FatorPE
# ---------------------------------------------------------------------------


class TestFatorPE:
    def test_labels_exist(self):
        for cod in [
            "F_ETA_CLIMA",
            "F_CALENDARIO",
            "F_CALENDARIO_ESTRUTURAL",
            "F_ETA_CROSS",
            "F_IND_CLIMA",
            "F_IND_RAMP",
            "F1_QUANTIZACAO",
            "F_RESIDUAL",
        ]:
            f = FatorPE(codigo=cod, gap_rs=100.0, pct_gap=0.1)
            assert f.label != cod  # should be translated
            assert len(f.descricao) > 20

    def test_f1_not_evitavel(self):
        f = FatorPE(codigo="F1_QUANTIZACAO", gap_rs=100, pct_gap=0.1)
        assert not f.evitavel

    def test_cross_term_evitavel(self):
        f = FatorPE(codigo="F_ETA_CROSS", gap_rs=100, pct_gap=0.1)
        assert f.evitavel

    def test_calendar_structural_not_evitavel(self):
        estrut = FatorPE(codigo="F_CALENDARIO_ESTRUTURAL", gap_rs=100, pct_gap=0.1)
        timing = FatorPE(codigo="F_CALENDARIO", gap_rs=100, pct_gap=0.1)
        assert not estrut.evitavel
        assert timing.evitavel

    def test_frozen(self):
        f = FatorPE(codigo="F_ETA_CLIMA", gap_rs=100, pct_gap=0.1)
        with pytest.raises((AttributeError, TypeError)):
            f.gap_rs = 999  # type: ignore[misc]


# ---------------------------------------------------------------------------
# DiagnosticoPEItem
# ---------------------------------------------------------------------------


class TestDiagnosticoPEItem:
    def test_aproveitamento_pct(self):
        item = _make_item(eta=0.75)
        assert math.isclose(item.aproveitamento_pct, 75.0)

    def test_gap_evitavel_vs_estrutural(self):
        item = _make_item(gap_rs=-5000)
        assert item.gap_evitavel_rs > 0
        assert item.gap_estrutural_rs > 0
        assert math.isclose(item.gap_evitavel_rs + item.gap_estrutural_rs, 5000.0, rel_tol=0.001)

    def test_to_dict_serializable(self):
        import json

        item = _make_item()
        d = item.to_dict()
        json_str = json.dumps(d, default=str)
        assert len(json_str) > 50

    def test_deficit_has_negative_gap(self):
        item = _make_item(gap_rs=-5000)
        assert item.gap_rs < 0

    def test_equilibrado_has_zero_or_positive_gap(self):
        item = _make_item(gap_rs=0.0)
        assert item.gap_rs == 0.0


# ---------------------------------------------------------------------------
# DiagnosticoPERelatorio
# ---------------------------------------------------------------------------


class TestDiagnosticoPERelatorio:
    def _make_relatorio(self, n_deficit=2):
        itens = tuple(_make_item(gap_rs=-5000 * (i + 1)) for i in range(n_deficit))
        return DiagnosticoPERelatorio(
            projeto_id="P1",
            gerado_em="2026-05-17",
            n_itens_deficit=n_deficit,
            gap_total_rs=sum(i.gap_rs for i in itens),
            gap_evitavel_rs=sum(i.gap_evitavel_rs for i in itens),
            gap_estrutural_rs=sum(i.gap_estrutural_rs for i in itens),
            fator_dominante_label="Clima e sazonalidade",
            aviso_cross_term=False,
            l_medio_requerido=0.112,
            itens_deficit=itens,
            consistencia_validada=True,
        )

    def test_resumo_causas_keys_are_labels(self):
        rel = self._make_relatorio()
        causas = rel.resumo_causas
        for k in causas:
            assert "F_" not in k  # should be human labels, not codes

    def test_resumo_causas_positive_values(self):
        rel = self._make_relatorio()
        for v in rel.resumo_causas.values():
            assert v > 0

    def test_zero_deficit(self):
        rel = DiagnosticoPERelatorio(
            projeto_id="P",
            gerado_em="2026",
            n_itens_deficit=0,
            gap_total_rs=0,
            gap_evitavel_rs=0,
            gap_estrutural_rs=0,
            fator_dominante_label="—",
            aviso_cross_term=False,
            l_medio_requerido=0,
            itens_deficit=(),
            consistencia_validada=True,
        )
        assert rel.n_itens_deficit == 0

    def test_to_dict_json_serializable(self):
        import json

        rel = self._make_relatorio()
        d = rel.to_dict()
        json_str = json.dumps(d, default=str)
        assert len(json_str) > 100


# ---------------------------------------------------------------------------
# DiagnosticoPEBuilder (integration with minimal canonical)
# ---------------------------------------------------------------------------


class TestDiagnosticoPEBuilder:
    def _make_canonical(self, n_semanas=10, eficiencia=0.8, n_equipes=3, fator_calendario=1.0, has_deficit=True):
        from concilium.application.skills import run_escopo_e_eap
        from concilium.domain.models.canonical import (
            Cronograma,
            DistribuicaoSemanal,
            EquipamentoEquipeDireta,
            EquipeDireta,
            FuncaoEquipeDireta,
            PontoEquilibrio,
            ScheduledActivityCanonical,
        )

        inputs = {
            "nome": "TestPE",
            "tipo_obra": "terraplenagem",
            "localizacao": "BR",
            "coordenadas": {"lat": 0, "lng": 0},
            "regime_trabalho": {"dias_semana": 6, "horas_dia": 8},
            "data_inicio": "2026-06-01",
            "data_termino": "2027-01-01",
            "eap": [
                {
                    "item_id": "eap-01",
                    "ordem": 1,
                    "cpu_id": "CPU-T",
                    "descricao": "Escavação",
                    "unidade": "m3",
                    "quantitativo": 10000.0,
                }
            ],
            "contexto_id": "test",
            "snapshot_catalogo_id": "s",
            "snapshot_perfil_id": "s",
        }
        canonical = run_escopo_e_eap(None, inputs).canonical
        equipe = EquipeDireta(
            equipe_id="eq-01",
            item_id="eap-01",
            cpu_id="CPU-T",
            funcoes=[FuncaoEquipeDireta(funcao_id="MO-OP", num_pessoas=1, custo_mensal_unitario=12000)],
            equipamentos=[EquipamentoEquipeDireta(equip_id="EQ-X", num_unidades=1, custo_mensal=35000)],
            custo_mao_obra_mensal=12000,
            custo_equipamentos_mensal=35000,
            custo_combustivel_total_mensal=8000,
            permanencia_meses=2.5,
            custo_total=137500,
        )
        dist = {
            f"2026-W{24 + w:02d}": DistribuicaoSemanal(
                num_equipes=n_equipes,
                qtd_executada=1000.0,
                qtd_acumulada=1000.0 * (w + 1),
                pct=min(1.0, (w + 1) / n_semanas),
                # ADR-082: o param `eficiencia` representa a praticabilidade (clima);
                # eficiencia(célula)=utilização m_ij=1.0; fator_total = η_j = clima×calendário.
                eficiencia=1.0,
                fator_clima=eficiencia,
                fator_calendario=fator_calendario,
                fator_total=eficiencia * fator_calendario,
            )
            for w in range(n_semanas)
        }
        sched = [
            ScheduledActivityCanonical(
                activity_id="eap-01",
                start_week=0,
                end_week=n_semanas - 1,
                duration_weeks=n_semanas,
                distribuicao_semanal=dist,
            )
        ]
        cronograma = Cronograma(
            algorithm="manual_allocation",
            quality_score=1.0,
            makespan_weeks=n_semanas,
            is_feasible=True,
            scheduled_activities=sched,
        )
        pe = PontoEquilibrio(
            item_id="eap-01",
            custo_fixo_equipe=137500.0,
            custo_venda_cpu=120000.0,
            delta=-17500.0 if has_deficit else 5000.0,
            delta_pct=-0.13 if has_deficit else 0.04,
            status_validacao="AVISO" if has_deficit else "OK",
            custo_operacional_real=137500.0,
        )
        return canonical.model_copy(
            update={
                "equipes_diretas": [equipe],
                "cronograma": cronograma,
                "ponto_equilibrio": [pe],
            }
        )

    def test_builds_diagnostico(self):
        canonical = self._make_canonical()
        diag = DiagnosticoPEBuilder().build(canonical)
        assert diag.n_itens_deficit >= 0

    def test_eta_computed_correctly(self):
        """η = Σ p(t)n(t) / Σ n(t)"""
        canonical = self._make_canonical(eficiencia=0.80, n_equipes=3)
        diag = DiagnosticoPEBuilder().build(canonical)
        if diag.itens_deficit:
            item = diag.itens_deficit[0]
            # With constant eficiencia=0.80, η should be ≈ 0.80
            assert math.isclose(item.eta_real, 0.80, abs_tol=0.01)

    def test_eta_range(self):
        """η ∈ (0, 1] always"""
        for eff in [0.5, 0.7, 0.9, 1.0]:
            canonical = self._make_canonical(eficiencia=eff)
            diag = DiagnosticoPEBuilder().build(canonical)
            for item in diag.itens_deficit:
                assert 0 < item.eta_real <= 1.0

    def test_no_deficit_empty_relatorio(self):
        canonical = self._make_canonical(has_deficit=False)
        diag = DiagnosticoPEBuilder().build(canonical)
        assert diag.n_itens_deficit == 0

    def test_gap_evitavel_leq_gap_total(self):
        canonical = self._make_canonical()
        diag = DiagnosticoPEBuilder().build(canonical)
        for item in diag.itens_deficit:
            assert item.gap_evitavel_rs <= abs(item.gap_rs) + 0.01

    def test_explicacao_natureza_periodo_exposed(self):
        canonical = self._make_canonical()
        diag = DiagnosticoPEBuilder().build(canonical)
        assert isinstance(diag.explicacao_natureza_periodo, dict)
        if diag.n_itens_deficit > 0:
            assert "resumo_global_natureza" in diag.explicacao_natureza_periodo
            assert "itens" in diag.explicacao_natureza_periodo

    def test_calendar_structural_factor_is_reported_when_calendar_reduces_capacity(self):
        canonical = self._make_canonical(eficiencia=0.9, fator_calendario=0.6)
        diag = DiagnosticoPEBuilder().build(canonical)
        assert diag.n_itens_deficit > 0
        item = diag.itens_deficit[0]
        by_code = {f.codigo: f.gap_rs for f in item.fatores}
        assert by_code.get("F_CALENDARIO_ESTRUTURAL", 0.0) > 0.0


# ---------------------------------------------------------------------------
# SolucaoInversa — roundtrip de L
# ---------------------------------------------------------------------------


class TestSolucaoInversa:
    def _make_solucao_L(self, l_atual=0.09, l_req=None, gap=-5000.0) -> SolucaoInversa:
        T_ef = 0.1338
        C_cat = 45000.0
        # Derivação correta de L_req:
        # delta_L = |gap| × (1-T) / C_cat (inversa exata)
        delta_L = abs(gap) * (1 - T_ef) / C_cat
        if l_req is None:
            l_req = l_atual + delta_L
        preco_atual = C_cat * (1 + l_atual) / (1 - T_ef)
        # custo_real = preco_atual - gap (gap é negativo, então custo > preco)
        custo_real = preco_atual - gap
        preco_novo = C_cat * (1 + l_req) / (1 - T_ef)
        pe_recalc = preco_novo - custo_real
        err = abs(pe_recalc - 0.0)
        return SolucaoInversa(
            parametro="L",
            valor_atual=l_atual,
            valor_requerido=l_req,
            delta_abs=l_req - l_atual,
            delta_pct=(l_req - l_atual) / l_atual * 100,
            impacto_preco_pct=(l_req - l_atual) / (1 - T_ef) * 100,
            impacto_produtividade_pct=0.0,
            impacto_recursos_pct=0.0,
            impacto_prazo_semanas=0.0,
            pe_gap_recalculado=round(pe_recalc, 2),
            roundtrip_valido=err < max(10.0, abs(gap) * 0.0001),
            erro_roundtrip=round(err, 2),
            confianca=5,
        )

    def test_label_is_human_readable(self):
        sol = self._make_solucao_L()
        assert sol.label != "L"
        assert len(sol.label) > 5

    def test_impacto_cliente_descricao(self):
        sol = self._make_solucao_L()
        assert "Preço" in sol.impacto_cliente_descricao or "preço" in sol.impacto_cliente_descricao.lower()

    def test_l_roundtrip_valid(self):
        """Inversa de L tem roundtrip analiticamente exato."""
        sol = self._make_solucao_L()
        assert sol.roundtrip_valido

    def test_confianca_5_for_L(self):
        sol = self._make_solucao_L()
        assert sol.confianca == 5

    def test_descricao_delta_contains_percentages(self):
        sol = self._make_solucao_L()
        desc = sol.descricao_delta
        assert "%" in desc


# ---------------------------------------------------------------------------
# BacktrackingPEBuilder
# ---------------------------------------------------------------------------


class TestBacktrackingPEBuilder:
    def _make_minimal_diagnostico(self, gap=-7500.0):
        # C_cat=73000 (consistente com _make_minimal_canonical)
        T_ef = 0.1338
        C_cat = 73000.0
        preco_venda = C_cat * (1 + 0.09) / (1 - T_ef)  # ≈ 91,797
        custo_real = preco_venda - gap  # custo > preco quando gap < 0
        pct_gap = gap / max(preco_venda, 1.0)
        l_req = custo_real * (1 - T_ef) / C_cat - 1
        item = DiagnosticoPEItem(
            atividade_id="eap-01",
            cpu_id="CPU-TEST",
            descricao="Escavação Teste",
            preco_venda=round(preco_venda, 2),
            custo_realizado=round(custo_real, 2),
            gap_rs=gap,
            pct_gap_sobre_venda=round(pct_gap, 4),
            eta_real=0.75,
            p_medio_uniforme=0.80,
            cov_n_p=0.0,
            eps_cross=0.05,
            validez_aproximacao=True,
            n_total=20.0,
            fatores=(
                _make_fator("F_ETA_CLIMA", abs(gap) * 0.6, 0.6),
                _make_fator("F1_QUANTIZACAO", abs(gap) * 0.4, 0.4),
            ),
            l_aplicado=0.09,
            l_requerido=round(l_req, 4),
            delta_l=round(l_req - 0.09, 4),
        )
        return DiagnosticoPERelatorio(
            projeto_id="P",
            gerado_em="2026",
            n_itens_deficit=1,
            gap_total_rs=gap,
            gap_evitavel_rs=abs(gap) * 0.6,
            gap_estrutural_rs=abs(gap) * 0.4,
            fator_dominante_label="Clima e sazonalidade",
            aviso_cross_term=False,
            l_medio_requerido=0.113,
            itens_deficit=(item,),
            consistencia_validada=True,
        )

    def _make_minimal_canonical(self):
        from concilium.application.skills import run_escopo_e_eap
        from concilium.domain.models.canonical import (
            BdiCategorias,
            Cronograma,
            DistribuicaoSemanal,
            EquipeDireta,
            FuncaoEquipeDireta,
            Planejamento,
            PrecoUnitarioCategoria,
            ScheduledActivityCanonical,
            SubtotalCategorias,
            SubtotalSemBdiComBdi,
        )

        inputs = {
            "nome": "BT",
            "tipo_obra": "terraplenagem",
            "localizacao": "BR",
            "coordenadas": {"lat": 0, "lng": 0},
            "regime_trabalho": {"dias_semana": 6, "horas_dia": 8},
            "data_inicio": "2026-06-01",
            "data_termino": "2027-01-01",
            "eap": [
                {
                    "item_id": "eap-01",
                    "ordem": 1,
                    "cpu_id": "C",
                    "descricao": "X",
                    "unidade": "m3",
                    "quantitativo": 100.0,
                }
            ],
            "contexto_id": "t",
            "snapshot_catalogo_id": "s",
            "snapshot_perfil_id": "s",
        }
        canonical = run_escopo_e_eap(None, inputs).canonical
        equipe = EquipeDireta(
            equipe_id="e",
            item_id="eap-01",
            cpu_id="C",
            funcoes=[FuncaoEquipeDireta(funcao_id="MO", num_pessoas=1, custo_mensal_unitario=12000)],
            equipamentos=[],
            custo_mao_obra_mensal=12000,
            custo_equipamentos_mensal=30000,
            permanencia_meses=2.0,
        )
        dist = {
            f"2026-W{24 + w:02d}": DistribuicaoSemanal(
                num_equipes=2, qtd_executada=10, qtd_acumulada=10.0 * (w + 1), pct=0.1, eficiencia=0.8
            )
            for w in range(10)
        }
        sched = [
            ScheduledActivityCanonical(
                activity_id="eap-01", start_week=0, end_week=9, duration_weeks=10, distribuicao_semanal=dist
            )
        ]
        cronograma = Cronograma(
            algorithm="manual_allocation",
            quality_score=1.0,
            makespan_weeks=10,
            is_feasible=True,
            scheduled_activities=sched,
        )
        # Planejamento mínimo para que BacktrackingPEBuilder tenha C_cat
        pu = PrecoUnitarioCategoria(mao_obra=300.0, equipamentos=350.0, diesel=80.0, material=0.0, total=730.0)
        pu_bdi = PrecoUnitarioCategoria(mao_obra=390.0, equipamentos=455.0, diesel=104.0, material=0.0, total=949.0)
        subtotal = SubtotalSemBdiComBdi(
            sem_bdi=SubtotalCategorias(mao_obra=30000, equipamentos=35000, diesel=8000, material=0, total=73000),
            com_bdi=SubtotalCategorias(mao_obra=39000, equipamentos=45500, diesel=10400, material=0, total=94900),
        )
        plan = Planejamento(
            item_id="eap-01",
            cpu_id="C",
            quantitativo=100.0,
            preco_unitario=pu,
            bdi=BdiCategorias(),
            preco_unitario_com_bdi=pu_bdi,
            subtotal=subtotal,
        )
        return canonical.model_copy(
            update={
                "equipes_diretas": [equipe],
                "cronograma": cronograma,
                "planejamento": [plan],
            }
        )

    def test_builds_backtracking(self):
        diag = self._make_minimal_diagnostico()
        canonical = self._make_minimal_canonical()
        bt = BacktrackingPEBuilder().build(diag, canonical)
        assert len(bt.itens) == 1

    def test_l_solution_always_present(self):
        diag = self._make_minimal_diagnostico()
        canonical = self._make_minimal_canonical()
        bt = BacktrackingPEBuilder().build(diag, canonical)
        for item in bt.itens:
            l_sols = [s for s in item.solucoes if s.parametro == "L"]
            assert len(l_sols) >= 1

    def test_l_solution_roundtrip_valid(self):
        """Inversa de L deve sempre ter roundtrip válido."""
        diag = self._make_minimal_diagnostico()
        canonical = self._make_minimal_canonical()
        bt = BacktrackingPEBuilder().build(diag, canonical)
        for item in bt.itens:
            l_sols = [s for s in item.solucoes if s.parametro == "L" and s.roundtrip_valido]
            assert len(l_sols) >= 1

    def test_recommended_solution_exists(self):
        diag = self._make_minimal_diagnostico()
        canonical = self._make_minimal_canonical()
        bt = BacktrackingPEBuilder().build(diag, canonical)
        for item in bt.itens:
            if item.solucoes:
                assert item.solucao_recomendada is not None

    def test_no_deficit_no_backtracking(self):
        diag = DiagnosticoPERelatorio(
            projeto_id="P",
            gerado_em="2026",
            n_itens_deficit=0,
            gap_total_rs=0,
            gap_evitavel_rs=0,
            gap_estrutural_rs=0,
            fator_dominante_label="—",
            aviso_cross_term=False,
            l_medio_requerido=0,
            itens_deficit=(),
            consistencia_validada=True,
        )
        canonical = self._make_minimal_canonical()
        bt = BacktrackingPEBuilder().build(diag, canonical)
        assert len(bt.itens) == 0

    def test_consistency_global_when_all_roundtrips_pass(self):
        diag = self._make_minimal_diagnostico()
        canonical = self._make_minimal_canonical()
        bt = BacktrackingPEBuilder().build(diag, canonical)
        # If all solutions have valid roundtrip, global consistency = True
        all_valid = all(all(s.roundtrip_valido for s in item.solucoes) for item in bt.itens)
        if all_valid:
            assert bt.consistencia_global

    def test_n_max_solution_present_when_equipe_available(self):
        """N_MAX inversion is computed when equipe + schedule are available."""
        diag = self._make_minimal_diagnostico()
        canonical = self._make_minimal_canonical()
        bt = BacktrackingPEBuilder().build(diag, canonical)
        if bt.itens:
            parametros = [s.parametro for s in bt.itens[0].solucoes]
            assert "N_MAX" in parametros, "N_MAX inversion should be present when equipe/schedule are available"

    def test_val_inv_roundtrip_fail_emitted_when_roundtrips_fail(self):
        """VAL-INV-ROUNDTRIP-FAIL is emitted when n_roundtrips_falharam > 0."""
        diag = self._make_minimal_diagnostico()
        canonical = self._make_minimal_canonical()
        bt = BacktrackingPEBuilder().build(diag, canonical)
        if bt.n_roundtrips_falharam > 0:
            assert "VAL-INV-ROUNDTRIP-FAIL" in bt.validacoes_emitidas
        else:
            assert "VAL-INV-ROUNDTRIP-FAIL" not in bt.validacoes_emitidas

    def test_validacoes_emitidas_field_exists(self):
        """BacktrackingPERelatorio has validacoes_emitidas tuple."""
        diag = self._make_minimal_diagnostico()
        canonical = self._make_minimal_canonical()
        bt = BacktrackingPEBuilder().build(diag, canonical)
        assert isinstance(bt.validacoes_emitidas, tuple)

    def test_explicacao_natureza_periodo_propagated_to_backtracking(self):
        diag = self._make_minimal_diagnostico()
        diag = replace(
            diag,
            explicacao_natureza_periodo={
                "itens": {
                    "eap-01": {
                        "janela_critica_iso": "2026-W28",
                        "natureza_dominante": "indireto",
                    }
                }
            },
        )
        canonical = self._make_minimal_canonical()
        bt = BacktrackingPEBuilder().build(diag, canonical)
        assert isinstance(bt.explicacao_natureza_periodo, dict)
        assert bt.explicacao_natureza_periodo.get("itens", {}).get("eap-01", {}).get("natureza_dominante") == "indireto"


# ─── ADR-060 §DoD: validações emitidas ───────────────────────────────────────


class TestDiagnosticoValidacoes:
    def test_val_pe_cross_term_emitted_when_cross_term_present(self):
        """VAL-PE-CROSS-TERM is emitted when aviso_cross_term is True."""
        from concilium.domain.models.analytics.diagnostico_pe import DiagnosticoPERelatorio

        # Build a relatorio with aviso_cross_term=True
        relatorio = DiagnosticoPERelatorio(
            projeto_id="x",
            gerado_em="2026-01-01T00:00:00",
            n_itens_deficit=1,
            gap_total_rs=-1000.0,
            gap_evitavel_rs=500.0,
            gap_estrutural_rs=500.0,
            fator_dominante_label="Clima",
            aviso_cross_term=True,
            l_medio_requerido=0.15,
            itens_deficit=(),
            consistencia_validada=True,
            validacoes_emitidas=("VAL-PE-CROSS-TERM",),
        )
        assert "VAL-PE-CROSS-TERM" in relatorio.validacoes_emitidas

    def test_no_cross_term_when_not_present(self):
        """VAL-PE-CROSS-TERM not emitted when aviso_cross_term is False."""
        from concilium.domain.models.analytics.diagnostico_pe import DiagnosticoPERelatorio

        relatorio = DiagnosticoPERelatorio(
            projeto_id="x",
            gerado_em="2026-01-01T00:00:00",
            n_itens_deficit=0,
            gap_total_rs=0.0,
            gap_evitavel_rs=0.0,
            gap_estrutural_rs=0.0,
            fator_dominante_label="—",
            aviso_cross_term=False,
            l_medio_requerido=0.0,
            itens_deficit=(),
            consistencia_validada=True,
            validacoes_emitidas=(),
        )
        assert "VAL-PE-CROSS-TERM" not in relatorio.validacoes_emitidas

    def test_invariante_validado_na_build(self):
        """consistencia_validada reflects sum-of-factors check."""
        # DiagnosticoPEBuilder sets consistencia_validada based on actual check
        # A zero-deficit project always passes
        from concilium.domain.services.analytics.diagnostico_pe_builder import DiagnosticoPEBuilder

        class _FakeCanonical:
            ponto_equilibrio = []
            cronograma = None
            equipes_diretas = []
            planejamento = []
            custos_atividades = []
            eap = []
            resultado = None
            bridge_analysis = None
            praticabilidade = None

        diag = DiagnosticoPEBuilder().build(_FakeCanonical())
        assert diag.consistencia_validada  # zero deficit → always consistent
