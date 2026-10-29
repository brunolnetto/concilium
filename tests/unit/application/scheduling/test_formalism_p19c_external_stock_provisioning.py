"""P19-C: fail-closed external stock provisioning and exact acquisition ownership."""
from __future__ import annotations

from dataclasses import replace
from fractions import Fraction as F
from typing import Literal

import pytest

from concilium.application.scheduling.contractual_cost_ledger import ExclusiveCostLedger
from concilium.application.scheduling.financial_cost_reconciliation import (
    reconcile_financial_sources,
)
from concilium.application.scheduling.physical_consumption_journal import (
    WeeklyConsumptionEvidence,
    book_weekly_physical_consumption,
)
from concilium.application.scheduling.physical_consumption_rates import (
    ConsumptionBasis,
    PhysicalConsumptionRate,
    PhysicallyPricedGood,
)
from concilium.application.scheduling.physical_stock_holding import (
    HoldingTariff,
    post_exact_weekly_holding,
)
from concilium.application.scheduling.physical_stock_ledger import (
    StockArrival,
    StockGood,
)
from concilium.application.scheduling.physical_stock_provisioning import (
    ExternalStockPurchase,
    book_external_stock_provisioning,
)

WEEKS = ("2026-W01", "2026-W02")
CURRENCY_SOURCE = "catalog_metadata.json"


def _base(
    goods: dict[str, StockGood] | None = None,
    consumption_unit_price: F = F(0),
):
    stock_goods = goods or {"ORE": StockGood("ORE", "kg", F(0))}
    internal_rate = PhysicallyPricedGood(
        PhysicalConsumptionRate(
            "ORE", F(1), "kg", ConsumptionBasis.PER_DELIVERED_UNIT, "unid",
        ),
        consumption_unit_price,
        "kg",
        price_source="internal-generation-policy",
        price_reference_date="2026-10-29",
    )
    consumption = book_weekly_physical_consumption(
        ExclusiveCostLedger(()),
        {"ORE": (internal_rate, "MAT")},
        (WeeklyConsumptionEvidence(
            "demand-1", "A", "ORE", "2026-W01",
            ConsumptionBasis.PER_DELIVERED_UNIT, "PLANNED_CLOSED_SCOPE",
            delivered_quantity=F(10), delivered_unit="unid",
        ),),
    )
    internal_generation = StockArrival(
        "internal-generation-1", "ORE", "2026-W01", F(8), "kg",
        "INTERNAL_GENERATION",
    )
    return stock_goods, consumption, (internal_generation,)


def _purchase(
    *,
    source_id: str = "quote-17",
    quantity: F = F(3),
    ordered_week: str = "2026-W01",
    arrival_week: str = "2026-W01",
    physical_unit: str = "kg",
    unit_price: F | None = F(5),
    price_unit: str | None = "kg",
    price_source: str | None = "supplier-quote-Q17",
    price_reference_date: str | None = "2026-10-29",
    currency: str | None = "BRL",
    category: Literal["MAT", "COMB"] = "MAT",
) -> ExternalStockPurchase:
    return ExternalStockPurchase(
        source_id=source_id,
        good_id="ORE",
        ordered_week=ordered_week,
        arrival_week=arrival_week,
        quantity=quantity,
        physical_unit=physical_unit,
        unit_price=unit_price,
        price_unit=price_unit,
        price_source=price_source,
        price_reference_date=price_reference_date,
        currency=currency,
        category=category,
    )


def _book(
    *,
    goods: dict[str, StockGood] | None = None,
    purchase: ExternalStockPurchase | None = None,
    other_arrivals: tuple[StockArrival, ...] | None = None,
):
    stock_goods, base, arrivals = _base(goods)
    return stock_goods, book_external_stock_provisioning(
        base,
        stock_goods,
        WEEKS,
        (purchase or _purchase(),),
        catalog_metadata={"currency": "BRL", "currency_source": CURRENCY_SOURCE},
        other_arrivals=arrivals if other_arrivals is None else other_arrivals,
    )


def test_external_receipt_and_priced_acquisition_are_separate_and_reconcile() -> None:
    goods, result = _book()
    assert result.stock.feasible
    assert result.stock.rows[0].physical_demand == F(10)
    assert result.stock.rows[0].external_receipts == F(3)
    assert result.stock.rows[0].internal_generation == F(8)
    assert result.stock.rows[0].fulfilled == F(10)
    assert result.stock.rows[0].closing == F(1)
    assert result.stock.rows[1].closing == F(1)
    assert result.external_cost == F(15)
    assert result.currency == "BRL"
    assert result.currency_source == CURRENCY_SOURCE
    assert result.authority == "EXTERNAL_STOCK_PROVISIONING_PREVIEW_NOT_PROJECT_GO"
    assert len(result.purchase_evidence) == 1
    assert result.purchase_evidence[0].price_source == "supplier-quote-Q17"
    assert result.purchase_evidence[0].measure.exact_cost == F(15)
    assert result.arrivals[-1].source_id == "EXTERNAL_RECEIPT:quote-17"

    holding = post_exact_weekly_holding(
        result.ledger,
        result.stock,
        goods,
        {"ORE": HoldingTariff("ORE", F(2), "kg")},
    )
    reconciled = reconcile_financial_sources(
        ExclusiveCostLedger(()), result.base_consumption, holding,
        stock_provisioning=result,
    )
    assert tuple(line.source_id for line in result.base_consumption.evidence) == ("demand-1",)
    assert reconciled.ledger.consumable_v == F(15)
    assert reconciled.indirect == F(4)
    assert reconciled.total == F(19)
    assert reconciled.holding_evidence_present
    assert reconciled.authority.endswith("NOT_PROJECT_GO")


def test_unit_conversion_is_exact_for_external_purchase() -> None:
    goods, base, arrivals = _base()
    purchase = _purchase(
        quantity=F(3, 1000), physical_unit="t", unit_price=F(5), price_unit="kg",
    )
    result = book_external_stock_provisioning(
        base,
        goods,
        WEEKS,
        (purchase,),
        catalog_metadata={"currency": "BRL", "currency_source": CURRENCY_SOURCE},
        other_arrivals=arrivals,
    )
    assert result.purchase_evidence[0].measure.physical_quantity == F(3, 1000)
    assert result.purchase_evidence[0].measure.priced_quantity == F(3)
    assert result.external_cost == F(15)
    assert result.stock.rows[0].external_receipts == F(3)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("unit_price", None, "explicit exact nonnegative unit price"),
        ("price_unit", None, "price unit"),
        ("price_source", None, "price source"),
        ("price_reference_date", None, "price reference date"),
        ("currency", None, "currency"),
        ("category", None, "MAT or COMB"),
    ],
)
def test_missing_price_unit_source_date_or_currency_fails_closed(
    field: str, value: object, message: str,
) -> None:
    values: dict[str, object] = {
        "source_id": "quote-17",
        "good_id": "ORE",
        "ordered_week": "2026-W01",
        "arrival_week": "2026-W01",
        "quantity": F(1),
        "physical_unit": "kg",
        "unit_price": F(5),
        "price_unit": "kg",
        "price_source": "supplier-quote-Q17",
        "price_reference_date": "2026-10-29",
        "currency": "BRL",
    }
    values[field] = value
    with pytest.raises(ValueError, match=message):
        ExternalStockPurchase(**values)  # type: ignore[arg-type]


def test_currency_codes_must_be_ascii_three_letter_codes() -> None:
    with pytest.raises(ValueError, match="uppercase 3-letter code"):
        _purchase(currency="ÅBC")
    goods, base, arrivals = _base()
    with pytest.raises(ValueError, match="financial currency must be an explicit uppercase 3-letter code"):
        book_external_stock_provisioning(
            base, goods, WEEKS, (_purchase(),),
            catalog_metadata={"currency": "ÅBC", "currency_source": CURRENCY_SOURCE},
            other_arrivals=arrivals,
        )


def test_unpriced_external_arrival_cannot_bypass_purchase_evidence() -> None:
    goods, base, arrivals = _base()
    unpriced = StockArrival(
        "unpriced-delivery", "ORE", "2026-W01", F(2), "kg",
        "EXTERNAL_DELIVERY", "2026-W01",
    )
    with pytest.raises(ValueError, match="external delivery requires a typed and priced"):
        book_external_stock_provisioning(
            base, goods, WEEKS, (_purchase(),),
            catalog_metadata={"currency": "BRL", "currency_source": CURRENCY_SOURCE},
            other_arrivals=arrivals + (unpriced,),
        )


def test_missing_catalog_currency_provenance_and_currency_mismatch_fail() -> None:
    goods, base, arrivals = _base()
    with pytest.raises(ValueError, match="catalog currency must be an uppercase ASCII"):
        book_external_stock_provisioning(
            base, goods, WEEKS, (_purchase(),),
            catalog_metadata={"currency_source": CURRENCY_SOURCE},
            other_arrivals=arrivals,
        )
    with pytest.raises(ValueError, match="catalog_metadata.json"):
        book_external_stock_provisioning(
            base, goods, WEEKS, (_purchase(),),
            catalog_metadata={"currency": "BRL", "currency_source": "runtime-input"},
            other_arrivals=arrivals,
        )
    with pytest.raises(ValueError, match="differs from verified financial currency"):
        book_external_stock_provisioning(
            base, goods, WEEKS, (_purchase(currency="USD"),),
            catalog_metadata={"currency": "BRL", "currency_source": CURRENCY_SOURCE},
            other_arrivals=arrivals,
        )


def test_missing_price_date_or_incompatible_price_unit_never_becomes_zero_cost() -> None:
    with pytest.raises(ValueError, match="canonical YYYY-MM-DD"):
        _purchase(price_reference_date="29/10/2026")
    with pytest.raises(ValueError, match="incompatible physical dimensions"):
        _purchase(price_unit="l")


def test_late_delivery_violating_stock_good_lead_time_is_rejected() -> None:
    goods = {"ORE": StockGood("ORE", "kg", F(0), lead_time_weeks=1)}
    with pytest.raises(ValueError, match="violates declared lead time"):
        _book(
            goods=goods,
            purchase=_purchase(ordered_week="2026-W01", arrival_week="2026-W01"),
        )


def test_external_provisioning_that_still_leaves_stockout_fails_closed() -> None:
    with pytest.raises(ValueError, match="unresolved physical stockout"):
        _book(purchase=_purchase(quantity=F(1)))


def test_duplicate_purchase_identity_cannot_double_book_arrival_or_cost() -> None:
    goods, base, arrivals = _base()
    repeated = _purchase()
    with pytest.raises(ValueError, match="duplicate external purchase source identity"):
        book_external_stock_provisioning(
            base,
            goods,
            WEEKS,
            (repeated, repeated),
            catalog_metadata={"currency": "BRL", "currency_source": CURRENCY_SOURCE},
            other_arrivals=arrivals,
        )
    collision = StockArrival(
        "EXTERNAL_RECEIPT:quote-17", "ORE", "2026-W01", F(1), "kg",
        "INTERNAL_GENERATION",
    )
    with pytest.raises(ValueError, match="duplicate physical stock source"):
        book_external_stock_provisioning(
            base,
            goods,
            WEEKS,
            (repeated,),
            catalog_metadata={"currency": "BRL", "currency_source": CURRENCY_SOURCE},
            other_arrivals=arrivals + (collision,),
        )


def test_external_provisioning_does_not_double_charge_priced_consumption() -> None:
    goods, base, arrivals = _base(consumption_unit_price=F(4))
    with pytest.raises(ValueError, match="would double count"):
        book_external_stock_provisioning(
            base,
            goods,
            WEEKS,
            (_purchase(),),
            catalog_metadata={"currency": "BRL", "currency_source": CURRENCY_SOURCE},
            other_arrivals=arrivals,
        )

def test_p20_rejects_forged_external_cost_or_stock_projection() -> None:
    _, result = _book()
    original = result.ledger.postings[-1]
    forged_ledger = ExclusiveCostLedger(
        result.ledger.postings[:-1] + (replace(original, amount=F(14)),)
    )
    forged_cost = replace(result, ledger=forged_ledger)
    with pytest.raises(ValueError, match="P19 external stock acquisition: missing, forged"):
        reconcile_financial_sources(
            ExclusiveCostLedger(()),
            result.base_consumption,
            stock_provisioning=forged_cost,
        )

    forged_stock = replace(result.stock, evidence_ids=("forged-source",))
    forged_projection = replace(result, stock=forged_stock)
    with pytest.raises(ValueError, match="stock projection does not reconcile"):
        reconcile_financial_sources(
            ExclusiveCostLedger(()),
            result.base_consumption,
            stock_provisioning=forged_projection,
        )


def test_explicit_zero_price_is_not_the_same_as_missing_price() -> None:
    goods, base, arrivals = _base()
    free_but_evidenced = _purchase(unit_price=F(0), price_source="written-zero-price")
    result = book_external_stock_provisioning(
        base,
        goods,
        WEEKS,
        (free_but_evidenced,),
        catalog_metadata={"currency": "BRL", "currency_source": CURRENCY_SOURCE},
        other_arrivals=arrivals,
    )
    assert result.external_cost == 0
    assert result.purchase_evidence[0].price_source == "written-zero-price"
    assert result.ledger.consumable_v == 0
    assert tuple(line.source_id for line in result.base_consumption.evidence) == ("demand-1",)
