from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi", reason="fastapi não instalado — pule este módulo de teste")
from fastapi.testclient import TestClient  # noqa: E402

from concilium.application.services.audit_service import AuditService
from concilium.application.services.pipeline_service import PipelineService
from concilium.application.services.project_service import ProjectService
from concilium.infrastructure.storage.file_project_repository import FileProjectRepository
from concilium.presentation.api.app import create_app

pytestmark = [pytest.mark.slow]


class RuntimeSpy:
    def __init__(self, observed: dict):
        self.observed = observed

    def run_pipeline(self, project, skill_inputs, invocation_context=None):
        self.observed["skill_inputs"] = skill_inputs
        self.observed["invocation_context"] = invocation_context or {}
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
        actor="tester",
    )

    assert payload["status"] == "OK"
    assert payload["version"] == "v1"
    assert observed["skill_inputs"]["01-escopo-e-eap"]["base"] == 1
    assert observed["skill_inputs"]["01-escopo-e-eap"]["nested"] == {"left": 10, "saved": 20, "request": 30}
    assert payload["skills_progress"][0]["skill"] == "skill-a"
    assert payload["skills_progress"][0]["status"] == "OK"
    assert observed["invocation_context"]["run_id"] == payload["run_id"]
    assert pipeline_service.list_runs(project.meta["id"])[0]["run_id"] == payload["run_id"]


def test_swagger_endpoint_is_available():
    client = TestClient(create_app())
    response = client.get("/swagger")
    assert response.status_code == 200
    assert "Swagger UI" in response.text
