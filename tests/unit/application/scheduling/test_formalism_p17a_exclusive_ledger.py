"""P17-A: real P16 pool chain ledger, exclusive K/V and exact ownership."""
from __future__ import annotations

from dataclasses import replace
from fractions import Fraction

import pytest

from concilium.application.scheduling.contractual_cost_ledger import (
    CostPosting,
    ExclusiveCostLedger,
    PhysicalPurchase,
    PostingNature,
    attach_physical_purchases,
    book_exact_pool,
)
from concilium.application.scheduling.resource_demand_levels import (
    normalize_weekly_resource_demand,
)
from concilium.application.scheduling.resource_level_contracts import (
    ResourceTariff,
    exact_money,
    optimize_homogeneous_pool,
)

F = Fraction


def _case():
    # Two activities share the same physical equipment during week 3.
    demand = normalize_weekly_resource_demand(
        ("2026-W01", "2026-W02", "2026-W03", "2026-W04", "2026-W05"),
        {
            "A": {"CRANE": (1, 0, 1, 0, 1)},
            "B": {"CRANE": (1, 0, 0, 0, 1)},
        },
    )
    tariff = ResourceTariff(F(5), F(10), F(20), F(10), 10)
    pool = optimize_homogeneous_pool(demand, {"CRANE": tariff})
    return pool, {"CRANE": tariff}


def test_exact_active_idle_mob_demob_categories_and_invariants() -> None:
    pool, tariffs = _case()
    result = book_exact_pool(pool, tariffs, {"CRANE": "EQ"})
    assert pool.ledgers[0].demand == (2, 0, 1, 0, 2)
    assert result.contractual_k == F(75)   # 25 active + 50 paid idle
    assert result.consumable_v == F(0)
    assert result.indirect == F(60)         # each of two chains: 20 mob + 10 demob
    assert result.direct == F(75)
    assert result.total == pool.total == F(135)
    assert {p.category for p in result.postings if p.nature in
            (PostingNature.ACTIVE, PostingNature.IDLE)} == {"EQ"}
    assert {p.category for p in result.postings if p.nature in
            (PostingNature.MOBILIZATION, PostingNature.DEMOBILIZATION)} == {"IND"}
    assert len({p.event_id for p in result.postings}) == len(result.postings)


def test_material_and_fuel_acquired_once_with_physical_quantities() -> None:
    pool, tariffs = _case()
    empty = book_exact_pool(pool, tariffs, {"CRANE": "EQ"})
    result = attach_physical_purchases(empty, (
        PhysicalPurchase("invoice-mat-1", "A", "CONCRETE", "2026-W05",
                         F(1, 2), "t", exact_money("100.10"), "MAT"),
        PhysicalPurchase("fuel-1", "B", "DIESEL", "2026-W05",
                         F(3), "L", exact_money("0.1"), "COMB"),
    ))
    assert result.contractual_k == F(75)
    assert result.consumable_v == F(1001, 20) + F(3, 10)
    assert result.indirect == F(60)
    assert result.total == F(135) + result.consumable_v
    assert sum(p.nature == PostingNature.ACQUISITION for p in result.postings) == 2


def test_zero_physical_output_has_no_variable_purchase_even_with_paid_idle() -> None:
    pool, tariffs = _case()
    ledger = book_exact_pool(pool, tariffs, {"CRANE": "EQ"})
    with_zero = attach_physical_purchases(ledger, (
        PhysicalPurchase("zero-delivery", "A", "DIESEL", "2026-W02",
                         F(0), "L", F(9), "COMB"),
    ))
    assert with_zero == ledger
    assert with_zero.sum_natures(PostingNature.IDLE) > 0
    assert with_zero.consumable_v == 0


def test_same_physical_invoice_cannot_be_posted_twice() -> None:
    pool, tariffs = _case()
    ledger = book_exact_pool(pool, tariffs, {"CRANE": "EQ"})
    purchase = PhysicalPurchase("p1", "A", "CONCRETE", "2026-W01",
                                F(3), "t", F(5), "MAT")
    with pytest.raises(ValueError, match="duplicate financial"):
        attach_physical_purchases(ledger, (purchase, purchase))


def test_two_resource_types_must_be_explicitly_classified() -> None:
    pool, tariffs = _case()
    with pytest.raises(ValueError, match="classification"):
        book_exact_pool(pool, tariffs, {})
    with pytest.raises(ValueError, match="mixed or consumable"):
        book_exact_pool(pool, tariffs, {"CRANE": "MAT"})  # type: ignore[dict-item]


def test_pool_tampering_cannot_be_laundered_into_financial_totals() -> None:
    pool, tariffs = _case()
    fraud = replace(pool.ledgers[0], standby_cost=F(49))
    with pytest.raises(ValueError, match="not reconciled"):
        book_exact_pool(replace(pool, ledgers=(fraud,)), tariffs, {"CRANE": "EQ"})
    fraud_demand = replace(pool.ledgers[0], presence=(2, 1, 2, 2, 2), standby=(0, 1, 1, 2, 0))
    with pytest.raises(ValueError, match="do not reconstruct"):
        book_exact_pool(replace(pool, ledgers=(fraud_demand,)), tariffs, {"CRANE": "EQ"})


def test_strict_exact_amount_and_cost_identity() -> None:
    post = CostPosting(("ONE",), PostingNature.ACTIVE, "MO", F(1, 10),
                       "CREW", "2026-W01")
    ledger = ExclusiveCostLedger((post,))
    assert ledger.contractual_k == F(1, 10)
    assert ledger.total == F(1, 10)
    with pytest.raises(ValueError, match="exact Fraction"):
        CostPosting(("BAD",), PostingNature.ACTIVE, "MO", 0.1,  # type: ignore[arg-type]
                    "CREW", "2026-W01")
    with pytest.raises(ValueError, match="MO/EQ"):
        CostPosting(("BAD",), PostingNature.ACTIVE, "MAT", F(1),  # type: ignore[arg-type]
                    "CRANE", "2026-W01")
    with pytest.raises(ValueError, match="financial ownership"):
        ExclusiveCostLedger((post, post))


def test_missing_consumption_unit_and_legacy_hourly_proxy_fail_closed() -> None:
    with pytest.raises(ValueError, match="physical provenance"):
        PhysicalPurchase("proxy", "A", "DIESEL", "2026-W01",
                         F(10), "", F(1), "COMB")
    with pytest.raises(ValueError, match="exact Fraction"):
        PhysicalPurchase("hourly-proxy", "A", "DIESEL", "2026-W01",
                         10.0, "L", F(1), "COMB")  # type: ignore[arg-type]


def test_separate_mo_resource_type_does_not_mingle_contracts() -> None:
    demand = normalize_weekly_resource_demand(("W01", "W02"), {
        "A": {"CREW": (1, 0), "CRANE": (1, 0)},
    })
    tariffs = {
        "CREW": ResourceTariff(F(4), F(4), F(0), F(0), 0),
        "CRANE": ResourceTariff(F(8), F(8), F(0), F(0), 0),
    }
    pool = optimize_homogeneous_pool(demand, tariffs)
    ledger = book_exact_pool(pool, tariffs, {"CREW": "MO", "CRANE": "EQ"})
    assert ledger.contractual_k == F(12)
    assert ledger.total == pool.total
    assert {x.category for x in ledger.postings if x.nature == PostingNature.ACTIVE} == {"MO", "EQ"}

def test_overlapping_instance_level_identity_rejected_even_if_money_balances() -> None:
    # P2 review: (1,2,1) and two chains with different boundaries.
    # Mutating the middle-week level 2 into another level 1 preserves
    # the *aggregate* weekly count and monetary totals, yet bills the
    # first physical instance twice and never owns the second.
    data = normalize_weekly_resource_demand(
        ("W01", "W02", "W03"), {"A": {"CRANE": (1, 2, 1)}}
    )
    tariff = ResourceTariff(F(5), F(10), F(20), F(10), 10)
    valid = optimize_homogeneous_pool(data, {"CRANE": tariff})
    assert book_exact_pool(valid, {"CRANE": tariff}, {"CRANE": "EQ"}).total == valid.total
    ledger = valid.ledgers[0]
    wrong_chains = tuple(
        replace(chain, level=1) if chain.level == 2 else chain
        for chain in ledger.chains
    )
    forged = replace(valid, ledgers=(replace(ledger, chains=wrong_chains),))
    with pytest.raises(ValueError, match="overlapping instance-level"):
        book_exact_pool(forged, {"CRANE": tariff}, {"CRANE": "EQ"})


def test_gap_in_required_instance_level_rejected_when_presence_is_forged() -> None:
    data = normalize_weekly_resource_demand(
        ("W01", "W02", "W03"), {"A": {"CRANE": (1, 2, 1)}}
    )
    tariff = ResourceTariff(F(5), F(10), F(20), F(10), 10)
    valid = optimize_homogeneous_pool(data, {"CRANE": tariff})
    ledger = valid.ledgers[0]
    chain = next(c for c in ledger.chains if c.level == 2)
    # Reassign the required level to a non-demanded level, preserving cost
    # and aggregate presence. This must also be rejected.
    wrong = replace(chain, level=3)
    forged = replace(
        valid,
        ledgers=(replace(ledger, chains=tuple(
            wrong if c is chain else c for c in ledger.chains
        )),),
    )
    with pytest.raises(ValueError, match="do not cover exact physical demand"):
        book_exact_pool(forged, {"CRANE": tariff}, {"CRANE": "EQ"})
