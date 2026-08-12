"""Rate limiting para MCP tools — ADR-098.

Implementação em memória (contador de janela deslizante por project_id).
Thread-safe para o modelo de execução do FastMCP (asyncio single-thread).
Limites configuráveis por env var sem redeploy.

Uso:
    @server.tool()
    @mcp_rate_limit(calls=10, period_s=60)
    def minha_tool(project_id: str, ...) -> dict:
        ...
"""

from __future__ import annotations

import inspect
from collections import defaultdict
from functools import wraps
from time import monotonic
from typing import Any

from concilium.infrastructure.settings import get_mcp

# project_id → lista de timestamps das chamadas recentes
_counters: dict[str, list[float]] = defaultdict(list)

# Lidos do singleton — ajustáveis por env sem redeploy (alterar e _reset_all())
_mcp = get_mcp()
_PIPELINE_CALLS = _mcp.rate_limit_calls
_PIPELINE_PERIOD = _mcp.rate_limit_period_s


def mcp_rate_limit(calls: int = _PIPELINE_CALLS, period_s: int = _PIPELINE_PERIOD):
    """Decorator de rate limit para tools MCP.

    Janela deslizante por `project_id` (ou "global" se ausente).
    Levanta RuntimeError com mensagem descritiva quando o limite é atingido —
    o FastMCP retorna essa mensagem ao agente LLM como texto de erro.
    """

    def decorator(tool_fn: Any) -> Any:
        def _check_and_register(kwargs: dict[str, Any]) -> None:
            project_id = kwargs.get("project_id") or "global"
            key = f"{tool_fn.__name__}:{project_id}"
            now = monotonic()

            # Remove timestamps fora da janela
            _counters[key] = [t for t in _counters[key] if now - t < period_s]

            if len(_counters[key]) >= calls:
                wait_s = round(period_s - (now - _counters[key][0]))
                raise RuntimeError(
                    f"Rate limit atingido para '{tool_fn.__name__}' "
                    f"(projeto '{project_id}'): máximo {calls} chamadas por {period_s}s. "
                    f"Aguarde ~{wait_s}s e tente novamente."
                )

            _counters[key].append(now)

        # 2026-08-12: mesmo bug de #148 (ver permission_guard.permission) — um
        # wrapper síncrono em volta de uma tool_fn `async def` devolve a coroutine
        # sem executá-la, porque o FastMCP decide se dá `await` inspecionando
        # ESTE wrapper, não a função original. Achado ao investigar as 8 tools de
        # escrita convertidas a async no PR #159: com @mcp_rate_limit() logo abaixo
        # de @permission(...), o wrapper síncrono daqui quebrava a cadeia antes do
        # fix async-aware do permission() ter chance de ver uma função async.
        if inspect.iscoroutinefunction(tool_fn):

            @wraps(tool_fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                _check_and_register(kwargs)
                return await tool_fn(*args, **kwargs)

            return async_wrapper

        @wraps(tool_fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            _check_and_register(kwargs)
            return tool_fn(*args, **kwargs)

        return wrapper

    return decorator
