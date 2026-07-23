"""Tests for formulario route, mcp/__main__, api/routes/benchmarks, concilium_service gaps."""

from __future__ import annotations

from unittest.mock import patch

import pytest

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



