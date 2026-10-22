"""P12-A independent proof vectors: weekly boundary, calendar and resource demand.

These tests deliberately implement a minimal pure-Python mathematical oracle,
not the scheduling runtime. They do not certify #15 RCPSP integration.
"""
from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import pytest

DOCS = Path(__file__).resolve().parents[2] / "docs/product/5-specifications/formulario_longo"
FORMATS = (
    DOCS / "FORMALISMO_LONGO.md",
    DOCS / "FORMALISMO_RESUMIDO.md",
    DOCS / "formulario_longo.tex",
)


def _exact(value: int | str | Fraction) -> Fraction:
    return Fraction(value)


def least_duration(
    start: int, scope: Fraction, nominal: Fraction, practicability: tuple[Fraction, ...]
) -> int | None:
    """Enumerate a bounded absolute calendar (weeks numbered from 1)."""
    if start < 1 or start > len(practicability) or scope <= 0 or nominal <= 0:
        return None
    total = Fraction(0)
    for index in range(start - 1, len(practicability)):
        total += nominal * practicability[index]
        if total >= scope:
            return index - (start - 1) + 1
    return None


def release_week(
    quantities: tuple[Fraction, ...], scope: Fraction, theta: Fraction, lag: int = 0
) -> int | None:
    """Q-FS: threshold measured at week END releases next week plus lag."""
    if scope <= 0 or theta <= 0 or theta > 1 or lag < 0 or any(q < 0 for q in quantities):
        raise ValueError("invalid physical predecessor")
    cumulative = Fraction(0)
    for week, delivered in enumerate(quantities, start=1):
        cumulative += delivered
        if cumulative >= theta * scope:
            return week + 1 + lag
    return None


@pytest.mark.parametrize(
    ("start", "expected"),
    [(1, 2), (2, 1), (3, 1)],
)
def test_start_week_changes_required_duration(start: int, expected: int) -> None:
    factors = (_exact(0), _exact(1), _exact(1))
    assert least_duration(start, _exact(100), _exact(100), factors) == expected


def test_zero_future_capacity_fails_bounded_horizon() -> None:
    assert least_duration(1, _exact(1), _exact(40), (_exact(0),) * 5) is None


@pytest.mark.parametrize(
    ("theta", "lag", "expected"),
    [
        ("1/2", 0, 3),  # 60/100 reached at END of week 2
        ("1", 0, 4),    # 100/100 reached at END of week 3
        ("1/2", 2, 5),
    ],
)
def test_physical_predecessor_release_is_next_week(
    theta: str, lag: int, expected: int
) -> None:
    assert release_week(
        (_exact(0), _exact(60), _exact(40)), _exact(100), _exact(theta), lag
    ) == expected


def test_zero_productivity_never_releases_quantity_predecessor() -> None:
    assert release_week((_exact(0),) * 3, _exact(100), _exact(1)) is None


def test_exact_threshold_equality_releases_only_following_week() -> None:
    assert release_week((_exact(50), _exact(50)), _exact(100), _exact("1/2")) == 2


@pytest.mark.parametrize(("theta", "lag"), [("0", 0), ("6/5", 0), ("1/2", -1)])
def test_invalid_precedence_contract_is_rejected(theta: str, lag: int) -> None:
    with pytest.raises(ValueError):
        release_week((_exact(10),), _exact(10), _exact(theta), lag)


def capacity_feasible(demand: tuple[int, ...], weekly_available: tuple[int, ...]) -> bool:
    return len(demand) == len(weekly_available) and all(
        0 <= d <= c for d, c in zip(demand, weekly_available, strict=True)
    )


def test_shifted_successors_cannot_overallocate_shared_resource() -> None:
    # Two independent successors both moved into week 3, only one unit exists.
    available = (1, 1, 1, 1)
    bad = (0, 0, 2, 0)
    rerouted = (0, 0, 1, 1)
    assert not capacity_feasible(bad, available)
    assert capacity_feasible(rerouted, available)


def test_scheduled_week_zero_production_does_not_change_installed_rate() -> None:
    productivity = _exact(10)
    hours = _exact(40)
    installed = productivity * hours
    assert installed == 400
    assert installed * _exact(0) == 0


def test_three_representations_reference_same_contract() -> None:
    contract = DOCS / "CALENDARIO_E_LIBERACAO_FISICA.md"
    assert contract.exists()
    contract_text = contract.read_text(encoding="utf-8")
    for marker in ("Pi_i", "theta", "INFEASIBLE"):
        # The source spells symbols in LaTeX; markers are checked below.
        assert marker in contract_text or marker.replace("Pi_i", r"\Pi_i") in contract_text
    for path in FORMATS:
        text = path.read_text(encoding="utf-8")
        assert "CALENDARIO_E_LIBERACAO_FISICA.md" in text, path.name
        assert "j_i^0" in text, path.name
        assert "ell_" in text or r"\ell_" in text, path.name


def test_canonical_ramp_weakly_increases_cumulative_capacity() -> None:
    """For fixed absolute start, mu^->=0 protects all existing mobilizations."""
    factors = (
        Fraction(1), Fraction(0), Fraction(1, 2),
        Fraction(1), Fraction(1), Fraction(0),
    )
    values: list[Fraction] = []
    for n in range(1, len(factors) + 1):
        teams = [
            min(1 + t, 4, 1 + 1 * (n - 1 - t))
            for t in range(n)
        ]
        # Nonlinear max-flow: one shared 15 u/h downstream bottleneck.
        flows = [min(10 * team, 15) for team in teams]
        values.append(sum(
            (Fraction(flow) * factor for flow, factor in zip(flows, factors, strict=False)),
            Fraction(0),
        ))
    assert values == sorted(values)
    # A zero-capacity first week and already saturated shared bottleneck
    # do not imply strict growth at every candidate duration.


def test_extension_can_break_resource_feasibility_even_if_capacity_grows() -> None:
    nominal_production = (100, 100)
    assert sum(nominal_production) >= 100
    assert capacity_feasible((1, 0), (1, 0))
    # Extending an activity into another resource-owner's week is infeasible.
    assert not capacity_feasible((1, 1), (1, 0))
