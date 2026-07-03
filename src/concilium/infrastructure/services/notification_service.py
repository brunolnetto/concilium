"""Serviço de notificação por email transacional (ADR-123 F1-F3)."""

from __future__ import annotations

import logging
import smtplib
import threading
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from concilium.infrastructure.settings import SmtpSettings, get_smtp

logger = logging.getLogger(__name__)


def get_smtp_settings() -> SmtpSettings:
    """Alias de get_smtp() para compatibilidade com o contrato da spec (ADR-123)."""
    return get_smtp()


# ── NotificationService ───────────────────────────────────────────────────────


class NotificationService:
    """Envia notificações por email transacional.

    Quando SMTP não configurado ou CONCILIUM__NOTIFICATIONS_ENABLED=0:
    registra o conteúdo via logger.info (fallback de dev/CI).

    Todos os métodos públicos capturam exceções e as logam como error —
    nunca propagam exceções para o chamador.
    """

    def __init__(self, settings: SmtpSettings | None = None) -> None:
        self._settings = settings or get_smtp_settings()

    # ── Métodos públicos ───────────────────────────────────────────────────────

    def notify_user_created(
        self,
        client_id: str,
        role: str,
        email: str,
        config_json_unix: str,
        config_json_windows: str,
    ) -> None:
        """Envia email de boas-vindas com os dois configs (macOS/Linux e Windows) em anexo.

        O admin não sabe necessariamente o SO do dispositivo do usuário no momento do
        cadastro — manda os dois e deixa o próprio usuário escolher o que corresponde
        ao seu sistema, em vez de arriscar mandar o formato errado.
        """
        try:
            subject = f"[Concilium] Bem-vindo, {client_id}! Sua conta foi criada."
            body = (
                f"Olá!\n\n"
                f"Sua conta no Concilium foi criada com sucesso.\n\n"
                f"  Usuário : {client_id}\n"
                f"  Perfil  : {role}\n\n"
                f"Em anexo, dois arquivos claude_desktop_config.json — use o que corresponde\n"
                f"ao seu sistema operacional:\n\n"
                f"  claude_desktop_config-macos-linux.json → macOS/Linux\n"
                f"  claude_desktop_config-windows.json     → Windows\n\n"
                f"Adicione o conteúdo do arquivo escolhido ao seu arquivo de configuração:\n\n"
                f"  macOS: ~/Library/Application Support/Claude/claude_desktop_config.json\n"
                f"  Win  : %APPDATA%\\Claude\\claude_desktop_config.json\n\n"
                f"Se não conseguir abrir os anexos, o conteúdo é:\n\n"
                f"[macOS/Linux]\n{config_json_unix}\n\n"
                f"[Windows]\n{config_json_windows}\n\n"
                f"Atenciosamente,\nEquipe Concilium"
            )
            self._send(
                to=email,
                subject=subject,
                body=body,
                attachments=[
                    ("claude_desktop_config-macos-linux.json", config_json_unix),
                    ("claude_desktop_config-windows.json", config_json_windows),
                ],
            )
        except Exception as exc:
            logger.error(
                "notify_user_created: falha ao notificar '%s' <%s>: %s",
                client_id,
                email,
                exc,
                exc_info=True,
            )

    def notify_client_code_migrated(
        self,
        client_id: str,
        email: str,
        config_json_unix: str,
        config_json_windows: str,
    ) -> None:
        """Notifica um client migrado (client_code gerado retroativamente) com os dois configs."""
        try:
            subject = f"[Concilium] Novo código de ativação para '{client_id}'"
            body = (
                f"Olá!\n\n"
                f"Sua conta no Concilium recebeu um código de ativação de dispositivo novo\n"
                f"(atualização do sistema de autenticação — nenhuma ação sua causou isso).\n\n"
                f"Para ativar o Claude Desktop (ou reativar um dispositivo já configurado),\n"
                f"substitua o bloco 'concilium' em claude_desktop_config.json pelo conteúdo\n"
                f"de um dos anexos — use o que corresponde ao seu sistema operacional:\n\n"
                f"  claude_desktop_config-macos-linux.json → macOS/Linux\n"
                f"  claude_desktop_config-windows.json     → Windows\n\n"
                f"  macOS: ~/Library/Application Support/Claude/claude_desktop_config.json\n"
                f"  Win  : %APPDATA%\\Claude\\claude_desktop_config.json\n\n"
                f"Se não conseguir abrir os anexos, o conteúdo é:\n\n"
                f"[macOS/Linux]\n{config_json_unix}\n\n"
                f"[Windows]\n{config_json_windows}\n\n"
                f"Atenciosamente,\nEquipe Concilium"
            )
            self._send(
                to=email,
                subject=subject,
                body=body,
                attachments=[
                    ("claude_desktop_config-macos-linux.json", config_json_unix),
                    ("claude_desktop_config-windows.json", config_json_windows),
                ],
            )
        except Exception as exc:
            logger.error(
                "notify_client_code_migrated: falha ao notificar '%s' <%s>: %s",
                client_id,
                email,
                exc,
                exc_info=True,
            )

    def notify_user_removed(self, client_id: str, email: str) -> None:
        """Envia email informando a remoção do usuário."""
        try:
            subject = f"[Concilium] Acesso de '{client_id}' removido."
            body = (
                f"Olá,\n\n"
                f"O acesso do usuário '{client_id}' ao Concilium foi removido e todos "
                f"os dispositivos associados foram revogados.\n\n"
                f"Se isso foi feito por engano, entre em contato com o administrador.\n\n"
                f"Atenciosamente,\nEquipe Concilium"
            )
            self._send(to=email, subject=subject, body=body)
        except Exception as exc:
            logger.error(
                "notify_user_removed: falha ao notificar '%s' <%s>: %s",
                client_id,
                email,
                exc,
                exc_info=True,
            )

    def notify_new_device(
        self,
        client_id: str,
        device_id: str,
        device_name: str,
        email: str,
        revoke_token: str,
    ) -> None:
        """Envia alerta de novo dispositivo com link de revogação."""
        try:
            from concilium.infrastructure.settings import get_api

            api = get_api()
            base_url = api.base_url or f"http://{api.host}:{api.port}"
            revoke_link = f"{base_url.rstrip('/')}/auth/revoke-pending/{revoke_token}"

            subject = f"[Concilium] Novo dispositivo conectado: {device_name}"
            body = (
                f"Olá, {client_id}!\n\n"
                f"Um novo dispositivo foi conectado à sua conta:\n\n"
                f"  Dispositivo : {device_name}\n"
                f"  Device ID   : {device_id}\n\n"
                f"Se você NÃO reconhece este acesso, clique no link abaixo para\n"
                f"iniciar a revogação imediata:\n\n"
                f"  {revoke_link}\n\n"
                f"Se foi você quem configurou este dispositivo, ignore este email.\n\n"
                f"Atenciosamente,\nEquipe Concilium"
            )
            self._send(to=email, subject=subject, body=body)
        except Exception as exc:
            logger.error(
                "notify_new_device: falha ao notificar '%s' <%s> device='%s': %s",
                client_id,
                email,
                device_id,
                exc,
                exc_info=True,
            )

    def notify_revoke_pending(
        self,
        client_id: str,
        device_id: str,
        email: str,
        revoke_token: str,
    ) -> None:
        """Envia email de confirmação de revogação solicitada via MCP self-service."""
        try:
            from concilium.infrastructure.settings import get_api

            api = get_api()
            base_url = api.base_url or f"http://{api.host}:{api.port}"
            confirm_link = f"{base_url.rstrip('/')}/auth/revoke-confirm/{revoke_token}"

            subject = f"[Concilium] Confirme a revogação do dispositivo '{device_id}'"
            body = (
                f"Olá, {client_id}!\n\n"
                f"Você solicitou a revogação do dispositivo '{device_id}'.\n\n"
                f"Para confirmar, clique no link abaixo (válido por 24h):\n\n"
                f"  {confirm_link}\n\n"
                f"Se não foi você, ignore este email — nenhuma ação será tomada.\n\n"
                f"Atenciosamente,\nEquipe Concilium"
            )
            self._send(to=email, subject=subject, body=body)
        except Exception as exc:
            logger.error(
                "notify_revoke_pending: falha ao notificar '%s' <%s> device='%s': %s",
                client_id,
                email,
                device_id,
                exc,
                exc_info=True,
            )

    # ── Internos ───────────────────────────────────────────────────────────────

    def _send(
        self,
        to: str,
        subject: str,
        body: str,
        attachment_name: str | None = None,
        attachment_content: str | None = None,
        attachments: list[tuple[str, str]] | None = None,
    ) -> None:
        """Envia email ou faz log fallback quando SMTP não está configurado.

        Aceita um único anexo (attachment_name/attachment_content, legado) ou uma
        lista de anexos (attachments — [(filename, content), ...], ex.: configs
        macOS/Linux e Windows lado a lado no mesmo email).
        """
        cfg = self._settings
        all_attachments = list(attachments or [])
        if attachment_name and attachment_content:
            all_attachments.append((attachment_name, attachment_content))

        if not cfg.enabled or not cfg.host:
            # Fallback dev/CI: log sem enviar
            logger.info(
                "[NOTIFICATION LOG FALLBACK] To=%s | Subject=%s | Body=%s%s",
                to,
                subject,
                body,
                f" | Attachments={[name for name, _ in all_attachments]}" if all_attachments else "",
            )
            return

        if all_attachments:
            msg: MIMEMultipart | MIMEText = MIMEMultipart()
            assert isinstance(msg, MIMEMultipart)
            msg.attach(MIMEText(body, "plain", "utf-8"))
            for name, content in all_attachments:
                part = MIMEBase("application", "json")
                part.set_payload(content.encode("utf-8"))
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", f'attachment; filename="{name}"')
                msg.attach(part)
        else:
            msg = MIMEText(body, "plain", "utf-8")

        msg["Subject"] = subject
        msg["From"] = cfg.from_addr
        msg["To"] = to

        with smtplib.SMTP(cfg.host, cfg.port) as server:
            server.ehlo()
            server.starttls()
            if cfg.user and cfg.password:
                server.login(cfg.user, cfg.password)
            server.sendmail(cfg.from_addr, [to], msg.as_string())

        logger.info("Email enviado para <%s>: %s", to, subject)


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
    return _notification_service
