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
    "ler_artefato_texto",
    "baixar_artefato_binario",
    "baixar_bundle_zip",
    # benchmark (ADR-116: listar_benchmarks/executar_benchmark removidas — dup de nep039)
    "empacotar_benchmark",
    "download_benchmark_zip",
    # benchmark_nep039
    "consultar_benchmark",
    "listar_benchmarks_nep039",
    "executar_benchmark_nep039",
    "editar_benchmark",
    "marcar_benchmark_imutavel",
    "comparar_execucoes_benchmark",
    # campaign
    "explorar_configuracoes_go",
    "listar_runs_campanha",
    "obter_resultado_campanha",
    # catalogo
    "listar_contextos",
    "pesquisar_catalogo",
    "consultar_saude_catalogo",
    "avaliar_plausibilidade_catalogo",
    "verificar_integridade_catalogo",
    "atualizar_preco_insumo",
    "adicionar_variante_producao",
    "consultar_preco_insumo_temporal",
    "tendencia_precos_catalogo",
    "comparar_rfi_catalogo",
    "calcular_pu_producao",
    "listar_versoes_catalogo",
    "comparar_versoes_catalogo",
    # escopo
    "consultar_estrutura_projeto",
    "configurar_escopo",
    "gerenciar_plano",
    # formulario
    "criar_projeto_formulario",
    # pipeline
    "disparar_pipeline",
    "consultar_job_pipeline",
    "listar_jobs_pipeline",
    "obter_estatisticas_jobs",
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
    "criar_projeto_spec",
    # system
    "ping",
    # tributacao
    "calcular_custo_empregador_clt",
    "calcular_inss_empregado",
    "calcular_irrf",
]


# ─────────────────────────────────────────────────────────────────────────────
# F1: TOOL_PERMISSIONS cobre todas as tools
# ─────────────────────────────────────────────────────────────────────────────


class TestToolPermissionsCoverage:
    """TOOL_PERMISSIONS deve mapear todas as 55 tools MCP."""

    def test_all_tools_have_entry_in_tool_permissions(self):
        from concilium.infrastructure.auth.permission_guard import TOOL_PERMISSIONS

        missing = [t for t in ALL_TOOL_NAMES if t not in TOOL_PERMISSIONS]
        assert not missing, f"{len(missing)} tools sem entrada em TOOL_PERMISSIONS:\n  " + "\n  ".join(sorted(missing))

    def test_tool_permissions_values_are_valid_permissions(self):
        """Cada valor em TOOL_PERMISSIONS deve ser uma permission string conhecida."""
        from concilium.infrastructure.auth.permission_guard import TOOL_PERMISSIONS

        valid_perms = {
            "project:read",
            "project:create",
            "project:run",
            "project:approve",
            "catalog:read",
            "catalog:write",
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
        from concilium.infrastructure.auth.permission_guard import TOOL_PERMISSIONS

        write_tools = {
            "iniciar_orcamento",
            "criar_projeto_formulario",
            "criar_projeto_spec",
            "disparar_pipeline",
            "executar_benchmark_nep039",
            "atualizar_preco_insumo",
            "adicionar_variante_producao",
            "aprovar_versao",
            "marcar_benchmark_imutavel",
        }
        read_only = {"project:read", "catalog:read", "artifacts:read", "system:read"}
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
    """validate_tool_coverage(server) detecta tools registradas sem mapeamento."""

    def _make_server(self, tool_names: list[str]):
        """Cria servidor FastMCP simulado com tools pelo nome."""
        server = MagicMock()
        tools = {}
        for name in tool_names:
            t = MagicMock()
            t.fn.__name__ = name
            tools[name] = t
        server._tool_manager._tools = tools
        return server

    def test_returns_empty_when_all_tools_mapped(self):
        from concilium.infrastructure.auth.permission_guard import TOOL_PERMISSIONS, validate_tool_coverage

        server = self._make_server(list(TOOL_PERMISSIONS.keys())[:5])
        missing = validate_tool_coverage(server)
        assert missing == []

    def test_returns_unmapped_tools(self):
        from concilium.infrastructure.auth.permission_guard import validate_tool_coverage

        server = self._make_server(["ferramenta_nova_sem_permissao"])
        missing = validate_tool_coverage(server)
        assert "ferramenta_nova_sem_permissao" in missing


# ─────────────────────────────────────────────────────────────────────────────
# F3: patch_mcp_auth_permissions() enforcement
# ─────────────────────────────────────────────────────────────────────────────


class TestPatchMcpAuthPermissions:
    """patch_mcp_auth_permissions() envolve tools com verificação de permissão."""

    def _make_server_with_tool(self, tool_name: str, tool_fn=None):
        server = MagicMock()
        if tool_fn is None:
            tool_fn = lambda: "ok"
            tool_fn.__name__ = tool_name
        tool = MagicMock()
        tool.fn = tool_fn
        tool.fn.__name__ = tool_name
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
        server = self._make_server_with_tool("disparar_pipeline", fn)
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
        server = self._make_server_with_tool("disparar_pipeline", fn)
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
        server = self._make_server_with_tool("listar_projetos", fn)
        patch_mcp_auth_permissions(server)
        tok = set_roles(["viewer"])
        try:
            server._tool_manager._tools["listar_projetos"].fn()
        finally:
            _current_roles.reset(tok)
        assert "read_ok" in result_holder

    def test_unmapped_tool_defaults_to_project_read(self):
        """Tool sem mapeamento exige project:read como mínimo."""
        from concilium.infrastructure.auth.permission_guard import (
            _current_roles,
            patch_mcp_auth_permissions,
            set_roles,
        )

        result_holder = []

        def fn():
            result_holder.append("default_perm")

        fn.__name__ = "tool_nova_sem_mapeamento"
        server = self._make_server_with_tool("tool_nova_sem_mapeamento", fn)
        patch_mcp_auth_permissions(server)
        # operator tem project:read, então deve passar
        tok = set_roles(["operator"])
        try:
            server._tool_manager._tools["tool_nova_sem_mapeamento"].fn()
        finally:
            _current_roles.reset(tok)
        assert "default_perm" in result_holder
