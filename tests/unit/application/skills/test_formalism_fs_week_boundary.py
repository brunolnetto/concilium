"""P15 runtime falsifiers: physical Q–FS releases occur at ISO week boundaries."""
from __future__ import annotations

import sys
from dataclasses import dataclass, replace
from datetime import date
from fractions import Fraction
from types import SimpleNamespace

import pytest

WEEKS = ["2026-W01", "2026-W02", "2026-W03", "2026-W04"]


def _scheduling():
    from concilium.application.skills import run_cronograma

    assert run_cronograma
    return sys.modules["_concilium_skillpkg_04_cronograma.skill"]._mod_scheduling


def _cell(q: int, cached: int) -> SimpleNamespace:
    return SimpleNamespace(qtd_executada=q, qtd_acumulada=cached)


def _release(distribution, threshold: float, lag: int = 0) -> int | None:
    return _scheduling()._release_fs_after_physical_delivery(
        distribution,
        physical_threshold=threshold,
        lag_weeks=lag,
        semanas_obra=WEEKS,
        data_inicio=date(2026, 1, 1),
    )


def test_threshold_met_in_week_one_releases_only_at_next_boundary() -> None:
    assert _release({WEEKS[0]: _cell(10, 10)}, 10) == 1
    assert _release({WEEKS[0]: _cell(10, 10)}, 10, lag=2) == 3


def test_first_zero_production_week_cannot_release_positive_threshold() -> None:
    distribution = {
        WEEKS[0]: _cell(0, 10),  # stale or fabricated cached accumulation
        WEEKS[1]: _cell(10, 10),
    }
    assert _release(distribution, 10) == 2
    assert _release(distribution, 11) is None


def test_zero_threshold_is_start_to_start_without_extra_week() -> None:
    distribution = {WEEKS[0]: _cell(0, 0), WEEKS[1]: _cell(10, 10)}
    assert _release(distribution, 0) == 0
    assert _release(distribution, 0, lag=1) == 1


@pytest.mark.parametrize(
    ("q", "lag", "match"),
    [(-1, 0, "negative"), (10, -1, "lag"), (10, 0.5, "lag")],
)
def test_invalid_physical_predecessor_input_fails_closed(q, lag, match) -> None:
    with pytest.raises(ValueError, match=match):
        _release({WEEKS[0]: _cell(q, q)}, 10, lag=lag)



def test_exact_rational_scope_threshold_does_not_release_one_week_early() -> None:
    # Q=0.7, theta=0.1 => threshold=0.07 exactly, while the first
    # week's output is one decimal digit below that physical threshold.
    threshold = Fraction("0.7") * Fraction("0.1")
    distribution = {
        WEEKS[0]: SimpleNamespace(qtd_executada="0.06999999999999999"),
        WEEKS[1]: SimpleNamespace(qtd_executada="0.00000000000000001"),
    }
    assert _release(distribution, threshold) == 2


def test_missing_interior_calendar_week_is_rejected() -> None:
    with pytest.raises(ValueError, match="missing ISO weeks"):
        _release({WEEKS[0]: _cell(1, 1), WEEKS[2]: _cell(9, 10)}, 10)


@dataclass(frozen=True)
class _FakeActivity:
    activity_id: str
    start_week: int
    ramp_profile: tuple = ()

    def model_copy(self, *, update):
        return replace(self, **update)


def test_runtime_conversion_moves_successor_after_physical_week_not_same_week(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise the real _convert_schedule_to_distribuicao control flow."""
    mod = _scheduling()
    items = {
        "A": SimpleNamespace(item_id="A", quantitativo=10, predecessores_tipados=lambda: []),
        "B": SimpleNamespace(
            item_id="B", quantitativo=1,
            predecessores_tipados=lambda: [
                SimpleNamespace(item_id="A", tipo="FS", lag=0, completion_threshold_pct=1)
            ],
        ),
    }
    candidate = SimpleNamespace(
        scheduled_activities=(_FakeActivity("A", 0), _FakeActivity("B", 1))
    )
    observed = {}
    monkeypatch.setattr(mod, "_build_activity_item_map", lambda _: {"A": "A", "B": "B"})
    monkeypatch.setattr(
        mod, "_resolve_item_for_scheduled_activity",
        lambda sa, *_: (sa.activity_id, items[sa.activity_id]),
    )
    monkeypatch.setattr(mod, "_find_item_by_id", lambda _, item_id: items[item_id])
    monkeypatch.setattr(mod, "_resolve_cpu_for_item", lambda *_: {})
    monkeypatch.setattr(mod, "_resolve_productivity", lambda *_: (1.0, False))
    monkeypatch.setattr(mod, "_compute_activity_n_max", lambda *_: 1)
    monkeypatch.setattr(mod, "_warn_if_activity_underdelivers", lambda *_args, **_kw: None)
    monkeypatch.setattr(mod, "_origem_capacidade", lambda *_args, **_kw: None)

    def materialize(sa, *_args, **_kwargs):
        observed[sa.activity_id] = sa.start_week
        if sa.activity_id == "A":
            return {
                WEEKS[0]: _cell(0, 10),  # forged cached Q must not affect release
                WEEKS[1]: _cell(10, 10),
            }, 10
        return {WEEKS[sa.start_week]: _cell(1, 1)}, 1

    monkeypatch.setattr(mod, "_build_activity_distribuicao", materialize)
    canonical = SimpleNamespace(
        eap=list(items.values()), projeto=SimpleNamespace(data_inicio=date(2026, 1, 1))
    )
    regime = SimpleNamespace(horas_dia=8, dias_semana=5, eta_jornada=1)
    validacoes = []
    result, _ = mod._convert_schedule_to_distribuicao(
        candidate, canonical, WEEKS, {}, {}, regime,
        {}, {}, {}, validacoes,
    )
    assert observed == {"A": 0, "B": 2}
    assert WEEKS[2] in result["B"]
