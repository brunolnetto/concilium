"""JWT validation middleware for FastAPI — ADR-094 Fase 4 (fallback interno).

Activated when CONCILIUM__AUTH_ENABLED=1. Otherwise a no-op (local/dev mode).
Primary enforcement is at the Azure Application Gateway (Fase 3); this is the
defense-in-depth layer that protects the container if the gateway is bypassed.

Skipped paths: /auth/token, /health, /, /swagger, /openapi.json, /redoc
"""

from __future__ import annotations

from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from concilium.infrastructure.settings import get_auth

_SKIP_PATHS: frozenset[str] = frozenset({
    "/",
    "/health",
    "/auth/token",
    "/auth/device/activate",   # ADR-099: troca device code por refresh token
    "/auth/token/refresh",     # ADR-099: troca refresh token por access token
    "/swagger",
    "/openapi.json",
    "/redoc",
})


class JWTAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not _auth_enabled() or request.url.path in _SKIP_PATHS:
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return _unauthorized("Authorization header ausente ou inválido.")

        token = auth_header[len("Bearer "):].strip()
        try:
            from concilium.infrastructure.auth.token_service import decode_token
            claims = decode_token(token)
        except Exception as exc:
            return _unauthorized(f"Token inválido: {exc}")

        request.state.jwt_claims = claims
        return await call_next(request)


def _auth_enabled() -> bool:
    return get_auth().enabled


def _unauthorized(detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"detail": detail},
        headers={"WWW-Authenticate": "Bearer"},
    )
