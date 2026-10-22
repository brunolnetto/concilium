"""Standalone decimal reference protocol. No imports from concilium runtime.

P22-A verifies the *shape* and independently calculated scalar baseline;
P22-B/C extend the evaluator after the mathematical spec is corrected.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

PROTOCOL_VERSION = "formalism-reference/1"
INPUTS = frozenset({
    "scope_total", "quantity_before_final_week", "nominal_final_week_capacity",
    "hours_per_week", "team_count", "contractual_rate_per_team_hour",
    "variable_rate_per_team_hour", "productivity_per_team_hour",
})
OUTPUTS = frozenset({
    "final_week_quantity", "scope_residual", "contractual_final_week_cost",
    "variable_final_week_cost", "variable_total_cost",
})


class ReferenceContractError(ValueError):
    """A reference vector is invalid or disagrees with a hand-checked result."""


def decimal_input(value: Any, name: str) -> Decimal:
    if not isinstance(value, str):
        raise ReferenceContractError(f"{name} must be an exact decimal string")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ReferenceContractError(f"{name} is not a decimal value") from exc
    if not result.is_finite():
        raise ReferenceContractError(f"{name} must be finite")
    return result


def evaluate_vector(vector: dict[str, Any]) -> dict[str, str]:
    """Exact scalar K/V baseline only. Not a full production or pricing oracle."""
    if vector.get("protocol") != PROTOCOL_VERSION:
        raise ReferenceContractError("unsupported reference protocol")
    fields = vector.get("inputs")
    if not isinstance(fields, dict) or set(fields) != INPUTS:
        raise ReferenceContractError("missing or unknown reference input fields")
    p = {key: decimal_input(fields[key], key) for key in INPUTS}
    for name in (
        "scope_total", "nominal_final_week_capacity", "hours_per_week",
        "team_count", "productivity_per_team_hour",
    ):
        if p[name] <= 0:
            raise ReferenceContractError(f"{name} must be positive")
    if p["team_count"] != p["team_count"].to_integral_value():
        raise ReferenceContractError("team_count must be an integer")
    if not 0 <= p["quantity_before_final_week"] < p["scope_total"]:
        raise ReferenceContractError("invalid previously delivered quantity")
    if p["contractual_rate_per_team_hour"] < 0 or p["variable_rate_per_team_hour"] < 0:
        raise ReferenceContractError("cost rates must be nonnegative")

    last_quantity = p["scope_total"] - p["quantity_before_final_week"]
    if last_quantity > p["nominal_final_week_capacity"]:
        raise ReferenceContractError("final-week capacity cannot close scope")

    results = {
        "final_week_quantity": last_quantity,
        "scope_residual": p["scope_total"] - (p["quantity_before_final_week"] + last_quantity),
        "contractual_final_week_cost": (
            p["contractual_rate_per_team_hour"] * p["hours_per_week"] * p["team_count"]
        ),
        "variable_final_week_cost": (
            p["variable_rate_per_team_hour"] * last_quantity / p["productivity_per_team_hour"]
        ),
        "variable_total_cost": (
            p["variable_rate_per_team_hour"] * p["scope_total"] / p["productivity_per_team_hour"]
        ),
    }
    return {key: format(value, "f") for key, value in results.items()}


def verify_golden(vector: dict[str, Any]) -> dict[str, str]:
    expected = vector.get("expected")
    if not isinstance(expected, dict) or set(expected) != OUTPUTS:
        raise ReferenceContractError("golden outputs must match the reference contract")
    actual = evaluate_vector(vector)
    for key in OUTPUTS:
        if Decimal(actual[key]) != decimal_input(expected[key], key):
            raise ReferenceContractError(
                f"{vector.get('case_id', 'unknown')} / {key}: "
                f"actual={actual[key]}, expected={expected[key]}"
            )
    return actual
