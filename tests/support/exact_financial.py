"""Small exact-financial fixtures for unit tests (#206, W3-A).

``evaluated_resultado`` runs the real P21 adapter over a tiny typed P20 ledger
(EQ 14 + MAT 5/2 direct, IND 9 indirect), so the view is tested against what
the pricing adapter actually persists:

* total cost 51/2 (direct 33/2, indirect 9), price 159/5;
* layers: overhead 81/40, profit 171/40, taxes 0; profit share 57/424.

The legacy float fields are deliberately absurd by default: nothing exact may
depend on them.
"""
from __future__ import annotations

from fractions import Fraction as F
from types import SimpleNamespace
from typing import Any

from concilium.application.scheduling.contractual_cost_ledger import (
    CostPosting,
    ExclusiveCostLedger,
    PostingNature,
)
from concilium.application.scheduling.markup_layers import LayerRates
from concilium.application.scheduling.operational_pricing_diagnostics import CatalogPriceBenchmark
from concilium.application.scheduling.physical_consumption_journal import (
    AcquisitionEvidenceLine,
    PhysicalConsumptionJournalResult,
)
from concilium.application.scheduling.physical_consumption_rates import PhysicalPurchaseMeasure
from concilium.application.scheduling.pricing_gates import RegulatoryBdiBasis
from concilium.application.scheduling.pricing_report_adapter import (
    InventoryEvidenceScope,
    SiteIndirectsScope,
    apply_pricing_report_evidence,
)
from concilium.domain.models.canonical import Resultado

ABSURD_LEGACY: dict[str, Any] = {
    "venda": SimpleNamespace(total_com_bdi=-1.0e30),
    "custo": SimpleNamespace(total=9.9e30, direto_equipes=-7.0e29),
    "resultado_financeiro": float("nan"),
    "margem_pct": 12345.678,
    "status_margem": "VERDE",
}


def typed_context(*, regulatory_floor: F = F(1, 10), minimum_profit_margin: F | None = F(0)) -> dict[str, object]:
    pool = ExclusiveCostLedger((
        CostPosting(("POOL", "R", "ACTIVE"), PostingNature.ACTIVE, "EQ", F(14), "R", "2026-W01"),
        CostPosting(("POOL", "R", "MOB"), PostingNature.MOBILIZATION, "IND", F(9), "R", "2026-W01"),
    ))
    evidence = AcquisitionEvidenceLine(
        "c1", "PLANNED_CLOSED_SCOPE", "A", "2026-W01",
        PhysicalPurchaseMeasure("ORE", F(1), "kg", F(1), "kg", F(5, 2)),
        "MAT",
    )
    acquisition = CostPosting(("CONSUMABLE", "c1"), PostingNature.ACQUISITION, "MAT", F(5, 2), "ORE", "2026-W01")
    consumption = PhysicalConsumptionJournalResult(ExclusiveCostLedger(pool.postings + (acquisition,)), (evidence,))
    return {
        "inventory_scope": InventoryEvidenceScope(
            status="NO_INVENTORY", source="test-fixture",
            reference_id="no-inventory-fixture", fingerprint="inventory-scope-fingerprint",
        ),
        "site_indirects_scope": SiteIndirectsScope(
            status="NO_SITE_INDIRECTS", source="test-fixture",
            reference_id="no-site-indirects-fixture", fingerprint="site-indirects-scope-fingerprint",
        ),
        "pool_ledger": pool,
        "consumption_journal": consumption,
        "bdi_by_category": {"MO": F(1, 10), "EQ": F(1, 5), "MAT": F(1, 2), "COMB": F(3, 10), "IND": F(1, 4)},
        "markup_layers": {
            "MO": LayerRates(F(0), F(0), F(0), F(1, 10)),
            "EQ": LayerRates(F(1, 10), F(0), F(0), F(1, 11)),
            "MAT": LayerRates(F(1, 4), F(0), F(0), F(1, 5)),
            "COMB": LayerRates(F(1, 10), F(0), F(0), F(2, 11)),
            "IND": LayerRates(F(0), F(0), F(0), F(1, 4)),
        },
        "bdi_floor_by_category": {"MO": F(1, 4), "EQ": F(1, 10), "MAT": F(1, 10), "COMB": F(1, 10), "IND": F(1, 10)},
        "catalog": CatalogPriceBenchmark(
            amount=F(25), currency="BRL", source="catalog",
            reference_id="catalog-ref", basis_fingerprint="scope-fp",
        ),
        "catalog_metadata": {"currency": "BRL", "currency_source": "catalog_metadata.json"},
        "operational_basis_fingerprint": "scope-fp",
        "regulatory_basis": RegulatoryBdiBasis(
            amount=F(25), currency="BRL", basis_fingerprint="scope-fp",
            minimum_rate=regulatory_floor, source="regulatory", reference_id="regulatory-ref",
        ),
        "minimum_profit_margin": minimum_profit_margin,
    }


def _blank(legacy: dict[str, Any] | None) -> Resultado:
    return Resultado.model_construct(
        pricing_diagnostics={}, pricing_gates={}, pricing_authority="", markup_layers=None,
        validacoes=[], **(ABSURD_LEGACY if legacy is None else legacy),
    )


def evaluated_resultado(legacy: dict[str, Any] | None = None, **context_overrides: Any) -> Resultado:
    """A Resultado whose exact pricing was evaluated by the real P21 adapter."""
    result = _blank(legacy)
    apply_pricing_report_evidence(
        result, {"certification_intent": "PREVIEW", "p20_financial_sources": typed_context(**context_overrides)}, [],
    )
    assert result.pricing_diagnostics.get("status") != "UNKNOWN", result.pricing_diagnostics
    return result


def unknown_resultado(inputs: dict[str, Any] | None = None, legacy: dict[str, Any] | None = None) -> Resultado:
    """A Resultado the real P21 adapter left not evaluated (reason recorded by the adapter)."""
    result = _blank(legacy)
    apply_pricing_report_evidence(result, {"certification_intent": "PREVIEW", **(inputs or {})}, [])
    assert result.pricing_diagnostics["status"] == "UNKNOWN"
    return result


def contract(contrato_id: str, *, witnessed: bool) -> SimpleNamespace:
    return SimpleNamespace(
        contrato_id=contrato_id, tipo_id=contrato_id.upper(),
        p16_global_assignment={"schema": "fixture"} if witnessed else None,
    )


def canonical(
    resultado: Any,
    *,
    contracts: list[Any] | None = None,
    p18: Any = "default",
    **extra: Any,
) -> SimpleNamespace:
    """Minimal canonical: witnessed pool + recorded P18 unless told otherwise."""
    return SimpleNamespace(
        resultado=resultado,
        contratos_recurso=[contract("c-eq", witnessed=True)] if contracts is None else contracts,
        p18_consumption_preview={"schema": "fixture"} if p18 == "default" else p18,
        ponto_equilibrio=[],
        **extra,
    )
