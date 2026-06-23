"""ASGI middleware de autenticação JWT para o MCP server HTTP (ADR-099).

Extrai o Bearer token do header Authorization, decodifica o JWT e seta
_current_roles contextvar ANTES de cada invocação de tool MCP.

Por que ASGI puro (não BaseHTTPMiddleware):
  BaseHTTPMiddleware usa anyio.create_task_group() internamente, o que cria
  um novo contexto de task e torna os contextvars invisíveis ao handler.
  O middleware ASGI puro executa na mesma task — o contextvar é propagado.

Integrado em server.py via _patch_mcp_with_auth() que envolve
streamable_http_app() e sse_app() com este middleware.
"""

from __future__ import annotations

from typing import Any

from concilium.infrastructure.settings import get_auth

# ADR-121 D4/D6: OTel propagation + baggage — importações lazy-safe
try:
    from opentelemetry import propagate
    from opentelemetry.baggage import set_baggage
    from opentelemetry.context import attach as context_attach, detach as context_detach
    _OTEL_AVAILABLE = True
except ImportError:  # pragma: no cover
    _OTEL_AVAILABLE = False
    propagate = None  # type: ignore[assignment]
    set_baggage = None  # type: ignore[assignment]
    context_attach = lambda ctx: None  # noqa: E731
    context_detach = lambda tok: None  # noqa: E731


class McpAuthMiddleware:
    """ASGI middleware: valida JWT e seta _current_roles antes de cada tool call."""

    def __init__(self, app: Any) -> None:
        self._app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        # Extrai todos os headers como dict str→str para OTel propagation
        raw_headers = scope.get("headers", [])
        headers = {k.lower(): v for k, v in raw_headers}
        headers_str: dict[str, str] = {
            k.decode("latin-1"): v.decode("latin-1")
            for k, v in raw_headers
        }

        auth: str = headers.get(b"authorization", b"").decode("latin-1")

        token_var = None
        auth_ctx_tokens = None
        otel_ctx_token = None  # ADR-121 D4: token de contexto OTel para detach

        # ADR-121 D4: extrai traceparent/tracestate e estabelece contexto OTel
        if _OTEL_AVAILABLE and propagate is not None:
            try:
                ctx = propagate.extract(headers_str)
                otel_ctx_token = context_attach(ctx)
            except Exception:
                pass  # propagação OTel é best-effort

        if auth.startswith("Bearer "):
            raw_token = auth[7:].strip()
            try:
                from concilium.infrastructure.auth.permission_guard import (
                    _current_roles,
                    reset_auth_context,
                    roles_from_token,
                    set_auth_context,
                    set_roles,
                )
                from concilium.infrastructure.auth.token_service import decode_token

                claims = decode_token(raw_token)
                token_var = set_roles(roles_from_token(claims))
                # ADR-118: propaga user_id (sub) e tenant_id (tid) para auditoria
                auth_ctx_tokens = set_auth_context(
                    claims.get("sub"),
                    claims.get("tid") or claims.get("tenant_id"),
                )

                # ADR-121 D6: injeta tenant_id e user_id como W3C Baggage
                if _OTEL_AVAILABLE and set_baggage is not None:
                    try:
                        tenant_id = claims.get("tid") or claims.get("tenant_id")
                        user_id = claims.get("sub")
                        baggage_ctx = None
                        if tenant_id:
                            baggage_ctx = set_baggage("tenant.id", tenant_id, baggage_ctx)
                        if user_id:
                            baggage_ctx = set_baggage("user.id", user_id, baggage_ctx)
                        if baggage_ctx is not None:
                            # attach devolve token para detach no finally
                            otel_ctx_token = context_attach(baggage_ctx)
                    except Exception:
                        pass  # baggage é best-effort

            except Exception as exc:
                if _auth_enabled():
                    await _send_json_response(
                        send,
                        401,
                        {"detail": f"Token MCP inválido: {exc}"},
                        headers=[(b"www-authenticate", b"Bearer")],
                    )
                    return
                # AUTH_ENABLED=0 → ignorar erros de token (modo dev)
        elif _auth_enabled():
            await _send_json_response(
                send,
                401,
                {"detail": "Authorization: Bearer <token> ausente."},
                headers=[(b"www-authenticate", b"Bearer")],
            )
            return

        try:
            await self._app(scope, receive, send)
        finally:
            if token_var is not None:
                from concilium.infrastructure.auth.permission_guard import _current_roles

                _current_roles.reset(token_var)
            if auth_ctx_tokens is not None:
                from concilium.infrastructure.auth.permission_guard import reset_auth_context

                reset_auth_context(auth_ctx_tokens)
            # ADR-121 D4/D6: desanexa contexto OTel (traceparent + baggage)
            if otel_ctx_token is not None:
                context_detach(otel_ctx_token)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _auth_enabled() -> bool:
    return get_auth().enabled


async def _send_json_response(
    send: Any,
    status: int,
    body: dict,
    headers: list | None = None,
) -> None:
    import json as _json

    encoded = _json.dumps(body, ensure_ascii=False).encode()
    resp_headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(encoded)).encode()),
        *(headers or []),
    ]
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": resp_headers,
        }
    )
    await send(
        {
            "type": "http.response.body",
            "body": encoded,
            "more_body": False,
        }
    )
