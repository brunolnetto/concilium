"""Tests for API analysis routes (analysis.py) — cover uncovered paths."""

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
    def compare_versions(self, project_id, left, right):
        return {"project_id": project_id, "diff": {}}

    def list_artifacts(self, project_id, version=None):
        return {"artifacts": []}

    def get_artifact_bytes(self, project_id, version, kind, filename):
        return b"data", "application/octet-stream"

    def download_artifact(self, project_id, version, filename):
        return b"data"

    def get_benchmark_reference(self, project_id):
        return {"benchmark": "ref"}

    def list_audit(self, project_id, limit=50):
        return [{"action": "run", "ts": "2026-01-01"}]

    def get_diagnostico_pe(self, project_id, version=None):
        return {"items": []}

    def get_calendario_operacional(self, project_id, version=None):
        return {"eventos": []}

    def simulate_calendario_operacional(self, project_id, req, version=None):
        return {"simulado": True}

    def get_cubo_analitico(self, project_id, version=None):
        return {"cubo": {}}

    def get_cubo_analitico_projection(self, project_id, version=None, granularidade="semana", **kw):
        return {"projecao": []}

    def get_cubo_projection_contract(self, **kw):
        return {"contratos": []}

    def get_cubo_analitico_projecao_contrato(self, project_id, version=None):
        return {"contratos": []}

    def get_cubo_pool_projection(self, project_id, version=None, **kw):
        return {"pool": []}

    def get_cubo_pool_projection_contract(self, **kw):
        return {"pool_contratos": []}


class _ErrorService(_FakeService):
    def compare_versions(self, *a, **kw):
        raise FileNotFoundError("not found")

    def list_artifacts(self, *a, **kw):
        raise FileNotFoundError("not found")

    def get_benchmark_reference(self, *a, **kw):
        raise FileNotFoundError("not found")

    def list_audit(self, *a, **kw):
        raise FileNotFoundError("not found")


def _client(svc=None):
    app = create_app()
    app.dependency_overrides[get_concilium_service] = lambda: svc or _FakeService()
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(scope="module")
def _fake_client():
    """App criado uma vez por módulo — evita create_app() por teste."""
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


class TestCompareRoutes:
    def test_compare_post_happy(self, _fake_client):
        resp = _fake_client.post("/api/projects/proj-1/compare", json={"left_version": "v1", "right_version": "v2"})
        assert resp.status_code == 200
        assert "diff" in resp.json()

    def test_compare_post_not_found(self, _error_client):
        resp = _error_client.post("/api/projects/proj-1/compare", json={"left_version": "v1", "right_version": "v2"})
        assert resp.status_code == 404

    def test_compare_get_happy(self, _fake_client):
        resp = _fake_client.get("/api/projects/proj-1/compare?left=v1&right=v2")
        assert resp.status_code == 200

    def test_compare_get_value_error(self):
        class VESvc(_FakeService):
            def compare_versions(self, *a, **kw):
                raise ValueError("bad")

        c = _client(VESvc())
        resp = c.get("/api/projects/proj-1/compare?left=v1&right=v2")
        assert resp.status_code == 400


class TestArtifactRoutes:
    def test_list_artifacts_happy(self, _fake_client):
        resp = _fake_client.get("/api/projects/proj-1/artifacts")
        assert resp.status_code == 200

    def test_list_artifacts_not_found(self, _error_client):
        resp = _error_client.get("/api/projects/proj-1/artifacts")
        assert resp.status_code == 404


class TestBenchmarkReferenceRoute:
    def test_get_benchmark_reference_happy(self, _fake_client):
        resp = _fake_client.get("/api/projects/proj-1/benchmark-reference")
        assert resp.status_code == 200

    def test_get_benchmark_reference_not_found(self, _error_client):
        resp = _error_client.get("/api/projects/proj-1/benchmark-reference")
        assert resp.status_code == 404


class TestAuditRoute:
    def test_list_audit_happy(self, _fake_client):
        resp = _fake_client.get("/api/projects/proj-1/audit")
        assert resp.status_code == 200

    def test_list_audit_not_found(self, _error_client):
        resp = _error_client.get("/api/projects/proj-1/audit")
        assert resp.status_code == 404


class TestDiagnosticoPeRoute:
    def test_get_diagnostico_pe_happy(self, _fake_client):
        resp = _fake_client.get("/api/projects/proj-1/diagnostico-pe")
        assert resp.status_code == 200

    def test_get_diagnostico_pe_not_found(self):
        class FNFSvc(_FakeService):
            def get_diagnostico_pe(self, *a, **kw):
                raise FileNotFoundError("not found")

        c = _client(FNFSvc())
        resp = c.get("/api/projects/proj-1/diagnostico-pe")
        assert resp.status_code == 404


class TestCalendarioRoutes:
    def test_get_calendario_happy(self, _fake_client):
        resp = _fake_client.get("/api/projects/proj-1/calendario-operacional")
        assert resp.status_code == 200

    def test_simulate_calendario_happy(self, _fake_client):
        resp = _fake_client.post(
            "/api/projects/proj-1/calendario-operacional/simular", json={"fator_calendario_semanal": {"2026-W01": 0.5}}
        )
        assert resp.status_code == 200


class TestCuboRoutes:
    def test_cubo_analitico_happy(self, _fake_client):
        resp = _fake_client.get("/api/projects/proj-1/cubo-analitico")
        assert resp.status_code == 200

    def test_cubo_projecao_happy(self, _fake_client):
        resp = _fake_client.get("/api/projects/proj-1/cubo-analitico/projecao")
        assert resp.status_code == 200

    def test_cubo_pool_happy(self, _fake_client):
        resp = _fake_client.get("/api/projects/proj-1/cubo-pool/projecao")
        assert resp.status_code == 200


class TestAnalysisErrorPaths:
    """Cover remaining uncovered lines: compare_query, download_artifact, cubo projecao contrato,
    cubo pool projecao contrato, etc."""

    def test_compare_get_not_found(self, _error_client):
        resp = _error_client.get("/api/projects/proj-1/compare?left=v1&right=v2")
        assert resp.status_code == 404

    def test_download_artifact_happy(self, _fake_client):
        resp = _fake_client.get("/api/projects/proj-1/artifacts/download?kind=json&filename=relatorio.json")
        assert resp.status_code == 200

    def test_download_artifact_not_found(self):
        class DownloadSvc(_FakeService):
            def get_artifact_bytes(self, *a, **kw):
                raise FileNotFoundError("no")

        c = _client(DownloadSvc())
        resp = c.get("/api/projects/proj-1/artifacts/download?kind=json&filename=missing.json")
        assert resp.status_code == 404

    def test_cubo_analitico_not_found(self):
        class FNFSvc(_FakeService):
            def get_cubo_analitico(self, *a, **kw):
                raise FileNotFoundError("no")

        c = _client(FNFSvc())
        resp = c.get("/api/projects/proj-1/cubo-analitico")
        assert resp.status_code == 404

    def test_cubo_projecao_contrato_happy(self, _fake_client):
        resp = _fake_client.get("/api/projects/proj-1/cubo-analitico/projecao/contrato")
        assert resp.status_code == 200

    def test_cubo_pool_projecao_contrato_happy(self, _fake_client):
        resp = _fake_client.get("/api/projects/proj-1/cubo-pool/projecao/contrato")
        assert resp.status_code == 200
