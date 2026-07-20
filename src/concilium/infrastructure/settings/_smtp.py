"""Settings (parte extraída de settings.py) — grupo _smtp."""

from __future__ import annotations

from dataclasses import dataclass

from ._core import _flag, _int, _refresh_if_env_changed, _str


@dataclass(frozen=True)
class SmtpSettings:
    """Configuração SMTP para envio de emails transacionais (ADR-123)."""

    host: str
    """CONCILIUM__SMTP_HOST — servidor SMTP."""

    port: int
    """CONCILIUM__SMTP_PORT — porta SMTP (default: 587)."""

    user: str
    """CONCILIUM__SMTP_USER — usuário de autenticação SMTP."""

    password: str
    """CONCILIUM__SMTP_PASSWORD — senha de autenticação SMTP."""

    from_addr: str
    """CONCILIUM__SMTP_FROM — endereço remetente."""

    enabled: bool
    """CONCILIUM__NOTIFICATIONS_ENABLED — habilita envio real de email (default: False)."""

    timeout_seconds: int
    """CONCILIUM__SMTP_TIMEOUT_SECONDS — timeout de conexão/comando SMTP (default: 15s).

    Sem isso, `smtplib.SMTP(host, port)` bloqueia indefinidamente se o servidor
    não responder — a chamada de origem (comando CLI, rota HTTP) fica travada
    junto, sem nenhum limite de tempo.
    """

    @classmethod
    def from_env(cls) -> SmtpSettings:
        password = _str("CONCILIUM__SMTP_PASSWORD", "")
        if not password:
            password = _read_smtp_password_from_kv() or ""
        return cls(
            host=_str("CONCILIUM__SMTP_HOST", ""),
            port=_int("CONCILIUM__SMTP_PORT", 587),
            user=_str("CONCILIUM__SMTP_USER", ""),
            password=password,
            from_addr=_str("CONCILIUM__SMTP_FROM", "concilium@mendesloboconstrucao.com.br"),
            enabled=_flag("CONCILIUM__NOTIFICATIONS_ENABLED"),
            timeout_seconds=_int("CONCILIUM__SMTP_TIMEOUT_SECONDS", 15),
        )


def _read_smtp_password_from_kv() -> str | None:
    """Lê smtp-password do Key Vault via Managed Identity (mesmo padrão do JWT)."""
    kv_url = _str("CONCILIUM__JWT_KEY_VAULT_URL", "").strip()
    if not kv_url:
        return None
    try:
        from azure.identity import DefaultAzureCredential  # ty: ignore[unresolved-import]
        from azure.keyvault.secrets import SecretClient  # ty: ignore[unresolved-import]

        client = SecretClient(vault_url=kv_url, credential=DefaultAzureCredential())
        value = client.get_secret("smtp-password").value or ""
        return value.strip() or None
    except Exception:
        return None


_smtp: SmtpSettings | None = None


def get_smtp() -> SmtpSettings:
    _refresh_if_env_changed()
    global _smtp
    if _smtp is None:
        _smtp = SmtpSettings.from_env()
    return _smtp




def _reset_smtp() -> None:
    global _smtp
    _smtp = None
