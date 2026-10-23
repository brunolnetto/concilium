"""P16-A: exact weekly demand layers for homogeneous fungible resources.

This module accepts *physical instance counts already derived* from the
team-composition function a_i,g(m_i,j). It does not infer resource demand from
throughput, an arbitrary peak, or ratios of heterogeneous resource types.
The weekly calendar order is caller-supplied and must already be validated.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class DemandLayer:
    """One physical instance-level, with half-open contiguous blocks."""

    resource_type: str
    level: int
    occupied_weeks: tuple[int, ...]
    blocks: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class WeeklyDemandLevels:
    """Immutable, reconstructible normalization of a supplied demand tensor."""

    calendar_weeks: tuple[str, ...]
    demand_by_type: tuple[tuple[str, tuple[int, ...]], ...]
    layers: tuple[DemandLayer, ...]

    def reconstruct(self) -> dict[str, tuple[int, ...]]:
        """Recover each d_g,j as the exact sum of active level indicators."""
        result: dict[str, list[int]] = {
            resource: [0] * len(self.calendar_weeks)
            for resource, _ in self.demand_by_type
        }
        for layer in self.layers:
            for week_index in layer.occupied_weeks:
                result[layer.resource_type][week_index] += 1
        return {resource: tuple(series) for resource, series in result.items()}


def _contiguous_blocks(occupied: tuple[int, ...]) -> tuple[tuple[int, int], ...]:
    """Maximal [start, end) blocks; adjacent weeks never produce a fake gap."""
    if not occupied:
        return ()
    blocks: list[tuple[int, int]] = []
    start = previous = occupied[0]
    for week in occupied[1:]:
        if week != previous + 1:
            blocks.append((start, previous + 1))
            start = week
        previous = week
    blocks.append((start, previous + 1))
    return tuple(blocks)


def normalize_weekly_resource_demand(
    calendar_weeks: Sequence[str],
    by_activity: Mapping[str, Mapping[str, Sequence[int]]] | None,
) -> WeeklyDemandLevels:
    """Sum exact d_g,j and decompose into levels l<=d_g,j.

    Contract:
    - `by_activity[activity_id][resource_type][week_index]` is the
      *explicit physical instance requirement* a_i,g(m_i,j), including
      zero-demand weeks. No implicit team-count normalization.
    - All declared demand series cover the same complete calendar horizon.
    - Missing `by_activity` is UNKNOWN and raises; an explicit empty map
      describes zero declared activities, *not* verified availability.
    - Every count is a nonnegative integer (bool and floats rejected).
    - The result proves sum_l 1[d_g,j>=l] == d_g,j exactly.
    """
    weeks = tuple(calendar_weeks)
    if not weeks or any(not isinstance(w, str) or not w.strip() for w in weeks):
        raise ValueError("calendar weeks must be nonempty strings")
    if len(set(weeks)) != len(weeks):
        raise ValueError("calendar weeks must be unique")
    if by_activity is None or not isinstance(by_activity, Mapping):
        raise ValueError("per-activity physical demand evidence is required")

    totals: dict[str, list[int]] = {}
    for activity, resources in sorted(by_activity.items()):
        if not isinstance(activity, str) or not activity.strip():
            raise ValueError("activity identifiers must be nonempty strings")
        if not isinstance(resources, Mapping):
            raise ValueError(f"{activity}: explicit resource demand map is required")
        for resource, counts in sorted(resources.items()):
            if not isinstance(resource, str) or not resource.strip():
                raise ValueError("resource type identifiers must be nonempty strings")
            if isinstance(counts, (str, bytes)) or not isinstance(counts, Sequence):
                raise ValueError(f"{activity}.{resource}: explicit weekly counts required")
            if len(counts) != len(weeks):
                raise ValueError(f"{activity}.{resource}: every calendar week needs a count")
            if any(type(quantity) is not int or quantity < 0 for quantity in counts):
                raise ValueError(
                    f"{activity}.{resource}: physical instance counts must be nonnegative integers"
                )
            total = totals.setdefault(resource, [0] * len(weeks))
            for j, quantity in enumerate(counts):
                total[j] += quantity

    demand_by_type = tuple(
        (resource, tuple(values)) for resource, values in sorted(totals.items())
    )
    layers: list[DemandLayer] = []
    for resource, values in demand_by_type:
        for level in range(1, max(values, default=0) + 1):
            occupied = tuple(j for j, value in enumerate(values) if value >= level)
            layers.append(DemandLayer(resource, level, occupied, _contiguous_blocks(occupied)))

    result = WeeklyDemandLevels(weeks, demand_by_type, tuple(layers))
    if result.reconstruct() != dict(demand_by_type):
        raise AssertionError("physical demand reconstruction invariant violated")
    return result
