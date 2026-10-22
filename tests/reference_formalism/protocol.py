"""Standalone *exact* rational reference protocol; never imports Concilium.

P22-A defines a verifiable scalar K/V baseline using decimal-string inputs.
Internally calculations use Fraction, not mutable Decimal context precision.
Nonterminating rational outputs are rejected rather than silently rounded.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from fractions import Fraction
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
    """A reference vector is invalid or disagrees with exact arithmetic."""


def decimal_input(value: Any, name: str) -> Fraction:
    """Parse a decimal string as an exact rational (no binary or decimal rounding)."""
    if not isinstance(value, str):
        raise ReferenceContractError(f"{name} must be an exact decimal string")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ReferenceContractError(f"{name} is not a decimal value") from exc
    if not result.is_finite():
        raise ReferenceContractError(f"{name} must be finite")
    return Fraction(result)


def _finite_decimal(value: Fraction, name: str) -> str:
    """Render a terminating rational exactly, rejecting nonterminating quotients."""
    denominator = value.denominator
    twos = 0
    fives = 0
    while denominator % 2 == 0:
        denominator //= 2
        twos += 1
    while denominator % 5 == 0:
        denominator //= 5
        fives += 1
    if denominator != 1:
        raise ReferenceContractError(
            f"{name} has a nonterminating decimal expansion; "
            "reference protocol requires a separate exact rational output policy"
        )
    scale = max(twos, fives)
    unsigned = abs(value.numerator) * 2 ** (scale - twos) * 5 ** (scale - fives)
    sign = "-" if value < 0 else ""
    if not scale:
        return sign + str(unsigned)
    digits = str(unsigned).zfill(scale + 1)
    whole, fractional = digits[:-scale], digits[-scale:].rstrip("0")
    return sign + whole + ("." + fractional if fractional else "")


def evaluate_vector(vector: dict[str, Any]) -> dict[str, str]:
    """Exact scalar K/V baseline only; no production-runtime certification."""
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
    if p["team_count"].denominator != 1:
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
    return {key: _finite_decimal(value, key) for key, value in results.items()}


def verify_golden(vector: dict[str, Any]) -> dict[str, str]:
    expected = vector.get("expected")
    if not isinstance(expected, dict) or set(expected) != OUTPUTS:
        raise ReferenceContractError("golden outputs must match the reference contract")
    actual = evaluate_vector(vector)
    for key in OUTPUTS:
        if decimal_input(actual[key], key) != decimal_input(expected[key], key):
            raise ReferenceContractError(
                f"{vector.get('case_id', 'unknown')} / {key}: "
                f"actual={actual[key]}, expected={expected[key]}"
            )
    return actual
