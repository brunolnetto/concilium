"""P19-B: no inventory holding leaks into MAT/COMB acquisition or K."""
from fractions import Fraction as F

import pytest

from concilium.application.scheduling.contractual_cost_ledger import (
    CostPosting,
    ExclusiveCostLedger,
    PostingNature,
)
from concilium.application.scheduling.physical_consumption_journal import AcquisitionEvidenceLine
from concilium.application.scheduling.physical_consumption_rates import PhysicalPurchaseMeasure
from concilium.application.scheduling.physical_stock_holding import (
    HoldingTariff,
    post_exact_weekly_holding,
)
from concilium.application.scheduling.physical_stock_ledger import (
    StockGood,
    StockProjection,
    project_exact_weekly_stock,
)


def _measured(week: str, amount: F, source: str) -> AcquisitionEvidenceLine:
    return AcquisitionEvidenceLine(
        source, "PLANNED_CLOSED_SCOPE", "ACTIVITY", week,
        PhysicalPurchaseMeasure("ORE", amount, "kg", amount, "kg", amount * F(10)),
    )


def _stock():
    goods = {"ORE": StockGood("ORE", "kg", F(5))}
    rows = project_exact_weekly_stock(
        goods, ("W01", "W02"),
        (_measured("W01", F(3), "physical-1"),
         _measured("W02", F(1), "physical-2")),
    )
    assert rows.feasible
    return goods, rows


def test_end_week_holding_is_indirect_and_leaves_variable_acquisition_unchanged() -> None:
    goods, stock = _stock()  # closing inventory: W01=2 kg, W02=1 kg
    base = ExclusiveCostLedger((
        CostPosting(
            ("CONSUMABLE", "physical-1"), PostingNature.ACQUISITION,
            "MAT", F(30), "ORE", "W01",
        ),
    ))
    result = post_exact_weekly_holding(
        base, stock, goods, {"ORE": HoldingTariff("ORE", F(5), "kg")},
    )
    assert result.holding_cost == F(15)
    assert result.ledger.consumable_v == F(30)
    assert result.ledger.contractual_k == 0
    assert result.ledger.indirect == F(15)
    assert result.ledger.total == F(45)
    assert [(r.week, r.closing_in_stock_unit, r.holding_cost) for r in result.charges] == [
        ("W01", F(2), F(10)), ("W02", F(1), F(5)),
    ]
    assert result.authority == "HOLDING_PREVIEW_NOT_PROJECT_GO"


def test_holding_rate_unit_is_physically_converted_without_rounding() -> None:
    goods = {"ORE": StockGood("ORE", "t", F(2))}
    stock = project_exact_weekly_stock(goods, ("W01",), ())
    result = post_exact_weekly_holding(
        ExclusiveCostLedger(()), stock, goods,
        {"ORE": HoldingTariff("ORE", F(1, 2), "kg")},
    )
    assert result.charges[0].billable_stock == F(2000)
    assert result.holding_cost == F(1000)
    assert result.ledger.indirect == F(1000)
    assert result.ledger.consumable_v == 0


def test_shortage_or_missing_tariff_fails_closed() -> None:
    goods = {"ORE": StockGood("ORE", "kg", F(1))}
    shortage = project_exact_weekly_stock(
        goods, ("W01",), (_measured("W01", F(3), "too-big"),),
    )
    with pytest.raises(ValueError, match="shortage"):
        post_exact_weekly_holding(
            ExclusiveCostLedger(()), shortage, goods,
            {"ORE": HoldingTariff("ORE", F(2), "kg")},
        )
    _, stock = _stock()
    with pytest.raises(ValueError, match="holding tariff"):
        post_exact_weekly_holding(ExclusiveCostLedger(()), stock, goods, {})


def test_duplicate_holding_is_rejected_by_unique_cost_ownership() -> None:
    goods, stock = _stock()
    tariffs = {"ORE": HoldingTariff("ORE", F(5), "kg")}
    first = post_exact_weekly_holding(ExclusiveCostLedger(()), stock, goods, tariffs)
    with pytest.raises(ValueError, match="duplicate financial ownership"):
        post_exact_weekly_holding(first.ledger, stock, goods, tariffs)


def test_bad_tariff_units_or_numbers_do_not_silently_price_stock() -> None:
    goods, stock = _stock()
    with pytest.raises(ValueError, match="exact nonnegative"):
        HoldingTariff("ORE", F(-1), "kg")
    with pytest.raises(ValueError, match="incompatible physical dimensions"):
        post_exact_weekly_holding(
            ExclusiveCostLedger(()), stock, goods,
            {"ORE": HoldingTariff("ORE", F(5), "l")},
        )
    with pytest.raises(ValueError, match="END_OF_WEEK"):
        HoldingTariff("ORE", F(5), "kg", basis="AVERAGE")
    duplicate = StockProjection((stock.rows[0], stock.rows[0]), (), True)
    with pytest.raises(ValueError, match="duplicate stock week"):
        post_exact_weekly_holding(
            ExclusiveCostLedger(()), duplicate, goods,
            {"ORE": HoldingTariff("ORE", F(5), "kg")},
        )
