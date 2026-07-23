"""Coverage batch 11 — campanha_equipamento_builder, diagnostico_pe_builder, conversor_unidades, equipe_custo_engine."""

from __future__ import annotations

# equipe_custo_engine.py line 72: __post_init__ sets total when computed > 0
# ---------------------------------------------------------------------------


class TestCustoEquipeDecomposicaoPostInit:
    def test_post_init_sets_total_from_components(self):
        """Line 72: total=0.0 and computed>0 → total is set to round(computed, 2)."""
        from concilium.domain.services.financial.equipe_custo_engine import CustoEquipeDecomposicao

        d = CustoEquipeDecomposicao(
            ativo_mo=5_000.0,
            ativo_eq=2_000.0,
            ativo_comb=0.0,
            ativo_mat=0.0,
            idle_mo=0.0,
            idle_eq=0.0,
            mob=500.0,
            demob=500.0,
        )
        assert d.total == 8_000.0

    def test_explicit_total_not_overridden(self):
        """Line 72 not hit: total already set → __post_init__ does not change it."""
        from concilium.domain.services.financial.equipe_custo_engine import CustoEquipeDecomposicao

        d = CustoEquipeDecomposicao(
            ativo_mo=5_000.0,
            ativo_eq=0.0,
            ativo_comb=0.0,
            ativo_mat=0.0,
            idle_mo=0.0,
            idle_eq=0.0,
            mob=0.0,
            demob=0.0,
            total=99_999.0,  # explicit → not overridden
        )
        assert d.total == 99_999.0

