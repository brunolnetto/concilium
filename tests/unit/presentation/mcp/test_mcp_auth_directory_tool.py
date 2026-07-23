"""Tests for concilium.presentation.mcp.tools.auth_directory — unit coverage (ADR-143)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from mcp.server.fastmcp import FastMCP

from concilium.presentation.mcp.tools.auth_directory import register


@pytest.fixture()
def tools():
    server = FastMCP("test-auth-directory")
    register(server)
    tool_map = server._tool_manager._tools
    return {name: tool.fn for name, tool in tool_map.items()}


class TestListarUsuariosVisiveis:
    def test_delegates_to_visibility_service_with_current_context(self, tools):
        with (
            patch(
                "concilium.infrastructure.auth.permission_guard.get_current_user_id",
                return_value="eng1",
            ),
            patch(
                "concilium.infrastructure.auth.permission_guard._current_roles",
            ) as mock_roles,
            patch(
                "concilium.application.services.visibility_service.list_visible_users",
                return_value=[{"client_id": "adm1", "email": "adm1@x.com", "roles": ["admin"], "active": True}],
            ) as mock_list,
        ):
            mock_roles.get.return_value = frozenset({"engineer"})
            result = tools["listar_usuarios_visiveis"]()

        mock_list.assert_called_once()
        called_args = mock_list.call_args.args
        assert called_args[0] == "eng1"
        assert set(called_args[1]) == {"engineer"}
        assert result["status"] == "ok"
        assert result["total"] == 1
        assert result["usuarios"][0]["client_id"] == "adm1"

    def test_empty_result_when_nothing_visible(self, tools):
        with (
            patch(
                "concilium.infrastructure.auth.permission_guard.get_current_user_id",
                return_value="aud1",
            ),
            patch(
                "concilium.infrastructure.auth.permission_guard._current_roles",
            ) as mock_roles,
            patch(
                "concilium.application.services.visibility_service.list_visible_users",
                return_value=[],
            ),
        ):
            mock_roles.get.return_value = frozenset({"auditor"})
            result = tools["listar_usuarios_visiveis"]()

        assert result["status"] == "ok"
        assert result["total"] == 0
        assert result["usuarios"] == []
