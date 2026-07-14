"""Tests for concilium.presentation.mcp.audit — ADR-118 MCP tool invocation auditing.

No prior test file existed for this module; it covers:
  - patch_fastmcp_server_with_audit: happy path, tools without .fn skipped,
    and the best-effort except-Exception-pass guard.
  - _with_audit: success and failure paths, and the best-effort _record()
    failure guard.
  - _record: success path and the best-effort except-Exception-pass guard.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from concilium.presentation.mcp.audit import _record, _with_audit, patch_fastmcp_server_with_audit


class TestPatchFastmcpServerWithAudit:
    def test_wraps_tools_with_fn(self):
        def original_fn(x: int) -> int:
            return x * 2

        original_fn.__name__ = "original_fn"
        tool = SimpleNamespace(fn=original_fn)
        server = SimpleNamespace(_tool_manager=SimpleNamespace(_tools={"t1": tool}))

        patch_fastmcp_server_with_audit(server)

        # tool.fn was replaced by the audit wrapper
        assert tool.fn is not original_fn
        with patch("concilium.presentation.mcp.audit._record"):
            assert tool.fn(5) == 10

    def test_tool_without_fn_is_skipped(self):
        """Line 34: hasattr(tool, 'fn') False → tool left untouched."""
        tool_no_fn = SimpleNamespace()
        server = SimpleNamespace(_tool_manager=SimpleNamespace(_tools={"t1": tool_no_fn}))

        # Should not raise, and tool_no_fn stays without a .fn attribute
        patch_fastmcp_server_with_audit(server)
        assert not hasattr(tool_no_fn, "fn")

    def test_tool_fn_not_callable_is_skipped(self):
        """Line 34: hasattr True but callable(tool.fn) False → skip."""
        tool = SimpleNamespace(fn="not-callable")
        server = SimpleNamespace(_tool_manager=SimpleNamespace(_tools={"t1": tool}))

        patch_fastmcp_server_with_audit(server)
        assert tool.fn == "not-callable"

    def test_missing_tool_manager_is_silently_ignored(self):
        """Lines 36-37: AttributeError from server._tool_manager → pass."""
        server = SimpleNamespace()  # no _tool_manager at all

        # Should not raise
        patch_fastmcp_server_with_audit(server)


class TestWithAudit:
    def test_success_records_invocation(self):
        def fn(a: int, b: int = 2) -> int:
            return a + b

        fn.__name__ = "fn"
        wrapped = _with_audit(fn)

        with patch("concilium.presentation.mcp.audit._record") as mock_record:
            result = wrapped(1, b=3)

        assert result == 4
        assert mock_record.call_count == 1
        _, kwargs = mock_record.call_args
        assert kwargs["status"] == "success"
        assert kwargs["error_type"] is None
        assert kwargs["input_keys"] == ["b"]

    def test_exception_is_recorded_and_reraised(self):
        def fn() -> None:
            raise ValueError("boom")

        fn.__name__ = "fn"
        wrapped = _with_audit(fn)

        with patch("concilium.presentation.mcp.audit._record") as mock_record:
            with pytest.raises(ValueError, match="boom"):
                wrapped()

        _, kwargs = mock_record.call_args
        assert kwargs["status"] == "failed"
        assert kwargs["error_type"] == "ValueError"

    def test_record_failure_is_swallowed(self):
        """Lines 79-80: _record() raising internally must not propagate."""

        def fn() -> str:
            return "ok"

        fn.__name__ = "fn"
        wrapped = _with_audit(fn)

        with patch("concilium.presentation.mcp.audit._record", side_effect=RuntimeError("db down")):
            result = wrapped()

        assert result == "ok"

    def test_captures_device_id_and_mcp_session_id(self):
        """ADR-138: wrapper captura device_id/mcp_session_id do contexto atual e
        repassa para _record, junto de user_id/tenant_id."""

        def fn() -> str:
            return "ok"

        fn.__name__ = "fn"
        wrapped = _with_audit(fn)

        with (
            patch("concilium.presentation.mcp.audit._record") as mock_record,
            patch(
                "concilium.infrastructure.auth.permission_guard.get_current_device_id",
                return_value="falcon-falcon",
            ),
            patch(
                "concilium.infrastructure.auth.permission_guard.get_current_mcp_session_id",
                return_value="sess-abc123",
            ),
        ):
            wrapped()

        _, kwargs = mock_record.call_args
        assert kwargs["device_id"] == "falcon-falcon"
        assert kwargs["mcp_session_id"] == "sess-abc123"

    def test_device_id_and_mcp_session_id_default_to_none(self):
        """Fora de request MCP (ex.: chamada direta em teste), ambos são None."""

        def fn() -> str:
            return "ok"

        fn.__name__ = "fn"
        wrapped = _with_audit(fn)

        with patch("concilium.presentation.mcp.audit._record") as mock_record:
            wrapped()

        _, kwargs = mock_record.call_args
        assert kwargs["device_id"] is None
        assert kwargs["mcp_session_id"] is None


class TestRecord:
    def test_record_success_appends_to_repository(self):
        mock_repo = MagicMock()
        with patch(
            "concilium.application.tool_invocations.repository.get_tool_invocation_repository",
            return_value=mock_repo,
        ):
            _record(
                invocation_id="ti-1",
                tool_name="tool_a",
                input_keys=["x"],
                user_id="u1",
                tenant_id="t1",
                status="success",
                started_at="2026-01-01T00:00:00+00:00",
                finished_at="2026-01-01T00:00:01+00:00",
                error_type=None,
                device_id="falcon-falcon",
                mcp_session_id="sess-abc123",
            )
        mock_repo.append.assert_called_once()
        inv = mock_repo.append.call_args[0][0]
        assert inv.device_id == "falcon-falcon"
        assert inv.mcp_session_id == "sess-abc123"

    def test_record_swallows_repository_errors(self):
        """Lines 114-115: any exception while persisting is swallowed."""
        with patch(
            "concilium.application.tool_invocations.repository.get_tool_invocation_repository",
            side_effect=RuntimeError("repo unavailable"),
        ):
            # Should not raise
            _record(
                invocation_id="ti-2",
                tool_name="tool_b",
                input_keys=[],
                user_id=None,
                tenant_id=None,
                status="failed",
                started_at="2026-01-01T00:00:00+00:00",
                finished_at="2026-01-01T00:00:01+00:00",
                error_type="ValueError",
                device_id=None,
                mcp_session_id=None,
            )
