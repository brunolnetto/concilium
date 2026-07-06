"""Tests for concilium.presentation.mcp.tools.auth_self — unit coverage.

Coverage targets:
  ativar_dispositivo: success and invalid client_code
  renovar_token: success and invalid/expired refresh_token
  listar_meus_dispositivos: no identity, success with devices
  revogar_meu_dispositivo: no identity, device not found, success with/without email
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from mcp.server.fastmcp import FastMCP

from concilium.presentation.mcp.tools.auth_self import register


@pytest.fixture()
def tools():
    server = FastMCP("test-auth-self")
    register(server)
    tool_map = server._tool_manager._tools
    return {name: tool.fn for name, tool in tool_map.items()}


class TestAtivarDispositivo:
    def test_success(self, tools):
        rt_record = MagicMock(
            token_id="RT-123",
            device_id="dev-1",
            device_name="meu-pc",
            client_id="client-1",
            expires_at="2099-01-01",
        )
        store = MagicMock()
        store.activate_device_code.return_value = rt_record
        with patch("concilium.infrastructure.auth.auth_store.get_auth_store", return_value=store):
            result = tools["ativar_dispositivo"]("RCODE-abc", "meu-pc")

        assert result["status"] == "ok"
        assert result["refresh_token"] == "RT-123"
        assert result["device_id"] == "dev-1"

    def test_invalid_client_code(self, tools):
        store = MagicMock()
        store.activate_device_code.return_value = None
        with patch("concilium.infrastructure.auth.auth_store.get_auth_store", return_value=store):
            result = tools["ativar_dispositivo"]("bad-code", "meu-pc")

        assert result["status"] == "error"
        assert "inválido" in result["message"]


class TestRenovarToken:
    def test_success(self, tools):
        record = MagicMock(client_id="client-1", roles=["self"])
        store = MagicMock()
        store.use_refresh_token.return_value = record
        with (
            patch("concilium.infrastructure.auth.auth_store.get_auth_store", return_value=store),
            patch(
                "concilium.infrastructure.auth.token_service.issue_token",
                return_value="jwt-token",
            ) as mock_issue,
        ):
            result = tools["renovar_token"]("RT-123")

        assert result["status"] == "ok"
        assert result["access_token"] == "jwt-token"
        assert result["token_type"] == "Bearer"
        assert isinstance(result["expires_in"], int)
        mock_issue.assert_called_once()

    def test_invalid_token(self, tools):
        store = MagicMock()
        store.use_refresh_token.return_value = None
        with patch("concilium.infrastructure.auth.auth_store.get_auth_store", return_value=store):
            result = tools["renovar_token"]("RT-bad")

        assert result["status"] == "error"
        assert "inválido" in result["message"]


class TestListarMeusDispositivos:
    def test_no_identity(self, tools):
        with patch(
            "concilium.infrastructure.auth.permission_guard.get_current_user_id",
            return_value=None,
        ):
            result = tools["listar_meus_dispositivos"]()

        assert result["status"] == "error"
        assert result["dispositivos"] == []

    def test_success(self, tools):
        device = MagicMock(
            device_id="dev-1",
            device_name="meu-pc",
            issued_at="2020-01-01",
            expires_at="2099-01-01",
            last_used_at=None,
        )
        store = MagicMock()
        store.list_devices.return_value = [device]
        with (
            patch(
                "concilium.infrastructure.auth.permission_guard.get_current_user_id",
                return_value="client-1",
            ),
            patch("concilium.infrastructure.auth.auth_store.get_auth_store", return_value=store),
        ):
            result = tools["listar_meus_dispositivos"]()

        assert result["status"] == "ok"
        assert result["total"] == 1
        assert result["dispositivos"][0]["device_id"] == "dev-1"
        assert result["dispositivos"][0]["last_used_at"] is None


class TestRevogarMeuDispositivo:
    def test_no_identity(self, tools):
        with patch(
            "concilium.infrastructure.auth.permission_guard.get_current_user_id",
            return_value=None,
        ):
            result = tools["revogar_meu_dispositivo"]("dev-1")

        assert result["status"] == "error"

    def test_device_not_found(self, tools):
        store = MagicMock()
        store.list_devices.return_value = []
        with (
            patch(
                "concilium.infrastructure.auth.permission_guard.get_current_user_id",
                return_value="client-1",
            ),
            patch("concilium.infrastructure.auth.auth_store.get_auth_store", return_value=store),
        ):
            result = tools["revogar_meu_dispositivo"]("dev-missing")

        assert result["status"] == "error"
        assert "não encontrado" in result["message"]

    def test_success_with_email(self, tools):
        device = MagicMock(device_id="dev-1")
        client = MagicMock(client_id="client-1", email="user@example.com")
        pending = MagicMock(revoke_token="REVOKE-1", expires_at="2099-01-01")
        store = MagicMock()
        store.list_devices.return_value = [device]
        store.create_revoke_pending.return_value = pending
        store.list_clients.return_value = [client]
        notification_service = MagicMock()
        with (
            patch(
                "concilium.infrastructure.auth.permission_guard.get_current_user_id",
                return_value="client-1",
            ),
            patch("concilium.infrastructure.auth.auth_store.get_auth_store", return_value=store),
            patch(
                "concilium.infrastructure.services.notification_service.get_notification_service",
                return_value=notification_service,
            ),
        ):
            result = tools["revogar_meu_dispositivo"]("dev-1")

        assert result["status"] == "pending"
        assert result["revoke_token"] == "REVOKE-1"
        assert "user@example.com" in result["message"]
        notification_service.notify_revoke_pending.assert_called_once_with(
            client_id="client-1",
            device_id="dev-1",
            email="user@example.com",
            revoke_token="REVOKE-1",
        )

    def test_success_without_email(self, tools):
        device = MagicMock(device_id="dev-1")
        client = MagicMock(client_id="client-1", email="")
        pending = MagicMock(revoke_token="REVOKE-1", expires_at="2099-01-01")
        store = MagicMock()
        store.list_devices.return_value = [device]
        store.create_revoke_pending.return_value = pending
        store.list_clients.return_value = [client]
        notification_service = MagicMock()
        with (
            patch(
                "concilium.infrastructure.auth.permission_guard.get_current_user_id",
                return_value="client-1",
            ),
            patch("concilium.infrastructure.auth.auth_store.get_auth_store", return_value=store),
            patch(
                "concilium.infrastructure.services.notification_service.get_notification_service",
                return_value=notification_service,
            ),
        ):
            result = tools["revogar_meu_dispositivo"]("dev-1")

        assert result["status"] == "pending"
        assert "Nenhum email cadastrado" in result["message"]
        notification_service.notify_revoke_pending.assert_not_called()

    def test_success_client_not_in_list(self, tools):
        """client_id não encontrado em list_clients() -> client_email vazio."""
        device = MagicMock(device_id="dev-1")
        pending = MagicMock(revoke_token="REVOKE-1", expires_at="2099-01-01")
        store = MagicMock()
        store.list_devices.return_value = [device]
        store.create_revoke_pending.return_value = pending
        store.list_clients.return_value = []
        notification_service = MagicMock()
        with (
            patch(
                "concilium.infrastructure.auth.permission_guard.get_current_user_id",
                return_value="client-1",
            ),
            patch("concilium.infrastructure.auth.auth_store.get_auth_store", return_value=store),
            patch(
                "concilium.infrastructure.services.notification_service.get_notification_service",
                return_value=notification_service,
            ),
        ):
            result = tools["revogar_meu_dispositivo"]("dev-1")

        assert result["status"] == "pending"
        notification_service.notify_revoke_pending.assert_not_called()
