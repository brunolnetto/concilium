"""Coverage batch 9 — validador_cobertura_item, cubo_pool_builder, eficiencia_field_builder,
s_curve_builder, catalog_governance."""

from __future__ import annotations

from types import SimpleNamespace

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

