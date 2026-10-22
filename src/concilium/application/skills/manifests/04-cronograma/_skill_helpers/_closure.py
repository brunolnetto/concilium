"""Typed numerical evidence for physical-scope closure (FORMALISMO V1/V5/V6).

Never synthesize production when the calendar or mobilized capacity is exhausted.
Preview may display an infeasibility; certified execution must not turn it into GO.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

# Versioned contract P14-A: the numerical tolerance is independent of monetary
# rounding, and is not scaled by large scopes to hide economically material Q.
SCOPE_TOLERANCE_VERSION = "scope-closure/v1"
SCOPE_ABS_TOL = 1e-9
SCOPE_REL_TOL = 1e-12

ClosureStatus = Literal["PASS", "FAIL", "UNKNOWN"]


@dataclass(frozen=True)
class PhysicalScopeClosure:
    item_id: str
    required: float
    delivered: float
    residual: float
    absolute_error: float
    tolerance: float
    status: ClosureStatus
    calendar_horizon_weeks: int | None
    reason: str

    @property
    def is_closed(self) -> bool:
        return self.status == "PASS"


def assess_scope_closure(
    item_id: str,
    required: float,
    delivered: float,
    *,
    calendar_horizon_weeks: int | None = None,
) -> PhysicalScopeClosure:
    """Check Σq = Q with explicit absolute/relative, versioned tolerances.

    Return UNKNOWN for nonfinite/invalid inputs and FAIL for a finite mismatch.
    An exhausted horizon cannot be extended by inventing future work weeks.
    """
    if calendar_horizon_weeks is not None and calendar_horizon_weeks < 0:
        raise ValueError("calendar_horizon_weeks must be nonnegative")
    if not (math.isfinite(required) and math.isfinite(delivered)) or required < 0 or delivered < 0:
        return PhysicalScopeClosure(
            item_id, required, delivered, math.nan, math.nan, SCOPE_ABS_TOL,
            "UNKNOWN", calendar_horizon_weeks, "INVALID_QUANTITY",
        )
    residual = required - delivered
    tolerance = max(SCOPE_ABS_TOL, required * SCOPE_REL_TOL)
    absolute_error = abs(residual)
    if absolute_error <= tolerance:
        status: ClosureStatus = "PASS"
        reason = "SCOPE_CLOSED"
    elif residual > 0:
        status = "FAIL"
        reason = "CALENDAR_OR_CAPACITY_EXHAUSTED"
    else:
        status = "FAIL"
        reason = "OVERPRODUCTION"
    return PhysicalScopeClosure(
        item_id, required, delivered, residual, absolute_error,
        tolerance, status, calendar_horizon_weeks, reason,
    )
