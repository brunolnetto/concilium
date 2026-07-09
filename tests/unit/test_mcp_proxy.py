"""Unit tests for concilium.presentation.mcp.proxy (ADR-094 / refactor MCP-protocol auth).

Covers:
  - _load_cache / _save_cache round-trip
  - _mcp_call: JSON and SSE response parsing, error branches
  - _initialize_session: session_id extraction from header
  - _activate: happy-path and error branches (via client_code, MCP tool ativar_dispositivo)
  - _get_access_token: cached refresh_token renewal, fallback to _activate
  - _refresh_loop background thread (one iteration)
  - _bridge async bridge: JSON response, SSE, 401-retry, non-200, malformed JSON
  - _write_error structure
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers to build a minimal mock httpx response
# ---------------------------------------------------------------------------


def _make_response(status_code: int = 200, body: dict | str = "", headers=None):
    resp = MagicMock()
    resp.status_code = status_code
    if isinstance(body, dict):
        resp.json.return_value = body
        resp.text = json.dumps(body)
    else:
        resp.text = body
        resp.json.side_effect = json.JSONDecodeError("bad", "", 0)
    resp.headers = headers or {}
    return resp


class _FakeStreamResponse:
    """Mimics the context manager returned by httpx.Client.stream(...)."""

    def __init__(self, status_code=200, headers=None, chunks=None, lines=None):
        self.status_code = status_code
        self.headers = headers or {}
        self._chunks = chunks or []
        self._lines = lines or []

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def iter_bytes(self, chunk_size=None):
        yield from self._chunks

    def iter_lines(self):
        yield from self._lines


def _stream_client(response: _FakeStreamResponse) -> MagicMock:
    """Build a MagicMock httpx.Client whose .stream(...) returns `response`."""
    http = MagicMock()
    http.stream.return_value = response
    return http


def _tool_result(status: str = "ok", **fields) -> dict:
    """Build an MCP tools/call 'result' payload as FastMCP wraps it: {"content": [...]}"""
    payload = {"status": status, **fields}
    return {"content": [{"text": json.dumps(payload)}]}


# ---------------------------------------------------------------------------
# Module-level patch context: redirect _TOKEN_DIR to tmp_path
# ---------------------------------------------------------------------------

import concilium.presentation.mcp.proxy as proxy_mod  # noqa: E402

# ---------------------------------------------------------------------------
# _load_cache / _save_cache
# ---------------------------------------------------------------------------


class TestLoadSaveCache:
    def test_save_creates_file_with_correct_content(self, tmp_path):
        """_save_cache writes JSON and sets chmod 600."""
        with patch.object(proxy_mod, "_TOKEN_DIR", tmp_path), patch.object(proxy_mod, "_DEVICE_ID", "test-device"):
            data = {"refresh_token": "abc123", "scopes": ["read"]}
            proxy_mod._save_cache(data)

            token_file = tmp_path / "test-device.json"
            assert token_file.exists()
            loaded = json.loads(token_file.read_text())
            assert loaded == data
            # chmod 600 → oct 0o600
            assert oct(token_file.stat().st_mode)[-3:] == "600"

    def test_load_reads_saved_data(self, tmp_path):
        """_load_cache returns what _save_cache wrote."""
        with patch.object(proxy_mod, "_TOKEN_DIR", tmp_path), patch.object(proxy_mod, "_DEVICE_ID", "test-device"):
            data = {"refresh_token": "tok", "scopes": []}
            proxy_mod._save_cache(data)
            result = proxy_mod._load_cache()
            assert result == data

    def test_load_returns_empty_dict_when_file_missing(self, tmp_path):
        """_load_cache returns {} if file does not exist."""
        with patch.object(proxy_mod, "_TOKEN_DIR", tmp_path), patch.object(proxy_mod, "_DEVICE_ID", "no-such-device"):
            result = proxy_mod._load_cache()
            assert result == {}

    def test_load_returns_empty_dict_on_corrupt_json(self, tmp_path):
        """_load_cache gracefully returns {} for malformed JSON."""
        with patch.object(proxy_mod, "_TOKEN_DIR", tmp_path), patch.object(proxy_mod, "_DEVICE_ID", "broken"):
            bad_file = tmp_path / "broken.json"
            bad_file.write_text("{not valid json", encoding="utf-8")
            result = proxy_mod._load_cache()
            assert result == {}

    def test_save_overwrites_existing_file(self, tmp_path):
        """_save_cache replaces previous content."""
        with patch.object(proxy_mod, "_TOKEN_DIR", tmp_path), patch.object(proxy_mod, "_DEVICE_ID", "dev"):
            proxy_mod._save_cache({"refresh_token": "old"})
            proxy_mod._save_cache({"refresh_token": "new"})
            result = proxy_mod._load_cache()
            assert result["refresh_token"] == "new"


# ---------------------------------------------------------------------------
# _mcp_call
# ---------------------------------------------------------------------------


class TestMcpCall:
    def test_json_response_returns_result(self):
        """Plain JSON response: 'result' field is returned."""
        resp = _FakeStreamResponse(
            status_code=200,
            headers={"content-type": "application/json"},
            chunks=[json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}).encode()],
        )
        http = _stream_client(resp)

        with patch.object(proxy_mod, "_SERVER_URL", "https://test.example.com"):
            result = proxy_mod._mcp_call(http, "foo", {"a": 1})

        assert result == {"ok": True}

    def test_sse_response_parses_data_line(self):
        """SSE response: first 'data: {...}' line (that isn't [DONE]) is parsed."""
        resp = _FakeStreamResponse(
            status_code=200,
            headers={"content-type": "text/event-stream"},
            lines=['data: {"jsonrpc":"2.0","id":1,"result":{"x":1}}', "", "data: [DONE]"],
        )
        http = _stream_client(resp)

        with patch.object(proxy_mod, "_SERVER_URL", "https://test.example.com"):
            result = proxy_mod._mcp_call(http, "foo", {})

        assert result == {"x": 1}

    def test_non_200_raises_runtime_error(self):
        resp = _FakeStreamResponse(status_code=500, chunks=[b"boom"])
        http = _stream_client(resp)

        with (
            patch.object(proxy_mod, "_SERVER_URL", "https://test.example.com"),
            pytest.raises(RuntimeError, match="HTTP 500"),
        ):
            proxy_mod._mcp_call(http, "foo", {})

    def test_mcp_error_field_raises_runtime_error(self):
        resp = _FakeStreamResponse(
            status_code=200,
            headers={"content-type": "application/json"},
            chunks=[json.dumps({"jsonrpc": "2.0", "id": 1, "error": {"message": "nope"}}).encode()],
        )
        http = _stream_client(resp)

        with (
            patch.object(proxy_mod, "_SERVER_URL", "https://test.example.com"),
            pytest.raises(RuntimeError, match="MCP error"),
        ):
            proxy_mod._mcp_call(http, "foo", {})

    def test_empty_json_body_raises(self):
        resp = _FakeStreamResponse(status_code=200, headers={"content-type": "application/json"}, chunks=[])
        http = _stream_client(resp)

        with (
            patch.object(proxy_mod, "_SERVER_URL", "https://test.example.com"),
            pytest.raises(RuntimeError, match="vazia"),
        ):
            proxy_mod._mcp_call(http, "foo", {})

    def test_sse_no_data_raises(self):
        resp = _FakeStreamResponse(status_code=200, headers={"content-type": "text/event-stream"}, lines=[])
        http = _stream_client(resp)

        with (
            patch.object(proxy_mod, "_SERVER_URL", "https://test.example.com"),
            pytest.raises(RuntimeError, match="SSE"),
        ):
            proxy_mod._mcp_call(http, "foo", {})

    def test_includes_authorization_and_session_headers(self):
        """access_token and session_id, when provided, populate the request headers."""
        resp = _FakeStreamResponse(
            status_code=200,
            headers={"content-type": "application/json"},
            chunks=[json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}).encode()],
        )
        http = _stream_client(resp)

        with patch.object(proxy_mod, "_SERVER_URL", "https://test.example.com"):
            proxy_mod._mcp_call(http, "foo", {}, access_token="tok-123", session_id="sess-xyz")

        headers = http.stream.call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer tok-123"
        assert headers["mcp-session-id"] == "sess-xyz"

    def test_sse_skips_non_data_and_done_lines_before_match(self):
        """Non-'data:' lines and 'data: [DONE]' are skipped until a real data line is found."""
        resp = _FakeStreamResponse(
            status_code=200,
            headers={"content-type": "text/event-stream"},
            lines=["event: ping", "data: [DONE]", 'data: {"jsonrpc":"2.0","id":1,"result":{"z":9}}'],
        )
        http = _stream_client(resp)

        with patch.object(proxy_mod, "_SERVER_URL", "https://test.example.com"):
            result = proxy_mod._mcp_call(http, "foo", {})

        assert result == {"z": 9}

    def test_sse_exception_during_iteration_before_any_data_raises(self):
        """If the server closes the stream before any usable data line, 'Nenhum dado' is raised."""

        class _RaisingLines:
            def __iter__(self):
                yield "event: ping"
                raise ConnectionError("closed early")

        resp = _FakeStreamResponse(status_code=200, headers={"content-type": "text/event-stream"})
        resp.iter_lines = lambda: _RaisingLines()
        http = _stream_client(resp)

        with (
            patch.object(proxy_mod, "_SERVER_URL", "https://test.example.com"),
            pytest.raises(RuntimeError, match="SSE"),
        ):
            proxy_mod._mcp_call(http, "foo", {})

    def test_json_exception_during_iteration_with_bytes_already_captured(self):
        """If the server closes the connection after sending bytes, the partial body is parsed."""
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"y": 2}}).encode()

        class _RaisingBytes:
            def __iter__(self):
                yield body
                raise ConnectionError("closed early")

        resp = _FakeStreamResponse(status_code=200, headers={"content-type": "application/json"})
        resp.iter_bytes = lambda chunk_size=None: _RaisingBytes()
        http = _stream_client(resp)

        with patch.object(proxy_mod, "_SERVER_URL", "https://test.example.com"):
            result = proxy_mod._mcp_call(http, "foo", {})

        assert result == {"y": 2}


# ---------------------------------------------------------------------------
# _initialize_session
# ---------------------------------------------------------------------------


class TestInitializeSession:
    def test_returns_session_id_from_header(self):
        resp = _FakeStreamResponse(status_code=200, headers={"mcp-session-id": "sess-123"}, chunks=[b""])
        http = _stream_client(resp)

        with patch.object(proxy_mod, "_SERVER_URL", "https://test.example.com"):
            session_id = proxy_mod._initialize_session(http)

        assert session_id == "sess-123"

    def test_missing_session_id_raises(self):
        resp = _FakeStreamResponse(status_code=200, headers={}, chunks=[b""])
        http = _stream_client(resp)

        with (
            patch.object(proxy_mod, "_SERVER_URL", "https://test.example.com"),
            pytest.raises(RuntimeError, match="mcp-session-id"),
        ):
            proxy_mod._initialize_session(http)

    def test_non_200_raises(self):
        resp = _FakeStreamResponse(status_code=401, chunks=[b"unauthorized"])
        http = _stream_client(resp)

        with (
            patch.object(proxy_mod, "_SERVER_URL", "https://test.example.com"),
            pytest.raises(RuntimeError, match="HTTP 401"),
        ):
            proxy_mod._initialize_session(http)

    def test_sends_authorization_header_when_access_token_given(self):
        resp = _FakeStreamResponse(status_code=200, headers={"mcp-session-id": "sess-auth"}, chunks=[b""])
        http = _stream_client(resp)

        with patch.object(proxy_mod, "_SERVER_URL", "https://test.example.com"):
            session_id = proxy_mod._initialize_session(http, access_token="tok-auth")

        assert session_id == "sess-auth"
        headers = http.stream.call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer tok-auth"

    def test_iter_bytes_exception_after_session_id_is_swallowed(self):
        """Server closing the stream right after the header is OK: session_id already captured."""

        def _raising_gen(chunk_size=None):
            if True:
                raise ConnectionError("closed early")
            yield

        resp = _FakeStreamResponse(status_code=200, headers={"mcp-session-id": "sess-close"})
        resp.iter_bytes = _raising_gen
        http = _stream_client(resp)

        with patch.object(proxy_mod, "_SERVER_URL", "https://test.example.com"):
            session_id = proxy_mod._initialize_session(http)

        assert session_id == "sess-close"


# ---------------------------------------------------------------------------
# _activate
# ---------------------------------------------------------------------------


class TestActivate:
    def test_happy_path_writes_refresh_token_and_returns_it(self, tmp_path):
        """_activate calls MCP tool ativar_dispositivo, saves refresh_token, returns it."""
        http = MagicMock()

        with (
            patch.object(proxy_mod, "_TOKEN_DIR", tmp_path),
            patch.object(proxy_mod, "_DEVICE_ID", "dev1"),
            patch.object(proxy_mod, "_CLIENT_CODE", "RCODE-test"),
            patch.object(
                proxy_mod,
                "_mcp_call",
                return_value=_tool_result(refresh_token="rt-xxx", device_id="dev1", client_id="bruno"),
            ) as mock_call,
        ):
            result = proxy_mod._activate(http, "sess-1")

        assert result == "rt-xxx"
        mock_call.assert_called_once()
        assert mock_call.call_args[0][1] == "ativar_dispositivo"
        assert mock_call.call_args[0][2] == {"client_code": "RCODE-test", "device_name": "dev1"}

        with patch.object(proxy_mod, "_TOKEN_DIR", tmp_path), patch.object(proxy_mod, "_DEVICE_ID", "dev1"):
            cache = proxy_mod._load_cache()
        assert cache["refresh_token"] == "rt-xxx"
        assert cache["client_id"] == "bruno"

    def test_mcp_call_failure_calls_sys_exit(self, tmp_path):
        """_activate calls sys.exit when the MCP call itself raises."""
        http = MagicMock()

        with (
            patch.object(proxy_mod, "_TOKEN_DIR", tmp_path),
            patch.object(proxy_mod, "_DEVICE_ID", "dev2"),
            patch.object(proxy_mod, "_CLIENT_CODE", "RCODE-test"),
            patch.object(proxy_mod, "_mcp_call", side_effect=RuntimeError("HTTP 403: Forbidden")),
        ):
            with pytest.raises(SystemExit):
                proxy_mod._activate(http, "sess-2")

    def test_missing_client_code_calls_sys_exit(self, tmp_path):
        """_activate calls sys.exit when _CLIENT_CODE is empty, without calling the server."""
        http = MagicMock()

        with (
            patch.object(proxy_mod, "_TOKEN_DIR", tmp_path),
            patch.object(proxy_mod, "_DEVICE_ID", "dev3"),
            patch.object(proxy_mod, "_CLIENT_CODE", ""),
            patch.object(proxy_mod, "_mcp_call") as mock_call,
        ):
            with pytest.raises(SystemExit):
                proxy_mod._activate(http, "sess-3")

        mock_call.assert_not_called()

    def test_status_error_calls_sys_exit(self, tmp_path):
        """_activate calls sys.exit when the tool returns status != 'ok'."""
        http = MagicMock()

        with (
            patch.object(proxy_mod, "_TOKEN_DIR", tmp_path),
            patch.object(proxy_mod, "_DEVICE_ID", "dev4"),
            patch.object(proxy_mod, "_CLIENT_CODE", "RCODE-test"),
            patch.object(
                proxy_mod,
                "_mcp_call",
                return_value=_tool_result(status="error", message="Código inválido"),
            ),
        ):
            with pytest.raises(SystemExit):
                proxy_mod._activate(http, "sess-4")

    def test_empty_content_calls_sys_exit(self, tmp_path):
        """_activate calls sys.exit when ativar_dispositivo returns no content."""
        http = MagicMock()

        with (
            patch.object(proxy_mod, "_TOKEN_DIR", tmp_path),
            patch.object(proxy_mod, "_DEVICE_ID", "dev5"),
            patch.object(proxy_mod, "_CLIENT_CODE", "RCODE-test"),
            patch.object(proxy_mod, "_mcp_call", return_value={"content": []}),
        ):
            with pytest.raises(SystemExit):
                proxy_mod._activate(http, "sess-5")


# ---------------------------------------------------------------------------
# _get_access_token
# ---------------------------------------------------------------------------


class TestGetAccessToken:
    def test_uses_cached_refresh_token_on_success(self, tmp_path):
        """Happy path: cached refresh_token → renovar_token MCP tool → access_token."""
        http = MagicMock()

        with (
            patch.object(proxy_mod, "_TOKEN_DIR", tmp_path),
            patch.object(proxy_mod, "_DEVICE_ID", "devA"),
            patch.object(
                proxy_mod,
                "_mcp_call",
                return_value=_tool_result(access_token="at-abc", expires_in=3600),
            ) as mock_call,
        ):
            proxy_mod._save_cache({"refresh_token": "rt-cached"})

            before = time.time()
            token, expire_at = proxy_mod._get_access_token(http, "sess-a")
            after = time.time()

        assert token == "at-abc"
        assert before + 3600 <= expire_at <= after + 3600
        mock_call.assert_called_once()
        assert mock_call.call_args[0][1] == "renovar_token"
        assert mock_call.call_args[0][2] == {"refresh_token": "rt-cached"}

    def test_defaults_expires_in_to_28800_when_absent(self, tmp_path):
        """expires_in defaults to 28800 (8 h) when the server omits it."""
        http = MagicMock()

        with (
            patch.object(proxy_mod, "_TOKEN_DIR", tmp_path),
            patch.object(proxy_mod, "_DEVICE_ID", "devB"),
            patch.object(proxy_mod, "_mcp_call", return_value=_tool_result(access_token="at-def")),
        ):
            proxy_mod._save_cache({"refresh_token": "rt-cached"})
            before = time.time()
            _, expire_at = proxy_mod._get_access_token(http, "sess-b")
            after = time.time()

        assert before + 28800 <= expire_at <= after + 28800

    def test_falls_back_to_activate_on_renewal_failure(self, tmp_path):
        """Renewal failure with a cached refresh_token triggers _activate then retries renewal."""
        http = MagicMock()
        renovar_calls = {"n": 0}

        def fake_mcp_call(http_client, tool_name, args, access_token=None, session_id=""):
            if tool_name == "renovar_token":
                renovar_calls["n"] += 1
                if renovar_calls["n"] == 1:
                    raise RuntimeError("refresh token expirado")
                return _tool_result(access_token="at-new", expires_in=100)
            if tool_name == "ativar_dispositivo":
                return _tool_result(refresh_token="rt-new", device_id="devC", client_id="bruno")
            raise AssertionError(f"unexpected tool: {tool_name}")

        with (
            patch.object(proxy_mod, "_TOKEN_DIR", tmp_path),
            patch.object(proxy_mod, "_DEVICE_ID", "devC"),
            patch.object(proxy_mod, "_CLIENT_CODE", "RCODE-test"),
            patch.object(proxy_mod, "_mcp_call", side_effect=fake_mcp_call),
        ):
            proxy_mod._save_cache({"refresh_token": "rt-old"})
            token, _ = proxy_mod._get_access_token(http, "sess-c")

        assert token == "at-new"
        assert renovar_calls["n"] == 2

    def test_no_cache_calls_activate_directly(self, tmp_path):
        """No cached refresh token → goes straight to _activate, then renews once."""
        http = MagicMock()

        def fake_mcp_call(http_client, tool_name, args, access_token=None, session_id=""):
            if tool_name == "ativar_dispositivo":
                return _tool_result(refresh_token="rt-fresh", device_id="devD", client_id="bruno")
            if tool_name == "renovar_token":
                return _tool_result(access_token="at-fresh", expires_in=50)
            raise AssertionError(f"unexpected tool: {tool_name}")

        with (
            patch.object(proxy_mod, "_TOKEN_DIR", tmp_path),
            patch.object(proxy_mod, "_DEVICE_ID", "devD"),
            patch.object(proxy_mod, "_CLIENT_CODE", "RCODE-new"),
            patch.object(proxy_mod, "_mcp_call", side_effect=fake_mcp_call),
        ):
            token, _ = proxy_mod._get_access_token(http, "sess-d")

        assert token == "at-fresh"

    def test_empty_content_on_cached_renewal_falls_back_to_activate(self, tmp_path):
        """Cached refresh_token renewal with empty content is treated as a failure → re-activates."""
        http = MagicMock()

        def fake_mcp_call(http_client, tool_name, args, access_token=None, session_id=""):
            if tool_name == "renovar_token" and args.get("refresh_token") == "rt-old":
                return {"content": []}
            if tool_name == "ativar_dispositivo":
                return _tool_result(refresh_token="rt-new", device_id="devF", client_id="bruno")
            if tool_name == "renovar_token" and args.get("refresh_token") == "rt-new":
                return _tool_result(access_token="at-new2", expires_in=100)
            raise AssertionError(f"unexpected call: {tool_name} {args}")

        with (
            patch.object(proxy_mod, "_TOKEN_DIR", tmp_path),
            patch.object(proxy_mod, "_DEVICE_ID", "devF"),
            patch.object(proxy_mod, "_CLIENT_CODE", "RCODE-test"),
            patch.object(proxy_mod, "_mcp_call", side_effect=fake_mcp_call),
        ):
            proxy_mod._save_cache({"refresh_token": "rt-old"})
            token, _ = proxy_mod._get_access_token(http, "sess-f")

        assert token == "at-new2"

    def test_status_error_on_cached_renewal_falls_back_to_activate(self, tmp_path):
        """Cached refresh_token renewal returning status='error' triggers re-activation."""
        http = MagicMock()

        def fake_mcp_call(http_client, tool_name, args, access_token=None, session_id=""):
            if tool_name == "renovar_token" and args.get("refresh_token") == "rt-old":
                return _tool_result(status="error", message="expirado")
            if tool_name == "ativar_dispositivo":
                return _tool_result(refresh_token="rt-new", device_id="devG", client_id="bruno")
            if tool_name == "renovar_token" and args.get("refresh_token") == "rt-new":
                return _tool_result(access_token="at-new3", expires_in=100)
            raise AssertionError(f"unexpected call: {tool_name} {args}")

        with (
            patch.object(proxy_mod, "_TOKEN_DIR", tmp_path),
            patch.object(proxy_mod, "_DEVICE_ID", "devG"),
            patch.object(proxy_mod, "_CLIENT_CODE", "RCODE-test"),
            patch.object(proxy_mod, "_mcp_call", side_effect=fake_mcp_call),
        ):
            proxy_mod._save_cache({"refresh_token": "rt-old"})
            token, _ = proxy_mod._get_access_token(http, "sess-g")

        assert token == "at-new3"

    def test_post_activate_empty_content_calls_sys_exit(self, tmp_path):
        """If the post-activation renewal returns empty content, sys.exit is called."""
        http = MagicMock()

        def fake_mcp_call(http_client, tool_name, args, access_token=None, session_id=""):
            if tool_name == "ativar_dispositivo":
                return _tool_result(refresh_token="rt-h", device_id="devH", client_id="bruno")
            if tool_name == "renovar_token":
                return {"content": []}
            raise AssertionError(f"unexpected tool: {tool_name}")

        with (
            patch.object(proxy_mod, "_TOKEN_DIR", tmp_path),
            patch.object(proxy_mod, "_DEVICE_ID", "devH"),
            patch.object(proxy_mod, "_CLIENT_CODE", "RCODE-h"),
            patch.object(proxy_mod, "_mcp_call", side_effect=fake_mcp_call),
        ):
            with pytest.raises(SystemExit):
                proxy_mod._get_access_token(http, "sess-h")

    def test_post_activate_renewal_error_calls_sys_exit(self, tmp_path):
        """If renewal after a fresh activation also fails, sys.exit is called."""
        http = MagicMock()

        def fake_mcp_call(http_client, tool_name, args, access_token=None, session_id=""):
            if tool_name == "ativar_dispositivo":
                return _tool_result(refresh_token="rt-x", device_id="devE", client_id="bruno")
            if tool_name == "renovar_token":
                return _tool_result(status="error", message="servidor indisponível")
            raise AssertionError(f"unexpected tool: {tool_name}")

        with (
            patch.object(proxy_mod, "_TOKEN_DIR", tmp_path),
            patch.object(proxy_mod, "_DEVICE_ID", "devE"),
            patch.object(proxy_mod, "_CLIENT_CODE", "RCODE-x"),
            patch.object(proxy_mod, "_mcp_call", side_effect=fake_mcp_call),
        ):
            with pytest.raises(SystemExit):
                proxy_mod._get_access_token(http, "sess-e")


# ---------------------------------------------------------------------------
# _refresh_loop
# ---------------------------------------------------------------------------


class TestRefreshLoop:
    def test_updates_state_after_one_iteration(self, tmp_path):
        """_refresh_loop updates state.access_token and state.expire_at after one cycle."""
        state = proxy_mod._State(access_token="old-token", expire_at=time.time() + 1)

        new_expire = time.time() + 7200
        http = MagicMock()

        iteration_count = {"n": 0}
        sleep_barrier = threading.Event()

        def mock_get_access_token(http_client, session_id):
            iteration_count["n"] += 1
            return "new-token", new_expire

        original_sleep = time.sleep

        def mock_sleep(duration):
            if iteration_count["n"] >= 1:
                # After the first token update, stop the loop by raising
                sleep_barrier.set()
                raise StopIteration("done")
            original_sleep(0)  # yield

        with (
            patch.object(proxy_mod, "_get_access_token", side_effect=mock_get_access_token),
            patch.object(proxy_mod.time, "sleep", side_effect=mock_sleep),
        ):
            try:
                proxy_mod._refresh_loop(state, http)
            except StopIteration:
                pass

        assert state.access_token == "new-token"
        assert state.expire_at == new_expire

    def test_logs_failure_on_exception(self, tmp_path, capsys):
        """_refresh_loop logs error when _get_access_token raises."""
        state = proxy_mod._State(access_token="tok", expire_at=time.time() + 1)

        call_count = {"n": 0}

        def mock_get_access_token(http_client, session_id):
            raise RuntimeError("network error")

        def mock_sleep(duration):
            call_count["n"] += 1
            if call_count["n"] >= 2:
                raise StopIteration("done")

        http = MagicMock()

        with (
            patch.object(proxy_mod, "_get_access_token", side_effect=mock_get_access_token),
            patch.object(proxy_mod.time, "sleep", side_effect=mock_sleep),
        ):
            try:
                proxy_mod._refresh_loop(state, http)
            except StopIteration:
                pass

        captured = capsys.readouterr()
        assert "Falha na renovação automática" in captured.err or "network error" in captured.err


# ---------------------------------------------------------------------------
# _write_error
# ---------------------------------------------------------------------------


class TestWriteError:
    def test_writes_jsonrpc_error_structure(self, capsys):
        """_write_error emits well-formed JSON-RPC 2.0 error to stdout."""
        msg = {"id": 42, "method": "tools/call"}
        proxy_mod._write_error(msg, "Something went wrong")
        out = capsys.readouterr().out
        data = json.loads(out.strip())
        assert data["jsonrpc"] == "2.0"
        assert data["id"] == 42
        assert data["error"]["code"] == -32000
        assert "Something went wrong" in data["error"]["message"]

    def test_no_response_for_notification_without_id(self, capsys):
        """JSON-RPC notifications (sem 'id') não recebem resposta — ecoar id:null
        é inválido pelo protocolo e alguns clientes (Claude Desktop) rejeitam a
        mensagem inteira por causa disso."""
        proxy_mod._write_error({"method": "notifications/cancelled"}, "boom")
        out = capsys.readouterr().out
        assert out == ""

    def test_no_response_for_completely_empty_msg(self, capsys):
        proxy_mod._write_error({}, "boom")
        out = capsys.readouterr().out
        assert out == ""

    def test_output_ends_with_newline(self, capsys):
        """_write_error output is terminated with newline."""
        proxy_mod._write_error({"id": 1}, "err")
        out = capsys.readouterr().out
        assert out.endswith("\n")


# ---------------------------------------------------------------------------
# _bridge (async)
# ---------------------------------------------------------------------------


class TestBridge:
    """Async tests for the _bridge coroutine."""

    @pytest.mark.asyncio
    async def test_json_response_written_to_stdout(self, tmp_path, capsys):
        """Normal JSON response from server is forwarded to stdout."""
        state = proxy_mod._State(access_token="token-xyz", expire_at=time.time() + 3600)
        http = MagicMock()

        server_resp = _make_response(200, {"result": "ok"}, headers={"content-type": "application/json"})
        http.post.return_value = server_resp

        lines_iter = iter(['{"id":1,"method":"ping"}\n', ""])  # EOF on second read

        loop = asyncio.get_event_loop()
        original_run_in_executor = loop.run_in_executor

        async def patched_run_in_executor(executor, func, *args):
            return next(lines_iter)

        with patch.object(proxy_mod, "_SERVER_URL", "https://test.example.com"):
            loop.run_in_executor = patched_run_in_executor
            try:
                await proxy_mod._bridge(state, http)
            finally:
                loop.run_in_executor = original_run_in_executor

        captured = capsys.readouterr()
        data = json.loads(captured.out.strip())
        assert data["result"] == "ok"

    @pytest.mark.asyncio
    async def test_bearer_header_sent(self, tmp_path, capsys):
        """HTTP POST includes Authorization: Bearer header."""
        state = proxy_mod._State(access_token="bearer-tok", expire_at=time.time() + 3600)
        http = MagicMock()

        server_resp = _make_response(200, {"result": "done"}, headers={"content-type": "application/json"})
        http.post.return_value = server_resp

        lines_iter = iter(['{"id":2,"method":"list"}\n', ""])

        loop = asyncio.get_event_loop()
        original_run_in_executor = loop.run_in_executor

        async def patched_run_in_executor(executor, func, *args):
            return next(lines_iter)

        with patch.object(proxy_mod, "_SERVER_URL", "https://test.example.com"):
            loop.run_in_executor = patched_run_in_executor
            try:
                await proxy_mod._bridge(state, http)
            finally:
                loop.run_in_executor = original_run_in_executor

        # headers may be positional or keyword
        all_kwargs = http.post.call_args.kwargs
        assert "Authorization" in all_kwargs.get("headers", {})
        assert all_kwargs["headers"]["Authorization"] == "Bearer bearer-tok"

    @pytest.mark.asyncio
    async def test_sse_lines_emitted(self, tmp_path, capsys):
        """SSE text/event-stream data: lines are forwarded one per line."""
        state = proxy_mod._State(access_token="tok", expire_at=time.time() + 3600)
        http = MagicMock()

        sse_body = 'data: {"event":"a"}\n: comment-line-not-data\ndata: {"event":"b"}\ndata: [DONE]\n'
        server_resp = _make_response(200, "", headers={"content-type": "text/event-stream"})
        server_resp.text = sse_body
        server_resp.json.side_effect = Exception("not json")
        http.post.return_value = server_resp

        lines_iter = iter(['{"id":3,"method":"stream"}\n', ""])

        loop = asyncio.get_event_loop()
        original_run_in_executor = loop.run_in_executor

        async def patched_run_in_executor(executor, func, *args):
            return next(lines_iter)

        with patch.object(proxy_mod, "_SERVER_URL", "https://test.example.com"):
            loop.run_in_executor = patched_run_in_executor
            try:
                await proxy_mod._bridge(state, http)
            finally:
                loop.run_in_executor = original_run_in_executor

        out_lines = [ln for ln in capsys.readouterr().out.strip().splitlines() if ln]
        assert len(out_lines) == 2  # [DONE] is skipped
        assert json.loads(out_lines[0])["event"] == "a"
        assert json.loads(out_lines[1])["event"] == "b"

    @pytest.mark.asyncio
    async def test_401_triggers_retry_with_fresh_token(self, tmp_path, capsys):
        """401 response triggers one retry with a freshly-obtained token."""
        state = proxy_mod._State(access_token="expired-tok", expire_at=time.time() + 3600)
        http = MagicMock()

        resp_401 = _make_response(401, "Unauthorized")
        resp_ok = _make_response(200, {"result": "retried"}, headers={"content-type": "application/json"})
        http.post.side_effect = [resp_401, resp_ok]

        lines_iter = iter(['{"id":4,"method":"ping"}\n', ""])

        loop = asyncio.get_event_loop()
        original_run_in_executor = loop.run_in_executor

        async def patched_run_in_executor(executor, func, *args):
            return next(lines_iter)

        with (
            patch.object(proxy_mod, "_SERVER_URL", "https://test.example.com"),
            patch.object(proxy_mod, "_get_access_token", return_value=("fresh-tok", time.time() + 7200)),
        ):
            loop.run_in_executor = patched_run_in_executor
            try:
                await proxy_mod._bridge(state, http)
            finally:
                loop.run_in_executor = original_run_in_executor

        assert http.post.call_count == 2
        # Second call uses fresh token
        second_call_headers = http.post.call_args_list[1].kwargs["headers"]
        assert second_call_headers["Authorization"] == "Bearer fresh-tok"
        # state updated
        assert state.access_token == "fresh-tok"

    @pytest.mark.asyncio
    async def test_non_200_emits_json_rpc_error(self, tmp_path, capsys):
        """Non-200 (not 401) response emits a JSON-RPC error to stdout."""
        state = proxy_mod._State(access_token="tok", expire_at=time.time() + 3600)
        http = MagicMock()

        http.post.return_value = _make_response(503, "Service Unavailable")

        lines_iter = iter(['{"id":5,"method":"tools/call"}\n', ""])

        loop = asyncio.get_event_loop()
        original_run_in_executor = loop.run_in_executor

        async def patched_run_in_executor(executor, func, *args):
            return next(lines_iter)

        with patch.object(proxy_mod, "_SERVER_URL", "https://test.example.com"):
            loop.run_in_executor = patched_run_in_executor
            try:
                await proxy_mod._bridge(state, http)
            finally:
                loop.run_in_executor = original_run_in_executor

        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["jsonrpc"] == "2.0"
        assert data["id"] == 5
        assert data["error"]["code"] == -32000
        assert "503" in data["error"]["message"]

    @pytest.mark.asyncio
    async def test_malformed_json_silently_skipped(self, tmp_path, capsys):
        """Malformed JSON lines are silently skipped (no output, no exception)."""
        state = proxy_mod._State(access_token="tok", expire_at=time.time() + 3600)
        http = MagicMock()

        lines_iter = iter(["not-json-at-all\n", ""])

        loop = asyncio.get_event_loop()
        original_run_in_executor = loop.run_in_executor

        async def patched_run_in_executor(executor, func, *args):
            return next(lines_iter)

        with patch.object(proxy_mod, "_SERVER_URL", "https://test.example.com"):
            loop.run_in_executor = patched_run_in_executor
            try:
                await proxy_mod._bridge(state, http)
            finally:
                loop.run_in_executor = original_run_in_executor

        out = capsys.readouterr().out
        assert out == ""
        http.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_lines_skipped(self, tmp_path, capsys):
        """Empty lines are skipped without calling http.post."""
        state = proxy_mod._State(access_token="tok", expire_at=time.time() + 3600)
        http = MagicMock()

        lines_iter = iter(["   \n", "\n", ""])

        loop = asyncio.get_event_loop()
        original_run_in_executor = loop.run_in_executor

        async def patched_run_in_executor(executor, func, *args):
            return next(lines_iter)

        with patch.object(proxy_mod, "_SERVER_URL", "https://test.example.com"):
            loop.run_in_executor = patched_run_in_executor
            try:
                await proxy_mod._bridge(state, http)
            finally:
                loop.run_in_executor = original_run_in_executor

        http.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_exception_during_post_emits_error(self, tmp_path, capsys):
        """Network exception during POST results in JSON-RPC error output."""
        state = proxy_mod._State(access_token="tok", expire_at=time.time() + 3600)
        http = MagicMock()
        http.post.side_effect = ConnectionError("connection refused")

        lines_iter = iter(['{"id":6,"method":"test"}\n', ""])

        loop = asyncio.get_event_loop()
        original_run_in_executor = loop.run_in_executor

        async def patched_run_in_executor(executor, func, *args):
            return next(lines_iter)

        with patch.object(proxy_mod, "_SERVER_URL", "https://test.example.com"):
            loop.run_in_executor = patched_run_in_executor
            try:
                await proxy_mod._bridge(state, http)
            finally:
                loop.run_in_executor = original_run_in_executor

        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["jsonrpc"] == "2.0"
        assert data["id"] == 6
        assert "connection refused" in data["error"]["message"]


# ---------------------------------------------------------------------------
# _State
# ---------------------------------------------------------------------------


class TestState:
    def test_initial_values(self):
        """_State stores access_token and expire_at correctly."""
        t = time.time() + 100
        s = proxy_mod._State("my-token", t)
        assert s.access_token == "my-token"
        assert s.expire_at == t

    def test_has_lock(self):
        """_State exposes a threading.Lock."""
        s = proxy_mod._State("tok", 0.0)
        assert isinstance(s.lock, type(threading.Lock()))


# ---------------------------------------------------------------------------
# _log / _die
# ---------------------------------------------------------------------------


class TestMain:
    def test_missing_httpx_calls_sys_exit(self):
        """main() calls _die when httpx cannot be imported."""
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "httpx":
                raise ImportError("no httpx")
            return real_import(name, *args, **kwargs)

        with (
            patch.object(builtins, "__import__", side_effect=fake_import),
            pytest.raises(SystemExit),
        ):
            proxy_mod.main()

    def test_happy_path_runs_bridge(self, tmp_path):
        """main() wires init/token/thread/bridge together end-to-end (all mocked)."""
        fake_httpx_client_instance = MagicMock()
        fake_httpx_client_instance.__enter__.return_value = fake_httpx_client_instance
        fake_httpx_client_instance.__exit__.return_value = False
        fake_httpx_module = MagicMock()
        fake_httpx_module.Client.return_value = fake_httpx_client_instance

        started_threads = []

        class _FakeThread:
            def __init__(self, target=None, args=(), daemon=None):
                self.target = target
                self.args = args
                self.daemon = daemon

            def start(self):
                started_threads.append(self)

        with (
            patch.dict("sys.modules", {"httpx": fake_httpx_module}),
            patch.object(proxy_mod, "_initialize_session", return_value="sess-main") as mock_init,
            patch.object(proxy_mod, "_get_access_token", return_value=("tok-main", time.time() + 3600)) as mock_gat,
            patch.object(proxy_mod.threading, "Thread", _FakeThread),
            patch.object(proxy_mod.asyncio, "run") as mock_run,
        ):
            proxy_mod.main()

        mock_init.assert_called_once_with(fake_httpx_client_instance)
        mock_gat.assert_called_once_with(fake_httpx_client_instance, "sess-main")
        assert len(started_threads) == 1
        assert started_threads[0].daemon is True
        mock_run.assert_called_once()
        # asyncio.run is mocked, so the real `_bridge(...)` coroutine it received
        # is never awaited — close it explicitly to avoid a RuntimeWarning leaking
        # into whichever test happens to run when it's garbage-collected.
        mock_run.call_args.args[0].close()


class TestLogDie:
    def test_log_writes_to_stderr(self, capsys):
        proxy_mod._log("hello world")
        err = capsys.readouterr().err
        assert "hello world" in err
        assert "[concilium-mcp-proxy]" in err

    def test_die_exits_with_1(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            proxy_mod._die("fatal error")
        assert exc_info.value.code == 1
        err = capsys.readouterr().err
        assert "fatal error" in err
