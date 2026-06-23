"""TDD — Item 5: RBAC role ↔ MCP tool mapping.

Cobre:
  - TOOL_PERMISSIONS cobre todas as 55 tools MCP registradas
  - patch_mcp_auth_permissions() bloqueia chamadas não autorizadas
  - patch_mcp_auth_permissions() permite chamadas autorizadas
  - validate_tool_coverage() detecta tools sem mapeamento
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

ALL_TOOL_NAMES = [
    # analise
    "auditar_plano",
    "comparar_planos",
    "explorar_pool_recursos",
    # artifacts
    "listar_artefatos_projeto",
    "obter_artefato",  # ADR-116 F5
    
    
    # benchmark (ADR-116: listar_benchmarks/executar_benchmark removidas — dup de nep039)
    "empacotar_benchmark",
    "download_benchmark_zip",
    # benchmark_nep039
    "consultar_benchmark",
    # campaign
    "explorar_configuracoes_go",
    "listar_runs_campanha",
    "obter_resultado_campanha",
    # catalogo
    "listar_contextos",
    "pesquisar_catalogo",
    "auditar_catalogo",  # ADR-116 F5: consultar_saude + avaliar_plausibilidade + verificar_integridade
    "atualizar_preco_insumo",
    "adicionar_variante_producao",
    "historico_preco_insumo",  # ADR-116 F5
    
    "comparar_rfi_catalogo",
    "calcular_pu_producao",
    "versoes_catalogo",  # ADR-116 F5
    
    # escopo
    "consultar_estrutura_projeto",
    "gerir_escopo",  # ADR-116 F5
    
    # formulario
    "criar_projeto",  # ADR-116 F5
    # pipeline
    "disparar_pipeline",
    "consultar_job_pipeline",
    "listar_jobs_pipeline",
    
    "cancelar_job_pipeline",
    # (ADR-116: avancar_pipeline removida — deprecada, substituída por disparar_pipeline)
    # projeto
    "listar_projetos",
    "iniciar_orcamento",
    "consultar_status",
    "aprovar_versao",
    "nova_versao",
    "salvar_perfil_bdi",
    # replan
    "simular_cenario_replan",
    # spec
    
    # system
    "ping",
    # tributacao (ADR-116 F5: 3 → 1 tool unificada)
    "calcular_tributos",
    # catalogo — ciclo de vida (ADR-120: rascunho → merge)
    "criar_rascunho_catalogo",
    "listar_divergencias_rascunho",
    "consultar_impacto_reajuste",
    "aprovar_merge_catalogo",
    "rejeitar_rascunho_catalogo",
]


# ─────────────────────────────────────────────────────────────────────────────
# F1: TOOL_PERMISSIONS cobre todas as tools
# ─────────────────────────────────────────────────────────────────────────────


def _ast_tool_permission_map() -> dict[str, str]:
    """ADR-117: deriva nome→permissão das tags @permission no source das tools (sem servidor vivo)."""
    import ast
    import glob
    import os

    root = os.path.join(os.path.dirname(__file__), "..", "..")
    mapping: dict[str, str] = {}
    for f in sorted(glob.glob(os.path.join(root, "src/concilium/presentation/mcp/tools/*.py"))):
        tree = ast.parse(open(f, encoding="utf-8").read())
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            is_tool = any(
                (isinstance(d, ast.Attribute) and d.attr == "tool")
                or (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr == "tool")
                for d in node.decorator_list
            )
            if not is_tool:
                continue
            for d in node.decorator_list:
                if isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == "permission":
                    if d.args and isinstance(d.args[0], ast.Constant):
                        mapping[node.name] = d.args[0].value
    return mapping


class TestToolPermissionsCoverage:
    """ADR-117: toda tool tem @permission inline (fonte única, derivada por introspecção)."""

    def test_all_tools_have_permission_tag(self):
        perm_map = _ast_tool_permission_map()
        missing = [t for t in ALL_TOOL_NAMES if t not in perm_map]
        assert not missing, f"{len(missing)} tools sem @permission inline:\n  " + "\n  ".join(sorted(missing))

    def test_tool_permissions_values_are_valid_permissions(self):
        """Cada permissão declarada via @permission deve ser uma string conhecida."""
        TOOL_PERMISSIONS = _ast_tool_permission_map()

        valid_perms = {
            "project:read",
            "project:create",
            "project:run",
            "project:approve",
            "catalog:read",
            "catalog:write",
            "catalog:validate",  # ADR-120
            "catalog:merge",     # ADR-120
            "artifacts:read",
            "artifacts:download",
            "financials:read",
            "auth:manage",
            "system:read",
        }
        invalid = {k: v for k, v in TOOL_PERMISSIONS.items() if v not in valid_perms}
        assert not invalid, f"Permissões inválidas: {invalid}"

    def test_write_tools_require_at_least_operator_permission(self):
        """Tools que modificam dados não devem exigir apenas catalog:read ou project:read."""
        TOOL_PERMISSIONS = _ast_tool_permission_map()

        write_tools = {
            "iniciar_orcamento",
            "criar_projeto",
            "disparar_pipeline",
            "atualizar_preco_insumo",
            "adicionar_variante_producao",
            "aprovar_versao",
            "criar_rascunho_catalogo",   # ADR-120
            "aprovar_merge_catalogo",    # ADR-120
            "rejeitar_rascunho_catalogo", # ADR-120
        }
        read_only = {"project:read", "catalog:read", "artifacts:read", "system:read", "catalog:validate"}
        for tool in write_tools:
            perm = TOOL_PERMISSIONS.get(tool)
            assert perm not in read_only, (
                f"Tool de escrita '{tool}' requer apenas '{perm}' (leitura). "
                "Deve exigir pelo menos project:create, project:run ou catalog:write."
            )


# ─────────────────────────────────────────────────────────────────────────────
# F2: validate_tool_coverage() detecta gaps
# ─────────────────────────────────────────────────────────────────────────────


class TestValidateToolCoverage:
    """validate_tool_coverage(server) detecta tools SEM tag @permission (ADR-117)."""

    def _make_server(self, tools_spec: dict[str, str | None]):
        """Cria servidor simulado. tools_spec: {nome: perm|None}.

        perm=None → fn sem _required_permission (deve ser detectada como não-coberta).
        """
        server = MagicMock()
        tools = {}
        for name, perm in tools_spec.items():
            t = MagicMock()
            fn = lambda: None
            fn.__name__ = name
            if perm is not None:
                fn._required_permission = perm
            t.fn = fn  # fn real (não MagicMock) — sem auto-criação de atributo
            tools[name] = t
        server._tool_manager._tools = tools
        return server

    def test_returns_empty_when_all_tools_tagged(self):
        from concilium.infrastructure.auth.permission_guard import validate_tool_coverage

        server = self._make_server({"a": "project:read", "b": "project:run"})
        assert validate_tool_coverage(server) == []

    def test_returns_untagged_tools(self):
        from concilium.infrastructure.auth.permission_guard import validate_tool_coverage

        server = self._make_server({"ferramenta_nova_sem_permissao": None})
        missing = validate_tool_coverage(server)
        assert "ferramenta_nova_sem_permissao" in missing


# ─────────────────────────────────────────────────────────────────────────────
# F3: patch_mcp_auth_permissions() enforcement
# ─────────────────────────────────────────────────────────────────────────────


class TestPatchMcpAuthPermissions:
    """patch_mcp_auth_permissions() envolve tools com verificação de permissão."""

    def _make_server_with_tool(self, tool_name: str, tool_fn=None, perm: str | None = None):
        server = MagicMock()
        if tool_fn is None:
            tool_fn = lambda: "ok"
            tool_fn.__name__ = tool_name
        if perm is not None:
            tool_fn._required_permission = perm  # ADR-117: tag posta por @permission
        tool = MagicMock()
        tool.fn = tool_fn
        server._tool_manager._tools = {tool_name: tool}
        return server

    def test_authorized_call_passes_through(self):
        """operator pode chamar disparar_pipeline (project:run)."""
        from concilium.infrastructure.auth.permission_guard import (
            _current_roles,
            patch_mcp_auth_permissions,
            set_roles,
        )

        result_holder = []

        def fn():
            result_holder.append("called")

        fn.__name__ = "disparar_pipeline"
        server = self._make_server_with_tool("disparar_pipeline", fn, perm="project:run")
        patch_mcp_auth_permissions(server)
        # Simula roles de operator
        tok = set_roles(["operator"])
        try:
            server._tool_manager._tools["disparar_pipeline"].fn()
        finally:
            _current_roles.reset(tok)
        assert "called" in result_holder

    def test_unauthorized_call_raises_permission_error(self):
        """viewer não pode chamar disparar_pipeline (project:run) quando auth ativo."""
        from concilium.infrastructure.auth.permission_guard import (
            _current_roles,
            patch_mcp_auth_permissions,
            set_roles,
        )

        def fn():
            pass

        fn.__name__ = "disparar_pipeline"
        server = self._make_server_with_tool("disparar_pipeline", fn, perm="project:run")
        patch_mcp_auth_permissions(server)
        tok = set_roles(["viewer"])
        with patch("concilium.infrastructure.auth.permission_guard._auth_enabled", return_value=True):
            try:
                with pytest.raises(PermissionError):
                    server._tool_manager._tools["disparar_pipeline"].fn()
            finally:
                _current_roles.reset(tok)

    def test_viewer_can_call_read_tool(self):
        """viewer pode chamar listar_projetos (project:read)."""
        from concilium.infrastructure.auth.permission_guard import (
            _current_roles,
            patch_mcp_auth_permissions,
            set_roles,
        )

        result_holder = []

        def fn():
            result_holder.append("read_ok")

        fn.__name__ = "listar_projetos"
        server = self._make_server_with_tool("listar_projetos", fn, perm="project:read")
        patch_mcp_auth_permissions(server)
        tok = set_roles(["viewer"])
        try:
            server._tool_manager._tools["listar_projetos"].fn()
        finally:
            _current_roles.reset(tok)
        assert "read_ok" in result_holder

    def test_untagged_tool_is_fail_closed(self):
        """ADR-117: tool sem tag @permission → fail-closed (exige auth:manage, só admin).

        operator NÃO tem auth:manage → negado quando auth ativo. O default deixou de
        ser project:read (permissivo) para auth:manage (restritivo) — segurança por omissão.
        """
        from concilium.infrastructure.auth.permission_guard import (
            _current_roles,
            patch_mcp_auth_permissions,
            set_roles,
        )

        def fn():
            return "executou"

        fn.__name__ = "tool_nova_sem_mapeamento"
        server = self._make_server_with_tool("tool_nova_sem_mapeamento", fn)  # sem perm= → sem tag
        patch_mcp_auth_permissions(server)
        tok = set_roles(["operator"])
        with patch("concilium.infrastructure.auth.permission_guard._auth_enabled", return_value=True):
            try:
                with pytest.raises(PermissionError):
                    server._tool_manager._tools["tool_nova_sem_mapeamento"].fn()
            finally:
                _current_roles.reset(tok)
# ADR-120: 5 novas tools de ciclo de vida de catálogo (appended after original list close)
