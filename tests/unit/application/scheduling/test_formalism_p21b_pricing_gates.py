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
from concilium.application.scheduling.markup_layers import LayerRates, decompose_by_category
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


def _layers() -> dict[str, LayerRates]:
    """Declared layers whose own markup is exactly ``_rates()`` (N9: layers are mandatory).

    MO 1.1; EQ 1.1 * 12/11 = 1.2; MAT 1.25 * 1.2 = 1.5; COMB 1.1 * 13/11 = 1.3; IND 1.25.
    """
    layers = {
        "MO": LayerRates(F(0), F(0), F(0), F(1, 10)),
        "EQ": LayerRates(F(1, 10), F(0), F(0), F(1, 11)),
        "MAT": LayerRates(F(1, 4), F(0), F(0), F(1, 5)),
        "COMB": LayerRates(F(1, 10), F(0), F(0), F(2, 11)),
        "IND": LayerRates(F(0), F(0), F(0), F(1, 4)),
    }
    assert {category: rates.beta for category, rates in layers.items()} == _rates()
    return layers


def _profit_layer() -> F:
    """Profit layer of the fixture ledger: EQ 14 * 1.1 / 11 = 7/5; IND 9 / 4 = 9/4;
    MAT 5/2 * 1.25 / 5 = 5/8 -> 171/40 (of P - C = 63/10; the rest is overhead)."""
    _by_category, total = decompose_by_category(
        ((row.category, row.amount) for row in _reconciliation().ledger.postings), _layers()
    )
    assert total.profit == F(171, 40)
    return total.profit


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
        catalog_metadata={"currency": "BRL", "currency_source": "catalog_metadata.json"},
        minimum_profit_margin=F(1, 10),
        profit_layer_amount=_profit_layer(),
    )
    assert result.regulatory_bdi_rate == F(3, 50)
    assert result.regulatory_status == "PASS"
    # Profit layer 171/40 over P 159/5 = 57/424 (~13.4%) >= 1/10.
    assert result.profit_layer_share == F(57, 424)
    assert result.profitability_status == "PASS"
    assert result.status == "PASS"
    assert result.authority == "P21_B_PRICING_GATES_PREVIEW_NOT_PROJECT_GO"


def test_p21b_bdi_floor_pass_cannot_override_a_price_at_cost() -> None:
    # A strong regulatory markup does not make a project economically viable
    # when the price does not exceed the cost. With mandatory nonnegative layers
    # the reachable case is P = C_tot (all layers zero): P = C = 51/2.
    original = _diagnostics()
    at_cost = replace(
        original,
        operational_price=F(51, 2),
        profit_amount=F(0),
        implied_bdi_on_catalog=F(-3, 20),
        realized_margin=F(0),
        equivalent_markup=F(0),
    )
    result = evaluate_pricing_gates(
        at_cost,
        regulatory_basis=_regulatory(amount=F(10), floor=F(1, 2)),
        catalog_metadata={"currency": "BRL", "currency_source": "catalog_metadata.json"},
        profit_layer_amount=F(0),
    )
    assert result.regulatory_bdi_rate == F(31, 20)
    assert result.regulatory_status == "PASS"
    assert result.profitability_status == "FAIL"
    assert result.status == "FAIL"
    assert "does not exceed total cost" in " ".join(result.reasons)


def test_p21b_a_loss_has_no_profit_layer_and_is_not_evaluated() -> None:
    # Adversarial alternate selling price below cost (P 20 < C_tot 51/2): no
    # nonnegative profit layer fits inside P - C_tot < 0, so the gate refuses
    # the evidence instead of grading it (the adapter reports UNKNOWN).
    loss = replace(
        _diagnostics(),
        operational_price=F(20),
        profit_amount=F(-11, 2),
        implied_bdi_on_catalog=F(-1, 3),
        realized_margin=F(-11, 40),
        equivalent_markup=F(-11, 51),
    )
    for claimed in (F(0), _profit_layer()):
        with pytest.raises(ValueError, match="profit layer"):
            evaluate_pricing_gates(
                loss,
                regulatory_basis=_regulatory(amount=F(10), floor=F(1, 2)),
                catalog_metadata={"currency": "BRL", "currency_source": "catalog_metadata.json"},
                profit_layer_amount=claimed,
            )


def test_p21b_profitable_price_does_not_pass_a_failed_regulatory_floor() -> None:
    result = evaluate_pricing_gates(
        _diagnostics(),
        regulatory_basis=_regulatory(floor=F(1, 10)),
        catalog_metadata={"currency": "BRL", "currency_source": "catalog_metadata.json"},
        minimum_profit_margin=F(1, 10),
        profit_layer_amount=_profit_layer(),
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
        catalog_metadata={"currency": "BRL", "currency_source": "catalog_metadata.json"},
        profit_layer_amount=_profit_layer(),
    )
    assert result.regulatory_status == "UNKNOWN"
    assert result.profitability_status == "PASS"
    assert result.status == "UNKNOWN"
    assert expected_reason in " ".join(result.reasons)


def test_p21b_explicit_margin_floor_is_not_conflated_with_regulatory_bdi() -> None:
    result = evaluate_pricing_gates(
        _diagnostics(),
        regulatory_basis=_regulatory(),
        catalog_metadata={"currency": "BRL", "currency_source": "catalog_metadata.json"},
        minimum_profit_margin=F(1, 4),
        profit_layer_amount=_profit_layer(),
    )
    assert result.regulatory_status == "PASS"
    assert result.profitability_status == "FAIL"
    assert result.status == "FAIL"
    assert "profit-layer share of the price is below the explicit minimum" in result.reasons


def test_p21b_inconsistent_diagnostics_and_implicit_currency_fail_closed() -> None:
    original = _diagnostics()
    forged = replace(original, profit_amount=F(0))
    with pytest.raises(ValueError, match="profit = P - C_tot"):
        evaluate_pricing_gates(
            forged,
            regulatory_basis=_regulatory(),
            catalog_metadata={"currency": "BRL", "currency_source": "catalog_metadata.json"},
            profit_layer_amount=F(0),
        )
    forged_provenance = replace(original, currency_source="user-input")
    with pytest.raises(ValueError, match="currency metadata fingerprint"):
        evaluate_pricing_gates(
            forged_provenance,
            regulatory_basis=_regulatory(),
            catalog_metadata={"currency": "BRL", "currency_source": "catalog_metadata.json"},
            profit_layer_amount=_profit_layer(),
        )


def test_p21b_regulatory_basis_requires_exact_positive_denominator_and_floor() -> None:
    with pytest.raises(ValueError, match="exact positive Fraction"):
        RegulatoryBdiBasis(F(0), "BRL", "scope-v1", F(1, 20), "source", "ref")
    with pytest.raises(ValueError, match="exact nonnegative Fraction"):
        RegulatoryBdiBasis(F(30), "BRL", "scope-v1", -F(1, 20), "source", "ref")


def _gates(**kwargs):
    return evaluate_pricing_gates(
        _diagnostics(),
        regulatory_basis=_regulatory(),
        catalog_metadata={"currency": "BRL", "currency_source": "catalog_metadata.json"},
        **kwargs,
    )


def test_n9_minimum_applies_to_the_profit_layer_not_to_the_gross_result() -> None:
    """(P - C)/P also contains overhead and taxes; the minimum is a criterion on
    the profit layer's share of the price, and it is the only criterion."""
    diagnostics = _diagnostics()
    profit = _profit_layer()
    share = profit / diagnostics.operational_price
    assert share == F(57, 424) < diagnostics.realized_margin == F(21, 106)

    # A minimum the gross result (P - C)/P would meet is not met by the profit layer.
    layered = _gates(minimum_profit_margin=diagnostics.realized_margin, profit_layer_amount=profit)
    assert layered.profit_layer_share == share
    assert layered.realized_margin == diagnostics.realized_margin  # reported, never the criterion
    assert layered.profitability_status == "FAIL"
    assert layered.reasons == ("profit-layer share of the price is below the explicit minimum",)

    passing = _gates(minimum_profit_margin=share, profit_layer_amount=profit)
    assert passing.profitability_status == "PASS"


def test_n9_the_profit_layer_is_mandatory() -> None:
    """No flat path: the gate cannot be evaluated without the profit layer."""
    with pytest.raises(TypeError, match="profit_layer_amount"):
        _gates(minimum_profit_margin=F(0))
    with pytest.raises(ValueError, match="profit layer"):
        _gates(profit_layer_amount=None)


def test_n9_profit_layer_cannot_exceed_the_gross_result_or_be_inexact() -> None:
    gross = _diagnostics().profit_amount
    for bad in (gross + 1, F(-1), 1.0):
        with pytest.raises(ValueError, match="profit layer"):
            _gates(profit_layer_amount=bad)
