"""P23-C application service: evaluate and persist a source-bound project certificate.

This service deliberately consumes the already materialized P15/P16/P20/P21
witnesses. It does not recalculate domain formulas and never treats absent
catalog, productivity calibration, solver or financial evidence as a success.
"""
from __future__ import annotations

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
        pool_summaries=canonical.resumo_utilizacao_contratos,
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
