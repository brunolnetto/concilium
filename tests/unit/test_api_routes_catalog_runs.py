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
