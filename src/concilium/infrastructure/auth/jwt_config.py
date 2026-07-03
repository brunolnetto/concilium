"""RS256 key loading — env vars, files, Azure Key Vault, or ephemeral dev keys.

Priority (private key):
  1. CONCILIUM__JWT_PRIVATE_KEY_PEM  — PEM string inline (env var)
  2. CONCILIUM__JWT_PRIVATE_KEY_PATH — path to PEM file
  3. CONCILIUM__JWT_KEY_VAULT_URL    — Azure Key Vault via Managed Identity (ADR-094 Fase 1)
  4. Auto-generated ephemeral key    — dev-only, invalidates on restart

Key Vault secret names: "jwt-private-key" and "jwt-public-key".
In production (ACI), the container's Managed Identity must have
"Key Vault Secrets User" role on the vault.
"""

from __future__ import annotations

import os
import warnings
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

from concilium.infrastructure.settings import get_auth


class RS256KeyPair(NamedTuple):
    private_pem: bytes
    public_pem: bytes


@lru_cache(maxsize=1)
def load_key_pair() -> RS256KeyPair:
    """Return RS256 key pair. Cached for the lifetime of the process."""
    private_pem = _read_pem(
        "CONCILIUM__JWT_PRIVATE_KEY_PEM",
        "CONCILIUM__JWT_PRIVATE_KEY_PATH",
        kv_secret="jwt-private-key",
    )
    public_pem = _read_pem(
        "CONCILIUM__JWT_PUBLIC_KEY_PEM",
        "CONCILIUM__JWT_PUBLIC_KEY_PATH",
        kv_secret="jwt-public-key",
    )

    if private_pem and public_pem:
        return RS256KeyPair(private_pem=private_pem, public_pem=public_pem)

    warnings.warn(
        "CONCILIUM__JWT keys not configured — generating ephemeral RS256 pair. "
        "Tokens will be invalid after restart. Configure CONCILIUM__JWT_KEY_VAULT_URL "
        "(production) or CONCILIUM__JWT_PRIVATE_KEY_PEM/_PATH (dev).",
        UserWarning,
        stacklevel=2,
    )
    return _generate_ephemeral()


def _read_pem(env_pem: str, env_path: str, *, kv_secret: str) -> bytes | None:
    auth = get_auth()
    pem_by_name = {
        "CONCILIUM__JWT_PRIVATE_KEY_PEM": auth.jwt_private_key_pem,
        "CONCILIUM__JWT_PUBLIC_KEY_PEM": auth.jwt_public_key_pem,
    }
    path_by_name = {
        "CONCILIUM__JWT_PRIVATE_KEY_PATH": auth.jwt_private_key_path,
        "CONCILIUM__JWT_PUBLIC_KEY_PATH": auth.jwt_public_key_path,
    }
    # Preserva bytes exatamente como definidos na env var (incluindo newline final).
    raw = os.environ.get(env_pem)
    if raw is None:
        raw = pem_by_name.get(env_pem, "")
    if raw.strip():
        return raw.encode()
    path_str = path_by_name.get(env_path, "").strip()
    if path_str:
        return Path(path_str).read_bytes()
    return _read_from_key_vault(kv_secret)


def _read_from_key_vault(secret_name: str) -> bytes | None:
    """Fetch a PEM secret from Azure Key Vault using Managed Identity."""
    kv_url = get_auth().key_vault_url.strip()
    if not kv_url:
        return None
    try:
        from azure.identity import DefaultAzureCredential  # ty: ignore[unresolved-import]
        from azure.keyvault.secrets import SecretClient  # ty: ignore[unresolved-import]

        client = SecretClient(vault_url=kv_url, credential=DefaultAzureCredential())
        value = client.get_secret(secret_name).value or ""
        return value.encode() if value.strip() else None
    except ImportError:
        warnings.warn(
            "azure-keyvault-secrets not installed. Install with: pip install 'concilium[azure]'",
            UserWarning,
            stacklevel=3,
        )
        return None
    except Exception as exc:
        warnings.warn(
            f"Key Vault read failed for '{secret_name}' at {kv_url!r}: {exc}. "
            "Check Managed Identity and RBAC (Key Vault Secrets User).",
            UserWarning,
            stacklevel=3,
        )
        return None


def _generate_ephemeral() -> RS256KeyPair:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return RS256KeyPair(private_pem=private_pem, public_pem=public_pem)
