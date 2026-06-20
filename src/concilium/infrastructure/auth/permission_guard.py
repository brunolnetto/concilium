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


# ── Mapeamento MCP tool → permissão ──────────────────────────────────────────

TOOL_PERMISSIONS: dict[str, str] = {
    # ── Leitura (viewer) ──────────────────────────────────────────────────────
    "listar_projetos": PROJECT_READ,
    "consultar_status": PROJECT_READ,
    "comparar_planos": PROJECT_READ,
    "explorar_pool_recursos": PROJECT_READ,
    "consultar_benchmark": PROJECT_READ,
    "listar_benchmarks_nep039": PROJECT_READ,
    "comparar_execucoes_benchmark": PROJECT_READ,
    "listar_runs_campanha": PROJECT_READ,
    "consultar_estrutura_projeto": PROJECT_READ,
    "consultar_job_pipeline": PROJECT_READ,
    "listar_jobs_pipeline": PROJECT_READ,
    "obter_estatisticas_jobs": PROJECT_READ,
    # ── Catálogo leitura (viewer) ─────────────────────────────────────────────
    "listar_contextos": CATALOG_READ,
    "pesquisar_catalogo": CATALOG_READ,
    "listar_cpus": CATALOG_READ,
    "buscar_cpu": CATALOG_READ,
    "derivar_recursos_do_catalogo": CATALOG_READ,
    "consultar_saude_catalogo": CATALOG_READ,
    "avaliar_plausibilidade_catalogo": CATALOG_READ,
    "verificar_integridade_catalogo": CATALOG_READ,
    "consultar_preco_insumo_temporal": CATALOG_READ,
    "tendencia_precos_catalogo": CATALOG_READ,
    "calcular_pu_producao": CATALOG_READ,
    "listar_versoes_catalogo": CATALOG_READ,
    "comparar_versoes_catalogo": CATALOG_READ,
    # ── Tributação (viewer — informacional) ───────────────────────────────────
    "calcular_custo_empregador_clt": CATALOG_READ,
    "calcular_inss_empregado": CATALOG_READ,
    "calcular_irrf": CATALOG_READ,
    # ── Sistema (admin) ───────────────────────────────────────────────────────
    "ping": SYSTEM_READ,
    # ── Artefatos leitura ─────────────────────────────────────────────────────
    "listar_artefatos_projeto": ARTIFACTS_READ,
    "auditar_plano": ARTIFACTS_READ,
    # ── Financeiros (auditor/operator) ────────────────────────────────────────
    "consultar_viabilidade_prazo": FINANCIALS_READ,
    "identificar_gargalos_recurso": FINANCIALS_READ,
    "obter_resultado_campanha": FINANCIALS_READ,
    "comparar_rfi_catalogo": FINANCIALS_READ,
    # ── Download (operator) ───────────────────────────────────────────────────
    "ler_artefato": ARTIFACTS_DOWNLOAD,
    "ler_artefato_texto": ARTIFACTS_DOWNLOAD,
    "baixar_artefato_binario": ARTIFACTS_DOWNLOAD,
    "baixar_bundle_zip": ARTIFACTS_DOWNLOAD,
    "download_benchmark_zip": ARTIFACTS_DOWNLOAD,
    # ── Criação (operator) ────────────────────────────────────────────────────
    "criar_projeto_formulario": PROJECT_CREATE,
    "criar_projeto_spec": PROJECT_CREATE,
    "iniciar_orcamento": PROJECT_CREATE,
    "nova_versao": PROJECT_CREATE,
    "configurar_escopo": PROJECT_CREATE,
    "gerenciar_plano": PROJECT_CREATE,
    # ── Execução (operator) ───────────────────────────────────────────────────
    "disparar_pipeline": PROJECT_RUN,
    "cancelar_job_pipeline": PROJECT_RUN,
    "executar_benchmark_nep039": PROJECT_RUN,
    "empacotar_benchmark": PROJECT_RUN,
    "explorar_configuracoes_go": PROJECT_RUN,
    "simular_cenario_replan": PROJECT_RUN,
    "salvar_perfil_bdi": PROJECT_RUN,
    "editar_benchmark": PROJECT_RUN,
    "simular_impacto_replan": PROJECT_RUN,
    "aplicar_sugestao_replan": PROJECT_RUN,
    # ── Aprovação / Escrita catálogo (engineer) ───────────────────────────────
    "aprovar_versao": PROJECT_APPROVE,
    "marcar_benchmark_imutavel": PROJECT_APPROVE,
    "atualizar_preco_insumo": CATALOG_WRITE,
    "adicionar_variante_producao": CATALOG_WRITE,
}


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

# Permissão padrão para tools sem mapeamento explícito (mínimo: qualquer usuário autenticado)
_DEFAULT_TOOL_PERMISSION = PROJECT_READ


def validate_tool_coverage(server: Any) -> list[str]:
    """Verifica quais tools registradas no servidor não têm entrada em TOOL_PERMISSIONS.

    Retorna lista de nomes de tools sem mapeamento.
    Chamado em build_server() para auditoria de cobertura.
    """
    try:
        tools = server._tool_manager._tools
    except AttributeError:
        return []
    missing = [name for name in tools if name not in TOOL_PERMISSIONS]
    if missing:
        _guard_log.warning(
            "RBAC: %d tool(s) sem mapeamento em TOOL_PERMISSIONS: %s — será aplicada permissão padrão '%s'",
            len(missing),
            missing,
            _DEFAULT_TOOL_PERMISSION,
        )
    return missing


def patch_mcp_auth_permissions(server: Any) -> None:
    """Envolve todas as tools MCP com verificação de permissão via TOOL_PERMISSIONS.

    Para tools com @permission() decorator: a verificação dupla é harmless
    (o decorator ainda executa depois do wrapper).
    Para tools sem @permission(): o wrapper é a única linha de defesa.
    Tools sem entrada em TOOL_PERMISSIONS recebem _DEFAULT_TOOL_PERMISSION.

    Chamado em build_server() após registrar todas as tools.
    """
    try:
        tools = server._tool_manager._tools
    except AttributeError:
        _guard_log.warning("patch_mcp_auth_permissions: servidor sem _tool_manager._tools — skipping")
        return

    for tool_name, tool in tools.items():
        if not (hasattr(tool, "fn") and callable(tool.fn)):
            continue
        required_perm = TOOL_PERMISSIONS.get(tool_name, _DEFAULT_TOOL_PERMISSION)
        original_fn = tool.fn

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

            return _auth_wrapper

        tool.fn = _make_wrapper(original_fn, required_perm)
