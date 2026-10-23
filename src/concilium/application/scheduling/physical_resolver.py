"""P15-B: deterministic bounded re-materialization of physical RCPSP calendars.

Searches finite, caller-declared start-week windows. Every candidate must
recompute the activity's physical production and resource demand at the new
ABSOLUTE calendar week, e.g. F_i(m) * H_i * p_ij * c_j.
Shifting an old q_ij series unchanged is *not* a valid materializer.

A local PASS certifies only the checked V1/V6 materialized constraints. This
is NOT the final joint cost/pool/GO certification (#15-C, #23).
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from itertools import islice, product
from math import prod
from typing import Literal

from .physical_validator import (
    PhysicalActivity,
    PhysicalCalendarAudit,
    PhysicalPrecedence,
    validate_materialized_calendar,
)

ResolveStatus = Literal["PASS", "FAIL", "UNKNOWN"]


@dataclass(frozen=True)
class PhysicalResolution:
    status: ResolveStatus
    activities: tuple[PhysicalActivity, ...] | None
    attempts: int
    complete_search: bool
    last_audit: PhysicalCalendarAudit | None

    @property
    def locally_admissible(self) -> bool:
        return self.status == "PASS"


def resolve_bounded_physical_calendar(
    item_ids: Sequence[str],
    admissible_starts: Mapping[str, Sequence[int]],
    materialize: Callable[[str, int], PhysicalActivity | None],
    precedences: Sequence[PhysicalPrecedence],
    *,
    calendar_horizon_weeks: int,
    pool_capacity: Mapping[str, Fraction] | None,
    max_states: int = 10_000,
) -> PhysicalResolution:
    """Try actual re-materialized schedules in deterministic week order.

    A materializer returning None rejects that start (infeasible climate,
    staffing, duration or unavailable capacity). A returned activity MUST use
    the requested absolute start and actual weekly deliveries and demands.

    An UNKNOWN result means pool data were missing or the search was limited,
    and must never be interpreted as a feasible schedule. FAIL means all of
    the explicitly supplied finite candidate starts were checked and failed.
    """
    if calendar_horizon_weeks <= 0 or max_states <= 0:
        raise ValueError("horizon and max_states must be positive")
    ids = tuple(sorted(item_ids))
    if len(ids) != len(set(ids)) or not ids or any(not name for name in ids):
        raise ValueError("item IDs must be nonempty and unique")
    if set(admissible_starts) != set(ids):
        raise ValueError("every item must declare its entire admissible start window")

    starts: list[tuple[int, ...]] = []
    for item in ids:
        choices = tuple(sorted(set(admissible_starts[item])))
        if not choices:
            raise ValueError("admissible start window cannot be empty")
        if any(not isinstance(start, int) or isinstance(start, bool) or start < 0
               or start >= calendar_horizon_weeks for start in choices):
            raise ValueError("start weeks must be integer positions inside the horizon")
        starts.append(choices)

    state_count = prod(len(choices) for choices in starts)
    complete_search = state_count <= max_states
    attempts = 0
    saw_unknown = False
    last_audit: PhysicalCalendarAudit | None = None

    for combination in islice(product(*starts), max_states):
        attempts += 1
        activities: list[PhysicalActivity] = []
        for item, start in zip(ids, combination, strict=True):
            physical = materialize(item, start)
            if physical is None:
                break
            if physical.item_id != item or physical.start_week != start:
                raise ValueError("materializer returned mismatched item or absolute start")
            activities.append(physical)
        if len(activities) != len(ids):
            continue
        audit = validate_materialized_calendar(
            activities, precedences,
            calendar_horizon_weeks=calendar_horizon_weeks,
            pool_capacity=pool_capacity,
        )
        last_audit = audit
        if audit.status == "PASS":
            return PhysicalResolution("PASS", tuple(activities), attempts, complete_search, audit)
        if audit.status == "UNKNOWN":
            saw_unknown = True

    status: ResolveStatus = "UNKNOWN" if saw_unknown or not complete_search else "FAIL"
    return PhysicalResolution(status, None, attempts, complete_search, last_audit)
