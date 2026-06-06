"""Ferramentas MCP de Estrutura de Projeto (Escopos e Planos) — Simplificadas (ADR-037)."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from concilium.presentation.mcp._context import _project, _wrap_response


def _resolve_escopo_id(store: Any, escopo_id: str | None = None) -> str:
    """Resolve o escopo_id para um ProjectStore.

    Se escopo_id fornecido, valida que existe. Caso contrário, infere automaticamente
    se o projeto tiver exatamente 1 escopo; lança erro se houver múltiplos ou nenhum.
    """
    escopos = store.list_escopos()
    if not escopos:
        raise ValueError(f"Projeto '{store.meta.get('id', '?')}' não possui escopos. Use configurar_escopo primeiro.")
    if escopo_id:
        if escopo_id not in escopos:
            raise ValueError(f"Escopo '{escopo_id}' não encontrado. Disponíveis: {escopos}")
        return escopo_id
    if len(escopos) == 1:
        return escopos[0]
    raise ValueError(f"Projeto tem múltiplos escopos. Especifique escopo_id. Disponíveis: {escopos}")


def register(server: FastMCP) -> None:
    """Registra as ferramentas consolidadas de estrutura de projeto."""

    @server.tool()
    def consultar_estrutura_projeto(project_id: str) -> dict[str, Any]:
        """Retorna a árvore completa de Escopos e Planos do projeto (ADR-031)."""
        store = _project(project_id)
        escopos = store.list_escopos()
        out = []
        for eid in escopos:
            es = store.escopo(eid)
            m = es.meta
            planos = []
            for pid in es.list_plans():
                ps = es.plan(pid)
                can = ps.load_canonical()
                planos.append(
                    {
                        "plano_id": pid,
                        "nome": ps.meta.get("nome", pid),
                        "status": ps.meta.get("status"),
                        "margem_pct": can.resultado.margem_pct if can and can.resultado else None,
                    }
                )
            out.append(
                {
                    "escopo_id": eid,
                    "nome": m.get("nome", eid),
                    "tipo_obra": m.get("tipo_obra"),
                    "status": m.get("status"),
                    "planos": planos,
                }
            )
        return _wrap_response({"project_id": project_id, "escopos": out})

    @server.tool()
    def configurar_escopo(
        project_id: str,
        escopo_id: str,
        nome: str,
        tipo_obra: str,
        localizacao: str,
        data_inicio: str,
        data_termino: str,
    ) -> dict[str, Any]:
        """Cria ou atualiza um escopo de obra no projeto."""
        store = _project(project_id)
        try:
            es = store.create_escopo(  # type: ignore[call-arg]
                escopo_id=escopo_id,
                nome=nome,
                tipo_obra=tipo_obra,
                localizacao=localizacao,
                data_inicio=data_inicio,
                data_termino=data_termino,
            )
        except Exception as e:
            return {"erro": str(e)}
        return _wrap_response({"status": "OK", "escopo_id": es.escopo_id})

    @server.tool()
    def gerenciar_plano(
        project_id: str,
        escopo_id: str,
        acao: str,
        nome: str | None = None,
        plano_id: str | None = None,
        hipotese: str | None = None,
    ) -> dict[str, Any]:
        """Gerencia planos dentro de um escopo (criar, aprovar, arquivar).

        Args:
            acao: 'criar' | 'aprovar' | 'arquivar'
        """
        store = _project(project_id)
        es = store.escopo(escopo_id)

        if acao == "criar":
            ps = es.create_plan(nome=nome or "Novo Plano", hipotese=hipotese)
            return _wrap_response({"plano_id": ps.plano_id})
        elif acao == "aprovar":
            if not plano_id:
                return {"erro": "plano_id obrigatório para aprovar"}
            arquivados = es.approve_plan(plano_id)
            return _wrap_response({"plano_aprovado": plano_id, "arquivados": arquivados})
        elif acao == "arquivar":
            if not plano_id:
                return {"erro": "plano_id obrigatório para arquivar"}
            ps = es.plan(plano_id)
            ps.archive()
            return _wrap_response({"status": "ARQUIVADO", "plano_id": plano_id})

        return {"erro": f"Ação '{acao}' inválida"}
