from __future__ import annotations

import pytest

from concilium.application.scheduling.formalism_evaluator import (
    REQUIRED_GATES,
    evaluate_formalism_certificate,
    gate_evidence_from_status,
)
from concilium.domain.models.formalism_certificate import REQUIRED_SOURCES, build_provisional_certificate
from concilium.infrastructure.storage.formalism_certificate_store import (
    persist_formalism_evaluation,
    read_formalism_evaluation,
)


class FakeProject:
    def __init__(self):
        self.data = {}

    def exists(self, path):
        return path in self.data

    def read_json(self, path, default):
        return self.data.get(path, default)

    def write_json(self, path, payload):
        self.data[path] = payload


def _fixture():
    sources = {name: {"version": 1, "source": name} for name in REQUIRED_SOURCES}
    envelope = build_provisional_certificate(
        project_id="project-1", run_id="run-001", scope="RFP",
        formalism_sha256="a" * 64, oracle_sha256="b" * 64, sources=sources,
    )
    evidence = tuple(
        gate_evidence_from_status(envelope, gate, "PASS", artifact_refs=(f"artifact:{gate}",))
        for gate in REQUIRED_GATES
    )
    evaluation = evaluate_formalism_certificate(envelope, evidence)
    return envelope, evaluation, sources


def test_persisted_evaluation_is_immutable_idempotent_and_reloadable_after_restart():
    project = FakeProject()
    envelope, evaluation, sources = _fixture()
    first = persist_formalism_evaluation(project, envelope, evaluation)
    second = persist_formalism_evaluation(project, envelope, evaluation)
    assert first.record_sha256 == second.record_sha256

    restarted_store = FakeProject()
    restarted_store.data = dict(project.data)
    loaded = read_formalism_evaluation(
        restarted_store, run_id=envelope.run_id,
        evaluation_sha256=evaluation.evaluation_sha256,
        current_sources=sources,
        current_formalism_sha256="a" * 64,
        current_oracle_sha256="b" * 64,
    )
    assert loaded is not None
    assert loaded.status == "CURRENT"
    assert loaded.recorded_decision == "GO"
    assert loaded.effective_decision == "GO"


def test_any_material_source_mutation_invalidates_the_recorded_go():
    project = FakeProject()
    envelope, evaluation, sources = _fixture()
    persist_formalism_evaluation(project, envelope, evaluation)
    mutated = dict(sources)
    mutated["schedule"] = {"version": 2, "source": "schedule"}
    loaded = read_formalism_evaluation(
        project, run_id=envelope.run_id,
        evaluation_sha256=evaluation.evaluation_sha256,
        current_sources=mutated,
        current_formalism_sha256="a" * 64,
        current_oracle_sha256="b" * 64,
    )
    assert loaded is not None
    assert loaded.status == "INVALIDATED"
    assert loaded.recorded_decision == "GO"
    assert loaded.effective_decision == "NOT_CERTIFIABLE"
    assert loaded.invalidated_sources == ("schedule",)


def test_missing_material_source_invalidates_and_is_named():
    project = FakeProject()
    envelope, evaluation, sources = _fixture()
    persist_formalism_evaluation(project, envelope, evaluation)
    mutated = dict(sources)
    mutated.pop("catalog")
    loaded = read_formalism_evaluation(
        project, run_id=envelope.run_id,
        evaluation_sha256=evaluation.evaluation_sha256,
        current_sources=mutated,
        current_formalism_sha256="a" * 64,
        current_oracle_sha256="b" * 64,
    )
    assert loaded is not None
    assert loaded.status == "INVALIDATED"
    assert "catalog" in loaded.invalidated_sources
    assert loaded.effective_decision == "NOT_CERTIFIABLE"


def test_mutated_record_checksum_is_rejected():
    project = FakeProject()
    envelope, evaluation, sources = _fixture()
    persist_formalism_evaluation(project, envelope, evaluation)
    path = next(iter(project.data))
    project.data[path]["evaluation"]["decision"] = "NOGO"
    with pytest.raises(ValueError, match="checksum/integrity"):
        read_formalism_evaluation(
            project, run_id=envelope.run_id,
            evaluation_sha256=evaluation.evaluation_sha256,
            current_sources=sources,
            current_formalism_sha256="a" * 64,
            current_oracle_sha256="b" * 64,
        )


def test_unsafe_run_id_and_wrong_evaluation_fingerprint_are_rejected():
    project = FakeProject()
    envelope, evaluation, sources = _fixture()
    persist_formalism_evaluation(project, envelope, evaluation)
    with pytest.raises(ValueError, match="unsafe path"):
        read_formalism_evaluation(
            project, run_id="../run", evaluation_sha256=evaluation.evaluation_sha256,
            current_sources=sources,
            current_formalism_sha256="a" * 64,
            current_oracle_sha256="b" * 64,
        )
    with pytest.raises(ValueError, match="SHA-256"):
        read_formalism_evaluation(
            project, run_id=envelope.run_id, evaluation_sha256="not-a-digest",
            current_sources=sources,
            current_formalism_sha256="a" * 64,
            current_oracle_sha256="b" * 64,
        )


def test_formalism_or_oracle_reference_change_invalidates_certificate():
    project = FakeProject()
    envelope, evaluation, sources = _fixture()
    persist_formalism_evaluation(project, envelope, evaluation)
    loaded = read_formalism_evaluation(
        project, run_id=envelope.run_id,
        evaluation_sha256=evaluation.evaluation_sha256,
        current_sources=sources,
        current_formalism_sha256="f" * 64,
        current_oracle_sha256="b" * 64,
    )
    assert loaded is not None
    assert loaded.status == "INVALIDATED"
    assert loaded.effective_decision == "NOT_CERTIFIABLE"
    assert loaded.invalidated_sources == ("formalism",)


def test_repeated_evaluation_with_same_evidence_is_idempotent():
    project = FakeProject()
    envelope, evaluation, sources = _fixture()
    persisted = persist_formalism_evaluation(project, envelope, evaluation)
    reevaluated = evaluate_formalism_certificate(envelope, evaluation.gate_evidence)
    second = persist_formalism_evaluation(project, envelope, reevaluated)
    assert second.record_sha256 == persisted.record_sha256
