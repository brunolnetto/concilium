"""P18-C1: strictly sourced Skill04 Q -> P18 purchases -> P20 read-only preview.

No canonical financial mutation, no inferred machine hours, no PROJECT_GO.
The caller must supply physical catalog rate/price mapping for every scheduled
activity and explicit observed operating hours for hourly goods.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from math import isfinite
from typing import Literal

from concilium.domain.models.canonical import CanonicalModel

from .contractual_cost_ledger import ExclusiveCostLedger
from .financial_cost_reconciliation import ExactFinancialReconciliation, reconcile_financial_sources
from .physical_consumption_journal import (
    PhysicalConsumptionJournalResult,
    WeeklyConsumptionEvidence,
    book_weekly_physical_consumption,
)
from .physical_consumption_rates import ConsumptionBasis, PhysicallyPricedGood

PricedCategory = Literal["MAT", "COMB"]
ActivityGoods = Mapping[str, Mapping[str, tuple[PhysicallyPricedGood, PricedCategory]]]
_SCOPE_TOLERANCE = Fraction(1, 1_000_000)


@dataclass(frozen=True)
class P18CConsumptionPreview:
    consumption: PhysicalConsumptionJournalResult
    reconciliation: ExactFinancialReconciliation
    authority: str = "P18C_SKILL04_PLANNED_PREVIEW_NOT_PROJECT_GO"


def _exact_q(value: float) -> Fraction:
    if type(value) not in (float, int) or not isfinite(value) or value < 0:
        raise ValueError("Skill04 weekly quantity requires a finite nonnegative number")
    return Fraction(str(value))


def _activity_scope_units(canonical: CanonicalModel) -> dict[str, tuple[Fraction, str]]:
    eap = {item.item_id: item for item in canonical.eap}
    if len(eap) != len(canonical.eap):
        raise ValueError("duplicate EAP item identity")
    activities = canonical.atividades
    if activities:
        result: dict[str, tuple[Fraction, str]] = {}
        for activity in activities:
            if activity.atividade_id in result or activity.eap_item_id not in eap:
                raise ValueError("duplicate activity or missing EAP mapping")
            item = eap[activity.eap_item_id]
            if not item.unidade:
                raise ValueError("physical EAP unit is required")
            result[activity.atividade_id] = (
                _exact_q(activity.quantitativo_atividade), item.unidade
            )
        return result
    # Legacy Skill04 may schedule EAP items directly, without canonical subactivities.
    if any(not item.unidade for item in eap.values()):
        raise ValueError("physical EAP unit is required")
    return {
        item_id: (_exact_q(item.quantitativo), item.unidade or "")
        for item_id, item in eap.items()
    }


def _iso_week(week: str) -> None:
    if (
        not isinstance(week, str) or len(week) != 8
        or week[4:6] != "-W" or not week[:4].isdigit() or not week[6:].isdigit()
    ):
        raise ValueError("physical consumption requires canonical YYYY-Www week")
    year, number = int(week[:4]), int(week[6:])
    try:
        date.fromisocalendar(year, number, 1)
    except ValueError as exc:
        raise ValueError("invalid ISO week for physical consumption") from exc


def book_skill04_planned_consumption_preview(
    canonical: CanonicalModel,
    pool: ExclusiveCostLedger,
    goods_by_activity: ActivityGoods,
    *,
    observed_hours: Sequence[WeeklyConsumptionEvidence] = (),
) -> P18CConsumptionPreview:
    """Create a P18/P20 preview from a *newly provided* final Skill04 schedule.

    The mapping is an explicit catalog/contract boundary, not an inferred
    κ from a monetary hourly proxy. All active weekly output is accounted for
    by exact decimal rational Q, never by dividing Q by an assumed F(m).
    Financial costs are reconciled as new disjoint events, not written into
    the old Skill06 canonical pricing/result fields.
    """
    if not isinstance(canonical, CanonicalModel) or not isinstance(pool, ExclusiveCostLedger):
        raise ValueError("typed canonical and P17 pool ledger are required")
    schedule = canonical.cronograma
    if schedule is None or not schedule.is_feasible or not schedule.scheduled_activities:
        raise ValueError("a feasible, nonempty Skill04 schedule is required")
    if not isinstance(goods_by_activity, Mapping):
        raise ValueError("explicit activity-to-physical-good catalog mapping required")
    scopes = _activity_scope_units(canonical)
    scheduled = schedule.scheduled_activities
    ids = [activity.activity_id for activity in scheduled]
    if len(set(ids)) != len(ids) or set(ids) != set(scopes) or set(ids) != set(goods_by_activity):
        raise ValueError("Skill04 schedule, EAP scope and physical catalog mapping must agree")

    goods: dict[str, tuple[PhysicallyPricedGood, PricedCategory]] = {}
    evidenced: list[WeeklyConsumptionEvidence] = []
    scheduled_weeks: set[tuple[str, str]] = set()
    hourly_requirements: set[tuple[str, str, str]] = set()

    for activity in scheduled:
        if activity.produtividade_fallback_aplicada:
            raise ValueError("uncalibrated Skill04 fallback cannot source P18 acquisition")
        activity_id = activity.activity_id
        expected_q, unit = scopes[activity_id]
        activity_goods = goods_by_activity[activity_id]
        if not isinstance(activity_goods, Mapping) or not activity_goods:
            raise ValueError("each scheduled activity requires an explicit physical goods mapping")
        for good_id, declaration in activity_goods.items():
            if (
                not isinstance(good_id, str) or not good_id.strip()
                or not isinstance(declaration, tuple) or len(declaration) != 2
            ):
                raise ValueError("malformed physical good declaration")
            priced, category = declaration
            if not isinstance(priced, PhysicallyPricedGood) or priced.rate.good_id != good_id:
                raise ValueError("physical catalog good identity mismatch")
            if category not in ("MAT", "COMB"):
                raise ValueError("MAT/COMB physical category is required")
            if good_id in goods and goods[good_id] != declaration:
                raise ValueError("conflicting physical rate/price for shared good")
            goods[good_id] = declaration

        weekly_q = Fraction(0)
        if not activity.distribuicao_semanal:
            raise ValueError("Skill04 requires a nonempty physical weekly distribution")
        for week, row in sorted(activity.distribuicao_semanal.items()):
            _iso_week(week)
            scheduled_weeks.add((activity_id, week))
            q = _exact_q(row.qtd_executada)
            weekly_q += q
            for good_id, (priced, _) in activity_goods.items():
                if priced.rate.basis == ConsumptionBasis.PER_DELIVERED_UNIT:
                    if q:
                        evidenced.append(WeeklyConsumptionEvidence(
                            evidence_id=f"P18C:Q:{activity_id}:{good_id}:{week}",
                            activity_id=activity_id, good_id=good_id, week=week,
                            basis=ConsumptionBasis.PER_DELIVERED_UNIT,
                            kind="PLANNED_CLOSED_SCOPE",
                            delivered_quantity=q, delivered_unit=unit,
                        ))
                else:
                    # Hours remain a separate observation, even on a zero-Q week.
                    hourly_requirements.add((activity_id, good_id, week))
        if abs(weekly_q - expected_q) > _SCOPE_TOLERANCE:
            raise ValueError("Skill04 weekly physical Q does not close activity scope")

    observed_keys: set[tuple[str, str, str]] = set()
    for observation in observed_hours:
        if not isinstance(observation, WeeklyConsumptionEvidence):
            raise ValueError("typed operating-hour evidence required")
        key = (observation.activity_id, observation.good_id, observation.week)
        if (
            observation.kind != "OBSERVED_OPERATION"
            or observation.basis != ConsumptionBasis.PER_OPERATING_HOUR
            or key not in hourly_requirements
            or (observation.activity_id, observation.week) not in scheduled_weeks
            or key in observed_keys
        ):
            raise ValueError("operating hours require unique matched Skill04 physical provenance")
        observed_keys.add(key)
        evidenced.append(observation)
    if observed_keys != hourly_requirements:
        raise ValueError("hourly physical goods require explicit operating-hour evidence")

    result = book_weekly_physical_consumption(pool, goods, evidenced)
    reconciled = reconcile_financial_sources(pool, result)
    return P18CConsumptionPreview(result, reconciled)
