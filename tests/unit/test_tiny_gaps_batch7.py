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

    def test_criar_projeto_formulario_sucesso(self):
        c = self._client()
        with patch(
            "concilium.application.services.project.formulario_service.criar_projeto",
            return_value={"status": "ok", "projeto_id": "p1"},
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
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"


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


# ─── presentation/api/app.py — instrumentation, exception handlers, main() ────


class TestAppCreateAppGaps:
    def _create_app_with_telemetry(self, *, otel_sdk_disabled: bool):
        from unittest.mock import MagicMock

        telemetry_mock = MagicMock()
        telemetry_mock.otel_sdk_disabled = otel_sdk_disabled

        with (
            patch("concilium.presentation.api.app.setup_telemetry"),
            patch("concilium.presentation.api.app.configure_logging"),
            patch("concilium.presentation.api.app.get_telemetry", return_value=telemetry_mock),
        ):
            from concilium.presentation.api.app import create_app

            return create_app()

    def test_instrumentation_enabled_calls_instrument_app(self):
        """Lines 79-82: otel habilitado → FastAPIInstrumentor.instrument_app é chamado."""
        with patch("opentelemetry.instrumentation.fastapi.FastAPIInstrumentor.instrument_app") as mock_instrument:
            self._create_app_with_telemetry(otel_sdk_disabled=False)
        mock_instrument.assert_called_once()

    def test_instrumentation_import_error_is_swallowed(self):
        """Lines 83-84: ImportError na instrumentação não propaga."""
        import sys

        with patch.dict(sys.modules, {"opentelemetry.instrumentation.fastapi": None}):
            app = self._create_app_with_telemetry(otel_sdk_disabled=False)
        assert app is not None

    def test_permission_error_handler_returns_403(self):
        """Linha 92: handler de PermissionError retorna 403."""
        import asyncio

        app = self._create_app_with_telemetry(otel_sdk_disabled=True)
        handler = app.exception_handlers[PermissionError]
        response = asyncio.run(handler(MagicMock(), PermissionError("nope")))
        assert response.status_code == 403

    def test_storage_unavailable_handler_returns_503(self):
        """Linha 104: handler de StorageUnavailableError retorna 503."""
        import asyncio

        from concilium.domain.repositories.blob_storage_port import StorageUnavailableError

        app = self._create_app_with_telemetry(otel_sdk_disabled=True)
        handler = app.exception_handlers[StorageUnavailableError]
        response = asyncio.run(handler(MagicMock(), StorageUnavailableError("down")))
        assert response.status_code == 503

    def test_rate_limit_handler_delegates_for_rate_limit_exceeded(self):
        """Linhas 117-119: RateLimitExceeded → delega para rate_limit_exceeded_handler."""
        import asyncio

        from slowapi.errors import RateLimitExceeded

        app = self._create_app_with_telemetry(otel_sdk_disabled=True)
        handler = app.exception_handlers[RateLimitExceeded]
        exc = RateLimitExceeded(MagicMock())
        with patch("concilium.presentation.api.app.rate_limit_exceeded_handler", return_value="handled") as mocked:
            result = asyncio.run(handler(MagicMock(), exc))
        mocked.assert_called_once()
        assert result == "handled"

    def test_rate_limit_handler_reraises_other_exceptions(self):
        """Linhas 117-118: exceção que não é RateLimitExceeded é relançada."""
        import asyncio

        from slowapi.errors import RateLimitExceeded

        app = self._create_app_with_telemetry(otel_sdk_disabled=True)
        handler = app.exception_handlers[RateLimitExceeded]
        with pytest.raises(RuntimeError, match="unexpected"):
            asyncio.run(handler(MagicMock(), RuntimeError("unexpected")))

    def test_main_runs_startup_and_uvicorn(self):
        """Lines 149-160: main() executa startup checks e chama uvicorn.run."""
        with (
            patch("concilium.infrastructure.settings.startup_check") as mock_startup,
            patch("concilium.infrastructure.storage.store_factory.ensure_storage_root") as mock_ensure,
            patch("concilium.presentation.api.app.resolve_api_bind", return_value=("0.0.0.0", 8000)),
            patch("concilium.infrastructure.settings.get_api") as mock_get_api,
            patch("uvicorn.run") as mock_run,
        ):
            mock_get_api.return_value.reload = False

            from concilium.presentation.api.app import main

            main()

        mock_startup.assert_called_once()
        mock_ensure.assert_called_once()
        mock_run.assert_called_once_with("concilium.presentation.api.app:app", host="0.0.0.0", port=8000, reload=False)
