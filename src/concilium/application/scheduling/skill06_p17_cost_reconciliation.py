"""P17-C: exact, read-only reconciliation of Skill05 K and Skill06 activity costs.

This sidecar audits existing Skill06 activity-cost diagnostics against active
per-activity costs reconstructed from P16's exact instance witness and the P17
exclusive ledger. It never rewrites sale, margin, or legacy costs and never
authorizes PROJECT_GO.
"""
from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from typing import Literal, cast

from concilium.application.scheduling.contractual_cost_ledger import (
    CostPosting,
    ExclusiveCostLedger,
    PostingNature,
)
from concilium.application.scheduling.skill06_p18c_consumption_preview import (
    build_skill05_exact_pool_ledger,
)
from concilium.domain.models.canonical import CanonicalModel

_CURRENCY_SOURCE = "catalog_metadata.json"
_SCHEMA = "concilium.p18.skill06-preview.v1"
_AUTHORITY = "P18_SKILL06_READ_ONLY_PREVIEW_NOT_PROJECT_GO"
_CENT = Fraction(1, 100)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an explicit mapping")
    return value


def _rational(value: object, label: str) -> Fraction:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be an exact rational string")
    try:
        amount = Fraction(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError(f"{label} must be an exact rational string") from exc
    if amount < 0:
        raise ValueError(f"{label} must be nonnegative")
    return amount


def _legacy_money(value: object, label: str) -> Fraction:
    """Preserve the decimal rendering of Skill06's legacy float diagnostics."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise ValueError(f"{label} must be a finite nonnegative monetary value")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a finite nonnegative monetary value") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"{label} must be a finite nonnegative monetary value")
    return Fraction(amount)


def _ledger_from_preview(preview: Mapping[str, object]) -> ExclusiveCostLedger:
    if preview.get("schema") != _SCHEMA or preview.get("authority") != _AUTHORITY:
        raise ValueError("unsupported P18 preview schema or authority")
    if preview.get("project_go_authorized") is not False:
        raise ValueError("P18 preview cannot authorize PROJECT_GO")
    if preview.get("currency_source") != _CURRENCY_SOURCE:
        raise ValueError("P18 preview currency provenance is missing")
    currency = preview.get("currency")
    if (
        not isinstance(currency, str)
        or not currency.isascii()
        or not currency.isalpha()
        or len(currency) != 3
        or currency != currency.upper()
    ):
        raise ValueError("P18 preview currency is invalid")

    raw_postings = preview.get("exclusive_postings")
    if not isinstance(raw_postings, list):
        raise ValueError("P18 preview must contain exclusive postings")
    postings: list[CostPosting] = []
    for index, raw in enumerate(raw_postings):
        row = _mapping(raw, f"preview posting {index}")
        raw_event = row.get("event_id")
        if (
            not isinstance(raw_event, list)
            or not raw_event
            or any(not isinstance(segment, str) or not segment for segment in raw_event)
        ):
            raise ValueError(f"preview posting {index} has invalid event identity")
        try:
            nature = PostingNature(row.get("nature"))
        except (ValueError, TypeError) as exc:
            raise ValueError(f"preview posting {index} has invalid posting nature") from exc
        category = row.get("category")
        if category not in ("MO", "EQ", "MAT", "COMB", "IND"):
            raise ValueError(f"preview posting {index} has invalid financial category")
        source = row.get("source")
        week = row.get("week")
        if not isinstance(source, str) or not source.strip():
            raise ValueError(f"preview posting {index} has no source identity")
        if week is not None and not isinstance(week, str):
            raise ValueError(f"preview posting {index} has invalid week")
        postings.append(CostPosting(
            event_id=tuple(raw_event),
            nature=nature,
            category=cast(Literal["MO", "EQ", "MAT", "COMB", "IND"], category),
            amount=_rational(row.get("amount"), f"preview posting {index} amount"),
            source=source,
            week=week,
        ))
    ledger = ExclusiveCostLedger(tuple(postings))
    totals = _mapping(preview.get("totals"), "P18 preview totals")
    expected = {
        "contractual_k": ledger.contractual_k,
        "consumable_v": ledger.consumable_v,
        "indirect": ledger.indirect,
        "direct": ledger.direct,
        "total": ledger.total,
    }
    for field, actual in expected.items():
        if _rational(totals.get(field), f"preview total {field}") != actual:
            raise ValueError(f"P18 preview total {field} does not reconstruct from exclusive postings")
    return ledger


def _activity_witness_costs(canonical: CanonicalModel) -> dict[str, Fraction]:
    """Allocate exact active K to the activity owning each active resource-week."""
    result: dict[str, Fraction] = {}
    for contract in canonical.contratos_recurso:
        witness = _mapping(
            contract.p16_global_assignment,
            f"{contract.tipo_id}: missing exact P16 witness",
        )
        weeks = witness.get("calendar_weeks")
        tariff = _mapping(witness.get("tariff"), f"{contract.tipo_id}: P16 tariff")
        chains = witness.get("chains")
        demand_by_activity = _mapping(
            witness.get("demand_by_activity"),
            f"{contract.tipo_id}: P16 activity demand",
        )
        if not isinstance(weeks, list) or not weeks or not isinstance(chains, list):
            raise ValueError(f"{contract.tipo_id}: P16 calendar/chains are missing")
        active_rate = _rational(tariff.get("active_week"), f"{contract.tipo_id}: active tariff")
        for activity_id, series in demand_by_activity.items():
            if not isinstance(activity_id, str) or not activity_id.strip():
                raise ValueError("P16 activity identity must be nonempty text")
            if not isinstance(series, list) or len(series) != len(weeks):
                raise ValueError(f"{contract.tipo_id}/{activity_id}: demand does not cover calendar")
            if any(type(value) is not int or value < 0 for value in series):
                raise ValueError(f"{contract.tipo_id}/{activity_id}: demand must be nonnegative integers")
            result.setdefault(activity_id, Fraction(0))
        for chain in chains:
            row = _mapping(chain, f"{contract.tipo_id}: P16 chain")
            active_indices = row.get("active_week_indices")
            assignment = _mapping(row.get("activity_by_week"), "P16 activity-by-week assignment")
            if not isinstance(active_indices, list):
                raise ValueError(f"{contract.tipo_id}: active-week indices are missing")
            for index in active_indices:
                if type(index) is not int or not 0 <= index < len(weeks):
                    raise ValueError(f"{contract.tipo_id}: invalid active-week index")
                activity_id = assignment.get(weeks[index])
                if not isinstance(activity_id, str) or activity_id not in result:
                    raise ValueError(f"{contract.tipo_id}: active week has no owned activity")
                result[activity_id] += active_rate
    return result


def _activity_lifecycle_allocations(
    canonical: CanonicalModel,
) -> tuple[dict[str, Fraction], Fraction]:
    """Allocate non-active P16 costs using Skill05's persisted item partitions.

    Skill06's legacy MO+EQ diagnostic is built from persisted instancial cost
    partitions. Those partitions include standby MO/EQ and MOB/DEMOB (folded into
    EQ by the existing ADR-085 adapter). Subtract their exact P16 amounts, allocated
    by the same persisted partition weights, before comparing activity diagnostics
    to the active-only K witness. This is read-only and does not rewrite legacy finance.
    """
    allocated: dict[str, Fraction] = {}
    nonactive_total = Fraction(0)
    for contract in canonical.contratos_recurso:
        witness = _mapping(
            contract.p16_global_assignment,
            f"{contract.tipo_id}: missing exact P16 witness",
        )
        costs = _mapping(witness.get("costs"), f"{contract.tipo_id}: P16 costs")
        standby = _rational(costs.get("standby"), f"{contract.tipo_id}: P16 standby cost")
        mobility = _rational(costs.get("mobility"), f"{contract.tipo_id}: P16 mobility cost")
        nonactive = standby + mobility
        nonactive_total += nonactive

        partitions = getattr(contract, "particao_por_item", None)
        if not isinstance(partitions, list):
            raise ValueError(f"{contract.tipo_id}: persisted activity cost partitions are missing")
        weights: dict[str, Fraction] = {}
        for part in partitions:
            activity_id = getattr(part, "item_id", None)
            if not isinstance(activity_id, str) or not activity_id.strip():
                raise ValueError(f"{contract.tipo_id}: invalid activity partition identity")
            if activity_id in weights:
                raise ValueError(f"{contract.tipo_id}/{activity_id}: duplicate activity cost partition")
            weights[activity_id] = _legacy_money(
                getattr(part, "custo_total_particionado", None),
                f"{contract.tipo_id}/{activity_id}.custo_total_particionado",
            )
        partition_total = sum(weights.values(), Fraction(0))
        if nonactive == 0:
            continue
        if partition_total <= 0:
            raise ValueError(
                f"{contract.tipo_id}: standby/MOB/DEMOB costs cannot be allocated without positive partitions"
            )
        witness_total = _rational(costs.get("pool_total"), f"{contract.tipo_id}: P16 pool total")
        if abs(partition_total - witness_total) > _CENT:
            raise ValueError(
                f"{contract.tipo_id}: activity partitions do not reconcile to exact P16 pool total"
            )
        for activity_id, weight in weights.items():
            if weight > 0:
                allocated[activity_id] = allocated.get(activity_id, Fraction(0)) + nonactive * weight / partition_total
    return allocated, nonactive_total


def _activity_diagnostic_costs(canonical: CanonicalModel) -> dict[str, Fraction]:
    """Sum weekly pre-BDI MO+EQ diagnostics; lifecycle costs may still be folded in."""
    if not canonical.custos_atividades:
        raise ValueError("Skill06 has no activity-cost diagnostics to reconcile")
    result: dict[str, Fraction] = {}
    for activity in canonical.custos_atividades:
        activity_id = activity.atividade_id
        if not isinstance(activity_id, str) or not activity_id.strip() or activity_id in result:
            raise ValueError("Skill06 activity-cost identities are missing or duplicated")
        weeks: set[str] = set()
        amount = Fraction(0)
        if not activity.custos_diretos_semanais:
            raise ValueError(f"{activity_id}: weekly contractual-cost diagnostics are missing")
        for row in activity.custos_diretos_semanais:
            week = row.semana_iso
            if not isinstance(week, str) or not week or week in weeks:
                raise ValueError(f"{activity_id}: duplicate or missing weekly cost identity")
            weeks.add(week)
            contractual = _legacy_money(row.custo_contratual, f"{activity_id}/{week}.custo_contratual")
            components = (
                _legacy_money(row.custo_mao_obra, f"{activity_id}/{week}.custo_mao_obra")
                + _legacy_money(row.custo_equipamentos, f"{activity_id}/{week}.custo_equipamentos")
            )
            if abs(contractual - components) > _CENT:
                raise ValueError(f"{activity_id}/{week}: MO+EQ diagnostic does not equal its components")
            amount += contractual
        result[activity_id] = amount
    return result


def build_skill06_p17_reconciliation(canonical: CanonicalModel) -> dict[str, object]:
    """Reconcile exact pool K, activity K diagnostics and once-only physical V."""
    if not isinstance(canonical, CanonicalModel):
        raise ValueError("P17-C requires a typed canonical project")
    preview = _mapping(canonical.p18_consumption_preview, "P18 consumption preview")
    preview_ledger = _ledger_from_preview(preview)
    pool = build_skill05_exact_pool_ledger(canonical)
    if not canonical.contratos_recurso:
        raise ValueError("P17-C requires exact Skill05 pool contracts")
    preview_currency = preview.get("currency")
    for contract in canonical.contratos_recurso:
        witness = _mapping(
            contract.p16_global_assignment,
            f"{contract.tipo_id}: missing exact P16 witness",
        )
        if witness.get("currency") != preview_currency:
            raise ValueError(f"{contract.tipo_id}: P18 preview currency differs from exact P16 witness")
    pool_ids = {posting.event_id: posting for posting in pool.postings}
    preview_ids = {posting.event_id: posting for posting in preview_ledger.postings}
    if any(preview_ids.get(event_id) != posting for event_id, posting in pool_ids.items()):
        raise ValueError("P18 preview does not preserve the exact Skill05 pool postings")
    if pool.contractual_k != preview_ledger.contractual_k:
        raise ValueError("P18 preview contractual K differs from reconstructed Skill05 pool")
    if pool.indirect != preview_ledger.indirect:
        raise ValueError("P18 preview MOB/DEMOB ledger differs from reconstructed Skill05 pool")

    witness_costs = _activity_witness_costs(canonical)
    lifecycle_allocations, lifecycle_total = _activity_lifecycle_allocations(canonical)
    diagnostic_costs = _activity_diagnostic_costs(canonical)
    expected_ids = set(witness_costs) | set(lifecycle_allocations)
    missing = sorted(expected_ids - diagnostic_costs.keys())
    unowned = sorted(
        activity_id for activity_id, amount in diagnostic_costs.items()
        if amount > 0 and activity_id not in expected_ids
    )
    activity_rows = []
    reasons: list[str] = []
    if missing:
        reasons.append("missing Skill06 activity-cost rows: " + ", ".join(missing))
    if unowned:
        reasons.append("activity MO+EQ diagnostics absent from the P16 witness/partitions: " + ", ".join(unowned))
    for activity_id in sorted(set(witness_costs) | set(lifecycle_allocations) | set(diagnostic_costs)):
        active_witness = witness_costs.get(activity_id, Fraction(0))
        allocated_nonactive = lifecycle_allocations.get(activity_id, Fraction(0))
        diagnostic_mo_eq = diagnostic_costs.get(activity_id, Fraction(0))
        active_diagnostic = diagnostic_mo_eq - allocated_nonactive
        delta = active_diagnostic - active_witness
        if active_diagnostic < -_CENT:
            reasons.append(
                f"{activity_id}: allocated standby/MOB/DEMOB exceeds the Skill06 MO+EQ diagnostic"
            )
        if abs(delta) > _CENT:
            reasons.append(
                f"{activity_id}: active MO+EQ diagnostic after lifecycle allocation differs from exact P16 active K by {delta}"
            )
        activity_rows.append({
            "activity_id": activity_id,
            "exact_p16_active_k": str(active_witness),
            "allocated_p16_standby_and_mobility": str(allocated_nonactive),
            "skill06_diagnostic_mo_eq": str(diagnostic_mo_eq),
            "skill06_active_k_diagnostic": str(active_diagnostic),
            "delta_active_diagnostic_minus_p16": str(delta),
        })

    active_k = pool.sum_natures(PostingNature.ACTIVE)
    idle_k = pool.sum_natures(PostingNature.IDLE)
    pool_k = pool.contractual_k
    activity_diagnostic_mo_eq = sum(diagnostic_costs.values(), Fraction(0))
    activity_active_diagnostic = activity_diagnostic_mo_eq - lifecycle_total
    p16_activity_active_k = sum(witness_costs.values(), Fraction(0))
    lifecycle_allocation_closes = sum(lifecycle_allocations.values(), Fraction(0)) == lifecycle_total
    if p16_activity_active_k != active_k:
        reasons.append("per-activity P16 active K does not close to active pool K")
    if not lifecycle_allocation_closes:
        reasons.append("allocated standby/MOB/DEMOB does not close to exact P16 lifecycle costs")
    if activity_active_diagnostic > pool_k + _CENT:
        reasons.append("activity active-K diagnostic exceeds contractual pool K after lifecycle allocation")
    totals = {
        "pool_active_k": str(active_k),
        "pool_idle_k": str(idle_k),
        "pool_contractual_k": str(pool_k),
        "p16_activity_active_k": str(p16_activity_active_k),
        "allocated_standby_and_mobility": str(lifecycle_total),
        "skill06_activity_diagnostic_mo_eq": str(activity_diagnostic_mo_eq),
        "skill06_active_k_diagnostic": str(activity_active_diagnostic),
        "pool_k_minus_activity_active_k_diagnostic": str(pool_k - activity_active_diagnostic),
        "physical_consumable_v": str(preview_ledger.consumable_v),
        "indirect_mob_demob": str(preview_ledger.indirect),
        "direct_k_plus_v": str(preview_ledger.direct),
        "total": str(preview_ledger.total),
    }
    return {
        "schema": "concilium.p17.skill06-reconciliation.v1",
        "authority": "P17_SKILL06_READ_ONLY_RECONCILIATION_NOT_PROJECT_GO",
        "project_go_authorized": False,
        "currency": preview.get("currency"),
        "currency_source": _CURRENCY_SOURCE,
        "status": "RECONCILED" if not reasons else "NOGO",
        "tolerance": str(_CENT),
        "reasons": reasons,
        "invariants": {
            "activity_assignment_closes_to_active_pool": (
                p16_activity_active_k == active_k
            ),
            "lifecycle_allocation_closes": lifecycle_allocation_closes,
            "activity_diagnostics_match_p16_active_k": (
                not missing
                and not unowned
                and all(
                    abs(
                        diagnostic_costs.get(activity_id, Fraction(0))
                        - lifecycle_allocations.get(activity_id, Fraction(0))
                        - witness_costs.get(activity_id, Fraction(0))
                    ) <= _CENT
                    for activity_id in expected_ids
                )
            ),
            "pool_covers_activity_k": activity_active_diagnostic <= pool_k + _CENT,
            "consumables_are_separate_from_k": all(
                posting.nature == PostingNature.ACQUISITION
                or posting.category not in ("MAT", "COMB")
                for posting in preview_ledger.postings
            ),
            "exclusive_posting_identity": len(preview_ids) == len(preview_ledger.postings),
        },
        "totals": totals,
        "activity_costs": activity_rows,
        "exclusive_postings": [
            {
                "event_id": list(post.event_id),
                "nature": post.nature.value,
                "category": post.category,
                "amount": str(post.amount),
                "source": post.source,
                "week": post.week,
            }
            for post in preview_ledger.postings
        ],
    }
