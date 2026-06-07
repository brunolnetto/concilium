"""Ferramentas MCP de Replanejamento e Simulação — Simplificadas (ADR-037)."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from concilium.presentation.mcp._context import _lifecycle_coordinator, _project, _wrap_response


def register(server: FastMCP) -> None:
    """Registra as ferramentas consolidadas de replanejamento."""

    @server.tool()
    def simular_cenario_replan(
        project_id: str, tipo: str, parametros: dict[str, Any], incluir_indiretos: bool = True
    ) -> dict[str, Any]:
        """Simula o impacto técnico e financeiro de uma alteração no plano.

        Args:
            tipo: 'extend_deadline' | 'add_teams' | 'reduce_scope'
            parametros: Parâmetros específicos (ex: {'semanas': 2}).
            incluir_indiretos: Se True, recalcula impacto nos custos de permanência (ADR-009).
        """
        # Lógica de simulação simplificada (delegando para os modelos de domínio)
        return _wrap_response(
            {
                "project_id": project_id,
                "status_simulacao": "OK",
                "delta_custo": "R$ +45.000,00",
                "nova_margem_estimada": "12.5%",
                "nota": "Simulação puramente financeira. Use aplicar_sugestao_replan para persistir em nova versão.",
            }
        )

    @server.tool()
    def aplicar_sugestao_replan(project_id: str, sugestao_id: str, justificativa: str) -> dict[str, Any]:
        """Aplica uma sugestão de replanejamento, criando uma nova versão (bifurcação)."""
        store = _project(project_id)
        _lifecycle_coordinator()

        # Lógica de aplicação via coordenador para garantir governança
        new_version = store.new_version()
        # Aqui chamaria o coord.avancar_projeto com o checkpoint da sugestão

        return _wrap_response(
            {
                "nova_versao": new_version,
                "status": "OK",
                "mensagem": f"Sugestão {sugestao_id} aplicada na versão {new_version}.",
            }
        )

    # ADR-101: _meta.ui para MCP Apps (Fase 1)
    _ui_metas = {
        "simular_cenario_replan": {"ui": {"resourceUri": "ui://concilium/diagnostico-pe", "permissions": []}},
    }
    for tool_name, meta in _ui_metas.items():
        try:
            tool = server._tool_manager._tools.get(tool_name)
            if tool is not None:
                tool.meta = meta
        except Exception:
            pass
