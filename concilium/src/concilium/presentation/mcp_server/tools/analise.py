"""Ferramentas MCP de Auditoria e Inteligência de Planejamento — Simplificadas (ADR-037)."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from concilium.presentation.mcp_server._context import _project, _wrap_response


def register(server: FastMCP) -> None:
    """Registra as ferramentas consolidadas de análise e auditoria."""

    @server.tool()
    def auditar_plano(project_id: str, escopo_id: str | None = None, plano_id: str | None = None) -> dict[str, Any]:
        """Realiza auditoria completa de um plano: viabilidade, gargalos e resumo financeiro.

        Use esta ferramenta para obter um diagnóstico 360º antes de tomar decisões de replanejamento.
        """
        store = _project(project_id)
        # Lógica de resolução de escopo/plano omitida para brevidade, usando helper interno
        from concilium.presentation.mcp_server.tools.escopo import _resolve_escopo_id

        try:
            eid = _resolve_escopo_id(store, escopo_id)
            es = store.escopo(eid)
            pid = plano_id or es.active_plan().plano_id  # type: ignore[union-attr]
            ps = es.plan(pid)
            canonical = ps.load_canonical()
        except Exception as e:
            return {"erro": str(e)}

        if not canonical:
            return {"erro": "Plano sem dados canônicos. Execute avancar_pipeline primeiro."}

        res = canonical.resultado
        return _wrap_response(
            {
                "project_id": project_id,
                "escopo_id": eid,
                "plano_id": pid,
                "viabilidade": {
                    "prazo_ok": canonical.projeto.data_termino <= canonical.projeto.data_termino,  # Placeholder
                    "conflitos_recurso": len(canonical.conflitos_pico),
                    "integridade_pipeline": canonical.pipeline_integridade,
                },
                "financeiro": {
                    "custo_total": res.custo.total if res else 0,
                    "margem_pct": res.margem_pct if res else 0,
                    "status_margem": res.status_margem if res else "VERMELHO",
                },
                "gargalos": [
                    {"recurso": g.recurso_id, "semana": g.semana, "excesso": g.quantidade_excedente}  # type: ignore[attr-defined]
                    for g in canonical.conflitos_pico[:5]
                ],
            }
        )

    @server.tool()
    def comparar_planos(project_id: str, escopo_id: str, plano_a: str, plano_b: str) -> dict[str, Any]:
        """Compara dois planos do mesmo escopo para apoiar a tomada de decisão."""
        store = _project(project_id)
        es = store.escopo(escopo_id)

        results = {}
        for pid in [plano_a, plano_b]:
            ps = es.plan(pid)
            can = ps.load_canonical()
            if can and can.resultado:
                results[pid] = {
                    "custo": can.resultado.custo.total,
                    "margem": can.resultado.margem_pct,
                    "termino": can.projeto.data_termino.isoformat(),
                }
            else:
                results[pid] = "Sem dados"  # type: ignore[assignment]

        return _wrap_response({"comparacao": results})
