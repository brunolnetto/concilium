"""Coverage sweep 2 — medium missing-line files (8-25 lines)."""

from __future__ import annotations

from unittest.mock import patch

# ─── jwt_auth middleware ──────────────────────────────────────────────────────


class TestJwtAuth:
    def test_unauthorized_returns_401(self):
        from concilium.presentation.api.middleware.jwt_auth import _unauthorized

        resp = _unauthorized("missing token")
        assert resp.status_code == 401

    def test_auth_enabled_reads_setting(self):
        from concilium.presentation.api.middleware.jwt_auth import _auth_enabled

        with patch("concilium.presentation.api.middleware.jwt_auth.get_auth") as mock_ga:
            mock_ga.return_value.enabled = False
            assert _auth_enabled() is False
            mock_ga.return_value.enabled = True
            assert _auth_enabled() is True

    def test_skip_paths_contains_health(self):
        from concilium.presentation.api.middleware.jwt_auth import _SKIP_PATHS

        assert "/health" in _SKIP_PATHS
        assert "/auth/token" in _SKIP_PATHS






from unittest.mock import AsyncMock, MagicMock  # noqa: E402

import pytest  # noqa: E402

# ─── presentation/api/middleware/jwt_auth.py ──────────────────────────────────


class TestJWTAuthMiddleware:
    def _make_middleware(self):
        from concilium.presentation.api.middleware.jwt_auth import JWTAuthMiddleware

        app_mock = MagicMock()
        return JWTAuthMiddleware(app_mock)

    def _make_request(self, path: str = "/runs", auth_header: str = "") -> MagicMock:
        req = MagicMock()
        req.url.path = path
        req.headers = {"Authorization": auth_header} if auth_header else {}
        req.state = MagicMock()
        return req

    @pytest.mark.asyncio
    async def test_skip_path_passes_through(self):
        mw = self._make_middleware()
        req = self._make_request(path="/health")
        call_next = AsyncMock(return_value=MagicMock())
        with patch("concilium.presentation.api.middleware.jwt_auth._auth_enabled", return_value=True):
            await mw.dispatch(req, call_next)
        call_next.assert_called_once_with(req)

    @pytest.mark.asyncio
    async def test_auth_disabled_passes_through(self):
        mw = self._make_middleware()
        req = self._make_request(path="/runs")
        call_next = AsyncMock(return_value=MagicMock())
        with patch("concilium.presentation.api.middleware.jwt_auth._auth_enabled", return_value=False):
            await mw.dispatch(req, call_next)
        call_next.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_bearer_returns_401(self):
        from fastapi.responses import JSONResponse

        mw = self._make_middleware()
        req = self._make_request(path="/runs", auth_header="")
        call_next = AsyncMock()
        with patch("concilium.presentation.api.middleware.jwt_auth._auth_enabled", return_value=True):
            result = await mw.dispatch(req, call_next)
        assert isinstance(result, JSONResponse)
        assert result.status_code == 401
        call_next.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_token_returns_401(self):
        from fastapi.responses import JSONResponse

        mw = self._make_middleware()
        req = self._make_request(path="/runs", auth_header="Bearer badtoken")
        call_next = AsyncMock()
        with (
            patch("concilium.presentation.api.middleware.jwt_auth._auth_enabled", return_value=True),
            patch("concilium.infrastructure.auth.token_service.decode_token", side_effect=ValueError("bad")),
        ):
            result = await mw.dispatch(req, call_next)
        assert isinstance(result, JSONResponse)
        assert result.status_code == 401

    @pytest.mark.asyncio
    async def test_valid_token_sets_claims_and_passes_through(self):
        mw = self._make_middleware()
        req = self._make_request(path="/runs", auth_header="Bearer validtoken")
        call_next = AsyncMock(return_value=MagicMock())
        with (
            patch("concilium.presentation.api.middleware.jwt_auth._auth_enabled", return_value=True),
            patch("concilium.infrastructure.auth.token_service.decode_token", return_value={"sub": "u1"}),
        ):
            await mw.dispatch(req, call_next)
        assert req.state.jwt_claims == {"sub": "u1"}
        call_next.assert_called_once()



