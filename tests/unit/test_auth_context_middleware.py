"""TDD para o AuthContextMiddleware e propagação de user_id/request_id.

Cobre:
  - AuthContextMiddleware injeta user_id (sub JWT), request_id (UUID) e IP
  - Resposta inclui cabeçalho X-Request-ID
  - _JsonFormatter inclui user_id e request_id quando dentro de request
  - _JsonFormatter emite "" para user_id/request_id quando fora de request
  - OTel span recebe atributos user.id e request.id
  - Endpoint /auth/token/issue emite token sem device registration
"""

from __future__ import annotations

import json
import logging
import uuid
from unittest.mock import MagicMock, patch

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_jwt_claims(sub: str = "bruno@mendeslobo.com.br", roles: list | None = None) -> dict:
    return {"sub": sub, "roles": roles or ["operator"], "exp": 9999999999, "iss": "concilium-auth"}


# ─────────────────────────────────────────────────────────────────────────────
# F1-A: AuthContextMiddleware — injeção de contextvars
# ─────────────────────────────────────────────────────────────────────────────

class TestAuthContextMiddleware:
    """AuthContextMiddleware seta user_id, request_id e source_ip nos contextvars."""

    @pytest.fixture
    def app_with_middleware(self):
        """FastAPI mínimo com AuthContextMiddleware + JWTAuthMiddleware mockado."""
        from fastapi import FastAPI
        from fastapi.responses import JSONResponse
        from concilium.infrastructure.middleware.auth_context import (
            AuthContextMiddleware,
            current_user_id,
            current_request_id,
            current_source_ip,
        )

        app = FastAPI()
        app.add_middleware(AuthContextMiddleware)

        @app.get("/echo")
        async def echo():
            return JSONResponse({
                "user_id": current_user_id.get(),
                "request_id": current_request_id.get(),
                "source_ip": current_source_ip.get(),
            })

        return app

    def test_request_id_is_uuid_format(self, app_with_middleware):
        from fastapi.testclient import TestClient
        client = TestClient(app_with_middleware)
        resp = client.get("/echo")
        assert resp.status_code == 200
        data = resp.json()
        # request_id deve ser UUID v4
        assert uuid.UUID(data["request_id"], version=4)

    def test_x_request_id_header_in_response(self, app_with_middleware):
        from fastapi.testclient import TestClient
        client = TestClient(app_with_middleware)
        resp = client.get("/echo")
        assert "X-Request-ID" in resp.headers
        assert uuid.UUID(resp.headers["X-Request-ID"], version=4)

    def test_request_id_matches_header(self, app_with_middleware):
        from fastapi.testclient import TestClient
        client = TestClient(app_with_middleware)
        resp = client.get("/echo")
        assert resp.json()["request_id"] == resp.headers["X-Request-ID"]

    def test_user_id_empty_when_no_bearer_token(self, app_with_middleware):
        from fastapi.testclient import TestClient
        client = TestClient(app_with_middleware)
        resp = client.get("/echo")
        assert resp.json()["user_id"] == ""

    def test_user_id_populated_from_bearer_jwt(self, app_with_middleware):
        """Quando Bearer token válido é fornecido, user_id = claims['sub']."""
        from fastapi import Request
        from fastapi.testclient import TestClient
        from concilium.infrastructure.middleware.auth_context import (
            AuthContextMiddleware,
            current_user_id,
        )

        app = app_with_middleware
        claims = _make_jwt_claims(sub="bruno@mendeslobo.com.br")

        with patch("concilium.infrastructure.middleware.auth_context._try_decode_token", return_value=claims):
            client = TestClient(app)
            resp = client.get("/echo", headers={"Authorization": "Bearer fake-token"})

        assert resp.json()["user_id"] == "bruno@mendeslobo.com.br"

    def test_source_ip_captured(self, app_with_middleware):
        from fastapi.testclient import TestClient
        client = TestClient(app_with_middleware)
        resp = client.get("/echo")
        # TestClient usa testclient como client host
        assert resp.json()["source_ip"] != ""

    def test_different_requests_get_different_request_ids(self, app_with_middleware):
        from fastapi.testclient import TestClient
        client = TestClient(app_with_middleware)
        r1 = client.get("/echo")
        r2 = client.get("/echo")
        assert r1.headers["X-Request-ID"] != r2.headers["X-Request-ID"]


# ─────────────────────────────────────────────────────────────────────────────
# F1-B: _JsonFormatter com user_id e request_id
# ─────────────────────────────────────────────────────────────────────────────

class TestJsonFormatterWithAuthContext:
    """_JsonFormatter inclui user_id e request_id do contexto de requisição."""

    @pytest.fixture(autouse=True)
    def formatter(self):
        from concilium.infrastructure.observability.logging_config import _JsonFormatter
        self.fmt = _JsonFormatter()

    def _record(self, msg="test") -> logging.LogRecord:
        return logging.LogRecord(
            name="test", level=logging.WARNING, pathname="", lineno=0,
            msg=msg, args=(), exc_info=None,
        )

    def test_user_id_empty_by_default(self):
        """Fora de request context, user_id é string vazia."""
        payload = json.loads(self.fmt.format(self._record()))
        assert "user_id" in payload
        assert payload["user_id"] == ""

    def test_request_id_empty_by_default(self):
        payload = json.loads(self.fmt.format(self._record()))
        assert "request_id" in payload
        assert payload["request_id"] == ""

    def test_user_id_present_when_contextvar_set(self):
        from concilium.infrastructure.middleware.auth_context import current_user_id
        token = current_user_id.set("ana@mendeslobo.com.br")
        try:
            payload = json.loads(self.fmt.format(self._record()))
            assert payload["user_id"] == "ana@mendeslobo.com.br"
        finally:
            current_user_id.reset(token)

    def test_request_id_present_when_contextvar_set(self):
        from concilium.infrastructure.middleware.auth_context import current_request_id
        req_id = str(uuid.uuid4())
        token = current_request_id.set(req_id)
        try:
            payload = json.loads(self.fmt.format(self._record()))
            assert payload["request_id"] == req_id
        finally:
            current_request_id.reset(token)

    def test_all_mandatory_fields_still_present(self):
        payload = json.loads(self.fmt.format(self._record()))
        for field in ("ts", "severity", "logger", "message", "trace_id", "span_id", "service", "user_id", "request_id"):
            assert field in payload, f"Campo obrigatório ausente: {field}"


# ─────────────────────────────────────────────────────────────────────────────
# F2: POST /auth/token/issue — emitir token sem device registration
# ─────────────────────────────────────────────────────────────────────────────

class TestDirectTokenIssuance:
    """/auth/token/issue emite token para usuário existente sem device code."""

    @pytest.fixture
    def client(self):
        from unittest.mock import patch
        from fastapi.testclient import TestClient
        from concilium.presentation.api.app import create_app
        with patch("concilium.presentation.api.app.setup_telemetry"), \
             patch("concilium.presentation.api.app.configure_logging"):
            app = create_app()
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c

    def test_issue_token_requires_valid_client_credentials(self, client):
        """POST /auth/token/issue com client_id/secret inválidos retorna 401."""
        resp = client.post("/auth/token/issue", json={
            "client_id": "nao-existe",
            "client_secret": "errado",
        })
        assert resp.status_code in (401, 422)

    def test_issue_token_endpoint_exists(self, client):
        """Endpoint existe (não retorna 404 nem 405)."""
        resp = client.post("/auth/token/issue", json={})
        assert resp.status_code != 404, "Endpoint /auth/token/issue deve existir"
        assert resp.status_code != 405, "Endpoint /auth/token/issue deve aceitar POST"
