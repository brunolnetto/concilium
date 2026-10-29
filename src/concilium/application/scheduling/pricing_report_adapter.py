"""P21-C: serialize the same exact pricing evidence across all report surfaces.

The adapter intentionally requires an explicit P20 reconciliation context. It
never reconstructs a financial ledger from rounded legacy display fields.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

from concilium.domain.models.canonical import Resultado, ValidacaoItem

from .financial_cost_reconciliation import (
    ExactFinancialReconciliation,
    reconcile_financial_sources,
)
from .operational_pricing_diagnostics import (
    CatalogPriceBenchmark,
    project_operational_pricing,
)
from .pricing_gates import RegulatoryBdiBasis, evaluate_pricing_gates


@dataclass(frozen=True)
class InventoryEvidenceScope:
    """Provenance-bearing declaration that inventory/holding coverage is complete."""

    status: Literal["NO_INVENTORY", "COMPLETE"]
    source: str
    reference_id: str
    fingerprint: str

    def __post_init__(self) -> None:
        if self.status not in ("NO_INVENTORY", "COMPLETE"):
            raise ValueError("inventory evidence scope must be NO_INVENTORY or COMPLETE")
        if any(not isinstance(value, str) or not value.strip() for value in (
            self.source, self.reference_id, self.fingerprint,
        )):
            raise ValueError("inventory evidence scope requires source, reference and fingerprint")


def _unknown(result: Resultado, validations: list, intent: str, reason: str) -> None:
    status = "AVISO" if intent == "PREVIEW" else "ERRO"
    result.pricing_diagnostics = {"status": "UNKNOWN", "reason": reason}
    result.pricing_gates = {
        "status": "UNKNOWN",
        "regulatory_status": "UNKNOWN",
        "profitability_status": "UNKNOWN",
        "reason": reason,
    }
    result.pricing_authority = "P21_C_PRICING_GATES_UNKNOWN_NOT_PROJECT_GO"
    validations.append(
        ValidacaoItem(
            codigo="VAL-P21-PRICE-EVIDENCE",
            status=status,
            mensagem=(
                "Preço não certificado: " if intent != "PREVIEW" else
                "Diagnóstico de preço indisponível: "
            ) + reason,
        )
    )


def apply_pricing_report_evidence(
    result: Resultado,
    inputs: Mapping[str, object],
    validations: list,
) -> None:
    """Attach exact P21 diagnostics and gates to the canonical Skill 06 result.

    All transports serialize this canonical result, so REST, MCP, UI, RFI and
    RFP see the same status. A missing P20 ledger is UNKNOWN, never PASS.
    """
    intent = str(inputs.get("certification_intent", "PREVIEW")).upper()
    context = inputs.get("p21_pricing_evidence", inputs.get("p20_financial_sources"))
    if not isinstance(context, Mapping):
        _unknown(
            result, validations, intent,
            "missing p21_pricing_evidence with authoritative P20 ledger and explicit bases",
        )
        return
    inventory_scope = context.get("inventory_scope")
    if not isinstance(inventory_scope, InventoryEvidenceScope):
        _unknown(
            result, validations, intent,
            "typed, provenance-bearing P19 inventory scope is required before pricing",
        )
        return
    if inventory_scope.status == "NO_INVENTORY" and (
        context.get("holding_journal") is not None
        or context.get("stock_provisioning_journal") is not None
    ):
        _unknown(
            result, validations, intent,
            "NO_INVENTORY scope conflicts with supplied P19 journals",
        )
        return
    if isinstance(context.get("source_build_error"), str):
        _unknown(result, validations, intent, context["source_build_error"])
        return

    reconciliation = context.get("reconciliation")
    if not isinstance(reconciliation, ExactFinancialReconciliation):
        pool_ledger = context.get("pool_ledger")
        consumption_journal = context.get("consumption_journal")
        if pool_ledger is not None and consumption_journal is not None:
            try:
                reconciliation = reconcile_financial_sources(
                    pool_ledger,
                    consumption_journal,
                    context.get("holding_journal"),
                    context.get("stock_provisioning_journal"),
                )
            except (TypeError, ValueError) as exc:
                _unknown(result, validations, intent, str(exc))
                return
    bdi_by_category = context.get("bdi_by_category")
    catalog = context.get("catalog")
    catalog_metadata = context.get("catalog_metadata")
    operational_basis_fingerprint = context.get("operational_basis_fingerprint")
    regulatory_basis = context.get("regulatory_basis")
    minimum_profit_margin = context.get("minimum_profit_margin")
    if (
        not isinstance(reconciliation, ExactFinancialReconciliation)
        or not isinstance(bdi_by_category, Mapping)
        or not isinstance(catalog, CatalogPriceBenchmark)
        or not isinstance(catalog_metadata, Mapping)
        or not isinstance(operational_basis_fingerprint, str)
        or (regulatory_basis is not None and not isinstance(regulatory_basis, RegulatoryBdiBasis))
        or (
            minimum_profit_margin is not None
            and (type(minimum_profit_margin) is not Fraction or minimum_profit_margin < 0)
        )
    ):
        _unknown(
            result, validations, intent,
            "pricing evidence has missing or invalid exact ledger, catalog, currency, or regulatory inputs",
        )
        return

    try:
        diagnostics = project_operational_pricing(
            reconciliation,
            bdi_by_category=bdi_by_category,
            catalog=catalog,
            catalog_metadata=catalog_metadata,
            operational_basis_fingerprint=operational_basis_fingerprint,
        )
        gates = evaluate_pricing_gates(
            diagnostics,
            regulatory_basis=regulatory_basis,
            catalog_metadata=catalog_metadata,
            minimum_profit_margin=minimum_profit_margin,
        )
    except (TypeError, ValueError) as exc:
        _unknown(result, validations, intent, str(exc))
        return

    result.pricing_diagnostics = {
        "operational_price": str(diagnostics.operational_price),
        "catalog_benchmark": str(diagnostics.catalog_benchmark),
        "direct_cost": str(diagnostics.direct_cost),
        "indirect_cost": str(diagnostics.indirect_cost),
        "total_cost": str(diagnostics.total_cost),
        "profit_amount": str(diagnostics.profit_amount),
        "implied_bdi_on_catalog": (
            str(diagnostics.implied_bdi_on_catalog)
            if diagnostics.implied_bdi_on_catalog is not None else None
        ),
        "cost_ratio_vs_catalog": (
            str(diagnostics.cost_ratio_vs_catalog)
            if diagnostics.cost_ratio_vs_catalog is not None else None
        ),
        "realized_margin": (
            str(diagnostics.realized_margin)
            if diagnostics.realized_margin is not None else None
        ),
        "equivalent_markup": (
            str(diagnostics.equivalent_markup)
            if diagnostics.equivalent_markup is not None else None
        ),
        "catalog_comparison": diagnostics.catalog_comparison,
        "comparison_reason": diagnostics.comparison_reason,
        "currency": diagnostics.operational_currency,
        "currency_source": diagnostics.currency_source,
        "currency_metadata_fingerprint": diagnostics.currency_metadata_fingerprint,
    }
    result.pricing_gates = {
        "status": gates.status,
        "regulatory_status": gates.regulatory_status,
        "profitability_status": gates.profitability_status,
        "regulatory_bdi_rate": str(gates.regulatory_bdi_rate) if gates.regulatory_bdi_rate is not None else None,
        "regulatory_bdi_floor": str(gates.regulatory_bdi_floor) if gates.regulatory_bdi_floor is not None else None,
        "profit_amount": str(gates.profit_amount),
        "realized_margin": str(gates.realized_margin) if gates.realized_margin is not None else None,
        "minimum_profit_margin": str(gates.minimum_profit_margin) if gates.minimum_profit_margin is not None else None,
        "regulatory_basis_reference": gates.regulatory_basis_reference,
        "reasons": "; ".join(gates.reasons),
    }
    result.pricing_authority = gates.authority
    if gates.status != "PASS":
        status = "AVISO" if intent == "PREVIEW" else "ERRO"
        validations.append(
            ValidacaoItem(
                codigo="VAL-P21-PRICE-GATES",
                status=status,
                mensagem=(
                    f"Pricing gates {gates.status}: " + "; ".join(gates.reasons)
                ),
            )
        )
