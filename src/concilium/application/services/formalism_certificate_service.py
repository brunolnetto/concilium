"""P23-B/C: source-bound GO/NOGO evaluation and append-only certificate lifecycle.

The evaluator consumes the exact physical P15 witness, P16 assignment witnesses,
P17/P18/P19/P20 journals and P21 gates already produced by the pipeline. Missing
or legacy evidence is UNKNOWN/NOT_EVALUATED; no report field or local PASS can
authorize a project-wide GO by itself.

P23-A envelopes and P23-B decisions are immutable. A changed source produces
an INVALIDATED lifecycle event and the read API returns NOT_EVALUATED for the
current state; historical issued records are never rewritten.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from fractions import Fraction
import hashlib
from typing import Any

from concilium.application.scheduling.physical_validator import (
    PhysicalActivity,
    PhysicalPrecedence,
    validate_materialized_calendar,
)
from concilium.application.services.project.project_repository import ProjectHandle
from concilium.domain.models.canonical import CanonicalModel
from concilium.domain.models.formalism_certificate import (
    FormalismCertificateEvent,
    FormalismCertificateRecord,
    FormalismGateEvaluation,
    SourceName,
    build_certificate_event,
    build_formalism_certificate_record,
    build_provisional_certificate,
    fingerprint_source,
    matches_current_sources,
)

# Git object identities of the normative LONGO/RESUMIDO files and independent
# P22 reference implementations/vectors on the P23 implementation baseline.
# The SHA-256 references are derived from these exact immutable Git blob IDs;
# #26 owns the traceability/anti-drift check that updates these references.
_FORMALISM_REFERENCE = (
    "long:f83d37c03b3dbcebc0cbb446cc6d4333fa05cdd5;"
    "resumido:7cc825e9af2de9d84af7fa2c2036f164db834cf5"
)
_ORACLE_REFERENCE = (
    "physical-reference:570e73eef9ef3e74f2249d263e9b652035966a98;"
    "economic-reference:c3fd324ba86c89ef849b9dd6b0f07aa1814a3eed;"
    "physical-vector:dda8e8117de996856a14ffa47e848344370d8b06;"
    "economic-vector:cef850620b8d2267228e8321cbbf923593e9f891"
)
FORMALISM_SHA256 = hashlib.sha256(_FORMALISM_REFERENCE.encode("ascii")).hexdigest()
ORACLE_SHA256 = hashlib.sha256(_ORACLE_REFERENCE.encode("ascii")).hexdigest()

_CERTIFICATE_ROOT = "formalism/certificates"
_CERTIFICATE_EVENTS = "formalism/certificate-events.jsonl"


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not all(isinstance(k, str) for k in value):
        raise ValueError(f"{label} must be a string-keyed mapping")
    return value


def _fraction(value: object, label: str, *, nonnegative: bool = True) -> Fraction:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be an exact rational string")
    try:
        result = Fraction(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError(f"{label} must be an exact rational string") from exc
    if nonnegative and result < 0:
        raise ValueError(f"{label} must be nonnegative")
    return result


def _integer(value: object, label: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return value


def _gate(
    gate_id: str,
    status: str,
    evidence: object | None,
    *reasons: str,
    applicable: bool = True,
) -> FormalismGateEvaluation:
    digest = None
    if evidence is not None:
        digest = fingerprint_source("canonical", {"gate": gate_id, "evidence": evidence})
    return FormalismGateEvaluation(
        gate_id=gate_id,
        status=status,
        evidence_sha256=digest,
        applicable=applicable,
        reasons=tuple(reason for reason in reasons if reason),
    )


def _unknown(gate_id: str, reason: str, evidence: object | None = None) -> FormalismGateEvaluation:
    return _gate(gate_id, "UNKNOWN", evidence, reason)


def _fail(gate_id: str, reason: str, evidence: object | None = None) -> FormalismGateEvaluation:
    return _gate(gate_id, "FAIL", evidence, reason)


def _physical_witness(canonical: CanonicalModel) -> tuple[list[PhysicalActivity], list[PhysicalPrecedence], dict[str, Fraction], int, Mapping[str, Any]]:
    witness = _mapping(canonical.physical_calendar_evidence, "physical_calendar_evidence")
    if witness.get("schema") != "concilium.p15.physical-calendar-witness.v1":
        raise ValueError("unsupported P15 physical witness schema")
    if witness.get("resolver_status") != "PASS" or witness.get("audit_status") != "PASS":
        raise ValueError("P15 did not persist a passing final physical-calendar witness")
    if witness.get("require_weekly_capacity") is not True:
        raise ValueError("P15 witness did not require weekly F(m) capacity evidence")
    horizon = _integer(witness.get("calendar_horizon_weeks"), "calendar_horizon_weeks", 1)
    raw_activities = witness.get("activities")
    if not isinstance(raw_activities, list) or not raw_activities:
        raise ValueError("physical witness has no scheduled activities")
    activities: list[PhysicalActivity] = []
    for index, raw in enumerate(raw_activities):
        row = _mapping(raw, f"physical activity {index}")
        deliveries_raw = row.get("deliveries")
        demands_raw = row.get("demands")
        capacities_raw = row.get("weekly_capacities")
        if not isinstance(deliveries_raw, list) or not isinstance(demands_raw, list) or not isinstance(capacities_raw, list):
            raise ValueError(f"physical activity {index} lacks exact weekly rows")
        deliveries = tuple(
            (_integer(pair[0], "delivery week"), _fraction(pair[1], "delivery quantity"))
            for pair in deliveries_raw
            if isinstance(pair, list) and len(pair) == 2
        )
        if len(deliveries) != len(deliveries_raw):
            raise ValueError(f"physical activity {index} has malformed delivery rows")
        demands = tuple(
            (_integer(item[0], "demand week"), str(item[1]), _fraction(item[2], "resource demand"))
            for item in demands_raw
            if isinstance(item, list) and len(item) == 3
        )
        if len(demands) != len(demands_raw):
            raise ValueError(f"physical activity {index} has malformed resource-demand rows")
        capacities = tuple(
            (_integer(pair[0], "capacity week"), _fraction(pair[1], "weekly capacity"))
            for pair in capacities_raw
            if isinstance(pair, list) and len(pair) == 2
        )
        if len(capacities) != len(capacities_raw):
            raise ValueError(f"physical activity {index} has malformed weekly-capacity rows")
        item_id = row.get("item_id")
        if not isinstance(item_id, str) or not item_id.strip():
            raise ValueError(f"physical activity {index} has no item identity")
        activities.append(PhysicalActivity(
            item_id=item_id,
            scope=_fraction(row.get("scope"), f"{item_id}.scope", nonnegative=False),
            start_week=_integer(row.get("start_week"), f"{item_id}.start_week"),
            end_week_exclusive=_integer(row.get("end_week_exclusive"), f"{item_id}.end_week_exclusive", 1),
            deliveries=deliveries,
            demands=demands,
            weekly_capacities=capacities,
        ))

    raw_edges = witness.get("precedences")
    if not isinstance(raw_edges, list):
        raise ValueError("physical witness precedence list is missing")
    precedences: list[PhysicalPrecedence] = []
    for index, raw in enumerate(raw_edges):
        row = _mapping(raw, f"precedence {index}")
        kind = row.get("kind")
        if kind not in ("FS", "SS", "FF"):
            raise ValueError(f"precedence {index} has an unsupported relation")
        predecessor, successor = row.get("predecessor"), row.get("successor")
        if not isinstance(predecessor, str) or not isinstance(successor, str):
            raise ValueError(f"precedence {index} has invalid endpoints")
        precedences.append(PhysicalPrecedence(
            predecessor=predecessor,
            successor=successor,
            kind=kind,
            lag_weeks=_integer(row.get("lag_weeks"), "lag_weeks"),
            completion_threshold=_fraction(
                row.get("completion_threshold"), "completion_threshold",
            ),
        ))

    raw_pool = _mapping(witness.get("pool_capacity"), "pool_capacity")
    pool = {key: _fraction(value, f"pool_capacity.{key}") for key, value in raw_pool.items()}
    if not pool:
        raise ValueError("physical witness has no explicit resource pool")
    return activities, precedences, pool, horizon, witness


def _physical_gates(canonical: CanonicalModel) -> tuple[FormalismGateEvaluation, FormalismGateEvaluation]:
    try:
        activities, precedences, pool, horizon, witness = _physical_witness(canonical)
        audit = validate_materialized_calendar(
            activities,
            precedences,
            calendar_horizon_weeks=horizon,
            pool_capacity=pool,
            require_weekly_capacity=True,
        )
    except (TypeError, ValueError, KeyError, OverflowError, ZeroDivisionError) as exc:
        return (
            _unknown("V1", f"physical Q/capacity evidence unavailable or malformed: {exc}"),
            _unknown("V6", f"physical calendar/precedence/resource evidence unavailable: {exc}"),
        )

    if audit.status != "PASS" and not audit.violations:
        return (
            _unknown("V1", "physical verifier did not establish PASS", witness),
            _unknown("V6", "physical verifier did not establish PASS", witness),
        )

    v1 = [v for v in audit.violations if v.code.startswith("V1_")]
    v6 = [v for v in audit.violations if v.code.startswith("V6_")]
    v1_unknown = [v for v in v1 if "UNVERIFIED" in v.code]
    v6_unknown = [v for v in v6 if "UNVERIFIED" in v.code]
    v1_reason = "; ".join(f"{v.code}:{v.item_id}:{v.reason}" for v in v1)
    v6_reason = "; ".join(f"{v.code}:{v.item_id}:{v.reason}" for v in v6)

    v1_result = (
        _unknown("V1", v1_reason, witness) if v1_unknown else
        _fail("V1", v1_reason, witness) if v1 else
        _gate("V1", "PASS", {"witness": witness, "audit": "PASS"})
    )
    v6_result = (
        _unknown("V6", v6_reason, witness) if v6_unknown else
        _fail("V6", v6_reason, witness) if v6 else
        _gate("V6", "PASS", {"witness": witness, "audit": "PASS"})
    )
    if audit.status == "FAIL" and not v1 and not v6:
        return (
            _fail("V1", "physical audit failed without classifiable V1 violation", witness),
            _fail("V6", "physical audit failed without classifiable V6 violation", witness),
        )
    if witness.get("audit_status") != audit.status:
        return (
            _fail("V1", "persisted P15 audit status differs from independent replay", witness),
            _fail("V6", "persisted P15 audit status differs from independent replay", witness),
        )
    return v1_result, v6_result


def _pool_gate(canonical: CanonicalModel) -> FormalismGateEvaluation:
    contracts = canonical.contratos_recurso or []
    if not contracts:
        return _unknown("V3", "no exact contractual resource assignment witness was persisted")
    snapshots: list[dict[str, object]] = []
    try:
        for contract in contracts:
            witness = _mapping(contract.p16_global_assignment, f"{contract.tipo_id}.p16_global_assignment")
            if (
                witness.get("schema") != "p16-global-instance-assignment/v1"
                or witness.get("proof_scope") != "EXACT_GLOBAL_INSTANCE_ASSIGNMENT_CONDITIONAL_ON_FIXED_PHYSICAL_DEMAND"
                or witness.get("status") != "EXACT_CONDITIONAL_ON_FIXED_PHYSICAL_DEMAND"
                or witness.get("is_project_go_certificate") is not False
            ):
                raise ValueError(f"{contract.tipo_id}: invalid exact P16 witness declaration")
            demand = witness.get("demand")
            presence = witness.get("presence")
            standby = witness.get("standby")
            if not all(isinstance(row, list) for row in (demand, presence, standby)):
                raise ValueError(f"{contract.tipo_id}: demand/presence/standby vectors are missing")
            if not demand or len(demand) != len(presence) or len(demand) != len(standby):
                raise ValueError(f"{contract.tipo_id}: demand/presence/standby horizons differ")
            for index, (d, p, idle) in enumerate(zip(demand, presence, standby, strict=True)):
                d = _integer(d, f"{contract.tipo_id}.demand[{index}]")
                p = _integer(p, f"{contract.tipo_id}.presence[{index}]")
                idle = _integer(idle, f"{contract.tipo_id}.standby[{index}]")
                if p < d or idle != p - d:
                    raise ValueError(f"{contract.tipo_id}: physical presence/standby mismatch in week {index}")
            demand_by_activity = _mapping(witness.get("demand_by_activity"), "demand_by_activity")
            if not demand_by_activity:
                raise ValueError(f"{contract.tipo_id}: per-activity demand is missing")
            for week_index, aggregate in enumerate(demand):
                reconstructed = 0
                for activity_id, series in demand_by_activity.items():
                    if not isinstance(activity_id, str) or not isinstance(series, list) or len(series) != len(demand):
                        raise ValueError(f"{contract.tipo_id}: malformed per-activity demand")
                    reconstructed += _integer(series[week_index], "per-activity demand")
                if reconstructed != aggregate:
                    raise ValueError(f"{contract.tipo_id}: demand does not reconstruct from activities")
            snapshots.append({
                "contract_id": contract.contrato_id,
                "resource_type": contract.tipo_id,
                "demand": demand,
                "presence": presence,
                "standby": standby,
            })
    except (ValueError, TypeError, KeyError) as exc:
        return _fail("V3", str(exc))
    return _gate("V3", "PASS", snapshots)


def _catalog_productivity_proven(catalog: object, item_cpu_ids: set[str]) -> tuple[bool, str]:
    try:
        data = _mapping(catalog, "resolved catalog")
        cpus_raw, production_raw = data.get("cpus"), data.get("producoes")
        if not isinstance(cpus_raw, list) or not isinstance(production_raw, list):
            return False, "resolved catalog lacks CPU/productivity sequences"
        cpus = {row.get("codigo"): row for row in cpus_raw if isinstance(row, Mapping)}
        productions = {row.get("id"): row for row in production_raw if isinstance(row, Mapping)}
        for cpu_id in item_cpu_ids:
            cpu = cpus.get(cpu_id)
            if not isinstance(cpu, Mapping):
                return False, f"CPU catalog record missing for {cpu_id}"
            prod_id = cpu.get("producao_id_ref")
            production = productions.get(prod_id)
            if not isinstance(production, Mapping):
                return False, f"versioned physical production record missing for CPU {cpu_id}"
            graph = production.get("grafo_sinergia")
            origin = production.get("origem")
            audit = production.get("auditoria")
            if not isinstance(graph, Mapping) or not graph:
                return False, f"F(m) graph missing for CPU {cpu_id}"
            if not isinstance(origin, Mapping) or not isinstance(audit, Mapping):
                return False, f"F(m) source/version metadata missing for CPU {cpu_id}"
            if not isinstance(origin.get("fonte_id"), str) or not origin.get("fonte_id", "").strip():
                return False, f"F(m) source identity missing for CPU {cpu_id}"
            if not isinstance(audit.get("versao"), str) or not audit.get("versao", "").strip():
                return False, f"F(m) version missing for CPU {cpu_id}"
        return True, ""
    except (TypeError, ValueError, AttributeError):
        return False, "resolved catalog productivity provenance is malformed"


def _productivity_gate(canonical: CanonicalModel, catalog: object) -> FormalismGateEvaluation:
    schedule = canonical.cronograma
    if schedule is None or not schedule.scheduled_activities:
        return _unknown("V5", "no final scheduled activity witness")
    eap = {item.item_id: item for item in canonical.eap or []}
    activity_to_item = {
        item.atividade_id: item.eap_item_id for item in canonical.atividades or []
    }
    checked: list[dict[str, object]] = []
    active_items: set[str] = set()
    for scheduled in schedule.scheduled_activities:
        item_id = activity_to_item.get(scheduled.activity_id, scheduled.activity_id)
        if item_id not in eap:
            return _fail("V5", f"scheduled activity {scheduled.activity_id} has no EAP/CPU mapping")
        cells = scheduled.distribuicao_semanal
        if not cells:
            return _unknown("V5", f"{item_id}: no persisted weekly productivity cells")
        for week, cell in cells.items():
            if cell.num_equipes > 0 and (
                cell.fator_clima * cell.fator_calendario * cell.fator_jornada > 0
            ):
                active_items.add(item_id)
                rate = cell.produtividade_fisica_horaria
                origin = cell.origem_produtividade
                if rate is not None and rate <= 0:
                    return _fail("V5", f"{item_id}/{week}: physical productivity F(m) is not positive")
                if rate is None or cell.capacidade_disponivel_semana is None:
                    return _unknown("V5", f"{item_id}/{week}: physical productivity/capacity witness is missing")
                if cell.capacidade_disponivel_semana < 0:
                    return _fail("V5", f"{item_id}/{week}: negative available physical capacity")
                if origin not in ("GRAFO_FLUXO", "GRAFO_ELEMENTOS"):
                    return _fail("V5", f"{item_id}/{week}: fallback/undeclared productivity origin {origin}")
                checked.append({
                    "item_id": item_id,
                    "week": week,
                    "rate": rate,
                    "capacity": cell.capacidade_disponivel_semana,
                    "origin": origin,
                })
    if not active_items:
        return _unknown("V5", "no productive team-week was available to verify F(m)>0")
    cpu_ids = {eap[item_id].cpu_id for item_id in active_items}
    proven, reason = _catalog_productivity_proven(catalog, cpu_ids)
    if not proven:
        return _unknown("V5", reason, checked)
    return _gate("V5", "PASS", {"cells": checked, "catalog_cpus": sorted(cpu_ids)})


def _pricing_gates(canonical: CanonicalModel) -> tuple[FormalismGateEvaluation, FormalismGateEvaluation]:
    result = canonical.resultado
    if result is None or not result.pricing_gates or not result.pricing_diagnostics:
        return (
            _unknown("V2", "P21 regulatory BDI evidence is missing"),
            _unknown("V4", "P21 operational price/profitability evidence is missing"),
        )
    gates = result.pricing_gates
    diagnostics = result.pricing_diagnostics
    intent = gates.get("certification_intent")
    if intent != "CERTIFIED":
        return (
            _unknown("V2", f"P21 certification_intent is {intent!r}, not CERTIFIED", gates),
            _unknown("V4", f"P21 certification_intent is {intent!r}, not CERTIFIED", gates),
        )

    regulatory_status = gates.get("regulatory_status")
    basis_fp = gates.get("regulatory_basis_fingerprint")
    operational_fp = diagnostics.get("operational_basis_fingerprint")
    if regulatory_status == "FAIL":
        v2 = _fail("V2", str(gates.get("reasons") or "regulatory BDI gate failed"), gates)
    elif regulatory_status != "PASS":
        v2 = _unknown("V2", str(gates.get("reasons") or "regulatory BDI basis is unknown"), gates)
    elif not basis_fp or basis_fp != operational_fp:
        v2 = _fail("V2", "regulatory BDI basis is not the same declared operational basis", gates)
    else:
        try:
            rate = _fraction(gates.get("regulatory_bdi_rate"), "regulatory BDI rate")
            floor = _fraction(gates.get("regulatory_bdi_floor"), "regulatory BDI floor")
            amount = _fraction(gates.get("regulatory_basis_amount"), "regulatory basis amount")
            if amount <= 0 or rate < floor:
                v2 = _fail("V2", "regulatory BDI rate is below floor or its base is nonpositive", gates)
            else:
                v2 = _gate("V2", "PASS", {
                    "rate": str(rate), "floor": str(floor), "basis_amount": str(amount),
                    "basis_fingerprint": basis_fp,
                })
        except (ValueError, TypeError) as exc:
            v2 = _unknown("V2", f"regulatory BDI inputs are incomplete: {exc}", gates)

    profit_status = gates.get("profitability_status")
    if profit_status == "FAIL":
        v4 = _fail("V4", str(gates.get("reasons") or "profitability gate failed"), gates)
    elif profit_status != "PASS":
        v4 = _unknown("V4", str(gates.get("reasons") or "profitability evidence is unknown"), gates)
    else:
        try:
            price = _fraction(diagnostics.get("operational_price"), "operational price")
            total_cost = _fraction(diagnostics.get("total_cost"), "total cost")
            profit = _fraction(gates.get("profit_amount"), "profit amount", nonnegative=False)
            margin = _fraction(gates.get("realized_margin"), "realized margin", nonnegative=False)
            if price <= 0 or total_cost <= 0 or price <= total_cost or profit != price - total_cost:
                v4 = _fail("V4", "P must be positive, C_tot positive and P>C_tot with exact profit identity", gates)
            elif margin != profit / price:
                v4 = _fail("V4", "reported realized margin does not reconstruct from exact P and C_tot", gates)
            else:
                minimum = gates.get("minimum_profit_margin")
                if minimum is not None and margin < _fraction(minimum, "minimum profit margin"):
                    v4 = _fail("V4", "realized margin is below the explicitly required contractual margin", gates)
                else:
                    v4 = _gate("V4", "PASS", {
                        "operational_price": str(price),
                        "total_cost": str(total_cost),
                        "profit": str(profit),
                        "margin": str(margin),
                    })
        except (ValueError, TypeError, ZeroDivisionError) as exc:
            v4 = _unknown("V4", f"profitability inputs are incomplete: {exc}", gates)
    return v2, v4


def _inventory_snapshot(canonical: CanonicalModel) -> Mapping[str, Any] | None:
    value = canonical.p23_inventory_evidence
    if not isinstance(value, Mapping):
        return None
    return value


def _consumption_gate(inventory: Mapping[str, Any] | None) -> FormalismGateEvaluation:
    if inventory is None or inventory.get("schema") != "concilium.p23.inventory-evidence.v1":
        return _unknown("V8", "typed P18 physical-consumption evidence was not persisted")
    rows = inventory.get("consumption_evidence")
    if not isinstance(rows, list):
        return _unknown("V8", "P18 physical-consumption evidence list is missing", inventory)
    seen: set[str] = set()
    units: dict[str, str] = {}
    totals: dict[tuple[str, str], Fraction] = {}
    for index, raw in enumerate(rows):
        try:
            row = _mapping(raw, f"consumption evidence {index}")
            source_id, activity_id, good_id, week, unit = (
                row.get("source_id"), row.get("activity_id"), row.get("good_id"),
                row.get("week"), row.get("physical_unit"),
            )
            if not all(isinstance(x, str) and x.strip() for x in (source_id, activity_id, good_id, week, unit)):
                raise ValueError("P18 consumption row lacks source/activity/good/week/unit identity")
            if source_id in seen:
                raise ValueError(f"duplicate P18 physical evidence id {source_id}")
            seen.add(source_id)
            previous_unit = units.get(good_id)
            if previous_unit is not None and previous_unit != unit:
                raise ValueError(f"{good_id}: inconsistent physical units across weekly consumption")
            units[good_id] = unit
            date.fromisocalendar(int(week[:4]), int(week[-2:]), 1)
            quantity = _fraction(row.get("physical_quantity"), "physical consumption quantity")
            priced = _fraction(row.get("priced_quantity"), "priced physical quantity")
            exact_cost = _fraction(row.get("exact_cost"), "physical consumption cost")
            if priced < 0 or exact_cost < 0:
                raise ValueError("negative physical acquisition/cost evidence")
            key = (good_id, week)
            totals[key] = totals.get(key, Fraction(0)) + quantity
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            return _fail("V8", str(exc), inventory)

    stock_rows = inventory.get("stock_rows")
    if stock_rows:
        stock_demand: dict[tuple[str, str], Fraction] = {}
        for index, raw in enumerate(stock_rows):
            row = _mapping(raw, f"stock row {index}")
            key = (str(row.get("good_id")), str(row.get("week")))
            demand = _fraction(row.get("physical_demand"), "stock physical demand")
            if key in stock_demand:
                return _fail("V8", "duplicate stock demand week/good row", inventory)
            stock_demand[key] = demand
        for key, amount in stock_demand.items():
            if totals.get(key, Fraction(0)) != amount:
                return _fail("V8", f"physical consumption does not reconstruct stock demand for {key}", inventory)
        if any(key not in stock_demand and amount for key, amount in totals.items()):
            return _fail("V8", "P18 physical consumption has weeks outside the P19 stock witness", inventory)

    if not rows:
        # An explicit empty P18 journal is a valid zero-consumption witness only
        # when its P21 inventory declaration is itself versioned/provenanced.
        if inventory.get("status") not in ("NO_INVENTORY", "COMPLETE"):
            return _unknown("V8", "no P18 rows and no explicit inventory scope", inventory)
        return _gate("V8", "PASS", inventory, "no physical consumables declared in the P18 journal", applicable=False)
    return _gate("V8", "PASS", {"rows": rows, "totals_by_good_week": {
        f"{good}|{week}": str(value) for (good, week), value in sorted(totals.items())
    }})


def _stock_gates(inventory: Mapping[str, Any] | None) -> tuple[FormalismGateEvaluation, FormalismGateEvaluation]:
    if inventory is None or inventory.get("schema") != "concilium.p23.inventory-evidence.v1":
        return (
            _unknown("V7", "typed P19 stock evidence was not persisted"),
            _unknown("V9", "typed P19 lead-time evidence was not persisted"),
        )
    scope = inventory.get("status")
    provenance = all(
        isinstance(inventory.get(key), str) and bool(inventory.get(key))
        for key in ("source", "reference_id", "fingerprint")
    )
    if scope == "NO_INVENTORY" and provenance:
        return (
            _gate("V7", "PASS", inventory, "explicit NO_INVENTORY scope", applicable=False),
            _gate("V9", "PASS", inventory, "no purchase orders or receipts in explicit NO_INVENTORY scope", applicable=False),
        )
    if scope != "COMPLETE" or not provenance:
        return (
            _unknown("V7", "inventory scope is not explicitly COMPLETE or NO_INVENTORY", inventory),
            _unknown("V9", "inventory scope/lead-time source provenance is incomplete", inventory),
        )

    goods_raw = inventory.get("goods")
    rows_raw = inventory.get("stock_rows")
    weeks_raw = inventory.get("calendar_weeks")
    if not isinstance(goods_raw, list) or not goods_raw or not isinstance(rows_raw, list) or not rows_raw or not isinstance(weeks_raw, list) or not weeks_raw:
        return (
            _unknown("V7", "COMPLETE inventory scope lacks goods, calendar or stock rows", inventory),
            _unknown("V9", "COMPLETE inventory scope lacks a declared calendar", inventory),
        )
    try:
        goods: dict[str, dict[str, Any]] = {}
        for raw in goods_raw:
            row = _mapping(raw, "stock good")
            good_id, unit = row.get("good_id"), row.get("unit")
            if not isinstance(good_id, str) or not good_id.strip() or not isinstance(unit, str) or not unit.strip() or good_id in goods:
                raise ValueError("stock good identity/unit missing or duplicated")
            goods[good_id] = {
                "unit": unit,
                "initial": _fraction(row.get("initial_quantity"), f"{good_id}.initial_quantity"),
                "lead": _integer(row.get("lead_time_weeks"), f"{good_id}.lead_time_weeks"),
            }
        weeks = tuple(str(week) for week in weeks_raw)
        if len(set(weeks)) != len(weeks):
            raise ValueError("inventory calendar repeats a week")
        week_dates = {
            week: date.fromisocalendar(int(week[:4]), int(week[-2:]), 1)
            for week in weeks
        }
        if any(
            week_dates[b] - week_dates[a] != __import__("datetime").timedelta(weeks=1)
            for a, b in zip(weeks, weeks[1:])
        ):
            raise ValueError("inventory calendar must be consecutive ISO weeks")
        previous: dict[str, Fraction] = {}
        seen_rows: set[tuple[str, str]] = set()
        for raw in rows_raw:
            row = _mapping(raw, "stock row")
            good_id, week, unit = row.get("good_id"), row.get("week"), row.get("unit")
            if good_id not in goods or week not in week_dates or unit != goods[good_id]["unit"]:
                raise ValueError("stock row does not match the declared good/calendar/unit")
            key = (str(good_id), str(week))
            if key in seen_rows:
                raise ValueError("duplicate stock good/week row")
            seen_rows.add(key)
            opening = _fraction(row.get("opening"), "stock opening")
            receipts = _fraction(row.get("external_receipts"), "external receipts")
            generation = _fraction(row.get("internal_generation"), "internal generation")
            overflow = _fraction(row.get("storage_overflow"), "storage overflow")
            demand = _fraction(row.get("physical_demand"), "physical demand")
            fulfilled = _fraction(row.get("fulfilled"), "fulfilled demand")
            shortage = _fraction(row.get("shortage"), "stock shortage")
            closing = _fraction(row.get("closing"), "closing stock")
            expected_opening = previous.get(str(good_id), goods[str(good_id)]["initial"])
            if opening != expected_opening:
                raise ValueError(f"{good_id}/{week}: opening balance differs from prior closing stock")
            if opening + receipts + generation != overflow + fulfilled + closing:
                raise ValueError(f"{good_id}/{week}: physical stock mass balance does not close")
            if demand != fulfilled + shortage:
                raise ValueError(f"{good_id}/{week}: physical demand/shortage balance does not close")
            if shortage > 0:
                raise ArithmeticError(f"{good_id}/{week}: unresolved physical stock shortage {shortage}")
            previous[str(good_id)] = closing
        expected_keys = {(good, week) for good in goods for week in weeks}
        if seen_rows != expected_keys:
            raise ValueError("stock ledger does not cover every declared good/week")
        v7 = _gate("V7", "PASS", {"goods": goods_raw, "stock_rows": rows_raw, "calendar": weeks})

        arrivals_raw = inventory.get("arrivals")
        purchases_raw = inventory.get("purchases")
        if not isinstance(arrivals_raw, list) or not isinstance(purchases_raw, list):
            raise ValueError("lead-time arrival/purchase evidence lists are missing")
        purchases: dict[str, Mapping[str, Any]] = {}
        for raw in purchases_raw:
            row = _mapping(raw, "external purchase")
            purchase_id = row.get("source_id")
            if not isinstance(purchase_id, str) or not purchase_id.strip() or purchase_id in purchases:
                raise ValueError("external purchase identity missing or duplicated")
            if row.get("good_id") not in goods:
                raise ValueError("external purchase refers to unknown stock good")
            if row.get("currency") != inventory.get("catalog_metadata", {}).get("currency"):
                raise ValueError("external purchase currency differs from verified catalog metadata")
            purchases[purchase_id] = row
        matched_receipts: set[str] = set()
        for raw in arrivals_raw:
            row = _mapping(raw, "stock arrival")
            source_id, good_id, arrival_week = row.get("source_id"), row.get("good_id"), row.get("arrival_week")
            if not isinstance(source_id, str) or not isinstance(good_id, str) or good_id not in goods:
                raise ValueError("stock arrival identity/good is invalid")
            if arrival_week not in week_dates:
                raise ValueError("stock arrival is outside the declared inventory calendar")
            if row.get("source") == "EXTERNAL_DELIVERY":
                purchase_id = source_id.removeprefix("EXTERNAL_RECEIPT:")
                purchase = purchases.get(purchase_id)
                if purchase is None or purchase_id in matched_receipts:
                    raise ValueError("external receipt does not map to exactly one priced purchase")
                matched_receipts.add(purchase_id)
                ordered_week = purchase.get("ordered_week")
                if ordered_week not in week_dates or purchase.get("arrival_week") != arrival_week or purchase.get("good_id") != good_id:
                    raise ValueError("purchase order/receipt dates or good identity mismatch")
                elapsed = (week_dates[str(arrival_week)] - week_dates[str(ordered_week)]).days // 7
                if elapsed < goods[good_id]["lead"]:
                    raise ArithmeticError(f"{good_id}: receipt violates the declared lead time")
                if _fraction(purchase.get("quantity"), "purchase quantity") != _fraction(row.get("quantity"), "receipt quantity") or purchase.get("physical_unit") != row.get("unit"):
                    raise ValueError("priced purchase does not match physical receipt")
            elif row.get("source") == "INTERNAL_GENERATION":
                if row.get("ordered_week") is not None:
                    raise ValueError("internal generation must not claim a purchase order")
            else:
                raise ValueError("unsupported physical receipt source")
        if matched_receipts != set(purchases):
            raise ValueError("some priced external purchases have no physical receipt")
        if purchases:
            metadata = _mapping(inventory.get("catalog_metadata"), "catalog metadata")
            if metadata.get("currency_source") != "catalog_metadata.json" or not isinstance(metadata.get("currency"), str):
                raise ValueError("external purchase currency does not have verified catalog metadata")
        v9 = _gate("V9", "PASS", {
            "goods": goods_raw, "calendar": weeks, "arrivals": arrivals_raw, "purchases": purchases_raw,
        })
        return v7, v9
    except ArithmeticError as exc:
        return _fail("V7", str(exc), inventory), _fail("V9", str(exc), inventory)
    except (TypeError, ValueError, KeyError, OverflowError) as exc:
        message = str(exc)
        return _fail("V7", message, inventory), _fail("V9", message, inventory)


def _ledger_gate(canonical: CanonicalModel, inventory: Mapping[str, Any] | None) -> FormalismGateEvaluation:
    p17 = canonical.p17_cost_reconciliation
    if not isinstance(p17, Mapping):
        return _unknown("V10", "P17 Skill05→Skill06 reconciliation is missing")
    if (
        p17.get("schema") != "concilium.p17.skill06-reconciliation.v1"
        or p17.get("authority") != "P17_SKILL06_READ_ONLY_RECONCILIATION_NOT_PROJECT_GO"
        or p17.get("project_go_authorized") is not False
    ):
        return _fail("V10", "P17 reconciliation schema/authority is not the expected read-only contract", p17)
    if p17.get("status") != "RECONCILED":
        return _fail("V10", "; ".join(p17.get("reasons", [])) or "P17 source reconciliation returned NOGO", p17)
    invariants = p17.get("invariants")
    if not isinstance(invariants, Mapping) or not invariants or any(value is not True for value in invariants.values()):
        return _fail("V10", "one or more P17 reconciliation invariants are false or missing", p17)
    postings = p17.get("exclusive_postings")
    totals = p17.get("totals")
    if not isinstance(postings, list) or not isinstance(totals, Mapping):
        return _unknown("V10", "P17 exact posting/totals evidence is incomplete", p17)
    identities: set[tuple[str, ...]] = set()
    k = v = indirect = Fraction(0)
    try:
        for raw in postings:
            row = _mapping(raw, "P17 posting")
            event_id = row.get("event_id")
            if not isinstance(event_id, list) or not event_id or any(not isinstance(x, str) or not x for x in event_id):
                raise ValueError("P17 posting has invalid event identity")
            event = tuple(event_id)
            if event in identities:
                raise ValueError("P17 contains duplicate event ownership")
            identities.add(event)
            amount = _fraction(row.get("amount"), "P17 posting amount")
            category, nature = row.get("category"), row.get("nature")
            if category in ("MO", "EQ"):
                k += amount
            elif category in ("MAT", "COMB"):
                v += amount
            elif category == "IND":
                indirect += amount
            else:
                raise ValueError("P17 posting has an unknown exclusive cost category")
            if not isinstance(nature, str) or not isinstance(row.get("source"), str) or not isinstance(row.get("week"), str):
                raise ValueError("P17 posting lacks nature/source/week provenance")
        expected_total = _fraction(totals.get("total"), "P17 total")
        if _fraction(totals.get("direct_k_plus_v"), "P17 direct") != k + v:
            raise ValueError("P17 direct K+V total does not reconstruct")
        if _fraction(totals.get("indirect_mob_demob"), "P17 indirect") != indirect:
            raise ValueError("P17 indirect total does not reconstruct")
        if expected_total != k + v + indirect:
            raise ValueError("P17 total does not reconstruct from exclusive source categories")
        if inventory is None or not isinstance(inventory.get("financial_postings"), list):
            return _unknown("V10", "P20 full K/V/IND financial source ledger was not persisted", p17)
        full_rows = inventory["financial_postings"]
        full_ids: set[tuple[str, ...]] = set()
        full_direct = full_indirect = Fraction(0)
        for raw in full_rows:
            row = _mapping(raw, "P20 posting")
            event_id = row.get("event_id")
            if not isinstance(event_id, list):
                raise ValueError("P20 event identity is invalid")
            event = tuple(event_id)
            if not event or event in full_ids:
                raise ValueError("P20 contains missing or duplicate event identity")
            full_ids.add(event)
            amount = _fraction(row.get("amount"), "P20 posting amount")
            category = row.get("category")
            if category in ("MO", "EQ", "MAT", "COMB"):
                full_direct += amount
            elif category == "IND":
                full_indirect += amount
            else:
                raise ValueError("P20 posting has unknown cost category")
        p20_totals = _mapping(inventory.get("financial_totals"), "P20 financial totals")
        if _fraction(p20_totals.get("direct"), "P20 direct") != full_direct:
            raise ValueError("P20 direct source postings do not reconcile")
        if _fraction(p20_totals.get("indirect"), "P20 indirect") != full_indirect:
            raise ValueError("P20 indirect source postings do not reconcile")
        if _fraction(p20_totals.get("total"), "P20 total") != full_direct + full_indirect:
            raise ValueError("P20 total does not reconcile")
        if canonical.resultado is None or not canonical.resultado.pricing_diagnostics:
            return _unknown("V10", "P21 price diagnostics are required to cross-check the reconciled ledger")
        diag = canonical.resultado.pricing_diagnostics
        if (
            _fraction(diag.get("direct_cost"), "P21 direct cost") != full_direct
            or _fraction(diag.get("indirect_cost"), "P21 indirect cost") != full_indirect
            or _fraction(diag.get("total_cost"), "P21 total cost") != full_direct + full_indirect
        ):
            raise ValueError("P21 pricing costs differ from P20 exact financial postings")
    except (TypeError, ValueError, KeyError, OverflowError, ZeroDivisionError) as exc:
        return _fail("V10", str(exc), {"p17": p17, "inventory": inventory})
    return _gate("V10", "PASS", {"p17": p17, "p20_postings": inventory["financial_postings"], "p20_totals": p20_totals})


def _regime_gate(canonical: CanonicalModel, inventory: Mapping[str, Any] | None) -> FormalismGateEvaluation:
    result = canonical.resultado
    if result is None or not result.pricing_gates or not result.pricing_diagnostics or inventory is None:
        return _unknown("V11", "versioned P13/P21 regime, catalog and formula evidence is missing")
    metadata = inventory.get("catalog_metadata")
    if not isinstance(metadata, Mapping) or metadata.get("currency_source") != "catalog_metadata.json":
        return _unknown("V11", "catalog currency metadata/provenance is incomplete", inventory)
    currency = metadata.get("currency")
    if currency != result.pricing_diagnostics.get("currency"):
        return _fail("V11", "catalog and operational pricing currencies differ", inventory)
    bdi = inventory.get("bdi_by_category")
    expected_categories = {"MO", "EQ", "MAT", "COMB", "IND"}
    if not isinstance(bdi, Mapping) or set(bdi) != expected_categories:
        return _unknown("V11", "explicit differentiated BDI rates for all cost categories are missing", inventory)
    try:
        for category, rate in bdi.items():
            _fraction(rate, f"BDI {category}")
    except (ValueError, TypeError) as exc:
        return _fail("V11", str(exc), bdi)
    if canonical.tabela_bdi_efetiva is None:
        return _unknown("V11", "canonical effective BDI table is missing")
    contracts = canonical.contratos_recurso or []
    if not contracts:
        return _unknown("V11", "no explicit P13 contractual regime witnesses were persisted")
    for contract in contracts:
        if (
            contract.regime_economico_p13 not in (
                "FULL_RATE_STANDBY", "DISCOUNTED_STANDBY", "EXPLICIT_OFF_HIRE"
            )
            or not isinstance(contract.origem_regime_p13, str)
            or not contract.origem_regime_p13.strip()
            or contract.moeda_regime_p13 != currency
        ):
            return _unknown("V11", f"{contract.tipo_id}: explicit P13 regime/source/currency is incomplete")
    if result.pricing_gates.get("certification_intent") != "CERTIFIED":
        return _unknown("V11", "P21 pricing evidence was not requested in CERTIFIED mode")
    return _gate("V11", "PASS", {
        "catalog_metadata": metadata,
        "catalog_benchmark": inventory.get("catalog_benchmark"),
        "regulatory_basis": inventory.get("regulatory_basis"),
        "bdi_by_category": bdi,
        "contracts": [
            {
                "contract_id": contract.contrato_id,
                "regime": contract.regime_economico_p13,
                "source": contract.origem_regime_p13,
                "currency": contract.moeda_regime_p13,
            }
            for contract in contracts
        ],
    })


def _sources(
    project: ProjectHandle,
    version: str,
    run: Mapping[str, Any],
    canonical: CanonicalModel,
    catalog: object,
) -> dict[SourceName, Any | None]:
    schedule = canonical.cronograma
    result = canonical.resultado
    productivity = None
    if schedule is not None:
        productivity = {
            "eap": canonical.eap,
            "activities": canonical.atividades,
            "scheduled": schedule.scheduled_activities,
        }
    calendar = None
    if canonical.calendario_operacional or canonical.fator_calendario_semanal or canonical.praticabilidade:
        calendar = {
            "operational": canonical.calendario_operacional,
            "weekly_factor": canonical.fator_calendario_semanal,
            "practicability": canonical.praticabilidade,
        }
    pool = None
    if canonical.contratos_recurso or canonical.recurso_pool or canonical.instancias_recurso:
        pool = {
            "contracts": canonical.contratos_recurso,
            "resource_pool": canonical.recurso_pool,
            "instances": canonical.instancias_recurso,
        }
    inventory = None
    if canonical.p23_inventory_evidence is not None or canonical.p18_consumption_preview is not None or canonical.resumo_estoque_consumiveis:
        inventory = {
            "p23_inventory_evidence": canonical.p23_inventory_evidence,
            "p18_preview": canonical.p18_consumption_preview,
            "stock_summary": canonical.resumo_estoque_consumiveis,
            "consumables": canonical.recursos_consumiveis,
        }
    ledger = None
    if canonical.p17_cost_reconciliation is not None or canonical.p23_inventory_evidence is not None:
        ledger = {
            "p17": canonical.p17_cost_reconciliation,
            "p20": (
                canonical.p23_inventory_evidence.get("financial_postings")
                if isinstance(canonical.p23_inventory_evidence, Mapping) else None
            ),
        }
    pricing = None
    if result is not None and (result.pricing_diagnostics or result.pricing_gates):
        pricing = {
            "diagnostics": result.pricing_diagnostics,
            "gates": result.pricing_gates,
            "authority": result.pricing_authority,
            "bdi": canonical.tabela_bdi_efetiva,
            "bdi_memorial": canonical.memorial_calculo_bdi,
        }
    resolved_catalog = catalog if isinstance(catalog, Mapping) and catalog else None
    return {
        "canonical": canonical,
        "catalog": resolved_catalog,
        "productivity": productivity,
        "calendar": calendar,
        "schedule": (
            {
                "cronograma": canonical.cronograma,
                "intervals": canonical.intervalos_atividade,
                "physical_witness": canonical.physical_calendar_evidence,
                "constraints": canonical.constraint_violations,
            }
            if schedule is not None else None
        ),
        "pool": pool,
        "inventory": inventory,
        "ledger": ledger,
        "pricing": pricing,
        "solver": {
            "version": version,
            "run_id": run.get("run_id"),
            "base_version": run.get("base_version"),
            "procurement_intent": run.get("procurement_intent"),
            "skill_inputs_override": run.get("skill_inputs_override"),
            "catalog_base_hash": run.get("catalogo_base_hash"),
            "skills_log": run.get("skills_log"),
            "pipeline_integrity": canonical.pipeline_integridade,
            "pipeline_blocked_from": canonical.pipeline_blocked_from,
        },
    }


def build_run_certificate(
    *,
    project_id: str,
    version: str,
    run: Mapping[str, Any],
    canonical: CanonicalModel,
    catalog: object,
) -> FormalismCertificateRecord:
    """Evaluate all V1-V11 gates against the current pipeline evidence."""
    intent = str(run.get("procurement_intent") or "rfi").upper()
    scope = "RFP" if intent == "RFP" else "RFI" if intent == "RFI" else "PREVIEW"
    sources = _sources(project=None, version=version, run=run, canonical=canonical, catalog=catalog) if False else None
    # Keep the public collector independent of storage; the ProjectHandle is
    # needed only by persistence/invalidation functions below.
    source_snapshot: dict[SourceName, Any | None] = _sources_from_run(
        version=version, run=run, canonical=canonical, catalog=catalog
    )
    envelope = build_provisional_certificate(
        project_id=project_id,
        run_id=str(run.get("run_id") or ""),
        scope=scope,
        formalism_sha256=FORMALISM_SHA256,
        oracle_sha256=ORACLE_SHA256,
        sources=source_snapshot,
    )
    v1, v6 = _physical_gates(canonical)
    v2, v4 = _pricing_gates(canonical)
    inventory = _inventory_snapshot(canonical)
    evaluations = [
        v1,
        v2,
        _pool_gate(canonical),
        v4,
        _productivity_gate(canonical, catalog),
        v6,
        *_stock_gates(inventory)[:1],
        _consumption_gate(inventory),
        *_stock_gates(inventory)[1:],
        _ledger_gate(canonical, inventory),
        _regime_gate(canonical, inventory),
    ]
    return build_formalism_certificate_record(envelope, evaluations)


def _sources_from_run(
    *,
    version: str,
    run: Mapping[str, Any],
    canonical: CanonicalModel,
    catalog: object,
) -> dict[SourceName, Any | None]:
    # Deliberately mirrors _sources() but without a storage dependency.
    result = canonical.resultado
    schedule = canonical.cronograma
    productivity = (
        {"eap": canonical.eap, "activities": canonical.atividades, "scheduled": schedule.scheduled_activities}
        if schedule is not None else None
    )
    calendar = (
        {
            "operational": canonical.calendario_operacional,
            "weekly_factor": canonical.fator_calendario_semanal,
            "practicability": canonical.praticabilidade,
        }
        if canonical.calendario_operacional or canonical.fator_calendario_semanal or canonical.praticabilidade
        else None
    )
    pool = (
        {
            "contracts": canonical.contratos_recurso,
            "resource_pool": canonical.recurso_pool,
            "instances": canonical.instancias_recurso,
        }
        if canonical.contratos_recurso or canonical.recurso_pool or canonical.instancias_recurso
        else None
    )
    inventory = (
        {
            "p23_inventory_evidence": canonical.p23_inventory_evidence,
            "p18_preview": canonical.p18_consumption_preview,
            "stock_summary": canonical.resumo_estoque_consumiveis,
            "consumables": canonical.recursos_consumiveis,
        }
        if canonical.p23_inventory_evidence is not None or canonical.p18_consumption_preview is not None or canonical.resumo_estoque_consumiveis
        else None
    )
    ledger = (
        {"p17": canonical.p17_cost_reconciliation, "p20": canonical.p23_inventory_evidence}
        if canonical.p17_cost_reconciliation is not None or canonical.p23_inventory_evidence is not None
        else None
    )
    pricing = (
        {
            "diagnostics": result.pricing_diagnostics,
            "gates": result.pricing_gates,
            "authority": result.pricing_authority,
            "bdi": canonical.tabela_bdi_efetiva,
            "bdi_memorial": canonical.memorial_calculo_bdi,
        }
        if result is not None and (result.pricing_diagnostics or result.pricing_gates)
        else None
    )
    return {
        "canonical": canonical,
        "catalog": catalog if isinstance(catalog, Mapping) and catalog else None,
        "productivity": productivity,
        "calendar": calendar,
        "schedule": (
            {
                "cronograma": schedule,
                "intervals": canonical.intervalos_atividade,
                "physical_witness": canonical.physical_calendar_evidence,
                "constraints": canonical.constraint_violations,
            }
            if schedule is not None else None
        ),
        "pool": pool,
        "inventory": inventory,
        "ledger": ledger,
        "pricing": pricing,
        "solver": {
            "version": version,
            "run_id": run.get("run_id"),
            "base_version": run.get("base_version"),
            "procurement_intent": run.get("procurement_intent"),
            "skill_inputs_override": run.get("skill_inputs_override"),
            "catalog_base_hash": run.get("catalogo_base_hash"),
            "skills_log": run.get("skills_log"),
            "pipeline_integrity": canonical.pipeline_integridade,
            "pipeline_blocked_from": canonical.pipeline_blocked_from,
        },
    }


def certificate_path(version: str, run_id: str) -> str:
    return f"{version}/{_CERTIFICATE_ROOT}/{run_id}.json"


def _summary(record: FormalismCertificateRecord, *, validity: str, **extra: Any) -> dict[str, Any]:
    return {
        "certificate_id": record.certificate_id,
        "decision": record.decision,
        "validity": validity,
        "scope": record.envelope.scope,
        "run_id": record.envelope.run_id,
        "inputs_sha256": record.envelope.inputs_sha256,
        "evaluation_sha256": record.evaluation_sha256,
        "evaluator_version": record.evaluator_version,
        "gates": [item.model_dump(mode="json") for item in record.evaluations],
        **extra,
    }


def issue_certificate(
    project: ProjectHandle,
    *,
    project_id: str,
    version: str,
    run: Mapping[str, Any],
    canonical: CanonicalModel,
    catalog: object,
) -> dict[str, Any]:
    """Persist immutable decision, a lifecycle event and the version index."""
    record = build_run_certificate(
        project_id=project_id,
        version=version,
        run=run,
        canonical=canonical,
        catalog=catalog,
    )
    path = certificate_path(version, record.envelope.run_id)
    project.write_json(path, record.model_dump(mode="json"))
    event = build_certificate_event(event_type="ISSUED", record=record)
    project.append_jsonl(f"{version}/{_CERTIFICATE_EVENTS}", event.model_dump(mode="json"))
    index = {
        "schema": "concilium.p23.certificate-index.v1",
        "latest_run_id": record.envelope.run_id,
        "latest_certificate_id": record.certificate_id,
        "latest_decision": record.decision,
        "validity": "CURRENT",
        "inputs_sha256": record.envelope.inputs_sha256,
    }
    project.write_json(f"{version}/{_CERTIFICATE_ROOT}/latest.json", index)
    return _summary(record, validity="CURRENT")


def _has_invalidation_event(project: ProjectHandle, version: str, certificate_id: str) -> bool:
    raw = project.read_json(f"{version}/{_CERTIFICATE_EVENTS}", [])
    if isinstance(raw, list):
        return any(
            isinstance(row, Mapping)
            and row.get("event_type") == "INVALIDATED"
            and row.get("certificate_id") == certificate_id
            for row in raw
        )
    # JSONL-backed storage may expose no structured list through read_json.
    # In that case the per-run invalidation sidecar below is the idempotency key.
    return bool(project.read_json(
        f"{version}/{_CERTIFICATE_ROOT}/invalidated/{certificate_id}.json",
        None,
    ))


def get_current_certificate(
    project: ProjectHandle,
    *,
    version: str,
    run: Mapping[str, Any],
    canonical: CanonicalModel,
    catalog: object,
) -> dict[str, Any]:
    """Revalidate fingerprints on read; stale historical GO never leaks as current."""
    run_id = str(run.get("run_id") or "")
    raw = project.read_json(certificate_path(version, run_id), None)
    if not isinstance(raw, Mapping):
        raise FileNotFoundError(f"Formalism certificate for run {run_id!r} was not issued")
    record = FormalismCertificateRecord.model_validate(raw)
    source_snapshot = _sources_from_run(
        version=version, run=run, canonical=canonical, catalog=catalog
    )
    if matches_current_sources(record.envelope, source_snapshot):
        return _summary(record, validity="CURRENT")

    observed = build_provisional_certificate(
        project_id=record.envelope.project_id,
        run_id=run_id,
        scope=record.envelope.scope,
        formalism_sha256=FORMALISM_SHA256,
        oracle_sha256=ORACLE_SHA256,
        sources=source_snapshot,
    )
    reason = "one or more material source fingerprints changed since certificate issuance"
    if not _has_invalidation_event(project, version, record.certificate_id):
        event = build_certificate_event(
            event_type="INVALIDATED",
            record=record,
            reason=reason,
            observed_inputs_sha256=observed.inputs_sha256,
        )
        project.append_jsonl(f"{version}/{_CERTIFICATE_EVENTS}", event.model_dump(mode="json"))
        project.write_json(
            f"{version}/{_CERTIFICATE_ROOT}/invalidated/{record.certificate_id}.json",
            event.model_dump(mode="json"),
        )
    index = project.read_json(f"{version}/{_CERTIFICATE_ROOT}/latest.json", {})
    if isinstance(index, dict) and index.get("latest_certificate_id") == record.certificate_id:
        project.write_json(f"{version}/{_CERTIFICATE_ROOT}/latest.json", {
            **index,
            "latest_decision": "NOT_EVALUATED",
            "validity": "INVALIDATED",
            "observed_inputs_sha256": observed.inputs_sha256,
            "invalidation_reason": reason,
        })
    return _summary(
        record,
        validity="INVALIDATED",
        historical_decision=record.decision,
        decision="NOT_EVALUATED",
        invalidation_reason=reason,
        observed_inputs_sha256=observed.inputs_sha256,
    )
