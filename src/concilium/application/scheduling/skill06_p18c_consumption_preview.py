"""P18-C3: opt-in Skill05 exact pool witness -> Skill06 physical preview.

This adapter reconstructs the exclusive P17 ledger from the persisted P16-E
witness, verifies the witness by rebuilding its postings, then composes the
read-only P18-C1/C2 preview. It never mutates legacy price/margin fields and
never emits PROJECT_GO.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from fractions import Fraction
from typing import Any

from concilium.application.scheduling.contractual_cost_ledger import (
    ContractCategory,
    ExclusiveCostLedger,
    PostingNature,
    book_exact_pool,
)
from concilium.application.scheduling.resource_level_contracts import (
    ExactPoolResult,
    InstanceChain,
    ResourceContractLedger,
    ResourceTariff,
    exact_money,
)
from concilium.application.scheduling.skill04_consumption_preview import (
    ActivityGoods,
    P18CConsumptionPreview,
    book_skill04_planned_consumption_preview,
    build_activity_goods_from_catalog,
)
from concilium.domain.models.canonical import CanonicalModel, RecursoContrato
from concilium.domain.services.planning.week_sequence import enumerar_semanas


_EXPECTED_PROOF_SCOPE = "EXACT_GLOBAL_INSTANCE_ASSIGNMENT_CONDITIONAL_ON_FIXED_PHYSICAL_DEMAND"
_EXPECTED_STATUS = "EXACT_CONDITIONAL_ON_FIXED_PHYSICAL_DEMAND"


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an explicit mapping")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be nonempty text")
    return value


def _integer(value: object, label: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return value


def _nonnegative_fraction(value: object, label: str) -> Fraction:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be an exact rational string")
    try:
        parsed = Fraction(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError(f"{label} must be an exact rational string") from exc
    if parsed < 0:
        raise ValueError(f"{label} must be nonnegative")
    return parsed


def _calendar(value: object, contract: RecursoContrato) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{contract.tipo_id}: P16 calendar must be a nonempty list")
    weeks = tuple(_text(week, "calendar week") for week in value)
    if len(set(weeks)) != len(weeks):
        raise ValueError(f"{contract.tipo_id}: duplicate calendar week")
    if weeks != tuple(enumerar_semanas(contract.semana_inicio, contract.semana_fim)):
        raise ValueError(f"{contract.tipo_id}: P16 calendar differs from the declared contract span")
    if contract.semanas_contrato != len(weeks):
        raise ValueError(f"{contract.tipo_id}: contract duration differs from P16 calendar")
    # enumerar_semanas preserves formats but does not fully validate malformed
    # ISO keys; validate them independently before using them as ledger weeks.
    for week in weeks:
        if "-W" in week:
            try:
                year, iso_week = week.split("-W")
                date.fromisocalendar(int(year), int(iso_week), 1)
            except (ValueError, TypeError) as exc:
                raise ValueError(f"{contract.tipo_id}: invalid ISO calendar week {week!r}") from exc
        elif not (week.startswith("S") and week[1:].isdigit()):
            raise ValueError(f"{contract.tipo_id}: unsupported weekly key {week!r}")
    return weeks


def _count_series(value: object, label: str, horizon: int) -> tuple[int, ...]:
    if not isinstance(value, list) or len(value) != horizon:
        raise ValueError(f"{label} must cover the full physical calendar")
    return tuple(_integer(item, label) for item in value)


def _serialized_postings(ledger: ExclusiveCostLedger) -> list[dict[str, object]]:
    return [
        {
            "event_id": list(post.event_id),
            "nature": post.nature.value,
            "category": post.category,
            "amount": str(post.amount),
            "source": post.source,
            "week": post.week,
        }
        for post in ledger.postings
    ]


def _contract_witness_ledger(contract: RecursoContrato) -> tuple[ExclusiveCostLedger, str]:
    raw = getattr(contract, "p16_global_assignment", None)
    witness = _mapping(raw, f"{contract.tipo_id}: missing exact P16-E witness")
    if witness.get("schema") != "p16-global-instance-assignment/v1":
        raise ValueError(f"{contract.tipo_id}: unsupported P16 witness schema")
    if witness.get("proof_scope") != _EXPECTED_PROOF_SCOPE or witness.get("status") != _EXPECTED_STATUS:
        raise ValueError(f"{contract.tipo_id}: P16 witness does not prove exact fixed-demand assignment")
    if witness.get("is_project_go_certificate") is not False:
        raise ValueError(f"{contract.tipo_id}: P16 witness cannot authorize PROJECT_GO")
    if witness.get("legacy_financial_projection_overridden") is not False:
        raise ValueError(f"{contract.tipo_id}: P16 witness cannot override legacy financial projection")

    resource_type = _text(witness.get("resource_type"), "P16 resource_type")
    contract_id = _text(witness.get("contract_id"), "P16 contract_id")
    # Validate tariff provenance here; the canonical sidecar serializes this
    # stable source_id separately from the reconstructed posting ledger.
    _text(witness.get("source_id"), "P16 tariff source_id")
    currency = _text(witness.get("currency"), "P16 currency")
    raw_category = witness.get("category")
    if raw_category == "MO":
        category: ContractCategory = "MO"
    elif raw_category == "EQ":
        category = "EQ"
    else:
        raise ValueError(f"{resource_type}: exact pool requires homogeneous MO/EQ category")
    if (
        resource_type != contract.tipo_id
        or contract_id != contract.contrato_id
        or currency != currency.upper()
        or len(currency) != 3
        or not currency.isalpha()
    ):
        raise ValueError(f"{contract.tipo_id}: P16 identity/currency differs from canonical contract")

    weeks = _calendar(witness.get("calendar_weeks"), contract)
    horizon = len(weeks)
    demand = _count_series(witness.get("demand"), "demand", horizon)
    presence = _count_series(witness.get("presence"), "presence", horizon)
    standby = _count_series(witness.get("standby"), "standby", horizon)
    if any(p != d + idle or p < d for p, d, idle in zip(presence, demand, standby, strict=True)):
        raise ValueError(f"{resource_type}: presence must equal physical demand plus standby")

    raw_activity_demand = _mapping(witness.get("demand_by_activity"), "demand_by_activity")
    if not raw_activity_demand:
        raise ValueError(f"{resource_type}: P16 witness has no per-activity demand")
    activity_demand = {
        _text(activity_id, "activity id"): _count_series(series, "activity demand", horizon)
        for activity_id, series in raw_activity_demand.items()
    }
    reconstructed_demand = tuple(
        sum(series[index] for series in activity_demand.values())
        for index in range(horizon)
    )
    if reconstructed_demand != demand:
        raise ValueError(f"{resource_type}: per-activity demand does not reconstruct aggregate demand")

    tariff_data = _mapping(witness.get("tariff"), "P16 tariff")
    declared_gap = _integer(tariff_data.get("max_idle_gap_declared"), "max_idle_gap_declared")
    feasible_gap = _integer(tariff_data.get("gap_max_viavel"), "gap_max_viavel")
    effective_gap = _integer(tariff_data.get("max_idle_gap_effective"), "max_idle_gap_effective")
    if effective_gap != min(declared_gap, feasible_gap):
        raise ValueError(f"{resource_type}: effective gap differs from the declared hard limits")
    tariff = ResourceTariff(
        active_week=exact_money(_text(tariff_data.get("active_week"), "active_week")),
        idle_week=exact_money(_text(tariff_data.get("idle_week"), "idle_week")),
        mobilize=exact_money(_text(tariff_data.get("mobilize"), "mobilize")),
        demobilize=exact_money(_text(tariff_data.get("demobilize"), "demobilize")),
        max_idle_gap=effective_gap,
    )

    raw_chains = witness.get("chains")
    if not isinstance(raw_chains, list):
        raise ValueError(f"{resource_type}: P16 chains must be a list")
    chains: list[InstanceChain] = []
    assigned_by_activity = {
        activity_id: [0] * horizon for activity_id in activity_demand
    }
    levels: set[int] = set()
    for raw_chain in raw_chains:
        row = _mapping(raw_chain, "P16 instance chain")
        level = _integer(row.get("instance_id"), "instance_id", minimum=1)
        start = _integer(row.get("start_index"), "start_index")
        end = _integer(row.get("end_exclusive_index"), "end_exclusive_index", minimum=1)
        active = _integer(row.get("active_weeks"), "active_weeks", minimum=1)
        idle = _integer(row.get("idle_weeks"), "idle_weeks")
        if (
            level in levels
            or level > contract.quantidade_contratada
            or not 0 <= start < end <= horizon
        ):
            raise ValueError(
                f"{resource_type}: duplicate, over-contracted or out-of-horizon instance chain"
            )
        levels.add(level)
        if row.get("start_week") != weeks[start] or row.get("end_week") != weeks[end - 1]:
            raise ValueError(f"{resource_type}: instance-chain week boundaries are forged")
        raw_active = row.get("active_week_indices")
        if not isinstance(raw_active, list):
            raise ValueError(f"{resource_type}: active_week_indices must be a list")
        active_indices = tuple(_integer(i, "active week index") for i in raw_active)
        if (
            not active_indices
            or tuple(sorted(set(active_indices))) != active_indices
            or any(i < start or i >= end for i in active_indices)
            or active_indices[0] != start
            or active_indices[-1] != end - 1
            or len(active_indices) != active
            or end - start - len(active_indices) != idle
            or row.get("active_weeks_iso") != [weeks[i] for i in active_indices]
        ):
            raise ValueError(f"{resource_type}: invalid active-week chain witness")
        activity_by_week = _mapping(row.get("activity_by_week"), "activity_by_week")
        expected_active_weeks = {weeks[i] for i in active_indices}
        if set(activity_by_week) != expected_active_weeks or any(
            not isinstance(activity, str) or not activity.strip()
            for activity in activity_by_week.values()
        ):
            raise ValueError(f"{resource_type}: activity assignment does not cover exact active weeks")
        for index in active_indices:
            activity_id = activity_by_week[weeks[index]]
            if activity_id not in assigned_by_activity:
                raise ValueError(
                    f"{resource_type}: chain assigns a week to an activity absent from P16 demand"
                )
            assigned_by_activity[activity_id][index] += 1
        chains.append(InstanceChain(
            resource_type=resource_type,
            level=level,
            start=start,
            end=end,
            active_weeks=active,
            idle_weeks=idle,
            active_week_indices=active_indices,
        ))

    if any(
        tuple(assigned_by_activity[activity_id]) != series
        for activity_id, series in activity_demand.items()
    ):
        raise ValueError(
            f"{resource_type}: instance-chain activity assignments do not reconstruct per-activity demand"
        )

    raw_costs = _mapping(witness.get("costs"), "P16 costs")
    active_cost = _nonnegative_fraction(raw_costs.get("active"), "active cost")
    standby_cost = _nonnegative_fraction(raw_costs.get("standby"), "standby cost")
    mobility_cost = _nonnegative_fraction(raw_costs.get("mobility"), "mobility cost")
    pool_total = _nonnegative_fraction(raw_costs.get("pool_total"), "pool total")
    physical = ResourceContractLedger(
        resource_type=resource_type,
        demand=demand,
        presence=presence,
        standby=standby,
        chains=tuple(chains),
        active_cost=active_cost,
        standby_cost=standby_cost,
        mobility_cost=mobility_cost,
    )
    pool = ExactPoolResult(
        calendar_weeks=weeks,
        ledgers=(physical,),
        proof_scope=_EXPECTED_PROOF_SCOPE,
    )
    try:
        booked = book_exact_pool(pool, {resource_type: tariff}, {resource_type: category})
    except ValueError as exc:
        # book_exact_pool validates the independent tariff-derived postings before
        # the later witness comparisons run. Surface a stable witness-integrity
        # diagnostic when persisted components reconcile to the same pool total
        # but disagree with those reconstructed postings; do not bypass the check.
        if "monetary ledger not reconciled to P16 exact pool" in str(exc):
            raise ValueError(
                f"{resource_type}: stored P16 cost components differ from reconstructed postings"
            ) from exc
        raise
    if pool.total != pool_total:
        raise ValueError(f"{resource_type}: persisted P16 pool total differs from exact components")
    rebuilt_active = sum(
        (post.amount for post in booked.postings if post.nature == PostingNature.ACTIVE),
        start=Fraction(0),
    )
    rebuilt_standby = sum(
        (post.amount for post in booked.postings if post.nature == PostingNature.IDLE),
        start=Fraction(0),
    )
    rebuilt_mobility = sum(
        (
            post.amount for post in booked.postings
            if post.nature in (PostingNature.MOBILIZATION, PostingNature.DEMOBILIZATION)
        ),
        start=Fraction(0),
    )
    if (active_cost, standby_cost, mobility_cost) != (
        rebuilt_active, rebuilt_standby, rebuilt_mobility
    ):
        raise ValueError(f"{resource_type}: stored P16 cost components differ from reconstructed postings")

    raw_ledger = _mapping(witness.get("exclusive_ledger"), "P16 exclusive ledger")
    expected_totals = {
        "contractual_k": booked.contractual_k,
        "consumable_v": booked.consumable_v,
        "indirect": booked.indirect,
        "direct": booked.direct,
        "total": booked.total,
    }
    for field, expected in expected_totals.items():
        if _nonnegative_fraction(raw_ledger.get(field), f"ledger {field}") != expected:
            raise ValueError(f"{resource_type}: persisted P16 ledger total {field} is forged")
    if booked.consumable_v != 0:
        raise ValueError(f"{resource_type}: contractual pool witness cannot include MAT/COMB")

    raw_postings = raw_ledger.get("postings")
    if raw_postings != _serialized_postings(booked):
        raise ValueError(f"{resource_type}: persisted P16 postings do not match the reconstructed exact ledger")
    if any(post.week not in weeks for post in booked.postings):
        raise ValueError(f"{resource_type}: ledger posting week lies outside the physical calendar")
    return booked, currency


def build_skill05_exact_pool_ledger(canonical: CanonicalModel) -> ExclusiveCostLedger:
    """Reconstruct a combined exact P17 ledger from all current Skill05 P16 witnesses."""
    if not isinstance(canonical, CanonicalModel):
        raise ValueError("typed canonical project is required")
    contracts = canonical.contratos_recurso
    if not isinstance(contracts, list):
        raise ValueError("canonical resource contracts must be a list")
    if not contracts:
        if canonical.recurso_pool or canonical.instancias_recurso:
            raise ValueError("physical pool/instances exist without a typed exact Skill05 contract")
        return ExclusiveCostLedger(())
    if any(not isinstance(contract, RecursoContrato) for contract in contracts):
        raise ValueError("all Skill05 contracts must be typed RecursoContrato instances")
    resource_types = [contract.tipo_id for contract in contracts]
    contract_ids = [contract.contrato_id for contract in contracts]
    if len(resource_types) != len(set(resource_types)) or len(contract_ids) != len(set(contract_ids)):
        raise ValueError("P18 requires one homogeneous, uniquely identified Skill05 contract per resource type")

    ledgers: list[ExclusiveCostLedger] = []
    currencies: set[str] = set()
    for contract in contracts:
        ledger, currency = _contract_witness_ledger(contract)
        ledgers.append(ledger)
        currencies.add(currency)
    if len(currencies) != 1:
        raise ValueError("P18 requires a common currency across the exact Skill05 pool")
    postings = tuple(post for ledger in ledgers for post in ledger.postings)
    combined = ExclusiveCostLedger(postings)
    if any(post.nature.value == "CONSUMABLE_ACQUISITION" for post in combined.postings):
        raise ValueError("Skill05 pool may not contain MAT/COMB acquisitions")
    return combined


def _validate_catalog_currency(
    canonical: CanonicalModel,
    catalogo: Mapping[str, object],
) -> str:
    """Read explicit price currency from the resolved catalog metadata."""
    currency = _text(catalogo.get("currency"), "catalog price currency")
    source = _text(catalogo.get("currency_source"), "catalog price currency source")
    if source != "catalog_metadata.json":
        raise ValueError("catalog currency must be sourced from catalog_metadata.json")
    if (
        currency != currency.upper()
        or len(currency) != 3
        or not currency.isascii()
        or not currency.isalpha()
    ):
        raise ValueError("catalog price currency must be an explicit uppercase three-letter code")
    witness_currencies: set[str] = set()
    for contract in canonical.contratos_recurso:
        witness = _mapping(contract.p16_global_assignment, f"{contract.tipo_id}: exact P16 witness")
        witness_currency = _text(witness.get("currency"), "P16 currency")
        if (
            witness_currency != witness_currency.upper()
            or len(witness_currency) != 3
            or not witness_currency.isascii()
            or not witness_currency.isalpha()
        ):
            raise ValueError(f"{contract.tipo_id}: invalid P16 witness currency")
        witness_currencies.add(witness_currency)
    if len(witness_currencies) > 1:
        raise ValueError("cannot reconcile pool contracts with different currencies")
    if witness_currencies and currency not in witness_currencies:
        raise ValueError("catalog price currency differs from the exact Skill05 pool currency")
    return currency


def _preview_record(
    preview: P18CConsumptionPreview,
    goods: ActivityGoods,
    canonical: CanonicalModel,
    currency: str,
) -> dict[str, object]:
    reconciliation = preview.reconciliation
    evidence_rows: list[dict[str, object]] = []
    for item in preview.consumption.evidence:
        good = goods.get(item.activity_id, {}).get(item.measure.good_id)
        if good is None:
            raise ValueError("physical preview evidence has no matching catalog good")
        priced, _category = good
        evidence_rows.append({
            "source_id": item.source_id,
            "kind": item.kind,
            "activity_id": item.activity_id,
            "good_id": item.measure.good_id,
            "week": item.week,
            "category": item.category,
            "physical_quantity": str(item.measure.physical_quantity),
            "physical_unit": item.measure.physical_unit,
            "priced_quantity": str(item.measure.priced_quantity),
            "price_unit": item.measure.price_unit,
            "unit_price": str(priced.price_per_unit),
            "exact_cost": str(item.measure.exact_cost),
            "price_source": item.price_source,
            "price_reference_date": item.price_reference_date,
        })
    pool_witnesses = []
    for contract in canonical.contratos_recurso:
        witness = _mapping(contract.p16_global_assignment, f"{contract.tipo_id}: exact P16 witness")
        pool_witnesses.append({
            "resource_type": contract.tipo_id,
            "contract_id": contract.contrato_id,
            "source_id": _text(witness.get("source_id"), "P16 tariff source_id"),
            "currency": _text(witness.get("currency"), "P16 currency"),
            "proof_scope": witness.get("proof_scope"),
            "status": witness.get("status"),
        })
    return {
        "schema": "concilium.p18.skill06-preview.v1",
        "authority": "P18_SKILL06_READ_ONLY_PREVIEW_NOT_PROJECT_GO",
        "project_go_authorized": False,
        "catalog_snapshot_id": canonical.projeto.snapshot_catalogo_id,
        "currency": currency,
        "currency_source": "catalog_metadata.json",
        "pool_witnesses": pool_witnesses,
        "consumption_authority": preview.consumption.authority,
        "reconciliation_authority": reconciliation.authority,
        "holding_evidence_present": reconciliation.holding_evidence_present,
        "totals": {
            "contractual_k": str(reconciliation.ledger.contractual_k),
            "consumable_v": str(reconciliation.ledger.consumable_v),
            "indirect": str(reconciliation.ledger.indirect),
            "direct": str(reconciliation.ledger.direct),
            "total": str(reconciliation.ledger.total),
        },
        "weekly_balances": [
            {
                "week": balance.week,
                "contractual_k": str(balance.contractual_k),
                "consumable_v": str(balance.consumable_v),
                "indirect": str(balance.indirect),
                "direct": str(balance.direct),
                "total": str(balance.total),
            }
            for balance in reconciliation.weeks
        ],
        "evidence": evidence_rows,
        "exclusive_postings": _serialized_postings(reconciliation.ledger),
    }


def build_p18_skill06_preview(
    canonical: CanonicalModel,
    catalogo: Mapping[str, object],
) -> dict[str, object]:
    """Build the opt-in P18 sidecar from final schedule, catalog and exact pool witness."""
    if not isinstance(catalogo, Mapping):
        raise ValueError("resolved catalog must be an explicit mapping")
    pool = build_skill05_exact_pool_ledger(canonical)
    currency = _validate_catalog_currency(canonical, catalogo)
    goods = build_activity_goods_from_catalog(canonical, catalogo)
    preview = book_skill04_planned_consumption_preview(canonical, pool, goods)
    return _preview_record(preview, goods, canonical, currency)
