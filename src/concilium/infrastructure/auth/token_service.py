"""JWT emission and validation using RS256 (PyJWT) — ADR-094 / ADR-099.

ADR-099: tokens agora carregam 'roles' em vez de 'scopes'.
Compatibilidade: tokens antigos com 'scopes' continuam funcionando
via mapeamento legado em roles_from_token() (permission_guard.py).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt  # PyJWT

from .jwt_config import load_key_pair

_ISSUER = "concilium-auth"
_ORG = "mendesloboconstrucao"
_ALGORITHM = "RS256"

TTL_INTERACTIVE = timedelta(hours=8)  # Claude Desktop, engenheiros, agentes LLM
TTL_CI = timedelta(days=90)  # service accounts CI/calibração


def issue_token(
    subject: str,
    roles: list[str],
    ttl: timedelta = TTL_INTERACTIVE,
) -> str:
    """Sign and return a JWT RS256 with 'roles' claim (ADR-099)."""
    keys = load_key_pair()
    now = datetime.now(UTC)
    payload: dict = {
        "iss": _ISSUER,
        "sub": subject,
        "org": _ORG,
        "roles": roles,
        "iat": now,
        "exp": now + ttl,
    }
    return jwt.encode(payload, keys.private_pem, algorithm=_ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT. Returns claims dict with 'roles'."""
    keys = load_key_pair()
    claims = jwt.decode(
        token,
        keys.public_pem,
        algorithms=[_ALGORITHM],
        options={"require": ["sub", "roles", "exp", "iss"]},
        issuer=_ISSUER,
    )
    return claims
