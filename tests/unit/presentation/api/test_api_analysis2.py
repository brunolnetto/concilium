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

    def get_cubo_estoque_consumivel_projection(self, project_id, version=None, **kw):
        return {"estoque_consumivel": []}

    def get_cubo_estoque_consumivel_projection_contract(self, **kw):
        return {"estoque_consumivel_contratos": []}


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

    def test_cubo_estoque_consumivel_happy(self, _fake_client):
        resp = _fake_client.get("/api/projects/proj-1/cubo-estoque-consumivel/projecao")
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

    def test_cubo_estoque_consumivel_projecao_contrato_happy(self, _fake_client):
        resp = _fake_client.get("/api/projects/proj-1/cubo-estoque-consumivel/projecao/contrato")
        assert resp.status_code == 200

    def test_cubo_estoque_consumivel_not_found(self):
        class FNFSvc(_FakeService):
            def get_cubo_estoque_consumivel_projection(self, *a, **kw):
                raise FileNotFoundError("no")

        c = _client(FNFSvc())
        resp = c.get("/api/projects/proj-1/cubo-estoque-consumivel/projecao")
        assert resp.status_code == 404

    def test_cubo_estoque_consumivel_bad_request(self):
        class ValueErrSvc(_FakeService):
            def get_cubo_estoque_consumivel_projection(self, *a, **kw):
                raise ValueError("face inválida")

        c = _client(ValueErrSvc())
        resp = c.get("/api/projects/proj-1/cubo-estoque-consumivel/projecao")
        assert resp.status_code == 400


from unittest.mock import MagicMock  # noqa: E402

from fastapi import HTTPException  # noqa: E402

# ─── analysis API routes ─────────────────────────────────────────────────────


class TestAnalysisRoutes:
    def _svc(self):
        return MagicMock()

    def test_compare_ok(self):
        from concilium.presentation.api.routes.analysis import compare

        svc = self._svc()
        svc.compare_versions.return_value = {"delta": 0.05}
        req = MagicMock()
        req.left_version = "v1"
        req.right_version = "v2"
        result = compare("proj-1", req, service=svc)
        assert "delta" in result

    def test_compare_not_found(self):
        from concilium.presentation.api.routes.analysis import compare

        svc = self._svc()
        svc.compare_versions.side_effect = FileNotFoundError("not found")
        req = MagicMock()
        req.left_version = "v1"
        req.right_version = "v99"
        with pytest.raises(HTTPException) as exc:
            compare("proj-1", req, service=svc)
        assert exc.value.status_code == 404

    def test_list_artifacts_ok(self):
        from concilium.presentation.api.routes.analysis import list_artifacts

        svc = self._svc()
        svc.list_artifacts.return_value = {"items": [{"nome": "relatorio.json"}]}
        result = list_artifacts("proj-1", version=None, service=svc)
        assert "items" in result

    def test_get_diagnostico_pe_ok(self):
        from concilium.presentation.api.routes.analysis import get_diagnostico_pe

        svc = self._svc()
        svc.get_diagnostico_pe.return_value = {"status": "VERDE"}
        result = get_diagnostico_pe("proj-1", service=svc)
        assert result["status"] == "VERDE"

    def test_get_diagnostico_pe_not_found(self):
        from concilium.presentation.api.routes.analysis import get_diagnostico_pe

        svc = self._svc()
        svc.get_diagnostico_pe.side_effect = FileNotFoundError("not found")
        with pytest.raises(HTTPException) as exc:
            get_diagnostico_pe("proj-1", service=svc)
        assert exc.value.status_code == 404

    def test_get_calendario_operacional(self):
        from concilium.presentation.api.routes.analysis import get_calendario_operacional

        svc = self._svc()
        svc.get_calendario_operacional.return_value = {"weeks": []}
        result = get_calendario_operacional("proj-1", service=svc)
        assert "weeks" in result

    def test_simulate_calendario_operacional(self):
        from concilium.presentation.api.routes.analysis import simulate_calendario_operacional

        svc = self._svc()
        svc.simulate_calendario_operacional.return_value = {"simulated": True}
        req = MagicMock()
        result = simulate_calendario_operacional("proj-1", req, service=svc)
        assert result["simulated"] is True

    def test_get_cubo_analitico_ok(self):
        from concilium.presentation.api.routes.analysis import get_cubo_analitico

        svc = self._svc()
        svc.get_cubo_analitico.return_value = {"faces": []}
        result = get_cubo_analitico("proj-1", version=None, service=svc)
        assert "faces" in result

    def test_get_cubo_analitico_not_found(self):
        from concilium.presentation.api.routes.analysis import get_cubo_analitico

        svc = self._svc()
        svc.get_cubo_analitico.side_effect = FileNotFoundError("not found")
        with pytest.raises(HTTPException) as exc:
            get_cubo_analitico("proj-1", version=None, service=svc)
        assert exc.value.status_code == 404

    def test_get_cubo_pool_projecao(self):
        from concilium.presentation.api.routes.analysis import get_cubo_pool_projecao

        svc = self._svc()
        svc.get_cubo_pool_projection.return_value = {"rows": []}
        result = get_cubo_pool_projecao("proj-1", face="instancia_ciclo_vida", version=None, service=svc)
        assert "rows" in result

    def test_get_benchmark_reference(self):
        from concilium.presentation.api.routes.analysis import get_benchmark_reference

        svc = self._svc()
        svc.get_benchmark_reference.return_value = {"slug": "AGIS"}
        result = get_benchmark_reference("proj-1", service=svc)
        assert result["slug"] == "AGIS"

    def test_get_benchmark_reference_not_found(self):
        from concilium.presentation.api.routes.analysis import get_benchmark_reference

        svc = self._svc()
        # If returns None, it should raise 404
        svc.get_benchmark_reference.side_effect = FileNotFoundError("not found")
        with pytest.raises(HTTPException) as exc:
            get_benchmark_reference("proj-1", service=svc)
        assert exc.value.status_code == 404

    def test_list_audit_ok(self):
        from concilium.presentation.api.routes.analysis import list_audit

        svc = self._svc()
        svc.list_audit.return_value = [{"action": "run"}]
        result = list_audit("proj-1", service=svc)
        assert "items" in result

    def test_compare_query_ok(self):
        from concilium.presentation.api.routes.analysis import compare_query

        svc = self._svc()
        svc.compare_versions.return_value = {"diff": []}
        result = compare_query("proj-1", left="v1", right="v2", service=svc)
        assert "diff" in result

    def test_compare_value_error(self):
        from concilium.presentation.api.routes.analysis import compare

        svc = self._svc()
        svc.compare_versions.side_effect = ValueError("bad version")
        req = MagicMock()
        req.left_version = "v1"
        req.right_version = "v2"
        with pytest.raises(HTTPException) as exc:
            compare("proj-1", req, service=svc)
        assert exc.value.status_code == 400

    def test_compare_query_value_error(self):
        from concilium.presentation.api.routes.analysis import compare_query

        svc = self._svc()
        svc.compare_versions.side_effect = ValueError("bad version")
        with pytest.raises(HTTPException) as exc:
            compare_query("proj-1", left="v1", right="v2", service=svc)
        assert exc.value.status_code == 400

    def test_download_artifact_ok(self):
        from concilium.presentation.api.routes.analysis import download_artifact

        svc = self._svc()
        svc.get_artifact_bytes.return_value = (b"data", "application/json")
        result = download_artifact("proj-1", kind="relatorio", filename="r.json", version=None, service=svc)
        assert result.body == b"data"

    def test_download_artifact_not_found(self):
        from concilium.presentation.api.routes.analysis import download_artifact

        svc = self._svc()
        svc.get_artifact_bytes.side_effect = FileNotFoundError("missing")
        with pytest.raises(HTTPException) as exc:
            download_artifact("proj-1", kind="relatorio", filename="r.json", version=None, service=svc)
        assert exc.value.status_code == 404

    def test_download_artifact_value_error(self):
        from concilium.presentation.api.routes.analysis import download_artifact

        svc = self._svc()
        svc.get_artifact_bytes.side_effect = ValueError("bad kind")
        with pytest.raises(HTTPException) as exc:
            download_artifact("proj-1", kind="bad", filename="r.json", version=None, service=svc)
        assert exc.value.status_code == 400

    def test_get_benchmark_reference_value_error(self):
        from concilium.presentation.api.routes.analysis import get_benchmark_reference

        svc = self._svc()
        svc.get_benchmark_reference.side_effect = ValueError("bad slug")
        with pytest.raises(HTTPException) as exc:
            get_benchmark_reference("proj-1", service=svc)
        assert exc.value.status_code == 400

    def test_get_diagnostico_pe_generic_exception_returns_aviso(self):
        from concilium.presentation.api.routes.analysis import get_diagnostico_pe

        svc = self._svc()
        svc.get_diagnostico_pe.side_effect = RuntimeError("cube unavailable")
        result = get_diagnostico_pe("proj-1", service=svc)
        assert result["diagnostico_pe"] is None
        assert result["backtracking_pe"] is None
        assert "cube unavailable" in result["aviso"]

    def test_get_calendario_operacional_not_found(self):
        from concilium.presentation.api.routes.analysis import get_calendario_operacional

        svc = self._svc()
        svc.get_calendario_operacional.side_effect = FileNotFoundError("missing")
        with pytest.raises(HTTPException) as exc:
            get_calendario_operacional("proj-1", version=None, service=svc)
        assert exc.value.status_code == 404

    def test_simulate_calendario_operacional_not_found(self):
        from concilium.presentation.api.routes.analysis import simulate_calendario_operacional

        svc = self._svc()
        svc.simulate_calendario_operacional.side_effect = FileNotFoundError("missing")
        req = MagicMock()
        req.model_dump.return_value = {}
        with pytest.raises(HTTPException) as exc:
            simulate_calendario_operacional("proj-1", req, version=None, service=svc)
        assert exc.value.status_code == 404

    def test_get_cubo_analitico_projecao_value_error(self):
        from concilium.presentation.api.routes.analysis import get_cubo_analitico_projecao

        svc = self._svc()
        svc.get_cubo_analitico_projection.side_effect = ValueError("bad face")
        with pytest.raises(HTTPException) as exc:
            get_cubo_analitico_projecao("proj-1", service=svc)
        assert exc.value.status_code == 400

    def test_get_cubo_analitico_projecao_not_found(self):
        from concilium.presentation.api.routes.analysis import get_cubo_analitico_projecao

        svc = self._svc()
        svc.get_cubo_analitico_projection.side_effect = FileNotFoundError("missing")
        with pytest.raises(HTTPException) as exc:
            get_cubo_analitico_projecao("proj-1", service=svc)
        assert exc.value.status_code == 404

    def test_get_cubo_analitico_projecao_contrato(self):
        from concilium.presentation.api.routes.analysis import get_cubo_analitico_projecao_contrato

        svc = self._svc()
        svc.get_cubo_projection_contract.return_value = {"faces": []}
        result = get_cubo_analitico_projecao_contrato("proj-1", service=svc)
        assert "faces" in result

    def test_get_cubo_pool_projecao_value_error(self):
        from concilium.presentation.api.routes.analysis import get_cubo_pool_projecao

        svc = self._svc()
        svc.get_cubo_pool_projection.side_effect = ValueError("bad face")
        with pytest.raises(HTTPException) as exc:
            get_cubo_pool_projecao("proj-1", version=None, service=svc)
        assert exc.value.status_code == 400

    def test_get_cubo_pool_projecao_not_found(self):
        from concilium.presentation.api.routes.analysis import get_cubo_pool_projecao

        svc = self._svc()
        svc.get_cubo_pool_projection.side_effect = FileNotFoundError("missing")
        with pytest.raises(HTTPException) as exc:
            get_cubo_pool_projecao("proj-1", version=None, service=svc)
        assert exc.value.status_code == 404

    def test_get_cubo_pool_projecao_contrato(self):
        from concilium.presentation.api.routes.analysis import get_cubo_pool_projecao_contrato

        svc = self._svc()
        svc.get_cubo_pool_projection_contract.return_value = {"faces": []}
        result = get_cubo_pool_projecao_contrato("proj-1", service=svc)
        assert "faces" in result



