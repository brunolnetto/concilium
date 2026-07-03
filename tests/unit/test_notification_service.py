"""Tests for infrastructure/services/notification_service.py (ADR-123)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def _make_smtp_settings(*, enabled: bool = False, host: str = "", user: str = "", password: str = ""):
    from concilium.infrastructure.settings import SmtpSettings

    return SmtpSettings(
        host=host,
        port=587,
        user=user,
        password=password,
        from_addr="concilium@test.com",
        enabled=enabled,
    )


class TestGetSmtpSettings:
    def test_returns_smtp_settings(self):
        from concilium.infrastructure.services.notification_service import get_smtp_settings

        with patch("concilium.infrastructure.services.notification_service.get_smtp") as mock:
            mock.return_value = _make_smtp_settings()
            result = get_smtp_settings()
        mock.assert_called_once()
        assert result is not None


class TestNotificationServiceInit:
    def test_uses_provided_settings(self):
        from concilium.infrastructure.services.notification_service import NotificationService

        cfg = _make_smtp_settings()
        svc = NotificationService(settings=cfg)
        assert svc._settings is cfg

    def test_defaults_to_get_smtp_settings(self):
        from concilium.infrastructure.services.notification_service import NotificationService

        cfg = _make_smtp_settings()
        with patch("concilium.infrastructure.services.notification_service.get_smtp_settings", return_value=cfg):
            svc = NotificationService()
        assert svc._settings is cfg


class TestSendFallback:
    """When SMTP not enabled or host empty, _send logs instead of sending."""

    def test_disabled_logs_to_info(self, caplog):
        import logging

        from concilium.infrastructure.services.notification_service import NotificationService

        cfg = _make_smtp_settings(enabled=False, host="")
        svc = NotificationService(settings=cfg)
        with caplog.at_level(logging.INFO, logger="concilium.infrastructure.services.notification_service"):
            svc._send("to@x.com", "Subj", "Body")
        assert any("NOTIFICATION LOG FALLBACK" in r.message for r in caplog.records)

    def test_enabled_but_no_host_logs_to_info(self, caplog):
        import logging

        from concilium.infrastructure.services.notification_service import NotificationService

        cfg = _make_smtp_settings(enabled=True, host="")
        svc = NotificationService(settings=cfg)
        with caplog.at_level(logging.INFO, logger="concilium.infrastructure.services.notification_service"):
            svc._send("to@x.com", "Subj", "Body")
        assert any("NOTIFICATION LOG FALLBACK" in r.message for r in caplog.records)

    def test_fallback_includes_attachment_name_in_log(self, caplog):
        import logging

        from concilium.infrastructure.services.notification_service import NotificationService

        cfg = _make_smtp_settings(enabled=False)
        svc = NotificationService(settings=cfg)
        with caplog.at_level(logging.INFO, logger="concilium.infrastructure.services.notification_service"):
            svc._send("to@x.com", "Subj", "Body", attachment_name="file.json", attachment_content='{"x":1}')
        assert any("file.json" in r.message for r in caplog.records)


class TestSendSmtp:
    """When SMTP is configured, _send constructs and sends the email."""

    def _make_smtp_mock(self):
        mock_server = MagicMock()
        mock_smtp_cls = MagicMock()
        mock_smtp_cls.return_value.__enter__ = lambda s, *a: mock_server
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)
        return mock_smtp_cls, mock_server

    def test_send_plain_text_no_auth(self):
        from concilium.infrastructure.services.notification_service import NotificationService

        cfg = _make_smtp_settings(enabled=True, host="smtp.test.com")
        svc = NotificationService(settings=cfg)
        mock_smtp_cls, mock_server = self._make_smtp_mock()
        with patch("smtplib.SMTP", mock_smtp_cls):
            svc._send("dest@x.com", "Hello", "World")
        mock_server.sendmail.assert_called_once()

    def test_send_with_auth(self):
        from concilium.infrastructure.services.notification_service import NotificationService

        cfg = _make_smtp_settings(enabled=True, host="smtp.test.com", user="u", password="p")
        svc = NotificationService(settings=cfg)
        mock_smtp_cls, mock_server = self._make_smtp_mock()
        with patch("smtplib.SMTP", mock_smtp_cls):
            svc._send("dest@x.com", "Hello", "World")
        mock_server.login.assert_called_once_with("u", "p")

    def test_send_with_attachment(self):
        from concilium.infrastructure.services.notification_service import NotificationService

        cfg = _make_smtp_settings(enabled=True, host="smtp.test.com")
        svc = NotificationService(settings=cfg)
        mock_smtp_cls, mock_server = self._make_smtp_mock()
        with patch("smtplib.SMTP", mock_smtp_cls):
            svc._send("dest@x.com", "Hello", "Body", attachment_name="conf.json", attachment_content='{"a":1}')
        args = mock_server.sendmail.call_args[0]
        assert "conf.json" in args[2]  # the message string contains the filename

    def test_send_logs_success(self, caplog):
        import logging

        from concilium.infrastructure.services.notification_service import NotificationService

        cfg = _make_smtp_settings(enabled=True, host="smtp.test.com")
        svc = NotificationService(settings=cfg)
        mock_smtp_cls, _ = self._make_smtp_mock()
        with patch("smtplib.SMTP", mock_smtp_cls):
            with caplog.at_level(logging.INFO, logger="concilium.infrastructure.services.notification_service"):
                svc._send("dest@x.com", "Hi", "Body")
        assert any("Email enviado" in r.message for r in caplog.records)


class TestNotifyUserCreated:
    def test_happy_path_fallback(self):
        from concilium.infrastructure.services.notification_service import NotificationService

        cfg = _make_smtp_settings(enabled=False)
        svc = NotificationService(settings=cfg)
        # Should not raise
        svc.notify_user_created("client1", "operator", "client1@test.com", '{"mcpServers":{}}')

    def test_exception_captured_as_error(self, caplog):
        import logging

        from concilium.infrastructure.services.notification_service import NotificationService

        cfg = _make_smtp_settings(enabled=False)
        svc = NotificationService(settings=cfg)
        with patch.object(svc, "_send", side_effect=RuntimeError("smtp down")):
            with caplog.at_level(logging.ERROR, logger="concilium.infrastructure.services.notification_service"):
                svc.notify_user_created("c1", "op", "c1@x.com", "{}")
        assert any("notify_user_created" in r.message for r in caplog.records)


class TestNotifyClientCodeMigrated:
    def test_happy_path_fallback(self):
        from concilium.infrastructure.services.notification_service import NotificationService

        cfg = _make_smtp_settings(enabled=False)
        svc = NotificationService(settings=cfg)
        # Should not raise
        svc.notify_client_code_migrated("legacy1", "legacy1@test.com", '{"mcpServers":{}}')

    def test_exception_captured_as_error(self, caplog):
        import logging

        from concilium.infrastructure.services.notification_service import NotificationService

        cfg = _make_smtp_settings(enabled=False)
        svc = NotificationService(settings=cfg)
        with patch.object(svc, "_send", side_effect=RuntimeError("smtp down")):
            with caplog.at_level(logging.ERROR, logger="concilium.infrastructure.services.notification_service"):
                svc.notify_client_code_migrated("c1", "c1@x.com", "{}")
        assert any("notify_client_code_migrated" in r.message for r in caplog.records)


class TestNotifyUserRemoved:
    def test_happy_path_fallback(self):
        from concilium.infrastructure.services.notification_service import NotificationService

        cfg = _make_smtp_settings(enabled=False)
        svc = NotificationService(settings=cfg)
        svc.notify_user_removed("client1", "client1@test.com")

    def test_exception_captured(self, caplog):
        import logging

        from concilium.infrastructure.services.notification_service import NotificationService

        cfg = _make_smtp_settings(enabled=False)
        svc = NotificationService(settings=cfg)
        with patch.object(svc, "_send", side_effect=OSError("net err")):
            with caplog.at_level(logging.ERROR, logger="concilium.infrastructure.services.notification_service"):
                svc.notify_user_removed("c1", "c1@x.com")
        assert any("notify_user_removed" in r.message for r in caplog.records)


class TestNotifyNewDevice:
    def _mock_api(self, base_url="https://app.test.com"):
        api = MagicMock()
        api.base_url = base_url
        api.host = "localhost"
        api.port = 8000
        return api

    def test_happy_path_fallback(self):
        from concilium.infrastructure.services.notification_service import NotificationService

        cfg = _make_smtp_settings(enabled=False)
        svc = NotificationService(settings=cfg)
        with patch("concilium.infrastructure.services.notification_service.get_smtp_settings", return_value=cfg):
            with patch("concilium.infrastructure.settings.get_api", return_value=self._mock_api()):
                svc.notify_new_device("c1", "dev-01", "MacBook", "c1@x.com", "revoke-tok-123")

    def test_uses_host_port_when_no_base_url(self):
        from concilium.infrastructure.services.notification_service import NotificationService

        cfg = _make_smtp_settings(enabled=False)
        svc = NotificationService(settings=cfg)
        api = self._mock_api(base_url="")
        api.host = "myhost"
        api.port = 9000
        with patch("concilium.infrastructure.settings.get_api", return_value=api):
            svc.notify_new_device("c1", "dev-01", "Win", "c1@x.com", "tok")

    def test_exception_captured(self, caplog):
        import logging

        from concilium.infrastructure.services.notification_service import NotificationService

        cfg = _make_smtp_settings(enabled=False)
        svc = NotificationService(settings=cfg)
        with patch.object(svc, "_send", side_effect=ValueError("bad")):
            with patch("concilium.infrastructure.settings.get_api", return_value=self._mock_api()):
                with caplog.at_level(logging.ERROR, logger="concilium.infrastructure.services.notification_service"):
                    svc.notify_new_device("c1", "dev-01", "Dev", "c1@x.com", "tok")
        assert any("notify_new_device" in r.message for r in caplog.records)


class TestNotifyRevokePending:
    def _mock_api(self, base_url="https://app.test.com"):
        api = MagicMock()
        api.base_url = base_url
        api.host = "localhost"
        api.port = 8000
        return api

    def test_happy_path_fallback(self):
        from concilium.infrastructure.services.notification_service import NotificationService

        cfg = _make_smtp_settings(enabled=False)
        svc = NotificationService(settings=cfg)
        with patch("concilium.infrastructure.settings.get_api", return_value=self._mock_api()):
            svc.notify_revoke_pending("c1", "dev-01", "c1@x.com", "confirm-tok")

    def test_uses_host_port_when_no_base_url(self):
        from concilium.infrastructure.services.notification_service import NotificationService

        cfg = _make_smtp_settings(enabled=False)
        svc = NotificationService(settings=cfg)
        api = self._mock_api(base_url="")
        api.host = "myhost"
        api.port = 9000
        with patch("concilium.infrastructure.settings.get_api", return_value=api):
            svc.notify_revoke_pending("c1", "dev-01", "c1@x.com", "tok")

    def test_exception_captured(self, caplog):
        import logging

        from concilium.infrastructure.services.notification_service import NotificationService

        cfg = _make_smtp_settings(enabled=False)
        svc = NotificationService(settings=cfg)
        with patch.object(svc, "_send", side_effect=ConnectionError("refused")):
            with patch("concilium.infrastructure.settings.get_api", return_value=self._mock_api()):
                with caplog.at_level(logging.ERROR, logger="concilium.infrastructure.services.notification_service"):
                    svc.notify_revoke_pending("c1", "dev-01", "c1@x.com", "tok")
        assert any("notify_revoke_pending" in r.message for r in caplog.records)


class TestGetNotificationServiceSingleton:
    def test_returns_instance(self):
        import concilium.infrastructure.services.notification_service as mod
        from concilium.infrastructure.services.notification_service import get_notification_service

        original = mod._notification_service
        try:
            mod._notification_service = None
            svc = get_notification_service()
            assert svc is not None
            # Second call returns same instance
            svc2 = get_notification_service()
            assert svc is svc2
        finally:
            mod._notification_service = original
