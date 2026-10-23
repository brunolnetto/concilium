"""P23-A: deterministic evidence envelope for a future formalism certificate.

An envelope is never an authorization to issue a price or GO: its only
allowed decision is NOT_EVALUATED until the independent P23-B evaluator exists.
Digests bind the mathematical specification and all material input categories.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
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


def _canonical_json(value: Any) -> bytes:
    """Canonical, unambiguous UTF-8 JSON; reject NaN, infinity and unknown types."""
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
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
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
