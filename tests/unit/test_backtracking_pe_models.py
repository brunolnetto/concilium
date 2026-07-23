"""Coverage sweep 3 — files with 20-35 lines missing."""

from __future__ import annotations

# ─── domain/models/backtracking_pe.py ────────────────────────────────────────


class TestBacktrackingPEModels:
    def test_solucao_inversa_fields(self):
        from concilium.domain.models.financial.backtracking_pe import SolucaoInversa

        s = SolucaoInversa(
            parametro="horas_dia",
            valor_atual=8.0,
            valor_requerido=10.0,
            delta_abs=2.0,
            delta_pct=0.25,
            impacto_preco_pct=0.05,
            impacto_produtividade_pct=0.1,
            impacto_recursos_pct=0.0,
            impacto_prazo_semanas=-2.0,
            pe_gap_recalculado=0.12,
            roundtrip_valido=True,
            erro_roundtrip=0.001,
            confianca=3,
        )
        assert s.parametro == "horas_dia"
        assert s.delta_abs == 2.0

    def test_backtracking_pe_classes_importable(self):
        from concilium.domain.models.financial.backtracking_pe import BacktrackingPEItem, BacktrackingPERelatorio

        assert BacktrackingPEItem is not None
        assert BacktrackingPERelatorio is not None



