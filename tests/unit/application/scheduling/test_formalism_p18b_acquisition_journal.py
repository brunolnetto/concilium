"""P18-B: typed output/hour evidence is the only source of consumable V."""
from fractions import Fraction

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

F = Fraction


def _goods():
    return {
        "CONCRETE": (
            PhysicallyPricedGood(
                PhysicalConsumptionRate("CONCRETE", F(1, 2), "t",
                                        ConsumptionBasis.PER_DELIVERED_UNIT, "m³"),
                F(100), "t",
            ), "MAT",
        ),
        "DIESEL": (
            PhysicallyPricedGood(
                PhysicalConsumptionRate("DIESEL", F(3), "l",
                                        ConsumptionBasis.PER_OPERATING_HOUR),
                F(1, 5), "l",
            ), "COMB",
        ),
    }


def _q(evidence_id: str, q: Fraction, week: str = "2026-W20"):
    return WeeklyConsumptionEvidence(
        evidence_id, "A", "CONCRETE", week,
        ConsumptionBasis.PER_DELIVERED_UNIT, "PLANNED_CLOSED_SCOPE",
        delivered_quantity=q, delivered_unit="m³",
    )


def _fuel(evidence_id: str, hours: Fraction):
    return WeeklyConsumptionEvidence(
        evidence_id, "A", "DIESEL", "2026-W20",
        ConsumptionBasis.PER_OPERATING_HOUR, "OBSERVED_OPERATION",
        operating_hours=hours,
    )


def test_two_goods_partial_week_and_exact_acquisition_without_k_inflation() -> None:
    ledger = ExclusiveCostLedger(())
    result = book_weekly_physical_consumption(ledger, _goods(), (
        _q("mat-full", F(400), "2026-W19"),
        _q("mat-final", F(100), "2026-W20"),
        _fuel("diesel-real", F(4)),
    ))
    # 500 m³ * 0.5 t/m³ * R$100/t + 4h * 3L/h * R$0.2/L.
    assert result.variable_cost == F(25000) + F(12, 5)
    assert result.journal.contractual_k == 0
    assert result.journal.indirect == 0
    assert result.journal.total == result.variable_cost
    assert len(result.evidence) == 3
    assert {s.kind for s in result.evidence} == {
        "OBSERVED_OPERATION", "PLANNED_CLOSED_SCOPE",
    }
    assert len(result.journal.postings) == 3


def test_no_delivered_scope_means_no_purchase_for_output_based_good() -> None:
    result = book_weekly_physical_consumption(
        ExclusiveCostLedger(()), _goods(), (_q("none", F(0)),)
    )
    assert result.variable_cost == 0
    assert len(result.journal.postings) == 0
    assert len(result.evidence) == 1
    assert result.evidence[0].measure.physical_quantity == 0


def test_duplicate_evidence_cannot_inflate_variable_cost() -> None:
    with pytest.raises(ValueError, match="duplicate physical evidence"):
        book_weekly_physical_consumption(
            ExclusiveCostLedger(()), _goods(), (_q("same", F(1)), _q("same", F(1)))
        )


def test_wrong_basis_missing_price_and_monetary_proxy_are_rejected() -> None:
    bad_hour = WeeklyConsumptionEvidence(
        "h1", "A", "DIESEL", "2026-W20",
        ConsumptionBasis.PER_OPERATING_HOUR, "PLANNED_CLOSED_SCOPE",
        operating_hours=F(4),
    )
    with pytest.raises(ValueError, match="missing priced"):
        book_weekly_physical_consumption(ExclusiveCostLedger(()), {}, (bad_hour,))
    wrong_q = WeeklyConsumptionEvidence(
        "q1", "A", "DIESEL", "2026-W20",
        ConsumptionBasis.PER_DELIVERED_UNIT, "PLANNED_CLOSED_SCOPE",
        delivered_quantity=F(5), delivered_unit="m³",
    )
    with pytest.raises(ValueError, match="incompatible"):
        book_weekly_physical_consumption(ExclusiveCostLedger(()), _goods(), (wrong_q,))
    with pytest.raises(ValueError, match="required"):
        WeeklyConsumptionEvidence(
            "proxy", "A", "DIESEL", "2026-W20",
            ConsumptionBasis.PER_OPERATING_HOUR, "OBSERVED_OPERATION",
        )


def test_mass_price_conversion_uses_purchased_unit_not_raw_output_unit() -> None:
    priced = PhysicallyPricedGood(
        PhysicalConsumptionRate("AGGREGATE", F(500), "kg",
                                ConsumptionBasis.PER_DELIVERED_UNIT, "m³"),
        F(200), "t",
    )
    result = book_weekly_physical_consumption(
        ExclusiveCostLedger(()), {"AGGREGATE": (priced, "MAT")}, (
            WeeklyConsumptionEvidence(
                "aggregate-1", "A", "AGGREGATE", "W01",
                ConsumptionBasis.PER_DELIVERED_UNIT, "PLANNED_CLOSED_SCOPE",
                delivered_quantity=F(4), delivered_unit="m³",
            ),
        ),
    )
    assert result.evidence[0].measure.physical_quantity == F(2000)
    assert result.evidence[0].measure.priced_quantity == F(2)
    assert result.variable_cost == F(400)
    assert result.journal.postings[0].amount == F(400)


def test_no_waste_identity_closes_activity_cost_and_aggregate_good_ledger_exactly() -> None:
    """Two activities share one good; activity-specific rates still conserve V exactly."""
    goods = {
        ("A", "AGGREGATE"): (
            PhysicallyPricedGood(
                PhysicalConsumptionRate(
                    "AGGREGATE", F(500), "kg",
                    ConsumptionBasis.PER_DELIVERED_UNIT, "m³",
                ),
                F(200), "t",
            ),
            "MAT",
        ),
        ("B", "AGGREGATE"): (
            PhysicallyPricedGood(
                PhysicalConsumptionRate(
                    "AGGREGATE", F(250), "kg",
                    ConsumptionBasis.PER_DELIVERED_UNIT, "m²",
                ),
                F(200), "t",
            ),
            "MAT",
        ),
    }
    evidence = (
        WeeklyConsumptionEvidence(
            "A-Q", "A", "AGGREGATE", "2026-W20",
            ConsumptionBasis.PER_DELIVERED_UNIT, "PLANNED_CLOSED_SCOPE",
            delivered_quantity=F(4), delivered_unit="m³",
        ),
        WeeklyConsumptionEvidence(
            "B-Q", "B", "AGGREGATE", "2026-W20",
            ConsumptionBasis.PER_DELIVERED_UNIT, "PLANNED_CLOSED_SCOPE",
            delivered_quantity=F(8), delivered_unit="m²",
        ),
    )

    result = book_weekly_physical_consumption(ExclusiveCostLedger(()), goods, evidence)

    # No-waste physical balance: 4*500 kg + 8*250 kg = 4,000 kg = 4 t.
    total_kg = sum((row.measure.physical_quantity for row in result.evidence), F(0))
    total_t = sum((row.measure.priced_quantity for row in result.evidence), F(0))
    assert total_kg == F(4000)
    assert total_t == F(4)
    # Aggregate-good valuation equals the independent activity decomposition:
    # p_t * U_t = 200*4 = (4*100) + (8*50) = R$800.
    aggregate_good_cost = F(200) * total_t
    activity_cost = F(4) * F(100) + F(8) * F(50)
    assert aggregate_good_cost == activity_cost == F(800)
    assert result.variable_cost == aggregate_good_cost
    assert result.journal.total == F(800)
    assert result.journal.contractual_k == 0
    assert result.journal.indirect == 0
    assert len(result.journal.postings) == 2
    assert len({posting.event_id for posting in result.journal.postings}) == 2
