"""P21-B: keep regulatory BDI-floor and economic-viability gates independent."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

from .operational_pricing_diagnostics import (
    OperationalPricingDiagnostics,
    _verified_catalog_currency,
)

GateStatus = Literal["PASS", "FAIL", "UNKNOWN"]


def _currency(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 3
        or not value.isalpha()
        or not value.isascii()
        or value != value.upper()
    ):
        raise ValueError(f"{field} must be an uppercase ASCII 3-letter currency code")
    return value


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} requires explicit provenance")
    return value


@dataclass(frozen=True)
class RegulatoryBdiBasis:
    """Explicit, comparable denominator and floor for a regulatory BDI check."""

    amount: Fraction
    currency: str
    basis_fingerprint: str
    minimum_rate: Fraction
    source: str
    reference_id: str

    def __post_init__(self) -> None:
        if type(self.amount) is not Fraction or self.amount <= 0:
            raise ValueError("regulatory BDI basis amount must be an exact positive Fraction")
        if type(self.minimum_rate) is not Fraction or self.minimum_rate < 0:
            raise ValueError("regulatory BDI floor must be an exact nonnegative Fraction")
        _currency(self.currency, "regulatory currency")
        _required_text(self.basis_fingerprint, "regulatory basis fingerprint")
        _required_text(self.source, "regulatory basis source")
        _required_text(self.reference_id, "regulatory basis reference")


@dataclass(frozen=True)
class PricingGateEvaluation:
    """Independent gate results; PASS is eligibility evidence, never PROJECT_GO."""

    regulatory_bdi_rate: Fraction | None
    regulatory_bdi_floor: Fraction | None
    regulatory_status: GateStatus
    profitability_status: GateStatus
    status: GateStatus
    profit_amount: Fraction
    realized_margin: Fraction | None
    minimum_profit_margin: Fraction | None
    regulatory_basis_reference: str | None
    reasons: tuple[str, ...]
    authority: str = "P21_B_PRICING_GATES_PREVIEW_NOT_PROJECT_GO"


def _validate_diagnostics(diagnostics: OperationalPricingDiagnostics) -> None:
    values = (
        diagnostics.operational_price,
        diagnostics.direct_cost,
        diagnostics.indirect_cost,
        diagnostics.total_cost,
        diagnostics.profit_amount,
    )
    if any(type(value) is not Fraction for value in values):
        raise ValueError("pricing diagnostics require exact Fraction arithmetic")
    if (
        diagnostics.operational_price < 0
        or diagnostics.direct_cost < 0
        or diagnostics.indirect_cost < 0
        or diagnostics.total_cost < 0
    ):
        raise ValueError("pricing diagnostics cannot contain negative price or cost")
    if diagnostics.direct_cost + diagnostics.indirect_cost != diagnostics.total_cost:
        raise ValueError("pricing diagnostics violate C_tot = C_D + C_ind")
    if diagnostics.profit_amount != diagnostics.operational_price - diagnostics.total_cost:
        raise ValueError("pricing diagnostics violate profit = P - C_tot")
    expected_margin = (
        diagnostics.profit_amount / diagnostics.operational_price
        if diagnostics.operational_price > 0 else None
    )
    if diagnostics.realized_margin != expected_margin:
        raise ValueError("pricing diagnostics realized margin does not reconcile")
    expected_markup = (
        diagnostics.operational_price / diagnostics.total_cost - 1
        if diagnostics.total_cost > 0 else None
    )
    if diagnostics.equivalent_markup != expected_markup:
        raise ValueError("pricing diagnostics equivalent markup does not reconcile")


def evaluate_pricing_gates(
    diagnostics: OperationalPricingDiagnostics,
    *,
    regulatory_basis: RegulatoryBdiBasis | None,
    catalog_metadata: Mapping[str, object],
    minimum_profit_margin: Fraction | None = None,
) -> PricingGateEvaluation:
    """Evaluate regulatory BDI floor and economic viability as separate gates.

    Incomparable or missing regulatory evidence yields UNKNOWN, never PASS.
    Economic viability independently requires P > C_tot and, when supplied,
    the explicit minimum realized-margin threshold. This is not certification.
    """
    if not isinstance(diagnostics, OperationalPricingDiagnostics):
        raise ValueError("P21-A operational pricing diagnostics are required")
    _validate_diagnostics(diagnostics)
    metadata_currency, metadata_source, metadata_fingerprint = (
        _verified_catalog_currency(catalog_metadata)
    )
    if (
        diagnostics.operational_currency != metadata_currency
        or diagnostics.currency_source != metadata_source
        or diagnostics.currency_metadata_fingerprint != metadata_fingerprint
    ):
        raise ValueError(
            "operational currency metadata fingerprint does not match pricing diagnostics"
        )
    if minimum_profit_margin is not None and (
        type(minimum_profit_margin) is not Fraction or minimum_profit_margin < 0
    ):
        raise ValueError("minimum profit margin must be an explicit nonnegative Fraction")
    if regulatory_basis is not None and not isinstance(regulatory_basis, RegulatoryBdiBasis):
        raise ValueError("typed regulatory BDI basis required")

    reasons: list[str] = []
    regulatory_rate: Fraction | None = None
    regulatory_floor: Fraction | None = None
    regulatory_reference: str | None = None
    regulatory_status: GateStatus
    if regulatory_basis is None:
        regulatory_status = "UNKNOWN"
        reasons.append("regulatory BDI basis is missing")
    else:
        regulatory_floor = regulatory_basis.minimum_rate
        regulatory_reference = regulatory_basis.reference_id
        if regulatory_basis.currency != diagnostics.operational_currency:
            regulatory_status = "UNKNOWN"
            reasons.append("regulatory and operational currencies differ")
        elif (
            regulatory_basis.basis_fingerprint
            != diagnostics.operational_basis_fingerprint
        ):
            regulatory_status = "UNKNOWN"
            reasons.append("regulatory and operational physical-scope fingerprints differ")
        else:
            regulatory_rate = (
                diagnostics.operational_price / regulatory_basis.amount - 1
            )
            if regulatory_rate >= regulatory_basis.minimum_rate:
                regulatory_status = "PASS"
            else:
                regulatory_status = "FAIL"
                reasons.append("operational BDI on the regulatory basis is below its floor")

    profitable = diagnostics.operational_price > diagnostics.total_cost
    margin_ok = (
        minimum_profit_margin is None
        or (
            diagnostics.realized_margin is not None
            and diagnostics.realized_margin >= minimum_profit_margin
        )
    )
    if profitable and margin_ok:
        profitability_status: GateStatus = "PASS"
    else:
        profitability_status = "FAIL"
        if not profitable:
            reasons.append("operational price does not exceed total cost")
        if not margin_ok:
            reasons.append("realized margin is below the explicit minimum")

    statuses = (regulatory_status, profitability_status)
    status: GateStatus = (
        "FAIL" if "FAIL" in statuses
        else "UNKNOWN" if "UNKNOWN" in statuses
        else "PASS"
    )
    return PricingGateEvaluation(
        regulatory_rate,
        regulatory_floor,
        regulatory_status,
        profitability_status,
        status,
        diagnostics.profit_amount,
        diagnostics.realized_margin,
        minimum_profit_margin,
        regulatory_reference,
        tuple(reasons),
    )
