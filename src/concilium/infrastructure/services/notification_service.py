"""Serviço de notificação por email transacional (ADR-123 F1-F3, ADR-134 D1/D3).

ADR-134: a infraestrutura conhece apenas `send()` — renderiza um par de templates
Jinja2 (`{template}.txt.jinja2` / `{template}.html.jinja2`), monta um email
`multipart/alternative` (com `multipart/mixed` por cima quando há anexos) e envia
via SMTP (ou loga em fallback dev/CI). Nenhum caso de uso de negócio (welcome
email, revogação, ownership, ...) vive aqui — isso é responsabilidade de
`application/services/notifications.py`.
"""

from __future__ import annotations

import logging
import smtplib
import threading
import time
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

import jinja2
from markupsafe import Markup, escape

from concilium.infrastructure.settings import SmtpSettings, get_smtp

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent / "templates" / "email"

# Retry/backoff em falha transitória de conexão (mesmo padrão de
# `SharePointBlobStorage._get_with_retry`, `infrastructure/adapters/blob_storage/
# sharepoint.py:24`) — 2 retries, 3 tentativas no total. Erros de aplicação
# (auth inválida, destinatário recusado) não são retentados: retry não resolve
# esses casos e pode mascarar o erro real por mais tempo.
#
# Cuidado: `smtplib.SMTPException` é subclasse de `OSError` nesta versão do
# Python — um `except OSError` sozinho pegaria também `SMTPAuthenticationError`/
# `SMTPRecipientsRefused` (erros de aplicação, não de conexão). Por isso os
# tipos não-retentáveis são checados primeiro, em except clause própria, antes
# do catch-all de `OSError`.
_RETRY_DELAYS_S: tuple[float, ...] = (1.0, 3.0)
_NON_RETRIABLE_SMTP_ERRORS: tuple[type[Exception], ...] = (
    smtplib.SMTPAuthenticationError,
    smtplib.SMTPRecipientsRefused,
    smtplib.SMTPSenderRefused,
    smtplib.SMTPDataError,
    smtplib.SMTPNotSupportedError,
)
_RETRIABLE_SMTP_ERRORS: tuple[type[Exception], ...] = (
    smtplib.SMTPConnectError,
    smtplib.SMTPServerDisconnected,
    smtplib.SMTPHeloError,
    OSError,  # timeout, conexão recusada, DNS — TimeoutError/ConnectionError são subclasses
)


def get_smtp_settings() -> SmtpSettings:
    """Alias de get_smtp() para compatibilidade com o contrato da spec (ADR-123)."""
    return get_smtp()


def _is_html_template(template_name: str | None) -> bool:
    """Autoescape somente para templates HTML (ADR-134 D7) — o `.txt.jinja2` não escapa."""
    return template_name is not None and template_name.endswith(".html.jinja2")


def _nl2br(value: str) -> Markup:
    """Converte '\\n' em '<br>' — única quebra de linha universalmente suportada em email HTML.

    `white-space: pre-wrap` (usado antes) depende do motor de renderização
    respeitar a propriedade CSS: o Outlook desktop (baseado no Word, não um
    engine de browser real) a ignora e colapsa todo o texto numa linha só —
    bug relatado em produção no email de boas-vindas (download_note). Cada
    linha é escapada individualmente antes de juntar com `<br>`, já que o
    resultado marcado `Markup` não passa pelo autoescape do Jinja de novo.
    """
    return Markup("<br>\n").join(escape(line) for line in value.split("\n"))


def _build_jinja_env() -> jinja2.Environment:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=_is_html_template,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["nl2br"] = _nl2br
    return env


_jinja_env = _build_jinja_env()


# ── NotificationService ───────────────────────────────────────────────────────


class NotificationService:
    """Envia notificações por email transacional.

    Quando SMTP não configurado ou CONCILIUM__NOTIFICATIONS_ENABLED=0:
    registra o conteúdo via logger.info (fallback de dev/CI).

    `send()` nunca propaga exceções para o chamador — captura, loga como error e
    retorna False (mesmo padrão dos antigos métodos `notify_*`, removidos por
    esta ADR, mas agora com sinalização de sucesso/falha para o chamador
    decidir se avisa o usuário — antes, uma falha de SMTP/anexo grande demais
    era só logada e o comando de origem imprimia "✓ enviado" mesmo assim).

    A conexão SMTP tem timeout (`CONCILIUM__SMTP_TIMEOUT_SECONDS`, default 15s)
    e falhas transitórias de conexão são retentadas com backoff (`_RETRY_DELAYS_S`)
    antes de `send()` desistir e retornar False.
    """

    def __init__(self, settings: SmtpSettings | None = None, jinja_env: jinja2.Environment | None = None) -> None:
        self._settings = settings or get_smtp_settings()
        self._jinja_env = jinja_env or _jinja_env

    # ── API pública (ADR-134 D1) ────────────────────────────────────────────────

    def send(
        self,
        *,
        to: str,
        subject: str,
        template: str,
        context: dict[str, Any],
        attachments: list[tuple[str, bytes, str]] | None = None,
    ) -> bool:
        """Renderiza `{template}.txt.jinja2`/`{template}.html.jinja2` e envia.

        `context` é passado como-está para ambos os templates. `attachments` é uma
        lista de `(filename, content_bytes, mime_type)` — ex.:
        `("config.json", b"{}", "application/json")`.

        Retorna True se o email foi despachado (enviado via SMTP ou registrado
        no fallback de log dev/CI) e False se algo falhou — o chamador decide o
        que fazer com isso (ex.: avisar o admin que o email pode não ter chegado).
        """
        try:
            text_body = self._render(f"{template}.txt.jinja2", context)
            html_body = self._render(f"{template}.html.jinja2", context)
            self._dispatch(to=to, subject=subject, text_body=text_body, html_body=html_body, attachments=attachments)
            return True
        except Exception as exc:
            logger.error(
                "send: falha ao notificar <%s> subject='%s' template='%s': %s",
                to,
                subject,
                template,
                exc,
                exc_info=True,
            )
            return False

    # ── Internos ───────────────────────────────────────────────────────────────

    def _render(self, template_name: str, context: dict[str, Any]) -> str:
        return self._jinja_env.get_template(template_name).render(**context)

    @staticmethod
    def _log_fallback(
        to: str, subject: str, text_body: str, attachments: list[tuple[str, bytes, str]] | None
    ) -> None:
        # Fallback dev/CI: log sem enviar
        logger.info(
            "[NOTIFICATION LOG FALLBACK] To=%s | Subject=%s | Body=%s%s",
            to,
            subject,
            text_body,
            f" | Attachments={[name for name, _, _ in attachments]}" if attachments else "",
        )

    @staticmethod
    def _build_message(
        text_body: str, html_body: str, attachments: list[tuple[str, bytes, str]] | None
    ) -> MIMEMultipart:
        alternative = MIMEMultipart("alternative")
        alternative.attach(MIMEText(text_body, "plain", "utf-8"))
        alternative.attach(MIMEText(html_body, "html", "utf-8"))

        if not attachments:
            return alternative

        mixed = MIMEMultipart("mixed")
        mixed.attach(alternative)
        for name, content, mime_type in attachments:
            maintype, _, subtype = mime_type.partition("/")
            part = MIMEBase(maintype or "application", subtype or "octet-stream")
            part.set_payload(content)
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f'attachment; filename="{name}"')
            mixed.attach(part)
        return mixed

    def _dispatch(
        self,
        *,
        to: str,
        subject: str,
        text_body: str,
        html_body: str,
        attachments: list[tuple[str, bytes, str]] | None,
    ) -> None:
        cfg = self._settings

        if not cfg.enabled or not cfg.host:
            self._log_fallback(to, subject, text_body, attachments)
            return

        msg = self._build_message(text_body, html_body, attachments)
        msg["Subject"] = subject
        msg["From"] = cfg.from_addr
        msg["To"] = to

        last_exc: Exception | None = None
        for attempt, delay in enumerate((*_RETRY_DELAYS_S, None)):
            try:
                with smtplib.SMTP(cfg.host, cfg.port, timeout=cfg.timeout_seconds) as server:
                    server.ehlo()
                    server.starttls()
                    if cfg.user and cfg.password:
                        server.login(cfg.user, cfg.password)
                    server.sendmail(cfg.from_addr, [to], msg.as_string())
                logger.info("Email enviado para <%s>: %s", to, subject)
                return
            except _NON_RETRIABLE_SMTP_ERRORS:
                raise
            except _RETRIABLE_SMTP_ERRORS as exc:
                last_exc = exc
                if delay is None:
                    break
                logger.warning(
                    "SMTP: falha transitória ao enviar para <%s> (tentativa %d/%d) — retry em %.1fs: %s",
                    to,
                    attempt + 1,
                    len(_RETRY_DELAYS_S) + 1,
                    delay,
                    exc,
                )
                time.sleep(delay)

        assert last_exc is not None  # loop só termina sem `return` se alguma tentativa levantou
        raise last_exc


# ── Singleton ─────────────────────────────────────────────────────────────────

_notification_service: NotificationService | None = None
_ns_lock = threading.Lock()


def get_notification_service() -> NotificationService:
    """Retorna o singleton de NotificationService."""
    global _notification_service
    if _notification_service is None:
        with _ns_lock:
            if _notification_service is None:  # pragma: no cover
                _notification_service = NotificationService()
    assert _notification_service is not None  # double-checked locking sempre atribui antes daqui
    return _notification_service
