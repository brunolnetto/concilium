"""P23-B: fail-closed aggregation of independently produced formalism evidence.

This module is deliberately an adapter/aggregator. It does not recalculate RCPSP,
production, pool allocation, stock, the P17-P20 journals, or BDI formulas. Those
remain owned by the corresponding domain validators. A GO is possible only for
an RFP with a complete source envelope and PASS evidence for every gate.
"""
from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from fractions import Fraction
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from concilium.domain.models.formalism_certificate import (
    REQUIRED_SOURCES,
    FormalismCertificate,
    SourceFingerprint,
    _canonical_json,
)

GateId = Literal[
    "V1", "V2", "V3", "V4", "V5", "V6",
    "FINANCIAL_COST_RECONCILIATION", "PRICE_PRESENT",
    "REGULATORY_BDI_BASIS", "PROFITABILITY", "PRODUCTIVITY_PROVENANCE",
]
GateStatus = Literal["PASS", "FAIL", "UNKNOWN", "NOT_EVALUATED"]
Decision = Literal["GO", "NOGO", "NOT_CERTIFIABLE"]

REQUIRED_GATES: tuple[GateId, ...] = (
    "V1", "V2", "V3", "V4", "V5", "V6",
    "FINANCIAL_COST_RECONCILIATION", "PRICE_PRESENT",
    "REGULATORY_BDI_BASIS", "PROFITABILITY", "PRODUCTIVITY_PROVENANCE",
)

GATE_SOURCES: dict[GateId, tuple[str, ...]] = {
    "V1": ("canonical", "productivity", "calendar", "schedule"),
    "V2": ("catalog", "ledger", "pricing"),
    "V3": ("pool",),
    "V4": ("ledger", "pricing"),
    "V5": ("canonical", "catalog", "productivity"),
    "V6": ("calendar", "schedule", "pool", "solver"),
    "FINANCIAL_COST_RECONCILIATION": ("pool", "inventory", "ledger"),
    "PRICE_PRESENT": ("catalog", "ledger", "pricing"),
    "REGULATORY_BDI_BASIS": ("catalog", "pricing"),
    "PROFITABILITY": ("ledger", "pricing"),
    "PRODUCTIVITY_PROVENANCE": ("catalog", "productivity"),
}


class ProductivityRateWitness(BaseModel):
    """One activity's source-backed hourly rate used by the V5/provenance gates.

    `calibration_reference` must identify the versioned calibration or approved
    first-principles source. A positive rate with an arbitrary/legacy fallback is
    not enough to certify a project.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    activity_id: str = Field(min_length=1)
    hourly_rate: str
    origin: Literal[
        "GRAFO_FLUXO", "GRAFO_ELEMENTOS", "TAXA_POR_FRENTE_ASSUMIDA",
        "FALLBACK_ARBITRARIO", "NAO_DECLARADA",
    ]
    source_reference: str | None = None
    calibration_reference: str | None = None

    @model_validator(mode="after")
    def validate_rate(self) -> ProductivityRateWitness:
        try:
            rate = Fraction(self.hourly_rate)
        except (ValueError, ZeroDivisionError) as exc:
            raise ValueError("hourly_rate must be an exact rational string") from exc
        if rate < 0:
            raise ValueError("hourly_rate cannot be negative")
        for name in ("source_reference", "calibration_reference"):
            value = getattr(self, name)
            if value is not None and not value.strip():
                raise ValueError(f"{name} cannot be blank")
        return self


class GateEvidence(BaseModel):
    """One independently produced gate result tied to the envelope's exact digests."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    gate_id: GateId
    status: GateStatus
    source_fingerprints: tuple[SourceFingerprint, ...]
    artifact_refs: tuple[str, ...] = ()
    observed: dict[str, Any] = Field(default_factory=dict)
    expected: dict[str, Any] = Field(default_factory=dict)
    tolerance: str | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def validate_evidence(self) -> GateEvidence:
        expected_names = tuple(name for name in REQUIRED_SOURCES if name in GATE_SOURCES[self.gate_id])
        actual_names = tuple(item.name for item in self.source_fingerprints)
        if actual_names != expected_names:
            raise ValueError(f"{self.gate_id} must fingerprint exactly its required sources in canonical order")
        if self.status == "PASS":
            if any(item.state != "PRESENT" for item in self.source_fingerprints):
                raise ValueError("a gate cannot PASS when any required source is UNAVAILABLE")
            if not self.artifact_refs:
                raise ValueError("PASS evidence requires at least one immutable artifact reference")
            if self.reason:
                raise ValueError("PASS evidence must not carry a failure reason")
        elif not self.reason or not self.reason.strip():
            raise ValueError(f"{self.status} evidence requires an explicit reason")
        _canonical_json(self.observed)
        _canonical_json(self.expected)
        if self.tolerance is not None and not self.tolerance.strip():
            raise ValueError("tolerance must be nonempty when supplied")
        if any(not ref.strip() for ref in self.artifact_refs):
            raise ValueError("artifact references must be nonempty")
        return self


class FormalismEvaluation(BaseModel):
    """Deterministic run decision bound to one immutable evidence envelope."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1.0.0"] = "1.0.0"
    project_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    scope: Literal["PREVIEW", "RFI", "RFP"]
    inputs_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    decision: Decision
    gate_evidence: tuple[GateEvidence, ...]
    reasons: tuple[str, ...] = ()
    evaluation_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_evaluation(self) -> FormalismEvaluation:
        if self.evaluated_at.utcoffset() is None:
            raise ValueError("evaluated_at must be timezone-aware")
        if tuple(item.gate_id for item in self.gate_evidence) != REQUIRED_GATES:
            raise ValueError("evaluation must contain every mandatory gate in canonical order")
        if len(set(self.reasons)) != len(self.reasons):
            raise ValueError("evaluation reasons must be unique")
        expected = _evaluation_fingerprint(
            project_id=self.project_id, run_id=self.run_id, scope=self.scope,
            inputs_sha256=self.inputs_sha256, decision=self.decision,
            gate_evidence=self.gate_evidence, reasons=self.reasons,
        )
        if expected != self.evaluation_sha256:
            raise ValueError("evaluation fingerprint does not match its immutable content")
        return self


def _evidence_from_envelope(envelope: FormalismCertificate, gate_id: GateId) -> tuple[SourceFingerprint, ...]:
    required = set(GATE_SOURCES[gate_id])
    return tuple(item for item in envelope.source_fingerprints if item.name in required)


def _artifact_refs(envelope: FormalismCertificate, gate_id: GateId) -> tuple[str, ...]:
    """Stable content references; never use filenames or mutable display labels."""
    refs = []
    for item in _evidence_from_envelope(envelope, gate_id):
        if item.sha256:
            refs.append(f"{item.name}:sha256:{item.sha256}")
    return tuple(refs)


def gate_evidence_from_status(
    envelope: FormalismCertificate,
    gate_id: GateId,
    status: GateStatus,
    *,
    artifact_refs: tuple[str, ...] | None = None,
    observed: dict[str, Any] | None = None,
    expected: dict[str, Any] | None = None,
    tolerance: str | None = None,
    reason: str | None = None,
) -> GateEvidence:
    """Bind a verifier status to exact source digests from the envelope."""
    return GateEvidence(
        gate_id=gate_id,
        status=status,
        source_fingerprints=_evidence_from_envelope(envelope, gate_id),
        artifact_refs=artifact_refs if artifact_refs is not None else _artifact_refs(envelope, gate_id),
        observed=observed or {}, expected=expected or {}, tolerance=tolerance, reason=reason,
    )


def _audit_status(audit: Any | None, prefix: str) -> tuple[GateStatus, tuple[str, ...], str | None]:
    if audit is None or not hasattr(audit, "violations"):
        return "UNKNOWN", (), "independent P15 physical audit is unavailable"
    rows = [v for v in audit.violations if str(getattr(v, "code", "")).startswith(prefix)]
    failed = [v for v in rows if not str(getattr(v, "code", "")).endswith("_UNVERIFIED")]
    unknown = [v for v in rows if str(getattr(v, "code", "")).endswith("_UNVERIFIED")]
    details = tuple(
        f"{getattr(v, 'code', 'UNKNOWN')}:{getattr(v, 'item_id', '')}:"
        f"{getattr(v, 'week', None)}:{getattr(v, 'reason', '')}"
        for v in rows
    )
    if failed:
        return "FAIL", details, "; ".join(details)
    if unknown:
        return "UNKNOWN", details, "; ".join(details)
    if getattr(audit, "status", None) == "PASS":
        return "PASS", details, None
    if getattr(audit, "status", None) == "FAIL":
        # A different V1/V6 family can fail while this family independently
        # passes. Unknown validator codes must not be treated as a clean result.
        known_other_family = all(
            str(getattr(v, "code", "")).startswith(("V1_", "V6_"))
            for v in audit.violations
        )
        if rows == [] and known_other_family and audit.violations:
            return "PASS", details, None
        return "UNKNOWN", details, f"physical audit failed without a conclusive {prefix} result"
    return "UNKNOWN", details, "physical audit did not produce PASS"


def _read(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def _pool_standby_status(pool_summaries: Sequence[Any] | None) -> tuple[GateStatus, dict[str, Any], str | None]:
    if not pool_summaries:
        return "UNKNOWN", {}, "P16 pool utilization summaries are missing"
    observed: dict[str, Any] = {}
    violations: list[str] = []
    for row in pool_summaries:
        contract_id = _read(row, "contrato_id")
        available = _read(row, "machine_weeks_disponiveis")
        standby = _read(row, "machine_weeks_standby")
        if not isinstance(contract_id, str) or not contract_id:
            return "UNKNOWN", observed, "pool summary has no stable contract identity"
        if type(available) is not int or type(standby) is not int or available <= 0 or standby < 0:
            return "UNKNOWN", observed, f"{contract_id}: invalid or absent machine-week denominator"
        observed[contract_id] = {"available": available, "standby": standby}
        if standby >= available:
            violations.append(f"{contract_id}: standby={standby}/{available} (100% standby or greater)")
    if violations:
        return "FAIL", observed, "; ".join(violations)
    return "PASS", observed, None


def _productivity_status(
    witnesses: Sequence[ProductivityRateWitness] | None,
    expected_activity_ids: Sequence[str] | None,
) -> tuple[GateStatus, dict[str, Any], str | None]:
    if not witnesses:
        return "UNKNOWN", {}, "no per-activity productivity witnesses were supplied"
    indexed = {row.activity_id: row for row in witnesses}
    if len(indexed) != len(witnesses):
        return "FAIL", {}, "duplicate activity productivity witness identity"
    expected = set(expected_activity_ids or ())
    if expected and set(indexed) != expected:
        missing = sorted(expected - set(indexed))
        extra = sorted(set(indexed) - expected)
        return "UNKNOWN", {"missing": missing, "extra": extra}, "productivity witness does not cover the full EAP activity set"
    failures: list[str] = []
    unknowns: list[str] = []
    observed: dict[str, Any] = {}
    for activity_id, row in sorted(indexed.items()):
        rate = Fraction(row.hourly_rate)
        observed[activity_id] = {
            "hourly_rate": row.hourly_rate, "origin": row.origin,
            "source_reference": row.source_reference,
            "calibration_reference": row.calibration_reference,
        }
        if row.origin in {"FALLBACK_ARBITRARIO", "TAXA_POR_FRENTE_ASSUMIDA"}:
            failures.append(f"{activity_id}: fallback/assumed productivity is not certifiable")
        elif row.origin == "NAO_DECLARADA" or not row.source_reference:
            unknowns.append(f"{activity_id}: productivity origin/source is not declared")
        elif rate <= 0:
            failures.append(f"{activity_id}: hourly productivity must be > 0 (observed {row.hourly_rate})")
        elif not row.calibration_reference:
            unknowns.append(f"{activity_id}: no versioned calibration/source reference")
    if failures:
        return "FAIL", observed, "; ".join(failures + unknowns)
    if unknowns:
        return "UNKNOWN", observed, "; ".join(unknowns)
    return "PASS", observed, None


def _as_fraction(value: Any, label: str) -> 