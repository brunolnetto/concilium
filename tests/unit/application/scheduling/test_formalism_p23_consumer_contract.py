from __future__ import annotations

from types import SimpleNamespace

from pydantic import BaseModel

from concilium.application.scheduling.formalism_evaluator import (
    REQUIRED_GATES,
    evaluate_formalism_certificate,
    gate_evidence_from_status,
)

from concilium.application.scheduling.formalism_certification_service import (
    _dump,
    build_pool_summaries,
    certificate_summary,
)
from concilium.domain.models.formalism_certificate import (
    REQUIRED_SOURCES,
    build_provisional_certificate,
)
from concilium.infrastructure.storage.formalism_certificate_store import (
    persist_formalism_evaluation,
    read_formalism_evaluation,
)


class _ProjectJsonStore:
    def __init__(self) -> None:
        self.data: dict[str, object] = {}

    def exists(self, path: str) -> bool:
        return path in self.data

    def read_json(self, path: str, default):
        return self.data.get(path, default)

    def write_json(self, path: str, payload) -> None:
        self.data[path] = payload


def _go_record():
    sources = {
        name: {"source_id": f"{name}-fixture", "version": "v1"}
        for name in REQUIRED_SOURCES
    }
    envelope = build_provisional_certificate(
        project_id="project-p23-consumers",
        run_id="run-golden-rfp",
        scope="RFP",
        formalism_sha256="a" * 64,
        oracle_sha256="b" * 64,
        sources=sources,
    )
    gates = tuple(
        gate_evidence_from_status(
            envelope,
            gate_id,
            "PASS",
            observed={"fixture": f"golden-{gate_id}"},
            expected={"fixture": f"golden-{gate_id}"},
            artifact_refs=(f"artifact://p24/{gate_id}",),
        )
        for gate_id in REQUIRED_GATES
    )
    evaluation = evaluate_formalism_certificate(envelope, gates)
    return envelope, evaluation, sources


def test_p24_golden_consumer_reads_the_persisted_p23_decision_not_a_second_oracle() -> None:
    store = _ProjectJsonStore()
    envelope, evaluation, sources = _go_record()
    persist_formalism_evaluation(store, envelope, evaluation)

    # Simulate a fresh process loading the content-addressed record after restart.
    restarted = _ProjectJsonStore()
    restarted.data = dict(store.data)
    loaded = read_formalism_evaluation(
        restarted,
        run_id=envelope.run_id,
        evaluation_sha256=evaluation.evaluation_sha256,
        current_sources=sources,
        current_formalism_sha256=envelope.formalism_sha256,
        current_oracle_sha256=envelope.oracle_sha256,
    )
    presentation = certificate_summary(loaded)

    assert presentation["status"] == "CURRENT"
    assert presentation["effective_decision"] == "GO"
    assert presentation["project_go"] is True
    assert presentation["evaluation_sha256"] == evaluation.evaluation_sha256
    assert len(presentation["gates"]) == len(REQUIRED_GATES)


def test_p24_adversarial_consumer_sees_invalidated_historical_go_as_not_certifiable() -> None:
    store = _ProjectJsonStore()
    envelope, evaluation, sources = _go_record()
    persist_formalism_evaluation(store, envelope, evaluation)

    changed = dict(sources)
    changed["schedule"] = {"source_id": "schedule-fixture", "version": "v2"}
    loaded = read_formalism_evaluation(
        store,
        run_id=envelope.run_id,
        evaluation_sha256=evaluation.evaluation_sha256,
        current_sources=changed,
        current_formalism_sha256=envelope.formalism_sha256,
        current_oracle_sha256=envelope.oracle_sha256,
    )
    presentation = certificate_summary(loaded)

    assert presentation["status"] == "INVALIDATED"
    assert presentation["recorded_decision"] == "GO"
    assert presentation["effective_decision"] == "NOT_CERTIFIABLE"
    assert presentation["project_go"] is False
    assert presentation["invalidated_sources"] == ["schedule"]


def test_p26_traceability_consumer_gets_gate_source_fingerprint_and_artifact_chain() -> None:
    store = _ProjectJsonStore()
    envelope, evaluation, sources = _go_record()
    persist_formalism_evaluation(store, envelope, evaluation)
    loaded = read_formalism_evaluation(
        store,
        run_id=envelope.run_id,
        evaluation_sha256=evaluation.evaluation_sha256,
        current_sources=sources,
        current_formalism_sha256=envelope.formalism_sha256,
        current_oracle_sha256=envelope.oracle_sha256,
    )
    presentation = certificate_summary(loaded)

    rows = {row["gate_id"]: row for row in presentation["gates"]}
    assert set(rows) == set(REQUIRED_GATES)
    for gate_id, row in rows.items():
        assert row["status"] == "PASS"
        assert row["artifact_refs"] == [f"artifact://p24/{gate_id}"]
        assert row["source_fingerprints"]
        assert all(
            source["state"] == "PRESENT" and len(source["sha256"]) == 64
            for source in row["source_fingerprints"]
        )
    assert presentation["record_sha256"] == loaded.record_sha256



class _SetBackedSource(BaseModel):
    source_nodes: set[str]


def test_source_snapshot_serializer_sorts_sets_before_fingerprinting() -> None:
    left = _dump(_SetBackedSource(source_nodes={"gamma", "alpha", "beta"}))
    right = _dump(_SetBackedSource(source_nodes={"beta", "gamma", "alpha"}))
    assert left == right
    assert left["source_nodes"] == ["alpha", "beta", "gamma"]


def test_application_boundary_binds_each_pool_summary_to_its_exact_p16_contract() -> None:
    witness = {
        "schema": "p16-global-instance-assignment/v1",
        "contract_id": "contract-1",
        "demand": [1, 0],
    }
    contract = SimpleNamespace(
        contrato_id="contract-1",
        tipo_id="EQ-1",
        quantidade_contratada=4,
        semanas_contrato=2,
        p16_global_assignment=witness,
    )
    summary = SimpleNamespace(
        contrato_id="contract-1",
        tipo_id="EQ-1",
        machine_weeks_disponiveis=2,
        machine_weeks_usados=1,
        machine_weeks_standby=0,
    )
    canonical = SimpleNamespace(
        contratos_recurso=[contract],
        resumo_utilizacao_contratos=[summary],
    )
    result = build_pool_summaries(canonical)
    assert result[0]["p16_global_assignment"] == _dump(witness)
    assert result[0]["contrato_id"] == "contract-1"
    assert result[0]["p16_contract_quantity"] == 4
    assert result[0]["p16_contract_weeks"] == 2
    assert result[0]["p16_resource_type"] == "EQ-1"
