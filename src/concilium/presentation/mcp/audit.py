"""Patcher de auditoria de invocações MCP (ADR-118).

Envolve todas as tools MCP registradas com um decorator que:
  1. Captura user_id / tenant_id do contexto de execução atual
  2. Mede duração da chamada
  3. Registra ToolInvocation ao término (sucesso ou falha)

Privacidade (ADR-095 D5):
  Apenas input_keys (nomes dos parâmetros) são registrados, nunca os valores.
  error_type registra a classe da exceção, nunca a mensagem (pode conter PII).

Posição no pipeline de patches (server.py):
  patch_fastmcp_server         — OTEL tracing
  patch_mcp_auth_permissions   — RBAC
  patch_fastmcp_server_with_audit  ← este módulo
"""

from __future__ import annotations

from datetime import UTC
from functools import wraps
from typing import Any


def patch_fastmcp_server_with_audit(server: Any) -> None:
    """Envolve todas as tools MCP com registro de ToolInvocation (best-effort).

    Acessa server._tool_manager._tools (API interna do FastMCP).
    Se a estrutura interna mudar, o patch é silenciosamente ignorado.
    """
    try:
        tools = server._tool_manager._tools
        for tool in tools.values():
            if hasattr(tool, "fn") and callable(tool.fn):
                tool.fn = _with_audit(tool.fn)
    except Exception:
        pass


def _with_audit(tool_fn: Any) -> Any:
    """Decora uma função de tool MCP com gravação de ToolInvocation."""

    @wraps(tool_fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        import uuid
        from datetime import datetime

        from concilium.infrastructure.auth.permission_guard import (
            get_current_device_id,
            get_current_mcp_session_id,
            get_current_tenant_id,
            get_current_user_id,
        )

        invocation_id = f"ti-{uuid.uuid4().hex[:12]}"
        started_at = datetime.now(UTC).isoformat()
        input_keys = list(kwargs.keys())
        user_id = get_current_user_id()
        tenant_id = get_current_tenant_id()
        device_id = get_current_device_id()
        mcp_session_id = get_current_mcp_session_id()

        status = "success"
        error_type: str | None = None
        try:
            result = tool_fn(*args, **kwargs)
            return result
        except Exception as exc:
            status = "failed"
            error_type = type(exc).__name__
            raise
        finally:
            finished_at = datetime.now(UTC).isoformat()
            try:
                _record(
                    invocation_id=invocation_id,
                    tool_name=tool_fn.__name__,
                    input_keys=input_keys,
                    user_id=user_id,
                    tenant_id=tenant_id,
                    status=status,
                    started_at=started_at,
                    finished_at=finished_at,
                    error_type=error_type,
                    device_id=device_id,
                    mcp_session_id=mcp_session_id,
                )
            except Exception:
                pass

    return wrapper


def _record(
    *,
    invocation_id: str,
    tool_name: str,
    input_keys: list[str],
    user_id: str | None,
    tenant_id: str | None,
    status: str,
    started_at: str,
    finished_at: str,
    error_type: str | None,
    device_id: str | None = None,
    mcp_session_id: str | None = None,
) -> None:
    """Persiste o registro no repositório (best-effort — nunca levanta)."""
    try:
        from concilium.application.tool_invocations.models import ToolInvocation
        from concilium.application.tool_invocations.repository import get_tool_invocation_repository

        inv = ToolInvocation(
            id=invocation_id,
            tool_name=tool_name,
            input_keys=input_keys,
            user_id=user_id,
            tenant_id=tenant_id,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            error_type=error_type,
            device_id=device_id,
            mcp_session_id=mcp_session_id,
        )
        get_tool_invocation_repository().append(inv)
    except Exception:
        pass
