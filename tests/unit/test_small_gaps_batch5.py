"""Coverage batch 5 — visualization normalization, diesel fallback, and other small gaps."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# pool_custo_estado.py lines 31, 40-42: normalize key fallbacks
# ---------------------------------------------------------------------------


class TestPoolCustoEstadoNormalizeKeys:
    def _comp(self, raw):
        from concilium.application.runtime.deliverables.visualizations.cube.pool_custo_estado import (
            _normalize_component_key,
        )

        return _normalize_component_key(raw)

    def _state(self, raw):
        from concilium.application.runtime.deliverables.visualizations.cube.pool_custo_estado import (
            _normalize_state_key,
        )

        return _normalize_state_key(raw)

    def test_unknown_component_returns_raw(self):
        """Line 31: no match → return txt as-is."""
        assert self._comp("unknown_comp") == "unknown_comp"

    def test_normalize_off_state(self):
        """Lines 40-41: 'off' → 'off'."""
        assert self._state("off") == "off"

    def test_normalize_desmobilizado_state(self):
        """Lines 40-41: 'desmobilizado' → 'off'."""
        assert self._state("desmobilizado") == "off"

    def test_unknown_state_returns_raw(self):
        """Line 42: no state match → return txt as-is."""
        assert self._state("unknown_state") == "unknown_state"


# ---------------------------------------------------------------------------
# bar_diesel_temporal.py: _fallback_liters_from_canonical missing line paths
# ---------------------------------------------------------------------------


class TestDieselFallbackMissingLines:
    def _fn(self):
        from concilium.application.runtime.deliverables.visualizations.cube.bar_diesel_temporal import (
            _fallback_liters_from_canonical,
        )

        return _fallback_liters_from_canonical

    def test_horas_semana_zero_returns_empty(self):
        """Line 20: horas_semana <= 0 → return {}."""
        fallback = self._fn()
        regime = SimpleNamespace(horas_dia=0, dias_semana=0)
        projeto = SimpleNamespace(regime_trabalho=regime)
        sa = SimpleNamespace(activity_id="A1", distribuicao_semanal={})
        cron = SimpleNamespace(scheduled_activities=[sa])
        canonical = SimpleNamespace(
            cronograma=cron,
            equipes_diretas=[SimpleNamespace(item_id="A1", equipamentos=[])],
            projeto=projeto,
        )
        assert fallback(canonical) == {}

    def test_sa_activity_id_not_in_equipes_skipped(self):
        """Line 27: sa.activity_id not in equipes by_item → continue."""
        fallback = self._fn()
        regime = SimpleNamespace(horas_dia=8, dias_semana=5)
        projeto = SimpleNamespace(regime_trabalho=regime)
        sa = SimpleNamespace(activity_id="B1", distribuicao_semanal={})  # "B1" not in equipes
        cron = SimpleNamespace(scheduled_activities=[sa])
        equipe = SimpleNamespace(item_id="A1", equipamentos=[])
        canonical = SimpleNamespace(cronograma=cron, equipes_diretas=[equipe], projeto=projeto)
        result = fallback(canonical)
        assert result == {}

    def test_num_equipes_zero_skipped(self):
        """Line 31: n_eq <= 0 → continue."""
        fallback = self._fn()
        regime = SimpleNamespace(horas_dia=8, dias_semana=5)
        projeto = SimpleNamespace(regime_trabalho=regime)
        dist = SimpleNamespace(num_equipes=0, eficiencia=1.0)
        sa = SimpleNamespace(activity_id="A1", distribuicao_semanal={"2024-W10": dist})
        cron = SimpleNamespace(scheduled_activities=[sa])
        equipe = SimpleNamespace(item_id="A1", equipamentos=[])
        canonical = SimpleNamespace(cronograma=cron, equipes_diretas=[equipe], projeto=projeto)
        assert fallback(canonical) == {}

    def test_consumo_litros_hora_zero_skipped(self):
        """Line 36: consumo_lh <= 0 → continue."""
        fallback = self._fn()
        regime = SimpleNamespace(horas_dia=8, dias_semana=5)
        projeto = SimpleNamespace(regime_trabalho=regime)
        dist = SimpleNamespace(num_equipes=2, eficiencia=1.0)
        equip = SimpleNamespace(consumo_litros_hora=0.0, num_unidades=1)
        sa = SimpleNamespace(activity_id="A1", distribuicao_semanal={"2024-W10": dist})
        cron = SimpleNamespace(scheduled_activities=[sa])
        equipe = SimpleNamespace(item_id="A1", equipamentos=[equip])
        canonical = SimpleNamespace(cronograma=cron, equipes_diretas=[equipe], projeto=projeto)
        assert fallback(canonical) == {}


# ---------------------------------------------------------------------------
# cubo_analitico_builder.py line 88: n_equipes <= 0 → return []
# ---------------------------------------------------------------------------


class TestCabCollectCelulasSemanaZeroEquipes:
    def test_n_equipes_zero_returns_empty(self):
        """Line 88: n_equipes <= 0 → return []."""
        from concilium.domain.services.analytics.cubo_analitico_builder import _cab_collect_celulas_semana

        dist = SimpleNamespace(num_equipes=0, eficiencia=1.0)
        equipe = MagicMock()
        result = _cab_collect_celulas_semana(equipe, "A1", "2024-W01", dist, 0.0, {}, {}, 0.0)
        assert result == []


# ---------------------------------------------------------------------------
# cubo_analitico_builder.py lines 380, 386, 389: _build_diesel_L_map paths
# ---------------------------------------------------------------------------


class TestCuboBuildDieselLMap:
    def _builder(self):
        from concilium.domain.services.analytics.cubo_analitico_builder import CuboAnaliticoBuilder

        return CuboAnaliticoBuilder()

    def test_no_cronograma_returns_empty(self):
        """Line 380: cronograma is None → return {}."""
        builder = self._builder()
        canonical = SimpleNamespace(cronograma=None, equipes_diretas=[])
        result = builder._build_diesel_L_map(canonical)
        assert result == {}

    def test_sa_not_found_for_equipe_skipped(self):
        """Line 386: sa not found for equipe.item_id → continue."""
        builder = self._builder()
        sa = SimpleNamespace(
            activity_id="A1", distribuicao_semanal={"2024-W01": SimpleNamespace(num_equipes=2, eficiencia=1.0)}
        )
        cron = SimpleNamespace(scheduled_activities=[sa])
        equipe = SimpleNamespace(item_id="B1", equipamentos=[])
        canonical = SimpleNamespace(cronograma=cron, equipes_diretas=[equipe])
        result = builder._build_diesel_L_map(canonical)
        assert result == {}

    def test_zero_consumo_base_skipped(self):
        """Line 389: consumo_base <= 0 → continue."""
        builder = self._builder()
        sa = SimpleNamespace(
            activity_id="A1", distribuicao_semanal={"2024-W01": SimpleNamespace(num_equipes=2, eficiencia=1.0)}
        )
        cron = SimpleNamespace(scheduled_activities=[sa])
        equipe = SimpleNamespace(
            item_id="A1",
            equipamentos=[
                SimpleNamespace(consumo_litros_hora=0.0, num_unidades=0, tipo_combustivel=None, equip_id="EQ-X")
            ],
        )
        canonical = SimpleNamespace(cronograma=cron, equipes_diretas=[equipe])
        result = builder._build_diesel_L_map(canonical)
        assert result == {}


# ---------------------------------------------------------------------------
# pool_ciclo_vida.py line 49: _draw_row with idle_w > 0
# ---------------------------------------------------------------------------


class TestPoolCicloVidaDrawRowWithIdle:
    def test_idle_w_gt_zero_draws_idle_bar(self):
        """Line 49: idle_w > 0 → ax.barh called for idle."""
        from concilium.application.runtime.deliverables.visualizations.cube.pool_ciclo_vida import _draw_row

        ax = MagicMock()
        row = {"prod_w": 5, "idle_w": 2, "off_w": 1, "custo_total": 500_000}
        _draw_row(ax, 0, row)
        assert ax.barh.call_count == 2


# ---------------------------------------------------------------------------
# bar_tempo_direto_categoria.py lines 42-43 and bar_tempo_indireto_categoria.py 42-43
# inner matplotlib cleanup in except Exception path
# ---------------------------------------------------------------------------


class TestBarTempoCategoriaMplCleanup:
    def test_direto_outer_exception_triggers_cleanup(self):
        """Lines 42-43: outer rendering exception → matplotlib close called."""
        import concilium.application.runtime.deliverables.visualizations.cube.bar_tempo_direto_categoria as mod

        canonical = MagicMock()
        cubo = MagicMock()

        with patch.object(mod, "build_payload", return_value={"rows": [{"a": 1}], "columns": ["a"]}):
            with patch.object(mod, "init_mpl", return_value=(MagicMock(), MagicMock())):
                with patch.object(mod, "render_stacked_bar", side_effect=RuntimeError("boom")):
                    result = mod.build(canonical, cubo)
        assert result is None

    def test_indireto_outer_exception_triggers_cleanup(self):
        """Lines 42-43 indireto: outer rendering exception → matplotlib close called."""
        import concilium.application.runtime.deliverables.visualizations.cube.bar_tempo_indireto_categoria as mod

        canonical = MagicMock()
        cubo = MagicMock()

        with patch.object(mod, "build_payload", return_value={"rows": [{"a": 1}], "columns": ["a"]}):
            with patch.object(mod, "init_mpl", return_value=(MagicMock(), MagicMock())):
                with patch.object(mod, "render_stacked_bar", side_effect=RuntimeError("boom")):
                    result = mod.build(canonical, cubo)
        assert result is None
