"""N10: declared site indirects enter the exact P20 ledger, priced per category by P21."""

from __future__ import annotations

import copy
import json
from fractions import Fraction as F
from pathlib import Path

import pytest

from concilium.application.scheduling.contractual_cost_ledger import (
    CostPosting,
    ExclusiveCostLedger,
    PostingNature,
)
from concilium.application.scheduling.financial_cost_reconciliation import reconcile_financial_sources
from concilium.application.scheduling.markup_layers import LayerRates, decompose_by_category
from concilium.application.scheduling.physical_consumption_journal import (
    AcquisitionEvidenceLine,
    PhysicalConsumptionJournalResult,
)
from concilium.application.scheduling.physical_consumption_rates import PhysicalPurchaseMeasure
from concilium.application.scheduling.site_indirect_journal import (
    SCHEMA,
    SiteIndirectDeclarationError,
    SiteIndirectJournal,
    parse_site_indirects_declaration,
    post_exact_site_indirects,
    site_indirect_postings,
)
from tests.reference_formalism.site_indirects_reference import evaluate_site_indirects

VECTORS = json.loads(
    (Path(__file__).resolve().parents[3] / "reference_formalism/vectors/economic_site_indirects_v1.json").read_text(
        encoding="utf-8"
    )
)["vectors"]


def _declaration(case: dict) -> dict:
    return {
        "schema": SCHEMA,
        "currency": "BRL",
        "source": "fixture declaration",
        "reference_id": "site-indirects-fixture-v1",
        "mobilised_weeks": case["mobilised_weeks"],
        "lines": case["lines"],
    }


def _production(case: dict) -> dict:
    """Production postings in the oracle's result shape."""
    declaration = parse_site_indirects_declaration(_declaration(case))
    journal = post_exact_site_indirects(ExclusiveCostLedger(()), declaration)
    by_category: dict[str, F] = {}
    by_week: dict[str, F] = {}
    for row in journal.postings:
        assert row.nature is PostingNature.INDIRECT and row.source == f"SITE_INDIRECT:{row.event_id[1]}"
        by_category[row.category] = by_category.get(row.category, F(0)) + row.amount
        by_week[row.week] = by_week.get(row.week, F(0)) + row.amount
    result = {
        "weeks": list(declaration.calendar_weeks),
        "postings": {"/".join(row.event_id[1:]): [row.week, row.category, str(row.amount)] for row in journal.postings},
        "by_line": {
            line: {c: str(v) for c, v in sorted(totals.items())} for line, totals in journal.cost_by_line().items()
        },
        "by_category": {c: str(v) for c, v in sorted(by_category.items())},
        "by_week": {w: str(v) for w, v in sorted(by_week.items())},
        "cost": str(journal.cost),
    }
    if "markup_by_category" in case:
        rates = {c: F(v) for c, v in case["markup_by_category"].items()} | {"MAT": F(0)}
        consumption = PhysicalConsumptionJournalResult(ExclusiveCostLedger(()), ())
        priced = reconcile_financial_sources(
            ExclusiveCostLedger(()), consumption, site_indirects=journal
        ).project_price_once_bdi(rates)
        result["price"] = str(priced.price_once_bdi)
    return result


@pytest.mark.parametrize("vector", VECTORS, ids=lambda v: v["case_id"])
def test_production_matches_the_independent_oracle(vector: dict) -> None:
    if "expected_error" in vector:
        with pytest.raises(ValueError):
            _production(vector["case"])
        return
    assert _production(vector["case"]) == vector["expected"] == evaluate_site_indirects(vector["case"])


ADM = {
    "line_id": "ADM",
    "driver": "perm",
    "source": "planilha de administração local",
    "monthly": {"MO": "43830", "EQ": "14610", "COMB": "1461", "VM": "2922"},
}
MOB = {"line_id": "MOB_SITE", "driver": "onetime", "source": "orçamento", "mobilize": "80000", "demobilize": "30000"}
CASE = {"mobilised_weeks": {"first": "2026-W19", "last": "2026-W22"}, "lines": [ADM, MOB]}


def _sources() -> tuple[ExclusiveCostLedger, PhysicalConsumptionJournalResult]:
    pool = ExclusiveCostLedger(
        (
            CostPosting(
                ("POOL", "R", "1", "0", "1", "CONTRACTUAL_ACTIVE", "0"),
                PostingNature.ACTIVE,
                "EQ",
                F(1000),
                "R",
                "2026-W19",
            ),
            CostPosting(("POOL", "R", "1", "0", "1", "MOB"), PostingNature.MOBILIZATION, "IND", F(90), "R", "2026-W19"),
        )
    )
    evidence = AcquisitionEvidenceLine(
        "c1",
        "PLANNED_CLOSED_SCOPE",
        "A",
        "2026-W19",
        PhysicalPurchaseMeasure("DIESEL", F(10), "L", F(10), "L", F(60)),
        "COMB",
    )
    acquisition = CostPosting(("CONSUMABLE", "c1"), PostingNature.ACQUISITION, "COMB", F(60), "DIESEL", "2026-W19")
    return pool, PhysicalConsumptionJournalResult(ExclusiveCostLedger(pool.postings + (acquisition,)), (evidence,))


def _journal(base: ExclusiveCostLedger, case: dict = CASE) -> SiteIndirectJournal:
    return post_exact_site_indirects(base, parse_site_indirects_declaration(_declaration(case)))


def test_p20_adds_exactly_the_declared_site_indirects() -> None:
    pool, consumption = _sources()
    before = reconcile_financial_sources(pool, consumption)
    after = reconcile_financial_sources(pool, consumption, site_indirects=_journal(consumption.journal))

    assert before.site_indirects is None and after.site_indirects is not None
    # Direct cost is untouched: site MO/EQ/COMB are indirect by nature, not K or V.
    assert (after.ledger.contractual_k, after.ledger.consumable_v) == (F(1000), F(60))
    assert after.direct == before.direct == F(1060)
    assert after.indirect == before.indirect + F(167792) == F(167882)
    assert after.total == F(168942)
    assert {w.week: w.indirect for w in after.weeks} == {
        "2026-W19": F(90) + F(94448),
        "2026-W20": F(14448),
        "2026-W21": F(14448),
        "2026-W22": F(44448),
    }
    # One attribution row per posting, owned by its declared source.
    site_rows = [row for row in after.event_attribution if row.event_id[0] == "SITE_INDIRECT"]
    assert len(site_rows) == 4 * 4 + 2 == len(after.site_indirects.postings)
    assert {(row.owner_scope, row.owner_id) for row in site_rows} == {
        ("SOURCE", ("SITE_INDIRECT:ADM",)),
        ("SOURCE", ("SITE_INDIRECT:MOB_SITE",)),
    }
    assert sum((row.amount for row in after.event_attribution), F(0)) == after.total
    assert sum((row.amount for row in after.category_balances), F(0)) == after.total


def test_p21_prices_each_sub_category_with_its_own_markup() -> None:
    pool, consumption = _sources()
    reconciliation = reconcile_financial_sources(pool, consumption, site_indirects=_journal(consumption.journal))
    rates = {"MO": F(1, 4), "EQ": F(1, 5), "MAT": F(0), "COMB": F(1, 10), "IND": F(1, 2)}
    priced = reconciliation.project_price_once_bdi(rates)
    by_category = {row.category: row for row in priced.categories}
    assert by_category["MO"].cost_before_bdi == F(40320)  # site labour only
    assert by_category["EQ"].cost_before_bdi == F(1000) + F(13440)
    assert by_category["COMB"].cost_before_bdi == F(60) + F(1344)
    assert by_category["IND"].cost_before_bdi == F(90) + F(112688)
    # Site part: 1185192/5 (oracle); pool EQ 1200, pool MOB 135, diesel 66.
    assert priced.price_once_bdi == F(1185192, 5) + 1200 + 135 + 66

    layers = {c: LayerRates(F(0), F(0), F(0), rate, ()) for c, rate in rates.items()}
    _, total = decompose_by_category(((r.category, r.amount) for r in reconciliation.ledger.postings), layers)
    assert (total.cost, total.price) == (reconciliation.total, priced.price_once_bdi)


@pytest.mark.parametrize("tamper", ["forged_amount", "extra_posting", "dropped_posting", "shifted_week"])
def test_p20_rejects_a_journal_that_differs_from_its_declaration(tamper: str) -> None:
    pool, consumption = _sources()
    journal = _journal(consumption.journal)
    rows = list(journal.ledger.postings)
    index = next(i for i, row in enumerate(rows) if row.event_id[0] == "SITE_INDIRECT")
    target = rows[index]
    if tamper == "forged_amount":
        rows[index] = CostPosting(
            target.event_id, target.nature, target.category, target.amount + 1, target.source, target.week
        )
    elif tamper == "extra_posting":
        rows.append(
            CostPosting(
                ("SITE_INDIRECT", "GHOST", "MOB"),
                PostingNature.INDIRECT,
                "IND",
                F(1),
                "SITE_INDIRECT:GHOST",
                "2026-W19",
            )
        )
    elif tamper == "dropped_posting":
        del rows[index]
    else:
        rows[index] = CostPosting(
            target.event_id, target.nature, target.category, target.amount, target.source, "2026-W22"
        )
    forged = SiteIndirectJournal(ExclusiveCostLedger(tuple(rows)), journal.declaration)
    with pytest.raises(ValueError, match="N10 site indirects"):
        reconcile_financial_sources(pool, consumption, site_indirects=forged)


def test_p20_rejects_an_untyped_journal_and_a_modified_base() -> None:
    pool, consumption = _sources()
    with pytest.raises(ValueError, match="typed site-indirects journal"):
        reconcile_financial_sources(pool, consumption, site_indirects=object())  # type: ignore[arg-type]
    # A journal posted over another base (missing the P18 acquisition) is not this project's ledger.
    with pytest.raises(ValueError, match="N10 site indirects"):
        reconcile_financial_sources(pool, consumption, site_indirects=_journal(pool))


def test_site_indirects_cannot_be_posted_twice() -> None:
    journal = _journal(ExclusiveCostLedger(()))
    with pytest.raises(ValueError, match="already carries site indirects"):
        post_exact_site_indirects(journal.ledger, journal.declaration)


def test_indirect_nature_never_takes_a_material_category_or_a_missing_week() -> None:
    with pytest.raises(ValueError, match="indirect cost needs"):
        CostPosting(("X",), PostingNature.INDIRECT, "MAT", F(1), "s", "2026-W19")
    with pytest.raises(ValueError, match="indirect cost needs"):
        CostPosting(("X",), PostingNature.INDIRECT, "MO", F(1), "s", None)
    # Pool movements and holding keep the IND category.
    with pytest.raises(ValueError, match="not contractual K or V"):
        CostPosting(("X",), PostingNature.MOBILIZATION, "EQ", F(1), "s", "2026-W19")
    with pytest.raises(ValueError, match="not contractual K or V"):
        CostPosting(("X",), PostingNature.HOLDING, "MO", F(1), "s", "2026-W19")


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda d: d.pop("currency"), "must declare exactly"),
        (lambda d: d.pop("source"), "must declare exactly"),
        (lambda d: d.update(schema="other"), "schema must be"),
        (lambda d: d.update(estimated=True), "must declare exactly"),
        (lambda d: d.update(reference_id=" "), "reference_id must be nonempty"),
        (lambda d: d.update(lines=[]), "at least one line"),
        (lambda d: d["mobilised_weeks"].update(last="2026-W18"), "precedes"),
        (lambda d: d["mobilised_weeks"].update(first="2026-W54"), "not a valid ISO week"),
        (lambda d: d["mobilised_weeks"].update(first="S1"), "ISO week YYYY-Www"),
        (lambda d: d["lines"][0]["monthly"].update(MO=43830.0), "exact decimal or rational string"),
        (lambda d: d["lines"][0]["monthly"].update(MO="about 40k"), "exact decimal or rational string"),
        (lambda d: d["lines"][0]["monthly"].update(MO="-1"), "nonnegative"),
        (lambda d: d["lines"][0]["monthly"].pop("VM"), "must declare exactly"),
        (lambda d: d["lines"][0]["monthly"].update(MAT="1"), "must declare exactly"),
        (lambda d: d["lines"][0].pop("source"), "must declare exactly"),
        (lambda d: d["lines"][0].update(driver="magnitude_financeira"), "driver must be perm or onetime"),
        (lambda d: d["lines"][1].pop("demobilize"), "must declare exactly"),
        (lambda d: d["lines"][1].update(line_id="ADM"), "duplicate site indirect line"),
    ],
)
def test_declaration_fails_closed(mutate, message: str) -> None:
    raw = copy.deepcopy(_declaration(CASE))
    mutate(raw)
    with pytest.raises(SiteIndirectDeclarationError, match=message):
        parse_site_indirects_declaration(raw)


def test_postings_are_a_pure_function_of_the_declaration() -> None:
    declaration = parse_site_indirects_declaration(_declaration(CASE))
    assert site_indirect_postings(declaration) == site_indirect_postings(declaration)
    assert len({row.event_id for row in site_indirect_postings(declaration)}) == 18
