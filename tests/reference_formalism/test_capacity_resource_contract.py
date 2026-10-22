"""Independent reference falsifiers: mobilization is physical capacity, not efficiency.

Proof cases for FORMALISMO_LONGO / CAPACIDADE_E_RECURSOS.md, issue #10.
No production imports and no production-generated reference answers.
"""

from decimal import Decimal
from itertools import product

D = Decimal


def _physical_capacity_per_hour(teams: int, rate_per_front: str, shared_limit: str | None) -> Decimal:
    """Closed-form reference for independent branches with optional shared bottleneck."""
    capacity = D(teams) * D(rate_per_front)
    return min(capacity, D(shared_limit)) if shared_limit is not None else capacity


def test_two_of_four_teams_has_no_extra_efficiency_penalty() -> None:
    m = 2
    m_max = 4
    capacity = _physical_capacity_per_hour(m, "10", None)
    assert capacity == D("20")
    assert capacity * D("40") == D("800")
    # Capacity ratio is *diagnostic*. Multiplying by it again is incorrect.
    alpha = capacity / _physical_capacity_per_hour(m_max, "10", None)
    assert alpha == D("0.5")
    assert capacity * D("40") * alpha != D("800")


def test_shared_bottleneck_saturates_without_duplicating_demand() -> None:
    cap_two = _physical_capacity_per_hour(2, "10", "15")
    cap_four = _physical_capacity_per_hour(4, "10", "15")
    assert cap_two == cap_four == D("15")
    assert cap_two * D("40") == cap_four * D("40") == D("600")
    assert 2 < 4  # one resource of this type per team: demand differs, production does not


def _pool_cost(
    demand: tuple[int, ...],
    presence: tuple[int, ...],
    active_cost: Decimal,
    idle_cost: Decimal,
    round_trip_cost: Decimal,
) -> tuple[Decimal, int]:
    if any(x < d for d, x in zip(demand, presence, strict=True)):
        raise ValueError("physical demand cannot exceed contracted presence")
    chains = sum(1 for idx, x in enumerate(presence) if x and (idx == 0 or not presence[idx - 1]))
    active_weeks = sum(demand)
    idle_weeks = sum(x - d for d, x in zip(demand, presence, strict=True))
    return active_cost * active_weeks + idle_cost * idle_weeks + round_trip_cost * chains, chains


def _optimal_contract(
    demand: tuple[int, ...], idle_cost: str, round_trip_cost: str
) -> tuple[tuple[int, ...], Decimal]:
    possibilities = (tuple(x) for x in product((0, 1), repeat=len(demand)))
    feasible = []
    for presence in possibilities:
        if all(x >= d for d, x in zip(demand, presence, strict=True)):
            cost, chains = _pool_cost(demand, presence, D("10"), D(idle_cost), D(round_trip_cost))
            feasible.append((cost, chains, presence))
    optimum = min(feasible)  # cost; then fewer transitions; then deterministic presence ordering
    return optimum[2], optimum[0]


def test_paid_idle_is_cost_optimal_when_remobilization_is_more_expensive() -> None:
    # Weeks 1 and 3 need one resource. A week of standby costs 100,
    # while ending one chain and starting the next costs 160.
    assert _optimal_contract((1, 0, 1), idle_cost="100", round_trip_cost="160") == (
        (1, 1, 1), D("280")
    )


def test_no_idle_at_optimum_when_remobilization_is_free() -> None:
    assert _optimal_contract((1, 0, 1), idle_cost="100", round_trip_cost="0") == (
        (1, 0, 1), D("20")
    )


def test_equal_costs_prefer_fewer_transitions() -> None:
    assert _optimal_contract((1, 0, 1), idle_cost="160", round_trip_cost="160") == (
        (1, 1, 1), D("340")
    )
