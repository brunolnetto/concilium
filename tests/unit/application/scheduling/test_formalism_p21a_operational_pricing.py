"""P21-A: independent arithmetic and fail-closed catalog comparability."""
from __future__ import annotations

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


def _rates() -> dict[str, F]:
    return {
        "MO": F(1, 10), "EQ": F(1, 5), "MAT": F(1, 2),
        "COMB": F(3, 10), "IND": F(1, 4),
    }


def _catalog(*, amount: F = F(30), currency: str = "BRL", basis: str = "scope-v1"):
    return CatalogPriceBenchmark(
        amount, currency, "catalog://benchmark/42", "benchmark-42", basis,
    )


def test_p21a_all_diagnostics_reconstruct_from_one_exact_ledger() -> None:
    result = project_operational_pricing(
        _reconciliation(),
        bdi_by_category=_rates(),
        catalog=_catalog(),
        catalog_metadata={"currency": "BRL", "currency_source": "catalog_metadata.json"},
        operational_basis_fingerprint="scope-v1",
    )

    assert result.operational_price == F(159, 5)
    assert result.catalog_benchmark == F(30)
    assert result.direct_cost == F(33, 2)
    assert result.indirect_cost == F(9)
    assert result.total_cost == F(51, 2)
    assert result.profit_amount == F(63, 10)
    assert result.implied_bdi_on_catalog == F(3, 50)
    assert result.cost_ratio_vs_catalog == F(17, 20)
    assert result.realized_margin == F(21, 106)
    assert result.equivalent_markup == F(21, 85)
    assert result.catalog_comparison == "COMPARABLE"
    assert result.comparison_reason is None
    assert result.authority == "P21_A_PRICING_DIAGNOSTICS_PREVIEW_NOT_PROJECT_GO"


@pytest.mark.parametrize(
    ("currency", "basis", "expected_reason"),
    [
        ("USD", "scope-v1", "currencies differ"),
        ("BRL", "different-scope", "fingerprints differ"),
    ],
)
def test_p21a_incomparable_catalog_keeps_operational_metrics_but_undefines_ratios(
    currency: str,
    basis: str,
    expected_reason: str,
) -> None:
    result = project_operational_pricing(
        _reconciliation(),
        bdi_by_category=_rates(),
        catalog=_catalog(currency=currency, basis=basis),
        operational_currency="BRL",
        currency_source="catalog_metadata.json",
        operational_basis_fingerprint="scope-v1",
    )

    assert result.operational_price == F(159, 5)
    assert result.total_cost == F(51, 2)
    assert result.realized_margin == F(21, 106)
    assert result.equivalent_markup == F(21, 85)
    assert result.catalog_comparison == "UNDEFINED"
    assert result.implied_bdi_on_catalog is None
    assert result.cost_ratio_vs_catalog is None
    assert expected_reason in (result.comparison_reason or "")


def test_p21a_zero_catalog_benchmark_does_not_divide_by_zero() -> None:
    result = project_operational_pricing(
        _reconciliation(),
        bdi_by_category=_rates(),
        catalog=_catalog(amount=F(0)),
        operational_currency="BRL",
        currency_source="catalog_metadata.json",
        operational_basis_fingerprint="scope-v1",
    )
    assert result.catalog_comparison == "UNDEFINED"
    assert result.implied_bdi_on_catalog is None
    assert result.cost_ratio_vs_catalog is None
    assert "must be positive" in (result.comparison_reason or "")


def test_p21a_missing_currency_provenance_is_not_accepted() -> None:
    with pytest.raises(ValueError, match="catalog_metadata.json provenance"):
        project_operational_pricing(
            _reconciliation(),
            bdi_by_category=_rates(),
            catalog=_catalog(),
            catalog_metadata={"currency": "BRL", "currency_source": "user-input"},
            operational_basis_fingerprint="scope-v1",
        )


def test_p21a_catalog_benchmark_requires_exact_values_and_provenance() -> None:
    with pytest.raises(ValueError, match="exact nonnegative Fraction"):
        CatalogPriceBenchmark(30.0, "BRL", "catalog", "ref", "scope-v1")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="uppercase ASCII"):
        _catalog(currency="ÅBC")
    with pytest.raises(ValueError, match="provenance"):
        CatalogPriceBenchmark(F(30), "BRL", "", "ref", "scope-v1")
