"""Rate limiting — ADR-098.

Chave por JWT sub (por usuário) ou IP como fallback.
Backend: MemoryStorage (ACI single-instance). Migrar para Redis via
CONCILIUM__RATE_LIMIT_STORAGE_URI quando houver múltiplas instâncias.

Limites:
  - Global (circuit breaker):     200/minute  por usuário  [SlowAPIMiddleware default]
  - Pipeline execution:            10/minute  por usuário  [decorador em runs.py]
  - Auth token (anti-brute-force):  5/minute  por IP       [decorador em auth.py]
"""

from __future__ import annotations

from fastapi import Request, Response
from slowapi import Limiter, _rate_limit_exceeded_handler as _slowapi_429
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from concilium.infrastructure.settings import get_telemetry


def _rate_limit_key(request: Request) -> str:
    """Chave de rate limit: JWT sub (por usuário) ou IP como fallback.

    Usar sub em vez de IP evita punição coletiva de usuários atrás de NAT corporativo.
    Fallback para IP preserva proteção mesmo quando o token é inválido ou ausente.
    """
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        try:
            from concilium.infrastructure.auth.token_service import decode_token
            payload = decode_token(auth.removeprefix("Bearer "))
            if sub := payload.get("sub"):
                return f"user:{sub}"
        except Exception:
            pass
    return f"ip:{get_remote_address(request)}"


_tel = get_telemetry()

limiter = Limiter(
    key_func=_rate_limit_key,
    default_limits=[_tel.rate_limit_global],
    storage_uri=_tel.rate_limit_storage_uri,
    headers_enabled=True,   # injeta X-RateLimit-* e Retry-After automaticamente
)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> Response:
    """Handler 429: emite métrica OTEL e delega resposta ao SlowAPI padrão."""
    try:
        from concilium.infrastructure.telemetry import record_rate_limit_exceeded
        record_rate_limit_exceeded(request.url.path)
    except Exception:
        pass
    return _slowapi_429(request, exc)
