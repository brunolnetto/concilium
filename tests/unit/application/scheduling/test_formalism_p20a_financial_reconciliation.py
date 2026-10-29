"""P20-A: independent arithmetic and adversarial accounting witnesses."""
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
    WeeklyConsumptionEvidence,
    book_weekly_physical_consumption,
)
from concilium.application.scheduling.physical_consumption_rates import (
    ConsumptionBasis,
    PhysicalConsumptionRate,
    PhysicallyPricedGood,
    PhysicalPurchaseMeasure,
)
from concilium.application.scheduling.physical_stock_holding import (
    HoldingJournal,
    HoldingTariff,
    HoldingWeekCharge,
    post_exact_weekly_holding,
)
from concilium.application.scheduling.physical_stock_ledger import (
    StockGood,
    project_exact_weekly_stock,
)


def _case() -> tuple[
    ExclusiveCostLedger, PhysicalConsumptionJournalResult, HoldingJournal
]:
    # Hand-calculated, with no production cost calculator:
    # 10 active + 4 idle + 3 mobilization + 2.50 MAT + 6 holding = 25.50.
    pool = ExclusiveCostLedger((
        CostPosting(("POOL", "R", "ACTIVE"), PostingNature.ACTIVE,
                    "EQ", F(10), "R", "2026-W01"),
        CostPosting(("POOL", "R", "IDLE"), PostingNature.IDLE,
                    "EQ", F(4), "R", "2026-W02"),
        CostPosting(("POOL", "R", "MOB"), PostingNature.MOBILIZATION,
                    "IND", F(3), "R", "2026-W01"),
    ))
    measure = PhysicalPurchaseMeasure("ORE", F(1), "kg", F(1), "kg", F(5, 2))
    physical = AcquisitionEvidenceLine(
        "c1", "PLANNED_CLOSED_SCOPE", "A", "2026-W01", measure, "MAT"
    )
    acquired = CostPosting(
        ("CONSUMABLE", "c1"), PostingNature.ACQUISITION,
        "MAT", F(5, 2), "ORE", "2026-W01",
    )
    consumption = PhysicalConsumptionJournalResult(
        ExclusiveCostLedger(pool.postings + (acquired,)), (physical,),
    )
    charge = HoldingWeekCharge("ORE", "2026-W02", F(2), F(2), "kg", F(6))
    posted = CostPosting(
        ("STOCK_HOLDING", "ORE", "2026-W02"), PostingNature.HOLDING,
        "IND", F(6), "PHYSICAL_STOCK:ORE", "2026-W02",
    )
    holding = HoldingJournal(
        ExclusiveCostLedger(consumption.journal.postings + (posted,)), (charge,),
    )
    return pool, consumption, holding


def test_exact_reconciliation_by_week_and_category_is_hand_calculated() -> None:
    pool, consumption, holding = _case()
    result = reconcile_financial_sources(pool, consumption, holding)
    assert result.holding_evidence_present
    assert result.ledger.contractual_k == F(14)
    assert result.ledger.consumable_v == F(5, 2)
    assert result.direct == F(33, 2)
    assert result.indirect == F(9)
    assert result.total == F(51, 2)
    assert [(w.week, w.contractual_k, w.consumable_v, w.indirect, w.total)
            for w in result.weeks] == [
        ("2026-W01", F(10), F(5, 2), F(3), F(31, 2)),
        ("2026-W02", F(4), F(0), F(6), F(10)),
    ]
    assert result.authority.endswith("NOT_PROJECT_GO")


def test_p20b_event_trace_and_weekly_categories_conserve_the_project_ledger() -> None:
    pool, consumption, holding = _case()
    result = reconcile_financial_sources(pool, consumption, holding)

    assert sum((event.amount for event in result.event_attribution), F(0)) == result.total
    assert sum((balance.amount for balance in result.category_balances), F(0)) == result.total
    assert [(row.week, row.category, row.amount) for row in result.category_balances] == [
        ("2026-W01", "EQ", F(10)),
        ("2026-W01", "IND", F(3)),
        ("2026-W01", "MAT", F(5, 2)),
        ("2026-W02", "EQ", F(4)),
        ("2026-W02", "IND", F(6)),
    ]


def test_p20b_activity_view_only_attributes_explicit_p18_consumables() -> None:
    pool, consumption, holding = _case()
    result = reconcile_financial_sources(pool, consumption, holding)

    # The source evidence explicitly binds this acquisition to activity A.
    assert len(result.activity_attributable_consumables) == 1
    attributed = result.activity_attributable_consumables[0]
    assert (attributed.activity_id, attributed.week, attributed.category, attributed.amount) == (
        "A", "2026-W01", "MAT", F(5, 2),
    )
    assert all(
        event.activity_id is None
        for event in result.event_attribution
        if event.nature in (
            PostingNature.ACTIVE, PostingNature.IDLE,
            PostingNature.MOBILIZATION, PostingNature.DEMOBILIZATION,
            PostingNature.HOLDING,
        )
    )
    assert all(
        event.owner_scope == "INSTANCE"
        for event in result.event_attribution
        if event.nature in (
            PostingNature.ACTIVE, PostingNature.IDLE,
            PostingNature.MOBILIZATION, PostingNature.DEMOBILIZATION,
        )
    )
    assert sum((row.amount for row in result.activity_attributable_consumables), F(0)) == F(5, 2)
    assert result.total == F(51, 2)


def test_p20b_category_and_activity_views_do_not_apply_bdi_or_rebook_costs() -> None:
    pool, consumption, holding = _case()
    result = reconcile_financial_sources(pool, consumption, holding)

    assert result.direct == F(33, 2)
    assert result.indirect == F(9)
    assert result.total == F(51, 2)
    assert all(type(row.amount) is F for row in result.category_balances)
    assert all(type(row.amount) is F for row in result.activity_attributable_consumables)
    assert len(result.event_attribution) == len(result.ledger.postings)


def test_no_holding_has_explicitly_incomplete_evidence_not_a_fake_zero() -> None:
    pool, consumption, _ = _case()
    result = reconcile_financial_sources(pool, consumption)
    assert not result.holding_evidence_present
    assert result.total == F(39, 2)


def test_source_delta_rejects_missing_and_forged_variable_purchase() -> None:
    pool, consumption, _ = _case()
    missing = replace(consumption, journal=pool)
    # The independent acquisition evidence guard rejects the missing posting
    # before the later set-difference check; both correctly fail closed.
    with pytest.raises(ValueError, match="differs from measured physical cost"):
        reconcile_financial_sources(pool, missing)
    original = consumption.journal.postings
    invented = CostPosting(
        ("CONSUMABLE", "c2"), PostingNature.ACQUISITION,
        "MAT", F(1), "ORE", "2026-W02",
    )
    forged = replace(consumption, journal=ExclusiveCostLedger(original + (invented,)))
    with pytest.raises(ValueError, match="missing, forged"):
        reconcile_financial_sources(pool, forged)


def test_equal_totals_do_not_hide_shifted_source_or_category() -> None:
    pool, consumption, _ = _case()
    posting = consumption.journal.postings[-1]
    # Same total and nature, but the week of acquisition was falsified.
    shifted = replace(posting, week="2026-W02")
    forged = replace(
        consumption,
        journal=ExclusiveCostLedger(pool.postings + (shifted,)),
    )
    with pytest.raises(ValueError, match="differs from measured"):
        reconcile_financial_sources(pool, forged)

    # A valid cost number cannot be reclassified as contractual wages.
    converted = CostPosting(
        ("CONSUMABLE", "c1"), PostingNature.ACTIVE,
        "MO", F(5, 2), "CREW", "2026-W01",
    )
    forged2 = replace(
        consumption, journal=ExclusiveCostLedger(pool.postings + (converted,))
    )
    with pytest.raises(ValueError, match="differs from measured"):
        reconcile_financial_sources(pool, forged2)


def test_prior_pool_event_cannot_be_mutated_even_with_equal_total() -> None:
    pool, consumption, _ = _case()
    replaced = replace(pool.postings[0], source="OTHER")
    forged = replace(
        consumption,
        journal=ExclusiveCostLedger((replaced,) + consumption.journal.postings[1:]),
    )
    with pytest.raises(ValueError, match="prior financial posting"):
        reconcile_financial_sources(pool, forged)


def test_holding_duplicate_missing_and_mutated_charge_fail_closed() -> None:
    pool, consumption, holding = _case()
    missing = replace(holding, ledger=consumption.journal)
    with pytest.raises(ValueError, match="P19 holding.*missing, forged"):
        reconcile_financial_sources(pool, consumption, missing)
    posting = holding.ledger.postings[-1]
    fraud = replace(
        holding, ledger=ExclusiveCostLedger(
            holding.ledger.postings[:-1] + (replace(posting, amount=F(5)),)
        )
    )
    with pytest.raises(ValueError, match="P19 holding.*missing, forged"):
        reconcile_financial_sources(pool, consumption, fraud)
    with pytest.raises(ValueError, match="duplicate stock holding evidence"):
        reconcile_financial_sources(
            pool, consumption, replace(holding, charges=holding.charges * 2)
        )


def test_zero_physical_purchase_does_not_create_a_monetary_event() -> None:
    pool, consumption, _ = _case()
    free = AcquisitionEvidenceLine(
        "zero", "PLANNED_CLOSED_SCOPE", "A", "2026-W02",
        PhysicalPurchaseMeasure("ORE", F(0), "kg", F(0), "kg", F(0)), "MAT",
    )
    with_zero = replace(consumption, evidence=consumption.evidence + (free,))
    assert reconcile_financial_sources(pool, with_zero).total == F(39, 2)
    false_cost = replace(free, measure=replace(free.measure, exact_cost=F(1)))
    with pytest.raises(ValueError, match="zero physical purchase"):
        reconcile_financial_sources(
            pool, replace(consumption, evidence=consumption.evidence + (false_cost,))
        )


def test_real_p18_and_p19_adapters_reconcile_without_repricing() -> None:
    # Analytical source: active 4, 1 m³ * 1 kg/m³ * 2/kg = 2,
    # closing (4 - 1) kg * 0.5/kg/week = 1.5 => 7.5.
    pool = ExclusiveCostLedger((
        CostPosting(("POOL", "A"), PostingNature.ACTIVE,
                    "MO", F(4), "CREW", "2026-W01"),
    ))
    good = PhysicallyPricedGood(
        PhysicalConsumptionRate("ORE", F(1), "kg",
                                ConsumptionBasis.PER_DELIVERED_UNIT, "m³"),
        F(2), "kg",
    )
    actual = book_weekly_physical_consumption(
        pool, {"ORE": (good, "MAT")},
        (WeeklyConsumptionEvidence(
            "physical-1", "A", "ORE", "2026-W01",
            ConsumptionBasis.PER_DELIVERED_UNIT, "PLANNED_CLOSED_SCOPE",
            delivered_quantity=F(1), delivered_unit="m³",
        ),),
    )
    goods = {"ORE": StockGood("ORE", "kg", F(4))}
    stock = project_exact_weekly_stock(goods, ("2026-W01",), actual.evidence)
    holding = post_exact_weekly_holding(
        actual.journal, stock, goods,
        {"ORE": HoldingTariff("ORE", F(1, 2), "kg")},
    )
    balanced = reconcile_financial_sources(pool, actual, holding)
    assert balanced.ledger.contractual_k == F(4)
    assert balanced.ledger.consumable_v == F(2)
    assert balanced.ledger.indirect == F(3, 2)
    assert balanced.total == F(15, 2)


def test_mixed_planned_and_observed_acquisition_is_not_booked_twice() -> None:
    pool, consumption, _ = _case()
    evidence = consumption.evidence[0]
    observed = replace(evidence, source_id="observed-2", kind="OBSERVED_OPERATION")
    extra = CostPosting(
        ("CONSUMABLE", "observed-2"), PostingNature.ACQUISITION,
        "MAT", F(5, 2), "ORE", "2026-W01",
    )
    fraud = replace(
        consumption, evidence=consumption.evidence + (observed,),
        journal=ExclusiveCostLedger(consumption.journal.postings + (extra,)),
    )
    with pytest.raises(ValueError, match="planned and observed"):
        reconcile_financial_sources(pool, fraud)


def test_duplicate_zero_quantity_source_and_empty_week_are_rejected() -> None:
    pool, consumption, _ = _case()
    zero = AcquisitionEvidenceLine(
        "z", "PLANNED_CLOSED_SCOPE", "A", "2026-W02",
        PhysicalPurchaseMeasure("ORE", F(0), "kg", F(0), "kg", F(0)), "MAT",
    )
    with pytest.raises(ValueError, match="duplicate acquisition evidence"):
        reconcile_financial_sources(
            pool, replace(consumption, evidence=consumption.evidence + (zero, zero))
        )
    bad_pool = ExclusiveCostLedger((
        CostPosting(("UNKNOWN_WEEK",), PostingNature.MOBILIZATION,
                    "IND", F(1), "SITE", None),
    ))
    empty = PhysicalConsumptionJournalResult(bad_pool, ())
    with pytest.raises(ValueError, match="weekly provenance"):
        reconcile_financial_sources(bad_pool, empty)


def test_zero_activity_has_exact_zero_balances_without_fabricated_costs() -> None:
    pool = ExclusiveCostLedger(())
    consumption = PhysicalConsumptionJournalResult(pool, ())
    result = reconcile_financial_sources(pool, consumption)
    assert not result.weeks
    assert result.direct == result.indirect == result.total == F(0)
    assert not result.holding_evidence_present


def test_category_forgery_preserving_total_is_rejected_against_p18() -> None:
    pool, consumption, _ = _case()
    acquisition = consumption.journal.postings[-1]
    falsified = replace(acquisition, category="COMB")
    fake = replace(
        consumption,
        journal=ExclusiveCostLedger(pool.postings + (falsified,)),
    )
    assert fake.journal.total == consumption.journal.total
    with pytest.raises(ValueError, match="differs from measured physical cost"):
        reconcile_financial_sources(pool, fake)


def test_unknown_legacy_purchase_category_is_not_a_financial_certificate() -> None:
    pool, consumption, _ = _case()
    legacy = replace(consumption.evidence[0], category=None)
    with pytest.raises(ValueError, match="lacks declared MAT/COMB category"):
        reconcile_financial_sources(
            pool, replace(consumption, evidence=(legacy,))
        )
