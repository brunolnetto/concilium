"""Coverage batch 9 — validador_cobertura_item, cubo_pool_builder, eficiencia_field_builder,
s_curve_builder, catalog_governance."""

from __future__ import annotations

from types import SimpleNamespace

# validador_cobertura_item.py line 37: Q<=0 or custo_total<=0 → VAL-COB-SEM-DADOS
# validador_cobertura_item.py line 86: OK path → VAL-COB-OK
# ---------------------------------------------------------------------------


class TestValidarCoberturaItem:
    def _call(self, item, equipe, planejamento):
        from concilium.domain.services.validador_cobertura_item import validar_cobertura_item

        return validar_cobertura_item(item, equipe, planejamento)

    def test_zero_custo_total_returns_sem_dados(self):
        """Line 37: equipe.custo_total=0 → VAL-COB-SEM-DADOS."""
        item = SimpleNamespace(item_id="item-01", quantitativo=100.0)
        equipe = SimpleNamespace(custo_total=0.0)
        planejamento = SimpleNamespace(preco_unitario_com_bdi=None)
        result = self._call(item, equipe, planejamento)
        assert len(result) == 1
        assert result[0].codigo == "VAL-COB-SEM-DADOS"

    def test_zero_quantitativo_returns_sem_dados(self):
        """Line 37: Q=0 → VAL-COB-SEM-DADOS."""
        item = SimpleNamespace(item_id="item-01", quantitativo=0.0)
        equipe = SimpleNamespace(custo_total=5000.0)
        planejamento = SimpleNamespace(preco_unitario_com_bdi=None)
        result = self._call(item, equipe, planejamento)
        assert len(result) == 1
        assert result[0].codigo == "VAL-COB-SEM-DADOS"

    def test_good_margin_returns_ok(self):
        """Line 86: margin >= MARGEM_MINIMA → VAL-COB-OK."""
        item = SimpleNamespace(item_id="item-01", quantitativo=100.0)
        equipe = SimpleNamespace(custo_total=10_000.0)  # custo_real = 100.0/unit
        pu = SimpleNamespace(total=200.0)  # pu_venda = 200, margin = 50%
        planejamento = SimpleNamespace(preco_unitario_com_bdi=pu)
        result = self._call(item, equipe, planejamento)
        assert len(result) == 1
        assert result[0].codigo == "VAL-COB-OK"


# ---------------------------------------------------------------------------

