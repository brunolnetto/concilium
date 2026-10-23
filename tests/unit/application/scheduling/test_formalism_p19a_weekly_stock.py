"""P19-A physical mass conservation, delay and stockout falsifiers."""
from fractions import Fraction as F

import pytest

from concilium.application.scheduling.contractual_cost_ledger import ExclusiveCostLedger
from concilium.application.scheduling.physical_consumption_journal import (
    WeeklyConsumptionEvidence,
    book_weekly_physical_consumption,
)
from concilium.application.scheduling.physical_consumption_rates import (
    ConsumptionBasis,
    PhysicalConsumptionRate,
    PhysicallyPricedGood,
)
from concilium.application.scheduling.physical_stock_ledger import (
    StockArrival,
    StockGood,
    project_exact_weekly_stock,
)

WEEKS = ("2026-W01", "2026-W02")


def _evidence(week: str, amount: F, source_id: str):
    price = PhysicallyPricedGood(
        PhysicalConsumptionRate(
            "SAND", F(1), "kg", ConsumptionBasis.PER_DELIVERED_UNIT, "kg"
        ),
        F(20), "kg",
    )
    result = book_weekly_physical_consumption(
        ExclusiveCostLedger(()),
        {"SAND": (price, "MAT")},
        (WeeklyConsumptionEvidence(
            source_id, "A", "SAND", week, ConsumptionBasis.PER_DELIVERED_UNIT,
            "PLANNED_CLOSED_SCOPE", delivered_quantity=amount, delivered_unit="kg",
        ),),
    )
    return result.evidence[0]


def test_weekly_stock_mass_balance_matches_physical_consumption_not_purchase_cost() -> None:
    goods = {"SAND": StockGood("SAND", "kg", F(4), lead_time_weeks=1)}
    arrivals = (
        StockArrival(
            "delivery-1", "SAND", "2026-W02", F(10), "kg",
            "EXTERNAL_DELIVERY", "2026-W01",
        ),
    )
    projection = project_exact_weekly_stock(
        goods, WEEKS,
        (_evidence("2026-W01", F(3), "use-1"),
         _evidence("2026-W02", F(8), "use-2")),
        arrivals,
    )
    assert projection.feasible
    assert projection.has_planned_demand  # never upgrades planning to observed
    first, second = projection.rows
    assert (first.opening, first.physical_demand, first.closing) == (F(4), F(3), F(1))
    assert (second.opening, second.external_receipts, second.closing) == (
        F(1), F(10), F(3)
    )
    assert projection.authority == "PHYSICAL_INVENTORY_PREVIEW_NOT_FINANCIAL_GO"
    assert projection.total_shortage == projection.total_overflow == 0


def test_shortage_does_not_fabricate_negative_stock_or_unpaid_delivery() -> None:
    ledger = project_exact_weekly_stock(
        {"SAND": StockGood("SAND", "kg", F(1))},
        ("2026-W01",),
        (_evidence("2026-W01", F(3), "excess-demand"),),
    )
    assert not ledger.feasible
    assert ledger.total_shortage == F(2)
    assert ledger.rows[0].fulfilled == F(1)
    assert ledger.rows[0].closing == 0
    assert ledger.rows[0].external_receipts == 0


def test_early_delivery_and_missing_order_are_rejected_not_backdated() -> None:
    good = {"SAND": StockGood("SAND", "kg", F(0), lead_time_weeks=1)}
    with pytest.raises(ValueError, match="lead time"):
        project_exact_weekly_stock(good, WEEKS, (), (
            StockArrival(
                "early", "SAND", "2026-W01", F(2), "kg",
                "EXTERNAL_DELIVERY", "2026-W01",
            ),
        ))
    with pytest.raises(ValueError, match="order week outside"):
        project_exact_weekly_stock(good, WEEKS, (), (
            StockArrival(
                "preorder", "SAND", "2026-W02", F(2), "kg",
                "EXTERNAL_DELIVERY", "2025-W52",
            ),
        ))


def test_storage_overflow_is_physical_loss_before_consumption() -> None:
    result = project_exact_weekly_stock(
        {"SAND": StockGood("SAND", "kg", F(5), capacity=F(6))},
        ("2026-W01",),
        (_evidence("2026-W01", F(2), "use-1"),),
        (StockArrival(
            "arrival", "SAND", "2026-W01", F(4), "kg",
            "EXTERNAL_DELIVERY", "2026-W01",
        ),),
    )
    (line,) = result.rows
    assert (line.storage_overflow, line.fulfilled, line.closing) == (F(3), F(2), F(4))
    assert line.opening + line.external_receipts == (
        line.storage_overflow + line.fulfilled + line.closing
    )


def test_internal_generation_is_not_automatically_a_physical_purchase() -> None:
    result = project_exact_weekly_stock(
        {"SAND": StockGood("SAND", "kg", F(0))},
        ("2026-W01",),
        (_evidence("2026-W01", F(2), "use-internal"),),
        (StockArrival(
            "quarry-1", "SAND", "2026-W01", F(3), "kg", "INTERNAL_GENERATION"
        ),),
    )
    line = result.rows[0]
    assert result.feasible
    assert (line.internal_generation, line.external_receipts, line.closing) == (
        F(3), F(0), F(1)
    )


def test_unit_conversion_and_duplicate_evidence_rejection() -> None:
    stock = {"SAND": StockGood("SAND", "t", F(2))}
    result = project_exact_weekly_stock(
        stock, ("2026-W01",),
        (_evidence("2026-W01", F(500), "consume-1"),),
    )
    assert result.rows[0].physical_demand == F(1, 2)
    assert result.rows[0].closing == F(3, 2)
    with pytest.raises(ValueError, match="duplicate physical stock source"):
        project_exact_weekly_stock(stock, ("2026-W01",),
                                   (_evidence("2026-W01", F(1), "duplicated"),),
                                   (StockArrival("duplicated", "SAND", "2026-W01",
                                                 F(1), "t", "INTERNAL_GENERATION"),))
    with pytest.raises(ValueError, match="incompatible physical dimensions"):
        project_exact_weekly_stock(
            stock, ("2026-W01",), (),
            (StockArrival("wrong-unit", "SAND", "2026-W01", F(1), "l",
                          "INTERNAL_GENERATION"),),
        )


def test_definitions_reject_unknown_goods_and_untrusted_numbers() -> None:
    with pytest.raises(ValueError):
        StockGood("SAND", "kg", F(-1))
    with pytest.raises(ValueError):
        StockGood("SAND", "kg", F(2), capacity=F(1))
    with pytest.raises(ValueError):
        StockGood("SAND", "kg", F(2), lead_time_weeks=-1)
    with pytest.raises(ValueError, match="unknown good"):
        project_exact_weekly_stock(
            {"SAND": StockGood("SAND", "kg", F(0))},
            ("2026-W01",),
            (_evidence("2026-W01", F(1), "demand-1"),),
            (StockArrival("wrong-good", "MISSING", "2026-W01", F(3), "kg",
                          "INTERNAL_GENERATION"),),
        )
