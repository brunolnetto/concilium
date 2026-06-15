from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi", reason="fastapi não instalado — pule este módulo de teste")
from fastapi.testclient import TestClient  # noqa: E402

from concilium.application.services.project.audit_service import AuditService
from concilium.application.services.pipeline_service import PipelineService
from concilium.application.services.project.project_service import ProjectService
from concilium.infrastructure.storage.file_project_repository import FileProjectRepository
from concilium.presentation.api.app import create_app

pytestmark = [pytest.mark.slow]


class RuntimeSpy:
    def __init__(self, observed: dict):
        self.observed = observed

    def run_pipeline(self, project, skill_inputs, invocation_context=None, skill_sequence=None):
        self.observed["skill_inputs"] = skill_inputs
        self.observed["invocation_context"] = invocation_context or {}
        self.observed["skill_sequence"] = skill_sequence or []
        version = project.current_version()
        project.append_jsonl(
            f"{version}/invocations.log",
            {
                "run_id": invocation_context["run_id"],
                "skill": "skill-a",
                "status": "OK",
                "duration_ms": 7,
                "avisos": [],
            },
        )
        return [{"skill": "skill-a", "status": "OK"}]


@pytest.fixture
def repository(tmp_path):
    root = tmp_path / "projects"
    root.mkdir()
    return FileProjectRepository(root)


@pytest.fixture
def audit_service():
    return AuditService()


@pytest.fixture
def project_service(repository, audit_service):
    return ProjectService(repository, audit_service)


def test_delete_version_blocks_last_project_version(repository, project_service):
    project = repository.create_project("Projeto Teste", "ctx")
    project.update_meta(tipo_projeto="project")
    project.new_version()

    with pytest.raises(RuntimeError, match="última versão"):
        project_service.delete_version(project.meta["id"], "v1")

    assert project.list_versions() == ["v1"]
    assert project.current_version() == "v1"


def test_delete_version_allows_last_hot_project(repository, project_service):
    project = repository.create_project("Projeto HOT", "ctx")
    project.update_meta(tipo_projeto="hot_project")
    project.new_version()
    project.write_json(
        "runs.json",
        [{"run_id": "run-1", "version": "v1", "base_version": "v1"}],
    )

    payload = project_service.delete_version(project.meta["id"], "v1")

    assert payload["versions"] == []
    assert payload["current_version"] is None
    assert payload["orphaned_runs"] == 1
    assert project.list_versions() == []


def test_run_project_merges_inputs_and_records_progress(repository, audit_service):
    observed: dict = {}
    pipeline_service = PipelineService(repository, audit_service, runtime_factory=lambda: RuntimeSpy(observed))
    project = repository.create_project("Projeto Pipeline", "ctx")
    project.write_json(
        "skill_inputs.json",
        {"01-escopo-e-eap": {"base": 1, "nested": {"left": 10}}},
    )
    project.write_json(
        "skill_overrides.json",
        {"01-escopo-e-eap": {"nested": {"saved": 20}}},
    )

    payload = pipeline_service.run_project(
        project.meta["id"],
        base_version=None,
        fork_version=False,
        skill_inputs_override={"01-escopo-e-eap": {"nested": {"request": 30}}},
        use_saved_overrides=True,
        use_mobilizacao_policy=True,
        use_strict_catalog_baseline=False,
        actor="tester",
    )

    assert payload["status"] == "OK"
    assert payload["version"] == "v1"
    assert observed["skill_inputs"]["01-escopo-e-eap"]["base"] == 1
    assert observed["skill_inputs"]["01-escopo-e-eap"]["nested"] == {"left": 10, "saved": 20, "request": 30}
    assert observed["skill_sequence"]
    assert payload["skills_progress"][0]["skill"] == "skill-a"
    assert payload["skills_progress"][0]["status"] == "OK"
    assert observed["invocation_context"]["run_id"] == payload["run_id"]
    assert pipeline_service.list_runs(project.meta["id"])[0]["run_id"] == payload["run_id"]


def test_run_project_can_disable_mobilizacao_policy_injection(repository, audit_service):
    observed: dict = {}
    pipeline_service = PipelineService(repository, audit_service, runtime_factory=lambda: RuntimeSpy(observed))
    project = repository.create_project("Projeto WMP", "ctx")
    project.write_json(
        "skill_inputs.json",
        {"04-cronograma": {"base": True}},
    )
    project.write_json(
        "mobilizacao_policies.json",
        {"item-1": {"n_inicial": 1, "n_maximo": 2, "taxa_mobilizacao": 0.5}},
    )

    payload = pipeline_service.run_project(
        project.meta["id"],
        base_version=None,
        fork_version=False,
        skill_inputs_override={},
        use_saved_overrides=True,
        use_mobilizacao_policy=False,
        use_strict_catalog_baseline=False,
        actor="tester",
    )

    assert payload["status"] == "OK"
    assert payload["use_mobilizacao_policy"] is False
    assert observed["skill_inputs"]["04-cronograma"] == {"base": True}
    assert "mobilizacao_policies" not in observed["skill_inputs"]["04-cronograma"]
    assert observed["skill_sequence"]


def test_resolved_catalog_baseline_prefers_project_reference(repository, audit_service):
    observed: dict = {}
    pipeline_service = PipelineService(repository, audit_service, runtime_factory=lambda: RuntimeSpy(observed))
    project = repository.create_project("Projeto Catalogo", "ctx")
    project.write_json(
        "skill_inputs.json",
        {"01-escopo-e-eap": {"base": True}},
    )
    project.write_json(
        "benchmark_reference.json",
        {
            "catalog": {
                "cpus": [{"codigo": "cpu-projeto", "descricao": "CPU do projeto"}],
                "insumos": [],
                "producoes": [],
            }
        },
    )

    payload = pipeline_service.run_project(
        project.meta["id"],
        base_version=None,
        fork_version=False,
        skill_inputs_override={},
        use_saved_overrides=True,
        use_mobilizacao_policy=False,
        use_strict_catalog_baseline=False,
        actor="tester",
    )

    resolved = project.read_json(f"{payload['version']}/resolved_catalog.json", {})
    assert payload["catalogo_base_origem"] == "project_reference"
    assert resolved["catalogo_base_origem"] == "project_reference"
    assert resolved["items"]["cpus"][0]["codigo"] == "cpu-projeto"
    assert observed["skill_sequence"]


def test_strict_catalog_baseline_fails_without_project_reference(repository, audit_service):
    observed: dict = {}
    pipeline_service = PipelineService(repository, audit_service, runtime_factory=lambda: RuntimeSpy(observed))
    project = repository.create_project("Projeto Estrito", "ctx")
    project.write_json(
        "skill_inputs.json",
        {"01-escopo-e-eap": {"base": True}},
    )

    payload = pipeline_service.run_project(
        project.meta["id"],
        base_version=None,
        fork_version=False,
        skill_inputs_override={},
        use_saved_overrides=True,
        use_mobilizacao_policy=False,
        use_strict_catalog_baseline=True,
        actor="tester",
    )

    assert payload["status"] == "EXCEPTION"
    assert "Baseline de catalogo do projeto nao encontrado" in payload["error"]


def test_swagger_endpoint_is_available():
    client = TestClient(create_app())
    response = client.get("/swagger")
    assert response.status_code == 200
    assert "Swagger UI" in response.text
