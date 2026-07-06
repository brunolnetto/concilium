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
    _is_public_tool_call,
    _make_cached_receive,
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


def _make_receive(body: bytes = b"{}") -> AsyncMock:
    """ASGI receive() mock returning a single complete http.request message.

    A bare AsyncMock() has no notion of ASGI message shape: _is_public_tool_call()
    loops `while True: message = await receive()` until it sees more_body=False,
    so an unconfigured mock spins forever instead of raising.
    """
    return AsyncMock(return_value={"type": "http.request", "body": body, "more_body": False})


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
    receive = _make_receive()
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
        receive = _make_receive()
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
        receive = _make_receive()
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
        receive = _make_receive()
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
        receive = _make_receive()
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
        receive = _make_receive()
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
        receive = _make_receive()
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
        receive = _make_receive()
        send = AsyncMock()

        fake_claims = {"roles": ["operator"], "sub": "u1"}
        fake_token_var = MagicMock()

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
                        with patch("concilium.infrastructure.auth.permission_guard._current_roles"):
                            await mw(scope, receive, send)

        inner.assert_awaited_once()
        awaited_scope, awaited_receive, awaited_send = inner.await_args.args
        assert awaited_scope == scope
        assert awaited_send is send
        assert callable(awaited_receive)  # body-caching wrapper replaces the original receive()

    @pytest.mark.asyncio
    async def test_valid_token_resets_contextvar_in_finally(self):
        inner = AsyncMock()
        mw = McpAuthMiddleware(inner)
        scope = _make_scope("http", headers=_auth_header("good.token"))
        receive = _make_receive()
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
        receive = _make_receive()
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
        receive = _make_receive()
        send = AsyncMock()
        with self._patch_auth_disabled():
            await mw(scope, receive, send)
        inner.assert_awaited_once()
        awaited_scope, awaited_receive, awaited_send = inner.await_args.args
        assert awaited_scope == scope
        assert awaited_send is send
        assert callable(awaited_receive)  # body-caching wrapper replaces the original receive()

    @pytest.mark.asyncio
    async def test_missing_auth_header_no_401_sent(self):
        """No 401 response emitted when auth is disabled and header is absent."""
        inner = AsyncMock()
        mw = McpAuthMiddleware(inner)
        scope = _make_scope("http", headers=[])
        receive = _make_receive()
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
        receive = _make_receive()
        send = AsyncMock()
        with self._patch_auth_disabled():
            with patch(
                "concilium.infrastructure.auth.token_service.decode_token",
                side_effect=Exception("some jwt error"),
            ):
                await mw(scope, receive, send)
        inner.assert_awaited_once()
        awaited_scope, awaited_receive, awaited_send = inner.await_args.args
        assert awaited_scope == scope
        assert awaited_send is send
        assert callable(awaited_receive)  # body-caching wrapper replaces the original receive()

    @pytest.mark.asyncio
    async def test_invalid_token_no_401_when_auth_disabled(self):
        """With auth disabled, token decode errors must not emit a 401."""
        inner = AsyncMock()
        mw = McpAuthMiddleware(inner)
        scope = _make_scope("http", headers=_auth_header("bad.token"))
        receive = _make_receive()
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
        receive = _make_receive()
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
    receive = _make_receive()
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
    receive = _make_receive()
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
    receive = _make_receive()
    send = AsyncMock()
    mock_auth = MagicMock()
    mock_auth.enabled = False
    with patch("concilium.presentation.mcp.middleware.get_auth", return_value=mock_auth):
        await mw(scope, receive, send)
    inner.assert_awaited_once()
    awaited_scope, awaited_receive, awaited_send = inner.await_args.args
    assert awaited_scope == scope
    assert awaited_send is send
    assert callable(awaited_receive)  # body-caching wrapper replaces the original receive()


@pytest.mark.asyncio
async def test_send_json_response_status_404():
    """_send_json_response works with arbitrary status codes."""
    send = _CapturingSend()
    await _send_json_response(send, 404, {"detail": "not found"})
    assert send.messages[0]["status"] == 404
    body = json.loads(send.messages[1]["body"])
    assert body == {"detail": "not found"}


# ---------------------------------------------------------------------------
# OTel best-effort exception handling (propagate.extract / set_baggage)
# ---------------------------------------------------------------------------


class TestBodyNotCachedWhenClientDisconnects:
    @pytest.mark.asyncio
    async def test_no_body_key_in_scope_skips_cached_receive_rewrap(self):
        """Quando o cliente desconecta durante a leitura de _is_public_tool_call,
        scope['_body'] nunca é setado — __call__ deve pular _make_cached_receive
        (branch false de `if "_body" in scope` na linha 160) e repassar o
        `receive` original para o app interno."""
        inner = AsyncMock()
        mw = McpAuthMiddleware(inner)
        scope = _make_scope("http", headers=[])
        receive = AsyncMock(return_value={"type": "http.disconnect"})
        send = AsyncMock()
        mock_auth = MagicMock()
        mock_auth.enabled = False
        with patch("concilium.presentation.mcp.middleware.get_auth", return_value=mock_auth):
            await mw(scope, receive, send)
        assert "_body" not in scope
        inner.assert_awaited_once()
        # o receive repassado ao app interno é o original (não o cached-receive)
        assert inner.call_args[0][1] is receive


class TestOtelBestEffort:
    @pytest.mark.asyncio
    async def test_propagate_extract_exception_is_swallowed(self):
        """propagate.extract() raising must not break the request (best-effort)."""
        inner = AsyncMock()
        mw = McpAuthMiddleware(inner)
        scope = _make_scope("http", headers=[])
        receive = _make_receive()
        send = AsyncMock()
        mock_auth = MagicMock()
        mock_auth.enabled = False
        with (
            patch("concilium.presentation.mcp.middleware.get_auth", return_value=mock_auth),
            patch(
                "concilium.presentation.mcp.middleware.propagate.extract",
                side_effect=RuntimeError("bad carrier"),
            ),
        ):
            await mw(scope, receive, send)
        inner.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_set_baggage_exception_is_swallowed(self):
        """set_baggage() raising during token processing must not break the request."""
        inner = AsyncMock()
        mw = McpAuthMiddleware(inner)
        scope = _make_scope("http", headers=_auth_header("good.token"))
        receive = _make_receive()
        send = AsyncMock()
        mock_auth = MagicMock()
        mock_auth.enabled = False
        fake_claims = {"roles": ["operator"], "sub": "u1", "tid": "tenant-1"}
        with (
            patch("concilium.presentation.mcp.middleware.get_auth", return_value=mock_auth),
            patch(
                "concilium.infrastructure.auth.token_service.decode_token",
                return_value=fake_claims,
            ),
            patch(
                "concilium.infrastructure.auth.permission_guard.roles_from_token",
                return_value=["operator"],
            ),
            patch(
                "concilium.presentation.mcp.middleware.set_baggage",
                side_effect=RuntimeError("baggage overflow"),
            ),
        ):
            await mw(scope, receive, send)
        inner.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_otel_unavailable_skips_traceparent_and_baggage_blocks(self):
        """Quando _OTEL_AVAILABLE é False, tanto o bloco de extração de
        traceparent quanto o de injeção de baggage são pulados inteiramente
        (branches false de `if _OTEL_AVAILABLE and ...` nas linhas 96 e 124)."""
        inner = AsyncMock()
        mw = McpAuthMiddleware(inner)
        scope = _make_scope("http", headers=_auth_header("good.token"))
        receive = _make_receive()
        send = AsyncMock()
        mock_auth = MagicMock()
        mock_auth.enabled = False
        fake_claims = {"roles": ["operator"], "sub": "u1", "tid": "tenant-1"}
        with (
            patch("concilium.presentation.mcp.middleware.get_auth", return_value=mock_auth),
            patch("concilium.presentation.mcp.middleware._OTEL_AVAILABLE", False),
            patch(
                "concilium.infrastructure.auth.token_service.decode_token",
                return_value=fake_claims,
            ),
            patch(
                "concilium.infrastructure.auth.permission_guard.roles_from_token",
                return_value=["operator"],
            ),
            patch(
                "concilium.presentation.mcp.middleware.propagate.extract",
                side_effect=AssertionError("não deveria ser chamado com OTel indisponível"),
            ),
            patch(
                "concilium.presentation.mcp.middleware.set_baggage",
                side_effect=AssertionError("não deveria ser chamado com OTel indisponível"),
            ),
        ):
            await mw(scope, receive, send)
        inner.assert_awaited_once()


# ---------------------------------------------------------------------------
# _make_cached_receive
# ---------------------------------------------------------------------------


class TestMakeCachedReceive:
    @pytest.mark.asyncio
    async def test_first_call_returns_cached_body(self):
        original = AsyncMock()
        receive = _make_cached_receive(b'{"a": 1}', original)
        message = await receive()
        assert message == {"type": "http.request", "body": b'{"a": 1}', "more_body": False}
        original.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_second_call_delegates_to_original_receive(self):
        original = AsyncMock(return_value={"type": "http.disconnect"})
        receive = _make_cached_receive(b"{}", original)
        await receive()
        second = await receive()
        assert second == {"type": "http.disconnect"}
        original.assert_awaited_once()


# ---------------------------------------------------------------------------
# _is_public_tool_call
# ---------------------------------------------------------------------------


class TestIsPublicToolCall:
    @pytest.mark.asyncio
    async def test_uses_cached_body_when_present(self):
        scope = {"_body": json.dumps({"method": "ping"}).encode("utf-8")}
        receive = AsyncMock()
        result = await _is_public_tool_call(scope, receive)
        assert result is True
        receive.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_disconnect_while_reading_body_returns_false(self):
        scope = {}
        receive = AsyncMock(return_value={"type": "http.disconnect"})
        result = await _is_public_tool_call(scope, receive)
        assert result is False

    @pytest.mark.asyncio
    async def test_empty_body_returns_false(self):
        scope = {}
        receive = AsyncMock(return_value={"type": "http.request", "body": b"", "more_body": False})
        result = await _is_public_tool_call(scope, receive)
        assert result is False
        assert scope["_body"] == b""

    @pytest.mark.asyncio
    async def test_public_method_returns_true(self):
        scope = {}
        body = json.dumps({"method": "notifications/initialized"}).encode("utf-8")
        receive = AsyncMock(return_value={"type": "http.request", "body": body, "more_body": False})
        result = await _is_public_tool_call(scope, receive)
        assert result is True

    @pytest.mark.asyncio
    async def test_tools_call_with_public_tool_name_returns_true(self):
        scope = {}
        body = json.dumps({"method": "tools/call", "params": {"name": "ativar_dispositivo"}}).encode("utf-8")
        receive = AsyncMock(return_value={"type": "http.request", "body": body, "more_body": False})
        result = await _is_public_tool_call(scope, receive)
        assert result is True

    @pytest.mark.asyncio
    async def test_unknown_message_type_is_ignored_and_loop_continues(self):
        """Uma mensagem ASGI que não é nem http.request nem http.disconnect é
        ignorada silenciosamente e o loop de leitura continua (branch false
        do elif, linha 222 -> volta para o topo do while)."""
        scope = {}
        body = json.dumps({"method": "ping"}).encode("utf-8")
        messages = [
            {"type": "http.lifespan.startup"},
            {"type": "http.request", "body": body, "more_body": False},
        ]
        receive = AsyncMock(side_effect=messages)
        result = await _is_public_tool_call(scope, receive)
        assert result is True
        assert scope["_body"] == body

    @pytest.mark.asyncio
    async def test_tools_call_with_private_tool_name_returns_false(self):
        scope = {}
        body = json.dumps({"method": "tools/call", "params": {"name": "some_private_tool"}}).encode("utf-8")
        receive = AsyncMock(return_value={"type": "http.request", "body": body, "more_body": False})
        result = await _is_public_tool_call(scope, receive)
        assert result is False

    @pytest.mark.asyncio
    async def test_multi_chunk_body_is_reassembled(self):
        """Body split across multiple http.request messages (more_body=True) must
        be concatenated before the loop exits — covers the while-loop back-edge."""
        scope = {}
        body = json.dumps({"method": "ping"}).encode("utf-8")
        half = len(body) // 2
        messages = [
            {"type": "http.request", "body": body[:half], "more_body": True},
            {"type": "http.request", "body": body[half:], "more_body": False},
        ]
        receive = AsyncMock(side_effect=messages)
        result = await _is_public_tool_call(scope, receive)
        assert result is True
        assert scope["_body"] == body

    @pytest.mark.asyncio
    async def test_malformed_json_body_returns_false(self):
        scope = {}
        receive = AsyncMock(return_value={"type": "http.request", "body": b"not json", "more_body": False})
        result = await _is_public_tool_call(scope, receive)
        assert result is False
