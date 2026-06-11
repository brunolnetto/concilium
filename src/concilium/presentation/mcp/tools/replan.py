"""Ferramentas MCP de Replanejamento e Simulação — Simplificadas (ADR-037)."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP


def register(server: FastMCP) -> None:
    """Registra as ferramentas consolidadas de replanejamento."""

    @server.tool()
    def simular_cenario_replan(
        project_id: str, tipo: str, parametros: dict[str, Any], incluir_indiretos: bool = True
    ) -> dict[str, Any]:
        """[NÃO IMPLEMENTADO] Simulação de replanejamento — retorna erro informativo."""
        return {
            "erro": "simular_cenario_replan ainda não implementado. Use auditar_plano + disparar_pipeline manualmente."
        }

    @server.tool()
    def aplicar_sugestao_replan(project_id: str, sugestao_id: str, justificativa: str) -> dict[str, Any]:
        """[NÃO IMPLEMENTADO] Aplicação de sugestão de replanejamento — retorna erro informativo."""
        return {"erro": "aplicar_sugestao_replan ainda não implementado. Crie nova versão via gerenciar_plano."}

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
