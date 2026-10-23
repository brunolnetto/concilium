"""Exact per-demand-level contractual pool under a *fixed* physical schedule.

P16-B (#16): physical weekly resource counts come from P16-A, not from
workforce/productivity ratios. This implementation does NOT optimize the
workforce or the RCPSP schedule and cannot certify project-wide GO.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from typing import Mapping

from .resource_demand_levels import WeeklyDemandLevels


def exact_money(value: str) -> Fraction:
    """Parse a finite decimal tariff without ever passing through binary float."""
    if not isinstance(value, str):
        raise ValueError("tariff must be an exact decimal string")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("tariff must be a valid decimal") from exc
    if not parsed.is_finite() or parsed < 0:
        raise ValueError("tariff must be finite and nonnegative")
    return Fraction(parsed)


@dataclass(frozen=True)
class ResourceTariff:
    """Costs per *single instance* in one physical calendar week.

    All rates must already refer to the same weekly horizon; hourly or monthly
    rates must be converted under the explicit contract before calling.
    """

    active_week: Fraction
    idle_week: Fraction
    mobilize: Fraction
    demobilize: Fraction
    max_idle_gap: int

    def __post_init__(self) -> None:
        for field in ("active_week", "idle_week", "mobilize", "demobilize"):
            value = getattr(self, field)
            if type(value) is not Fraction or value < 0:
                raise ValueError(f"{field} must be an exact nonnegative Fraction")
        if type(self.max_idle_gap) is not int or self.max_idle_gap < 0:
            raise ValueError("max_idle_gap must be a nonnegative integer")

    @property
    def movement(self) -> Fraction:
        return self.mobilize + self.demobilize


@dataclass(frozen=True)
class InstanceChain:
    resource_type: str
    level: int
    start: int
    end: int
    active_weeks: int
    idle_weeks: int

    @property
    def presence_weeks(self) -> int:
        return self.end - self.start


@dataclass(frozen=True)
class ResourceContractLedger:
    resource_type: str
    demand: tuple[int, ...]
    presence: tuple[int, ...]
    standby: tuple[int, ...]
    chains: tuple[InstanceChain, ...]
    active_cost: Fraction
    standby_cost: Fraction
    mobility_cost: Fraction

    @property
    def total(self) -> Fraction:
        return self.active_cost + self.standby_cost + self.mobility_cost


@dataclass(frozen=True)
class ExactPoolResult:
    calendar_weeks: tuple[str, ...]
    ledgers: tuple[ResourceContractLedger, ...]
    proof_scope: str = "EXACT_POOL_CONDITIONAL_ON_FIXED_PHYSICAL_DEMAND"

    @property
    def total(self) -> Fraction:
        return sum((ledger.total for ledger in self.ledgers), start=Fraction(0))


def _optimal_level_chains(
    resource_type: str,
    level: int,
    blocks: tuple[tuple[int, int], ...],
    tariff: ResourceTariff,
) -> tuple[InstanceChain, ...]:
    """Independent gap choices minimize the cost of a fungible demand layer.

    Every chain pays one mobilization and one demobilization. Keeping a layer
    across a gap of k weeks adds k*idle_week; splitting adds one extra
    (mobilize+demobilize). On equal cost, keeping minimizes transitions.
    """
    if not blocks:
        return ()
    chains: list[InstanceChain] = []
    first_start, current_end = blocks[0]
    active = current_end - first_start

    for start, end in blocks[1:]:
        gap = start - current_end
        if gap <= 0:
            raise ValueError("demand blocks must be disjoint and nonadjacent")
        keep = gap <= tariff.max_idle_gap and Fraction(gap) * tariff.idle_week <= tariff.movement
        if keep:
            current_end = end
            active += end - start
        else:
            chains.append(
                InstanceChain(resource_type, level, first_start, current_end,
                              active, current_end - first_start - active)
            )
            first_start, current_end = start, end
            active = end - start

    chains.append(
        InstanceChain(resource_type, level, first_start, current_end,
                      active, current_end - first_start - active)
    )
    return tuple(chains)


def optimize_homogeneous_pool(
    normalized: WeeklyDemandLevels,
    tariffs: Mapping[str, ResourceTariff],
) -> ExactPoolResult:
    """Optimal K/idle/movement ledger for homogeneous resources with fixed d_gj.

    Contracts are independent by type and instance level. This theorem does
    not apply if types share a contract, idle rates are nonlinear, lead times
    couple choices, or changing teams/dates is allowed during the solve.
    """
    demand = dict(normalized.demand_by_type)
    if not isinstance(tariffs, Mapping) or set(tariffs) != set(demand):
        raise ValueError("one declared tariff per resource type is required")
    if normalized.reconstruct() != demand:
        raise ValueError("demand levels do not reconstruct physical requirements")

    ledgers: list[ResourceContractLedger] = []
    for resource, physical in sorted(demand.items()):
        tariff = tariffs[resource]
        if not isinstance(tariff, ResourceTariff):
            raise ValueError(f"{resource}: invalid contract tariff")
        chains = tuple(
            chain
            for layer in normalized.layers if layer.resource_type == resource
            for chain in _optimal_level_chains(resource, layer.level, layer.blocks, tariff)
        )
        presence = [0] * len(normalized.calendar_weeks)
        for chain in chains:
            for j in range(chain.start, chain.end):
                presence[j] += 1
        idle = tuple(x - d for x, d in zip(presence, physical, strict=True))
        if any(s < 0 for s in idle):
            raise AssertionError("contracted presence falls below physical demand")
        if sum(chain.active_weeks for chain in chains) != sum(physical):
            raise AssertionError("contract level activity is not reconciled")
        if sum(chain.idle_weeks for chain in chains) != sum(idle):
            raise AssertionError("contract standby is not reconciled")
        ledgers.append(ResourceContractLedger(
            resource_type=resource,
            demand=physical,
            presence=tuple(presence),
            standby=idle,
            chains=chains,
            active_cost=Fraction(sum(physical)) * tariff.active_week,
            standby_cost=Fraction(sum(idle)) * tariff.idle_week,
            mobility_cost=Fraction(len(chains)) * tariff.movement,
        ))
    return ExactPoolResult(tuple(normalized.calendar_weeks), tuple(ledgers))
