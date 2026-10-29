"""P21-A: derive operational pricing diagnostics from the reconciled P20 ledger."""
from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping
from fractions import Fraction
from typing import Literal

from .financial_cost_reconciliation import ExactFinancialReconciliation

_CURRENCY_SOURCE = "catalog_metadata.json"


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


def _verified_catalog_currency(metadata: Mapping[str, object]) -> tuple[str, str, str]:
    """Read currency/source and fingerprint the same resolved metadata object."""
    if not isinstance(metadata, Mapping):
        raise ValueError("resolved catalog currency metadata is required")
    if any(not isinstance(key, str) for key in metadata):
        raise ValueError("catalog metadata keys must be strings")
    currency = metadata.get("currency")
    source = metadata.get("currency_source")
    if source != _CURRENCY_SOURCE:
        raise ValueError("operational currency must use catalog_metadata.json provenance")
    try:
        canonical = json.dumps(
            dict(metadata), sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("catalog currency metadata must be canonical JSON data") from exc
    fingerprint = sha256(
        b"concilium.catalog-currency-metadata.v1\\0" + canonical.encode("utf-8")
    ).hexdigest()
    return _currency(currency, "operational currency"), _CURRENCY_SOURCE, fingerprint


@dataclass(frozen=True)
class CatalogPriceBenchmark:
    """A catalog comparison value with explicit currency and scope provenance."""

    amount: Fraction
    currency: str
    source: str
    reference_id: str
    basis_fingerprint: str

    def __post_init__(self) -> None:
        if type(self.amount) is not Fraction or self.amount < 0:
            raise ValueError("catalog benchmark amount must be an exact nonnegative Fraction")
        _currency(self.currency, "catalog currency")
        _required_text(self.source, "catalog benchmark source")
        _required_text(self.reference_id, "catalog benchmark reference")
        _required_text(self.basis_fingerprint, "catalog benchmark basis fingerprint")


@dataclass(frozen=True)
class OperationalPricingDiagnostics:
    """Exact operational ratios; catalog ratios remain undefined when bases differ."""

    operational_price: Fraction
    catalog_benchmark: Fraction
    direct_cost: Fraction
    indirect_cost: Fraction
    total_cost: Fraction
    profit_amount: Fraction
    implied_bdi_on_catalog: Fraction | None
    cost_ratio_vs_catalog: Fraction | None
    realized_margin: Fraction | None
    equivalent_markup: Fraction | None
    catalog_comparison: Literal["COMPARABLE", "UNDEFINED"]
    comparison_reason: str | None
    operational_currency: str
    currency_source: str
    currency_metadata_fingerprint: str
    catalog_currency: str
    operational_basis_fingerprint: str
    catalog_basis_fingerprint: str
    authority: str = "P21_A_PRICING_DIAGNOSTICS_PREVIEW_NOT_PROJECT_GO"


def project_operational_pricing(
    reconciliation: ExactFinancialReconciliation,
    *,
    bdi_by_category: Mapping[str, Fraction],
    catalog: CatalogPriceBenchmark,
    catalog_metadata: Mapping[str, object],
    operational_basis_fingerprint: str,
) -> OperationalPricingDiagnostics:
    """Derive P, C_D, C_ind, C_tot and ratios from one exact source ledger.

    The catalog-based BDI and cost ratio are diagnostics only. They are
    undefined unless the catalog and operational values have matching currency
    and the caller supplies the same explicit physical-scope fingerprint.
    Regulatory BDI-floor evaluation belongs to P21-B, not this function.
    """
    if not isinstance(reconciliation, ExactFinancialReconciliation):
        raise ValueError("P20 exact financial reconciliation is required")
    if not isinstance(catalog, CatalogPriceBenchmark):
        raise ValueError("typed catalog price benchmark is required")
    operational_currency, currency_source, currency_fingerprint = (
        _verified_catalog_currency(catalog_metadata)
    )
    operational_basis_fingerprint = _required_text(
        operational_basis_fingerprint, "operational basis fingerprint",
    )
    priced = reconciliation.project_price_once_bdi(bdi_by_category)
    price = priced.price_once_bdi
    total_cost = reconciliation.ledger.total
    profit = price - total_cost
    margin = profit / price if price > 0 else None
    equivalent_markup = price / total_cost - 1 if total_cost > 0 else None

    reasons: list[str] = []
    if operational_currency != catalog.currency:
        reasons.append("catalog and operational currencies differ")
    if operational_basis_fingerprint != catalog.basis_fingerprint:
        reasons.append("catalog and operational physical-scope fingerprints differ")
    if catalog.amount <= 0:
        reasons.append("catalog benchmark must be positive")
    comparable = not reasons
    implied_bdi = price / catalog.amount - 1 if comparable else None
    cost_ratio = total_cost / catalog.amount if comparable else None
    return OperationalPricingDiagnostics(
        operational_price=price,
        catalog_benchmark=catalog.amount,
        direct_cost=reconciliation.ledger.direct,
        indirect_cost=reconciliation.ledger.indirect,
        total_cost=total_cost,
        profit_amount=profit,
        implied_bdi_on_catalog=implied_bdi,
        cost_ratio_vs_catalog=cost_ratio,
        realized_margin=margin,
        equivalent_markup=equivalent_markup,
        catalog_comparison="COMPARABLE" if comparable else "UNDEFINED",
        comparison_reason="; ".join(reasons) if reasons else None,
        operational_currency=operational_currency,
        currency_source=currency_source,
        currency_metadata_fingerprint=currency_fingerprint,
        catalog_currency=catalog.currency,
        operational_basis_fingerprint=operational_basis_fingerprint,
        catalog_basis_fingerprint=catalog.basis_fingerprint,
    )
