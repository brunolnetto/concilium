"""P11-B: read-only physical/financial realization from real Skill 04 and P17+ postings.

This is a typed, exact *preview*. Pool costs cannot be attributed to multiple
activities without independent physical-instance ownership evidence. Never use
these ratios as P23 project GO, invent a reference price, or book a second cost.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from fractions import Fraction

from concilium.domain.models.canonical import DistribuicaoSemanal

from .contractual_cost_ledger import ExclusiveCostLedger, PostingNature

ZERO = Fraction(0)
CATEGORIES = frozenset({"MO", "EQ", "MAT", "COMB", "IND"})


def _exact(value: int | float | str | Fraction, *, name: str) -> Fraction:
    if isinstance(value, bool):
        raise ValueError(f"{name}: boolean is not a monetary or physical amount")
    try:
        quantity = Fraction(str(value))
    except (ValueError, TypeError, ZeroDivisionError) as exc:
        raise ValueError(f"{name}: invalid physical or monetary quantity") from exc
    if quantity < 0:
        raise ValueError(f"{name}: negative amount")
    return quantity


def _iso(week: str) -> date:
    try:
        year, weeknum = week.split("-W")
        if len(year) != 4 or len(weeknum) != 2:
            raise ValueError("bad width")
        return date.fromisocalendar(int(year), int(weeknum), 1)
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError(f"invalid ISO calendar week: {week!r}") from exc


@dataclass(frozen=True)
class RealizedActivityWeek:
    activity_id: str
    week: str
    nominal_output: Fraction
    available_output: Fraction
    delivered_output: Fraction
    nominal_efficiency: Fraction | None
    realized_efficiency: Fraction | None
    closure_fraction: Fraction | None


@dataclass(frozen=True)
class RealizedActivity:
    activity_id: str
    delivered_output: Fraction
    nominal_output: Fraction
    realized_efficiency: Fraction | None
    weeks: tuple[RealizedActivityWeek, ...]


@dataclass(frozen=True)
class RealizedFinancialWeek:
    week: str
    contractual_k: Fraction
    physically_purchased_v: Fraction
    indirect: Fraction
    cost_before_bdi: Fraction
    price_once_bdi: Fraction
    bdi_equivalent: Fraction | None
    variable_share: Fraction | None
    zeta: Fraction | None
    pi: Fraction | None


@dataclass(frozen=True)
class RealizedFinancialProjection:
    activities: tuple[RealizedActivity, ...]
    weeks: tuple[RealizedFinancialWeek, ...]
    contractual_k: Fraction
    physically_purchased_v: Fraction
    indirect: Fraction
    price_once_bdi: Fraction
    effective_bdi: Fraction | None
    activity_efficiency: Fraction | None
    activity_zeta: Fraction | None
    activity_pi: Fraction | None
    authority: str = "P11_B_READ_ONLY_PREVIEW_NOT_PROJECT_GO"


def _activity(
    activity_id: str,
    distribution: Mapping[str, DistribuicaoSemanal],
    expected_scope: Fraction,
) -> RealizedActivity:
    if not activity_id or not distribution or expected_scope <= 0:
        raise ValueError("complete nonempty activity and positive physical scope required")
    weeks = sorted(distribution, key=_iso)
    stamps = [_iso(w) for w in weeks]
    if any((later - first).days != 7
           for first, later in zip(stamps, stamps[1:], strict=False)):
        raise ValueError(f"{activity_id}: activity weeks must be consecutive, including zero weeks")
    result: list[RealizedActivityWeek] = []
    cumulative = ZERO
    reference_total = ZERO
    for week in weeks:
        cell = distribution[week]
        if not isinstance(cell, DistribuicaoSemanal):
            raise ValueError("Skill 04 source must be a typed weekly cell")
        if cell.capacidade_disponivel_semana is None:
            raise ValueError("exogenous available physical capacity is missing")
        nominal = _exact(cell.q_max_celula, name="q_max_celula")
        available = _exact(cell.capacidade_disponivel_semana, name="capacity")
        delivered = _exact(cell.qtd_executada, name="qtd_executada")
        observed_total = _exact(cell.qtd_acumulada, name="qtd_acumulada")
        if delivered > available or available > nominal:
            raise ValueError("q > capacity or available capacity > F(m)H")
        cumulative += delivered
        reference_total += nominal
        if cumulative != observed_total:
            raise ValueError("Skill 04 cumulative physical scope does not reconcile")
        result.append(RealizedActivityWeek(
            activity_id, week, nominal, available, delivered,
            available / nominal if nominal else None,
            delivered / nominal if nominal else None,
            delivered / available if available else None,
        ))
    if cumulative != expected_scope:
        raise ValueError(f"activity {activity_id} does not close its declared physical Q")
    return RealizedActivity(
        activity_id, cumulative, reference_total,
        cumulative / reference_total if reference_total else None, tuple(result),
    )


def project_realized_financials(
    *,
    distributions_by_activity: Mapping[str, Mapping[str, DistribuicaoSemanal]],
    scopes_by_activity: Mapping[str, int | float | str | Fraction],
    ledger: ExclusiveCostLedger,
    bdi_by_category: Mapping[str, Fraction],
    independent_variable_unit_rate: Fraction | None = None,
) -> RealizedFinancialProjection:
    """Project documented fields using *unchanged* weekly cells and cost events.

    independent_variable_unit_rate is an independent physical-output based
    contract in BRL/u_i, never recovered by V/q or by a monetary material proxy.
    Only one activity may claim financial zeta/pi: with multiple activities,
    project K is shared and allocating it to an activity without chain evidence
    would be fictitious. This function does not post or change costs.
    """
    if not distributions_by_activity or set(distributions_by_activity) != set(scopes_by_activity):
        raise ValueError("exact nonempty activity identifiers and declared scopes required")
    if not isinstance(ledger, ExclusiveCostLedger):
        raise ValueError("an exclusive real financial ledger is required")
    if set(bdi_by_category) != CATEGORIES or any(
        type(rate) is not Fraction or rate < 0 for rate in bdi_by_category.values()
    ):
        raise ValueError("explicit exact nonnegative BDI rates for all categories required")
    single = len(distributions_by_activity) == 1
    if independent_variable_unit_rate is not None and (
        not single or type(independent_variable_unit_rate) is not Fraction
        or independent_variable_unit_rate < 0
    ):
        raise ValueError("typed physical-output rate only for a single scoped activity")
    activities = tuple(
        _activity(activity, distributions_by_activity[activity],
                  _exact(scopes_by_activity[activity], name="Q"))
        for activity in sorted(distributions_by_activity)
    )
    all_weeks = {entry.week for activity in activities for entry in activity.weeks}
    physical_week = {
        row.week: row for a in activities for row in a.weeks
    } if single else {}
    buckets: dict[str, list[Fraction]] = {
        week: [ZERO, ZERO, ZERO, ZERO] for week in all_weeks
    }
    for event in ledger.postings:
        if not isinstance(event.week, str) or event.week not in all_weeks:
            raise ValueError("cost posting has no corresponding physical week")
        if event.category not in bdi_by_category:
            raise ValueError("unclassified financial event cannot be marked-up")
        values = buckets[event.week]
        if event.nature in (PostingNature.ACTIVE, PostingNature.IDLE):
            values[0] += event.amount
        elif event.nature == PostingNature.ACQUISITION:
            values[1] += event.amount
        elif event.nature in (
            PostingNature.MOBILIZATION, PostingNature.DEMOBILIZATION,
            PostingNature.INDIRECT, PostingNature.HOLDING,
        ):
            values[2] += event.amount
        else:
            raise ValueError("unsupported cost posting nature")
        values[3] += event.amount * (1 + bdi_by_category[event.category])

    financial: list[RealizedFinancialWeek] = []
    total_k = total_v = total_ind = total_price = ZERO
    for week in sorted(all_weeks, key=_iso):
        k, v, indirect, price = buckets[week]
        cost = k + v + indirect
        direct = k + v
        zeta: Fraction | None = None
        pi: Fraction | None = None
        if independent_variable_unit_rate is not None:
            physical = physical_week[week]
            if v != independent_variable_unit_rate * physical.delivered_output:
                raise ValueError("physical V posting differs from verified output rate")
            reference = k + independent_variable_unit_rate * physical.nominal_output
            zeta = direct / reference if reference else None
            if reference > 0 and physical.delivered_output > 0 and physical.nominal_output > 0:
                pi = (
                    (direct / physical.delivered_output)
                    / (reference / physical.nominal_output)
                )
                if physical.realized_efficiency is None or zeta != physical.realized_efficiency * pi:
                    raise ValueError("realized efficiency and zeta/pi do not reconcile")
        financial.append(RealizedFinancialWeek(
            week, k, v, indirect, cost, price,
            price / cost - 1 if cost else None,
            v / direct if direct else None,
            zeta, pi,
        ))
        total_k += k
        total_v += v
        total_ind += indirect
        total_price += price
    if (
        total_k != ledger.contractual_k
        or total_v != ledger.consumable_v
        or total_ind != ledger.indirect
        or total_k + total_v + total_ind != ledger.total
    ):
        raise ValueError("week financial projection differs from exclusive source ledger")

    total_direct = total_k + total_v
    total = total_direct + total_ind
    efficiency: Fraction | None = None
    overall_zeta: Fraction | None = None
    overall_pi: Fraction | None = None
    if single:
        activity = activities[0]
        efficiency = activity.realized_efficiency
        if independent_variable_unit_rate is not None:
            reference = total_k + independent_variable_unit_rate * activity.nominal_output
            overall_zeta = total_direct / reference if reference else None
            if activity.delivered_output > 0 and activity.nominal_output > 0 and reference > 0:
                overall_pi = (
                    (total_direct / activity.delivered_output)
                    / (reference / activity.nominal_output)
                )
                if overall_zeta != efficiency * overall_pi:
                    raise ValueError("aggregated zeta/pi identity failed")
    return RealizedFinancialProjection(
        activities, tuple(financial), total_k, total_v, total_ind, total_price,
        total_price / total - 1 if total else None,
        efficiency, overall_zeta, overall_pi,
    )
