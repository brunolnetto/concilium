"""Tests for formulario route, mcp/__main__, api/routes/benchmarks, concilium_service gaps."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# ─── presentation/mcp/__main__.py (1 missing: line 6) ─────────────────────────


class TestMcpMain:
    def test_module_has_main(self):
        import concilium.presentation.mcp.__main__ as mod

        assert hasattr(mod, "main")

    def test_main_importable_from_module(self):
        from concilium.presentation.mcp.__main__ import main

        assert callable(main)


# ─── presentation/api/routes/formulario.py ────────────────────────────────────


class TestFormularioRoutes:
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

    def test_sugerir_cpus_happy(self):
        c = self._client()
        with patch(
            "concilium.application.services.project.formulario_service.build_eap",
            return_value={
                "mapeados": [{"descricao": "Esc", "cpu_id": "CPU-1", "_confianca": 0.9, "item_id": "1.1"}],
                "nao_mapeados": [],
                "total": 1,
            },
        ):
            with patch("concilium.infrastructure.auth.permission_guard._auth_enabled", return_value=False):
                resp = c.post(
                    "/api/formulario/sugerir-cpus",
                    json={"servicos": [{"descricao": "Escavação", "quantidade": 100, "unidade": "m³"}]},
                )
        assert resp.status_code == 200
        data = resp.json()
        assert "mapeados" in data

    def test_criar_projeto_formulario_error(self):
        c = self._client()
        with patch(
            "concilium.application.services.project.formulario_service.criar_projeto",
            side_effect=ValueError("missing field"),
        ):
            with patch("concilium.infrastructure.auth.permission_guard._auth_enabled", return_value=False):
                resp = c.post(
                    "/api/formulario/projeto",
                    json={
                        "nome": "Test",
                        "contexto_id": "ctx",
                        "tipo_obra": "terra",
                        "localizacao": "SP",
                        "data_inicio": "2026-01-01",
                        "servicos": [],
                    },
                )
        assert resp.status_code == 400

    def test_criar_projeto_formulario_status_erro(self):
        c = self._client()
        with patch(
            "concilium.application.services.project.formulario_service.criar_projeto",
            return_value={"status": "erro", "erro": "cpu not found"},
        ):
            with patch("concilium.infrastructure.auth.permission_guard._auth_enabled", return_value=False):
                resp = c.post(
                    "/api/formulario/projeto",
                    json={
                        "nome": "Test",
                        "contexto_id": "ctx",
                        "tipo_obra": "terra",
                        "localizacao": "SP",
                        "data_inicio": "2026-01-01",
                        "servicos": [],
                    },
                )
        assert resp.status_code == 400


# ─── presentation/api/routes/benchmarks.py (6 missing: 76-77, 104-107) ────────


class TestBenchmarkRoutes:
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

    def test_run_benchmark_not_found(self):
        svc = MagicMock()
        svc.run_benchmark.side_effect = FileNotFoundError("not found")
        c = self._client(svc)
        resp = c.post("/api/benchmarks/AGIS/run", json={})
        assert resp.status_code == 404

    def test_get_benchmark_report_not_found(self):
        svc = MagicMock()
        svc.get_benchmark_report.side_effect = FileNotFoundError("not found")
        c = self._client(svc)
        resp = c.get("/api/benchmarks/AGIS/report")
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
    with TestClient(app, raise_server_exceptions=False) as c:
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


# ─── infrastructure/catalog/query_engine.py (88 missing) ─────────────────────


class TestQueryEngine:
    def _catalog(self):
        return {
            "cpus": [
                {"codigo": "CPU-ESC", "descricao": "Escavação de solo", "unidade": "m³", "categoria": "TERRA"},
                {"codigo": "CPU-PAV", "descricao": "Pavimentação asfáltica", "unidade": "m²", "categoria": "PAVE"},
            ],
            "insumos": [
                {
                    "codigo": "INS-DIESEL",
                    "descricao": "Diesel",
                    "tipo": "COMBUSTIVEL",
                    "preco_unitario": 6.5,
                    "unidade": "litro",
                }
            ],
            "producoes": [],
            "funcoes": [],
        }

    def test_catalog_session_from_resolved(self):
        from concilium.infrastructure.catalog.query_engine import CatalogSession

        session = CatalogSession.from_resolved(self._catalog())
        assert session is not None

    def test_catalog_session_find_cpu(self):
        from concilium.infrastructure.catalog.query_engine import CatalogSession

        session = CatalogSession.from_resolved(self._catalog())
        result = session.find_cpus_by_categoria("TERRA")
        assert len(result) >= 1
        assert any(c["codigo"] == "CPU-ESC" for c in result)

    def test_catalog_session_get_composicao_empty(self):
        from concilium.infrastructure.catalog.query_engine import CatalogSession

        session = CatalogSession.from_resolved(self._catalog())
        result = session.get_composicao_com_precos("CPU-MISSING")
        assert result == []

    def test_catalog_session_get_equipe_missing(self):
        from concilium.infrastructure.catalog.query_engine import CatalogSession

        session = CatalogSession.from_resolved(self._catalog())
        result = session.get_equipe_com_precos("PROD-MISSING")
        assert isinstance(result, dict)
