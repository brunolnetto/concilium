"""P11-C: exact first-class Skill06 preview from typed real sources."""
from __future__ import annotations

from fractions import Fraction as F

import pytest

from concilium.application.scheduling.contractual_cost_ledger import (
    CostPosting,
    ExclusiveCostLedger,
    PostingNature,
)
from concilium.application.scheduling.financial_cost_reconciliation import (
    ExactFinancialReconciliation,
    WeekFinancialBalance,
)
from concilium.application.scheduling.skill06_realized_consumer import (
    build_skill06_realized_preview,
)
from concilium.domain.models.canonical import (
    CanonicalModel,
    Cronograma,
    DistribuicaoSemanal,
    Resultado,
    ScheduledActivityCanonical,
)

W = "2026-W01"
BDI = {"MO": F(3, 10), "EQ": F(3, 10), "MAT": F(1, 10),
       "COMB": F(1, 10), "IND": F(1, 5)}


def canonical(q: int = 100, scope: int = 100) -> CanonicalModel:
    cell = DistribuicaoSemanal(
        num_equipes=1, qtd_executada=q, qtd_acumulada=q,
        pct=q / scope, q_max_celula=400, capacidade_disponivel_semana=400,
    )
    return CanonicalModel.model_construct(cronograma=Cronograma(
        scheduled_activities=[ScheduledActivityCanonical(
            activity_id="A", start_week=0, end_week=0, duration_weeks=1,
            distribuicao_semanal={W: cell},
        )],
    ))


def source() -> ExactFinancialReconciliation:
    ledger = ExclusiveCostLedger((
        CostPosting(("K", W), PostingNature.ACTIVE, "MO", F(400), "contract", W),
        CostPosting(("V", W), PostingNature.ACQUISITION, "MAT", F(100), "good", W),
    ))
    return ExactFinancialReconciliation(
        ledger, (WeekFinancialBalance(W, F(400), F(100), F(0)),), False,
    )


def test_result_model_has_typed_optional_realized_diagnostic() -> None:
    record = Resultado.model_construct()
    assert record.metricas_realizadas_p11 is None


def test_real_skill06_consumer_publishes_auditable_exact_ratios() -> None:
    original = source()
    original_ids = tuple(x.event_id for x in original.ledger.postings)
    preview = build_skill06_realized_preview(
        canonical(), reconciliation=original, scopes_by_activity={"A": F(100)},
        bdi_by_category=BDI, independent_variable_unit_rate=F(1),
    )
    assert preview.authority == "P11_B_READ_ONLY_PREVIEW_NOT_PROJECT_GO"
    assert preview.source == "SKILL04_P20_EXCLUSIVE_POSTINGS"
    assert preview.contractual_k == "400"
    assert preview.physically_purchased_v == "100"
    assert preview.indirect == "0"
    assert preview.price_once_bdi == "630"
    assert preview.effective_bdi == "13/50"
    assert preview.activity_efficiencies == {"A": "1/4"}
    assert preview.zeta == "5/8"
    assert preview.pi == "5/2"
    assert tuple(x.event_id for x in original.ledger.postings) == original_ids
    bound = Resultado.model_construct().model_copy(
        update={"metricas_realizadas_p11": preview},
    )
    assert bound.metricas_realizadas_p11 == preview
    assert bound.model_dump()["metricas_realizadas_p11"]["zeta"] == "5/8"


def test_real_skill06_consumer_fails_if_scope_or_ledger_is_missing() -> None:
    with pytest.raises(ValueError, match="physical Q"):
        build_skill06_realized_preview(
            canonical(), reconciliation=source(), scopes_by_activity={},
            bdi_by_category=BDI,
        )
    with pytest.raises(ValueError, match="reconciled P20"):
        build_skill06_realized_preview(
            canonical(), reconciliation=None,  # type: ignore[arg-type]
            scopes_by_activity={"A": 100}, bdi_by_category=BDI,
        )


def test_missing_schedule_and_duplicated_activity_are_rejected() -> None:
    empty = CanonicalModel.model_construct(cronograma=Cronograma())
    with pytest.raises(ValueError, match="activity calendar"):
        build_skill06_realized_preview(
            empty, reconciliation=source(), scopes_by_activity={"A": 100},
            bdi_by_category=BDI,
        )
    duplicate = canonical()
    schedule = duplicate.cronograma
    assert schedule is not None
    duplication = schedule.model_copy(update={
        "scheduled_activities": schedule.scheduled_activities * 2
    })
    duplicate = duplicate.model_copy(update={"cronograma": duplication})
    with pytest.raises(ValueError, match="duplicate/missing"):
        build_skill06_realized_preview(
            duplicate, reconciliation=source(), scopes_by_activity={"A": 100},
            bdi_by_category=BDI,
        )


def test_bdionce_must_use_complete_exact_category_rates() -> None:
    with pytest.raises(ValueError, match="BDI"):
        build_skill06_realized_preview(
            canonical(), reconciliation=source(), scopes_by_activity={"A": 100},
            bdi_by_category={"MO": F(3, 10)},
        )


def test_consumer_prohibits_relabeling_projection_as_project_go() -> None:
    from pydantic import ValidationError
    from concilium.domain.models.canonical._financeiro_resultado import (
        MetricasRealizadasP11,
    )

    with pytest.raises(ValidationError):
        MetricasRealizadasP11(
            authority="PROJECT_GO", contractual_k="400",
            physically_purchased_v="100", indirect="0", price_once_bdi="630",
            effective_bdi="13/50", activity_efficiencies={"A": "1/4"},
            zeta="5/8", pi="5/2",
        )
