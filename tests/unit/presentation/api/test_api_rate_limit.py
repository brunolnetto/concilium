"""Tests for small-gap files: benchmark repository port, week_sequence, config mixin,
permission_guard, rate_limit, jwt_auth, replan MCP tool."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

# ─── presentation/api/rate_limit.py ───────────────────────────────────────────


class TestRateLimit:
    def test_rate_limit_key_uses_jwt_sub(self):
        from concilium.presentation.api.rate_limit import _rate_limit_key

        req = MagicMock()
        req.headers = {"Authorization": "Bearer mytoken"}
        with patch(
            "concilium.infrastructure.auth.token_service.decode_token",
            return_value={"sub": "user-123"},
        ):
            result = _rate_limit_key(req)
        assert result == "user:user-123"

    def test_rate_limit_key_falls_back_to_ip(self):
        from concilium.presentation.api.rate_limit import _rate_limit_key

        req = MagicMock()
        req.headers = {}
        with patch("concilium.presentation.api.rate_limit.get_remote_address", return_value="1.2.3.4"):
            result = _rate_limit_key(req)
        assert result == "ip:1.2.3.4"

    def test_rate_limit_key_decode_exception_falls_back(self):
        from concilium.presentation.api.rate_limit import _rate_limit_key

        req = MagicMock()
        req.headers = {"Authorization": "Bearer badtoken"}
        with (
            patch("concilium.infrastructure.auth.token_service.decode_token", side_effect=ValueError("bad")),
            patch("concilium.presentation.api.rate_limit.get_remote_address", return_value="5.6.7.8"),
        ):
            result = _rate_limit_key(req)
        assert result == "ip:5.6.7.8"

    def test_rate_limit_key_bearer_without_sub_falls_back_to_ip(self):
        """Linha 36->40: token válido decodifica mas payload não tem 'sub' → fallback IP."""
        from concilium.presentation.api.rate_limit import _rate_limit_key

        req = MagicMock()
        req.headers = {"Authorization": "Bearer no-sub-token"}
        with (
            patch(
                "concilium.infrastructure.auth.token_service.decode_token",
                return_value={"other_claim": "x"},
            ),
            patch("concilium.presentation.api.rate_limit.get_remote_address", return_value="9.9.9.9"),
        ):
            result = _rate_limit_key(req)
        assert result == "ip:9.9.9.9"

    def test_rate_limit_exceeded_handler_swallows_telemetry_exception(self):
        """Linhas 59-60: exceção ao emitir métrica OTEL não propaga."""
        from slowapi.errors import RateLimitExceeded

        from concilium.presentation.api.rate_limit import rate_limit_exceeded_handler

        req = MagicMock()
        req.url.path = "/runs"
        exc = MagicMock(spec=RateLimitExceeded)
        with (
            patch(
                "concilium.infrastructure.telemetry.record_rate_limit_exceeded",
                side_effect=RuntimeError("otel down"),
            ),
            patch("concilium.presentation.api.rate_limit._slowapi_429", return_value=MagicMock()) as mocked_429,
        ):
            result = rate_limit_exceeded_handler(req, exc)
        assert result is not None
        mocked_429.assert_called_once()

    def test_rate_limit_exceeded_handler_does_not_raise(self):
        from slowapi.errors import RateLimitExceeded

        from concilium.presentation.api.rate_limit import rate_limit_exceeded_handler

        req = MagicMock()
        req.url.path = "/runs"
        exc = MagicMock(spec=RateLimitExceeded)
        with (
            patch("concilium.infrastructure.telemetry.record_rate_limit_exceeded"),
            patch("concilium.presentation.api.rate_limit._slowapi_429", return_value=MagicMock()),
        ):
            result = rate_limit_exceeded_handler(req, exc)
        assert result is not None



