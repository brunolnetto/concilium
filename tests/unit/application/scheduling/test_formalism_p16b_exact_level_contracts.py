"""P16-B: exact demand-layer pool witness, independent brute-force adversary."""
from __future__ import annotations

from fractions import Fraction
from itertools import product

import pytest

from concilium.application.scheduling.resource_demand_levels import (
    normalize_weekly_resource_demand,
)
from concilium.application.scheduling.resource_level_contracts import (
    ResourceTariff,
    exact_money,
    optimize_homogeneous_pool,
)


def _data(requirements: dict[str, tuple[int, ...]]):
    size = len(next(iter(requirements.values())))
    return normalize_weekly_resource_demand(
        [f"W{week:03d}" for week in range(size)],
        {"A": requirements},
    )


def _tariff(idle: str, *, max_gap: int = 10) -> ResourceTariff:
    return ResourceTariff(
        active_week=exact_money("5"),
        idle_week=exact_money(idle),
        mobilize=exact_money("20"),
        demobilize=exact_money("10"),
        max_idle_gap=max_gap,
    )


def _independent_brute_force_minimum(normalized, resource: str, tariff: ResourceTariff):
    """Enumerate ALL gap keep/split choices; does not call the production solver."""
    optimum = Fraction(0)
    optimal_chain_count = 0
    for layer in normalized.layers:
        if layer.resource_type != resource:
            continue
        gaps = [
            following[0] - preceding[1]
            for preceding, following in zip(layer.blocks, layer.blocks[1:], strict=False)
        ]
        active = sum(end - start for start, end in layer.blocks)
        choices = []
        for flags in product((False, True), repeat=len(gaps)):
            if any(keep and gap > tariff.max_idle_gap for keep, gap in zip(flags, gaps, strict=True)):
                continue
            idle = sum(gap for keep, gap in zip(flags, gaps, strict=True) if keep)
            chains = 1 + sum(not flag for flag in flags)
            cost = (
                Fraction(active) * tariff.active_week
                + Fraction(idle) * tariff.idle_week
                + Fraction(chains) * (tariff.mobilize + tariff.demobilize)
            )
            choices.append((cost, chains))
        best = min(choices)  # exact cost, then fewest transitions on ties
        optimum += best[0]
        optimal_chain_count += best[1]
    return optimum, optimal_chain_count


def test_reconstruct_and_optimize_two_resource_levels_with_exact_tie() -> None:
    normalized = _data({"CRANE": (2, 0, 1, 0, 2)})
    result = optimize_homogeneous_pool(normalized, {"CRANE": _tariff("10")})
    ledger = result.ledgers[0]
    assert result.proof_scope == "EXACT_POOL_CONDITIONAL_ON_FIXED_PHYSICAL_DEMAND"
    assert ledger.demand == (2, 0, 1, 0, 2)
    assert ledger.presence == (2, 2, 2, 2, 2)
    assert ledger.standby == (0, 2, 1, 2, 0)
    assert len(ledger.chains) == 2
    assert ledger.active_cost == 25
    assert ledger.standby_cost == 50
    assert ledger.mobility_cost == 60
    assert result.total == 135
    assert (result.total, len(ledger.chains)) == _independent_brute_force_minimum(
        normalized, "CRANE", _tariff("10")
    )


@pytest.mark.parametrize(
    ("idle", "max_gap", "expected_presence", "expected_chains"),
    [
        ("10", 2, (2, 1, 1, 1, 2), 3),  # longest gap physically forbidden
        ("11", 10, (2, 1, 1, 1, 2), 3),  # 3*11 > 30, split level 2
        ("0", 10, (2, 2, 2, 2, 2), 2),  # free idle is preferable
        ("100", 10, (2, 0, 1, 0, 2), 5),  # free split is not implied
    ],
)
def test_gap_choices_match_brute_force(
    idle: str, max_gap: int, expected_presence: tuple[int, ...], expected_chains: int
) -> None:
    normalized = _data({"CRANE": (2, 0, 1, 0, 2)})
    tariff = _tariff(idle, max_gap=max_gap)
    result = optimize_homogeneous_pool(normalized, {"CRANE": tariff})
    ledger = result.ledgers[0]
    assert ledger.presence == expected_presence
    assert len(ledger.chains) == expected_chains
    assert (ledger.total, len(ledger.chains)) == _independent_brute_force_minimum(
        normalized, "CRANE", tariff
    )


def test_two_types_do_not_subsidize_or_share_instances() -> None:
    normalized = _data({"CRANE": (1, 0, 1), "OPERATOR": (0, 2, 0)})
    result = optimize_homogeneous_pool(
        normalized, {"CRANE": _tariff("4"), "OPERATOR": _tariff("4")}
    )
    by_type = {ledger.resource_type: ledger for ledger in result.ledgers}
    assert by_type["CRANE"].presence == (1, 1, 1)
    assert by_type["OPERATOR"].presence == (0, 2, 0)
    assert result.total == sum(ledger.total for ledger in result.ledgers)


def test_zero_demand_requires_no_fictitious_contract() -> None:
    normalized = _data({"CRANE": (0, 0, 0)})
    result = optimize_homogeneous_pool(normalized, {"CRANE": _tariff("1")})
    assert result.total == 0
    assert result.ledgers[0].chains == ()
    assert result.ledgers[0].presence == (0, 0, 0)


def test_missing_tariff_never_defaults_to_free_idle() -> None:
    normalized = _data({"CRANE": (1, 0, 1)})
    with pytest.raises(ValueError, match="one declared tariff"):
        optimize_homogeneous_pool(normalized, {})


def test_invalid_tariffs_fail_closed() -> None:
    for token in ("NaN", "Infinity", "-1"):
        with pytest.raises(ValueError, match="finite and nonnegative"):
            exact_money(token)
    with pytest.raises(ValueError, match="exact decimal string"):
        exact_money(0.1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="nonnegative Fraction"):
        ResourceTariff(Fraction(-1), Fraction(0), Fraction(0), Fraction(0), 0)
    with pytest.raises(ValueError, match="max_idle_gap"):
        ResourceTariff(Fraction(1), Fraction(0), Fraction(0), Fraction(0), -1)


def test_exact_fraction_arithmetic_handles_decimal_boundaries() -> None:
    normalized = _data({"CRANE": (1, 0, 1)})
    tariff = ResourceTariff(
        exact_money("1"), exact_money("0.3"), exact_money("0.1"), exact_money("0.2"), 1
    )
    result = optimize_homogeneous_pool(normalized, {"CRANE": tariff})
    ledger = result.ledgers[0]
    assert len(ledger.chains) == 1
    assert ledger.standby_cost == Fraction(3, 10)
    assert ledger.mobility_cost == Fraction(3, 10)
    assert (ledger.total, len(ledger.chains)) == _independent_brute_force_minimum(
        normalized, "CRANE", tariff
    )
