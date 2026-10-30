"""P18-C1: strictly sourced Skill04 Q -> P18 purchases -> P20 read-only preview.

No canonical financial mutation, no inferred machine hours, no PROJECT_GO.
The caller must supply physical catalog rate/price mapping for every scheduled
activity and explicit observed operating hours for hourly goods.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from fractions import Fraction
from math import isfinite
from typing import Literal

from concilium.domain.models.canonical import CanonicalModel
from concilium.domain.units import normalize_unidade

from .contractual_cost_ledger import ExclusiveCostLedger
from .financial_cost_reconciliation import ExactFinancialReconciliation, reconcile_financial_sources
from .physical_consumption_journal import (
    PhysicalConsumptionJournalResult,
    WeeklyConsumptionEvidence,
    book_weekly_physical_consumption,
)
from .physical_consumption_rates import (
    ConsumptionBasis,
    PhysicalConsumptionRate,
    PhysicallyPricedGood,
    convert_physical,
)

PricedCategory = Literal["MAT", "COMB"]
ActivityGoods = Mapping[str, Mapping[str, tuple[PhysicallyPricedGood, PricedCategory]]]
_ABS_SCOPE_TOLERANCE = Fraction(1, 1_000_000)
_REL_SCOPE_TOLERANCE = Fraction(1, 1_000_000_000)
# Skill01 explicitly uses round(fracao * Q, 6) for split children.
_CHILD_ROUNDING_ERROR = Fraction(1, 2_000_000)


@dataclass(frozen=True)
class P18CConsumptionPreview:
    consumption: PhysicalConsumptionJournalResult
    reconciliation: ExactFinancialReconciliation
    authority: str = "P18C_SKILL04_PLANNED_PREVIEW_NOT_PROJECT_GO"


def _exact_q(value: object) -> Fraction:
    # Catalog rows are Mapping[str, object]. Narrow explicitly to exact built-in
    # numeric types; bool, Decimal, strings and numeric proxy objects are not
    # accepted as physical measurements.
    if type(value) is int:
        numeric: int | float = value
    elif type(value) is float:
        numeric = value
    else:
        raise ValueError("Skill04 weekly quantity requires a finite nonnegative number")
    if numeric < 0:
        raise ValueError("Skill04 weekly quantity requires a finite nonnegative number")
    # math.isfinite converts integers to float; an adversarially large int can
    # overflow during that conversion instead of failing closed with ValueError.
    try:
        finite = isfinite(numeric)
    except OverflowError:
        finite = False
    if not finite:
        raise ValueError("Skill04 weekly quantity requires a finite nonnegative number")
    return Fraction(str(numeric))


def _scope_tolerance(expected: Fraction) -> Fraction:
    """A relative cap prevents tiny quantities from being erased by epsilon."""
    return min(_ABS_SCOPE_TOLERANCE, expected * _REL_SCOPE_TOLERANCE)


def _activity_scope_units(canonical: CanonicalModel) -> dict[str, tuple[Fraction, str]]:
    """Skill04's *final* activity IDs are EAP item_ids, not Skill01 subactivity IDs.

    Skill01 subdivisions must still reconcile to each parent EAP item, even
    though Skill04 currently schedules and distributes each parent in aggregate.
    """
    eap = {item.item_id: item for item in canonical.eap}
    if len(eap) != len(canonical.eap):
        raise ValueError("duplicate EAP item identity")
    if not eap or any(not item.unidade for item in eap.values()):
        raise ValueError("physical EAP unit is required")
    scopes = {
        item_id: (_exact_q(item.quantitativo), item.unidade or "")
        for item_id, item in eap.items()
    }
    if canonical.atividades:
        totals: dict[str, Fraction] = {item_id: Fraction(0) for item_id in eap}
        fractions: dict[str, Fraction] = {item_id: Fraction(0) for item_id in eap}
        children: dict[str, int] = {item_id: 0 for item_id in eap}
        seen: set[str] = set()
        for activity in canonical.atividades:
            if (
                activity.atividade_id in seen
                or activity.eap_item_id not in eap
                or activity.cpu_id != eap[activity.eap_item_id].cpu_id
            ):
                raise ValueError("duplicate subactivity, missing EAP mapping or CPU mismatch")
            seen.add(activity.atividade_id)
            parent = activity.eap_item_id
            scope, _ = scopes[parent]
            fraction = _exact_q(activity.fracao_quantitativo)
            actual_q = _exact_q(activity.quantitativo_atividade)
            # Skill01's explicit decomposition rounds each child to 6 decimal
            # places. Its default single child instead copies the full Q.
            # Accept only actual Skill01 producer output or an exact fraction
            # calculation; never widen the parent weekly-physical-Q tolerance.
            producer_q = Fraction(str(round(
                activity.fracao_quantitativo * eap[parent].quantitativo, 6
            )))
            exact_q = scope * fraction
            if (
                abs(actual_q - producer_q) > _scope_tolerance(scope)
                and abs(actual_q - exact_q) > _scope_tolerance(scope)
            ):
                raise ValueError("Skill01 subactivity quantity violates producer rounding")
            totals[parent] += actual_q
            fractions[parent] += fraction
            children[parent] += 1
        for item_id, (scope, _) in scopes.items():
            # Independent per-child checks make the sum-of-rounding tolerance
            # safe: an arbitrary missing/forged quantity cannot exploit it.
            producer_tolerance = children[item_id] * _CHILD_ROUNDING_ERROR
            if (
                not totals[item_id]
                or abs(totals[item_id] - scope)
                > producer_tolerance + _scope_tolerance(scope)
                or abs(fractions[item_id] - 1) > _REL_SCOPE_TOLERANCE
            ):
                raise ValueError("Skill01 subactivity scope/fractions do not close parent EAP")
    return scopes



def build_activity_goods_from_catalog(
    canonical: CanonicalModel,
    catalogo: Mapping[str, object],
) -> ActivityGoods:
    """Build a fail-closed P18 physical BOM mapping from the real catalog.

    Only CPU.composicao_itens MATERIAL/DIESEL/COMBUSTIVEL rows are treated as
    per-delivered-unit physical consumption. The good's unit/price/source come
    from the matching Insumo. Hourly MaterialEquipe or equipment fuel estimates
    are deliberately not converted into purchases here: they need matched
    observed operating-hour evidence. Internally generated materials likewise
    require a producer-consumer transfer, not an acquisition posting.
    """
    if not isinstance(canonical, CanonicalModel) or not isinstance(catalogo, Mapping):
        raise ValueError("typed canonical and catalog mapping are required")
    scopes = _activity_scope_units(canonical)
    schedule = canonical.cronograma
    if schedule is None or not schedule.is_feasible or not schedule.scheduled_activities:
        raise ValueError("a feasible, nonempty Skill04 schedule is required")

    activity_ids = [activity.activity_id for activity in schedule.scheduled_activities]
    if len(set(activity_ids)) != len(activity_ids) or set(activity_ids) != set(scopes):
        raise ValueError("Skill04 schedule and EAP activity identities must agree")

    raw_cpus = catalogo.get("cpus")
    raw_insumos = catalogo.get("insumos")
    if (
        not isinstance(raw_cpus, Sequence)
        or isinstance(raw_cpus, (str, bytes))
        or not isinstance(raw_insumos, Sequence)
        or isinstance(raw_insumos, (str, bytes))
    ):
        raise ValueError("catalog CPUs and insumos must be explicit sequences")

    def _index(rows: Sequence[object], key: str, label: str) -> dict[str, Mapping[str, object]]:
        indexed: dict[str, Mapping[str, object]] = {}
        for raw in rows:
            if not isinstance(raw, Mapping):
                raise ValueError(f"{label} catalog row must be a mapping")
            identity = raw.get(key)
            if not isinstance(identity, str) or not identity.strip() or identity in indexed:
                raise ValueError(f"{label} catalog identity is missing or duplicated")
            indexed[identity] = raw
        return indexed

    cpus = _index(raw_cpus, "codigo", "CPU")
    insumos = _index(raw_insumos, "codigo", "Insumo")
    eap = {item.item_id: item for item in canonical.eap}
    goods_by_activity: dict[str, dict[str, tuple[PhysicallyPricedGood, PricedCategory]]] = {}

    for activity_id in activity_ids:
        item = eap[activity_id]
        cpu = cpus.get(item.cpu_id)
        if cpu is None:
            raise ValueError(f"{activity_id}: missing CPU catalog source {item.cpu_id!r}")
        cpu_unit_raw = cpu.get("unidade")
        if not isinstance(cpu_unit_raw, str) or not cpu_unit_raw.strip():
            raise ValueError(f"{activity_id}: CPU output unit is missing")
        try:
            cpu_unit = normalize_unidade(cpu_unit_raw)
            eap_unit = normalize_unidade(item.unidade or "")
            # The coefficient is per CPU output unit. A dimension-changing
            # CPU/EAP match would corrupt the calculated physical consumption.
            convert_physical(Fraction(1), eap_unit, cpu_unit)
        except ValueError as exc:
            raise ValueError(f"{activity_id}: incompatible or missing CPU/EAP unit") from exc

        composition = cpu.get("composicao_itens")
        if not isinstance(composition, Sequence) or isinstance(composition, (str, bytes)):
            raise ValueError(f"{activity_id}: explicit CPU.composicao_itens is required")

        activity_goods: dict[str, tuple[PhysicallyPricedGood, PricedCategory]] = {}
        for line in composition:
            if not isinstance(line, Mapping):
                raise ValueError(f"{activity_id}: malformed CPU composition row")
            category_raw = line.get("categoria_custo")
            if category_raw in ("MAO_OBRA", "EQUIPAMENTO"):
                continue
            if category_raw not in ("MATERIAL", "DIESEL", "COMBUSTIVEL"):
                raise ValueError(f"{activity_id}: unsupported composition category {category_raw!r}")

            good_id = line.get("insumo_id")
            if not isinstance(good_id, str) or not good_id.strip():
                raise ValueError(f"{activity_id}: consumable row has no insumo_id")
            if good_id in activity_goods:
                raise ValueError(f"{activity_id}/{good_id}: duplicate physical BOM good")
            insumo = insumos.get(good_id)
            if insumo is None:
                raise ValueError(f"{activity_id}/{good_id}: missing physical Insumo catalog record")
            if insumo.get("tipo") != "MATERIAL":
                raise ValueError(f"{activity_id}/{good_id}: consumable Insumo type must be MATERIAL")
            if insumo.get("origem_material") == "GERACAO_INTERNA":
                raise ValueError(
                    f"{activity_id}/{good_id}: internally generated material requires "
                    "producer-consumer transfer evidence, not an acquisition posting"
                )
            if insumo.get("origem_material") != "AQUISICAO_EXTERNA":
                raise ValueError(f"{activity_id}/{good_id}: acquisition provenance is missing")
            price_source = insumo.get("fonte_preco")
            if not isinstance(price_source, str) or not price_source.strip():
                raise ValueError(f"{activity_id}/{good_id}: unit-price provenance is missing")
            price_reference_date = insumo.get("data_referencia_preco")
            if price_reference_date is not None and (
                not isinstance(price_reference_date, str) or not price_reference_date.strip()
            ):
                raise ValueError(f"{activity_id}/{good_id}: invalid price reference date")

            good_unit_raw = insumo.get("unidade")
            if not isinstance(good_unit_raw, str) or not good_unit_raw.strip():
                raise ValueError(f"{activity_id}/{good_id}: physical good unit is missing")
            try:
                good_unit = normalize_unidade(good_unit_raw)
                declared_line_unit = line.get("unidade")
                if declared_line_unit is not None:
                    if not isinstance(declared_line_unit, str):
                        raise ValueError("composition unit must be text")
                    if normalize_unidade(declared_line_unit) != good_unit:
                        raise ValueError("composition unit differs from Insumo physical unit")
                coefficient = _exact_q(line.get("coeficiente"))
                price = _exact_q(insumo.get("preco_unitario"))
            except ValueError as exc:
                raise ValueError(f"{activity_id}/{good_id}: invalid physical rate/price/unit") from exc
            if coefficient <= 0:
                raise ValueError(f"{activity_id}/{good_id}: physical BOM coefficient must be positive")

            basis = PhysicalConsumptionRate(
                good_id=good_id,
                physical_rate=coefficient,
                good_unit=good_unit,
                basis=ConsumptionBasis.PER_DELIVERED_UNIT,
                activity_unit=cpu_unit,
            )
            category: PricedCategory = "MAT" if category_raw == "MATERIAL" else "COMB"
            activity_goods[good_id] = (
                PhysicallyPricedGood(
                    basis,
                    price,
                    good_unit,
                    price_source=price_source,
                    price_reference_date=price_reference_date,
                ),
                category,
            )

        if not activity_goods:
            raise ValueError(
                f"{activity_id}: no explicit physical per-delivered-unit consumable BOM; "
                "hourly rates require separate observed operating-hour evidence"
            )
        goods_by_activity[activity_id] = activity_goods

    return goods_by_activity


def _scheduled_week_keys(canonical: CanonicalModel, start: int, end: int, duration: int) -> set[str]:
    """Rebuild exact ISO coverage from the same project-start offset as Skill04.

    Require zero-output weeks within the materialized interval, since hourly
    costs/observations cannot be dropped by removing a zero-Q dictionary key.
    """
    if (
        type(start) is not int or type(end) is not int or type(duration) is not int
        or start < 0 or end < start or duration < end - start + 1
        or end - start > 5200
    ):
        raise ValueError("invalid Skill04 scheduled week interval")
    base_date = canonical.projeto.data_inicio
    monday = base_date - timedelta(days=base_date.weekday())
    weeks: set[str] = set()
    for offset in range(start, end + 1):
        year, week, _ = (monday + timedelta(weeks=offset)).isocalendar()
        weeks.add(f"{year}-W{week:02d}")
    return weeks


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

    # Rates are activity-specific even when several activities consume the
    # same catalog good; e.g. each CPU may declare a different L/h of diesel.
    # Prices/category remain shared and must agree for a given good identity.
    goods: dict[tuple[str, str], tuple[PhysicallyPricedGood, PricedCategory]] = {}
    shared_good_prices: dict[str, tuple[Fraction, str, PricedCategory, str | None, str | None]] = {}
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
            price_identity = (
                priced.price_per_unit,
                priced.price_unit,
                category,
                priced.price_source,
                priced.price_reference_date,
            )
            previous_price = shared_good_prices.get(good_id)
            if previous_price is not None and previous_price != price_identity:
                raise ValueError("conflicting physical price/category for shared good")
            shared_good_prices[good_id] = price_identity
            goods[(activity_id, good_id)] = declaration

        weekly_q = Fraction(0)
        if not activity.distribuicao_semanal:
            raise ValueError("Skill04 requires a nonempty physical weekly distribution")
        productive_weeks = _scheduled_week_keys(
            canonical, activity.start_week, activity.end_week, activity.duration_weeks
        )
        # The final assembler bounds start/end by *positive* production, but
        # MANUAL Skill04 retains project-wide zero-output leading/trailing
        # weeks. Allow these only when the entire materialized weekly interval
        # is contiguous. Keep their explicit hourly observations mandatory.
        base_date = canonical.projeto.data_inicio
        project_monday = base_date - timedelta(days=base_date.weekday())
        week_offsets: dict[str, int] = {}
        for week in activity.distribuicao_semanal:
            _iso_week(week)
            monday = date.fromisocalendar(int(week[:4]), int(week[6:]), 1)
            offset = (monday - project_monday).days // 7
            if offset < 0 or offset > 5200:
                raise ValueError("Skill04 physical week is outside project calendar")
            week_offsets[week] = offset
        complete_weeks = _scheduled_week_keys(
            canonical, min(week_offsets.values()), max(week_offsets.values()),
            max(week_offsets.values()) - min(week_offsets.values()) + 1,
        )
        if (
            not productive_weeks.issubset(complete_weeks)
            or set(activity.distribuicao_semanal) != complete_weeks
        ):
            raise ValueError("Skill04 weekly distribution does not cover scheduled interval")
        positive_weeks = [
            week for week, row in activity.distribuicao_semanal.items()
            if _exact_q(row.qtd_executada) > 0
        ]
        if positive_weeks and (
            min(week_offsets[w] for w in positive_weeks) != activity.start_week
            or max(week_offsets[w] for w in positive_weeks) != activity.end_week
        ):
            raise ValueError("Skill04 productive bounds disagree with weekly physical Q")
        for week, row in sorted(activity.distribuicao_semanal.items()):
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
        # A fixed absolute epsilon alone could certify an entirely missing
        # micro-activity. Require both bounded absolute and relative error.
        tolerance = _scope_tolerance(expected_q)
        if abs(weekly_q - expected_q) > tolerance:
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
