"""RBAC — Roles e Permissões (ADR-099).

Permissões são derivadas dos roles em runtime — não ficam no JWT.
Isso permite alterar ROLE_PERMISSIONS sem revogar tokens existentes.

Roles disponíveis:
  operator        → health check + leitura + criar projetos + executar pipeline + dados financeiros
  engineer        → operator + aprovar versões + escrever catálogo
  admin           → engineer + gerir usuários e sistema
  auditor         → health check + leitura + dados financeiros (sem executar nada)
  catalog-manager → health check + especialista em catálogo (sem acesso a projetos de clientes)

Decorators disponíveis (funcionam em FastAPI routes e MCP tools):

  @permission("project:run")
  def minha_funcao(request, ...): ...

  @roles("operator", "engineer")
  def minha_funcao(request, ...): ...
"""

from __future__ import annotations

import contextvars
import logging as _logging
from functools import wraps
from typing import Any

from concilium.infrastructure.settings import get_auth

# ── Permissões granulares ─────────────────────────────────────────────────────

PROJECT_READ = "project:read"
PROJECT_CREATE = "project:create"
PROJECT_RUN = "project:run"
PROJECT_APPROVE = "project:approve"
PROJECT_DELETE = "project:delete"  # ADR-126 D3: fecha lacuna — delete_project não tinha @permission
PROJECT_MANAGE_CONFIG = "project:manage-config"  # ADR-126 D3: idem para patch_project_config
PROJECT_MANAGE_OWNERSHIP = "project:manage-ownership"  # ADR-126 D3: iniciar transferência de ownership
ARTIFACTS_READ = "artifacts:read"
ARTIFACTS_DOWNLOAD = "artifacts:download"
CATALOG_READ = "catalog:read"
CATALOG_WRITE = "catalog:write"
CATALOG_VALIDATE = "catalog:validate"  # ADR-120 D1: health/plausibility/integrity checks
CATALOG_MERGE = "catalog:merge"  # ADR-120 D1: promoção rascunho→ativo (4 olhos)
FINANCIALS_READ = "financials:read"
AUTH_MANAGE = "auth:manage"
AUTH_SELF = "auth:self"  # ADR-123 F5: gestão de dispositivos próprios (self-service)
AUTH_PUBLIC = "auth:public"  # bootstrap sem token (ativar_dispositivo, renovar_token) — sempre permitido
SYSTEM_READ = "system:read"
HEALTH_READ = "health:read"  # health check do servidor — qualquer usuário autenticado com acesso operacional

# ── Mapeamento role → permissões ──────────────────────────────────────────────

_OPERATOR = frozenset(
    {
        HEALTH_READ,
        PROJECT_READ,
        PROJECT_CREATE,
        PROJECT_RUN,
        PROJECT_DELETE,  # ADR-126 D3: gate de role; ownership (require_owner_or_admin) restringe ao próprio projeto
        PROJECT_MANAGE_CONFIG,  # ADR-126 D3: idem
        PROJECT_MANAGE_OWNERSHIP,  # ADR-126 D3: quem pode criar projetos pode gerir ownership dos que possui
        ARTIFACTS_READ,
        ARTIFACTS_DOWNLOAD,
        CATALOG_READ,
        CATALOG_VALIDATE,  # ADR-120 D3: operator pode rodar health checks de catálogo
        FINANCIALS_READ,
        AUTH_SELF,  # ADR-123 F5: todos os roles têm self-service de dispositivos
    }
)

_ENGINEER = _OPERATOR | frozenset({PROJECT_APPROVE, CATALOG_WRITE})
# ADR-120 D3: engineer NÃO tem CATALOG_MERGE (princípio dos 4 olhos: quem edita não aprova)

_ADMIN = _ENGINEER | frozenset({AUTH_MANAGE, SYSTEM_READ, CATALOG_MERGE})

# ADR-120 D2: catalog-manager — especialista em catálogo, sem acesso a projetos de clientes
_CATALOG_MANAGER = frozenset(
    {
        HEALTH_READ,
        CATALOG_READ,
        CATALOG_VALIDATE,
        CATALOG_WRITE,
        CATALOG_MERGE,
        FINANCIALS_READ,  # para avaliar impacto de reajuste em projetos
        AUTH_SELF,  # ADR-123 F5
    }
)

_AUDITOR = frozenset(
    {
        HEALTH_READ,
        PROJECT_READ,
        ARTIFACTS_READ,
        ARTIFACTS_DOWNLOAD,
        FINANCIALS_READ,
        AUTH_SELF,  # ADR-123 F5
    }
)

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "operator": _OPERATOR,
    "engineer": _ENGINEER,
    "admin": _ADMIN,
    "auditor": _AUDITOR,
    "catalog-manager": _CATALOG_MANAGER,  # ADR-120 D2
}

VALID_ROLES: frozenset[str] = frozenset(ROLE_PERMISSIONS.keys())

# ── ADR-119 D1: Superfície de manipulação por role — Pipeline Intent Binding ──
# Cada role tem um conjunto permitido de ProcurementIntent para acionar pipeline.
# operator → só RFI (exploração rápida, OLTP); engineer/admin → RFI + RFP (análise completa).
ROLE_ALLOWED_INTENTS: dict[str, frozenset[str]] = {
    "operator": frozenset({"rfi"}),
    "engineer": frozenset({"rfi", "rfp"}),
    "admin": frozenset({"rfi", "rfp"}),
    "auditor": frozenset(),
}


def check_intent_allowed(intent: str | None, roles: list[str]) -> None:
    """Verifica se o procurement_intent é permitido para os roles do token.

    Raise:
        PermissionError: se o intent não é permitido para nenhum dos roles.
    """
    if not _auth_enabled() or intent is None:
        return
    normalized = str(intent).lower().strip()
    allowed = set()
    for role in roles:
        allowed |= ROLE_ALLOWED_INTENTS.get(role, frozenset())
    if normalized not in allowed:
        roles_str = roles or ["(nenhum)"]
        raise PermissionError(
            f"Intent '{normalized}' não permitido para roles {roles_str!r}. "
            f"Intents permitidos: {sorted(allowed) or '(nenhum)'}. "
            "operator pode usar 'rfi'; engineer/admin podem usar 'rfi' ou 'rfp'."
        )


# ── Mapeamento legado: scopes ADR-094 → roles ADR-099 ─────────────────────────

LEGACY_SCOPE_TO_ROLE: dict[str, str] = {
    "mcp:read": "auditor",
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
    return roles  # fail-closed: JWT sem roles = sem acesso (viewer removido)


def _mcp_message_claims() -> dict | None:
    """Decodifica claims do JWT da mensagem MCP *atual*, via request_ctx do SDK.

    Por que não usar _current_roles/_current_user_id/_current_tenant_id direto:
    em sessões streamable-http *stateful* (padrão do SDK — Concilium nunca passa
    stateless_http=True), o McpAuthMiddleware seta esses contextvars por
    requisição HTTP, mas o SDK MCP despacha tools/call de requisições após a
    primeira usando uma task persistente criada na ABERTURA da sessão (ver
    mcp.server.lowlevel.server.Server.run: `tg.start_soon(self._handle_message,
    ...)` dentro de um task group aberto uma única vez). Essa task captura o
    contexto de quando a sessão foi criada (chamada 'initialize', pública, sem
    roles) — os contextvars setados pela requisição HTTP de uma tool call
    posterior nunca chegam a essa task. Sintoma: "Roles do token: ['(nenhum)']"
    mesmo com um Bearer token válido e roles corretos.

    O próprio SDK, porém, re-seta corretamente `request_ctx` a cada MENSAGEM
    (não a cada sessão) em Server._handle_request, com o Request HTTP real
    (headers inclusos) em `.request` — daí extraímos o Bearer token aqui, por
    chamada, contornando o problema. Ver docstring de patch_mcp_auth_permissions.

    Retorna None se não há request_ctx ativo, sem Authorization Bearer, ou
    token inválido — o chamador deve cair para o contextvar legado nesses casos
    (transporte stdio, testes que chamam set_roles()/set_auth_context() direto).
    """
    from mcp.server.lowlevel.server import request_ctx

    ctx = request_ctx.get(None)
    request = getattr(ctx, "request", None) if ctx is not None else None
    if request is None:
        return None
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return None

    from concilium.infrastructure.auth.token_service import decode_token

    try:
        return decode_token(auth[7:].strip())
    except Exception:
        return None


def _effective_mcp_roles() -> list[str]:
    """Roles efetivos para a chamada de tool MCP atual (ver _mcp_message_claims)."""
    claims = _mcp_message_claims()
    if claims is not None:
        return roles_from_token(claims)
    return list(_current_roles.get())


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


def require_owner_or_admin(actor_id: str, owner_id: str | None, roles: list[str]) -> None:
    """ADR-126 D3: 2ª camada de autorização — ownership, sobre a base de @permission (role).

    Ações destrutivas/estruturais (delete_project, patch_project_config,
    transfer-ownership) exigem role compatível (checado por @permission antes
    desta chamada) **E** (owner_id == actor_id **OU** role admin).

    No-op quando AUTH_ENABLED=0 (dev local) — mesma convenção de require_permission.
    owner_id=None (projeto legado sem migração/backfill, ADR-126 F5) é permissivo:
    o gate de role via @permission já é a única barreira nesse caso.
    """
    if not _auth_enabled():
        return
    if "admin" in roles:
        return
    if owner_id is None:
        return
    if actor_id != owner_id:
        raise PermissionError(
            f"Ação restrita ao dono do projeto (owner_id={owner_id!r}) ou a um admin. "
            f"Actor atual: {actor_id!r}, roles: {roles!r}."
        )


def _auth_enabled() -> bool:
    return get_auth().enabled


# ── Mapeamento MCP tool → permissão (ADR-117) ────────────────────────────────
# Não é mais mantido à mão: a fonte de verdade são as tags @permission nas tools.
# Este dict é um CACHE populado em runtime por build_tool_permission_map(server)
# (chamado em patch_mcp_auth_permissions), para consumidores name-based.
TOOL_PERMISSIONS: dict[str, str] = {}


# ── Contextvars para MCP tools (sem request HTTP) ────────────────────────────

_current_roles: contextvars.ContextVar[frozenset[str]] = contextvars.ContextVar(
    "_rbac_current_roles", default=frozenset()
)

_current_user_id: contextvars.ContextVar[str | None] = contextvars.ContextVar[str | None](
    "_auth_current_user_id", default=None
)

_current_tenant_id: contextvars.ContextVar[str | None] = contextvars.ContextVar[str | None](
    "_auth_current_tenant_id", default=None
)

_current_device_id: contextvars.ContextVar[str | None] = contextvars.ContextVar[str | None](
    "_auth_current_device_id", default=None
)


def set_roles(token_roles: list[str]) -> contextvars.Token:
    """Define os roles do request MCP atual. Chamar antes de invocar a tool."""
    return _current_roles.set(frozenset(token_roles))


def set_auth_context(
    user_id: str | None, tenant_id: str | None, device_id: str | None = None
) -> tuple[contextvars.Token, contextvars.Token, contextvars.Token]:
    """Define user_id, tenant_id e device_id extraídos do JWT no contexto de execução atual.

    device_id (ADR-138 sessões): ausente nos fluxos sem device (ver token_service.issue_token).

    Retorna tokens para reset no finally do middleware (ADR-118).
    """
    return (_current_user_id.set(user_id), _current_tenant_id.set(tenant_id), _current_device_id.set(device_id))


def reset_auth_context(tokens: tuple[contextvars.Token, contextvars.Token, contextvars.Token]) -> None:
    """Restaura contextvars de identidade ao estado anterior."""
    _current_user_id.reset(tokens[0])
    _current_tenant_id.reset(tokens[1])
    _current_device_id.reset(tokens[2])


def get_current_user_id() -> str | None:
    """Retorna user_id do contexto MCP atual (JWT sub). None fora de request.

    Prioriza claims resolvidos por-mensagem (_mcp_message_claims) sobre o
    contextvar _current_user_id — ver _mcp_message_claims para o porquê.
    """
    claims = _mcp_message_claims()
    if claims is not None:
        return claims.get("sub")
    return _current_user_id.get()


def get_current_tenant_id() -> str | None:
    """Retorna tenant_id do contexto MCP atual (JWT tid). None fora de request.

    Prioriza claims resolvidos por-mensagem (_mcp_message_claims) sobre o
    contextvar _current_tenant_id — ver _mcp_message_claims para o porquê.
    """
    claims = _mcp_message_claims()
    if claims is not None:
        return claims.get("tid") or claims.get("tenant_id")
    return _current_tenant_id.get()


def get_current_device_id() -> str | None:
    """Retorna device_id do contexto MCP atual (JWT device_id, ADR-138 sessões).

    None se o token não veio do fluxo de refresh de dispositivo (ex.: client_id/
    secret direto), ou fora de request. Prioriza claims por-mensagem sobre o
    contextvar _current_device_id — ver _mcp_message_claims para o porquê.
    """
    claims = _mcp_message_claims()
    if claims is not None:
        return claims.get("device_id")
    return _current_device_id.get()


def get_current_mcp_session_id() -> str | None:
    """Retorna o Mcp-Session-Id da mensagem MCP atual (ADR-138 sessões).

    Não é claim do JWT — é um header de protocolo (streamable-http), correlato
    à conexão, não à identidade. Por isso não tem fallback de contextvar: só
    faz sentido o valor da mensagem atual (via request_ctx do SDK, correto
    por-mensagem mesmo em sessões stateful reusadas — ver _mcp_message_claims).
    None fora de request HTTP (ex.: stdio) ou se o header não foi enviado.
    """
    from mcp.server.lowlevel.server import request_ctx

    ctx = request_ctx.get(None)
    request = getattr(ctx, "request", None) if ctx is not None else None
    if request is None:
        return None
    return request.headers.get("mcp-session-id")


def _get_roles_from_context(kwargs: dict[str, Any]) -> list[str]:
    """Extrai roles do contexto atual.

    FastAPI route: lê request.state.jwt_claims (injetado pelo JWTAuthMiddleware)
    MCP tool:      ver _effective_mcp_roles
    """
    request = kwargs.get("request")
    if request is not None:
        claims = getattr(request.state, "jwt_claims", {})
        return roles_from_token(claims)
    return _effective_mcp_roles()


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
            # AUTH_PUBLIC: bootstrap sem token (ex: ativar_dispositivo) — sempre permitido,
            # não passa por _auth_enabled()/roles pois é chamado antes de existir qualquer token.
            if perm != AUTH_PUBLIC and _auth_enabled():
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
        # setattr (não atributo direto): `wrapper` é uma função decorada com @wraps,
        # cujo tipo estático não declara `_required_permission` — a tag é inerentemente
        # dinâmica (lida via getattr em _tool_required_permission). noqa: B010 evita
        # que o ruff reescreva isto de volta para atribuição direta (que o ty rejeita).
        setattr(wrapper, "_required_permission", perm)  # noqa: B010
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
    mapping = {name: (_tool_required_permission(tool) or _FAILCLOSED_TOOL_PERMISSION) for name, tool in tools.items()}
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
                # AUTH_PUBLIC: bootstrap sem token — ver permission() acima.
                if perm != AUTH_PUBLIC and _auth_enabled():
                    token_roles = _effective_mcp_roles()
                    if perm not in get_permissions(token_roles):
                        raise PermissionError(
                            f"MCP tool '{fn.__name__}' requer '{perm}'. "
                            f"Roles do token: {token_roles or ['(nenhum)']}. "
                            "Solicite ao admin o role adequado."
                        )
                return fn(*args, **kwargs)

            # setattr (não atributo direto): mesma justificativa do @permission acima.
            setattr(_auth_wrapper, "_required_permission", perm)  # noqa: B010  # propaga a tag
            return _auth_wrapper

        tool.fn = _make_wrapper(original_fn, required_perm)
