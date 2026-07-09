"""Tests for infrastructure/services/notification_service.py (ADR-123, ADR-134 F1).

ADR-134 D1/D5: a infraestrutura só expõe `send()` (renderiza template Jinja2 +
monta multipart/alternative + envia via SMTP/fallback). Os antigos métodos
`notify_*` foram removidos — migrados para `application/services/notifications.py`.
"""

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


class TestRenderTemplate:
    """ADR-134 D2/D3 — o template `notification` consome heading/intro/details/cta/footer_note."""

    def _example_context(self):
        return {
            "heading": "Bem-vindo ao Concilium",
            "intro": "Sua conta foi criada com sucesso.",
            "details": [("Usuário", "bruno"), ("Perfil", "operator")],
            "cta": {"label": "Acessar Concilium", "url": "https://concilium.example.com"},
            "footer_note": "Este link expira em 24h.",
        }

    def test_txt_template_renders_all_fields(self):
        from concilium.infrastructure.services.notification_service import NotificationService

        svc = NotificationService(settings=_make_smtp_settings())
        body = svc._render("notification.txt.jinja2", self._example_context())
        assert "Bem-vindo ao Concilium" in body
        assert "Sua conta foi criada com sucesso." in body
        assert "Usuário: bruno" in body
        assert "Perfil: operator" in body
        assert "Acessar Concilium: https://concilium.example.com" in body
        assert "Este link expira em 24h." in body

    def test_html_template_renders_all_fields_and_extends_base(self):
        from concilium.infrastructure.services.notification_service import NotificationService

        svc = NotificationService(settings=_make_smtp_settings())
        body = svc._render("notification.html.jinja2", self._example_context())
        assert "Concilium" in body  # cabeçalho da _base
        assert "Bem-vindo ao Concilium" in body
        assert "Usuário" in body and "bruno" in body
        assert 'href="https://concilium.example.com"' in body
        assert "Este link expira em 24h." in body

    def test_html_template_autoescapes_user_data(self):
        """ADR-134 D7 — autoescape protege contra dado de usuário quebrando markup."""
        from concilium.infrastructure.services.notification_service import NotificationService

        svc = NotificationService(settings=_make_smtp_settings())
        ctx = {
            "heading": "<script>alert(1)</script>",
            "intro": None,
            "details": None,
            "cta": None,
            "footer_note": None,
        }
        body = svc._render("notification.html.jinja2", ctx)
        assert "<script>alert(1)</script>" not in body
        assert "&lt;script&gt;" in body

    def test_txt_template_omits_optional_blocks_when_absent(self):
        from concilium.infrastructure.services.notification_service import NotificationService

        svc = NotificationService(settings=_make_smtp_settings())
        ctx = {"heading": "Só o essencial", "intro": None, "details": None, "cta": None, "footer_note": None}
        body = svc._render("notification.txt.jinja2", ctx)
        assert "Só o essencial" in body
        assert ":" not in body.replace("Só o essencial", "")


class TestBuildMessage:
    def test_alternative_without_attachments(self):
        from concilium.infrastructure.services.notification_service import NotificationService

        msg = NotificationService._build_message("texto puro", "<b>html</b>", None)
        assert msg.get_content_type() == "multipart/alternative"
        parts = msg.get_payload()
        assert parts[0].get_payload(decode=True).decode("utf-8") == "texto puro"
        assert parts[1].get_payload(decode=True).decode("utf-8") == "<b>html</b>"

    def test_mixed_with_attachments(self):
        from concilium.infrastructure.services.notification_service import NotificationService

        msg = NotificationService._build_message(
            "texto",
            "<p>html</p>",
            [("config.json", b'{"a":1}', "application/json")],
        )
        assert msg.get_content_type() == "multipart/mixed"
        parts = msg.get_payload()
        assert parts[0].get_content_type() == "multipart/alternative"
        assert "config.json" in msg.as_string()


class TestSendFallback:
    """Quando SMTP não habilitado ou sem host, send() loga em vez de enviar."""

    def test_disabled_logs_to_info(self, caplog):
        import logging

        from concilium.infrastructure.services.notification_service import NotificationService

        cfg = _make_smtp_settings(enabled=False)
        svc = NotificationService(settings=cfg)
        with caplog.at_level(logging.INFO, logger="concilium.infrastructure.services.notification_service"):
            svc.send(to="to@x.com", subject="Subj", template="notification", context={"heading": "Oi"})
        assert any("NOTIFICATION LOG FALLBACK" in r.message for r in caplog.records)

    def test_enabled_but_no_host_logs_to_info(self, caplog):
        import logging

        from concilium.infrastructure.services.notification_service import NotificationService

        cfg = _make_smtp_settings(enabled=True, host="")
        svc = NotificationService(settings=cfg)
        with caplog.at_level(logging.INFO, logger="concilium.infrastructure.services.notification_service"):
            svc.send(to="to@x.com", subject="Subj", template="notification", context={"heading": "Oi"})
        assert any("NOTIFICATION LOG FALLBACK" in r.message for r in caplog.records)

    def test_fallback_includes_attachment_name_in_log(self, caplog):
        import logging

        from concilium.infrastructure.services.notification_service import NotificationService

        cfg = _make_smtp_settings(enabled=False)
        svc = NotificationService(settings=cfg)
        with caplog.at_level(logging.INFO, logger="concilium.infrastructure.services.notification_service"):
            svc.send(
                to="to@x.com",
                subject="Subj",
                template="notification",
                context={"heading": "Oi"},
                attachments=[("file.json", b'{"x":1}', "application/json")],
            )
        assert any("file.json" in r.message for r in caplog.records)


class TestSendSmtp:
    """Quando SMTP configurado, send() constrói e envia o email multipart."""

    def _make_smtp_mock(self):
        mock_server = MagicMock()
        mock_smtp_cls = MagicMock()
        mock_smtp_cls.return_value.__enter__ = lambda s, *a: mock_server
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)
        return mock_smtp_cls, mock_server

    def test_send_no_auth(self):
        from concilium.infrastructure.services.notification_service import NotificationService

        cfg = _make_smtp_settings(enabled=True, host="smtp.test.com")
        svc = NotificationService(settings=cfg)
        mock_smtp_cls, mock_server = self._make_smtp_mock()
        with patch("smtplib.SMTP", mock_smtp_cls):
            svc.send(to="dest@x.com", subject="Hello", template="notification", context={"heading": "World"})
        mock_server.sendmail.assert_called_once()

    def test_send_with_auth(self):
        from concilium.infrastructure.services.notification_service import NotificationService

        cfg = _make_smtp_settings(enabled=True, host="smtp.test.com", user="u", password="p")
        svc = NotificationService(settings=cfg)
        mock_smtp_cls, mock_server = self._make_smtp_mock()
        with patch("smtplib.SMTP", mock_smtp_cls):
            svc.send(to="dest@x.com", subject="Hello", template="notification", context={"heading": "World"})
        mock_server.login.assert_called_once_with("u", "p")

    def test_send_with_attachment(self):
        from concilium.infrastructure.services.notification_service import NotificationService

        cfg = _make_smtp_settings(enabled=True, host="smtp.test.com")
        svc = NotificationService(settings=cfg)
        mock_smtp_cls, mock_server = self._make_smtp_mock()
        with patch("smtplib.SMTP", mock_smtp_cls):
            svc.send(
                to="dest@x.com",
                subject="Hello",
                template="notification",
                context={"heading": "World"},
                attachments=[("conf.json", b'{"a":1}', "application/json")],
            )
        args = mock_server.sendmail.call_args[0]
        assert "conf.json" in args[2]

    def test_send_logs_success(self, caplog):
        import logging

        from concilium.infrastructure.services.notification_service import NotificationService

        cfg = _make_smtp_settings(enabled=True, host="smtp.test.com")
        svc = NotificationService(settings=cfg)
        mock_smtp_cls, _ = self._make_smtp_mock()
        with patch("smtplib.SMTP", mock_smtp_cls):
            with caplog.at_level(logging.INFO, logger="concilium.infrastructure.services.notification_service"):
                svc.send(to="dest@x.com", subject="Hi", template="notification", context={"heading": "World"})
        assert any("Email enviado" in r.message for r in caplog.records)


class TestSendNeverRaises:
    def test_smtp_failure_is_captured_and_logged(self, caplog):
        import logging

        from concilium.infrastructure.services.notification_service import NotificationService

        cfg = _make_smtp_settings(enabled=True, host="smtp.test.com")
        svc = NotificationService(settings=cfg)
        with patch("smtplib.SMTP", side_effect=OSError("conexão recusada")):
            with caplog.at_level(logging.ERROR, logger="concilium.infrastructure.services.notification_service"):
                svc.send(to="dest@x.com", subject="Hi", template="notification", context={"heading": "World"})
        assert any("send: falha ao notificar" in r.message for r in caplog.records)

    def test_unknown_template_is_captured_and_logged(self, caplog):
        import logging

        from concilium.infrastructure.services.notification_service import NotificationService

        cfg = _make_smtp_settings(enabled=False)
        svc = NotificationService(settings=cfg)
        with caplog.at_level(logging.ERROR, logger="concilium.infrastructure.services.notification_service"):
            svc.send(to="dest@x.com", subject="Hi", template="nao_existe", context={})
        assert any("send: falha ao notificar" in r.message for r in caplog.records)


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
