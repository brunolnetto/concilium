"""Client credential store — env-based MVP, Azure AD B2C seam.

Clients are defined via CONCILIUM__AUTH_CLIENTS (JSON env var):

    {
      "claude-desktop": {
        "secret": "plaintext-dev-secret",
        "roles": ["operator"]
      },
      "ci-runner": {
        "secret_hash": "sha256:<hex>",
        "roles": ["service-ci"]
      }
    }

secret_hash is preferred for production (sha256 hex of the raw secret).
Plaintext secret is accepted for local dev.
"""

from __future__ import annotations

import hashlib
import hmac
import json

from concilium.infrastructure.settings import get_auth


def validate_client(client_id: str, client_secret: str) -> list[str] | None:
    """Return roles for the client, or None if credentials are invalid."""
    store = _load_store()
    entry = store.get(client_id)
    if entry is None:
        return None

    if not _verify_secret(client_secret, entry):
        return None

    return list(entry.get("roles", []))


def _verify_secret(provided: str, entry: dict) -> bool:
    secret_hash: str = entry.get("secret_hash", "")
    if secret_hash:
        expected = "sha256:" + hashlib.sha256(provided.encode()).hexdigest()
        return hmac.compare_digest(expected, secret_hash)
    plaintext: str = entry.get("secret", "")
    if plaintext:
        return hmac.compare_digest(provided, plaintext)
    return False


def _load_store() -> dict:
    raw = get_auth().clients_json.strip()
    if not raw:
        return {}
    return json.loads(raw)
