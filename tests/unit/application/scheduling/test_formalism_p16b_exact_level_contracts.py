"""P16-B: exact demand-layer pool witness, independent brute-force adversary."""
from __future__ import annotations

from fractions import Fraction
from itertools import product

import pytest

from concilium.application.scheduling.resource_demand_levels import (
    normalize_weekly_resource_demand,
)
from concilium.application.scheduling.contractual_cost_ledger import book_exact_pool
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
    assert result.proof_scope == "EXACT_GLOBAL_INSTANCE_ASSIGNMENT_CONDITIONAL_ON_FIXED_PHYSICAL_DEMAND"
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


def _independent_global_instance_minimum(
    demand: tuple[int, ...], tariff: ResourceTariff
) -> tuple[Fraction, int]:
    """Exhaustive labeled-instance path oracle for tiny horizons, no production calls."""
    from functools import lru_cache

    @lru_cache(maxsize=None)
    def solve(remaining: tuple[int, ...]) -> tuple[Fraction, int]:
        if not any(remaining):
            return Fraction(0), 0
        first = next(j for j, quantity in enumerate(remaining) if quantity > 0)
        later = [j for j in range(first + 1, len(remaining)) if remaining[j] > 0]
        alternatives = []
        for mask in range(1 << len(later)):
            active = (first,) + tuple(
                week for index, week in enumerate(later) if mask & (1 << index)
            )
            if any(
                following - previous - 1 > tariff.max_idle_gap
                for previous, following in zip(active[:-1], active[1:], strict=True)
            ):
                continue
            reduced = list(remaining)
            for week in active:
                reduced[week] -= 1
            idle_weeks = sum(
                following - previous - 1
                for previous, following in zip(active[:-1], active[1:], strict=True)
            )
            chain_cost = (
                Fraction(len(active)) * tariff.active_week
                + Fraction(idle_weeks) * tariff.idle_week
                + tariff.movement
            )
            tail_cost, tail_chains = solve(tuple(reduced))
            alternatives.append((chain_cost + tail_cost, 1 + tail_chains))
        return min(alternatives)

    return solve(demand)


def test_global_instance_assignment_falsifier_costs_92_not_120() -> None:
    normalized = _data({"CRANE": (2, 1, 1, 2)})
    tariff = ResourceTariff(
        active_week=exact_money("5"),
        idle_week=exact_money("1"),
        mobilize=exact_money("20"),
        demobilize=exact_money("10"),
        max_idle_gap=1,
    )
    result = optimize_homogeneous_pool(normalized, {"CRANE": tariff})
    ledger = result.ledgers[0]

    assert result.total == 92
    assert ledger.active_cost == 30
    assert ledger.standby_cost == 2
    assert ledger.mobility_cost == 60
    assert ledger.presence == (2, 2, 2, 2)
    assert ledger.standby == (0, 1, 1, 0)
    assert {
        chain.active_week_indices for chain in ledger.chains
    } == {(0, 1, 3), (0, 2, 3)}
    assert (result.total, len(ledger.chains)) == _independent_global_instance_minimum(
        ledger.demand, tariff
    )

    # Downstream financial booking must honor the physical instance assignment,
    # not reinterpret globally assigned chains as permanent vertical demand levels.
    booked = book_exact_pool(result, {"CRANE": tariff}, {"CRANE": "EQ"})
    assert booked.contractual_k == 32
    assert booked.indirect == 60
    assert booked.total == 92


@pytest.mark.parametrize(
    ("demand", "active", "idle", "mobilize", "demobilize", "max_gap"),
    [
        ((2, 1, 1, 2), "5", "1", "20", "10", 1),
        ((1, 0, 1), "3", "0.3", "0.1", "0.2", 1),
        ((0, 2, 1, 2), "7", "2", "11", "13", 2),
        ((2, 0, 1, 0, 2), "5", "10", "20", "10", 2),
        ((1, 1, 0, 1), "4", "2", "3", "5", 0),
    ],
)
def test_global_optimizer_matches_independent_instance_path_oracle(
    demand: tuple[int, ...],
    active: str,
    idle: str,
    mobilize: str,
    demobilize: str,
    max_gap: int,
) -> None:
    normalized = _data({"R": demand})
    tariff = ResourceTariff(
        active_week=exact_money(active),
        idle_week=exact_money(idle),
        mobilize=exact_money(mobilize),
        demobilize=exact_money(demobilize),
        max_idle_gap=max_gap,
    )
    result = optimize_homogeneous_pool(normalized, {"R": tariff})
    ledger = result.ledgers[0]
    expected = _independent_global_instance_minimum(demand, tariff)
    assert (result.total, len(ledger.chains)) == expected
    assert tuple(
        sum(j in chain.active_week_indices for chain in ledger.chains)
        for j in range(len(demand))
    ) == demand


def test_global_optimizer_exhaustively_matches_instance_path_oracle_for_small_demands() -> None:
    """Exhaust all 4-week demand tensors with counts 0..2 against an independent oracle."""
    tariffs = (
        # Canonical counterexample; profitable links and a strict idle-gap cap.
        ResourceTariff(exact_money("5"), exact_money("1"), exact_money("20"), exact_money("10"), 1),
        # Exact decimal tie between keeping one idle week and mobilizing again.
        ResourceTariff(exact_money("3"), exact_money("0.3"), exact_money("0.1"), exact_money("0.2"), 1),
        # Wider admissible gap and asymmetric mobilization/demobilization.
        ResourceTariff(exact_money("7"), exact_money("2"), exact_money("11"), exact_money("13"), 2),
        # Zero-gap contract: only adjacent active weeks may share an instance.
        ResourceTariff(exact_money("4"), exact_money("2"), exact_money("3"), exact_money("5"), 0),
        # Free standby and movement exercise deterministic tie-breaking.
        ResourceTariff(exact_money("5"), exact_money("0"), exact_money("0"), exact_money("0"), 3),
    )

    # 3**4 = 81 distinct weekly demand profiles × five tariff regimes.
    # The oracle enumerates labeled instance paths and is independent of min-cost flow.
    for demand in product(range(3), repeat=4):
        normalized = _data({"R": demand})
        for tariff in tariffs:
            result = optimize_homogeneous_pool(normalized, {"R": tariff})
            ledger = result.ledgers[0]
            expected_cost, expected_chains = _independent_global_instance_minimum(demand, tariff)
            assert (result.total, len(ledger.chains)) == (expected_cost, expected_chains), (
                f"demand={demand}, tariff={tariff}"
            )
            reconstructed = tuple(
                sum(week in chain.active_week_indices for chain in ledger.chains)
                for week in range(len(demand))
            )
            assert reconstructed == demand, f"demand reconstruction failed for {demand}"

