"""Ferramentas MCP de Auditoria e Inteligência de Planejamento — Simplificadas (ADR-037)."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from concilium.infrastructure.auth.permission_guard import permission
from concilium.presentation.mcp._context import _project, _wrap_response


def register(server: FastMCP) -> None:
    """Registra as ferramentas consolidadas de análise e auditoria."""

    @server.tool()
    @permission("artifacts:read")
    def auditar_plano(project_id: str, escopo_id: str | None = None, plano_id: str | None = None) -> dict[str, Any]:
        """Realiza auditoria completa de um plano: viabilidade, gargalos e resumo financeiro.

        Use esta ferramenta para obter um diagnóstico 360º antes de tomar decisões de replanejamento.
        """
        store = _project(project_id)
        # Lógica de resolução de escopo/plano omitida para brevidade, usando helper interno
        from concilium.presentation.mcp.tools.escopo import _resolve_escopo_id

        try:
            eid = _resolve_escopo_id(store, escopo_id)
            es = store.escopo(eid)
            pid = plano_id or es.active_plan().plano_id  # type: ignore[union-attr]
            ps = es.plan(pid)
            canonical = ps.load_canonical()
        except Exception as e:
            return {"erro": str(e)}

        if not canonical:
            return {"erro": "Plano sem dados canônicos. Execute disparar_pipeline primeiro."}

        res = canonical.resultado
        return _wrap_response(
            {
                "project_id": project_id,
                "escopo_id": eid,
                "plano_id": pid,
                "viabilidade": {
                    "prazo_ok": canonical.projeto.data_termino >= __import__("datetime").date.today(),
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
    @permission("project:read")
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

    @server.tool()
    @permission("project:read")
    def explorar_pool_recursos(
        project_id: str,
        face: str = "instancia_ciclo_vida",
        escopo_id: str | None = None,
        plano_id: str | None = None,
        granularidade: str = "mes",
        atividade_id: str | None = None,
        instancia_id: str | None = None,
    ) -> dict[str, Any]:
        """ADR-086: Explora a decomposição composicional-temporal do pool de recursos.

        Retorna linhas + narrativa honesta (física vs. causal) para investigar por que uma
        atividade/instância custou o que custou, separando o que cada slot *fez* (prod/idle/off,
        custo por componente) do que é *imputado* causalmente (ociosidade ao sucessor, mob/demob
        na cadeia) e da economia vs. execução autônoma.

        Faces: instancia_ciclo_vida | custo_estado_componente | utilizacao_temporal |
        atividade_instancia | causa_custo | economia_pool | cadeia_perpetuacao.
        """
        from concilium.application.services.analytics.cubo_pool_projection import (
            resolve_cubo_pool_projection,
        )
        from concilium.presentation.mcp.tools.escopo import _resolve_escopo_id

        store = _project(project_id)
        try:
            eid = _resolve_escopo_id(store, escopo_id)
            es = store.escopo(eid)
            pid = plano_id or es.active_plan().plano_id  # type: ignore[union-attr]
            canonical = es.plan(pid).load_canonical()
        except Exception as e:
            return {"erro": str(e)}

        if not canonical:
            return {"erro": "Plano sem dados canônicos. Execute disparar_pipeline primeiro."}
        if not (getattr(canonical, "contratos_recurso", None) or getattr(canonical, "instancias_recurso", None)):
            return {"erro": "Sem pool de recursos neste plano (rcpsp_spec ausente em skill-05)."}

        proj = resolve_cubo_pool_projection(
            canonical,
            face=face,
            granularidade=granularidade,
            atividade_id=atividade_id,
            instancia_id=instancia_id,
        )
        return _wrap_response(
            {
                "project_id": project_id,
                "escopo_id": eid,
                "plano_id": pid,
                "face": proj["face"],
                "natureza": proj["natureza"],
                "narrativa": proj["narrativa"],
                "rows": proj["rows"],
                "totais": proj["totais"],
                "invariantes_ok": proj["invariantes_ok"],
            }
        )
