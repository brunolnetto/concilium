"""P21-C: the canonical report exposes one shared, fail-closed pricing gate."""
from __future__ import annotations

from fractions import Fraction as F

from concilium.application.scheduling.contractual_cost_ledger import (
    CostPosting,
    ExclusiveCostLedger,
    PostingNature,
)
from concilium.application.scheduling.financial_cost_reconciliation import (
    reconcile_financial_sources,
)
from concilium.application.scheduling.operational_pricing_diagnostics import (
    CatalogPriceBenchmark,
)
from concilium.application.scheduling.physical_consumption_journal import (
    AcquisitionEvidenceLine,
    PhysicalConsumptionJournalResult,
)
from concilium.application.scheduling.physical_consumption_rates import (
    PhysicalPurchaseMeasure,
)
from concilium.application.scheduling.pricing_gates import RegulatoryBdiBasis
from concilium.application.scheduling.pricing_report_adapter import (
    InventoryEvidenceScope,
    apply_pricing_report_evidence,
)
from concilium.domain.models.canonical import Resultado


def _result() -> Resultado:
    return Resultado.model_construct(
        pricing_diagnostics={},
        pricing_gates={},
        pricing_authority="",
    )


def test_preview_without_exact_ledger_is_unknown_and_visible() -> None:
    result = _result()
    validations: list = []
    apply_pricing_report_evidence(result, {"certification_intent": "PREVIEW"}, validations)

    assert result.pricing_gates["status"] == "UNKNOWN"
    assert result.pricing_authority == "P21_C_PRICING_GATES_UNKNOWN_NOT_PROJECT_GO"
    assert validations[-1].codigo == "VAL-P21-PRICE-EVIDENCE"
    assert validations[-1].status == "AVISO"
    payload = result.model_dump()
    assert payload["pricing_gates"]["status"] == "UNKNOWN"
    assert payload["pricing_authority"] == result.pricing_authority


def test_certified_mode_without_exact_ledger_fails_closed() -> None:
    result = _result()
    validations: list = []
    apply_pricing_report_evidence(result, {"certification_intent": "CERTIFIED"}, validations)

    assert result.pricing_gates["status"] == "UNKNOWN"
    assert validations[-1].codigo == "VAL-P21-PRICE-EVIDENCE"
    assert validations[-1].status == "ERRO"


def test_auto_go_without_exact_ledger_fails_closed() -> None:
    result = _result()
    validations: list = []
    apply_pricing_report_evidence(result, {"certification_intent": "AUTO_GO"}, validations)

    assert result.pricing_gates["status"] == "UNKNOWN"
    assert validations[-1].codigo == "VAL-P21-PRICE-EVIDENCE"
    assert validations[-1].status == "ERRO"


def test_rfi_and_rfp_keep_the_same_canonical_pricing_gate_shape() -> None:
    for mode in ("RFI", "RFP"):
        result = _result()
        validations: list = []
        apply_pricing_report_evidence(
            result,
            {"certification_intent": "PREVIEW", "proposal_mode": mode},
            validations,
        )
        payload = result.model_dump()
        assert payload["pricing_gates"]["status"] == "UNKNOWN"
        assert payload["pricing_diagnostics"]["status"] == "UNKNOWN"


def test_invalid_typed_financial_sources_fail_closed_in_auto_go() -> None:
    result = _result()
    validations: list = []
    apply_pricing_report_evidence(
        result,
        {
            "certification_intent": "AUTO_GO",
            "p20_financial_sources": {
                "pool_ledger": object(),
                "consumption_journal": object(),
            },
        },
        validations,
    )
    assert result.pricing_gates["status"] == "UNKNOWN"
    assert validations[-1].codigo == "VAL-P21-PRICE-EVIDENCE"
    assert validations[-1].status == "ERRO"


def test_typed_p20_sources_reach_one_shared_operational_and_regulatory_gate() -> None:
    pool = ExclusiveCostLedger((
        CostPosting(
            ("POOL", "R", "ACTIVE"), PostingNature.ACTIVE,
            "EQ", F(14), "R", "2026-W01",
        ),
        CostPosting(
            ("POOL", "R", "MOB"), PostingNature.MOBILIZATION,
            "IND", F(9), "R", "2026-W01",
        ),
    ))
    evidence = AcquisitionEvidenceLine(
        "c1", "PLANNED_CLOSED_SCOPE", "A", "2026-W01",
        PhysicalPurchaseMeasure("ORE", F(1), "kg", F(1), "kg", F(5, 2)),
        "MAT",
    )
    acquisition = CostPosting(
        ("CONSUMABLE", "c1"), PostingNature.ACQUISITION,
        "MAT", F(5, 2), "ORE", "2026-W01",
    )
    consumption = PhysicalConsumptionJournalResult(
        ExclusiveCostLedger(pool.postings + (acquisition,)), (evidence,),
    )
    catalog_metadata = {
        "currency": "BRL",
        "currency_source": "catalog_metadata.json",
    }
    context = {
        "inventory_scope": InventoryEvidenceScope(
            status="NO_INVENTORY",
            source="test-fixture",
            reference_id="no-inventory-fixture",
            fingerprint="inventory-scope-fingerprint",
        ),
        "pool_ledger": pool,
        "consumption_journal": consumption,
        "bdi_by_category": {
            "MO": F(1, 10),
            "EQ": F(1, 5),
            "MAT": F(1, 2),
            "COMB": F(3, 10),
            "IND": F(1, 4),
        },
        "catalog": CatalogPriceBenchmark(
            amount=F(100),
            currency="BRL",
            source="catalog",
            reference_id="catalog-ref",
            basis_fingerprint="scope-fp",
        ),
        "catalog_metadata": catalog_metadata,
        "operational_basis_fingerprint": "scope-fp",
        "regulatory_basis": RegulatoryBdiBasis(
            amount=F(100),
            currency="BRL",
            basis_fingerprint="scope-fp",
            minimum_rate=F(1, 10),
            source="regulatory",
            reference_id="regulatory-ref",
        ),
        "minimum_profit_margin": F(0),
    }
    result = _result()
    validations: list = []
    apply_pricing_report_evidence(
        result,
        {"certification_intent": "PREVIEW", "p20_financial_sources": context},
        validations,
    )

    assert result.pricing_diagnostics["operational_price"] == "159/5"
    assert result.pricing_diagnostics["total_cost"] == "51/2"
    assert result.pricing_gates["regulatory_status"] == "FAIL"
    assert result.pricing_gates["profitability_status"] == "PASS"
    assert result.pricing_gates["status"] == "FAIL"
    assert validations[-1].codigo == "VAL-P21-PRICE-GATES"
    assert validations[-1].status == "AVISO"
