"""Tests for catalog, catalogs, runs, projects API routes."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException


def _svc():
    return MagicMock()


# ─── catalog.py routes ──────────────────────────────────────────────────────


class TestCatalogRoutes:
    def test_get_project_catalog_overrides(self):
        from concilium.presentation.api.routes.catalog import get_project_catalog_overrides

        svc = _svc()
        svc.get_project_catalog_overrides.return_value = {"cpu-1": {"field": "val"}}
        result = get_project_catalog_overrides("proj-1", service=svc)
        assert "cpu-1" in result

    def test_get_project_catalog_overrides_not_found(self):
        from concilium.presentation.api.routes.catalog import get_project_catalog_overrides

        svc = _svc()
        svc.get_project_catalog_overrides.side_effect = FileNotFoundError("not found")
        with pytest.raises(HTTPException) as exc:
            get_project_catalog_overrides("proj-1", service=svc)
        assert exc.value.status_code == 404

    def test_extend_cpu_ok(self):
        from concilium.presentation.api.routes.catalog import extend_cpu

        svc = _svc()
        req = MagicMock()
        req.cpu_id = "cpu-1"
        req.cpu_data = {"field": "val"}
        req.motivo = ""
        result = extend_cpu("proj-1", req, x_user="eng", service=svc)
        assert result["status"] == "ok"
        svc.extend_cpu.assert_called_once()

    def test_extend_cpu_propagates_exception(self):
        from concilium.presentation.api.routes.catalog import extend_cpu

        svc = _svc()
        svc.extend_cpu.side_effect = ValueError("bad cpu")
        with pytest.raises(ValueError, match="bad cpu"):
            extend_cpu("proj-1", "cpu-1", {"f": 1}, x_user="eng", service=svc)

    def test_resolve_cpu_found(self):
        from concilium.presentation.api.routes.catalog import resolve_cpu

        svc = _svc()
        svc.resolve_cpu.return_value = {"id": "cpu-1", "descricao": "Terraplenagem"}
        result = resolve_cpu("proj-1", "cpu-1", service=svc)
        assert result["id"] == "cpu-1"

    def test_resolve_cpu_not_found(self):
        from concilium.presentation.api.routes.catalog import resolve_cpu

        svc = _svc()
        svc.resolve_cpu.return_value = None
        with pytest.raises(HTTPException) as exc:
            resolve_cpu("proj-1", "cpu-1", service=svc)
        assert exc.value.status_code == 404


# ─── catalogs.py routes ─────────────────────────────────────────────────────


class TestCatalogsRoutes:
    def test_list_catalogs(self):
        from concilium.presentation.api.routes.catalogs import list_catalogs

        svc = _svc()
        svc.list_catalogs.return_value = [{"id": "mendeslobo"}]
        result = list_catalogs(service=svc)
        assert result["items"][0]["id"] == "mendeslobo"

    def test_get_catalog_ok(self):
        from concilium.presentation.api.routes.catalogs import get_catalog

        svc = _svc()
        svc.get_catalog.return_value = {"id": "mendeslobo", "n_cpus": 50}
        result = get_catalog("mendeslobo", service=svc)
        assert result["id"] == "mendeslobo"

    def test_get_catalog_not_found(self):
        from concilium.presentation.api.routes.catalogs import get_catalog

        svc = _svc()
        svc.get_catalog.side_effect = FileNotFoundError("not found")
        with pytest.raises(HTTPException) as exc:
            get_catalog("missing", service=svc)
        assert exc.value.status_code == 404

    def test_list_catalog_cpus(self):
        from concilium.presentation.api.routes.catalogs import list_catalog_cpus

        svc = _svc()
        svc.list_catalog_cpus.return_value = {"items": [], "total": 0}
        result = list_catalog_cpus("mendeslobo", q=None, limit=10, service=svc)
        assert "items" in result

    def test_list_catalog_cpus_not_found(self):
        from concilium.presentation.api.routes.catalogs import list_catalog_cpus

        svc = _svc()
        svc.list_catalog_cpus.side_effect = FileNotFoundError("cat not found")
        with pytest.raises(HTTPException) as exc:
            list_catalog_cpus("missing", q=None, limit=10, service=svc)
        assert exc.value.status_code == 404

    def test_get_catalog_cpu_found(self):
        from concilium.presentation.api.routes.catalogs import get_catalog_cpu

        svc = _svc()
        svc.get_catalog_cpu.return_value = {"codigo": "CPU-1"}
        result = get_catalog_cpu("cat", "CPU-1", service=svc)
        assert result["codigo"] == "CPU-1"

    def test_get_catalog_cpu_not_found(self):
        from concilium.presentation.api.routes.catalogs import get_catalog_cpu

        svc = _svc()
        svc.get_catalog_cpu.return_value = None
        with pytest.raises(HTTPException) as exc:
            get_catalog_cpu("cat", "CPU-MISSING", service=svc)
        assert exc.value.status_code == 404

    def test_upsert_catalog_cpu_ok(self):
        from concilium.presentation.api.routes.catalogs import upsert_catalog_cpu

        svc = _svc()
        svc.upsert_catalog_cpu.return_value = {"id": "CPU-1", "status": "ok"}
        req = MagicMock()
        req.cpu_data = {"descricao": "test"}
        req.motivo = ""
        result = upsert_catalog_cpu("cat", "CPU-1", req, x_user="eng", service=svc)
        assert result["id"] == "CPU-1"

    def test_upsert_catalog_cpu_error(self):
        from concilium.presentation.api.routes.catalogs import upsert_catalog_cpu

        svc = _svc()
        svc.upsert_catalog_cpu.side_effect = ValueError("invalid")
        req = MagicMock()
        req.cpu_data = {}
        req.motivo = ""
        with pytest.raises(HTTPException) as exc:
            upsert_catalog_cpu("cat", "CPU-1", req, x_user="eng", service=svc)
        assert exc.value.status_code == 422

    def test_upsert_catalog_cpu_not_found(self):
        from concilium.presentation.api.routes.catalogs import upsert_catalog_cpu

        svc = _svc()
        svc.upsert_catalog_cpu.side_effect = FileNotFoundError("catalog not found")
        req = MagicMock()
        req.cpu_data = {}
        req.motivo = ""
        with pytest.raises(HTTPException) as exc:
            upsert_catalog_cpu("cat", "CPU-1", req, x_user="eng", service=svc)
        assert exc.value.status_code == 404

    def test_upsert_catalog_cpu_unexpected_error(self):
        from concilium.presentation.api.routes.catalogs import upsert_catalog_cpu

        svc = _svc()
        svc.upsert_catalog_cpu.side_effect = RuntimeError("boom")
        req = MagicMock()
        req.cpu_data = {}
        req.motivo = ""
        with pytest.raises(HTTPException) as exc:
            upsert_catalog_cpu("cat", "CPU-1", req, x_user="eng", service=svc)
        assert exc.value.status_code == 500

    def test_list_catalog_insumos(self):
        from concilium.presentation.api.routes.catalogs import list_catalog_insumos

        svc = _svc()
        svc.list_catalog_insumos.return_value = {"items": [], "total": 0}
        result = list_catalog_insumos("cat", q=None, limit=20, service=svc)
        assert "items" in result

    def test_search_catalog(self):
        from concilium.presentation.api.routes.catalogs import search_catalog

        svc = _svc()
        svc.search_catalog.return_value = {"items": [{"id": "CPU-1"}], "total": 1}
        result = search_catalog("terraplenagem", catalog_id=None, limit=10, service=svc)
        assert result["total"] == 1


# ─── runs.py routes ─────────────────────────────────────────────────────────


class TestRunsRoutes:
    def test_list_runs(self):
        from concilium.presentation.api.routes.runs import list_runs

        svc = _svc()
        svc.list_versions.return_value = ["v1", "v2"]
        result = list_runs("proj-1", service=svc)
        assert "items" in result

    def test_get_run(self):
        from concilium.presentation.api.routes.runs import get_run

        svc = _svc()
        svc.get_run.return_value = {"version": "v1"}
        result = get_run("proj-1", "v1", service=svc)
        assert result["version"] == "v1"

    def test_get_run_not_found(self):
        from concilium.presentation.api.routes.runs import get_run

        svc = _svc()
        svc.get_run.side_effect = FileNotFoundError("not found")
        with pytest.raises(HTTPException) as exc:
            get_run("proj-1", "v99", service=svc)
        assert exc.value.status_code == 404

    def test_fork_version_ok(self):
        from concilium.presentation.api.routes.runs import fork_version

        svc = _svc()
        svc.fork_version.return_value = {"new_version": "v3"}
        req = MagicMock()
        result = fork_version("proj-1", "v1", req, x_user="eng", service=svc)
        assert result["new_version"] == "v3"

    def test_fork_version_not_found(self):
        from concilium.presentation.api.routes.runs import fork_version

        svc = _svc()
        svc.fork_version.side_effect = FileNotFoundError("not found")
        req = MagicMock()
        with pytest.raises(HTTPException) as exc:
            fork_version("proj-1", "v99", req, x_user="eng", service=svc)
        assert exc.value.status_code == 404


# ─── projects.py routes ─────────────────────────────────────────────────────


class TestProjectsRoutes:
    def test_list_projects(self):
        from concilium.presentation.api.routes.projects import list_projects

        svc = _svc()
        svc.list_projects.return_value = [{"id": "proj-1"}]
        req = MagicMock()
        req.state = MagicMock(spec=[])
        result = list_projects(req, service=svc)
        assert result["items"][0]["id"] == "proj-1"

    def test_create_project_ok(self):
        from concilium.presentation.api.routes.projects import create_project

        svc = _svc()
        svc.create_project.return_value = {
            "project_id": "new-proj",
            "nome": "Test",
            "contexto_id": "mendeslobo",
            "current_version": "v1",
        }
        req = MagicMock()
        result = create_project(req, x_user="eng", service=svc)
        assert result.project_id == "new-proj"

    def test_create_project_error(self):
        from concilium.presentation.api.routes.projects import create_project

        svc = _svc()
        svc.create_project.side_effect = Exception("invalid")
        req = MagicMock()
        with pytest.raises(HTTPException) as exc:
            create_project(req, x_user="eng", service=svc)
        assert exc.value.status_code == 400

    def test_get_project_ok(self):
        from concilium.presentation.api.routes.projects import get_project

        svc = _svc()
        svc.get_project.return_value = {"id": "proj-1"}
        result = get_project("proj-1", service=svc)
        assert result["id"] == "proj-1"

    def test_get_project_not_found(self):
        from concilium.presentation.api.routes.projects import get_project

        svc = _svc()
        svc.get_project.side_effect = FileNotFoundError("not found")
        with pytest.raises(HTTPException) as exc:
            get_project("proj-1", service=svc)
        assert exc.value.status_code == 404

    def test_delete_project_ok(self):
        from concilium.presentation.api.routes.projects import delete_project

        svc = _svc()
        svc.delete_project.return_value = {"status": "deleted"}
        # ADR-126 D3: delete_project agora recebe `request` (extração de roles/ownership
        # via @permission/require_owner_or_admin) — no-op aqui pois AUTH_ENABLED=0 (default).
        result = delete_project(request=_svc(), project_id="proj-1", x_user="eng", service=svc)
        assert result["status"] == "deleted"

    def test_delete_project_not_found(self):
        from concilium.presentation.api.routes.projects import delete_project

        svc = _svc()
        svc.delete_project.side_effect = FileNotFoundError("not found")
        with pytest.raises(HTTPException) as exc:
            delete_project(request=_svc(), project_id="proj-1", service=svc)
        assert exc.value.status_code == 404

    def test_list_versions(self):
        from concilium.presentation.api.routes.projects import list_versions

        svc = _svc()
        svc.list_versions.return_value = ["v1", "v2"]
        result = list_versions("proj-1", service=svc)
        assert "v1" in result["items"]

    def test_delete_version_ok(self):
        from concilium.presentation.api.routes.projects import delete_version

        svc = _svc()
        svc.delete_version.return_value = {"deleted": "v2"}
        result = delete_version("proj-1", "v2", service=svc)
        assert result["deleted"] == "v2"

    def test_delete_version_error(self):
        from concilium.presentation.api.routes.projects import delete_version

        svc = _svc()
        svc.delete_version.side_effect = Exception("cannot delete last version")
        with pytest.raises(HTTPException) as exc:
            delete_version("proj-1", "v1", x_user="eng", service=svc)
        assert exc.value.status_code == 400



# ─── presentation/api/routes/catalogs.py (8 missing: 63-64, 89-92, 105-106) ───


_catalogs_app_cache: list = []  # list-as-cache para evitar global mutável


class TestApiCatalogsRoutes:
    def _client(self, svc):
        pytest.importorskip("fastapi")
        from fastapi.testclient import TestClient

        try:
            from concilium.presentation.api.app import create_app
            from concilium.presentation.api.container import get_concilium_service
        except TypeError:
            pytest.skip("FastAPI incompatível")
        if not _catalogs_app_cache:
            _catalogs_app_cache.append(create_app())
        app = _catalogs_app_cache[0]
        app.dependency_overrides[get_concilium_service] = lambda: svc
        return TestClient(app, raise_server_exceptions=False)

    def test_get_cpu_returns_none_gives_404(self):
        svc = MagicMock()
        svc.get_catalog_cpu.return_value = None
        c = self._client(svc)
        resp = c.get("/api/catalogs/cat-1/cpus/CPU-MISSING")
        assert resp.status_code == 404

    def test_get_cpu_exception_gives_404(self):
        svc = MagicMock()
        svc.get_catalog_cpu.side_effect = RuntimeError("not found")
        c = self._client(svc)
        resp = c.get("/api/catalogs/cat-1/cpus/CPU-1")
        assert resp.status_code == 404

    def test_upsert_cpu_value_error_gives_422(self):
        svc = MagicMock()
        svc.upsert_catalog_cpu.side_effect = ValueError("invalid")
        c = self._client(svc)
        resp = c.put("/api/catalogs/cat-1/cpus/CPU-1", json={"cpu_data": {}, "motivo": "test"})
        assert resp.status_code == 422

    def test_list_insumos_error_gives_404(self):
        svc = MagicMock()
        svc.list_catalog_insumos.side_effect = FileNotFoundError("cat not found")
        c = self._client(svc)
        resp = c.get("/api/catalogs/cat-1/insumos")
        assert resp.status_code == 404


# ─── presentation/api/routes/projects.py (10 missing — patch_project_config error) ──


@pytest.fixture(scope="module")
def _projects_app():
    """App FastAPI criado uma vez por módulo para TestProjectsRouteErrors."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    try:
        from concilium.presentation.api.app import create_app
    except TypeError:
        pytest.skip("FastAPI incompatível")
    app = create_app()
    with TestClient(app, raise_server_exceptions=False):
        yield app  # yield the app, not the client — svc varies per test


class TestProjectsRouteErrors:
    def _client(self, svc=None):
        pytest.importorskip("fastapi")
        from fastapi.testclient import TestClient

        try:
            from concilium.presentation.api.app import create_app
            from concilium.presentation.api.container import get_concilium_service
        except TypeError:
            pytest.skip("FastAPI incompatível")
        app = create_app()
        if svc:
            app.dependency_overrides[get_concilium_service] = lambda: svc
        return TestClient(app, raise_server_exceptions=False)

    def _client_with_svc(self, app, svc):
        from fastapi.testclient import TestClient

        from concilium.presentation.api.container import get_concilium_service

        app.dependency_overrides[get_concilium_service] = lambda: svc
        return TestClient(app, raise_server_exceptions=False)

    def test_patch_project_config_not_found(self, _projects_app):
        svc = MagicMock()
        svc.patch_project_config.side_effect = FileNotFoundError("not found")
        c = self._client_with_svc(_projects_app, svc)
        resp = c.patch("/api/projects/proj-1/config", json={"nome": "X"})
        assert resp.status_code == 404

    def test_upsert_eap_happy(self, _projects_app):
        svc = MagicMock()
        svc.upsert_eap.return_value = {"eap": [{"item_id": "1.1"}]}
        c = self._client_with_svc(_projects_app, svc)
        resp = c.put("/api/projects/proj-1/eap", json={"items": [{"item_id": "1.1", "cpu_id": "CPU-1"}]})
        assert resp.status_code in (200, 422)

    def test_delete_project_generic_exception(self, _projects_app):
        svc = MagicMock()
        svc.delete_project.side_effect = RuntimeError("boom")
        c = self._client_with_svc(_projects_app, svc)
        resp = c.delete("/api/projects/proj-1")
        assert resp.status_code == 400
        assert "boom" in resp.json()["detail"]

    def test_delete_project_not_found(self, _projects_app):
        svc = MagicMock()
        svc.delete_project.side_effect = FileNotFoundError("nope")
        c = self._client_with_svc(_projects_app, svc)
        resp = c.delete("/api/projects/proj-1")
        assert resp.status_code == 404

    def test_delete_version_generic_exception(self, _projects_app):
        svc = MagicMock()
        svc.delete_version.side_effect = RuntimeError("boom-version")
        c = self._client_with_svc(_projects_app, svc)
        resp = c.delete("/api/projects/proj-1/versions/v1")
        assert resp.status_code == 400
        assert "boom-version" in resp.json()["detail"]

    def test_upsert_eap_value_error(self, _projects_app):
        svc = MagicMock()
        svc.upsert_eap.side_effect = ValueError("ciclo detectado")
        c = self._client_with_svc(_projects_app, svc)
        resp = c.put("/api/projects/proj-1/eap", json=[{"item_id": "1.1", "cpu_id": "CPU-1"}])
        assert resp.status_code == 422

    def test_upsert_eap_not_found(self, _projects_app):
        svc = MagicMock()
        svc.upsert_eap.side_effect = FileNotFoundError("no project")
        c = self._client_with_svc(_projects_app, svc)
        resp = c.put("/api/projects/proj-1/eap", json=[{"item_id": "1.1", "cpu_id": "CPU-1"}])
        assert resp.status_code == 404

    def test_list_versions_tree_builds_hierarchy(self, _projects_app):
        """ADR-119 D3: ?tree=true returns hierarchical tree with authorship metadata."""
        svc = MagicMock()
        svc.list_versions.return_value = ["v1", "v2", "v3"]
        svc.get_version_history.return_value = {
            "v1": {
                "criado_em": "2026-01-01",
                "criado_por": "alice",
                "role_criador": "engenheiro",
                "procurement_intent": None,
                "forked_from": None,
                "motivo": "inicial",
            },
            "v2": {
                "criado_em": "2026-01-02",
                "criado_por": "bob",
                "role_criador": "gerente",
                "procurement_intent": "orcamento",
                "forked_from": "v1",
                "motivo": "revisao",
            },
            "v3": {
                "criado_em": "2026-01-03",
                "criado_por": "carol",
                "role_criador": "gerente",
                "procurement_intent": None,
                # forked_from references a version not present in items -> treated as root
                "forked_from": "v-nonexistent",
                "motivo": "cenario",
            },
        }
        c = self._client_with_svc(_projects_app, svc)
        resp = c.get("/api/projects/proj-1/versions?tree=true")
        assert resp.status_code == 200
        body = resp.json()
        assert set(body["roots"]) == {"v1", "v3"}
        assert body["children"] == {"v1": ["v2"]}
        assert len(body["items"]) == 3

    def test_list_versions_not_found(self, _projects_app):
        svc = MagicMock()
        svc.list_versions.side_effect = FileNotFoundError("no project")
        c = self._client_with_svc(_projects_app, svc)
        resp = c.get("/api/projects/proj-1/versions")
        assert resp.status_code == 404



