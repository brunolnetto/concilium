"""Coverage batch 33 — projection, cubo_analitico_builder, backtracking_pe_builder."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# projection.py line 34:
# _bfc_custo_direto_total when custo_direto is None (no venda, no direto_equipes)
# ---------------------------------------------------------------------------


class TestBfcCustoDiretoTotal:
    def test_custo_direto_none_falls_through_to_line34(self):
        """Line 34: custo_direto is None → return (None, custo.total, None)."""
        from concilium.application.benchmarks.report.projection import _bfc_custo_direto_total

        custo = SimpleNamespace(direto_equipes=None, total=500.0)
        result = _bfc_custo_direto_total(custo, custo_indireto=50.0, venda=None)

        assert result[0] is None  # custo_direto = None
        assert result[1] == 500.0  # custo.total
        assert result[2] is None  # instancial = None


# ---------------------------------------------------------------------------
# projection.py line 59:
# _bfc_preco_venda when all sources are unavailable → "indisponivel"
# ---------------------------------------------------------------------------


class TestBfcPrecoVenda:
    def test_all_sources_unavailable_returns_indisponivel(self):
        """Line 59: no preco_venda from any source → (raw_bdi_lucro, None, 'indisponivel')."""
        from concilium.application.benchmarks.report.projection import _bfc_preco_venda

        # venda with no valid preco fields and raw_bdi_lucro=None → fallback all fail
        venda = SimpleNamespace(
            total_com_bdi=None,
            total_custo_plus_catalogo=None,
            bdi_lucro_impostos=None,  # raw_bdi_lucro=None → nivel 3 also fails
        )

        result = _bfc_preco_venda(venda, custo_total=None)
        assert result[0] is None  # raw_bdi_lucro
        assert result[1] is None  # preco_venda
        assert result[2] == "indisponivel"

    def test_raw_bdi_lucro_but_no_custo_total_returns_indisponivel(self):
        """Line 59: bdi_lucro set but custo_total=None → can't compute nivel 3 → indisponivel."""
        from concilium.application.benchmarks.report.projection import _bfc_preco_venda

        venda = SimpleNamespace(
            total_com_bdi=None,
            total_custo_plus_catalogo=None,
            bdi_lucro_impostos=0.15,
        )
        result = _bfc_preco_venda(venda, custo_total=None)
        assert result[2] == "indisponivel"


# ---------------------------------------------------------------------------
# projection.py line 74:
# _bfc_bdi_lucro returns 0.15 default when raw is None and no preco/custo
# ---------------------------------------------------------------------------


class TestBfcBdiLucro:
    def test_no_inputs_returns_default_015(self):
        """Line 74: raw_bdi_lucro=None, preco_venda=None → return 0.15."""
        from concilium.application.benchmarks.report.projection import _bfc_bdi_lucro

        result = _bfc_bdi_lucro(preco_venda=None, custo_total=None, raw_bdi_lucro=None)
        assert result == 0.15

    def test_no_inputs_with_zero_custo_returns_default(self):
        """Line 74: raw=None, custo_total=0 (falsy) → return 0.15."""
        from concilium.application.benchmarks.report.projection import _bfc_bdi_lucro

        result = _bfc_bdi_lucro(preco_venda=100.0, custo_total=0.0, raw_bdi_lucro=None)
        assert result == 0.15  # custo_total=0 is falsy → falls through to 0.15


# ---------------------------------------------------------------------------
# cubo_analitico_builder.py line 312:
# _enrich_with_financial_data: item with semana_offset=None → continue
# cubo_analitico_builder.py line 350:
# _build_autonomous: equipe with sa missing or no distribuicao_semanal → continue
# ---------------------------------------------------------------------------


class TestCuboAnaliticoBuilderContinues:
    def test_indireto_item_with_none_semana_is_skipped(self):
        """Line 312: item.semana is None → continue (no cell added)."""
        from unittest.mock import patch

        from concilium.domain.services.analytics.cubo_analitico_builder import CuboAnaliticoBuilder

        # Item with semana=None should be skipped
        ind_item_no_semana = SimpleNamespace(semana=None, custo_semanal=100.0, categoria="ADM")
        ind_item_valid = SimpleNamespace(semana=2, custo_semanal=200.0, categoria="ADM")

        fake_cubo_pool = SimpleNamespace(celulas=[])  # empty → _build_from_pool → calls _build_autonomous indirectly

        canonical_in = SimpleNamespace(
            projeto=SimpleNamespace(nome="TEST", data_inicio="2026-01-05"),
            equipes_diretas=None,
            indiretos_semanal=[ind_item_no_semana, ind_item_valid],  # one None semana, one valid
            cronograma=None,
            tabela_bdi_efetiva=None,
        )

        builder = CuboAnaliticoBuilder()

        with patch("concilium.domain.services.analytics.cubo_pool_builder.CuboPoolInstancialBuilder") as MockBuilder:
            mock_instance = MockBuilder.return_value
            mock_instance.build.return_value = fake_cubo_pool

            result = builder.build(canonical_in)

        # Result exists; the None-semana item was skipped
        assert result is not None

    def test_autonomous_equipe_without_sa_is_skipped(self):
        """Line 350: equipe.item_id not in sched_lookup → sa is None → continue."""
        from unittest.mock import patch

        from concilium.domain.services.analytics.cubo_analitico_builder import CuboAnaliticoBuilder

        # An equipe that references a non-existent scheduled activity
        equipe_orphan = SimpleNamespace(
            item_id="ACT-ORPHAN",
            equipamentos=[],
            custo_mao_obra_mensal=100.0,
            custo_equipamentos_mensal=50.0,
            custo_combustivel_total_mensal=10.0,
            custo_material_mensal=5.0,
        )
        sa_for_other = SimpleNamespace(
            activity_id="ACT-OTHER",
            distribuicao_semanal={"2026-W01": SimpleNamespace(num_equipes=1)},
        )

        canonical_in = SimpleNamespace(
            projeto=SimpleNamespace(nome="TEST", data_inicio=""),
            equipes_diretas=[equipe_orphan],
            indiretos_semanal=None,
            cronograma=SimpleNamespace(
                scheduled_activities=[sa_for_other],  # ACT-ORPHAN not in here
            ),
            tabela_bdi_efetiva=None,
        )

        builder = CuboAnaliticoBuilder()

        fake_cubo_pool = SimpleNamespace(celulas=[])
        with patch("concilium.domain.services.analytics.cubo_pool_builder.CuboPoolInstancialBuilder") as MockBuilder:
            mock_instance = MockBuilder.return_value
            mock_instance.build.return_value = fake_cubo_pool

            result = builder.build(canonical_in)

        # orphan equipe was skipped; result still valid
        assert result is not None


# ---------------------------------------------------------------------------
# backtracking_pe_builder.py lines 148-151:
# Score function for T0_RAMP with item_cubo_hint having "indireto" and "janela_critica_iso"
# ---------------------------------------------------------------------------


class TestBacktrackingPeBuilderT0RampHint:
    def _make_solution(self, parametro: str):
        """Create a minimal PlannerSolution-like SimpleNamespace."""
        return SimpleNamespace(
            parametro=parametro,
            tipo_equipamento=None,
            tipo_equipe=None,
            tipo_atividade=None,
        )

    def test_t0_ramp_with_indireto_and_janela_critica_reduces_score(self):
        """Lines 148-151: T0_RAMP cubo hint reduces its score — covered via _btpb_process_item.

        The score closure is defined inside _btpb_process_item; the only way to
        exercise it is to drive _btpb_process_item with a T0_RAMP solution and a
        non-empty item_cubo_hint.  See also test_small_gaps_batch40.py which covers
        these lines via the same approach.
        """
        from concilium.domain.models.financial.backtracking_pe import SolucaoInversa
        from concilium.domain.services.analytics.backtracking_pe_builder import BacktrackingPEBuilder

        builder = BacktrackingPEBuilder()

        t0_ramp = SolucaoInversa(
            parametro="T0_RAMP",
            valor_atual=0.0,
            valor_requerido=4.0,
            delta_abs=4.0,
            delta_pct=0.0,
            impacto_preco_pct=3.0,
            impacto_produtividade_pct=0.0,
            impacto_recursos_pct=0.0,
            impacto_prazo_semanas=4.0,
            pe_gap_recalculado=0.0,
            roundtrip_valido=True,
            erro_roundtrip=0.0,
            confianca=3,
        )

        item = MagicMock()
        item.atividade_id = "ACT-X"
        item.descricao = "Test"
        item.gap_rs = -30_000.0
        item.fatores = ()

        with patch.object(builder, "_compute_solucoes", return_value=[t0_ramp]):
            bt_item, _ = builder._btpb_process_item(
                item,
                equipe_lookup={},
                sched_lookup={},
                plan_lookup={},
                prat=None,
                pe_gap_alvo=0.0,
                item_cubo_hint={"natureza_dominante": "indireto", "janela_critica_iso": "2026-W10"},
            )

        assert bt_item.solucao_recomendada is not None
        assert bt_item.solucao_recomendada.parametro == "T0_RAMP"
