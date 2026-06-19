"""Tests for API routes/auth.py — cover uncovered paths."""

from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi", reason="fastapi not installed")
from fastapi.testclient import TestClient  # noqa: E402

try:
    from concilium.presentation.api.app import create_app
except TypeError as exc:
    pytest.skip(f"FastAPI incompatível: {exc}", allow_module_level=True)


def _client():
    app = create_app()
    # Reset SlowAPI in-memory rate limiter to avoid cross-test bleeding
    try:
        from concilium.presentation.api.rate_limit import limiter

        if hasattr(limiter, "_storage") and hasattr(limiter._storage, "reset"):
            limiter._storage.reset()
    except Exception:
        pass
    return TestClient(app, raise_server_exceptions=False)


class TestIssueToken:
    def test_invalid_credentials_returns_401(self):
        from unittest.mock import MagicMock, patch

        c = _client()
        store_mock = MagicMock()
        store_mock.get_client_roles.return_value = None
        with patch("concilium.infrastructure.auth.auth_store.get_auth_store", return_value=store_mock):
            resp = c.post("/auth/token", json={"client_id": "bad", "client_secret": "bad"})
        assert resp.status_code == 401

    def test_valid_credentials_returns_token(self):
        from unittest.mock import MagicMock, patch

        c = _client()
        store_mock = MagicMock()
        store_mock.get_client_roles.return_value = ["viewer"]
        with (
            patch("concilium.infrastructure.auth.auth_store.get_auth_store", return_value=store_mock),
            patch("concilium.infrastructure.auth.token_service.issue_token", return_value="jwt-token-123"),
        ):
            resp = c.post("/auth/token", json={"client_id": "svc", "client_secret": "secret"})
        assert resp.status_code == 200
        assert resp.json()["access_token"] == "jwt-token-123"

    def test_valid_credentials_with_ttl_days(self):
        from unittest.mock import MagicMock, patch

        c = _client()
        store_mock = MagicMock()
        store_mock.get_client_roles.return_value = ["operator"]
        with (
            patch("concilium.infrastructure.auth.auth_store.get_auth_store", return_value=store_mock),
            patch("concilium.infrastructure.auth.token_service.issue_token", return_value="jwt-30d"),
        ):
            resp = c.post("/auth/token", json={"client_id": "svc", "client_secret": "secret", "ttl_days": 30})
        assert resp.status_code == 200


class TestActivateDevice:
    def test_invalid_device_code_returns_401(self):
        from unittest.mock import MagicMock, patch

        c = _client()
        store_mock = MagicMock()
        store_mock.activate_device_code.return_value = None
        with patch("concilium.infrastructure.auth.auth_store.get_auth_store", return_value=store_mock):
            resp = c.post("/auth/device/activate", json={"device_code": "bad"})
        assert resp.status_code == 401

    def test_valid_device_code_returns_refresh_token(self):
        from unittest.mock import MagicMock, patch

        c = _client()
        store_mock = MagicMock()
        rt = MagicMock()
        rt.token_id = "RT-abc"
        rt.device_id = "dev-1"
        rt.client_id = "svc"
        rt.roles = ["viewer"]
        rt.expires_at = "2026-12-31T00:00:00Z"
        store_mock.activate_device_code.return_value = rt
        with patch("concilium.infrastructure.auth.auth_store.get_auth_store", return_value=store_mock):
            resp = c.post("/auth/device/activate", json={"device_code": "RCODE-valid"})
        assert resp.status_code == 200
        assert resp.json()["refresh_token"] == "RT-abc"


class TestRefreshToken:
    def test_invalid_refresh_token_returns_401(self):
        from unittest.mock import MagicMock, patch

        c = _client()
        store_mock = MagicMock()
        store_mock.use_refresh_token.return_value = None
        with patch("concilium.infrastructure.auth.auth_store.get_auth_store", return_value=store_mock):
            resp = c.post("/auth/token/refresh", json={"refresh_token": "RT-invalid"})
        assert resp.status_code == 401

    def test_valid_refresh_token_returns_access_token(self):
        from unittest.mock import MagicMock, patch

        c = _client()
        store_mock = MagicMock()
        record = MagicMock()
        record.client_id = "svc"
        record.roles = ["operator"]
        store_mock.use_refresh_token.return_value = record
        with (
            patch("concilium.infrastructure.auth.auth_store.get_auth_store", return_value=store_mock),
            patch("concilium.infrastructure.auth.token_service.issue_token", return_value="new-jwt"),
        ):
            resp = c.post("/auth/token/refresh", json={"refresh_token": "RT-valid"})
        assert resp.status_code == 200
        assert resp.json()["access_token"] == "new-jwt"
