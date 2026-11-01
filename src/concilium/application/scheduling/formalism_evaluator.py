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
    """Bind a verifier status to exact source digests from the envelope.

    A positive verifier result is automatically downgraded when one of its
    required source objects was unavailable in the immutable envelope. That is
    NOT_CERTIFIABLE, not an exception and certainly not a pass.
    """
    source_fingerprints = _evidence_from_envelope(envelope, gate_id)
    if status == "PASS":
        unavailable = [item.name for item in source_fingerprints if item.state != "PRESENT"]
        if unavailable:
            status = "UNKNOWN"
            reason = "required gate sources unavailable: " + ", ".join(unavailable)
            artifact_refs = ()
    return GateEvidence(
        gate_id=gate_id,
        status=status,
        source_fingerprints=source_fingerprints,
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
        if rate <= 0:
            failures.append(f"{activity_id}: hourly productivity must be > 0 (observed {row.hourly_rate})")
        elif row.origin == "FALLBACK_ARBITRARIO":
            failures.append(f"{activity_id}: arbitrary preview fallback is never certifiable")
        elif row.origin == "TAXA_POR_FRENTE_ASSUMIDA":
            unknowns.append(
                f"{activity_id}: assumed per-front rate has no independently verified calibration artifact"
            )
        elif row.origin == "NAO_DECLARADA" or not row.source_reference:
            unknowns.append(f"{activity_id}: productivity origin/source is not declared")
        elif not row.calibration_reference:
            unknowns.append(f"{activity_id}: no versioned calibration/source reference")
    if failures:
        return "FAIL", observed, "; ".join(failures + unknowns)
    if unknowns:
        return "UNKNOWN", observed, "; ".join(unknowns)
    return "PASS", observed, None


def _as_fraction(value: Any, label: str) -> > Fraction:
    if type(value) is Fraction:
        return value
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be an exact rational string")
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError, OverflowError) as exc:
        raise ValueError(f"{label} must be an exact rational string") from exc


def _nature(value: Any) -> str:
    return str(getattr(value, "value", value))


def _inventory_scope_state(
    inventory_scope: Mapping[str, Any] | None,
    holding_evidence_present: bool | None,
    posting_natures: Sequence[str],
) -> tuple[GateStatus, dict[str, Any], str | None]:
    if not isinstance(inventory_scope, Mapping):
        return "UNKNOWN", {}, "P21 inventory scope declaration is missing"
    status = inventory_scope.get("status")
    source = inventory_scope.get("source")
    reference = inventory_scope.get("reference_id")
    fingerprint = inventory_scope.get("fingerprint")
    observed = {
        "status": status, "source": source,
        "reference_id": reference, "fingerprint": fingerprint,
        "holding_evidence_present": holding_evidence_present,
    }
    if status not in {"NO_INVENTORY", "COMPLETE"}:
        return "UNKNOWN", observed, "inventory scope must explicitly be NO_INVENTORY or COMPLETE"
    if any(not isinstance(value, str) or not value.strip() for value in (source, reference, fingerprint)):
        return "UNKNOWN", observed, "inventory scope requires source, reference and fingerprint"
    if type(holding_evidence_present) is not bool:
        return "UNKNOWN", observed, "P20 did not record whether P19 holding evidence was supplied"
    if status == "COMPLETE" and not holding_evidence_present:
        return "UNKNOWN", observed, "COMPLETE inventory scope has no P19 holding journal witness"
    if status == "NO_INVENTORY" and "INVENTORY_HOLDING" in posting_natures:
        return "FAIL", observed, "NO_INVENTORY scope conflicts with P19 holding postings"
    return "PASS", observed, None


def _financial_reconciliation_status(
    reconciliation: Any | None,
    inventory_scope: Mapping[str, Any] | None,
) -> tuple[GateStatus, dict[str, Any], str | None]:
    """Replay persisted P20 JSON and inventory coverage exactly.

    P20's PREVIEW_NOT_PROJECT_GO authority is not a certificate. P23 may consume
    its journal only after exact replay and an explicit P21 inventory-scope contract.
    """
    if reconciliation is None:
        return "UNKNOWN", {}, "P20 exact financial reconciliation is missing"

    if isinstance(reconciliation, Mapping):
        if reconciliation.get("schema") != "concilium.p20.financial-reconciliation.v1":
            return "UNKNOWN", {}, "unsupported P20 persisted reconciliation schema"
        postings = reconciliation.get("postings")
        attribution = reconciliation.get("event_attribution")
        weekly = reconciliation.get("weekly_balances")
        weekly_categories = reconciliation.get("weekly_category_balances")
        totals = reconciliation.get("totals")
        if not all(isinstance(x, list) for x in (postings, attribution, weekly, weekly_categories)) or not isinstance(totals, Mapping):
            return "UNKNOWN", {}, "P20 persisted reconciliation is missing postings, attribution or weekly evidence"
        expected_rows: dict[tuple[str, ...], tuple[str, str, Fraction, str, str]] = {}
        grouped: dict[tuple[str, str], Fraction] = {}
        category_grouped: dict[tuple[str, str], Fraction] = {}
        k = v = indirect = Fraction(0)
        for index, raw in enumerate(postings):
            if not isinstance(raw, Mapping):
                return "FAIL", {}, f"P20 posting {index} is not an object"
            raw_id = raw.get("event_id")
            if not isinstance(raw_id, list) or not raw_id or any(not isinstance(x, str) or not x for x in raw_id):
                return "FAIL", {}, f"P20 posting {index} has missing/invalid event identity"
            event_id = tuple(raw_id)
            if event_id in expected_rows:
                return "FAIL", {}, "duplicate P20 financial event ownership"
            nature = raw.get("nature")
            category = raw.get("category")
            source = raw.get("source")
            week = raw.get("week")
            if nature not in {"CONTRACTUAL_ACTIVE", "CONTRACTUAL_IDLE", "MOBILIZATION_EVENT", "DEMOBILIZATION_EVENT", "CONSUMABLE_ACQUISITION", "INDIRECT", "INVENTORY_HOLDING"}:
                return "FAIL", {}, f"P20 posting {index} has invalid nature"
            if category not in {"MO", "EQ", "MAT", "COMB", "IND"}:
                return "FAIL", {}, f"P20 posting {index} has invalid category"
            if not isinstance(source, str) or not source.strip() or not isinstance(week, str) or not week.strip():
                return "UNKNOWN", {}, f"P20 posting {index} lacks source/week provenance"
            try:
                amount = _as_fraction(raw.get("amount"), f"P20 posting {index} amount")
            except ValueError as exc:
                return "UNKNOWN", {}, str(exc)
            if amount < 0:
                return "FAIL", {}, f"P20 posting {index} has a negative amount"
            expected_rows[event_id] = (nature, category, amount, source, week)
            grouped[(week, nature)] = grouped.get((week, nature), Fraction(0)) + amount
            category_grouped[(week, category)] = category_grouped.get((week, category), Fraction(0)) + amount
            if nature in {"CONTRACTUAL_ACTIVE", "CONTRACTUAL_IDLE"}:
                k += amount
            elif nature == "CONSUMABLE_ACQUISITION":
                v += amount
            else:
                indirect += amount

        expected_totals = {
            "contractual_k": k, "consumable_v": v, "direct": k + v,
            "indirect": indirect, "total": k + v + indirect,
        }
        try:
            observed_totals = {name: _as_fraction(totals.get(name), f"P20 total {name}") for name in expected_totals}
        except ValueError as exc:
            return "UNKNOWN", {}, str(exc)
        if observed_totals != expected_totals:
            return "FAIL", {k: str(v) for k, v in expected_totals.items()}, "P20 aggregate totals do not reconstruct from exclusive postings"

        actual_rows: dict[tuple[str, ...], tuple[str, str, Fraction, str, str]] = {}
        for index, raw in enumerate(attribution):
            if not isinstance(raw, Mapping):
                return "FAIL", {}, f"P20 event attribution {index} is not an object"
            raw_id = raw.get("event_id")
            if not isinstance(raw_id, list) or not raw_id or any(not isinstance(x, str) or not x for x in raw_id):
                return "FAIL", {}, f"P20 event attribution {index} has invalid identity"
            event_id = tuple(raw_id)
            if event_id in actual_rows:
                return "FAIL", {}, "duplicate P20 event attribution identity"
            owner_scope = raw.get("owner_scope")
            owner_id = raw.get("owner_id")
            if owner_scope not in {"ACTIVITY", "INSTANCE", "GOOD", "SOURCE"} or not isinstance(owner_id, list) or not owner_id or any(not isinstance(x, str) or not x for x in owner_id):
                return "UNKNOWN", {}, f"P20 event {event_id} has no valid owner attribution"
            try:
                amount = _as_fraction(raw.get("amount"), f"P20 attribution {index} amount")
            except ValueError as exc:
                return "UNKNOWN", {}, str(exc)
            actual_rows[event_id] = (
                str(raw.get("nature")), str(raw.get("category")), amount,
                str(raw.get("source")), str(raw.get("week")),
            )
        if actual_rows != expected_rows:
            return "FAIL", {"posting_count": len(expected_rows), "attribution_count": len(actual_rows)}, "P20 event attribution differs from exclusive postings"

        weekly_seen: dict[str, tuple[Fraction, Fraction, Fraction]] = {}
        for index, row in enumerate(weekly):
            if not isinstance(row, Mapping) or not isinstance(row.get("week"), str):
                return "FAIL", {}, f"P20 weekly balance {index} has no ISO week"
            week = row["week"]
            try:
                values = tuple(_as_fraction(row.get(key), f"P20 weekly {week}/{key}") for key in ("contractual_k", "consumable_v", "indirect"))
            except ValueError as exc:
                return "UNKNOWN", {}, str(exc)
            if week in weekly_seen:
                return "FAIL", {}, f"duplicate P20 weekly balance {week}"
            weekly_seen[week] = values
        recomputed_weeks: dict[str, tuple[Fraction, Fraction, Fraction]] = {}
        for week, _nature in grouped:
            active = grouped.get((week, "CONTRACTUAL_ACTIVE"), Fraction(0))
            idle = grouped.get((week, "CONTRACTUAL_IDLE"), Fraction(0))
            consumables = grouped.get((week, "CONSUMABLE_ACQUISITION"), Fraction(0))
            other = sum((grouped.get((week, nature), Fraction(0)) for nature in ("MOBILIZATION_EVENT", "DEMOBILIZATION_EVENT", "INDIRECT", "INVENTORY_HOLDING")), Fraction(0))
            recomputed_weeks[week] = (active + idle, consumables, other)
        if weekly_seen != recomputed_weeks:
            return "FAIL", {"observed_weeks": len(weekly_seen), "recomputed_weeks": len(recomputed_weeks)}, "P20 weekly balances do not reconstruct from postings"

        weekly_category_seen: dict[tuple[str, str], Fraction] = {}
        for index, row in enumerate(weekly_categories):
            if not isinstance(row, Mapping) or not isinstance(row.get("week"), str) or not isinstance(row.get("category"), str):
                return "FAIL", {}, f"P20 weekly category balance {index} is invalid"
            key = (row["week"], row["category"])
            if key in weekly_category_seen:
                return "FAIL", {}, "duplicate P20 weekly category balance"
            try:
                weekly_category_seen[key] = _as_fraction(row.get("amount"), f"P20 weekly category {key}")
            except ValueError as exc:
                return "UNKNOWN", {}, str(exc)
        if weekly_category_seen != category_grouped:
            return "FAIL", {}, "P20 weekly category ledger does not reconstruct from postings"
        return "PASS", {k: str(v) for k, v in expected_totals.items()} | {"posting_count": len(postings)}, None
k}/{key}") for key in ("contractual_k", "consumable_v", "indirect"))
            except ValueError as exc:
                return "UNKNOWN", {}, str(exc)
            if week in weekly_seen:
                return "FAIL", {}, f"duplicate P20 weekly balance {week}"
            weekly_seen[week] = values
        recomputed_weeks: dict[str, tuple[Fraction, Fraction, Fraction]] = {}
        for week, _nature in grouped:
            active = grouped.get((week, "CONTRACTUAL_ACTIVE"), Fraction(0))
            idle = grouped.get((week, "CONTRACTUAL_IDLE"), Fraction(0))
            consumables = grouped.get((week, "CONSUMABLE_ACQUISITION"), Fraction(0))
            other = sum((grouped.get((week, nature), Fraction(0)) for nature in ("MOBILIZATION_EVENT", "DEMOBILIZATION_EVENT", "INDIRECT", "INVENTORY_HOLDING")), Fraction(0))
            recomputed_weeks[week] = (active + idle, consumables, other)
        if weekly_seen != recomputed_weeks:
            return "FAIL", {"observed_weeks": len(weekly_seen), "recomputed_weeks": len(recomputed_weeks)}, "P20 weekly balances do not reconstruct from postings"

        weekly_category_seen: dict[tuple[str, str], Fraction] = {}
        for index, row in enumerate(weekly_categories):
            if not isinstance(row, Mapping) or not isinstance(row.get("week"), str) or not isinstance(row.get("category"), str):
                return "FAIL", {}, f"P20 weekly category balance {index} is invalid"
            key = (row["week"], row["category"])
            if key in weekly_category_seen:
                return "FAIL", {}, "duplicate P20 weekly category balance"
            try:
                weekly_category_seen[key] = _as_fraction(row.get("amount"), f"P20 weekly category {key}")
            except ValueError as exc:
                return "UNKNOWN", {}, str(exc)
        if weekly_category_seen != category_grouped:
            return "FAIL", {}, "P20 weekly category ledger does not reconstruct from postings"
        inventory_status, inventory_observed, inventory_reason = _inventory_scope_state(
            inventory_scope,
            reconciliation.get("holding_evidence_present"),
            [str(row.get("nature")) for row in postings if isinstance(row, Mapping)],
        )
        totals_observed = {k: str(v) for k, v in expected_totals.items()} | {
            "posting_count": len(postings),
        } | {"inventory_scope": inventory_observed}
        if inventory_status != "PASS":
            return inventory_status, totals_observed, inventory_reason
        return "PASS", totals_observed, None

    ledger = getattr(reconciliation, "ledger", None)
    postings = getattr(ledger, "postings", None)
    if postings is None:
        return "UNKNOWN", {}, "P20 reconciliation has no exclusive cost ledger"
    event_ids = [getattr(line, "event_id", None) for line in postings]
    if any(not event_id for event_id in event_ids) or len(set(event_ids)) != len(event_ids):
        return "FAIL", {}, "duplicate or missing financial event ownership"
    direct = getattr(ledger, "direct", None)
    indirect = getattr(ledger, "indirect", None)
    total = getattr(ledger, "total", None)
    if any(type(value) is not Fraction for value in (direct, indirect, total)):
        return "UNKNOWN", {}, "P20 ledger totals are not exact Fraction values"
    if direct < 0 or indirect < 0 or total <= 0 or direct + indirect != total:
        return "FAIL", {"direct": str(direct), "indirect": str(indirect), "total": str(total)}, "P20 identity C_total = C_direct + C_indirect failed"
    attribution = getattr(reconciliation, "event_attribution", ())
    if not attribution:
        return "UNKNOWN", {"posting_count": len(postings)}, "P20 event-level attribution is missing"
    expected = {
        line.event_id: (line.nature, line.category, line.amount, line.source, line.week)
        for line in postings
    }
    actual: dict[Any, tuple[Any, ...]] = {}
    for row in attribution:
        event_id = getattr(row, "event_id", None)
        if event_id in actual:
            return "FAIL", {}, "duplicate P20 event attribution identity"
        actual[event_id] = (
            getattr(row, "nature", None), getattr(row, "category", None),
            getattr(row, "amount", None), getattr(row, "source", None), getattr(row, "week", None),
        )
    if actual != expected:
        return "FAIL", {"posting_count": len(postings), "attribution_count": len(attribution)}, "P20 event attribution differs from the exclusive ledger"
    weekly = getattr(reconciliation, "weeks", ())
    if weekly:
        weekly_total = sum((getattr(row, "total", Fraction(-1)) for row in weekly), Fraction())
        if weekly_total != total:
            return "FAIL", {"weekly_total": str(weekly_total), "ledger_total": str(total)}, "weekly P20 totals do not reconcile to the project ledger"
    inventory_status, inventory_observed, inventory_reason = _inventory_scope_state(
        inventory_scope,
        getattr(reconciliation, "holding_evidence_present", None),
        [_nature(getattr(row, "nature", "")) for row in postings],
    )
    observed = {
        "posting_count": len(postings), "direct": str(direct),
        "indirect": str(indirect), "total": str(total),
        "inventory_scope": inventory_observed,
    }
    if inventory_status != "PASS":
        return inventory_status, observed, inventory_reason
    return "PASS", observed, None


def _pricing_status(
    pricing: Any | None,
    pricing_gates: Any | None,
    *,
    reconciled_total: Fraction | None = None,
) -> dict[str, tuple[GateStatus, dict[str, Any], str | None]]:
    if pricing is None:
        price = ("FAIL", {}, "operational selling price is absent from the canonical pricing evidence")
        v4 = ("UNKNOWN", {}, "operational pricing diagnostics are missing")
        p = total_cost = profit = None
    else:
        try:
            p = _as_fraction(_read(pricing, "operational_price"), "P21 operational_price")
            total_cost = _as_fraction(_read(pricing, "total_cost"), "P21 total_cost")
            profit = _as_fraction(_read(pricing, "profit_amount"), "P21 profit_amount")
        except ValueError as exc:
            price = ("FAIL", {}, "required operational price/cost evidence is absent or invalid") if _read(pricing, "operational_price") is None else ("UNKNOWN", {}, str(exc))
            v4 = ("UNKNOWN", {}, str(exc))
            p = total_cost = profit = None
        else:
            if p <= 0:
                price = ("FAIL", {"operational_price": str(p)}, "operational selling price must be > 0")
            else:
                price = ("PASS", {"operational_price": str(p)}, None)
            if p > 0 and total_cost > 0:
                v4 = ("PASS", {"P": str(p), "C_tot": str(total_cost)}, None)
            else:
                v4 = ("FAIL", {"P": str(p), "C_tot": str(total_cost)}, "V4 requires P > 0 and C_total > 0")
            if profit != p - total_cost:
                return {
                    "PRICE_PRESENT": ("FAIL", {"P": str(p), "C_tot": str(total_cost), "profit": str(profit)}, "P21 profit does not reconstruct as P - C_total"),
                    "V4": v4,
                    "REGULATORY_BDI_BASIS": ("UNKNOWN", {}, "financial diagnostics did not reconcile"),
                    "PROFITABILITY": ("FAIL", {}, "financial diagnostics did not reconcile"),
                    "V2": ("UNKNOWN", {}, "financial diagnostics did not reconcile"),
                }
            if reconciled_total is not None and total_cost != reconciled_total:
                return {
                    "PRICE_PRESENT": ("FAIL", {"P": str(p), "C_tot": str(total_cost), "P20_total": str(reconciled_total)}, "P21 total cost differs from P20 exclusive ledger"),
                    "V4": ("FAIL", {"P": str(p), "C_tot": str(total_cost), "P20_total": str(reconciled_total)}, "P21 price is not based on reconciled P20 cost"),
                    "REGULATORY_BDI_BASIS": ("UNKNOWN", {}, "P21/P20 monetary sources do not reconcile"),
                    "PROFITABILITY": ("FAIL", {}, "P21/P20 monetary sources do not reconcile"),
                    "V2": ("UNKNOWN", {}, "P21/P20 monetary sources do not reconcile"),
                }

    if pricing_gates is None:
        regulatory = ("FAIL", {}, "mandatory regulatory BDI basis/gate is missing for an RFP")
        profitability = ("UNKNOWN", {}, "P21 profitability gate is missing")
    else:
        regulatory_raw = _read(pricing_gates, "regulatory_status", "UNKNOWN")
        regulatory_reasons_raw = _read(pricing_gates, "reasons", ())
        regulatory_reasons = (
            tuple(regulatory_reasons_raw) if isinstance(regulatory_reasons_raw, (list, tuple))
            else tuple([regulatory_reasons_raw]) if isinstance(regulatory_reasons_raw, str) and regulatory_reasons_raw
            else ()
        )
        regulatory_status: GateStatus = regulatory_raw if regulatory_raw in {"PASS", "FAIL", "UNKNOWN"} else "UNKNOWN"
        if regulatory_status == "UNKNOWN":
            regulatory_status = "FAIL"  # RFP requires a comparable regulatory basis.
        regulatory = (
            regulatory_status,
            {
                "regulatory_bdi_rate": str(_read(pricing_gates, "regulatory_bdi_rate")),
                "floor": str(_read(pricing_gates, "regulatory_bdi_floor")),
                "reference": _read(pricing_gates, "regulatory_basis_reference"),
            },
            None if regulatory_status == "PASS" else "; ".join(str(x) for x in regulatory_reasons) or "regulatory BDI basis is missing or incomparable",
        )
        profit_raw = _read(pricing_gates, "profitability_status", "UNKNOWN")
        profit_status: GateStatus = profit_raw if profit_raw in {"PASS", "FAIL", "UNKNOWN"} else "UNKNOWN"
        profitability = (
            profit_status,
            {"profit": str(_read(pricing_gates, "profit_amount")), "margin": str(_read(pricing_gates, "realized_margin"))},
            None if profit_status == "PASS" else "; ".join(str(x) for x in regulatory_reasons) or "P21 profitability gate did not PASS",
        )
        if profit is not None and profit <= 0:
            profitability = ("FAIL", {"profit": str(profit)}, "operational price does not exceed total cost")
    return {
        "PRICE_PRESENT": price,
        "V4": v4,
        "REGULATORY_BDI_BASIS": regulatory,
        "PROFITABILITY": profitability,
        "V2": regulatory,
    }


def _evaluation_fingerprint(
    *, project_id: str, run_id: str, scope: str, inputs_sha256: str,
    decision: str, gate_evidence: tuple[GateEvidence, ...], reasons: tuple[str, ...],
) -> str:
    manifest = {
        "schema_version": "1.0.0", "project_id": project_id, "run_id": run_id,
        "scope": scope, "inputs_sha256": inputs_sha256, "decision": decision,
        "gate_evidence": [item.model_dump(mode="json") for item in gate_evidence],
        "reasons": list(reasons),
    }
    return hashlib.sha256(b"concilium-formalism-evaluation/v1\n" + _canonical_json(manifest)).hexdigest()
did not reconcile"),
                }
            if reconciled_total is not None and total_cost != reconciled_total:
                return {
                    "PRICE_PRESENT": ("FAIL", {"P": str(p), "C_tot": str(total_cost), "P20_total": str(reconciled_total)}, "P21 total cost differs from P20 exclusive ledger"),
                    "V4": ("FAIL", {"P": str(p), "C_tot": str(total_cost), "P20_total": str(reconciled_total)}, "P21 price is not based on reconciled P20 cost"),
                    "REGULATORY_BDI_BASIS": ("UNKNOWN", {}, "P21/P20 monetary sources do not reconcile"),
                    "PROFITABILITY": ("FAIL", {}, "P21/P20 monetary sources do not reconcile"),
                    "V2": ("UNKNOWN", {}, "P21/P20 monetary sources do not reconcile"),
                }

    if pricing_gates is None:
        regulatory = ("FAIL", {}, "mandatory regulatory BDI basis/gate is missing for an RFP")
        profitability = ("UNKNOWN", {}, "P21 profitability gate is missing")
    else:
        regulatory_raw = _read(pricing_gates, "regulatory_status", "UNKNOWN")
        regulatory_reasons_raw = _read(pricing_gates, "reasons", ())
        regulatory_reasons = (
            tuple(regulatory_reasons_raw) if isinstance(regulatory_reasons_raw, (list, tuple))
            else tuple([regulatory_reasons_raw]) if isinstance(regulatory_reasons_raw, str) and regulatory_reasons_raw
            else ()
        )
        regulatory_status: GateStatus = regulatory_raw if regulatory_raw in {"PASS", "FAIL", "UNKNOWN"} else "UNKNOWN"
        if regulatory_status == "UNKNOWN":
            regulatory_status = "FAIL"  # RFP requires a comparable regulatory basis.
        regulatory = (
            regulatory_status,
            {
                "regulatory_bdi_rate": str(_read(pricing_gates, "regulatory_bdi_rate")),
                "floor": str(_read(pricing_gates, "regulatory_bdi_floor")),
                "reference": _read(pricing_gates, "regulatory_basis_reference"),
            },
            None if regulatory_status == "PASS" else "; ".join(str(x) for x in regulatory_reasons) or "regulatory BDI basis is missing or incomparable",
        )
        profit_raw = _read(pricing_gates, "profitability_status", "UNKNOWN")
        profit_status: GateStatus = profit_raw if profit_raw in {"PASS", "FAIL", "UNKNOWN"} else "UNKNOWN"
        profitability = (
            profit_status,
            {"profit": str(_read(pricing_gates, "profit_amount")), "margin": str(_read(pricing_gates, "realized_margin"))},
            None if profit_status == "PASS" else "; ".join(str(x) for x in regulatory_reasons) or "P21 profitability gate did not PASS",
        )
        if profit is not None and profit <= 0:
            profitability = ("FAIL", {"profit": str(profit)}, "operational price does not exceed total cost")
    return {
        "PRICE_PRESENT": price,
        "V4": v4,
        "REGULATORY_BDI_BASIS": regulatory,
        "PROFITABILITY": profitability,
        "V2": regulatory,
    }


def _evaluation_fingerprint(
    *, project_id: str, run_id: str, scope: str, inputs_sha256: str,
    decision: str, gate_evidence: tuple[GateEvidence, ...], reasons: tuple[str, ...],
) -> str:
    manifest = {
        "schema_version": "1.0.0", "project_id": project_id, "run_id": run_id,
        "scope": scope, "inputs_sha256": inputs_sha256, "decision": decision,
        "gate_evidence": [item.model_dump(mode="json") for item in gate_evidence],
        "reasons": list(reasons),
    }
    return hashlib.sha256(b"concilium-formalism-evaluation/v1\n" + _canonical_json(manifest)).hexdigest()


def evaluate_formalism_certificate(
    envelope: FormalismCertificate,
    evidence: Sequence[GateEvidence],
) -> FormalismEvaluation:
    """Issue GO only for a complete RFP with every physical/financial gate PASS.

    A FAIL in any gate yields NOGO. UNKNOWN/NOT_EVALUATED, missing gates,
    unavailable sources, PREVIEW and RFI are never silently promoted to GO.
    """
    if not isinstance(envelope, FormalismCertificate):
        raise TypeError("an immutable FormalismCertificate evidence envelope is required")
    supplied: dict[str, GateEvidence] = {}
    for item in evidence:
        if not isinstance(item, GateEvidence):
            raise TypeError("all gate inputs must be typed GateEvidence objects")
        if item.gate_id in supplied:
            raise ValueError(f"duplicate gate evidence: {item.gate_id}")
        expected_sources = _evidence_from_envelope(envelope, item.gate_id)
        if item.source_fingerprints != expected_sources:
            raise ValueError(f"{item.gate_id} evidence is bound to different source fingerprints")
        supplied[item.gate_id] = item

    normalized: list[GateEvidence] = []
    for gate_id in REQUIRED_GATES:
        item = supplied.get(gate_id)
        if item is None:
            item = GateEvidence(
                gate_id=gate_id, status="NOT_EVALUATED",
                source_fingerprints=_evidence_from_envelope(envelope, gate_id),
                reason="mandatory gate has no independently produced evidence",
            )
        normalized.append(item)

    failed = [item for item in normalized if item.status == "FAIL"]
    all_pass = all(item.status == "PASS" for item in normalized)
    all_sources_present = all(item.state == "PRESENT" for item in envelope.source_fingerprints)
    reasons: list[str] = []
    for item in normalized:
        if item.status != "PASS":
            reasons.append(f"{item.gate_id}: {item.reason}")
    if envelope.scope != "RFP":
        reasons.append(f"scope {envelope.scope} is not a complete RFP certification scope")
    if not all_sources_present:
        unavailable = [item.name for item in envelope.source_fingerprints if item.state != "PRESENT"]
        reasons.append("required RFP sources unavailable: " + ", ".join(unavailable))

    if failed:
        decision: Decision = "NOGO"
    elif all_pass and all_sources_present and envelope.scope == "RFP":
        decision = "GO"
    else:
        decision = "NOT_CERTIFIABLE"

    unique_reasons = tuple(dict.fromkeys(reasons))
    gates = tuple(normalized)
    digest = _evaluation_fingerprint(
        project_id=envelope.project_id, run_id=envelope.run_id, scope=envelope.scope,
        inputs_sha256=envelope.inputs_sha256, decision=decision,
        gate_evidence=gates, reasons=unique_reasons,
    )
    return FormalismEvaluation(
        project_id=envelope.project_id, run_id=envelope.run_id, scope=envelope.scope,
        inputs_sha256=envelope.inputs_sha256, decision=decision, gate_evidence=gates,
        reasons=unique_reasons, evaluation_sha256=digest,
    )
pe.scope,
        inputs_sha256=envelope.inputs_sha256, decision=decision, gate_evidence=gates,
        reasons=unique_reasons, evaluation_sha256=digest,
    )


def _physical_family_status(
    physical_resolution: Mapping[str, Any] | None,
    prefix: str,
) -> tuple[GateStatus, tuple[str, ...], str | None]:
    if physical_resolution is None or physical_resolution.get("schema") != "concilium.p15.physical-resolution.v1":
        return "UNKNOWN", (), "structured P15 physical-resolution witness is missing or unsupported"
    raw_status = physical_resolution.get("status")
    audit_status = physical_resolution.get("audit_status")
    details_raw = physical_resolution.get("violation_details")
    details = tuple(str(x) for x in details_raw) if isinstance(details_raw, list) else ()
    rows = tuple(x for x in details if x.split(":", 1)[0].startswith(prefix))
    if rows:
        if any("_UNVERIFIED" in x.split(":", 1)[0] for x in rows):
            return "UNKNOWN", rows, "; ".join(rows)
        return "FAIL", rows, "; ".join(rows)
    other_rows = tuple(x for x in details if x.split(":", 1)[0].startswith(("V1_", "V6_")))
    if audit_status == "PASS" and raw_status == "PASS":
        return "PASS", (), None
    if audit_status == "FAIL" and other_rows and all(x.split(":", 1)[0].startswith("V1_" if prefix == "V6_" else "V6_") for x in other_rows):
        return "PASS", (), None
    if raw_status == "FAIL" and physical_resolution.get("complete_search") is True:
        reason = str(physical_resolution.get("reason") or "bounded physical resolution proved no feasible schedule")
        if prefix == "V6_":
            return "FAIL", details, reason
        return "UNKNOWN", details, "bounded physical search was infeasible, but no independent V1 scope-closure violation was identified"
    return "UNKNOWN", details, str(physical_resolution.get("reason") or "physical family has no independent PASS/FAIL witness")


def build_formalism_gate_evidence(
    envelope: FormalismCertificate,
    *,
    physical_audit: Any | None = None,
    physical_resolution: Mapping[str, Any] | None,
    pool_summaries: Sequence[Any] | None,
    productivity_witnesses: Sequence[ProductivityRateWitness] | None,
    expected_activity_ids: Sequence[str] | None,
    financial_reconciliation: Any | None,
    pricing_diagnostics: Any | None,
    pricing_gates: Any | None,
) -> tuple[GateEvidence, ...]:
    """Adapt P15/P16/P20/P21 persisted witnesses into independently fingerprinted gates."""
    # A live validator may add detail. After restart the structured P15 witness
    # remains sufficient because it carries family-coded violations and the final
    # schedule fingerprint; never substitute an untyped success string.
    v1_status, v1_rows, v1_reason = _physical_family_status(physical_resolution, "V1_")
    v6_status, v6_rows, v6_reason = _physical_family_status(physical_resolution, "V6_")

    if physical_audit is not None:
        live_v1, live_v1_rows, live_v1_reason = _audit_status(physical_audit, "V1_")
        live_v6, live_v6_rows, live_v6_reason = _audit_status(physical_audit, "V6_")
        if live_v1 == "FAIL" or live_v1 == "UNKNOWN":
            v1_status, v1_rows, v1_reason = live_v1, live_v1_rows, live_v1_reason
        if live_v6 == "FAIL" or live_v6 == "UNKNOWN":
            v6_status, v6_rows, v6_reason = live_v6, live_v6_rows, live_v6_reason

    resolution_status: GateStatus = "UNKNOWN"
    resolution_reason = "structured P15 physical-resolution witness is missing"
    resolution_observed: dict[str, Any] = {}
    if physical_resolution is not None and physical_resolution.get("schema") == "concilium.p15.physical-resolution.v1":
        raw = physical_resolution.get("status")
        audit = physical_resolution.get("audit_status")
        attempts = physical_resolution.get("attempts")
        complete = physical_resolution.get("complete_search")
        resolution_observed = {
            "status": raw, "audit_status": audit, "attempts": attempts,
            "complete_search": complete,
            "schedule_sha256": physical_resolution.get("schedule_sha256"),
        }
        schedule_fp = next(x for x in envelope.source_fingerprints if x.name == "schedule")
        if raw == "FAIL" and complete is True:
            resolution_status = "FAIL"
            resolution_reason = str(physical_resolution.get("reason") or "P15 proved no feasible bounded schedule")
        elif raw == "FAIL":
            resolution_status = "UNKNOWN"
            resolution_reason = str(physical_resolution.get("reason") or "P15 search was inconclusive")
        elif raw == "PASS" and audit == "PASS" and type(attempts) is int and attempts > 0 and complete is True:
            if schedule_fp.state == "PRESENT" and physical_resolution.get("schedule_sha256") == schedule_fp.sha256:
                resolution_status = "PASS"
                resolution_reason = ""
            else:
                resolution_status = "UNKNOWN"
                resolution_reason = "P15 witness is not bound to the current canonical schedule fingerprint"
        elif raw == "PASS" and complete is not True:
            resolution_status = "UNKNOWN"
            resolution_reason = "P15 found a feasible witness but did not prove the declared search domain complete"
        else:
            resolution_status = "UNKNOWN"
            resolution_reason = str(physical_resolution.get("reason") or "P15 did not produce a complete physical witness")

    if v1_status == "UNKNOWN" and resolution_status == "FAIL":
        v1_reason = v1_reason or resolution_reason
    if v6_status == "UNKNOWN" and resolution_status == "FAIL":
        v6_status, v6_reason = "FAIL", resolution_reason
    elif resolution_status != "PASS" and v6_status == "PASS":
        v6_status, v6_reason = "UNKNOWN", resolution_reason

    pool_status, pool_observed, pool_reason = _pool_standby_status(pool_summaries)
    productivity_status, productivity_observed, productivity_reason = _productivity_status(
        productivity_witnesses, expected_activity_ids,
    )
    inventory_scope = {
        "status": _read(pricing_diagnostics, "inventory_scope_status"),
        "source": _read(pricing_diagnostics, "inventory_scope_source"),
        "reference_id": _read(pricing_diagnostics, "inventory_scope_reference_id"),
        "fingerprint": _read(pricing_diagnostics, "inventory_scope_fingerprint"),
    }
    finance_status, finance_observed, finance_reason = _financial_reconciliation_status(
        financial_reconciliation, inventory_scope,
    )
    finance_total = None
    if finance_status == "PASS":
        try:
            finance_total = _as_fraction(finance_observed.get("total"), "P20 total")
        except ValueError:
            finance_status, finance_reason = "UNKNOWN", "P20 total is not available as an exact amount"
    price_map = _pricing_status(pricing_diagnostics, pricing_gates, reconciled_total=finance_total)

    return (
        gate_evidence_from_status(envelope, "V1", v1_status, observed={"violations": v1_rows}, reason=v1_reason),
on),
        gate_evidence_from_status(envelope, "V2", price_map["V2"][0], observed=price_map["V2"][1], reason=price_map["V2"][2]),
        gate_evidence_from_status(envelope, "V3", pool_status, observed=pool_observed, reason=pool_reason),
        gate_evidence_from_status(envelope, "V4", price_map["V4"][0], observed=price_map["V4"][1], reason=price_map["V4"][2]),
        gate_evidence_from_status(envelope, "V5", productivity_status, observed=productivity_observed, reason=productivity_reason),
        gate_evidence_from_status(envelope, "V6", v6_status, observed={"audit_violations": v6_rows, "resolution": resolution_observed}, reason=v6_reason),
        gate_evidence_from_status(envelope, "FINANCIAL_COST_RECONCILIATION", finance_status, observed=finance_observed, reason=finance_reason),
        gate_evidence_from_status(envelope, "PRICE_PRESENT", price_map["PRICE_PRESENT"][0], observed=price_map["PRICE_PRESENT"][1], reason=price_map["PRICE_PRESENT"][2]),
        gate_evidence_from_status(envelope, "REGULATORY_BDI_BASIS", price_map["REGULATORY_BDI_BASIS"][0], observed=price_map["REGULATORY_BDI_BASIS"][1], reason=price_map["REGULATORY_BDI_BASIS"][2]),
        gate_evidence_from_status(envelope, "PROFITABILITY", price_map["PROFITABILITY"][0], observed=price_map["PROFITABILITY"][1], reason=price_map["PROFITABILITY"][2]),
        gate_evidence_from_status(envelope, "PRODUCTIVITY_PROVENANCE", productivity_status, observed=productivity_observed, reason=productivity_reason),
    )


def evaluate_project_evidence(envelope: FormalismCertificate, **evidence: Any) -> FormalismEvaluation:
    return evaluate_formalism_certificate(envelope, build_formalism_gate_evidence(envelope, **evidence))
