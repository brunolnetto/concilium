"""P23-C application service: evaluate and persist a source-bound project certificate.

This service deliberately consumes the already materialized P15/P16/P20/P21
witnesses. It does not recalculate domain formulas and never treats absent
catalog, productivity calibration, solver or financial evidence as a success.
"""
from __future__ import annotations

import hashlib
import json
import math

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from fractions import Fraction
from pathlib import Path
from typing import Any

from concilium.application.scheduling.formalism_evaluator import (
    FormalismEvaluation,
    ProductivityRateWitness,
    evaluate_project_evidence,
)
from concilium.domain.models.canonical import CanonicalModel
from concilium.domain.models.formalism_certificate import (
    ExecutionScope,
    FormalismCertificate,
    SourceName,
    build_provisional_certificate,
)
from concilium.infrastructure.storage.formalism_certificate_store import (
    CertificateReadResult,
    PersistedFormalismEvaluation,
    persist_formalism_evaluation,
    read_formalism_evaluation,
)


# Pinned content identities of the normative specifications and independent
# reference implementations/vectors. #26 owns the drift check.
_FORMALISM_REFERENCE = (
    "long:f83d37c03b3dbcebc0cbb446cc6d4333fa05cdd5;"
    "resumido:7cc825e9af2de9d84af7fa2c2036f164db834cf5"
)
_ORACLE_REFERENCE = (
    "physical-reference:570e73eef9ef3e74f2249d263e9b652035966a98;"
    "economic-reference:c3fd324ba86c89ef849b9dd6b0f07aa1814a3eed;"
    "physical-vector:dda8e8117de996856a14ffa47e848344370d8b06;"
    "economic-vector:cef850620b8d2267228e8321cbbf923593e9f891;"
    "calendar-oracle:31fd9174ec88968da2130e1a0ceb93351df65ff5"
)
FORMALISM_SHA256 = hashlib.sha256(_FORMALISM_REFERENCE.encode("ascii")).hexdigest()
ORACLE_SHA256 = hashlib.sha256(_ORACLE_REFERENCE.encode("ascii")).hexdigest()


def _catalog_items(resolved_catalog: Mapping[str, Any] | None) -> dict[str, list[dict[str, Any]]] | None:
    """Normalize the immutable per-run catalog payload; never fall back to master."""
    if not isinstance(resolved_catalog, Mapping):
        return None
    items = resolved_catalog.get("items", resolved_catalog)
    if not isinstance(items, Mapping):
        return None
    normalized: dict[str, list[dict[str, Any]]] = {}
    for key in ("cpus", "insumos", "producoes"):
        value = items.get(key)
        if not isinstance(value, list) or any(not isinstance(row, Mapping) for row in value):
            return None
        normalized[key] = [dict(row) for row in value]
    return normalized


def load_resolved_catalog_snapshot(
    project: Any,
    version: str,
    run_id: str | None = None,
) -> dict[str, Any] | None:
    """Read only the exact run-pinned resolved_catalog.json snapshot."""
    try:
        payload = project.read_json(f"{version}/resolved_catalog.json", None)
    except Exception:
        return None
    if not isinstance(payload, Mapping):
        return None
    if payload.get("version") != version:
        return None
    if run_id is not None and payload.get("run_id") != run_id:
        return None
    normalized = _catalog_items(payload)
    if normalized is None:
        return None
    return {
        **normalized,
        "catalogo_base_origem": payload.get("catalogo_base_origem"),
        "catalogo_base_hash": payload.get("catalogo_base_hash"),
        "resolution_trace": payload.get("resolution_trace"),
        "catalogo_id": payload.get("catalogo_id"),
        "jurisdicao_id": payload.get("jurisdicao_id"),
        "run_id": payload.get("run_id"),
        "version": payload.get("version"),
    }


def _finite_rate_text(value: object) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        if not math.isfinite(float(value)) or value < 0:
            return None
    except (OverflowError, ValueError):
        return None
    return str(value)


def build_productivity_rate_witnesses(
    canonical: CanonicalModel,
    resolved_catalog: Mapping[str, Any] | None,
) -> tuple[ProductivityRateWitness, ...] | None:
    """Bind each EAP item to final weekly F(m) cells and its versioned source.

    A calibration reference is emitted only for graph-backed, versioned production
    records with an explicit origin type and quality sample record. Legacy,
    estimated, assumed and fallback rates remain unverified.
    """
    catalog = _catalog_items(resolved_catalog)
    schedule = canonical.cronograma
    if catalog is None or schedule is None or not schedule.scheduled_activities:
        return None

    cpu_by_id = {
        row.get("codigo"): row for row in catalog["cpus"]
        if isinstance(row.get("codigo"), str) and row.get("codigo")
    }
    production_by_id = {
        row.get("id"): row for row in catalog["producoes"]
        if isinstance(row.get("id"), str) and row.get("id")
    }
    scheduled_by_item = {row.activity_id: row for row in schedule.scheduled_activities}
    if len(scheduled_by_item) != len(schedule.scheduled_activities):
        return None
    if set(scheduled_by_item) != {item.item_id for item in canonical.eap}:
        return None

    witnesses: list[ProductivityRateWitness] = []
    for item in canonical.eap:
        scheduled = scheduled_by_item[item.item_id]
        cells = getattr(scheduled, "distribuicao_semanal", None) or {}
        active = {
            week: cell for week, cell in cells.items()
            if cell.num_equipes > 0
            and cell.fator_clima * cell.fator_calendario * cell.fator_jornada > 0
        }
        if not active:
            return None

        weekly_rates: dict[str, str] = {}
        origins: set[str] = set()
        for week, cell in sorted(active.items()):
            rate = _finite_rate_text(cell.produtividade_fisica_horaria)
            if rate is None:
                return None
            weekly_rates[week] = rate
            origins.add(str(cell.origem_produtividade))
        origin = next(iter(origins)) if len(origins) == 1 else "NAO_DECLARADA"
        if origin not in {
            "GRAFO_FLUXO", "GRAFO_ELEMENTOS",
            "TAXA_POR_FRENTE_ASSUMIDA", "FALLBACK_ARBITRARIO", "NAO_DECLARADA",
        }:
            origin = "NAO_DECLARADA"

        cpu = cpu_by_id.get(item.cpu_id)
        production_id = cpu.get("producao_id_ref") if isinstance(cpu, Mapping) else None
        production = production_by_id.get(production_id)
        source_reference: str | None = None
        calibration_reference: str | None = None
        if isinstance(production, Mapping):
            origin_data = production.get("origem")
            audit_data = production.get("auditoria")
            quality = production.get("qualidade")
            graph = production.get("grafo_sinergia")
            if isinstance(origin_data, Mapping):
                source_id = origin_data.get("fonte_id")
                source_type = origin_data.get("tipo")
                source_date = origin_data.get("data_calibracao")
                source_ref = origin_data.get("referencia")
                if all(isinstance(value, str) and value.strip() for value in (
                    source_id, source_type, source_date, source_ref,
                )):
                    source_reference = f"{source_id}|{source_type}|{source_date}|{source_ref}"
            if (
                origin in {"GRAFO_FLUXO", "GRAFO_ELEMENTOS"}
                and isinstance(graph, Mapping) and bool(graph)
                and isinstance(audit_data, Mapping)
                and isinstance(audit_data.get("versao"), str)
                and audit_data.get("versao", "").strip()
                and isinstance(quality, Mapping)
                and type(quality.get("quantidade_amostras")) is int
                and quality.get("quantidade_amostras", 0) > 0
                and type(quality.get("confianca_pct")) is int
                and quality.get("confianca_pct", 0) > 0
                and isinstance(origin_data, Mapping)
                and origin_data.get("tipo") in {"calibrado_contra_obra_real", "tabela_referencia"}
                and source_reference
            ):
                calibration_payload = {
                    "production_id": production_id,
                    "version": audit_data["versao"],
                    "production": dict(production),
                }
                calibration_bytes = json.dumps(
                    _dump(calibration_payload), sort_keys=True,
                    separators=(",", ":"), ensure_ascii=False, allow_nan=False,
                ).encode("utf-8")
                calibration_reference = (
                    f"production:{production_id}:version:{audit_data['versao']}:"
                    f"sha256:{hashlib.sha256(calibration_bytes).hexdigest()}"
                )

        witnesses.append(ProductivityRateWitness(
            activity_id=item.item_id,
            hourly_rate=min(weekly_rates.values(), key=lambda value: Fraction(value)),
            weekly_rates=weekly_rates,
            origin=origin,
            source_reference=source_reference,
            calibration_reference=calibration_reference,
        ))
    return tuple(witnesses)


def build_solver_context(
    run: Mapping[str, Any],
    version: str,
    canonical: CanonicalModel,
) -> dict[str, Any] | None:
    """Return exact run-scoped inputs and P15 search proof."""
    if not version or not isinstance(run.get("run_id"), str):
        return None
    overrides = run.get("skill_inputs_override")
    if not isinstance(overrides, Mapping):
        return None
    return {
        "run_id": run.get("run_id"),
        "version": version,
        "base_version": run.get("base_version"),
        "procurement_intent": run.get("procurement_intent"),
        "catalogo_base_origem": run.get("catalogo_base_origem"),
        "catalogo_base_hash": run.get("catalogo_base_hash"),
        "use_strict_catalog_baseline": run.get("use_strict_catalog_baseline"),
        "use_mobilizacao_policy": run.get("use_mobilizacao_policy"),
        "skill_inputs_override": dict(overrides),
        "cronograma_algorithm": (
            canonical.cronograma.algorithm if canonical.cronograma is not None else None
        ),
        "physical_resolution": _dump(canonical.p15_physical_resolution),
        "pipeline_integrity": canonical.pipeline_integridade,
        "pipeline_blocked_from": list(canonical.pipeline_blocked_from),
    }


def certificate_scope_for_run(run: Mapping[str, Any]) -> ExecutionScope:
    intent = str(run.get("procurement_intent") or "rfi").strip().upper()
    return "RFP" if intent == "RFP" else "RFI" if intent == "RFI" else "PREVIEW"


def certificate_summary(result: CertificateReadResult | None) -> dict[str, Any]:
    """Expose current/historical decision plus per-gate evidence to all consumers."""
    payload = certificate_presentation_payload(result)
    if result is None:
        return {
            **payload,
            "scope": None,
            "reasons": ["formalism certificate has not been evaluated for this run"],
            "gates": [],
        }
    return {
        **payload,
        "scope": result.evaluation.scope,
        "reasons": list(result.evaluation.reasons),
        "gates": [gate.model_dump(mode="json") for gate in result.evaluation.gate_evidence],
    }


def _dump(value: Any) -> Any:
    """Convert source snapshots to deterministic JSON-safe primitives."""
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return _dump(value.model_dump(mode="json"))
    if isinstance(value, Enum):
        return _dump(value.value)
    if isinstance(value, (Fraction, Decimal)):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _dump(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_dump(item) for item in value]
    return value


def build_formalism_source_snapshot(
    canonical: CanonicalModel,
    *,
    resolved_catalog: Mapping[str, Any] | None,
    productivity_witnesses: Sequence[ProductivityRateWitness] | None,
    solver_context: Mapping[str, Any] | None,
) -> dict[SourceName, Any | None]:
    """Create the exact ten-source manifest used by both issuance and read-time invalidation.

    `schedule` deliberately uses the same projection as P15's schedule_sha256.
    `productivity_witnesses` and `solver_context` must be supplied by the trusted
    orchestration boundary; no values are inferred from a user-facing report.
    """
    result = canonical.resultado
    cronograma = _dump(canonical.cronograma)
    pricing = None if result is None else {
        "diagnostics": _dump(result.pricing_diagnostics),
        "gates": _dump(result.pricing_gates),
    }
    ledger = None if result is None else _dump(result.p20_financial_reconciliation)
    pool = {
        "recurso_pool": _dump(canonical.recurso_pool),
        "contratos_recurso": _dump(canonical.contratos_recurso),
        "cadeias_perpetuacao": _dump(canonical.cadeias_perpetuacao),
        "instancias_recurso": _dump(canonical.instancias_recurso),
        "resumo_utilizacao_contratos": _dump(canonical.resumo_utilizacao_contratos),
    }
    inventory_scope = None
    if result is not None and isinstance(result.pricing_diagnostics, Mapping):
        inventory_scope = {
            key: result.pricing_diagnostics.get(key)
            for key in (
                "inventory_scope_status", "inventory_scope_source",
                "inventory_scope_reference_id", "inventory_scope_fingerprint",
            )
        }
    inventory = {
        "recursos_consumiveis": _dump(canonical.recursos_consumiveis),
        "resumo_estoque_consumiveis": _dump(canonical.resumo_estoque_consumiveis),
        "p18_consumption_preview": _dump(canonical.p18_consumption_preview),
        "inventory_scope": inventory_scope,
    }
    productivity_value = None if productivity_witnesses is None else [
        witness.model_dump(mode="json") for witness in productivity_witnesses
    ]
    solver_value = None if solver_context is None else _dump(solver_context)
    return {
        "canonical": _dump(canonical),
        "catalog": _dump(resolved_catalog),
        "productivity": productivity_value,
        "calendar": {
            "calendario_operacional": _dump(canonical.calendario_operacional),
            "fator_calendario_semanal": _dump(canonical.fator_calendario_semanal),
        },
        # Must match fingerprint_source("schedule", {"cronograma": ...}) in Skill 04.
        "schedule": None if cronograma is None else {"cronograma": cronograma},
        "pool": pool if canonical.contratos_recurso or canonical.resumo_utilizacao_contratos else None,
        "inventory": inventory if canonical.recursos_consumiveis or canonical.resumo_estoque_consumiveis or inventory_scope else None,
        "ledger": ledger,
        "pricing": pricing,
        "solver": solver_value,
    }


def build_pool_summaries(canonical: CanonicalModel) -> tuple[dict[str, Any], ...]:
    """Bind each utilization summary to the exact P16 witness for that contract."""
    contracts = {
        contract.contrato_id: contract
        for contract in (canonical.contratos_recurso or [])
    }
    if len(contracts) != len(canonical.contratos_recurso or []):
        return ()
    summaries: list[dict[str, Any]] = []
    for summary in canonical.resumo_utilizacao_contratos or []:
        if hasattr(summary, "model_dump"):
            row = summary.model_dump(mode="json")
        elif isinstance(summary, Mapping):
            row = dict(summary)
        elif hasattr(summary, "__dict__"):
            row = dict(vars(summary))
        else:
            return ()
        contract_id = row.get("contrato_id")
        contract = contracts.get(contract_id)
        if contract is None:
            row["p16_global_assignment"] = None
        else:
            row["p16_global_assignment"] = _dump(contract.p16_global_assignment)
        summaries.append(row)
    return tuple(summaries)


def evaluate_and_persist_project_certificate(
    project: Any,
    canonical: CanonicalModel,
    *,
    project_id: str,
    run_id: str,
    scope: ExecutionScope,
    formalism_sha256: str,
    oracle_sha256: str,
    resolved_catalog: Mapping[str, Any] | None,
    productivity_witnesses: Sequence[ProductivityRateWitness] | None,
    solver_context: Mapping[str, Any] | None,
) -> tuple[FormalismCertificate, FormalismEvaluation, PersistedFormalismEvaluation]:
    """Evaluate and persist an immutable certificate record under ProjectHandle JSON storage."""
    sources = build_formalism_source_snapshot(
        canonical,
        resolved_catalog=resolved_catalog,
        productivity_witnesses=productivity_witnesses,
        solver_context=solver_context,
    )
    envelope = build_provisional_certificate(
        project_id=project_id,
        run_id=run_id,
        scope=scope,
        formalism_sha256=formalism_sha256,
        oracle_sha256=oracle_sha256,
        sources=sources,
    )
    reconciliation = None if canonical.resultado is None else canonical.resultado.p20_financial_reconciliation
    pricing_diagnostics = None if canonical.resultado is None else canonical.resultado.pricing_diagnostics
    pricing_gates = None if canonical.resultado is None else canonical.resultado.pricing_gates
    evaluation = evaluate_project_evidence(
        envelope,
        physical_resolution=canonical.p15_physical_resolution,
        pool_summaries=build_pool_summaries(canonical),
        productivity_witnesses=productivity_witnesses,
        expected_activity_ids=[item.item_id for item in canonical.eap],
        financial_reconciliation=reconciliation,
        pricing_diagnostics=pricing_diagnostics,
        pricing_gates=pricing_gates,
    )
    persisted = persist_formalism_evaluation(project, envelope, evaluation)
    return envelope, evaluation, persisted


def read_current_project_certificate(
    project: Any,
    *,
    run_id: str,
    evaluation_sha256: str,
    canonical: CanonicalModel,
    resolved_catalog: Mapping[str, Any] | None,
    productivity_witnesses: Sequence[ProductivityRateWitness] | None,
    solver_context: Mapping[str, Any] | None,
    current_formalism_sha256: str,
    current_oracle_sha256: str,
) -> CertificateReadResult | None:
    """Read after process restart; source mutation downgrades any old GO before presentation."""
    current_sources = build_formalism_source_snapshot(
        canonical,
        resolved_catalog=resolved_catalog,
        productivity_witnesses=productivity_witnesses,
        solver_context=solver_context,
    )
    return read_formalism_evaluation(
        project,
        run_id=run_id,
        evaluation_sha256=evaluation_sha256,
        current_sources=current_sources,
        current_formalism_sha256=current_formalism_sha256,
        current_oracle_sha256=current_oracle_sha256,
    )


def certificate_presentation_payload(result: CertificateReadResult | None) -> dict[str, Any]:
    """Shared API/MCP/UI projection; only a current persisted GO may set project_go=True."""
    if result is None:
        return {
            "status": "NOT_FOUND",
            "recorded_decision": None,
            "effective_decision": "NOT_CERTIFIABLE",
            "project_go": False,
        }
    current_go = result.status == "CURRENT" and result.effective_decision == "GO"
    return {
        "status": result.status,
        "recorded_decision": result.recorded_decision,
        "effective_decision": result.effective_decision,
        "project_go": current_go,
        "invalidated_sources": list(result.invalidated_sources),
        "evaluation_sha256": result.evaluation.evaluation_sha256,
        "record_sha256": result.record_sha256,
    }
