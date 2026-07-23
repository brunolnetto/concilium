"""Tests for application/services/notifications.py (ADR-134 F2/F3).

Cada função é fina: monta o `context` (D2) e chama `NotificationService.send()`.
Aqui mockamos `get_notification_service().send` — a renderização/envio real já é
coberta por `tests/unit/test_notification_service.py` (F1).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def _patched_service():
    mock_service = MagicMock()
    patcher = patch(
        "concilium.application.services.notifications.get_notification_service",
        return_value=mock_service,
    )
    return patcher, mock_service


class TestBuildProxyDownloadNote:
    def test_empty_when_no_urls(self):
        from concilium.application.services.notifications import _build_proxy_download_note

        assert _build_proxy_download_note(None) == ""
        assert _build_proxy_download_note({}) == ""
        assert _build_proxy_download_note({"windows": None, "linux": None, "macos": None}) == ""

    def test_includes_each_present_url(self):
        from concilium.application.services.notifications import _build_proxy_download_note

        note = _build_proxy_download_note(
            {
                "windows": "https://x/win.exe",
                "linux": "https://x/linux",
                "macos": "https://x/macos",
            }
        )
        assert "https://x/win.exe" in note
        assert "https://x/linux" in note
        assert "https://x/macos" in note


class TestReadSkillTutorialDelegation:
    """ADR-144 D6: a leitura real do skill vive em skill_content.py — aqui só
    confere que notifications.py delega para lá, sem duplicar a lógica
    (coberta em detalhe por tests/unit/test_skill_content.py)."""

    def test_delegates_to_shared_skill_content_module(self):
        from concilium.application.services import notifications
        from concilium.application.services.skill_content import read_skill_content

        assert notifications._read_skill_tutorial is read_skill_content


class TestNotifyUserCreated:
    def test_sends_with_user_created_template_and_attachments(self):
        from concilium.application.services.notifications import notify_user_created

        patcher, mock_service = _patched_service()
        with patcher:
            notify_user_created("bruno", "operator", "bruno@x.com", '{"unix":true}', '{"windows":true}')

        mock_service.send.assert_called_once()
        kwargs = mock_service.send.call_args.kwargs
        assert kwargs["to"] == "bruno@x.com"
        assert kwargs["template"] == "user_created"
        assert kwargs["context"]["heading"] == "Bem-vindo ao Concilium, bruno!"
        assert ("Perfil", "operator") in kwargs["context"]["details"]
        assert len(kwargs["attachments"]) == 3
        names = [a[0] for a in kwargs["attachments"]]
        assert "claude_desktop_config-macos-linux.json" in names
        assert "claude_desktop_config-windows.json" in names
        assert "concilium_usage_tutorial.skill" in names
        # attachments carry bytes content (ADR-134 D1 contract)
        assert all(isinstance(a[1], bytes) for a in kwargs["attachments"])

    def test_download_note_included_when_urls_present(self):
        from concilium.application.services.notifications import notify_user_created

        patcher, mock_service = _patched_service()
        with patcher:
            notify_user_created(
                "bruno",
                "operator",
                "bruno@x.com",
                "{}",
                "{}",
                proxy_download_urls={"windows": "https://x/win.exe"},
            )
        kwargs = mock_service.send.call_args.kwargs
        assert "https://x/win.exe" in kwargs["context"]["download_note"]


class TestNotifyClientCodeMigrated:
    def test_sends_with_user_created_template(self):
        from concilium.application.services.notifications import notify_client_code_migrated

        patcher, mock_service = _patched_service()
        with patcher:
            notify_client_code_migrated("legacy1", "legacy1@x.com", "{}", "{}")
        mock_service.send.assert_called_once()
        kwargs = mock_service.send.call_args.kwargs
        assert kwargs["template"] == "user_created"
        assert "legacy1" in kwargs["context"]["heading"]
        assert kwargs["context"]["details"] is None


class TestNotifyUserRemoved:
    def test_sends_generic_notification(self):
        from concilium.application.services.notifications import notify_user_removed

        patcher, mock_service = _patched_service()
        with patcher:
            notify_user_removed("client1", "client1@x.com")
        mock_service.send.assert_called_once()
        kwargs = mock_service.send.call_args.kwargs
        assert kwargs["to"] == "client1@x.com"
        assert kwargs["template"] == "notification"
        assert "client1" in kwargs["context"]["heading"]


class TestNotifyUserEdited:
    def test_details_reflect_changes(self):
        from concilium.application.services.notifications import notify_user_edited

        patcher, mock_service = _patched_service()
        with patcher:
            notify_user_edited("client1", "client1@x.com", {"client_code": "regenerado"})
        kwargs = mock_service.send.call_args.kwargs
        assert ("client_code", "regenerado") in kwargs["context"]["details"]


class TestNotifyDeviceRevokedAdmin:
    def test_sends_with_device_details(self):
        from concilium.application.services.notifications import notify_device_revoked_admin

        patcher, mock_service = _patched_service()
        with patcher:
            notify_device_revoked_admin("client1", "macbook-01", "client1@x.com")
        kwargs = mock_service.send.call_args.kwargs
        assert ("Dispositivo", "macbook-01") in kwargs["context"]["details"]


class TestNotifyNewDevice:
    def test_cta_points_to_revoke_pending_link(self):
        from concilium.application.services.notifications import notify_new_device

        patcher, mock_service = _patched_service()
        api = MagicMock(base_url="https://app.test.com", host="localhost", port=8000)
        with patcher, patch("concilium.infrastructure.settings.get_api", return_value=api):
            notify_new_device("c1", "dev-01", "MacBook", "c1@x.com", "revoke-tok-123")
        kwargs = mock_service.send.call_args.kwargs
        assert kwargs["context"]["cta"]["url"] == "https://app.test.com/auth/revoke-pending/revoke-tok-123"

    def test_uses_host_port_when_no_base_url(self):
        from concilium.application.services.notifications import notify_new_device

        patcher, mock_service = _patched_service()
        api = MagicMock(base_url="", host="myhost", port=9000)
        with patcher, patch("concilium.infrastructure.settings.get_api", return_value=api):
            notify_new_device("c1", "dev-01", "Win", "c1@x.com", "tok")
        kwargs = mock_service.send.call_args.kwargs
        assert kwargs["context"]["cta"]["url"] == "http://myhost:9000/auth/revoke-pending/tok"


class TestNotifyRevokePending:
    def test_cta_points_to_revoke_confirm_link(self):
        from concilium.application.services.notifications import notify_revoke_pending

        patcher, mock_service = _patched_service()
        api = MagicMock(base_url="https://app.test.com", host="localhost", port=8000)
        with patcher, patch("concilium.infrastructure.settings.get_api", return_value=api):
            notify_revoke_pending("c1", "dev-01", "c1@x.com", "confirm-tok")
        kwargs = mock_service.send.call_args.kwargs
        assert kwargs["context"]["cta"]["url"] == "https://app.test.com/auth/revoke-confirm/confirm-tok"
