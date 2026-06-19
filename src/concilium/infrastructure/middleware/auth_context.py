"""Contextvars de autenticação para rastreabilidade de origem — ADR-094 extensão.

Injeta user_id (sub do JWT), request_id (UUID por request) e source_ip
em contextvars acessíveis por toda a pilha dentro de uma requisição:
  - _JsonFormatter (ADR-111) inclui estes campos em cada log line
  - OTel spans recebem os atributos correspondentes
  - Logs de observabilidade (ADR-112) podem correlacionar por request_id

Uso:
    # Leitura em qualquer parte do código durante uma request:
    from concilium.infrastructure.middleware.auth_context import current_user_id
    uid = current_user_id.get()   # "" se fora de request context
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# ─────────────────────────────────────────────────────────────────────────────
# Contextvars públicos — default "" para código fora de request (CLI, testes)
# ─────────────────────────────────────────────────────────────────────────────

current_user_id: ContextVar[str] = ContextVar("current_user_id", default="")
current_request_id: ContextVar[str] = ContextVar("current_request_id", default="")
current_source_ip: ContextVar[str] = ContextVar("current_source_ip", default="")


# ─────────────────────────────────────────────────────────────────────────────
# Helper: decodifica token JWT sem lançar exceção
# ─────────────────────────────────────────────────────────────────────────────

def _try_decode_token(token: str) -> dict | None:
    """Decodifica JWT silenciosamente. Retorna claims ou None se inválido."""
    try:
        from concilium.infrastructure.auth.token_service import decode_token
        return decode_token(token)
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# AuthContextMiddleware
# ─────────────────────────────────────────────────────────────────────────────

class AuthContextMiddleware(BaseHTTPMiddleware):
    """Middleware ASGI que popula contextvars de rastreabilidade para cada request.

    Deve ser registrado ANTES do JWTAuthMiddleware em app.py para que o
    request_id já esteja disponível mesmo quando o JWT é inválido.

    Injeta:
      current_user_id   — sub do JWT (se Bearer token presente e válido)
      current_request_id — UUID v4 único por request
      current_source_ip  — IP do cliente (X-Forwarded-For ou client.host)
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        req_id = str(uuid.uuid4())
        user_id = ""
        source_ip = _extract_client_ip(request)

        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[len("Bearer "):].strip()
            claims = _try_decode_token(token)
            if claims:
                user_id = str(claims.get("sub") or "")

        t_user = current_user_id.set(user_id)
        t_req = current_request_id.set(req_id)
        t_ip = current_source_ip.set(source_ip)

        _set_otel_span_attributes(user_id, req_id)

        try:
            response = await call_next(request)
        finally:
            current_user_id.reset(t_user)
            current_request_id.reset(t_req)
            current_source_ip.reset(t_ip)

        response.headers["X-Request-ID"] = req_id
        return response


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _extract_client_ip(request: Request) -> str:
    """Extrai IP real do cliente respeitando X-Forwarded-For (proxy/gateway)."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    client = request.client
    return client.host if client else ""


def _set_otel_span_attributes(user_id: str, request_id: str) -> None:
    """Adiciona user.id e request.id ao span OTel ativo (best-effort)."""
    try:
        from opentelemetry import trace
        span = trace.get_current_span()
        if span and span.is_recording():
            if user_id:
                span.set_attribute("user.id", user_id)
            span.set_attribute("request.id", request_id)
    except Exception:
        pass
