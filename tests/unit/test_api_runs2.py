"""Additional API route tests for runs.py — cover uncovered paths."""

from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi", reason="fastapi not installed")
from fastapi.testclient import TestClient  # noqa: E402

try:
    from concilium.presentation.api.app import create_app
    from concilium.presentation.api.container import get_concilium_service
except TypeError as exc:
    pytest.skip(f"FastAPI incompatível: {exc}", allow_module_level=True)


class _FakeService:
    def run_project(self, project_id, *, base_version, fork_version, skill_inputs_override,
                    use_saved_overrides, use_mobilizacao_policy, use_strict_catalog_baseline, actor):
        return {
            "project_id": project_id,
            "run_id": "run-1",
            "version": "v1",
            "status": "CONCLUIDO",
            "skills_log": [],
            "summary": {},
            "output_files": [],
            "use_mobilizacao_policy": use_mobilizacao_policy,
            "use_strict_catalog_baseline": use_strict_catalog_baseline,
        }

    def start_run_project(self, project_id, *, base_version, fork_version, skill_inputs_override,
                          use_saved_overrides, use_mobilizacao_policy, use_strict_catalog_baseline, actor):
        return {"project_id": project_id, "run_id": "run-1", "status": "queued",
                "use_mobilizacao_policy": False, "use_strict_catalog_baseline": False}

    def list_runs(self, project_id):
        return [{"run_id": "run-1", "status": "done"}]

    def get_run(self, project_id, run_id):
        return {"run_id": run_id, "status": "done"}

    def fork_version(self, project_id, version, *, actor):
        return {"project_id": project_id, "version": version, "forked_from": version, "actor": actor}

    def resolve_run_base_version(self, project_id, run_id):
        return "v1"


class _ErrorService(_FakeService):
    def run_project(self, *a, **kw):
        raise FileNotFoundError("project not found")

    def list_runs(self, project_id):
        raise FileNotFoundError("not found")

    def get_run(self, *a, **kw):
        raise FileNotFoundError("not found")

    def fork_version(self, *a, **kw):
        raise Exception("conflict")


def _client(svc=None):
    app = create_app()
    app.dependency_overrides[get_concilium_service] = lambda: (svc or _FakeService())
    return TestClient(app, raise_server_exceptions=False)


class TestRunProjectRoute:
    def test_run_project_happy(self):
        c = _client()
        resp = c.post("/api/projects/proj-1/runs", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_id"] == "proj-1"

    def test_run_project_not_found(self):
        c = _client(_ErrorService())
        resp = c.post("/api/projects/proj-1/runs", json={})
        assert resp.status_code == 404

    def test_run_project_generic_error(self):
        class FailSvc(_FakeService):
            def run_project(self, *a, **kw):
                raise ValueError("bad input")
        c = _client(FailSvc())
        resp = c.post("/api/projects/proj-1/runs", json={})
        assert resp.status_code == 400


class TestRerunProjectRoute:
    def test_rerun_happy(self):
        c = _client()
        resp = c.post("/api/projects/proj-1/rerun", json={"base_version": "v1"})
        assert resp.status_code == 200

    def test_rerun_resolves_from_run_id(self):
        c = _client()
        resp = c.post("/api/projects/proj-1/rerun", json={"base_run_id": "run-1"})
        assert resp.status_code == 200

    def test_rerun_not_found(self):
        class RerunErrorSvc(_FakeService):
            def run_project(self, *a, **kw):
                raise FileNotFoundError("not found")
        c = _client(RerunErrorSvc())
        resp = c.post("/api/projects/proj-1/rerun", json={})
        assert resp.status_code == 404


class TestListRunsRoute:
    def test_list_runs_happy(self):
        c = _client()
        resp = c.get("/api/projects/proj-1/runs")
        assert resp.status_code == 200
        assert "items" in resp.json()

    def test_list_runs_not_found(self):
        c = _client(_ErrorService())
        resp = c.get("/api/projects/proj-1/runs")
        assert resp.status_code == 404


class TestGetRunRoute:
    def test_get_run_happy(self):
        c = _client()
        resp = c.get("/api/projects/proj-1/runs/run-1")
        assert resp.status_code == 200
        assert resp.json()["run_id"] == "run-1"

    def test_get_run_not_found(self):
        c = _client(_ErrorService())
        resp = c.get("/api/projects/proj-1/runs/run-missing")
        assert resp.status_code == 404


class TestForkVersionRoute:
    def test_fork_version_happy(self):
        c = _client()
        resp = c.post("/api/projects/proj-1/versions/v1/fork", json={"actor": "admin"})
        assert resp.status_code == 200
        assert resp.json()["actor"] == "admin"

    def test_fork_version_without_body(self):
        c = _client()
        resp = c.post("/api/projects/proj-1/versions/v1/fork")
        assert resp.status_code == 200

    def test_fork_version_error(self):
        c = _client(_ErrorService())
        resp = c.post("/api/projects/proj-1/versions/v1/fork")
        assert resp.status_code == 400
