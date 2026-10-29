"""P20-C: exact, category-specific BDI applied once to the authoritative ledger."""
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
from concilium.application.scheduling.physical_consumption_journal import (
    AcquisitionEvidenceLine,
    PhysicalConsumptionJournalResult,
)
from concilium.application.scheduling.physical_consumption_rates import (
    PhysicalPurchaseMeasure,
)


def _result():
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
        "MO": F(1, 10),
        "EQ": F(1, 5),
        "MAT": F(1, 2),
        "COMB": F(3, 10),
        "IND": F(1, 4),
    }


def test_p20c_bdi_is_applied_once_per_category_without_rounding() -> None:
    result = _result()
    priced = result.project_price_once_bdi(_rates())

    assert result.total == F(51, 2)
    assert priced.cost_before_bdi == F(51, 2)
    assert priced.bdi_amount == F(63, 10)
    assert priced.price_once_bdi == F(159, 5)
    by_category = {row.category: row for row in priced.categories}
    assert by_category["EQ"].cost_before_bdi == F(14)
    assert by_category["EQ"].bdi_amount == F(14, 5)
    assert by_category["MAT"].cost_before_bdi == F(5, 2)
    assert by_category["MAT"].bdi_amount == F(5, 4)
    assert by_category["IND"].cost_before_bdi == F(9)
    assert by_category["IND"].bdi_amount == F(9, 4)
    assert by_category["MO"].price_once_bdi == by_category["COMB"].price_once_bdi == F(0)
    assert sum((row.price_once_bdi for row in priced.weekly), F(0)) == priced.price_once_bdi
    assert priced.price_once_bdi == priced.cost_before_bdi + priced.bdi_amount
    assert priced.authority == "P20_C_CATEGORY_BDI_PREVIEW_NOT_PROJECT_GO"


def test_p20c_missing_extra_or_inexact_bdi_rates_fail_closed() -> None:
    result = _result()
    with pytest.raises(ValueError, match="explicit exact nonnegative BDI rates"):
        result.project_price_once_bdi({"EQ": F(1, 5)})
    with pytest.raises(ValueError, match="explicit exact nonnegative BDI rates"):
        result.project_price_once_bdi({**_rates(), "OTHER": F(0)})
    with pytest.raises(ValueError, match="explicit exact nonnegative BDI rates"):
        result.project_price_once_bdi({**_rates(), "EQ": F(-1, 5)})
    with pytest.raises(ValueError, match="explicit exact nonnegative BDI rates"):
        result.project_price_once_bdi({**_rates(), "EQ": 0.2})


def test_p20c_bdi_refuses_a_forged_event_attribution() -> None:
    result = _result()
    forged_first = replace(
        result.event_attribution[0],
        amount=result.event_attribution[0].amount + F(1),
    )
    forged = replace(
        result,
        event_attribution=(forged_first,) + result.event_attribution[1:],
    )
    with pytest.raises(ValueError, match="attribution does not match the authoritative ledger"):
        forged.project_price_once_bdi(_rates())


def test_p20c_bdi_prices_source_events_once_and_keeps_preview_authority() -> None:
    result = _result()
    priced = result.project_price_once_bdi(_rates())
    assert len(priced.weekly) == 3
    assert sum((line.cost_before_bdi for line in priced.categories), F(0)) == result.ledger.total
    assert sum((line.bdi_amount for line in priced.categories), F(0)) == priced.bdi_amount
    assert result.authority == "FINANCIAL_SOURCES_RECONCILED_PREVIEW_NOT_PROJECT_GO"
