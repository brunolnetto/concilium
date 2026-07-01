"""Coverage batch 9 — validador_cobertura_item, cubo_pool_builder, eficiencia_field_builder, s_curve_builder, catalog_governance."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
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
# eficiencia_field_builder.py line 92: qm <= 0 → continue (skipped week)
# eficiencia_field_builder.py line 99: q_max_list empty → early return with defaults
# eficiencia_field_builder.py line 188: sa without item_id → continue
# eficiencia_field_builder.py line 191: sa with non-dict dist → continue
# ---------------------------------------------------------------------------


class TestEficienciaFieldBuilder:
    def _make_campo(self):
        from concilium.domain.services.analytics.eficiencia_field_builder import CampoEficiencia

        return CampoEficiencia()

    def test_decomposicao_causal_skips_zero_qmax(self):
        """Line 92: qm=0 → continue in decomposicao_causal; only positive weeks contribute."""
        campo = self._make_campo()
        campo.atividades = ["A1"]
        campo.Q_max = {"A1": {"2024-W01": 0.0, "2024-W02": 10.0}}  # W01 skipped (qm=0)
        campo.Eta_plan = {"A1": {"2024-W01": 0.9, "2024-W02": 0.8}}
        campo.Eta_clima = {"A1": {"2024-W01": 1.0, "2024-W02": 0.9}}
        campo.Delta = {"A1": {"2024-W01": 1.0, "2024-W02": 1.0}}
        result = campo.decomposicao_causal()
        assert isinstance(result, dict)
        assert "eta_plan_global" in result

    def test_decomposicao_causal_empty_qmax_returns_defaults(self):
        """Line 99: all qm<=0 → q_max_list empty → early return defaults."""
        campo = self._make_campo()
        campo.atividades = ["A1"]
        campo.Q_max = {"A1": {"2024-W01": 0.0}}
        campo.Eta_plan = {"A1": {"2024-W01": 0.9}}
        campo.Eta_clima = {"A1": {}}
        campo.Delta = {"A1": {}}
        result = campo.decomposicao_causal()
        assert result == {"eta_clima_global": 1.0, "delta_global": 1.0, "eta_plan_global": 1.0}

    def test_build_skips_sa_without_item_id(self):
        """Line 188: sa.activity_id is None and no item_id → continue."""
        from concilium.domain.services.analytics.eficiencia_field_builder import EficienciaFieldBuilder

        # sa with no activity_id or item_id
        sa = SimpleNamespace(activity_id=None, item_id=None, distribuicao_semanal={})
        cronograma = SimpleNamespace(scheduled_activities=[sa])
        canonical = SimpleNamespace(cronograma=cronograma)
        builder = EficienciaFieldBuilder()
        campo = builder.build(canonical)
        assert campo.atividades == []

    def test_build_skips_sa_with_non_dict_dist(self):
        """Line 191: sa.distribuicao_semanal is not a dict → continue."""
        from concilium.domain.services.analytics.eficiencia_field_builder import EficienciaFieldBuilder

        # sa with valid activity_id but non-dict dist
        sa = SimpleNamespace(activity_id="A1", item_id=None, distribuicao_semanal="not-a-dict")
        cronograma = SimpleNamespace(scheduled_activities=[sa])
        canonical = SimpleNamespace(cronograma=cronograma)
        builder = EficienciaFieldBuilder()
        campo = builder.build(canonical)
        assert campo.atividades == []  # skipped due to non-dict dist


# ---------------------------------------------------------------------------
# s_curve_builder.py lines 59, 67: continue paths in _scb_collect_direct_costs
# ---------------------------------------------------------------------------


class TestSCurveBuilderDirectCosts:
    def test_equipe_not_found_in_lookup_skipped(self):
        """Line 59: equipe_lookup.get(sa.activity_id) returns None → continue."""
        from concilium.domain.services.analytics.s_curve_builder import _scb_collect_direct_costs

        sa = SimpleNamespace(activity_id="B1", distribuicao_semanal={})
        equipe_lookup = {}  # B1 not in lookup
        custo, equip, n = _scb_collect_direct_costs([sa], equipe_lookup)
        assert sum(custo.values()) == 0.0

    def test_n_equipes_zero_skipped(self):
        """Line 67: n_equipes=0 → continue."""
        from concilium.domain.services.analytics.s_curve_builder import _scb_collect_direct_costs

        dist = SimpleNamespace(num_equipes=0, eficiencia=1.0, fator_total=None)
        sa = SimpleNamespace(activity_id="A1", distribuicao_semanal={"2024-W01": dist})
        equipe = SimpleNamespace(
            custo_mao_obra_mensal=5000.0,
            custo_equipamentos_mensal=2000.0,
            custo_material_mensal=0.0,
            custo_combustivel_total_mensal=1000.0,
            equipamentos=[],
        )
        custo, equip, n = _scb_collect_direct_costs([sa], {"A1": equipe})
        assert sum(custo.values()) == 0.0


# ---------------------------------------------------------------------------
# catalog_governance.py line 22: assert_catalog_healthy raises CatalogGovernanceError
# ---------------------------------------------------------------------------


class TestCatalogGovernanceAssertHealthy:
    def test_raises_when_errors_found(self):
        """Line 22: assert_catalog_healthy with errors → raises CatalogGovernanceError."""
        from unittest.mock import patch

        from concilium.application.orchestrators.catalog_governance import (
            CatalogGovernanceError,
            assert_catalog_healthy,
        )

        with patch(
            "concilium.application.orchestrators.catalog_governance.collect_catalog_critical_errors",
            return_value=[{"cpu": "CPU-01", "erro": "field missing"}],
        ):
            with pytest.raises(CatalogGovernanceError):
                assert_catalog_healthy("test-catalog", {})
