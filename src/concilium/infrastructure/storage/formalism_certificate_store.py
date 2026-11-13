"""P23-C: immutable persistence and read-time source-fingerprint invalidation."""
from __future__ import annotations

import hashlib
import re
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from concilium.application.scheduling.formalism_evaluator import FormalismEvaluation
from concilium.domain.models.formalism_certificate import (
    REQUIRED_SOURCES,
    FormalismCertificate,
    SourceName,
    _canonical_json,
    fingerprint_source,
    matches_current_sources,
)


class ProjectJsonStore(Protocol):
    def read_json(self, relative_path: str, default: Any) -> Any: ...
    def write_json(self, relative_path: str, payload: Any) -> None: ...
    def exists(self, relative_path: str) -> bool: ...


class PersistedFormalismEvaluation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal["1.0.0"] = "1.0.0"
    envelope: FormalismCertificate
    evaluation: FormalismEvaluation
    record_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_binding(self) -> PersistedFormalismEvaluation:
        if (
            self.envelope.project_id, self.envelope.run_id, self.envelope.inputs_sha256
        ) != (
            self.evaluation.project_id, self.evaluation.run_id, self.evaluation.inputs_sha256
        ):
            raise ValueError("persisted evaluation does not belong to its evidence envelope")
        if _record_fingerprint(self.envelope, self.evaluation) != self.record_sha256:
            raise ValueError("persisted record checksum mismatch")
        return self


class CertificateReadResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    status: Literal["CURRENT", "INVALIDATED"]
    recorded_decision: Literal["GO", "NOGO", "NOT_CERTIFIABLE"]
    effective_decision: Literal["GO", "NOGO", "NOT_CERTIFIABLE"]
    evaluation: FormalismEvaluation
    record_sha256: str
    invalidated_sources: tuple[str, ...] = ()


def _same_envelope_identity(left: FormalismCertificate, right: FormalismCertificate) -> bool:
    """Compare certificate identity while ignoring non-semantic creation time."""
    return (
        left.project_id == right.project_id
        and left.run_id == right.run_id
        and left.scope == right.scope
        and left.formalism_sha256 == right.formalism_sha256
        and left.oracle_sha256 == right.oracle_sha256
        and left.inputs_sha256 == right.inputs_sha256
        and left.source_fingerprints == right.source_fingerprints
    )


def _record_fingerprint(envelope: FormalismCertificate, evaluation: FormalismEvaluation) -> str:
    value = {
        "schema_version": "1.0.0",
        "envelope": envelope.model_dump(mode="json"),
        "evaluation": evaluation.model_dump(mode="json"),
    }
    return hashlib.sha256(b"concilium-formalism-persisted-record/v1\n" + _canonical_json(value)).hexdigest()


def _record_path(run_id: str, evaluation_sha256: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", run_id):
        raise ValueError("run_id contains unsafe path characters")
    if not re.fullmatch(r"[a-f0-9]{64}", evaluation_sha256):
        raise ValueError("evaluation fingerprint must be a lowercase SHA-256 digest")
    return f"formalism_certificates/{run_id}/{evaluation_sha256}.json"


def persist_formalism_evaluation(
    project: ProjectJsonStore,
    envelope: FormalismCertificate,
    evaluation: FormalismEvaluation,
) -> PersistedFormalismEvaluation:
    """Persist by content-addressed key; identical writes are idempotent, changes conflict."""
    if (
        envelope.project_id, envelope.run_id, envelope.inputs_sha256
    ) != (
        evaluation.project_id, evaluation.run_id, evaluation.inputs_sha256
    ):
        raise ValueError("evaluation/envelope project, run or input fingerprint mismatch")
    record = PersistedFormalismEvaluation(
        envelope=envelope,
        evaluation=evaluation,
        record_sha256=_record_fingerprint(envelope, evaluation),
    )
    path = _record_path(envelope.run_id, evaluation.evaluation_sha256)
    payload = record.model_dump(mode="json")
    if project.exists(path):
        existing_payload = project.read_json(path, None)
        try:
            existing = PersistedFormalismEvaluation.model_validate(existing_payload)
        except ValidationError as exc:
            raise ValueError("existing persisted certificate checksum/integrity validation failed") from exc
        # evaluated_at is an audit timestamp, not part of evaluation identity.
        # Re-evaluating identical evidence is idempotent and keeps the first record.
        if (
            _same_envelope_identity(existing.envelope, envelope)
            and existing.evaluation.evaluation_sha256 == evaluation.evaluation_sha256
            and existing.evaluation.decision == evaluation.decision
        ):
            return existing
        raise RuntimeError("immutable certificate record already exists with different content")
    project.write_json(path, payload)
    if project.read_json(path, None) != payload:
        raise RuntimeError("certificate persistence read-after-write verification failed")
    return record


def read_formalism_evaluation(
    project: ProjectJsonStore,
    *,
    run_id: str,
    evaluation_sha256: str,
    current_sources: dict[SourceName, Any | None],
    current_formalism_sha256: str,
    current_oracle_sha256: str,
) -> CertificateReadResult | None:
    """Reload after restart and downgrade stale records before any caller can present GO."""
    path = _record_path(run_id, evaluation_sha256)
    payload = project.read_json(path, None)
    if payload is None:
        return None
    try:
        record = PersistedFormalismEvaluation.model_validate(payload)
    except ValidationError as exc:
        raise ValueError("persisted certificate checksum/integrity validation failed") from exc
    if record.envelope.run_id != run_id:
        raise ValueError("persisted record run ID does not match lookup")

    current_match = (
        set(current_sources) == set(REQUIRED_SOURCES)
        and matches_current_sources(record.envelope, current_sources)
        and record.envelope.formalism_sha256 == current_formalism_sha256
        and record.envelope.oracle_sha256 == current_oracle_sha256
    )
    old_by_name = {item.name: item for item in record.envelope.source_fingerprints}
    changed: list[str] = []
    if set(current_sources) != set(REQUIRED_SOURCES):
        changed.append("source_manifest")
    if record.envelope.formalism_sha256 != current_formalism_sha256:
        changed.append("formalism")
    if record.envelope.oracle_sha256 != current_oracle_sha256:
        changed.append("oracle")
    for name in REQUIRED_SOURCES:
        if name not in current_sources:
            changed.append(name)
            continue
        value = current_sources[name]
        new_state = "UNAVAILABLE" if value is None else "PRESENT"
        new_digest = None if value is None else fingerprint_source(name, value)
        old = old_by_name[name]
        if old.state != new_state or old.sha256 != new_digest:
            changed.append(name)

    status: Literal["CURRENT", "INVALIDATED"] = "CURRENT" if current_match else "INVALIDATED"
    effective = record.evaluation.decision if current_match else "NOT_CERTIFIABLE"
    return CertificateReadResult(
        status=status,
        recorded_decision=record.evaluation.decision,
        effective_decision=effective,
        evaluation=record.evaluation,
        record_sha256=record.record_sha256,
        invalidated_sources=tuple(changed),
    )
