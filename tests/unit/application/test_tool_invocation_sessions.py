"""Testes de sumarização de sessões MCP por dispositivo (ADR-138).

Uma "sessão" é derivada do audit log (ToolInvocation) agrupado por
mcp_session_id — não é um registro persistido à parte.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from concilium.application.tool_invocations.models import ToolInvocation
from concilium.application.tool_invocations.sessions import sessions_for_device, summarize_sessions


def _inv(
    id: str,
    mcp_session_id: str | None,
    started_at: str,
    finished_at: str,
    device_id: str | None = "falcon-falcon",
    user_id: str | None = "bruno",
    tenant_id: str | None = "mendeslobo",
) -> ToolInvocation:
    return ToolInvocation(
        id=id,
        tool_name="ping",
        input_keys=[],
        user_id=user_id,
        tenant_id=tenant_id,
        status="success",
        started_at=started_at,
        finished_at=finished_at,
        device_id=device_id,
        mcp_session_id=mcp_session_id,
    )


class TestSummarizeSessions:
    def test_empty_list_returns_empty(self):
        assert summarize_sessions([]) == []

    def test_single_call_produces_single_session(self):
        inv = _inv("i1", "sess-1", "2026-07-14T10:00:00+00:00", "2026-07-14T10:00:01+00:00")
        result = summarize_sessions([inv])

        assert len(result) == 1
        s = result[0]
        assert s.session_id == "sess-1"
        assert s.device_id == "falcon-falcon"
        assert s.user_id == "bruno"
        assert s.tenant_id == "mendeslobo"
        assert s.started_at == "2026-07-14T10:00:00+00:00"
        assert s.last_activity_at == "2026-07-14T10:00:01+00:00"
        assert s.call_count == 1

    def test_multiple_calls_in_same_session_aggregate(self):
        invs = [
            _inv("i1", "sess-1", "2026-07-14T10:00:00+00:00", "2026-07-14T10:00:01+00:00"),
            _inv("i2", "sess-1", "2026-07-14T10:05:00+00:00", "2026-07-14T10:05:02+00:00"),
            _inv("i3", "sess-1", "2026-07-14T10:02:00+00:00", "2026-07-14T10:02:01+00:00"),
        ]
        result = summarize_sessions(invs)

        assert len(result) == 1
        s = result[0]
        assert s.call_count == 3
        assert s.started_at == "2026-07-14T10:00:00+00:00"  # earliest started_at
        assert s.last_activity_at == "2026-07-14T10:05:02+00:00"  # latest finished_at

    def test_multiple_sessions_sorted_by_last_activity_desc(self):
        invs = [
            _inv("i1", "sess-old", "2026-07-14T08:00:00+00:00", "2026-07-14T08:00:01+00:00"),
            _inv("i2", "sess-new", "2026-07-14T10:00:00+00:00", "2026-07-14T10:00:01+00:00"),
        ]
        result = summarize_sessions(invs)

        assert [s.session_id for s in result] == ["sess-new", "sess-old"]

    def test_invocations_without_mcp_session_id_are_ignored(self):
        invs = [
            _inv("i1", None, "2026-07-14T10:00:00+00:00", "2026-07-14T10:00:01+00:00"),
            _inv("i2", "sess-1", "2026-07-14T10:05:00+00:00", "2026-07-14T10:05:01+00:00"),
        ]
        result = summarize_sessions(invs)

        assert len(result) == 1
        assert result[0].session_id == "sess-1"

    def test_all_invocations_without_session_id_returns_empty(self):
        invs = [_inv("i1", None, "2026-07-14T10:00:00+00:00", "2026-07-14T10:00:01+00:00")]
        assert summarize_sessions(invs) == []

    def test_distinct_devices_produce_distinct_sessions(self):
        invs = [
            _inv("i1", "sess-1", "2026-07-14T10:00:00+00:00", "2026-07-14T10:00:01+00:00", device_id="device-a"),
            _inv("i2", "sess-2", "2026-07-14T10:00:00+00:00", "2026-07-14T10:00:01+00:00", device_id="device-b"),
        ]
        result = summarize_sessions(invs)

        by_id = {s.session_id: s for s in result}
        assert by_id["sess-1"].device_id == "device-a"
        assert by_id["sess-2"].device_id == "device-b"


class TestSessionsForDevice:
    def test_delegates_to_repository_list_by_device(self):
        mock_repo = MagicMock()
        mock_repo.list_by_device.return_value = [
            _inv("i1", "sess-1", "2026-07-14T10:00:00+00:00", "2026-07-14T10:00:01+00:00"),
        ]
        with patch(
            "concilium.application.tool_invocations.repository.get_tool_invocation_repository",
            return_value=mock_repo,
        ):
            result = sessions_for_device("falcon-falcon", limit=50)

        mock_repo.list_by_device.assert_called_once_with("falcon-falcon", limit=50)
        assert len(result) == 1
        assert result[0].session_id == "sess-1"

    def test_no_invocations_returns_empty(self):
        mock_repo = MagicMock()
        mock_repo.list_by_device.return_value = []
        with patch(
            "concilium.application.tool_invocations.repository.get_tool_invocation_repository",
            return_value=mock_repo,
        ):
            assert sessions_for_device("unknown-device") == []
