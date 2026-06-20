"""ADR-099 — Permission guard para ferramentas MCP.

Substitui o modelo de scopes planos (ADR-094) por roles/permissões granulares.
Mantém compatibilidade com tokens legados que usam 'scopes'.

Em modo local (CONCILIUM__AUTH_ENABLED=0): todas as verificações são no-op.
Em modo HTTP (Azure/produção): roles são extraídos do token JWT e propagados
via _current_roles contextvar antes de cada invocação de tool.

Uso nas tools MCP:

    from concilium.infrastructure.auth.permission_guard import permission

    @server.tool()
    @permission("project:run")
    def disparar_pipeline(...):
        ...  # lógica da ferramenta

O decorator @permission lê _current_roles (setado por set_roles() no
adaptador HTTP) e verifica via ROLE_PERMISSIONS.
"""

from __future__ import annotations

# Re-exporta os símbolos de permission_guard para compatibilidade
from concilium.infrastructure.auth.permission_guard import (
    ROLE_PERMISSIONS,
    TOOL_PERMISSIONS,
    _current_roles,
    get_permissions,
    permission,
    roles,
    roles_from_token,
    set_roles,
)
from concilium.infrastructure.settings import get_auth

__all__ = [
    "permission",
    "roles",
    "set_roles",
    "get_permissions",
    "roles_from_token",
    "ROLE_PERMISSIONS",
    "TOOL_PERMISSIONS",
    # Legado — mantido para compatibilidade com código existente
    "check_scope",
    "set_scopes",
    "SCOPES_REQUIRED",
]

# ── Tool permission checking ──────────────────────────────────────────────────


def check_scope(tool_name: str) -> None:
    """Verifica permissão necessária para executar a tool via TOOL_PERMISSIONS.

    No-op quando AUTH_ENABLED=0 (desenvolvimento local).
    """
    # Skip if auth is disabled
    if not get_auth().enabled:
        return

    # If tool doesn't require permission, allow
    perm = TOOL_PERMISSIONS.get(tool_name)
    if not perm:
        return

    # Check permission
    from concilium.infrastructure.auth.permission_guard import require_permission

    require_permission(perm, list(_current_roles.get()))


def set_scopes(scopes: list[str]) -> object:
    """Legado: mantido para compatibilidade de API, mas converte para roles."""
    from concilium.infrastructure.auth.permission_guard import LEGACY_SCOPE_TO_ROLE

    mapped_roles = list({LEGACY_SCOPE_TO_ROLE.get(s, "operator") for s in scopes})
    return set_roles(mapped_roles)


# Legado — SCOPES_REQUIRED foi substituído por TOOL_PERMISSIONS
SCOPES_REQUIRED: dict = {}
