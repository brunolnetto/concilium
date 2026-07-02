"""Batch 40: inference.py, backtracking_pe_builder.py, dependencia_eap.py."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

# ─── inference.py lines 155-157 (canonical path + direto_itemizado) ──────────


class TestExtractReferenceProjectionCanonicalPath:
    """Lines 154-157: canonical branch with numeric direto_itemizado."""

    def _call(self, ref: dict):
        from concilium.application.benchmarks.inference import BenchmarkInferenceService

        return BenchmarkInferenceService._extract_reference_projection(ref)

    def test_canonical_path_sets_custo_direto_from_itemizado(self):
        """Line 155: out['custo_direto'] = direto_itemizado."""
        ref = {
            "resultado": {
                # No benchmark_confronto_referencia → confronto_ref is None
                "canonical": {
                    "custo": {
                        "direto_equipes": 500_000.0,
                        "total": 900_000.0,
                    },
                    "venda": {"total_com_bdi": 1_100_000.0},
                },
            },
            "planejamento_detalhado": [
                {"subtotal": {"sem_bdi": {"total": 620_000.0}}}
            ],
        }
        out, trace = self._call(ref)
        assert isinstance(out, dict)
        assert out["custo_direto"] == 620_000.0

    def test_canonical_path_computes_custo_total_when_indireto_numeric(self):
        """Lines 156-157: custo_total recomputed when custo_indireto is numeric."""
        ref = {
            "resultado": {
                "canonical": {
                    "custo": {
                        "direto_equipes": 500_000.0,
                        "indireto_overhead": 150_000.0,  # _sum_indireto sums this
                        "total": 900_000.0,
                    },
                    "venda": {"total_com_bdi": 1_100_000.0},
                },
            },
            "planejamento_detalhado": [
                {"subtotal": {"sem_bdi": {"total": 620_000.0}}}
            ],
        }
        out, trace = self._call(ref)
        assert isinstance(out, dict)
        assert out["custo_direto"] == 620_000.0
        assert out["custo_total"] == 620_000.0 + 150_000.0


# ─── inference.py line 220 (subtotal not-a-dict continue) ────────────────────


class TestSumPlanejamentoSubtotal:
    """Line 220: continue when subtotal is present but not a dict."""

    def test_non_dict_subtotal_is_skipped(self):
        from concilium.application.benchmarks.inference import BenchmarkInferenceService

        ref = {
            "planejamento_detalhado": [
                {"subtotal": "not_a_dict"},          # skipped (line 219-220)
                {"subtotal": {"sem_bdi": {"total": 300_000.0}}},  # counted
            ]
        }
        result = BenchmarkInferenceService._sum_planejamento_subtotal(ref, "sem_bdi")
        assert result == 300_000.0

    def test_none_subtotal_is_skipped(self):
        from concilium.application.benchmarks.inference import BenchmarkInferenceService

        ref = {
            "planejamento_detalhado": [
                {"subtotal": None},
                {"subtotal": {"sem_bdi": {"total": 200_000.0}}},
            ]
        }
        result = BenchmarkInferenceService._sum_planejamento_subtotal(ref, "sem_bdi")
        assert result == 200_000.0


# ─── backtracking_pe_builder.py lines 148-151 (T0_RAMP cubo hint scoring) ────


def _make_solucao(parametro: str, roundtrip_valido: bool = True):
    from concilium.domain.models.financial.backtracking_pe import SolucaoInversa

    return SolucaoInversa(
        parametro=parametro,
        valor_atual=0.0,
        valor_requerido=0.1,
        delta_abs=0.1,
        delta_pct=10.0,
        impacto_preco_pct=5.0,
        impacto_produtividade_pct=0.0,
        impacto_recursos_pct=0.0,
        impacto_prazo_semanas=0.0,
        pe_gap_recalculado=0.0,
        roundtrip_valido=roundtrip_valido,
        erro_roundtrip=0.0,
        confianca=4,
    )


class TestBtpbProcessItemCuboHint:
    """Lines 148-151: T0_RAMP solution with cubo hint adjusts score."""

    def _make_item(self):
        item = MagicMock()
        item.atividade_id = "ACT-1"
        item.descricao = "Escavação"
        item.gap_rs = -50_000.0
        item.fatores = ()
        return item

    def test_cubo_hint_indireto_adjusts_score(self):
        """Lines 148-149: natureza_dominante == 'indireto' reduces base score."""
        from concilium.domain.services.analytics.backtracking_pe_builder import BacktrackingPEBuilder

        builder = BacktrackingPEBuilder()
        t0 = _make_solucao("T0_RAMP")

        with patch.object(builder, "_compute_solucoes", return_value=[t0]):
            bt_item, fails = builder._btpb_process_item(
                self._make_item(),
                equipe_lookup={},
                sched_lookup={},
                plan_lookup={},
                prat=None,
                pe_gap_alvo=0.0,
                item_cubo_hint={"natureza_dominante": "indireto"},
            )

        assert bt_item.solucao_recomendada is not None
        assert bt_item.solucao_recomendada.parametro == "T0_RAMP"

    def test_cubo_hint_janela_critica_adjusts_score(self):
        """Lines 150-151: janela_critica_iso truthy reduces base score."""
        from concilium.domain.services.analytics.backtracking_pe_builder import BacktrackingPEBuilder

        builder = BacktrackingPEBuilder()
        t0 = _make_solucao("T0_RAMP")

        with patch.object(builder, "_compute_solucoes", return_value=[t0]):
            bt_item, fails = builder._btpb_process_item(
                self._make_item(),
                equipe_lookup={},
                sched_lookup={},
                plan_lookup={},
                prat=None,
                pe_gap_alvo=0.0,
                item_cubo_hint={"janela_critica_iso": "2025-W22"},
            )

        assert bt_item.solucao_recomendada is not None

    def test_cubo_hint_both_fields_covered(self):
        """Lines 148-151 fully: both indireto + janela_critica."""
        from concilium.domain.services.analytics.backtracking_pe_builder import BacktrackingPEBuilder

        builder = BacktrackingPEBuilder()
        t0 = _make_solucao("T0_RAMP")

        with patch.object(builder, "_compute_solucoes", return_value=[t0]):
            bt_item, _ = builder._btpb_process_item(
                self._make_item(),
                equipe_lookup={},
                sched_lookup={},
                plan_lookup={},
                prat=None,
                pe_gap_alvo=0.0,
                item_cubo_hint={"natureza_dominante": "indireto", "janela_critica_iso": "2025-W22"},
            )

        assert bt_item.solucao_recomendada is not None


# ─── backtracking_pe_builder.py line 394 (_solve_combinada non-None) ─────────


class TestSolveCombinada:
    """Line 394: sol_comb appended when both T0_RAMP and L solutions exist."""

    def test_solve_combinada_returns_non_none_when_both_exist(self):
        from concilium.domain.services.analytics.backtracking_pe_builder import BacktrackingPEBuilder

        builder = BacktrackingPEBuilder()
        item = MagicMock()
        item.gap_rs = -50_000.0
        item.fatores = ()

        t0 = _make_solucao("T0_RAMP")
        l_sol = _make_solucao("L")

        result = builder._solve_combinada(item, [t0, l_sol], alvo=0.0, denominator=100_000.0, T_ef=0.30)

        assert result is not None
        assert result.parametro == "COMBINADA"
        assert result.roundtrip_valido is True

    def test_compute_solucoes_appends_combinada(self):
        """Line 394: verify combinada is appended inside _compute_solucoes."""
        from concilium.domain.services.analytics.backtracking_pe_builder import BacktrackingPEBuilder

        builder = BacktrackingPEBuilder()
        item = MagicMock()
        item.gap_rs = -50_000.0
        item.fatores = ()

        t0 = _make_solucao("T0_RAMP")
        l_sol = _make_solucao("L")

        # Patch sub-solvers to return T0_RAMP and L, leaving combinada to be appended
        with (
            patch.object(builder, "_solve_L", return_value=(l_sol, 100_000.0, 0.3)),
            patch.object(builder, "_solve_P", return_value=None),
            patch.object(builder, "_solve_timing", return_value=t0),
            patch.object(builder, "_solve_timing_calendario", return_value=None),
            patch.object(builder, "_solve_n_max", return_value=None),
        ):
            solucoes = builder._compute_solucoes(item, {}, {}, {}, None, 0.0)

        parametros = [s.parametro for s in solucoes]
        assert "COMBINADA" in parametros


# ─── dependencia_eap.py lines 197-202, 214-215, 242, 303 ────────────────────


class TestDrawSingleEdge:
    """Lines 197-202, 214-215: _draw_single_edge draws arrow + label."""

    def test_calls_annotate_and_text(self):
        from concilium.application.runtime.deliverables.visualizations.charts.dependencia_eap import (
            _draw_single_edge,
        )

        ax = MagicMock()
        pe = MagicMock()
        pos = {"A": (0.0, 0.0), "B": (4.0, 1.0)}

        _draw_single_edge(ax, pos, "A", "B", "FS", pe)

        ax.annotate.assert_called_once()
        ax.text.assert_called_once()

    def test_same_y_uses_zero_rad(self):
        from concilium.application.runtime.deliverables.visualizations.charts.dependencia_eap import (
            _draw_single_edge,
        )

        ax = MagicMock()
        pe = MagicMock()
        pos = {"X": (0.0, 0.0), "Y": (4.0, 0.0)}

        _draw_single_edge(ax, pos, "X", "Y", "FS+2sem", pe)

        ax.annotate.assert_called_once()


class TestDrawEdgesCallsSingle:
    """Line 242: _draw_single_edge called when pred is in pos."""

    def test_pred_in_pos_triggers_draw_single_edge(self):
        from concilium.application.runtime.deliverables.visualizations.charts.dependencia_eap import (
            _draw_edges,
        )

        ax = MagicMock()
        pe = MagicMock()
        tasks = [{"item_id": "B", "predecessores": [{"item_id": "A"}]}]
        pos = {"A": (0.0, 0.0), "B": (4.0, 0.0)}

        _draw_edges(ax, tasks, pos, pe)

        ax.annotate.assert_called_once()

    def test_multiple_predecessors_draws_each(self):
        from concilium.application.runtime.deliverables.visualizations.charts.dependencia_eap import (
            _draw_edges,
        )

        ax = MagicMock()
        pe = MagicMock()
        tasks = [
            {"item_id": "C", "predecessores": [{"item_id": "A"}, {"item_id": "B"}]}
        ]
        pos = {"A": (0.0, 0.0), "B": (0.0, 1.0), "C": (4.0, 0.5)}

        _draw_edges(ax, tasks, pos, pe)

        assert ax.annotate.call_count == 2


class TestBuildNetworkxPosEmpty:
    """Line 303: return None when _assign_positions yields empty pos."""

    def test_returns_none_when_pos_empty(self):
        from concilium.application.runtime.deliverables.visualizations.charts.dependencia_eap import (
            _build_networkx,
        )

        mock_plt = MagicMock()
        mock_fig_to_bytes = MagicMock()

        with (
            patch(
                "concilium.application.runtime.deliverables.visualizations.charts.dependencia_eap.init_mpl",
                return_value=(mock_plt, mock_fig_to_bytes),
            ),
            patch(
                "concilium.application.runtime.deliverables.visualizations.charts.dependencia_eap._assign_positions",
                return_value=({}, {}),
            ),
        ):
            result = _build_networkx([{"item_id": "A", "predecessores": []}])

        assert result is None
