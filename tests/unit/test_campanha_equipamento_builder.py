"""Coverage batch 11 — campanha_equipamento_builder, diagnostico_pe_builder, conversor_unidades, equipe_custo_engine."""

from __future__ import annotations

from types import SimpleNamespace

# campanha_equipamento_builder.py line 36: continue when sa not in sched_lookup
# campanha_equipamento_builder.py line 39: continue when equip_id is empty
# campanha_equipamento_builder.py line 70: alertas.append (VAL-CAMP-01)
# campanha_equipamento_builder.py line 184: return self._regimes[tipo_id]
# ---------------------------------------------------------------------------


class TestCebCollectUsoPorTipo:
    def _call(self, canonical, sched_lookup):
        from concilium.domain.services.campaign.campanha_equipamento_builder import _ceb_collect_uso_por_tipo

        return _ceb_collect_uso_por_tipo(canonical, sched_lookup)

    def test_skips_equipe_when_sa_not_in_sched_lookup(self):
        """Line 36: equipe.item_id absent from sched_lookup → if not sa: continue."""
        equipe = SimpleNamespace(item_id="X1", equipamentos=[])
        canonical = SimpleNamespace(equipes_diretas=[equipe])
        result = self._call(canonical, {})
        assert dict(result) == {}

    def test_skips_equip_when_equip_id_is_empty(self):
        """Line 39: equip_id='' → if not equip.equip_id: continue."""
        equip = SimpleNamespace(equip_id="", num_unidades=1, custo_mensal=1000.0)
        equipe = SimpleNamespace(item_id="X1", equipamentos=[equip])
        sa = SimpleNamespace(start_week=1, end_week=4)
        canonical = SimpleNamespace(equipes_diretas=[equipe])
        result = self._call(canonical, {"X1": sa})
        assert dict(result) == {}

    def test_collects_valid_equip(self):
        """Normal path: valid equip_id adds entry to uso_por_tipo."""
        equip = SimpleNamespace(equip_id="EQ-01", num_unidades=2, custo_mensal=5000.0)
        equipe = SimpleNamespace(item_id="A1", equipamentos=[equip])
        sa = SimpleNamespace(start_week=1, end_week=4)
        canonical = SimpleNamespace(equipes_diretas=[equipe])
        result = self._call(canonical, {"A1": sa})
        assert "EQ-01" in result
        assert len(result["EQ-01"]) == 1


class TestCebGroupSortedUsos:
    def _call(self, sorted_usos, gap_limit, regime, tipo_id):
        from concilium.domain.services.campaign.campanha_equipamento_builder import _ceb_group_sorted_usos

        return _ceb_group_sorted_usos(sorted_usos, gap_limit, regime, tipo_id)

    def test_alerta_when_mob_cost_exceeds_standby_and_gap_within_threshold(self):
        """Line 70: gap>gap_limit, mob_cost>standby_cost, gap<=threshold → VAL-CAMP-01."""
        regime = SimpleNamespace(
            custo_standby_semanal=50.0,  # gap=5 semanas → standby = 250
            custo_mob=600.0,  # mob+demob = 1200 > 250
            custo_demob=600.0,
            threshold_dismissal=10,  # gap=5 <= 10
        )
        sorted_usos = [
            {"item_id": "A1", "start_week": 1, "end_week": 4},
            {"item_id": "A2", "start_week": 10, "end_week": 14},  # gap = 10-4-1 = 5
        ]
        groups, alertas = self._call(sorted_usos, gap_limit=0, regime=regime, tipo_id="EQ-ESCAVADEIRA")
        assert any("VAL-CAMP-01" in a for a in alertas)

    def test_no_alerta_when_mob_cost_below_standby(self):
        """No alert when standby is cheaper than mob+demob."""
        regime = SimpleNamespace(
            custo_standby_semanal=500.0,  # gap=5 → standby = 2500 > mob+demob
            custo_mob=100.0,
            custo_demob=100.0,
            threshold_dismissal=10,
        )
        sorted_usos = [
            {"item_id": "A1", "start_week": 1, "end_week": 4},
            {"item_id": "A2", "start_week": 10, "end_week": 14},
        ]
        groups, alertas = self._call(sorted_usos, gap_limit=0, regime=regime, tipo_id="EQ-ESCAVADEIRA")
        assert alertas == []


class TestCampanhaEquipamentoBuilderGetRegime:
    def test_returns_from_regimes_override_when_tipo_id_known(self):
        """Line 184: tipo_id in self._regimes → return self._regimes[tipo_id]."""
        from concilium.domain.models.campaign.campanha_equipamento import RegimePermanencia
        from concilium.domain.services.campaign.campanha_equipamento_builder import CampanhaEquipamentoBuilder

        regime = RegimePermanencia.estimado("EQ-CAMINHAO", 8000.0)
        builder = CampanhaEquipamentoBuilder(regimes_override={"EQ-CAMINHAO": regime})
        result = builder._get_regime("EQ-CAMINHAO", 8000.0)
        assert result is regime

    def test_falls_back_to_estimado_when_not_in_override(self):
        """Line 185: tipo_id not in self._regimes → RegimePermanencia.estimado(...)."""
        from concilium.domain.services.campaign.campanha_equipamento_builder import CampanhaEquipamentoBuilder

        builder = CampanhaEquipamentoBuilder(regimes_override={})
        result = builder._get_regime("EQ-UNKNOWN", 5000.0)
        assert result is not None


# ---------------------------------------------------------------------------

