"""Settings (parte extraída de settings.py) — grupo _auth."""

from __future__ import annotations

from dataclasses import dataclass

from ._core import _flag, _refresh_if_env_changed, _str


@dataclass(frozen=True)
class AuthSettings:
    """Configuração de autenticação JWT (ADR-094)."""

    enabled: bool
    """CONCILIUM__AUTH_ENABLED — habilita middleware JWT (default: False)."""

    clients_json: str
    """CONCILIUM__AUTH_CLIENTS — JSON com client_id/secret/scopes dos consumidores."""

    jwt_private_key_pem: str
    """CONCILIUM__JWT_PRIVATE_KEY_PEM — chave RS256 privada em PEM (inline)."""

    jwt_private_key_path: str
    """CONCILIUM__JWT_PRIVATE_KEY_PATH — caminho para arquivo PEM da chave privada."""

    jwt_public_key_pem: str
    """CONCILIUM__JWT_PUBLIC_KEY_PEM — chave RS256 pública em PEM (inline)."""

    jwt_public_key_path: str
    """CONCILIUM__JWT_PUBLIC_KEY_PATH — caminho para arquivo PEM da chave pública."""

    key_vault_url: str
    """CONCILIUM__JWT_KEY_VAULT_URL — URL do Azure Key Vault (ex: https://concilium-kv.vault.azure.net).
    Usado em produção via Managed Identity — segredos 'jwt-private-key' e 'jwt-public-key'."""

    data_path: str
    """CONCILIUM__AUTH_DATA_PATH — [opt] Diretório para clients.json e refresh_tokens.json.
    Default: ~/.concilium/auth/"""

    @classmethod
    def from_env(cls) -> AuthSettings:
        return cls(
            enabled=_flag("CONCILIUM__AUTH_ENABLED"),
            clients_json=_str("CONCILIUM__AUTH_CLIENTS", ""),
            jwt_private_key_pem=_str("CONCILIUM__JWT_PRIVATE_KEY_PEM", ""),
            jwt_private_key_path=_str("CONCILIUM__JWT_PRIVATE_KEY_PATH", ""),
            jwt_public_key_pem=_str("CONCILIUM__JWT_PUBLIC_KEY_PEM", ""),
            jwt_public_key_path=_str("CONCILIUM__JWT_PUBLIC_KEY_PATH", ""),
            key_vault_url=_str("CONCILIUM__JWT_KEY_VAULT_URL", ""),
            data_path=_str("CONCILIUM__AUTH_DATA_PATH", ""),
        )


_auth: AuthSettings | None = None


def get_auth() -> AuthSettings:
    _refresh_if_env_changed()
    global _auth
    if _auth is None:
        _auth = AuthSettings.from_env()
    return _auth




def _reset_auth() -> None:
    global _auth
    _auth = None
