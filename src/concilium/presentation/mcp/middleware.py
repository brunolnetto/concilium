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


class McpAuthMiddleware:
    """ASGI middleware: valida JWT e seta _current_roles antes de cada tool call."""

    def __init__(self, app: Any) -> None:
        self._app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        # Extrai Authorization header (bytes nos headers ASGI)
        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        auth: str = headers.get(b"authorization", b"").decode("latin-1")

        token_var = None

        if auth.startswith("Bearer "):
            raw_token = auth[7:].strip()
            try:
                from concilium.infrastructure.auth.permission_guard import (
                    _current_roles,
                    roles_from_token,
                    set_roles,
                )
                from concilium.infrastructure.auth.token_service import decode_token

                claims = decode_token(raw_token)
                token_var = set_roles(roles_from_token(claims))
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
