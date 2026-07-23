"""Coverage batch 9 — validador_cobertura_item, cubo_pool_builder, eficiencia_field_builder,
s_curve_builder, catalog_governance."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

# cubo_pool_builder.py line 23: _get_projeto_id returns "" when proj is None
# cubo_pool_builder.py line 46: _get_span uses fallback sorted set when span is empty
# cubo_pool_builder.py line 120: _check_off_zero returns dict when off cell has cost
# cubo_pool_builder.py line 197: validar_invariantes_cubo_pool appends h3
# ---------------------------------------------------------------------------


class TestCuboPoolBuilder:
    def test_get_projeto_id_no_projeto_returns_empty(self):
        """Line 23: canonical.projeto is None → return ''."""
        from concilium.domain.services.analytics.cubo_pool_builder import _get_projeto_id

        canonical = SimpleNamespace(projeto=None)
        assert _get_projeto_id(canonical) == ""

    def test_get_projeto_id_missing_attr_returns_empty(self):
        """Line 23: canonical has no 'projeto' attr → return ''."""
        from concilium.domain.services.analytics.cubo_pool_builder import _get_projeto_id

        canonical = object()  # no projeto attr at all
        assert _get_projeto_id(canonical) == ""

    def test_get_span_empty_span_uses_prod_map(self):
        """Line 46: enumerar_semanas returns [] → fallback to sorted(set(prod_map)|idle_set)."""
        from unittest.mock import patch

        from concilium.domain.services.analytics.cubo_pool_builder import _get_span

        inst = MagicMock()
        contrato = MagicMock()
        prod_map = {"2024-W01": "A1", "2024-W02": "A1"}
        idle_set: set = set()

        with patch(
            "concilium.domain.services.analytics.cubo_pool_builder.enumerar_semanas",
            return_value=[],  # force empty span
        ):
            span = _get_span(inst, contrato, prod_map, idle_set)

        assert "2024-W01" in span
        assert "2024-W02" in span

    def test_check_off_zero_returns_dict_for_off_cell_with_cost(self):
        """Line 120: cell with estado='off' and custo_total != 0 → returns violation dict."""
        from concilium.domain.services.analytics.cubo_pool_builder import _check_off_zero

        bad_cell = SimpleNamespace(estado="off", custo_total=100.0, instancia_id="EQ-01", semana_iso="2024-W01")
        good_cell = SimpleNamespace(estado="prod", custo_total=0.0, instancia_id="EQ-01", semana_iso="2024-W02")
        cubo = SimpleNamespace(celulas=[good_cell, bad_cell])
        result = _check_off_zero(cubo)
        assert result is not None
        assert result["codigo"] == "VAL-POOL-CUBO-OFF-ZERO"
        assert result["custo"] == 100.0

    def test_validar_invariantes_appends_off_violation(self):
        """Line 197: off cell with non-zero cost → violacoes contains h3."""
        from concilium.domain.services.analytics.cubo_pool_builder import validar_invariantes_cubo_pool

        bad_cell = SimpleNamespace(
            estado="off",
            custo_total=50.0,
            instancia_id="EQ-01",
            semana_iso="2024-W01",
            contrato_id="C1",
        )
        cubo = SimpleNamespace(celulas=[bad_cell])
        contratos = []  # no H1 check needed
        result = validar_invariantes_cubo_pool(cubo, contratos)
        assert any(v["codigo"] == "VAL-POOL-CUBO-OFF-ZERO" for v in result)


# ---------------------------------------------------------------------------

