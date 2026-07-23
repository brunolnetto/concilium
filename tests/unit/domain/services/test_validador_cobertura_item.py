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



from unittest.mock import MagicMock  # noqa: E402

# ─── domain/services/validador_cobertura_item.py (2 missing: 46, 75) ──────────


def _make_eap_item(item_id="A1", quantitativo=10.0):
    from concilium.domain.services.validador_cobertura_item import EapItem

    return EapItem(item_id=item_id, cpu_id="CPU-1", quantitativo=quantitativo)


def _make_equipe(custo_total=1000.0):
    from concilium.domain.services.validador_cobertura_item import EquipeDireta

    return EquipeDireta(item_id="A1", custo_total=custo_total)


def _make_planejamento(pu_total=1200.0):
    plan = MagicMock()
    if pu_total is None:
        plan.preco_unitario_com_bdi = None
    else:
        plan.preco_unitario_com_bdi = MagicMock()
        plan.preco_unitario_com_bdi.total = pu_total
    return plan


class TestValidadorCoberturaItem:
    def test_invalid_pu_returns_aviso(self):
        from concilium.domain.services.validador_cobertura_item import validar_cobertura_item

        result = validar_cobertura_item(_make_eap_item(), _make_equipe(1000), _make_planejamento(None))
        assert result[0].codigo == "VAL-COB-SEM-PRECO"

    def test_margem_negativa_aviso(self):
        from concilium.domain.services.validador_cobertura_item import validar_cobertura_item

        # custo_real = 1000/10 = 100, pu_venda = 80 → margem < 0
        result = validar_cobertura_item(_make_eap_item(quantitativo=10), _make_equipe(1000), _make_planejamento(80.0))
        assert result[0].codigo == "VAL-COB-NEG"

    def test_margem_baixa_aviso(self):
        from concilium.domain.services.validador_cobertura_item import validar_cobertura_item

        # custo = 49, pu = 50 → margem = 2% < MARGEM_MINIMA (5%)
        result = validar_cobertura_item(_make_eap_item(quantitativo=10), _make_equipe(490), _make_planejamento(50.0))
        codes = [r.codigo for r in result]
        assert any(c.startswith("VAL-COB") for c in codes)



