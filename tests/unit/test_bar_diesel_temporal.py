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
