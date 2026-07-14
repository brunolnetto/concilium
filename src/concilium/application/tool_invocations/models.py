"""Modelo de ToolInvocation — unidade de auditoria por chamada MCP (ADR-118).

Privacidade (consistente com ADR-095 D5):
  Apenas metadados operacionais são armazenados.
  Nenhum dado de projeto (quantitativos, preços, nomes de atividades)
  é gravado — apenas as chaves dos parâmetros (input_keys), não seus valores.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ToolInvocation:
    """Registro imutável de uma invocação de tool MCP.

    Armazenado pelo ToolInvocationRepository ao término da execução.
    Status possíveis: "success" | "failed".
    """

    id: str
    tool_name: str
    input_keys: list[str]
    user_id: str | None
    tenant_id: str | None
    status: str
    started_at: str
    finished_at: str
    error_type: str | None = field(default=None)
    device_id: str | None = field(default=None)  # ADR-138: dispositivo que fez a chamada
    mcp_session_id: str | None = field(default=None)  # ADR-138: sessão MCP (Mcp-Session-Id)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tool_name": self.tool_name,
            "input_keys": self.input_keys,
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error_type": self.error_type,
            "device_id": self.device_id,
            "mcp_session_id": self.mcp_session_id,
        }

    @staticmethod
    def from_dict(d: dict) -> ToolInvocation:
        return ToolInvocation(
            id=d["id"],
            tool_name=d["tool_name"],
            input_keys=d.get("input_keys", []),
            user_id=d.get("user_id"),
            tenant_id=d.get("tenant_id"),
            status=d["status"],
            started_at=d["started_at"],
            finished_at=d["finished_at"],
            error_type=d.get("error_type"),
            device_id=d.get("device_id"),
            mcp_session_id=d.get("mcp_session_id"),
        )
