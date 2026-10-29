"""Exact per-demand-level contractual pool under a *fixed* physical schedule.

P16-B (#16): physical weekly resource counts come from P16-A, not from
workforce/productivity ratios. This implementation does NOT optimize the
workforce or the RCPSP schedule and cannot certify project-wide GO.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from fractions import Fraction

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
    # Empty means the historical fixed-level representation. Nonempty gives
    # the exact active weeks of this globally assigned physical instance.
    active_week_indices: tuple[int, ...] = ()

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
    proof_scope: str = "EXACT_GLOBAL_INSTANCE_ASSIGNMENT_CONDITIONAL_ON_FIXED_PHYSICAL_DEMAND"

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


@dataclass
class _ResidualEdge:
    to: int
    reverse_index: int
    capacity: int
    cost: tuple[Fraction, int]
    original_capacity: int = 0


def _cost_add(left: tuple[Fraction, int], right: tuple[Fraction, int]) -> tuple[Fraction, int]:
    return (left[0] + right[0], left[1] + right[1])


def _cost_neg(value: tuple[Fraction, int]) -> tuple[Fraction, int]:
    return (-value[0], -value[1])


def _add_residual_edge(
    graph: list[list[_ResidualEdge]],
    source: int,
    target: int,
    capacity: int,
    cost: tuple[Fraction, int],
) -> int:
    """Append a forward/residual pair and return the forward edge index."""
    forward_index = len(graph[source])
    reverse_index = len(graph[target])
    graph[source].append(
        _ResidualEdge(target, reverse_index, capacity, cost, capacity)
    )
    graph[target].append(
        _ResidualEdge(source, forward_index, 0, _cost_neg(cost), 0)
    )
    return forward_index


def _global_instance_chains(
    resource_type: str,
    demand: tuple[int, ...],
    tariff: ResourceTariff,
) -> tuple[InstanceChain, ...]:
    """Solve the exact fungible-instance assignment as optional min-cost flow.

    A left event at week i matched to a right event at week j means the same
    physical instance remains contracted between the two active weeks. Its
    incremental cost versus splitting is idle_week * (j-i-1) - movement.
    Every event can have one predecessor and one successor independently,
    producing disjoint time-directed instance paths. Costs are exact Fractions;
    the secondary tuple component maximizes links on exact monetary ties.
    """
    horizon = len(demand)
    if any(type(value) is not int or value < 0 for value in demand):
        raise ValueError(f"{resource_type}: weekly physical demand must be nonnegative integers")
    if horizon == 0:
        raise ValueError("physical demand horizon cannot be empty")
    if not any(demand):
        return ()

    # S -> left-week events -> right-week events -> T.
    source = 0
    left_base = 1
    right_base = 1 + horizon
    sink = 1 + 2 * horizon
    graph: list[list[_ResidualEdge]] = [[] for _ in range(sink + 1)]
    zero_cost = (Fraction(0), 0)
    link_edges: dict[tuple[int, int], tuple[int, int]] = {}

    for week, quantity in enumerate(demand):
        _add_residual_edge(graph, source, left_base + week, quantity, zero_cost)
        _add_residual_edge(graph, right_base + week, sink, quantity, zero_cost)

    for start, start_demand in enumerate(demand):
        if not start_demand:
            continue
        for end in range(start + 1, horizon):
            end_demand = demand[end]
            if not end_demand:
                continue
            gap = end - start - 1
            if gap > tariff.max_idle_gap:
                continue
            # Primary objective is exact money; secondary objective reduces
            # chain count when keep/split are exactly equal in money.
            incremental = (
                Fraction(gap) * tariff.idle_week - tariff.movement,
                -1,
            )
            u = left_base + start
            v = right_base + end
            capacity = min(start_demand, end_demand)
            edge_index = _add_residual_edge(graph, u, v, capacity, incremental)
            link_edges[(start, end)] = (u, edge_index)

    # Successive shortest augmenting paths. Initial forward graph is acyclic;
    # Bellman-Ford handles negative exact costs and residual reassignment edges.
    # Only strictly improving optional links are admitted; (0, -1) is a keep
    # decision on an exact money tie.
    node_count = len(graph)
    while True:
        distance: list[tuple[Fraction, int] | None] = [None] * node_count
        previous: list[tuple[int, int] | None] = [None] * node_count
        distance[source] = zero_cost
        for _ in range(node_count - 1):
            changed = False
            for u, edges in enumerate(graph):
                base = distance[u]
                if base is None:
                    continue
                for edge_index, edge in enumerate(edges):
                    if edge.capacity <= 0:
                        continue
                    candidate = _cost_add(base, edge.cost)
                    current = distance[edge.to]
                    if current is None or candidate < current:
                        distance[edge.to] = candidate
                        previous[edge.to] = (u, edge_index)
                        changed = True
            if not changed:
                break
        best = distance[sink]
        if best is None or best >= zero_cost:
            break

        path: list[tuple[int, int]] = []
        current_node = sink
        while current_node != source:
            step = previous[current_node]
            if step is None:
                raise AssertionError("shortest residual path has no predecessor")
            path.append(step)
            current_node = step[0]
            if len(path) > node_count:
                raise AssertionError("residual predecessor cycle in minimum-cost flow")
        amount = min(graph[u][edge_index].capacity for u, edge_index in path)
        if amount <= 0:
            raise AssertionError("minimum-cost flow found a zero-capacity path")
        for u, edge_index in path:
            edge = graph[u][edge_index]
            edge.capacity -= amount
            graph[edge.to][edge.reverse_index].capacity += amount

    # Expand aggregated week-to-week flow into deterministic labeled events.
    # Incoming and outgoing slots are independent because an active instance can
    # have both a predecessor and a successor at its active week.
    successor: dict[tuple[int, int], tuple[int, int]] = {}
    predecessor: dict[tuple[int, int], tuple[int, int]] = {}
    for (start, end), (u, edge_index) in sorted(link_edges.items()):
        edge = graph[u][edge_index]
        amount = edge.original_capacity - edge.capacity
        for _ in range(amount):
            source_event = next(
                (start, slot) for slot in range(demand[start])
                if (start, slot) not in successor
            )
            target_event = next(
                (end, slot) for slot in range(demand[end])
                if (end, slot) not in predecessor
            )
            successor[source_event] = target_event
            predecessor[target_event] = source_event

    events = tuple(
        (week, slot)
        for week, quantity in enumerate(demand)
        for slot in range(quantity)
    )
    visited: set[tuple[int, int]] = set()
    paths: list[tuple[tuple[int, int], ...]] = []
    for first in events:
        if first in predecessor:
            continue
        path: list[tuple[int, int]] = []
        current = first
        while current not in visited:
            visited.add(current)
            path.append(current)
            following = successor.get(current)
            if following is None:
                break
            current = following
        else:
            raise AssertionError("instance assignment contains a path merge/cycle")
        paths.append(tuple(path))
    if visited != set(events):
        raise AssertionError("some physical demand events are absent from instance chains")

    paths.sort(
        key=lambda path: (
            path[0][0],
            tuple(week for week, _slot in path),
            path[0][1],
        )
    )
    chains: list[InstanceChain] = []
    for identity, path in enumerate(paths, start=1):
        active_weeks = tuple(week for week, _slot in path)
        start = active_weeks[0]
        end_exclusive = active_weeks[-1] + 1
        idle_weeks = end_exclusive - start - len(active_weeks)
        if any(
            following - previous - 1 > tariff.max_idle_gap
            for previous, following in zip(active_weeks, active_weeks[1:], strict=True)
        ):
            raise AssertionError("optimizer produced a chain beyond the allowed idle gap")
        chains.append(
            InstanceChain(
                resource_type=resource_type,
                level=identity,
                start=start,
                end=end_exclusive,
                active_weeks=len(active_weeks),
                idle_weeks=idle_weeks,
                active_week_indices=active_weeks,
            )
        )

    # Independent reconstruction assertions guard the optimizer/decoder seam.
    active_by_week = [0] * horizon
    presence_by_week = [0] * horizon
    for chain in chains:
        for week in chain.active_week_indices:
            active_by_week[week] += 1
        for week in range(chain.start, chain.end):
            presence_by_week[week] += 1
    if tuple(active_by_week) != demand:
        raise AssertionError("global instance chains do not reconstruct physical demand")
    if any(presence_by_week[j] < demand[j] for j in range(horizon)):
        raise AssertionError("contractual presence falls below physical demand")
    return tuple(chains)


def optimize_homogeneous_pool(
    normalized: WeeklyDemandLevels,
    tariffs: Mapping[str, ResourceTariff],
) -> ExactPoolResult:
    """Globally optimize instance assignment for fixed homogeneous physical demand.

    Every instance can be assigned to different active weeks. The min-cost-flow
    model jointly chooses which active demands share a physical instance chain,
    charging exact idle weeks for gaps within the declared maximum and one
    MOB/DEMOB pair per resulting chain. Resource types remain independent.
    This solves the fungible-instance assignment globally for fixed d_gj; it does
    not optimize the RCPSP schedule, heterogeneous contracts, nonlinear tariffs
    or the whole project GO decision.
    """
    demand = dict(normalized.demand_by_type)
    if not isinstance(tariffs, Mapping) or set(tariffs) != set(demand):
        raise ValueError("one declared tariff per resource type is required")
    if len(demand) != len(normalized.demand_by_type):
        raise ValueError("duplicate resource type in physical demand")
    weeks = tuple(normalized.calendar_weeks)
    if not weeks or any(not isinstance(week, str) or not week.strip() for week in weeks):
        raise ValueError("physical calendar weeks must be nonempty strings")
    if len(set(weeks)) != len(weeks):
        raise ValueError("physical calendar weeks must be unique")
    if any(len(series) != len(weeks) for series in demand.values()):
        raise ValueError("physical demand series must cover the full calendar horizon")
    if any(type(value) is not int or value < 0 for series in demand.values() for value in series):
        raise ValueError("physical demand counts must be nonnegative integers")
    if normalized.reconstruct() != demand:
        raise ValueError("demand layers do not reconstruct physical requirements")

    ledgers: list[ResourceContractLedger] = []
    for resource, physical in sorted(demand.items()):
        tariff = tariffs[resource]
        if not isinstance(tariff, ResourceTariff):
            raise ValueError(f"{resource}: invalid contract tariff")
        chains = _global_instance_chains(resource, physical, tariff)
        presence = [0] * len(weeks)
        active = [0] * len(weeks)
        for chain in chains:
            for j in range(chain.start, chain.end):
                presence[j] += 1
            for j in chain.active_week_indices:
                active[j] += 1
        if tuple(active) != physical:
            raise AssertionError("global instance assignment fails exact active-demand reconstruction")
        idle = tuple(p - d for p, d in zip(presence, physical, strict=True))
        if any(value < 0 for value in idle):
            raise AssertionError("contracted presence falls below physical demand")
        if sum(chain.active_weeks for chain in chains) != sum(physical):
            raise AssertionError("global instance activity is not reconciled")
        if sum(chain.idle_weeks for chain in chains) != sum(idle):
            raise AssertionError("global instance standby is not reconciled")
        expected_total = (
            Fraction(sum(physical)) * tariff.active_week
            + Fraction(sum(idle)) * tariff.idle_week
            + Fraction(len(chains)) * tariff.movement
        )
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
        if ledgers[-1].total != expected_total:
            raise AssertionError("global pool financial reconstruction failed")
    return ExactPoolResult(weeks, tuple(ledgers))
