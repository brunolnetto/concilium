"""FastAPI helpers de contexto — ADR-099.

Acesso aos claims JWT do request atual para routes que precisam do sub/roles
além das verificações de permissão (que são feitas via @permission decorator).
"""

from __future__ import annotations

from typing import Any

from fastapi import Request


def get_current_claims(request: Request) -> dict[str, Any]:
    """Retorna os JWT claims do request (populados pelo JWTAuthMiddleware).

    Retorna dict vazio quando AUTH_ENABLED=0 (dev mode).
    """
    return getattr(request.state, "jwt_claims", {})


def get_current_subject(request: Request) -> str | None:
    """Retorna o 'sub' (client_id) do token atual, ou None em dev mode."""
    return get_current_claims(request).get("sub")
