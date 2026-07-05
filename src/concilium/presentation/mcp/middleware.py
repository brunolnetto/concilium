"""ASGI middleware de autenticação JWT para o MCP server HTTP (ADR-099).

Extrai o Bearer token do header Authorization, decodifica o JWT e seta
_current_roles contextvar ANTES de cada invocação de tool MCP.

Tools públicos (não requerem auth):
  - ativar_dispositivo: bootstrap de novo dispositivo
  - renovar_token: obter access_token de refresh_token

Por que ASGI puro (não BaseHTTPMiddleware):
  BaseHTTPMiddleware usa anyio.create_task_group() internamente, o que cria
  um novo contexto de task e torna os contextvars invisíveis ao handler.
  O middleware ASGI puro executa na mesma task — o contextvar é propagado.

Integrado em server.py via _patch_mcp_with_auth() que envolve
streamable_http_app() e sse_app() com este middleware.
"""

from __future__ import annotations

import json
from types import ModuleType
from typing import TYPE_CHECKING, Any

from concilium.infrastructure.settings import get_auth

if TYPE_CHECKING:
    from collections.abc import Callable

    from opentelemetry.context import Context

# Tools que não requerem autenticação (bootstrap)
_PUBLIC_TOOLS: frozenset[str] = frozenset({"ativar_dispositivo", "renovar_token"})

# Métodos de protocolo MCP que não requerem autenticação.
# notifications/initialized é obrigatório no handshake streamable-http: sem ele o
# FastMCP não processa tools/call — precisa passar antes de existir qualquer token.
_PUBLIC_METHODS: frozenset[str] = frozenset({"initialize", "ping", "notifications/initialized"})

# ADR-121 D4/D6: OTel propagation + baggage — importações lazy-safe
if TYPE_CHECKING:
    _SetBaggageFn = Callable[[str, object, "Context | None"], "Context"]


def _load_otel() -> tuple[ModuleType | None, _SetBaggageFn | None, bool]:
    try:
        from opentelemetry import propagate as _propagate
        from opentelemetry.baggage import set_baggage as _set_baggage

        return _propagate, _set_baggage, True
    except ImportError:  # pragma: no cover
        return None, None, False


propagate, set_baggage, _OTEL_AVAILABLE = _load_otel()

if _OTEL_AVAILABLE:
    from opentelemetry.context import attach as context_attach
    from opentelemetry.context import detach as context_detach
else:  # pragma: no cover

    def context_attach(context: Any) -> Any:  # noqa: ARG001
        """Fallback no-op quando opentelemetry não está instalado."""
        return None

    def context_detach(token: Any) -> None:  # noqa: ARG001
        """Fallback no-op quando opentelemetry não está instalado."""


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
        headers_str: dict[str, str] = {k.decode("latin-1"): v.decode("latin-1") for k, v in raw_headers}

        # Verifica se é uma chamada de tool público (não requer auth)
        is_public_tool = await _is_public_tool_call(scope, receive)

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
                if _auth_enabled() and not is_public_tool:
                    await _send_json_response(
                        send,
                        401,
                        {"detail": f"Token MCP inválido: {exc}"},
                        headers=[(b"www-authenticate", b"Bearer")],
                    )
                    return
                # AUTH_ENABLED=0 ou tool público → ignorar erros de token
        elif _auth_enabled() and not is_public_tool:
            await _send_json_response(
                send,
                401,
                {"detail": "Authorization: Bearer <token> ausente."},
                headers=[(b"www-authenticate", b"Bearer")],
            )
            return

        try:
            # Se lemos o body para detectar tool público, precisamos re-emitir
            if "_body" in scope:
                receive = _make_cached_receive(scope["_body"], receive)
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


def _make_cached_receive(body: bytes, original_receive: Any):
    """Cria um receive() que re-emite o body já lido pelo middleware.

    Chamadas seguintes DELEGAM ao receive original em vez de fabricar
    http.disconnect: o transporte streamable-http chama receive() enquanto
    streama a resposta SSE para detectar desconexão do cliente — um
    disconnect falso aborta o stream antes de qualquer evento ser enviado.
    """
    sent = False

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        # Bloqueia até o cliente desconectar de verdade (ou novo frame chegar).
        return await original_receive()

    return receive


async def _is_public_tool_call(scope: dict, receive: Any) -> bool:
    """Detecta se a requisição é uma chamada de tool público (não requer auth).

    Lê o corpo da requisição de forma não-destrutiva e verifica se é uma
    chamada de tool que está em _PUBLIC_TOOLS.

    NOTA: Esta função modifica o scope["_body"] para cachear o body lido.
    O ASGI app downstream deve ler de scope["_body"] em vez de receive().
    """
    # Cache do body para evitar múltiplas leituras
    if "_body" in scope:
        body_bytes = scope["_body"]
    else:
        # Lê o body completo
        body_bytes = b""
        while True:
            message = await receive()
            if message["type"] == "http.request":
                body_bytes += message.get("body", b"")
                if not message.get("more_body", False):
                    break
            elif message["type"] == "http.disconnect":
                return False

        # Cacheia para o app downstream
        scope["_body"] = body_bytes

    if not body_bytes:
        return False

    try:
        data = json.loads(body_bytes.decode("utf-8"))
        method = data.get("method", "")

        # Métodos de protocolo público (initialize, ping, notifications/initialized)
        if method in _PUBLIC_METHODS:
            return True

        # Tools públicos via tools/call
        if method == "tools/call":
            tool_name = data.get("params", {}).get("name", "")
            return tool_name in _PUBLIC_TOOLS
    except (json.JSONDecodeError, UnicodeDecodeError):
        pass

    return False


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
