"""Sumarização de sessões MCP por dispositivo (ADR-138).

Uma "sessão" aqui é uma agregação DERIVADA do audit log de ToolInvocation já
existente (ADR-118), agrupada por mcp_session_id — não é um registro próprio
persistido. Isso evita qualquer escrita adicional por chamada de tool: o
audit log já é gravado a cada invocação, então listar sessões é uma leitura +
agregação em memória sobre dados que já existem.

Invocações sem mcp_session_id (transportes sem Request HTTP, ex. stdio, ou
chamadas anteriores ao ADR-138) não entram em nenhuma sessão resumida.
"""

from __future__ import annotations

from dataclasses import dataclass

from concilium.application.tool_invocations.models import ToolInvocation


@dataclass(frozen=True)
class DeviceSession:
    """Resumo de uma sessão MCP (uma conexão streamable-http/SSE) de um dispositivo."""

    session_id: str
    device_id: str | None
    user_id: str | None
    tenant_id: str | None
    started_at: str
    last_activity_at: str
    call_count: int


def summarize_sessions(invocations: list[ToolInvocation]) -> list[DeviceSession]:
    """Agrupa invocações por mcp_session_id.

    Retorna mais recente primeiro (por last_activity_at). Invocações sem
    mcp_session_id são ignoradas — não há como agrupá-las em uma sessão.
    """
    groups: dict[str, list[ToolInvocation]] = {}
    for inv in invocations:
        if not inv.mcp_session_id:
            continue
        groups.setdefault(inv.mcp_session_id, []).append(inv)

    result = [_summarize_group(session_id, invs) for session_id, invs in groups.items()]
    return sorted(result, key=lambda s: s.last_activity_at, reverse=True)


def _summarize_group(session_id: str, invs: list[ToolInvocation]) -> DeviceSession:
    first = min(invs, key=lambda i: i.started_at)
    last = max(invs, key=lambda i: i.finished_at)
    return DeviceSession(
        session_id=session_id,
        device_id=first.device_id,
        user_id=first.user_id,
        tenant_id=first.tenant_id,
        started_at=first.started_at,
        last_activity_at=last.finished_at,
        call_count=len(invs),
    )


def sessions_for_device(device_id: str, limit: int = 1000) -> list[DeviceSession]:
    """Consulta o audit log e devolve sessões resumidas para um dispositivo."""
    from concilium.application.tool_invocations.repository import get_tool_invocation_repository

    invocations = get_tool_invocation_repository().list_by_device(device_id, limit=limit)
    return summarize_sessions(invocations)
