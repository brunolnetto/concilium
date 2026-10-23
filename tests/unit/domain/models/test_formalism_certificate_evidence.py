"""P23-A: immutable, deterministic input hashes without any fictional GO."""
from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from concilium.domain.models.formalism_certificate import (
    REQUIRED_SOURCES,
    FormalismCertificate,
    SourceFingerprint,
    build_provisional_certificate,
    matches_current_sources,
)

HASH_A = "a" * 64
HASH_B = "b" * 64


def _sources() -> dict:
    sources = {name: {"revision": 1} for name in REQUIRED_SOURCES}
    sources["canonical"] = {"b": [2, 1], "a": {"rho": "10.0", "teams": 2}}
    sources["productivity"] = {
        "F(2)": "20",
        "origin": "GRAFO_FLUXO",
        "calibration": "NAO_CERTIFICADA",
    }
    sources["calendar"] = {"p": 0.75, "c": 0.8, "hours": 40}
    sources["ledger"] = None
    sources["pricing"] = None
    return sources


def _make(sources: dict | None = None, scope: str = "RFI") -> FormalismCertificate:
    return build_provisional_certificate(
        project_id="P1", run_id="run-1", scope=scope,
        formalism_sha256=HASH_A, oracle_sha256=HASH_B,
        sources=_sources() if sources is None else sources,
    )


def test_stable_order_independent_hashes_and_serialization() -> None:
    raw = _sources()
    first = _make(raw)
    raw["canonical"] = {"a": {"teams": 2, "rho": "10.0"}, "b": [2, 1]}
    second = _make(raw)
    assert first.inputs_sha256 == second.inputs_sha256
    assert first.source_fingerprints == second.source_fingerprints
    assert FormalismCertificate.model_validate_json(first.model_dump_json()) == first
    assert matches_current_sources(first, raw)
    assert first.decision == "NOT_EVALUATED"


@pytest.mark.parametrize(
    "name", ["canonical", "productivity", "calendar", "catalog", "schedule",
             "pool", "inventory", "ledger", "pricing", "solver"]
)
def test_mutation_of_any_material_source_invalidates_snapshot(name: str) -> None:
    original = _sources()
    envelope = _make(original)
    changed = deepcopy(original)
    changed[name] = {"revision": 999, "controlled": False}
    assert not matches_current_sources(envelope, changed)
    assert _make(changed).inputs_sha256 != envelope.inputs_sha256


def test_missing_and_unavailable_are_distinct_from_empty() -> None:
    raw = _sources()
    envelope = _make(raw)
    assert not matches_current_sources(envelope, {k: v for k, v in raw.items() if k != "ledger"})
    raw["ledger"] = {}
    assert not matches_current_sources(envelope, raw)
    with pytest.raises(ValueError, match="enumerate all ten"):
        _make({k: v for k, v in raw.items() if k != "pricing"})
    assert next(x for x in envelope.source_fingerprints if x.name == "ledger").state == "UNAVAILABLE"


def test_scope_and_versions_invalidate_envelope_without_fake_go() -> None:
    rfi = _make()
    rfp = _make(scope="RFP")
    assert rfi.inputs_sha256 != rfp.inputs_sha256
    assert _make().decision == "NOT_EVALUATED"
    with pytest.raises(ValidationError):
        FormalismCertificate.model_validate({
            **rfi.model_dump(), "decision": "GO",
        })
    with pytest.raises(ValidationError):
        SourceFingerprint(name="productivity", state="UNAVAILABLE", sha256=HASH_A)


def test_nonfinite_and_unordered_snapshots_are_rejected() -> None:
    raw = _sources()
    raw["calendar"] = {"practicability": float("nan")}
    with pytest.raises(ValueError):
        _make(raw)
    raw["calendar"] = {"unhashable": {"a", "b"}}
    with pytest.raises(TypeError):
        _make(raw)


def test_frozen_structure_and_envelope_checksum() -> None:
    envelope = _make()
    with pytest.raises(ValidationError):
        envelope.decision = "NOT_EVALUATED"
    with pytest.raises(ValidationError):
        FormalismCertificate.model_validate({
            **envelope.model_dump(),
            "inputs_sha256": "0" * 64,
        })
    with pytest.raises(ValidationError):
        FormalismCertificate.model_validate({
            **envelope.model_dump(),
            "source_fingerprints": tuple(reversed(envelope.source_fingerprints)),
        })


def test_preview_cannot_claim_certified_pricing() -> None:
    preview = _make(scope="PREVIEW")
    assert preview.decision == "NOT_EVALUATED"
    assert next(x for x in preview.source_fingerprints if x.name == "pricing").state == "UNAVAILABLE"
    assert next(x for x in preview.source_fingerprints if x.name == "productivity").state == "PRESENT"
    assert matches_current_sources(preview, _sources())
