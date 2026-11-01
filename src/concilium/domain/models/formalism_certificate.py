"""P23-A: deterministic evidence envelope for a future formalism certificate.

An envelope is never an authorization to issue a price or GO: its only
allowed decision is NOT_EVALUATED until the independent P23-B evaluator exists.
Digests bind the mathematical specification and all material input categories.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SourceName = Literal[
    "canonical",
    "catalog",
    "productivity",
    "calendar",
    "schedule",
    "pool",
    "inventory",
    "ledger",
    "pricing",
    "solver",
]
ExecutionScope = Literal["PREVIEW", "RFI", "RFP"]
SourceState = Literal["PRESENT", "UNAVAILABLE"]

REQUIRED_SOURCES: tuple[SourceName, ...] = (
    "canonical",
    "catalog",
    "productivity",
    "calendar",
    "schedule",
    "pool",
    "inventory",
    "ledger",
    "pricing",
    "solver",
)


def _reject_unordered(value: Any) -> None:
    """Do not allow Pydantic JSON conversion to hide sets as unstable lists.

    The *Python-mode* snapshot preserves nested set/frozenset fields, whereas
    model_dump(mode="json") silently serializes them as lists with potentially
    process-dependent order. Reject before that lossy conversion.
    """
    if isinstance(value, BaseModel):
        _reject_unordered(value.model_dump(mode="python"))
    elif isinstance(value, (set, frozenset)):
        raise TypeError("unordered set/frozenset must be normalized before fingerprinting")
    elif isinstance(value, dict):
        for key, item in value.items():
            _reject_unordered(key)
            _reject_unordered(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_unordered(item)


def _canonical_json(value: Any) -> bytes:
    """Canonical UTF-8 JSON; reject nonfinite values and unordered inputs."""
    _reject_unordered(value)
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def fingerprint_source(name: SourceName, value: Any) -> str:
    """Versioned, domain-separated digest of a material source snapshot."""
    return hashlib.sha256(
        b"concilium-formalism-source/v1\n"
        + name.encode("ascii")
        + b"\n"
        + _canonical_json(value)
    ).hexdigest()


class SourceFingerprint(BaseModel):
    """Immutable statement about an available or explicitly unavailable source."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: SourceName
    state: SourceState
    sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_availability(self) -> SourceFingerprint:
        if (self.state == "PRESENT") != (self.sha256 is not None):
            raise ValueError("PRESENT requires digest; UNAVAILABLE forbids digest")
        return self


class FormalismCertificate(BaseModel):
    """Immutable, NOT_EVALUATED-only evidence envelope, not a GO certificate.

    The engine must not infer approval from hashes. P23-B owns mandatory
    gate evaluation and the first possible typed GO/NOGO decision.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1.0.0"] = "1.0.0"
    project_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    scope: ExecutionScope
    formalism_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    oracle_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_fingerprints: tuple[SourceFingerprint, ...]
    inputs_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    decision: Literal["NOT_EVALUATED"] = "NOT_EVALUATED"

    @model_validator(mode="after")
    def validate_contract(self) -> FormalismCertificate:
        keys = tuple(x.name for x in self.source_fingerprints)
        if keys != REQUIRED_SOURCES:
            raise ValueError("source digests must cover each required category in canonical order")
        if self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        expected = fingerprint_inputs(
            self.scope,
            self.formalism_sha256,
            self.oracle_sha256,
            self.source_fingerprints,
        )
        if expected != self.inputs_sha256:
            raise ValueError("input fingerprints do not match the envelope checksum")
        return self


def fingerprint_inputs(
    scope: ExecutionScope,
    formalism_sha256: str,
    oracle_sha256: str,
    fingerprints: tuple[SourceFingerprint, ...],
) -> str:
    """Deterministic aggregate including presence, scope and versioned references."""
    manifest = {
        "schema_version": "1.0.0",
        "scope": scope,
        "formalism_sha256": formalism_sha256,
        "oracle_sha256": oracle_sha256,
        "sources": [entry.model_dump(mode="json") for entry in fingerprints],
    }
    return hashlib.sha256(
        b"concilium-formalism-envelope/v1\n" + _canonical_json(manifest)
    ).hexdigest()


def build_provisional_certificate(
    *,
    project_id: str,
    run_id: str,
    scope: ExecutionScope,
    formalism_sha256: str,
    oracle_sha256: str,
    sources: dict[SourceName, Any | None],
) -> FormalismCertificate:
    """Freeze input evidence without evaluating or authorizing any gate.

    Every category is mandatory. A source not produced in RFI/preview must
    be supplied as explicit None, never silently omitted or replaced by {}.
    """
    if set(sources) != set(REQUIRED_SOURCES):
        raise ValueError("source snapshot must enumerate all ten material categories")
    fingerprints = tuple(
        SourceFingerprint(name=name, state="UNAVAILABLE")
        if sources[name] is None else
        SourceFingerprint(
            name=name, state="PRESENT", sha256=fingerprint_source(name, sources[name])
        )
        for name in REQUIRED_SOURCES
    )
    return FormalismCertificate(
        project_id=project_id,
        run_id=run_id,
        scope=scope,
        formalism_sha256=formalism_sha256,
        oracle_sha256=oracle_sha256,
        source_fingerprints=fingerprints,
        inputs_sha256=fingerprint_inputs(
            scope, formalism_sha256, oracle_sha256, fingerprints
        ),
    )


def matches_current_sources(
    envelope: FormalismCertificate,
    sources: dict[SourceName, Any | None],
) -> bool:
    """Compare live snapshots; missing source categories fail closed."""
    if set(sources) != set(REQUIRED_SOURCES):
        return False
    try:
        digests = tuple(
            SourceFingerprint(name=name, state="UNAVAILABLE")
            if sources[name] is None else
            SourceFingerprint(
                name=name, state="PRESENT",
                sha256=fingerprint_source(name, sources[name]),
            )
            for name in REQUIRED_SOURCES
        )
    except (TypeError, ValueError, OverflowError):
        return False
    return digests == envelope.source_fingerprints


# P23-B: independently evaluated V1-V11 decision record.
GateId = Literal["V1", "V2", "V3", "V4", "V5", "V6", "V7", "V8", "V9", "V10", "V11"]
GateStatus = Literal["PASS", "FAIL", "UNKNOWN", "NOT_EVALUATED"]
CertificateDecision = Literal["GO", "NOGO", "NOT_EVALUATED"]
CertificateEventType = Literal["ISSUED", "INVALIDATED"]

REQUIRED_GATES: tuple[GateId, ...] = (
    "V1", "V2", "V3", "V4", "V5", "V6",
    "V7", "V8", "V9", "V10", "V11",
)


class FormalismGateEvaluation(BaseModel):
    """One versioned, source-bound V1-V11 result.

    PASS requires a SHA-256 of the exact evidence object that was checked.
    Missing or incomplete evidence must be UNKNOWN/NOT_EVALUATED, never PASS.
    A deliberately inapplicable gate still needs a source-bound explanation.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    gate_id: GateId
    status: GateStatus
    evidence_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    applicable: bool = True
    reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_evidence_contract(self) -> FormalismGateEvaluation:
        if self.status == "PASS" and self.evidence_sha256 is None:
            raise ValueError("PASS requires a fingerprint of the exact checked evidence")
        if self.status != "PASS" and not self.reasons:
            raise ValueError("non-PASS gates require explicit reasons")
        if not self.applicable and (self.status != "PASS" or not self.reasons):
            raise ValueError("inapplicable gates require an evidence-backed PASS and explanation")
        return self


def _decision_for(
    scope: ExecutionScope,
    evaluations: tuple[FormalismGateEvaluation, ...],
) -> CertificateDecision:
    """A failure is NOGO; GO is exclusively a complete RFP decision."""
    if any(item.status == "FAIL" for item in evaluations):
        return "NOGO"
    if scope != "RFP" or tuple(item.gate_id for item in evaluations) != REQUIRED_GATES:
        return "NOT_EVALUATED"
    if all(item.status == "PASS" for item in evaluations):
        return "GO"
    return "NOT_EVALUATED"


def _evaluation_digest(
    envelope: FormalismCertificate,
    evaluations: tuple[FormalismGateEvaluation, ...],
    decision: CertificateDecision,
    evaluator_version: str,
) -> str:
    payload = {
        "schema_version": "p23-decision.v1",
        "evaluator_version": evaluator_version,
        "envelope_inputs_sha256": envelope.inputs_sha256,
        "decision": decision,
        "gates": [item.model_dump(mode="json") for item in evaluations],
    }
    return hashlib.sha256(
        b"concilium-formalism-evaluation/v1\n" + _canonical_json(payload)
    ).hexdigest()


class FormalismCertificateRecord(BaseModel):
    """Immutable evaluation result referencing the P23-A source envelope.

    The decision is derived from all eleven required gates. It cannot be set
    independently of the persisted gate results. Invalidation is an appended
    event (below), not an in-place rewrite of this historical record.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["p23-decision.v1"] = "p23-decision.v1"
    certificate_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    envelope: FormalismCertificate
    evaluator_version: Literal["p23-v1"] = "p23-v1"
    evaluations: tuple[FormalismGateEvaluation, ...]
    decision: CertificateDecision
    evaluation_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_record(self) -> FormalismCertificateRecord:
        gate_ids = tuple(item.gate_id for item in self.evaluations)
        if gate_ids != REQUIRED_GATES:
            raise ValueError("certificate must contain exactly V1-V11 in canonical order")
        expected_decision = _decision_for(self.envelope.scope, self.evaluations)
        if self.decision != expected_decision:
            raise ValueError("certificate decision is inconsistent with its gate evaluations")
        expected_digest = _evaluation_digest(
            self.envelope, self.evaluations, self.decision, self.evaluator_version
        )
        if expected_digest != self.evaluation_sha256 or self.certificate_id != expected_digest:
            raise ValueError("certificate checksum does not match its immutable evidence")
        if self.created_at.utcoffset() is None:
            raise ValueError("certificate created_at must be timezone-aware")
        return self


class FormalismCertificateEvent(BaseModel):
    """Append-only lifecycle event; a stale GO remains historical, never current."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    event_type: CertificateEventType
    certificate_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    decision_at_issue: CertificateDecision
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    reason: str | None = None
    observed_inputs_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_event(self) -> FormalismCertificateEvent:
        if self.event_type == "INVALIDATED" and not self.reason:
            raise ValueError("invalidation event requires an explicit reason")
        if self.created_at.utcoffset() is None:
            raise ValueError("certificate event created_at must be timezone-aware")
        return self


def build_formalism_certificate_record(
    envelope: FormalismCertificate,
    evaluations: tuple[FormalismGateEvaluation, ...] | list[FormalismGateEvaluation],
) -> FormalismCertificateRecord:
    """Create a deterministic, fail-closed V1-V11 decision record.

    Missing gates are materialized as NOT_EVALUATED. Duplicate or unordered
    supplied gates are rejected; callers cannot omit a gate to obtain GO.
    """
    supplied = tuple(evaluations)
    supplied_ids = tuple(item.gate_id for item in supplied)
    if len(set(supplied_ids)) != len(supplied_ids):
        raise ValueError("duplicate formalism gate evaluation")
    if tuple(item for item in REQUIRED_GATES if item in supplied_ids) != supplied_ids:
        raise ValueError("formalism gates must be supplied in canonical V1-V11 order")
    by_id = {item.gate_id: item for item in supplied}
    complete = tuple(
        by_id.get(gate_id) or FormalismGateEvaluation(
            gate_id=gate_id,
            status="NOT_EVALUATED",
            reasons=("required evidence was not supplied to the evaluator",),
        )
        for gate_id in REQUIRED_GATES
    )
    decision = _decision_for(envelope.scope, complete)
    digest = _evaluation_digest(envelope, complete, decision, "p23-v1")
    return FormalismCertificateRecord(
        certificate_id=digest,
        envelope=envelope,
        evaluator_version="p23-v1",
        evaluations=complete,
        decision=decision,
        evaluation_sha256=digest,
    )


def build_certificate_event(
    *,
    event_type: CertificateEventType,
    record: FormalismCertificateRecord,
    reason: str | None = None,
    observed_inputs_sha256: str | None = None,
) -> FormalismCertificateEvent:
    """Deterministic event identity; duplicate issuance/invalidation is idempotent."""
    created_at = datetime.now(UTC)
    payload = {
        "event_type": event_type,
        "certificate_id": record.certificate_id,
        "decision_at_issue": record.decision,
        "reason": reason,
        "observed_inputs_sha256": observed_inputs_sha256,
        "created_at": created_at.isoformat(),
    }
    event_id = hashlib.sha256(
        b"concilium-formalism-certificate-event/v1\n" + _canonical_json(payload)
    ).hexdigest()
    return FormalismCertificateEvent(
        event_id=event_id,
        event_type=event_type,
        certificate_id=record.certificate_id,
        decision_at_issue=record.decision,
        created_at=created_at,
        reason=reason,
        observed_inputs_sha256=observed_inputs_sha256,
    )
