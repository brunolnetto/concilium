"""Coverage batch 4 — small missing-line targets across many files."""

from __future__ import annotations

from types import SimpleNamespace

# cubo_combustivel_builder.py line 36: equip with custo_mensal <= 0 → skip
# ---------------------------------------------------------------------------


class TestCuboCombustivelSkipsZeroCusto:
    def test_equip_with_zero_custo_skipped(self):
        """Line 36: custo_combustivel_mensal=0 → continue (equip not added to celulas)."""
        from concilium.domain.services.analytics.cubo_combustivel_builder import build_cubo_combustivel_face

        equip = SimpleNamespace(
            equip_id="EQ-CAM01",
            custo_combustivel_mensal=0.0,
            tipo_combustivel="DIESEL",
        )
        equipe = SimpleNamespace(
            item_id="CPU-01",
            permanencia_meses=3.0,
            equipamentos=[equip],
        )
        canonical = SimpleNamespace(
            projeto=SimpleNamespace(nome="TestProj"),
            equipes_diretas=[equipe],
        )
        face = build_cubo_combustivel_face(canonical)
        assert len(face.celulas) == 0


# ---------------------------------------------------------------------------

