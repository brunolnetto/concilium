"""MCP tool para visibilidade de usuários entre roles (ADR-143)."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from concilium.infrastructure.auth.permission_guard import permission


def register(server: FastMCP) -> None:
    """Registra a ferramenta de visibilidade de usuários no servidor MCP."""

    @server.tool()
    @permission("auth:list-visible")
    def listar_usuarios_visiveis() -> dict[str, Any]:
        """Lista outros usuários visíveis para os roles do usuário autenticado.

        Visibilidade escopada por role (ADR-143 D2) — não é tudo-ou-nada: cada
        role vê um subconjunto de roles definido em `ROLE_VISIBILITY`. Nunca
        inclui dispositivos, senha/hash ou notas administrativas (D3) — apenas
        client_id, email, roles e active. Nunca inclui o próprio chamador.

        Cada consulta é registrada para o digest opcional do usuário consultado
        (D7/D8) — nunca há notificação atômica por consulta.
        """
        from concilium.application.services.visibility_service import list_visible_users
        from concilium.infrastructure.auth.permission_guard import _current_roles, get_current_user_id

        caller_id = get_current_user_id()
        caller_roles = list(_current_roles.get())

        usuarios = list_visible_users(caller_id, caller_roles)
        return {
            "status": "ok",
            "total": len(usuarios),
            "usuarios": usuarios,
        }
