"""Exact post-materialization V1/V6 checks for physical RCPSP schedules.

P15-A verifies (rather than re-solves) a *materialized* calendar. Inputs are
already in absolute week coordinates and physical quantities; no rounding of
weekly production and no inference of dates from the nominal RCPSP durations.
This is a local verifier, NOT a GO certificate or global optimality proof.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

Relation = Literal["FS", "SS", "FF"]
AuditStatus = Literal["PASS", "FAIL", "UNKNOWN"]


@dataclass(frozen=True)
class PhysicalActivity:
    item_id: str
    scope: Fraction
    start_week: int
    end_week_exclusive: int
    # A positive delivery on week j becomes available at boundary j+1.
    deliveries: tuple[tuple[int, Fraction], ...]
    # Physical resource reservation in a week, including zero-output weeks.
    demands: tuple[tuple[int, str, Fraction], ...] = ()
    # Already derived from the ONE weekly capacity law:
    # B_ij = H_i * F_i(m_ij) * practicability_ij * calendar_j * eta_workday_i.
    # It is a witness, never a separately inferred productivity.
    weekly_capacities: tuple[tuple[int, Fraction], ...] = ()


@dataclass(frozen=True)
class PhysicalPrecedence:
    predecessor: str
    successor: str
    kind: Relation = "FS"
    lag_weeks: int = 0
    completion_threshold: Fraction = Fraction(1)


@dataclass(frozen=True)
class PhysicalViolation:
    code: str
    item_id: str
    week: int | None
    reason: str


@dataclass(frozen=True)
class PhysicalCalendarAudit:
    status: AuditStatus
    violations: tuple[PhysicalViolation, ...]

    @property
    def locally_admissible(self) -> bool:
        return self.status == "PASS"


# The Skill 04 runtime stores floating-point weekly cells; the bridge converts
# them to decimal Fractions. Keep exact Fraction oracle inputs exact, but tolerate
# only the same versioned physical scope error used by P14 when crossing that API.
SCOPE_ABS_TOLERANCE = Fraction(1, 10**9)
SCOPE_REL_TOLERANCE = Fraction(1, 10**12)


def scope_tolerance(required: Fraction) -> Fraction:
    return max(SCOPE_ABS_TOLERANCE, abs(required) * SCOPE_REL_TOLERANCE)


def scope_is_closed(required: Fraction, delivered: Fraction) -> bool:
    return abs(required - delivered) <= scope_tolerance(required)


def _release_after_scope(activity: PhysicalActivity, theta: Fraction) -> int | None:
    """Earliest exclusive week boundary satisfying Q*theta.

    theta=0 is start-to-start (no end-of-week delivery required).
    For theta>0, even if delivery occurs during week j, release is j+1.
    A sub-tolerance float representation error uses the same versioned Q
    closure tolerance as the physical scope gate, never percentage rounding.
    """
    if theta == 0:
        return activity.start_week
    required = theta * activity.scope
    cumulative = Fraction(0)
    for week, quantity in sorted(activity.deliveries):
        cumulative += quantity
        if cumulative >= required or required - cumulative <= scope_tolerance(required):
            return week + 1
    return None


def validate_materialized_calendar(
    activities: Sequence[PhysicalActivity],
    precedences: Sequence[PhysicalPrecedence],
    *,
    calendar_horizon_weeks: int,
    pool_capacity: Mapping[str, Fraction] | None = None,
    require_weekly_capacity: bool = False,
) -> PhysicalCalendarAudit:
    """Validate exact physical releases and the shared weekly resource pool.

    PASS means this *specific materialized* schedule satisfies the checked
    constraints, not that a joint RCPSP / financial certificate is available.
    Missing pool capacity returns UNKNOWN when resources are demanded.
    Each provided weekly-capacity witness must bound the materialized q_ij.
    An incomplete witness returns UNKNOWN rather than claiming physical GO;
    strict mode also requires a witness for every positive-delivery week.
    The witness must come from the shared F(m)/calendar law; this validator
    checks its consistency against q, not the solver or provenance.
    """
    if calendar_horizon_weeks < 0:
        raise ValueError("calendar_horizon_weeks must be nonnegative")
    issues: list[PhysicalViolation] = []
    by_id: dict[str, PhysicalActivity] = {}
    usage: dict[tuple[int, str], Fraction] = defaultdict(Fraction)

    for a in activities:
        if not a.item_id or a.item_id in by_id:
            issues.append(PhysicalViolation("V6_DUPLICATE_ITEM", a.item_id, None, "missing or duplicate item id"))
            continue
        by_id[a.item_id] = a
        if not (0 <= a.start_week < a.end_week_exclusive <= calendar_horizon_weeks):
            issues.append(PhysicalViolation("V6_OUT_OF_HORIZON", a.item_id, None, "activity outside bounded calendar"))
        if a.scope <= 0:
            issues.append(PhysicalViolation("V1_INVALID_SCOPE", a.item_id, None, "Q must be positive"))
        capacity_by_week: dict[int, Fraction] = {}
        for week, capacity in a.weekly_capacities:
            if (
                not a.start_week <= week < a.end_week_exclusive
                or capacity < 0
                or week in capacity_by_week
            ):
                issues.append(PhysicalViolation(
                    "V1_INVALID_WEEKLY_CAPACITY", a.item_id, week,
                    "negative, duplicated or out-of-activity weekly capacity witness",
                ))
            else:
                capacity_by_week[week] = capacity
        delivered = Fraction(0)
        last_week: int | None = None
        for week, q in sorted(a.deliveries):
            if not a.start_week <= week < a.end_week_exclusive or q < 0 or week == last_week:
                issues.append(
                    PhysicalViolation("V1_INVALID_DELIVERY", a.item_id, week, "invalid week, quantity or duplicate")
                )
            # Only verified capacity from the materialized weekly F(m)
            # envelope may justify a positive delivery. Never infer
            # capacity from its already-capped output q.
            if q > 0 and week not in capacity_by_week and (
                require_weekly_capacity or bool(a.weekly_capacities)
            ):
                issues.append(PhysicalViolation(
                    "V1_WEEKLY_CAPACITY_UNVERIFIED", a.item_id, week,
                    "positive delivery has no verified B_ij witness",
                ))
            elif week in capacity_by_week and q > capacity_by_week[week]:
                issues.append(PhysicalViolation(
                    "V1_WEEKLY_CAPACITY_EXCEEDED", a.item_id, week,
                    f"q={q}; available_capacity={capacity_by_week[week]}",
                ))
            delivered += q
            last_week = week
        if not scope_is_closed(a.scope, delivered):
            issues.append(PhysicalViolation(
                "V1_SCOPE_UNCLOSED", a.item_id, None,
                f"Q={a.scope}; sum_q={delivered}; absolute_error={abs(a.scope-delivered)}; "
                f"tolerance={scope_tolerance(a.scope)}",
            ))
        for week, resource, demand in a.demands:
            if not a.start_week <= week < a.end_week_exclusive or not resource or demand < 0:
                issues.append(PhysicalViolation("V6_INVALID_DEMAND", a.item_id, week, "invalid resource reservation"))
            else:
                usage[(week, resource)] += demand

    for edge in precedences:
        if edge.lag_weeks < 0 or edge.kind not in ("FS", "SS", "FF") or not 0 <= edge.completion_threshold <= 1:
            issues.append(PhysicalViolation("V6_INVALID_EDGE", edge.successor, None, "invalid precedence parameters"))
            continue
        pred = by_id.get(edge.predecessor)
        succ = by_id.get(edge.successor)
        if pred is None or succ is None:
            issues.append(
                PhysicalViolation("V6_UNKNOWN_EDGE_ITEM", edge.successor, None, "predecessor/successor not present")
            )
            continue
        if edge.kind == "FS":
            release = _release_after_scope(pred, edge.completion_threshold)
            if release is None:
                issues.append(
                    PhysicalViolation("V6_UNRELEASED_PREDECESSOR", edge.successor, None, "physical Q threshold unmet")
                )
            elif succ.start_week < release + edge.lag_weeks:
                issues.append(PhysicalViolation(
                    "V6_PREMATURE_FS", edge.successor, succ.start_week,
                    f"start={succ.start_week}; earliest={release + edge.lag_weeks}",
                ))
        elif edge.kind == "SS" and succ.start_week < pred.start_week + edge.lag_weeks:
            issues.append(PhysicalViolation("V6_PREMATURE_SS", edge.successor, succ.start_week, "SS lag violated"))
        elif edge.kind == "FF" and succ.end_week_exclusive < pred.end_week_exclusive + edge.lag_weeks:
            issues.append(
                PhysicalViolation("V6_PREMATURE_FF", edge.successor, succ.end_week_exclusive, "FF lag violated")
            )

    for (week, resource), demand in sorted(usage.items()):
        if pool_capacity is None or resource not in pool_capacity:
            issues.append(PhysicalViolation(
                "V6_POOL_UNVERIFIED", resource, week, "physical resource capacity not supplied",
            ))
            continue
        limit = pool_capacity[resource]
        if limit < 0:
            issues.append(PhysicalViolation("V6_INVALID_POOL", resource, week, "negative pool capacity"))
        elif demand > limit:
            issues.append(PhysicalViolation(
                "V6_POOL_OVERBOOKED", resource, week, f"demand={demand}; capacity={limit}",
            ))
    hard_failure = any(not v.code.endswith("_UNVERIFIED") for v in issues)
    uncertain = any(v.code.endswith("_UNVERIFIED") for v in issues)
    status: AuditStatus = "FAIL" if hard_failure else "UNKNOWN" if uncertain else "PASS"
    return PhysicalCalendarAudit(status, tuple(issues))
