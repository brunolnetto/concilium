"""P11-B: executable Skill04 physical cells + exact source ledger, not toy costs."""
from __future__ import annotations

from fractions import Fraction as F

import pytest

from concilium.application.scheduling.contractual_cost_ledger import (
    CostPosting,
    ExclusiveCostLedger,
    PostingNature,
)
from concilium.application.scheduling.realized_financial_metrics import (
    project_realized_financials,
)
from concilium.domain.models.canonical import DistribuicaoSemanal

WEEKS = ("2026-W01", "2026-W02", "2026-W03", "2026-W04")
BDI = {"MO": F(3, 10), "EQ": F(3, 10), "MAT": F(1, 10),
       "COMB": F(1, 10), "IND": F(1, 5)}


def cell(q: int, cumulative: int, nominal: int = 400,
         available: int = 400) -> DistribuicaoSemanal:
    return DistribuicaoSemanal(
        num_equipes=1,
        qtd_executada=q,
        qtd_acumulada=cumulative,
        pct=min(1, cumulative / 900),
        q_max_celula=nominal,
        capacidade_disponivel_semana=available,
    )


def ledger(rows: tuple[tuple[str, int, int, int], ...]) -> ExclusiveCostLedger:
    events: list[CostPosting] = []
    for week, k, v, indirect in rows:
        if k:
            events.append(CostPosting(
                ("K", week), PostingNature.ACTIVE, "MO", F(k), "contract:crew", week
            ))
        if v:
            events.append(CostPosting(
                ("V", week), PostingNature.ACQUISITION, "MAT", F(v),
                "measured:material", week
            ))
        if indirect:
            events.append(CostPosting(
                ("I", week), PostingNature.INDIRECT, "IND", F(indirect),
                "one-time:indirect", week
            ))
    return ExclusiveCostLedger(tuple(events))


def project(distribution: dict[str, DistribuicaoSemanal],
            cost: ExclusiveCostLedger, scope: int):
    return project_realized_financials(
        distributions_by_activity={"A": distribution},
        scopes_by_activity={"A": scope},
        ledger=cost,
        bdi_by_category=BDI,
        independent_variable_unit_rate=F(1),
    )


def test_real_skill04_partial_week_and_financial_postings() -> None:
    output = project({WEEKS[0]: cell(100, 100)},
                     ledger(((WEEKS[0], 400, 100, 0),)), 100)
    week = output.weeks[0]
    physical = output.activities[0].weeks[0]
    assert output.authority == "P11_B_READ_ONLY_PREVIEW_NOT_PROJECT_GO"
    assert physical.nominal_efficiency == 1
    assert physical.realized_efficiency == F(1, 4)
    assert physical.closure_fraction == F(1, 4)
    assert week.contractual_k == F(400)
    assert week.physically_purchased_v == F(100)
    assert week.cost_before_bdi == F(500)
    assert week.price_once_bdi == F(630)
    assert week.bdi_equivalent == F(13, 50)
    assert week.variable_share == F(1, 5)
    assert week.zeta == F(5, 8)
    assert week.pi == F(5, 2)
    assert output.activity_zeta == F(5, 8)
    assert output.activity_pi == F(5, 2)


def test_three_real_weekly_cells_project_to_exact_aggregate() -> None:
    distribution = {
        WEEKS[0]: cell(400, 400),
        WEEKS[1]: cell(400, 800),
        WEEKS[2]: cell(100, 900),
    }
    output = project(distribution, ledger((
        (WEEKS[0], 400, 400, 0),
        (WEEKS[1], 400, 400, 0),
        (WEEKS[2], 400, 100, 0),
    )), 900)
    assert output.activities[0].delivered_output == F(900)
    assert output.activities[0].nominal_output == F(1200)
    assert output.activity_efficiency == F(3, 4)
    assert output.contractual_k == F(1200)
    assert output.physically_purchased_v == F(900)
    assert output.indirect == 0
    assert output.activity_zeta == F(7, 8)
    assert output.activity_pi == F(7, 6)
    assert output.price_once_bdi == F(2550)
    assert output.effective_bdi == F(3, 14)
    assert sum((w.cost_before_bdi for w in output.weeks), F(0)) == F(2100)
    assert output.weeks[-1].contractual_k == F(400)
    assert output.weeks[-1].variable_share == F(1, 5)


def test_zero_output_middle_week_bills_k_without_fabricated_pi() -> None:
    distribution = {
        WEEKS[0]: cell(400, 400),
        WEEKS[1]: cell(0, 400, available=0),
        WEEKS[2]: cell(100, 500),
    }
    output = project(distribution, ledger((
        (WEEKS[0], 400, 400, 0),
        (WEEKS[1], 400, 0, 0),
        (WEEKS[2], 400, 100, 0),
    )), 500)
    physical = output.activities[0].weeks[1]
    finance = output.weeks[1]
    assert physical.nominal_efficiency == 0
    assert physical.realized_efficiency == 0
    assert physical.closure_fraction is None
    assert finance.contractual_k == 400
    assert finance.physically_purchased_v == 0
    assert finance.zeta == F(1, 2)
    assert finance.pi is None


def test_indirect_is_price_once_but_not_activity_direct_zeta() -> None:
    output = project(
        {WEEKS[0]: cell(100, 100)},
        ledger(((WEEKS[0], 400, 100, 50),)), 100,
    )
    assert output.indirect == 50
    assert output.weeks[0].cost_before_bdi == 550
    assert output.price_once_bdi == 690
    assert output.activity_zeta == F(5, 8)
    assert output.effective_bdi == F(14, 55)


def test_multi_activity_shared_pool_does_not_invent_activity_finances() -> None:
    output = project_realized_financials(
        distributions_by_activity={
            "A": {WEEKS[0]: cell(10, 10, nominal=20, available=20)},
            "B": {WEEKS[0]: cell(5, 5, nominal=10, available=10)},
        },
        scopes_by_activity={"A": 10, "B": 5},
        ledger=ledger(((WEEKS[0], 100, 0, 0),)),
        bdi_by_category=BDI,
    )
    assert {a.activity_id: a.realized_efficiency for a in output.activities} == {
        "A": F(1, 2), "B": F(1, 2)
    }
    assert output.activity_zeta is None
    assert output.activity_pi is None
    assert output.activity_efficiency is None
    with pytest.raises(ValueError, match="single"):
        project_realized_financials(
            distributions_by_activity={
                "A": {WEEKS[0]: cell(10, 10, nominal=20, available=20)},
                "B": {WEEKS[0]: cell(5, 5, nominal=10, available=10)},
            },
            scopes_by_activity={"A": 10, "B": 5},
            ledger=ledger(((WEEKS[0], 100, 0, 0),)),
            bdi_by_category=BDI,
            independent_variable_unit_rate=F(1),
        )


@pytest.mark.parametrize("wrong_v", [0, 99, 101])
def test_physical_output_unit_price_must_match_exact_posted_v(wrong_v: int) -> None:
    with pytest.raises(ValueError, match="differs from verified"):
        project({WEEKS[0]: cell(100, 100)},
                ledger(((WEEKS[0], 400, wrong_v, 0),)), 100)


def test_missing_zero_week_and_undelivered_scope_are_rejected() -> None:
    with pytest.raises(ValueError, match="consecutive"):
        project({
            WEEKS[0]: cell(400, 400),
            WEEKS[2]: cell(100, 500),
        }, ledger(((WEEKS[0], 400, 400, 0), (WEEKS[2], 400, 100, 0))), 500)
    with pytest.raises(ValueError, match="does not close"):
        project({WEEKS[0]: cell(100, 100)},
                ledger(((WEEKS[0], 400, 100, 0),)), 101)


def test_wrong_cumulative_and_overproduction_are_rejected() -> None:
    with pytest.raises(ValueError, match="cumulative"):
        project({WEEKS[0]: cell(100, 200)},
                ledger(((WEEKS[0], 400, 100, 0),)), 100)
    with pytest.raises(ValueError, match="capacity"):
        project({WEEKS[0]: cell(110, 110, nominal=100, available=100)},
                ledger(((WEEKS[0], 400, 110, 0),)), 110)


def test_posting_outside_physical_calendar_does_not_disappear() -> None:
    with pytest.raises(ValueError, match="corresponding physical week"):
        project({WEEKS[0]: cell(100, 100)}, ledger((
            (WEEKS[0], 400, 100, 0),
            (WEEKS[1], 0, 0, 50),
        )), 100)


def test_zero_cost_or_zero_reference_fail_closed() -> None:
    output = project_realized_financials(
        distributions_by_activity={
            "A": {WEEKS[0]: cell(1, 1, nominal=1, available=1)}
        },
        scopes_by_activity={"A": 1},
        ledger=ExclusiveCostLedger(()),
        bdi_by_category=BDI,
    )
    assert output.effective_bdi is None
    assert output.activity_zeta is None
    assert output.activity_pi is None


def test_missing_bdi_categories_and_float_rate_are_rejected() -> None:
    with pytest.raises(ValueError, match="BDI"):
        project_realized_financials(
            distributions_by_activity={"A": {WEEKS[0]: cell(100, 100)}},
            scopes_by_activity={"A": 100},
            ledger=ledger(((WEEKS[0], 400, 100, 0),)),
            bdi_by_category={"MO": F(3, 10)},
        )
    with pytest.raises(ValueError, match="BDI"):
        project_realized_financials(
            distributions_by_activity={"A": {WEEKS[0]: cell(100, 100)}},
            scopes_by_activity={"A": 100},
            ledger=ledger(((WEEKS[0], 400, 100, 0),)),
            bdi_by_category={**BDI, "MO": 0.3},  # type: ignore[dict-item]
        )


def test_existing_p20_snapshot_projects_real_skill04_without_reposting() -> None:
    from concilium.application.scheduling.financial_cost_reconciliation import (
        ExactFinancialReconciliation, WeekFinancialBalance,
    )

    source = ledger(((WEEKS[0], 400, 100, 0),))
    provenance = ExactFinancialReconciliation(
        source, (WeekFinancialBalance(WEEKS[0], F(400), F(100), F(0)),), True
    )
    before = tuple(source.postings)
    actual = provenance.project_skill04_realization(
        distributions_by_activity={"A": {WEEKS[0]: cell(100, 100)}},
        scopes_by_activity={"A": 100},
        bdi_by_category=BDI,
        independent_variable_unit_rate=F(1),
    )
    assert actual.activity_zeta == F(5, 8)
    assert actual.activity_pi == F(5, 2)
    assert actual.price_once_bdi == F(630)
    assert tuple(source.postings) == before
    assert actual.authority == "P11_B_READ_ONLY_PREVIEW_NOT_PROJECT_GO"

    forged = ExactFinancialReconciliation(
        source, (WeekFinancialBalance(WEEKS[0], F(399), F(101), F(0)),), True
    )
    with pytest.raises(ValueError, match="does not reconcile"):
        forged.project_skill04_realization(
            distributions_by_activity={"A": {WEEKS[0]: cell(100, 100)}},
            scopes_by_activity={"A": 100},
            bdi_by_category=BDI,
            independent_variable_unit_rate=F(1),
        )


def test_unattributed_posting_does_not_silently_disappear() -> None:
    output = ledger(((WEEKS[0], 400, 100, 0),))
    forged = ExclusiveCostLedger((
        *output.postings,
        CostPosting(
            ("MOB", "outsider"), PostingNature.MOBILIZATION, "IND",
            F(200), "mob:outsider", WEEKS[3]
        ),
    ))
    with pytest.raises(ValueError, match="corresponding physical week"):
        project({WEEKS[0]: cell(100, 100)}, forged, 100)


def test_duplicate_financial_event_is_rejected_by_authoritative_ledger() -> None:
    same = CostPosting(
        ("K", WEEKS[0]), PostingNature.ACTIVE, "MO", F(400),
        "contract:crew", WEEKS[0],
    )
    with pytest.raises(ValueError, match="duplicate financial ownership"):
        ExclusiveCostLedger((same, same))
