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
            