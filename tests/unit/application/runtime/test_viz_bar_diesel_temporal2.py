"""Expanded pytest coverage for bar_diesel_temporal.py — targets 80%+ coverage."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from concilium.application.runtime.deliverables.visualizations.cube.bar_diesel_temporal import (
    _week_months_contribution,
    _week_of_month_index,
    build,
)

# ---------------------------------------------------------------------------
# _week_of_month_index — boundary cases
# ---------------------------------------------------------------------------


class TestWeekOfMonthIndex:
    def test_day_1_is_always_wom1(self):
        # No matter what weekday the 1st falls on, day=1 is always WOM #1.
        for month in range(1, 13):
            d = date(2026, month, 1)
            assert _week_of_month_index(d) == 1, f"Failed for {d}"

    def test_first_saturday_of_month_is_wom1(self):
        # March 2026: the 1st is a Sunday, so first Saturday = March 7.
        assert _week_of_month_index(date(2026, 3, 7)) == 1

    def test_first_sunday_after_first_saturday_is_wom2(self):
        # March 8, 2026 (Sunday) is the first day of WOM #2.
        assert _week_of_month_index(date(2026, 3, 8)) == 2

    def test_wom2_saturday_still_wom2(self):
        # March 14 (Saturday) is still in WOM #2.
        assert _week_of_month_index(date(2026, 3, 14)) == 2

    def test_wom3_starts_next_sunday(self):
        # March 15 (Sunday) starts WOM #3.
        assert _week_of_month_index(date(2026, 3, 15)) == 3

    def test_wom5_at_month_end(self):
        # March 2026 has a WOM#5 (29–31).
        assert _week_of_month_index(date(2026, 3, 29)) == 5
        assert _week_of_month_index(date(2026, 3, 31)) == 5

    def test_month_starting_on_monday(self):
        # June 2026: the 1st is a Monday.
        # First Saturday = June 6 → WOM#1; June 7 (Sunday) → WOM#2.
        assert _week_of_month_index(date(2026, 6, 1)) == 1
        assert _week_of_month_index(date(2026, 6, 6)) == 1
        assert _week_of_month_index(date(2026, 6, 7)) == 2

    def test_month_starting_on_saturday(self):
        # August 2026: the 1st is a Saturday → first_week_end = Aug 1.
        # So WOM#1 is only Aug 1; Aug 2 (Sunday) is WOM#2.
        assert _week_of_month_index(date(2026, 8, 1)) == 1
        assert _week_of_month_index(date(2026, 8, 2)) == 2


# ---------------------------------------------------------------------------
# _week_months_contribution — proportion and total invariants
# ---------------------------------------------------------------------------


class TestWeekMonthsContribution:
    def test_week_entirely_within_one_month_sums_to_fuel(self):
        # 2026-W10: Mon March 2 – Sun March 8. Entirely in March 2026.
        fuel = 700.0
        portions = _week_months_contribution("2026-W10", fuel)
        assert abs(sum(portions.values()) - fuel) < 1e-9
        # All days in March, so only one bucket family
        buckets = {k[0] for k in portions}
        assert buckets == {"2026-03"}

    def test_week_entirely_within_one_month_per_day_portion(self):
        # Each of the 7 days should contribute fuel/7.
        fuel = 70.0
        portions = _week_months_contribution("2026-W10", fuel)
        # Sum of all portions equals fuel
        assert abs(sum(portions.values()) - fuel) < 1e-9

    def test_week_spanning_month_boundary_splits_correctly(self):
        # 2026-W14: Mon March 30 – Sun April 5.
        # Mon March 30 = WOM#5 in March, Tue March 31 = WOM#5 in March → 2 days in March
        # Wed April 1 – Sun April 5 → 5 days in April (all WOM#1)
        fuel = 70.0
        per_day = fuel / 7.0
        portions = _week_months_contribution("2026-W14", fuel)

        # Total must be preserved
        assert abs(sum(portions.values()) - fuel) < 1e-9

        # March portion: 2 days * per_day
        march_total = sum(v for (b, _), v in portions.items() if b == "2026-03")
        april_total = sum(v for (b, _), v in portions.items() if b == "2026-04")
        assert abs(march_total - 2 * per_day) < 1e-9
        assert abs(april_total - 5 * per_day) < 1e-9

    def test_week_spanning_month_boundary_has_both_buckets(self):
        portions = _week_months_contribution("2026-W14", 100.0)
        buckets = {k[0] for k in portions}
        assert "2026-03" in buckets
        assert "2026-04" in buckets

    def test_all_7_day_portions_sum_to_fuel_total(self):
        # Use a week that might hit year boundary: 2025-W01 starts Jan 1, 2025
        # (a Wednesday), so Mon Dec 30 2024 – Sun Jan 5 2025.
        fuel = 350.0
        portions = _week_months_contribution("2025-W01", fuel)
        assert abs(sum(portions.values()) - fuel) < 1e-9

    def test_zero_fuel_produces_zero_portions(self):
        portions = _week_months_contribution("2026-W10", 0.0)
        assert all(v == 0.0 for v in portions.values())

    def test_negative_fuel_preserved_in_total(self):
        # Edge case: negative fuel (unlikely in production, but function is pure).
        fuel = -70.0
        portions = _week_months_contribution("2026-W10", fuel)
        assert abs(sum(portions.values()) - fuel) < 1e-9


# ---------------------------------------------------------------------------
# build() — top-level function
# ---------------------------------------------------------------------------


def _make_celula(semana_iso: str, consumo_diesel_L: float):
    return SimpleNamespace(semana_iso=semana_iso, consumo_diesel_L=consumo_diesel_L)


def _fake_init_mpl():
    """Return a fake (plt, fig_to_bytes) pair that avoids real matplotlib."""
    mock_bar = MagicMock()
    mock_bar.get_y.return_value = 0.0
    mock_bar.get_height.return_value = 0.5
    mock_bar.get_x.return_value = 0.0
    mock_bar.get_width.return_value = 0.7

    mock_ax = MagicMock()
    mock_ax.bar.return_value = [mock_bar]

    mock_fig = MagicMock()

    mock_plt = MagicMock()
    mock_plt.subplots.return_value = (mock_fig, mock_ax)

    def fig_to_bytes(fig):  # noqa: ARG001
        return b"PNG"

    return mock_plt, fig_to_bytes


class TestBuild:
    def test_returns_none_when_cubo_celulas_is_empty(self):
        cubo = SimpleNamespace(celulas=[])
        canonical = SimpleNamespace()
        with patch(
            "concilium.application.runtime.deliverables.visualizations.cube.bar_diesel_temporal.init_mpl",
            side_effect=_fake_init_mpl,
        ):
            result = build(canonical, cubo)
        assert result is None

    def test_returns_none_when_cubo_has_no_celulas_attr(self):
        cubo = SimpleNamespace()  # no .celulas attribute
        canonical = SimpleNamespace()
        with patch(
            "concilium.application.runtime.deliverables.visualizations.cube.bar_diesel_temporal.init_mpl",
            side_effect=_fake_init_mpl,
        ):
            result = build(canonical, cubo)
        assert result is None

    def test_returns_none_when_all_diesel_zero(self):
        cubo = SimpleNamespace(
            celulas=[
                _make_celula("2026-W10", 0.0),
                _make_celula("2026-W11", 0.0),
            ]
        )
        canonical = SimpleNamespace()
        with patch(
            "concilium.application.runtime.deliverables.visualizations.cube.bar_diesel_temporal.init_mpl",
            side_effect=_fake_init_mpl,
        ):
            result = build(canonical, cubo)
        assert result is None

    def test_returns_bytes_when_fuel_positive(self):
        cubo = SimpleNamespace(
            celulas=[
                _make_celula("2026-W10", 1000.0),
            ]
        )
        canonical = SimpleNamespace()
        with patch(
            "concilium.application.runtime.deliverables.visualizations.cube.bar_diesel_temporal.init_mpl",
            side_effect=_fake_init_mpl,
        ):
            result = build(canonical, cubo)
        assert isinstance(result, bytes)
        assert result == b"PNG"

    def test_uses_canonical_fallback_when_cube_diesel_is_zero(self):
        # cubo sem litros monetários; fallback físico usa cronograma + equipes.
        cubo = SimpleNamespace(celulas=[_make_celula("2026-W10", 0.0)])
        canonical = SimpleNamespace(
            projeto=SimpleNamespace(regime_trabalho=SimpleNamespace(horas_dia=10, dias_semana=6)),
            cronograma=SimpleNamespace(
                scheduled_activities=[
                    SimpleNamespace(
                        activity_id="act-1",
                        distribuicao_semanal={
                            "2026-W10": SimpleNamespace(num_equipes=1, eficiencia=1.0),
                        },
                    )
                ]
            ),
            equipes_diretas=[
                SimpleNamespace(
                    item_id="act-1",
                    equipamentos=[
                        SimpleNamespace(consumo_litros_hora=10.0, num_unidades=1),
                    ],
                )
            ],
        )
        with patch(
            "concilium.application.runtime.deliverables.visualizations.cube.bar_diesel_temporal.init_mpl",
            side_effect=_fake_init_mpl,
        ):
            result = build(canonical, cubo)
        assert isinstance(result, bytes)

    def test_returns_bytes_with_multiple_weeks_across_months(self):
        cubo = SimpleNamespace(
            celulas=[
                _make_celula("2026-W10", 500.0),
                _make_celula("2026-W14", 700.0),  # crosses March/April boundary
                _make_celula("2026-W18", 300.0),
            ]
        )
        canonical = SimpleNamespace()
        with patch(
            "concilium.application.runtime.deliverables.visualizations.cube.bar_diesel_temporal.init_mpl",
            side_effect=_fake_init_mpl,
        ):
            result = build(canonical, cubo)
        assert isinstance(result, bytes)

    def test_returns_none_when_import_error(self):
        cubo = SimpleNamespace(celulas=[_make_celula("2026-W10", 100.0)])
        canonical = SimpleNamespace()
        with patch(
            "concilium.application.runtime.deliverables.visualizations.cube.bar_diesel_temporal.init_mpl",
            side_effect=ImportError("no matplotlib"),
        ):
            result = build(canonical, cubo)
        assert result is None

    def test_mix_of_zero_and_nonzero_fuel_returns_bytes(self):
        cubo = SimpleNamespace(
            celulas=[
                _make_celula("2026-W10", 0.0),
                _make_celula("2026-W11", 800.0),
                _make_celula("2026-W12", 0.0),
            ]
        )
        canonical = SimpleNamespace()
        with patch(
            "concilium.application.runtime.deliverables.visualizations.cube.bar_diesel_temporal.init_mpl",
            side_effect=_fake_init_mpl,
        ):
            result = build(canonical, cubo)
        assert isinstance(result, bytes)

    def test_none_consumo_diesel_treated_as_zero(self):
        # consumo_diesel_L = None should be treated as 0.0 (not raise)
        cubo = SimpleNamespace(
            celulas=[
                _make_celula("2026-W10", None),
            ]
        )
        canonical = SimpleNamespace()
        with patch(
            "concilium.application.runtime.deliverables.visualizations.cube.bar_diesel_temporal.init_mpl",
            side_effect=_fake_init_mpl,
        ):
            result = build(canonical, cubo)
        # All cells produce 0 fuel → empty monthly_wom → None
        assert result is None

    def test_celulas_none_returns_none(self):
        # cubo.celulas = None
        cubo = SimpleNamespace(celulas=None)
        canonical = SimpleNamespace()
        with patch(
            "concilium.application.runtime.deliverables.visualizations.cube.bar_diesel_temporal.init_mpl",
            side_effect=_fake_init_mpl,
        ):
            result = build(canonical, cubo)
        assert result is None

    def test_fallback_zero_eficiencia_week_is_skipped(self):
        # A fallback week with eficiencia=0.0 yields exactly 0 liters, which
        # must be skipped by the `if liters <= 0: continue` guard rather than
        # contributing an empty bucket. A second week with real consumption
        # keeps monthly_wom non-empty so we exercise both branches.
        cubo = SimpleNamespace(celulas=[_make_celula("2026-W10", 0.0)])
        canonical = SimpleNamespace(
            projeto=SimpleNamespace(regime_trabalho=SimpleNamespace(horas_dia=10, dias_semana=6)),
            cronograma=SimpleNamespace(
                scheduled_activities=[
                    SimpleNamespace(
                        activity_id="act-1",
                        distribuicao_semanal={
                            "2026-W10": SimpleNamespace(num_equipes=1, eficiencia=0.0),
                            "2026-W11": SimpleNamespace(num_equipes=1, eficiencia=1.0),
                        },
                    )
                ]
            ),
            equipes_diretas=[
                SimpleNamespace(
                    item_id="act-1",
                    equipamentos=[
                        SimpleNamespace(consumo_litros_hora=10.0, num_unidades=1),
                    ],
                )
            ],
        )
        with patch(
            "concilium.application.runtime.deliverables.visualizations.cube.bar_diesel_temporal.init_mpl",
            side_effect=_fake_init_mpl,
        ):
            result = build(canonical, cubo)
        assert isinstance(result, bytes)

    def test_returns_none_on_unexpected_exception(self):
        # Simulate a downstream error after init_mpl succeeds
        cubo = SimpleNamespace(celulas=[_make_celula("bad-week", 100.0)])
        canonical = SimpleNamespace()
        with patch(
            "concilium.application.runtime.deliverables.visualizations.cube.bar_diesel_temporal.init_mpl",
            side_effect=_fake_init_mpl,
        ):
            # "bad-week" is not a valid ISO week string → ValueError inside the try block
            result = build(canonical, cubo)
        assert result is None

    def test_fallback_week_with_zero_num_unidades_yields_zero_liters_and_is_skipped(self):
        # num_unidades=0 makes the per-equipment litros computation exactly 0.0,
        # which still lands an entry in the fallback dict (defaultdict += 0.0),
        # exercising the `if liters <= 0: continue` guard in build(). A second
        # week with real equipment keeps monthly_wom non-empty.
        cubo = SimpleNamespace(celulas=[_make_celula("2026-W10", 0.0), _make_celula("2026-W11", 0.0)])
        canonical = SimpleNamespace(
            projeto=SimpleNamespace(regime_trabalho=SimpleNamespace(horas_dia=10, dias_semana=6)),
            cronograma=SimpleNamespace(
                scheduled_activities=[
                    SimpleNamespace(
                        activity_id="act-1",
                        distribuicao_semanal={
                            "2026-W10": SimpleNamespace(num_equipes=1, eficiencia=1.0),
                            "2026-W11": SimpleNamespace(num_equipes=1, eficiencia=1.0),
                        },
                    )
                ]
            ),
            equipes_diretas=[
                SimpleNamespace(
                    item_id="act-1",
                    equipamentos=[
                        SimpleNamespace(consumo_litros_hora=10.0, num_unidades=0),
                    ],
                )
            ],
        )
        with patch(
            "concilium.application.runtime.deliverables.visualizations.cube.bar_diesel_temporal.init_mpl",
            side_effect=_fake_init_mpl,
        ):
            result = build(canonical, cubo)
        # Both weeks yield 0 liters → monthly_wom stays empty → None.
        assert result is None
