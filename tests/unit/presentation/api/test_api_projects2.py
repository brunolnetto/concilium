"""Tests for API routes/projects.py and routes/auth.py — cover uncovered paths."""

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
    def list_projects(self):
        return [{"id": "proj-1", "nome": "Test"}]

    def create_project(self, req, actor="system"):
        return {
            "project_id": "proj-new",
            "nome": "New Project",
            "contexto_id": "ctx",
            "current_version": "v1",
            "tipo_projeto": "benchmark",
            "status_eap": "NAO_INICIADA",
        }

    def get_project(self, project_id):
        return {"id": project_id, "nome": "Test"}

    def delete_project(self, project_id, actor="system"):
        return {"deleted": project_id}

    def patch_project_config(self, project_id, patch, actor="system"):
        return {"id": project_id, **patch}

    def list_versions(self, project_id):
        return [{"version": "v1", "status": "RASCUNHO"}]

    def delete_version(self, project_id, version, actor="system"):
        return {"deleted": version}

    def get_eap(self, project_id, version=None):
        return {"eap": []}

    def upsert_eap(self, project_id, items, actor="system"):
        return {"eap": items}


class _ErrorService(_FakeService):
    def get_project(self, *a, **kw):
        raise FileNotFoundError("not found")

    def delete_project(self, *a, **kw):
        raise FileNotFoundError("not found")

    def list_versions(self, *a, **kw):
        raise FileNotFoundError("not found")

    def delete_version(self, *a, **kw):
        raise FileNotFoundError("not found")

    def get_eap(self, *a, **kw):
        raise FileNotFoundError("not found")

    def upsert_eap(self, *a, **kw):
        raise ValueError("invalid eap")


class _StorageUnavailableService(_FakeService):
    def list_projects(self):
        from concilium.domain.repositories.blob_storage_port import StorageUnavailableError

        raise StorageUnavailableError("SharePoint indisponível ao ler 'projetos/index.json' (status=503): ...")


def _client(svc=None):
    app = create_app()
    app.dependency_overrides[get_concilium_service] = lambda: svc or _FakeService()
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(scope="module")
def _fake_client():
    app = create_app()
    app.dependency_overrides[get_concilium_service] = lambda: _FakeService()
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture(scope="module")
def _error_client():
    app = create_app()
    app.dependency_overrides[get_concilium_service] = lambda: _ErrorService()
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


class TestProjectsRoutes:
    def test_list_projects(self, _fake_client):
        resp = _fake_client.get("/api/projects/")
        assert resp.status_code == 200

    def test_create_project(self, _fake_client):
        resp = _fake_client.post("/api/projects/", json={"nome": "New Project", "contexto_id": "ctx"})
        assert resp.status_code == 200

    def test_get_project_happy(self, _fake_client):
        resp = _fake_client.get("/api/projects/proj-1")
        assert resp.status_code == 200

    def test_get_project_not_found(self, _error_client):
        resp = _error_client.get("/api/projects/proj-missing")
        assert resp.status_code == 404

    def test_delete_project_happy(self, _fake_client):
        resp = _fake_client.delete("/api/projects/proj-1")
        assert resp.status_code == 200

    def test_delete_project_not_found(self, _error_client):
        resp = _error_client.delete("/api/projects/proj-missing")
        assert resp.status_code == 404

    def test_list_projects_storage_unavailable_returns_503(self):
        resp = _client(_StorageUnavailableService()).get("/api/projects/")
        assert resp.status_code == 503
        assert "SharePoint indisponível" in resp.json()["detail"]

    def test_list_versions_happy(self, _fake_client):
        resp = _fake_client.get("/api/projects/proj-1/versions")
        assert resp.status_code == 200

    def test_list_versions_not_found(self, _error_client):
        resp = _error_client.get("/api/projects/proj-missing/versions")
        assert resp.status_code == 404

    def test_delete_version_happy(self, _fake_client):
        resp = _fake_client.delete("/api/projects/proj-1/versions/v1")
        assert resp.status_code == 200

    def test_delete_version_not_found(self, _error_client):
        resp = _error_client.delete("/api/projects/proj-1/versions/v99")
        assert resp.status_code == 404

    def test_get_eap_happy(self, _fake_client):
        resp = _fake_client.get("/api/projects/proj-1/eap")
        assert resp.status_code == 200

    def test_get_eap_not_found(self, _error_client):
        resp = _error_client.get("/api/projects/proj-1/eap")
        assert resp.status_code == 404

    def test_upsert_eap_error(self, _error_client):
        resp = _error_client.put("/api/projects/proj-1/eap", json={"items": []})
        assert resp.status_code in (400, 422)

    def test_patch_project_config(self, _fake_client):
        resp = _fake_client.patch("/api/projects/proj-1/config", json={"nome": "Updated"})
        assert resp.status_code == 200
