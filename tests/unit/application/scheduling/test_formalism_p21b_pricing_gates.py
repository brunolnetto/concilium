"""P21-B: adversarial separation of regulatory BDI and economic gates."""
from __future__ import annotations

from dataclasses import replace
from fractions import Fraction as F

import pytest

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
    project_operational_pricing,
)
from concilium.application.scheduling.physical_consumption_journal import (
    AcquisitionEvidenceLine,
    PhysicalConsumptionJournalResult,
)
from concilium.application.scheduling.physical_consumption_rates import (
    PhysicalPurchaseMeasure,
)
from concilium.application.scheduling.pricing_gates import (
    RegulatoryBdiBasis,
    evaluate_pricing_gates,
)
def _rates() -> dict[str, F]:
    return {
        "MO": F(1, 10), "EQ": F(1, 5), "MAT": F(1, 2),
        "COMB": F(3, 10), "IND": F(1, 4),
    }


def _reconciliation():
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
    return reconcile_financial_sources(pool, consumption)


def _diagnostics():
    return project_operational_pricing(
        _reconciliation(),
        bdi_by_category=_rates(),
        catalog=CatalogPriceBenchmark(
            F(30), "BRL", "catalog-source", "catalog-ref", "scope-v1",
        ),
        catalog_metadata={"currency": "BRL", "currency_source": "catalog_metadata.json"},
        operational_basis_fingerprint="scope-v1",
    )


def _regulatory(
    *,
    amount: F = F(30),
    floor: F = F(1, 20),
    currency: str = "BRL",
    basis: str = "scope-v1",
) -> RegulatoryBdiBasis:
    return RegulatoryBdiBasis(
        amount, currency, basis, floor, "TCU-regulatory-source", "TCU-basis-v1",
    )


def test_p21b_regulatory_floor_and_profitability_pass_independently() -> None:
    result = evaluate_pricing_gates(
        _diagnostics(),
        regulatory_basis=_regulatory(),
        minimum_profit_margin=F(1, 10),
    )
    assert result.regulatory_bdi_rate == F(3, 50)
    assert result.regulatory_status == "PASS"
    assert result.profitability_status == "PASS"
    assert result.status == "PASS"
    assert result.authority == "P21_B_PRICING_GATES_PREVIEW_NOT_PROJECT_GO"


def test_p21b_bdi_floor_pass_cannot_override_a_loss() -> None:
    # Adversarial legacy/alternate selling price: a strong regulatory markup
    # does not make a project economically viable when P < C_tot.
    original = _diagnostics()
    loss = replace(
        original,
        operational_price=F(20),
        profit_amount=F(-11, 2),
        implied_bdi_on_catalog=F(-1, 3),
        realized_margin=F(-11, 40),
        equivalent_markup=F(-11, 51),
    )
    result = evaluate_pricing_gates(
        loss,
        regulatory_basis=_regulatory(amount=F(10), floor=F(1, 2)),
    )
    assert result.regulatory_bdi_rate == F(1)
    assert result.regulatory_status == "PASS"
    assert result.profitability_status == "FAIL"
    assert result.status == "FAIL"
    assert "does not exceed total cost" in " ".join(result.reasons)


def test_p21b_profitable_price_does_not_pass_a_failed_regulatory_floor() -> None:
    result = evaluate_pricing_gates(
        _diagnostics(),
        regulatory_basis=_regulatory(floor=F(1, 10)),
        minimum_profit_margin=F(1, 10),
    )
    assert result.regulatory_bdi_rate == F(3, 50)
    assert result.regulatory_status == "FAIL"
    assert result.profitability_status == "PASS"
    assert result.status == "FAIL"


@pytest.mark.parametrize(
    ("basis", "expected_reason"),
    [
        (None, "basis is missing"),
        (_regulatory(currency="USD"), "currencies differ"),
        (_regulatory(basis="other-scope"), "fingerprints differ"),
    ],
)
def test_p21b_missing_or_incomparable_regulatory_basis_is_unknown(
    basis: RegulatoryBdiBasis | None,
    expected_reason: str,
) -> None:
    result = evaluate_pricing_gates(
        _diagnostics(),
        regulatory_basis=basis,
    )
    assert result.regulatory_status == "UNKNOWN"
    assert result.profitability_status == "PASS"
    assert result.status == "UNKNOWN"
    assert expected_reason in " ".join(result.reasons)


def test_p21b_explicit_margin_floor_is_not_conflated_with_regulatory_bdi() -> None:
    result = evaluate_pricing_gates(
        _diagnostics(),
        regulatory_basis=_regulatory(),
        minimum_profit_margin=F(1, 4),
    )
    assert result.regulatory_status == "PASS"
    assert result.profitability_status == "FAIL"
    assert result.status == "FAIL"
    assert "below the explicit minimum" in " ".join(result.reasons)


def test_p21b_inconsistent_diagnostics_and_implicit_currency_fail_closed() -> None:
    original = _diagnostics()
    forged = replace(original, profit_amount=F(0))
    with pytest.raises(ValueError, match="profit = P - C_tot"):
        evaluate_pricing_gates(
            forged,
            regulatory_basis=_regulatory(),
        )
    forged_provenance = replace(original, currency_source="user-input")
    with pytest.raises(ValueError, match="catalog_metadata.json provenance"):
        evaluate_pricing_gates(
            forged_provenance,
            regulatory_basis=_regulatory(),
        )


def test_p21b_regulatory_basis_requires_exact_positive_denominator_and_floor() -> None:
    with pytest.raises(ValueError, match="exact positive Fraction"):
        RegulatoryBdiBasis(F(0), "BRL", "scope-v1", F(1, 20), "source", "ref")
    with pytest.raises(ValueError, match="exact nonnegative Fraction"):
        RegulatoryBdiBasis(F(30), "BRL", "scope-v1", -F(1, 20), "source", "ref")
