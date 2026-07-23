from __future__ import annotations

from datetime import date

from concilium.application.runtime.deliverables.visualizations.cube.bar_diesel_temporal import (
    _week_months_contribution,
    _week_of_month_index,
)


def test_week_of_month_index_keeps_wom5():
    assert _week_of_month_index(date(2026, 3, 1)) == 1
    assert _week_of_month_index(date(2026, 3, 7)) == 1
    assert _week_of_month_index(date(2026, 3, 8)) == 2
    assert _week_of_month_index(date(2026, 3, 28)) == 4
    assert _week_of_month_index(date(2026, 3, 29)) == 5
    assert _week_of_month_index(date(2026, 3, 31)) == 5


def test_week_months_contribution_preserves_total_and_wom5_when_crossing_month_end():
    portions = _week_months_contribution("2026-W14", 70.0)

    assert round(sum(portions.values()), 6) == 70.0
    assert ("2026-03", 5) in portions
    assert portions[("2026-03", 5)] > 0.0


from types import SimpleNamespace  # noqa: E402

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

