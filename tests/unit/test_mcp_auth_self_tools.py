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

    def test_unknown_device_with_prior_devices_triggers_notification(self, tools):
        """ADR-123 F3: device_id novo + client já tinha outros dispositivos -> notifica."""
        old_device = MagicMock(device_id="dev-old", client_id="client-1")
        rt_record = MagicMock(
            token_id="RT-123",
            device_id="dev-new",
            device_name="meu-pc",
            client_id="client-1",
            expires_at="2099-01-01",
        )
        store = MagicMock()
        store.list_devices.return_value = [old_device]
        store.activate_device_code.return_value = rt_record
        with (
            patch("concilium.infrastructure.auth.auth_store.get_auth_store", return_value=store),
            patch(
                "concilium.application.services.device_detection.notify_if_unknown_device"
            ) as notify_mock,
        ):
            result = tools["ativar_dispositivo"]("RCODE-abc", "meu-pc")

        assert result["status"] == "ok"
        notify_mock.assert_called_once_with(store, rt_record, {"dev-old"})

    def test_first_device_of_client_does_not_notify(self, tools):
        rt_record = MagicMock(
            token_id="RT-123",
            device_id="dev-1",
            device_name="meu-pc",
            client_id="client-1",
            expires_at="2099-01-01",
        )
        store = MagicMock()
        store.list_devices.return_value = []
        store.activate_device_code.return_value = rt_record
        with (
            patch("concilium.infrastructure.auth.auth_store.get_auth_store", return_value=store),
            patch(
                "concilium.application.services.notifications.notify_new_device"
            ) as notify_new_device_mock,
        ):
            result = tools["ativar_dispositivo"]("RCODE-abc", "meu-pc")

        assert result["status"] == "ok"
        notify_new_device_mock.assert_not_called()


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

    def test_unknown_device_with_prior_devices_triggers_notification(self, tools):
        """ADR-123 F3: renovar_token também aciona a detecção (use_refresh_token)."""
        old_device = MagicMock(device_id="dev-old", client_id="client-1")
        record = MagicMock(client_id="client-1", device_id="dev-new", roles=["self"])
        store = MagicMock()
        store.list_devices.return_value = [old_device]
        store.use_refresh_token.return_value = record
        with (
            patch("concilium.infrastructure.auth.auth_store.get_auth_store", return_value=store),
            patch(
                "concilium.infrastructure.auth.token_service.issue_token",
                return_value="jwt-token",
            ),
            patch(
                "concilium.application.services.device_detection.notify_if_unknown_device"
            ) as notify_mock,
        ):
            result = tools["renovar_token"]("RT-123")

        assert result["status"] == "ok"
        notify_mock.assert_called_once_with(store, record, {"dev-old"})


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
        with (
            patch(
                "concilium.infrastructure.auth.permission_guard.get_current_user_id",
                return_value="client-1",
            ),
            patch("concilium.infrastructure.auth.auth_store.get_auth_store", return_value=store),
            patch(
                "concilium.application.services.notifications.notify_revoke_pending",
            ) as notify_mock,
        ):
            result = tools["revogar_meu_dispositivo"]("dev-1")

        assert result["status"] == "pending"
        assert result["revoke_token"] == "REVOKE-1"
        assert "user@example.com" in result["message"]
        notify_mock.assert_called_once_with(
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
        with (
            patch(
                "concilium.infrastructure.auth.permission_guard.get_current_user_id",
                return_value="client-1",
            ),
            patch("concilium.infrastructure.auth.auth_store.get_auth_store", return_value=store),
            patch(
                "concilium.application.services.notifications.notify_revoke_pending",
            ) as notify_mock,
        ):
            result = tools["revogar_meu_dispositivo"]("dev-1")

        assert result["status"] == "pending"
        assert "Nenhum email cadastrado" in result["message"]
        notify_mock.assert_not_called()

    def test_success_client_not_in_list(self, tools):
        """client_id não encontrado em list_clients() -> client_email vazio."""
        device = MagicMock(device_id="dev-1")
        pending = MagicMock(revoke_token="REVOKE-1", expires_at="2099-01-01")
        store = MagicMock()
        store.list_devices.return_value = [device]
        store.create_revoke_pending.return_value = pending
        store.list_clients.return_value = []
        with (
            patch(
                "concilium.infrastructure.auth.permission_guard.get_current_user_id",
                return_value="client-1",
            ),
            patch("concilium.infrastructure.auth.auth_store.get_auth_store", return_value=store),
            patch(
                "concilium.application.services.notifications.notify_revoke_pending",
            ) as notify_mock,
        ):
            result = tools["revogar_meu_dispositivo"]("dev-1")

        assert result["status"] == "pending"
        notify_mock.assert_not_called()


class TestObterInstrucoesAtualizadas:
    """ADR-144 D6: sempre lê o arquivo do disco (nunca congela no boot, ao
    contrário do padrão ui:// do ADR-101), e marca last_skill_version_seen
    do client_id atual — só aqui, nunca em ping() (D3/A7)."""

    def test_no_identity(self, tools):
        with patch(
            "concilium.infrastructure.auth.permission_guard.get_current_user_id",
            return_value=None,
        ):
            result = tools["obter_instrucoes_atualizadas"]()

        assert result["status"] == "error"

    def test_success_returns_content_and_version_and_marks_cursor(self, tools):
        store = MagicMock()
        with (
            patch(
                "concilium.infrastructure.auth.permission_guard.get_current_user_id",
                return_value="client-1",
            ),
            patch("concilium.infrastructure.auth.auth_store.get_auth_store", return_value=store),
            patch(
                "concilium.application.services.skill_content.read_skill_content",
                return_value=b"# Versao: 5 - 2026-07-20\nconteudo do skill",
            ),
        ):
            result = tools["obter_instrucoes_atualizadas"]()

        assert result["status"] == "ok"
        assert result["versao"] == 5
        assert "conteudo do skill" in result["conteudo"]
        store.mark_skill_version_seen.assert_called_once_with("client-1", 5)

    def test_reads_fresh_content_every_call_not_cached(self, tools):
        """Achado do ADR-144 D6: nunca deve congelar no import/boot."""
        store = MagicMock()
        with (
            patch(
                "concilium.infrastructure.auth.permission_guard.get_current_user_id",
                return_value="client-1",
            ),
            patch("concilium.infrastructure.auth.auth_store.get_auth_store", return_value=store),
        ):
            with patch(
                "concilium.application.services.skill_content.read_skill_content",
                return_value=b"# Versao: 1 - 2026-01-01\nprimeira",
            ):
                first = tools["obter_instrucoes_atualizadas"]()
            with patch(
                "concilium.application.services.skill_content.read_skill_content",
                return_value=b"# Versao: 2 - 2026-07-20\nsegunda",
            ):
                second = tools["obter_instrucoes_atualizadas"]()

        assert first["versao"] == 1
        assert second["versao"] == 2
        assert first["conteudo"] != second["conteudo"]
