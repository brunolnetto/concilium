"""P11-C: explicit, fail-closed publication of P20×Skill04 read-only metrics.

Only an independently reconciled ledger + typed sources can populate this
diagnostic. Legacy pricing and margin fields are not silently overwritten.
"""
from __future__ import annotations

from collections.abc import Mapping
from fractions import Fraction

from concilium.domain.models.canonical import CanonicalModel
from concilium.domain.models.canonical._financeiro_resultado import (
    MetricasRealizadasP11,
)

from .financial_cost_reconciliation import ExactFinancialReconciliation


def build_skill06_realized_preview(
    canonical: CanonicalModel,
    *,
    reconciliation: ExactFinancialReconciliation,
    scopes_by_activity: Mapping[str, int | float | str | Fraction],
    bdi_by_category: Mapping[str, Fraction],
    independent_variable_unit_rate: Fraction | None = None,
) -> MetricasRealizadasP11:
    """Project owned events with precise reference, without assigning GO.

    The caller supplies physical scopes and a reconciled *typed* P20 snapshot;
    otherwise no diagnostic can be published. Source IDs are checked in P20.
    """
    if not isinstance(canonical, CanonicalModel):
        raise ValueError("Skill06 preview needs a typed canonical project")
    if not isinstance(reconciliation, ExactFinancialReconciliation):
        raise ValueError("Skill06 preview needs a reconciled P20 source")
    schedule = canonical.cronograma
    if schedule is None or not schedule.scheduled_activities:
        raise ValueError("Skill06 preview needs the true Skill04 activity calendar")
    distributions = {}
    for scheduled in schedule.scheduled_activities:
        if (
            not scheduled.activity_id
            or scheduled.activity_id in distributions
            or not scheduled.distribuicao_semanal
        ):
            raise ValueError("duplicate/missing Skill04 activity identity or calendar")
        distributions[scheduled.activity_id] = scheduled.distribuicao_semanal
    if not isinstance(scopes_by_activity, Mapping) or set(distributions) != set(scopes_by_activity):
        raise ValueError("Skill06 preview requires a physical Q for every activity")
    projection = reconciliation.project_skill04_realization(
        distributions_by_activity=distributions,
        scopes_by_activity=scopes_by_activity,
        bdi_by_category=bdi_by_category,
        independent_variable_unit_rate=independent_variable_unit_rate,
    )
    return MetricasRealizadasP11(
        authority="P11_B_READ_ONLY_PREVIEW_NOT_PROJECT_GO",
        contractual_k=str(projection.contractual_k),
        physically_purchased_v=str(projection.physically_purchased_v),
        indirect=str(projection.indirect),
        price_once_bdi=str(projection.price_once_bdi),
        effective_bdi=(
            str(projection.effective_bdi) if projection.effective_bdi is not None else None
        ),
        activity_efficiencies={
            activity.activity_id: (
                str(activity.realized_efficiency)
                if activity.realized_efficiency is not None else None
            )
            for activity in projection.activities
        },
        zeta=str(projection.activity_zeta) if projection.activity_zeta is not None else None,
        pi=str(projection.activity_pi) if projection.activity_pi is not None else None,
    )
