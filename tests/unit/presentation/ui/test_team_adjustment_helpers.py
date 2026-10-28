"""Workforce UI helpers preserve integer physical team-count semantics."""

from __future__ import annotations

import pytest

from concilium.presentation.ui.helpers.helpers import (
    apply_global_team_adjustment,
    build_num_equipes_override,
    build_team_adjustment_rows,
)


def _reference_with_weekly_counts(counts: dict[str, int | float]) -> dict:
    return {
        "cronograma": {
            "atividades": [
                {
                    "item_id": "eap-01",
                    "descricao": "Escavação",
                    "semanas": {
                        week: {"num_equipes": count}
                        for week, count in counts.items()
                    },
                }
            ]
        }
    }


def test_team_adjustment_rows_keep_average_analytic_and_peak_integral() -> None:
    rows = build_team_adjustment_rows(
        _reference_with_weekly_counts(
            {"2026-W01": 1, "2026-W02": 2, "2026-W03": 3}
        )
    )

    assert len(rows) == 1
    assert rows[0]["num_equipes_base"] == 2.0
    assert rows[0]["num_equipes_maximo"] == 3
    assert type(rows[0]["num_equipes_maximo"]) is int


def test_team_adjustment_rows_reject_fractional_physical_counts() -> None:
    with pytest.raises(ValueError, match="nonnegative integer team count"):
        build_team_adjustment_rows(
            _reference_with_weekly_counts({"2026-W01": 1.5})
        )


def test_team_adjustment_rows_reject_non_finite_physical_counts() -> None:
    with pytest.raises(ValueError, match="nonnegative integer team count"):
        build_team_adjustment_rows(
            _reference_with_weekly_counts({"2026-W01": float("inf")})
        )


def test_manual_team_override_emits_integer_count_only_on_active_weeks() -> None:
    reference = _reference_with_weekly_counts(
        {"2026-W01": 1, "2026-W02": 0, "2026-W03": 3}
    )

    override = build_num_equipes_override(
        reference,
        [{"item_id": "eap-01", "num_equipes_maximo": 4}],
    )

    assert override == {
        "eap-01": {"2026-W01": 4, "2026-W03": 4}
    }
    assert all(
        type(count) is int
        for weekly in override.values()
        for count in weekly.values()
    )


def test_manual_team_override_rejects_fractional_ceiling() -> None:
    reference = _reference_with_weekly_counts({"2026-W01": 1})
    with pytest.raises(ValueError, match="nonnegative integer team count"):
        build_num_equipes_override(
            reference,
            [{"item_id": "eap-01", "num_equipes_maximo": 1.5}],
        )


def test_global_adjustment_rounds_the_integral_peak_not_the_average() -> None:
    rows = [{"num_equipes_base": 1.5, "num_equipes_maximo": 3}]

    adjusted = apply_global_team_adjustment(rows, 40.0)

    assert adjusted[0]["num_equipes_base"] == 1.5
    assert adjusted[0]["num_equipes_maximo"] == 4
    assert type(adjusted[0]["num_equipes_maximo"]) is int


def test_global_adjustment_rejects_non_finite_percentage() -> None:
    with pytest.raises(ValueError, match="percentage must be finite"):
        apply_global_team_adjustment(
            [{"num_equipes_maximo": 3}], float("nan")
        )
