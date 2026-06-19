"""Unit tests for McpAuthMiddleware (presentation/mcp/middleware.py).

Tests McpAuthMiddleware as a pure-ASGI callable.
Covers all public functions: __init__, __call__, _auth_enabled, _send_json_response.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from concilium.presentation.mcp.middleware import (
    McpAuthMiddleware,
    _auth_enabled,
    _send_json_response,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_scope(scope_type: str = "http", headers: list | None = None) -> dict:
    """Build a minimal ASGI scope dict."""
    return {
        "type": scope_type,
        "headers": headers or [],
    }


def _auth_header(token: str) -> list:
    return [(b"authorization", f"Bearer {token}".encode("latin-1"))]


class _CapturingSend:
    """Async callable that records every ASGI message sent to it."""

    def __init__(self):
        self.messages: list[dict] = []

    async def __call__(self, message: dict) -> None:
        self.messages.append(message)


# ---------------------------------------------------------------------------
# _auth_enabled
# ---------------------------------------------------------------------------


class TestAuthEnabled:
    def test_returns_true_when_auth_enabled(self):
        mock_auth = MagicMock()
        mock_auth.enabled = True
        with patch("concilium.presentation.mcp.middleware.get_auth", return_value=mock_auth):
            assert _auth_enabled() is True

    def test_returns_false_when_auth_disabled(self):
        mock_auth = MagicMock()
        mock_auth.enabled = False
        with patch("concilium.presentation.mcp.middleware.get_auth", return_value=mock_auth):
            assert _auth_enabled() is False


# ---------------------------------------------------------------------------
# _send_json_response
# ---------------------------------------------------------------------------


class TestSendJsonResponse:
    @pytest.mark.asyncio
    async def test_sends_two_asgi_messages(self):
        send = _CapturingSend()
        await _send_json_response(send, 200, {"ok": True})
        assert len(send.messages) == 2

    @pytest.mark.asyncio
    async def test_response_start_status(self):
        send = _CapturingSend()
        await _send_json_response(send, 403, {"detail": "forbidden"})
        start = send.messages[0]
        assert start["type"] == "http.response.start"
        assert start["status"] == 403

    @pytest.mark.asyncio
    async def test_response_start_content_type(self):
        send = _CapturingSend()
        await _send_json_response(send, 200, {"x": 1})
        headers = dict(send.messages[0]["headers"])
        assert headers[b"content-type"] == b"application/json"

    @pytest.mark.asyncio
    async def test_response_start_content_length(self):
        send = _CapturingSend()
        body_dict = {"detail": "hello"}
        await _send_json_response(send, 200, body_dict)
        expected_len = len(json.dumps(body_dict, ensure_ascii=False).encode())
        headers = dict(send.messages[0]["headers"])
        assert headers[b"content-length"] == str(expected_len).encode()

    @pytest.mark.asyncio
    async def test_response_body_json(self):
        send = _CapturingSend()
        await _send_json_response(send, 401, {"detail": "nope"})
        body_msg = send.messages[1]
        assert body_msg["type"] == "http.response.body"
        assert body_msg["more_body"] is False
        parsed = json.loads(body_msg["body"])
        assert parsed == {"detail": "nope"}

    @pytest.mark.asyncio
    async def test_extra_headers_included(self):
        send = _CapturingSend()
        extra = [(b"www-authenticate", b"Bearer")]
        await _send_json_response(send, 401, {}, headers=extra)
        headers = dict(send.messages[0]["headers"])
        assert headers[b"www-authenticate"] == b"Bearer"

    @pytest.mark.asyncio
    async def test_no_extra_headers_when_none(self):
        send = _CapturingSend()
        await _send_json_response(send, 200, {})
        keys = [k for k, _ in send.messages[0]["headers"]]
        assert b"www-authenticate" not in keys

    @pytest.mark.asyncio
    async def test_unicode_body_encoded_correctly(self):
        send = _CapturingSend()
        await _send_json_response(send, 200, {"msg": "olá mundo"})
        body_bytes = send.messages[1]["body"]
        parsed = json.loads(body_bytes.decode("utf-8"))
        assert parsed["msg"] == "olá mundo"


# ---------------------------------------------------------------------------
# McpAuthMiddleware.__init__
# ---------------------------------------------------------------------------


class TestMcpAuthMiddlewareInit:
    def test_stores_inner_app(self):
        inner = AsyncMock()
        mw = McpAuthMiddleware(inner)
        assert mw._app is inner


# ---------------------------------------------------------------------------
# McpAuthMiddleware.__call__ — non-http scopes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("scope_type", ["websocket", "lifespan"])
@pytest.mark.asyncio
async def test_non_http_scope_forwarded(scope_type):
    """Non-http scopes must be forwarded to inner app unchanged."""
    inner = AsyncMock()
    mw = McpAuthMiddleware(inner)
    scope = _make_scope(scope_type)
    receive = AsyncMock()
    send = AsyncMock()
    await mw(scope, receive, send)
    inner.assert_awaited_once_with(scope, receive, send)
    send.assert_not_awaited()


# ---------------------------------------------------------------------------
# McpAuthMiddleware.__call__ — http scope, auth ENABLED
# ---------------------------------------------------------------------------


class TestMcpAuthMiddlewareHttpAuthEnabled:
    """Tests where auth is enabled (get_auth().enabled == True)."""

    def _patch_auth_enabled(self, enabled: bool):
        mock_auth = MagicMock()
        mock_auth.enabled = enabled
        return patch("concilium.presentation.mcp.middleware.get_auth", return_value=mock_auth)

    @pytest.mark.asyncio
    async def test_missing_authorization_header_returns_401(self):
        inner = AsyncMock()
        mw = McpAuthMiddleware(inner)
        scope = _make_scope("http", headers=[])
        receive = AsyncMock()
        send = _CapturingSend()
        with self._patch_auth_enabled(True):
            await mw(scope, receive, send)
        assert send.messages[0]["status"] == 401
        inner.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_missing_auth_header_sends_www_authenticate(self):
        inner = AsyncMock()
        mw = McpAuthMiddleware(inner)
        scope = _make_scope("http", headers=[])
        receive = AsyncMock()
        send = _CapturingSend()
        with self._patch_auth_enabled(True):
            await mw(scope, receive, send)
        headers_dict = dict(send.messages[0]["headers"])
        assert headers_dict.get(b"www-authenticate") == b"Bearer"

    @pytest.mark.asyncio
    async def test_missing_auth_header_body_detail(self):
        inner = AsyncMock()
        mw = McpAuthMiddleware(inner)
        scope = _make_scope("http", headers=[])
        receive = AsyncMock()
        send = _CapturingSend()
        with self._patch_auth_enabled(True):
            await mw(scope, receive, send)
        body = json.loads(send.messages[1]["body"])
        assert "ausente" in body["detail"].lower() or "bearer" in body["detail"].lower()

    @pytest.mark.asyncio
    async def test_invalid_token_returns_401(self):
        inner = AsyncMock()
        mw = McpAuthMiddleware(inner)
        scope = _make_scope("http", headers=_auth_header("bad.token.here"))
        receive = AsyncMock()
        send = _CapturingSend()
        with self._patch_auth_enabled(True):
            with patch(
                "concilium.infrastructure.auth.token_service.decode_token",
                side_effect=Exception("invalid token"),
            ):
                await mw(scope, receive, send)
        assert send.messages[0]["status"] == 401
        inner.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_invalid_token_www_authenticate_header(self):
        inner = AsyncMock()
        mw = McpAuthMiddleware(inner)
        scope = _make_scope("http", headers=_auth_header("bad.token"))
        receive = AsyncMock()
        send = _CapturingSend()
        with self._patch_auth_enabled(True):
            with patch(
                "concilium.infrastructure.auth.token_service.decode_token",
                side_effect=ValueError("expired"),
            ):
                await mw(scope, receive, send)
        headers_dict = dict(send.messages[0]["headers"])
        assert headers_dict.get(b"www-authenticate") == b"Bearer"

    @pytest.mark.asyncio
    async def test_invalid_token_body_contains_error(self):
        inner = AsyncMock()
        mw = McpAuthMiddleware(inner)
        scope = _make_scope("http", headers=_auth_header("bad.token"))
        receive = AsyncMock()
        send = _CapturingSend()
        exc_msg = "signature has expired"
        with self._patch_auth_enabled(True):
            with patch(
                "concilium.infrastructure.auth.token_service.decode_token",
                side_effect=Exception(exc_msg),
            ):
                await mw(scope, receive, send)
        body = json.loads(send.messages[1]["body"])
        assert exc_msg in body["detail"]

    @pytest.mark.asyncio
    async def test_valid_token_calls_inner_app(self):
        inner = AsyncMock()
        mw = McpAuthMiddleware(inner)
        scope = _make_scope("http", headers=_auth_header("good.token.here"))
        receive = AsyncMock()
        send = AsyncMock()

        fake_claims = {"roles": ["viewer"], "sub": "u1"}
        fake_token_var = MagicMock()

        with self._patch_auth_enabled(True):
            with patch(
                "concilium.infrastructure.auth.token_service.decode_token",
                return_value=fake_claims,
            ):
                with patch(
                    "concilium.infrastructure.auth.permission_guard.roles_from_token",
                    return_value=["viewer"],
                ) as mock_roles_from:
                    with patch(
                        "concilium.infrastructure.auth.permission_guard.set_roles",
                        return_value=fake_token_var,
                    ) as mock_set_roles:
                        with patch("concilium.infrastructure.auth.permission_guard._current_roles") as mock_var:
                            await mw(scope, receive, send)

        inner.assert_awaited_once_with(scope, receive, send)

    @pytest.mark.asyncio
    async def test_valid_token_resets_contextvar_in_finally(self):
        inner = AsyncMock()
        mw = McpAuthMiddleware(inner)
        scope = _make_scope("http", headers=_auth_header("good.token"))
        receive = AsyncMock()
        send = AsyncMock()

        fake_claims = {"roles": ["operator"], "sub": "u2"}
        fake_token_var = MagicMock()
        mock_current_roles = MagicMock()

        with self._patch_auth_enabled(True):
            with patch(
                "concilium.infrastructure.auth.token_service.decode_token",
                return_value=fake_claims,
            ):
                with patch(
                    "concilium.infrastructure.auth.permission_guard.roles_from_token",
                    return_value=["operator"],
                ):
                    with patch(
                        "concilium.infrastructure.auth.permission_guard.set_roles",
                        return_value=fake_token_var,
                    ):
                        with patch(
                            "concilium.infrastructure.auth.permission_guard._current_roles",
                            mock_current_roles,
                        ):
                            await mw(scope, receive, send)

        mock_current_roles.reset.assert_called_once_with(fake_token_var)

    @pytest.mark.asyncio
    async def test_contextvar_reset_even_if_inner_app_raises(self):
        """The finally block must reset the contextvar even when inner app raises."""

        async def raising_app(scope, receive, send):
            raise RuntimeError("inner exploded")

        mw = McpAuthMiddleware(raising_app)
        scope = _make_scope("http", headers=_auth_header("good.token"))
        receive = AsyncMock()
        send = AsyncMock()

        fake_claims = {"roles": ["admin"], "sub": "u3"}
        fake_token_var = MagicMock()
        mock_current_roles = MagicMock()

        with self._patch_auth_enabled(True):
            with patch(
                "concilium.infrastructure.auth.token_service.decode_token",
                return_value=fake_claims,
            ):
                with patch(
                    "concilium.infrastructure.auth.permission_guard.roles_from_token",
                    return_value=["admin"],
                ):
                    with patch(
                        "concilium.infrastructure.auth.permission_guard.set_roles",
                        return_value=fake_token_var,
                    ):
                        with patch(
                            "concilium.infrastructure.auth.permission_guard._current_roles",
                            mock_current_roles,
                        ):
                            with pytest.raises(RuntimeError, match="inner exploded"):
                                await mw(scope, receive, send)

        mock_current_roles.reset.assert_called_once_with(fake_token_var)


# ---------------------------------------------------------------------------
# McpAuthMiddleware.__call__ — http scope, auth DISABLED
# ---------------------------------------------------------------------------


class TestMcpAuthMiddlewareHttpAuthDisabled:
    """Tests where auth is disabled (get_auth().enabled == False)."""

    def _patch_auth_disabled(self):
        mock_auth = MagicMock()
        mock_auth.enabled = False
        return patch("concilium.presentation.mcp.middleware.get_auth", return_value=mock_auth)

    @pytest.mark.asyncio
    async def test_missing_auth_header_calls_inner_app(self):
        """No Authorization header + auth disabled → inner app called, no 401."""
        inner = AsyncMock()
        mw = McpAuthMiddleware(inner)
        scope = _make_scope("http", headers=[])
        receive = AsyncMock()
        send = AsyncMock()
        with self._patch_auth_disabled():
            await mw(scope, receive, send)
        inner.assert_awaited_once_with(scope, receive, send)

    @pytest.mark.asyncio
    async def test_missing_auth_header_no_401_sent(self):
        """No 401 response emitted when auth is disabled and header is absent."""
        inner = AsyncMock()
        mw = McpAuthMiddleware(inner)
        scope = _make_scope("http", headers=[])
        receive = AsyncMock()
        send = AsyncMock()
        with self._patch_auth_disabled():
            await mw(scope, receive, send)
        send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_invalid_token_error_swallowed_inner_app_called(self):
        """Invalid token with auth disabled → error swallowed, inner app still called."""
        inner = AsyncMock()
        mw = McpAuthMiddleware(inner)
        scope = _make_scope("http", headers=_auth_header("bad.token"))
        receive = AsyncMock()
        send = AsyncMock()
        with self._patch_auth_disabled():
            with patch(
                "concilium.infrastructure.auth.token_service.decode_token",
                side_effect=Exception("some jwt error"),
            ):
                await mw(scope, receive, send)
        inner.assert_awaited_once_with(scope, receive, send)

    @pytest.mark.asyncio
    async def test_invalid_token_no_401_when_auth_disabled(self):
        """With auth disabled, token decode errors must not emit a 401."""
        inner = AsyncMock()
        mw = McpAuthMiddleware(inner)
        scope = _make_scope("http", headers=_auth_header("bad.token"))
        receive = AsyncMock()
        send = AsyncMock()
        with self._patch_auth_disabled():
            with patch(
                "concilium.infrastructure.auth.token_service.decode_token",
                side_effect=Exception("some jwt error"),
            ):
                await mw(scope, receive, send)
        send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_contextvar_reset_when_no_valid_token(self):
        """When token decode fails and auth is disabled, no contextvar is set or reset."""
        inner = AsyncMock()
        mw = McpAuthMiddleware(inner)
        scope = _make_scope("http", headers=_auth_header("bad.token"))
        receive = AsyncMock()
        send = AsyncMock()
        mock_current_roles = MagicMock()
        with self._patch_auth_disabled():
            with patch(
                "concilium.infrastructure.auth.token_service.decode_token",
                side_effect=Exception("jwt error"),
            ):
                with patch(
                    "concilium.infrastructure.auth.permission_guard._current_roles",
                    mock_current_roles,
                ):
                    await mw(scope, receive, send)
        mock_current_roles.reset.assert_not_called()


# ---------------------------------------------------------------------------
# Parametrized: scope type forwarding
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "scope_type",
    ["websocket", "lifespan", "http2", "custom_type"],
)
@pytest.mark.asyncio
async def test_non_http_scopes_always_forwarded(scope_type):
    """Every non-http scope must be passed straight to inner app."""
    inner = AsyncMock()
    mw = McpAuthMiddleware(inner)
    scope = _make_scope(scope_type)
    receive = AsyncMock()
    send = AsyncMock()
    await mw(scope, receive, send)
    inner.assert_awaited_once_with(scope, receive, send)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_authorization_header_without_bearer_prefix_auth_enabled():
    """Header like 'Basic xxx' (not Bearer) triggers 401 when auth enabled."""
    inner = AsyncMock()
    mw = McpAuthMiddleware(inner)
    scope = _make_scope("http", headers=[(b"authorization", b"Basic dXNlcjpwYXNz")])
    receive = AsyncMock()
    send = _CapturingSend()
    mock_auth = MagicMock()
    mock_auth.enabled = True
    with patch("concilium.presentation.mcp.middleware.get_auth", return_value=mock_auth):
        await mw(scope, receive, send)
    assert send.messages[0]["status"] == 401
    inner.assert_not_awaited()


@pytest.mark.asyncio
async def test_authorization_header_without_bearer_prefix_auth_disabled():
    """Header like 'Basic xxx' with auth disabled → inner app called (no token)."""
    inner = AsyncMock()
    mw = McpAuthMiddleware(inner)
    scope = _make_scope("http", headers=[(b"authorization", b"Basic dXNlcjpwYXNz")])
    receive = AsyncMock()
    send = AsyncMock()
    mock_auth = MagicMock()
    mock_auth.enabled = False
    with patch("concilium.presentation.mcp.middleware.get_auth", return_value=mock_auth):
        await mw(scope, receive, send)
    inner.assert_awaited_once_with(scope, receive, send)


@pytest.mark.asyncio
async def test_send_json_response_status_404():
    """_send_json_response works with arbitrary status codes."""
    send = _CapturingSend()
    await _send_json_response(send, 404, {"detail": "not found"})
    assert send.messages[0]["status"] == 404
    body = json.loads(send.messages[1]["body"])
    assert body == {"detail": "not found"}
