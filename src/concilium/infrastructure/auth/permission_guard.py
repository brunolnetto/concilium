"""RBAC — Roles e Permissões (ADR-099).

Permissões são derivadas dos roles em runtime — não ficam no JWT.
Isso permite alterar ROLE_PERMISSIONS sem revogar tokens existentes.

Roles disponíveis:
  viewer      → leitura de projetos e artefatos (sem dados financeiros)
  operator    → viewer + criar + executar pipeline + dados financeiros
  engineer    → operator + aprovar versões + escrever catálogo
  admin       → engineer + gerir usuários e sistema
  service-ci  → criar + executar pipeline (sem financeiro, sem aprovação)
  auditor     → leitura + dados financeiros (sem executar nada)

Decorators disponíveis (funcionam em FastAPI routes e MCP tools):

  @permission("project:run")
  def minha_funcao(request, ...): ...

  @roles("operator", "engineer")
  def minha_funcao(request, ...): ...
"""

from __future__ import annotations

import contextvars
from functools import wraps
from typing import Any

from concilium.infrastructure.settings import get_auth

# ── Permissões granulares ─────────────────────────────────────────────────────

PROJECT_READ = "project:read"
PROJECT_CREATE = "project:create"
PROJECT_RUN = "project:run"
PROJECT_APPROVE = "project:approve"
ARTIFACTS_READ = "artifacts:read"
ARTIFACTS_DOWNLOAD = "artifacts:download"
CATALOG_READ = "catalog:read"
CATALOG_WRITE = "catalog:write"
FINANCIALS_READ = "financials:read"
AUTH_MANAGE = "auth:manage"
SYSTEM_READ = "system:read"

# ── Mapeamento role → permissões ──────────────────────────────────────────────

_VIEWER = frozenset({PROJECT_READ, ARTIFACTS_READ, CATALOG_READ})

_OPERATOR = _VIEWER | frozenset(
    {
        PROJECT_CREATE,
        PROJECT_RUN,
        ARTIFACTS_DOWNLOAD,
        FINANCIALS_READ,
    }
)

_ENGINEER = _OPERATOR | frozenset({PROJECT_APPROVE, CATALOG_WRITE})

_ADMIN = _ENGINEER | frozenset({AUTH_MANAGE, SYSTEM_READ})

_SERVICE_CI = frozenset({PROJECT_CREATE, PROJECT_RUN})

_AUDITOR = frozenset(
    {
        PROJECT_READ,
        ARTIFACTS_READ,
        ARTIFACTS_DOWNLOAD,
        FINANCIALS_READ,
    }
)

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "viewer": _VIEWER,
    "operator": _OPERATOR,
    "engineer": _ENGINEER,
    "admin": _ADMIN,
    "service-ci": _SERVICE_CI,
    "auditor": _AUDITOR,
}

VALID_ROLES: frozenset[str] = frozenset(ROLE_PERMISSIONS.keys())

# ── Mapeamento legado: scopes ADR-094 → roles ADR-099 ─────────────────────────

LEGACY_SCOPE_TO_ROLE: dict[str, str] = {
    "mcp:read": "viewer",
    "mcp:write": "engineer",
    "pipeline:run": "operator",
}

# ── Helpers ───────────────────────────────────────────────────────────────────


def get_permissions(roles: list[str]) -> frozenset[str]:
    """Computa permissões efetivas para uma lista de roles."""
    result: set[str] = set()
    for role in roles:
        result |= ROLE_PERMISSIONS.get(role, frozenset())
    return frozenset(result)


def roles_from_token(claims: dict) -> list[str]:
    """Extrai roles do token JWT.

    Prioridade:
      1. Claim 'roles' (novo formato ADR-099)
      2. Claim 'scopes' (legado ADR-094) → mapeado para roles equivalentes
    """
    if "roles" in claims:
        return list(claims["roles"])
    # Legado: scopes → roles
    scopes = claims.get("scopes") or []
    roles: list[str] = []
    for scope in scopes:
        role = LEGACY_SCOPE_TO_ROLE.get(scope)
        if role and role not in roles:
            roles.append(role)
    return roles or ["viewer"]  # fallback mais seguro: viewer, não nada


def require_permission(perm: str, token_roles: list[str]) -> None:
    """Levanta PermissionError se os roles não conferem a permissão necessária.

    No-op quando AUTH_ENABLED=0 (desenvolvimento local).
    """
    if not _auth_enabled():
        return
    if perm not in get_permissions(token_roles):
        raise PermissionError(
            f"Permissão '{perm}' necessária. "
            f"Roles do token: {token_roles}. "
            "Solicite ao admin o role adequado (ex: 'operator' para executar pipelines)."
        )


def _auth_enabled() -> bool:
    return get_auth().enabled


# ── Mapeamento MCP tool → permissão (ADR-117) ────────────────────────────────
# Não é mais mantido à mão: a fonte de verdade são as tags @permission nas tools.
# Este dict é um CACHE populado em runtime por build_tool_permission_map(server)
# (chamado em patch_mcp_auth_permissions), para consumidores name-based.
TOOL_PERMISSIONS: dict[str, str] = {}


# ── Contextvar para MCP tools (sem request HTTP) ──────────────────────────────

_current_roles: contextvars.ContextVar[frozenset[str]] = contextvars.ContextVar(
    "_rbac_current_roles", default=frozenset()
)


def set_roles(token_roles: list[str]) -> contextvars.Token:
    """Define os roles do request MCP atual. Chamar antes de invocar a tool."""
    return _current_roles.set(frozenset(token_roles))


def _get_roles_from_context(kwargs: dict[str, Any]) -> list[str]:
    """Extrai roles do contexto atual.

    FastAPI route: lê request.state.jwt_claims (injetado pelo JWTAuthMiddleware)
    MCP tool:      lê contextvar _current_roles (setado pelo adaptador HTTP)
    """
    request = kwargs.get("request")
    if request is not None:
        claims = getattr(request.state, "jwt_claims", {})
        return roles_from_token(claims)
    return list(_current_roles.get())


# ── Decorators ────────────────────────────────────────────────────────────────


def permission(perm: str):
    """Decorator: verifica permissão RBAC antes de executar a função.

    Funciona em FastAPI routes (lê request.state.jwt_claims)
    e em MCP tools (lê _current_roles contextvar).

    Uso:
        # FastAPI
        @router.post("/runs")
        @limiter.limit("10/minute")
        @permission("project:run")
        def run_project(request: Request, ...): ...

        # MCP tool
        @server.tool()
        @permission("project:run")
        def avancar_pipeline(...): ...
    """

    def decorator(fn: Any) -> Any:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if _auth_enabled():
                token_roles = _get_roles_from_context(kwargs)
                if perm not in get_permissions(token_roles):
                    raise PermissionError(
                        f"Permissão '{perm}' necessária. "
                        f"Roles do token: {token_roles or ['(nenhum)']!r}. "
                        "Solicite ao admin o role adequado."
                    )
            return fn(*args, **kwargs)

        # ADR-117: tag introspectável — fonte única da permissão da tool,
        # lida por patch_mcp_auth_permissions e pelo teste de governança.
        wrapper._required_permission = perm  # type: ignore[attr-defined]
        return wrapper

    return decorator


def roles(*required_roles: str):
    """Decorator: verifica se o token tem pelo menos um dos roles especificados.

    Mais permissivo que @permission — basta ter UM dos roles listados.

    Uso:
        @router.post("/approve")
        @roles("engineer", "admin")
        def approve_version(request: Request, ...): ...
    """

    def decorator(fn: Any) -> Any:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if _auth_enabled():
                token_roles = _get_roles_from_context(kwargs)
                if not any(r in token_roles for r in required_roles):
                    raise PermissionError(
                        f"Roles necessários: {list(required_roles)}. Roles do token: {token_roles or ['(nenhum)']!r}."
                    )
            return fn(*args, **kwargs)

        return wrapper

    return decorator


# ── Enforcement centralizado para MCP tools ────────────────────────────────────

import logging as _logging

_guard_log = _logging.getLogger(__name__)


# ADR-117: fonte da permissão é a tag _required_permission posta por @permission.
# Tool sem tag → fail-closed (exige AUTH_MANAGE, só admin) + warning. O teste de
# governança (fail-closed estático) impede que isso aconteça em produção.
_FAILCLOSED_TOOL_PERMISSION = AUTH_MANAGE


def _tool_required_permission(tool: Any) -> str | None:
    """Lê a permissão declarada via @permission (tag _required_permission)."""
    fn = getattr(tool, "fn", None)
    return getattr(fn, "_required_permission", None)


def validate_tool_coverage(server: Any) -> list[str]:
    """Retorna tools registradas SEM tag @permission (ADR-117 — fail-closed).

    Chamado em build_server() para auditoria. Tools sem tag são logadas como
    erro de governança (deveriam ter @permission inline).
    """
    try:
        tools = server._tool_manager._tools
    except AttributeError:
        return []
    missing = [name for name, tool in tools.items() if _tool_required_permission(tool) is None]
    if missing:
        _guard_log.error(
            "RBAC: %d tool(s) sem @permission inline: %s — fail-closed (exigirá %s).",
            len(missing),
            missing,
            _FAILCLOSED_TOOL_PERMISSION,
        )
    return missing


def build_tool_permission_map(server: Any) -> dict[str, str]:
    """Deriva a tabela tool→permissão por introspecção (ADR-117 D5).

    Substitui o antigo dict TOOL_PERMISSIONS mantido à mão — agora a tabela é
    reconstruída a partir das tags @permission. Use para auditoria/relatório.
    """
    try:
        tools = server._tool_manager._tools
    except AttributeError:
        return {}
    mapping = {
        name: (_tool_required_permission(tool) or _FAILCLOSED_TOOL_PERMISSION)
        for name, tool in tools.items()
    }
    # Atualiza o cache módulo-level para consumidores name-based (ex.: scope_guard).
    TOOL_PERMISSIONS.clear()
    TOOL_PERMISSIONS.update(mapping)
    return mapping


def patch_mcp_auth_permissions(server: Any) -> None:
    """Defesa em profundidade: envolve cada tool com checagem pela tag _required_permission.

    A fonte da permissão é a tag posta por @permission (ADR-117). Tools sem tag
    recebem _FAILCLOSED_TOOL_PERMISSION (admin) — o teste de governança garante que
    isso não ocorra. O decorator inline já checa; este wrapper cobre o transporte HTTP.

    Chamado em build_server() após registrar todas as tools.
    """
    try:
        tools = server._tool_manager._tools
    except AttributeError:
        _guard_log.warning("patch_mcp_auth_permissions: servidor sem _tool_manager._tools — skipping")
        return

    # Popula o cache name-based (TOOL_PERMISSIONS) a partir das tags antes do re-wrap.
    build_tool_permission_map(server)

    for _tool_name, tool in tools.items():
        if not (hasattr(tool, "fn") and callable(tool.fn)):
            continue
        original_fn = tool.fn
        required_perm = getattr(original_fn, "_required_permission", None) or _FAILCLOSED_TOOL_PERMISSION

        def _make_wrapper(fn: Any, perm: str) -> Any:
            @wraps(fn)
            def _auth_wrapper(*args: Any, **kwargs: Any) -> Any:
                if _auth_enabled():
                    token_roles = list(_current_roles.get())
                    if perm not in get_permissions(token_roles):
                        raise PermissionError(
                            f"MCP tool '{fn.__name__}' requer '{perm}'. "
                            f"Roles do token: {token_roles or ['(nenhum)']}. "
                            "Solicite ao admin o role adequado."
                        )
                return fn(*args, **kwargs)

            _auth_wrapper._required_permission = perm  # type: ignore[attr-defined]  # propaga a tag
            return _auth_wrapper

        tool.fn = _make_wrapper(original_fn, required_perm)
