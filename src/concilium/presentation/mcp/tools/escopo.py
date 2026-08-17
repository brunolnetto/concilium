"""Ferramentas MCP de Estrutura de Projeto (Escopos e Planos) — Simplificadas (ADR-037)."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from concilium.infrastructure.auth.permission_guard import permission
from concilium.presentation.mcp._context import _project, _wrap_response
from concilium.presentation.mcp.rate_limit import mcp_rate_limit


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
    @permission("project:read")
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
    @permission("project:create")
    @mcp_rate_limit()
    def gerir_escopo(
        project_id: str,
        entidade: str,
        escopo_id: str,
        acao: str = "criar",
        nome: str | None = None,
        tipo_obra: str | None = None,
        localizacao: str | None = None,
        data_inicio: str | None = None,
        data_termino: str | None = None,
        coordenadas_lat: float = 0.0,
        coordenadas_lng: float = 0.0,
        dias_semana: int = 6,
        horas_dia: int = 8,
        horas_improdutivas_dia: float = 0.5,
        plano_id: str | None = None,
        hipotese: str | None = None,
        logistica_consumiveis: dict[str, dict[str, float]] | None = None,
        roster_mo_membro: dict[str, Any] | None = None,
        roster_eq_ativo: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Cria ou gerencia escopos e planos do projeto.

        entidade: "escopo" | "plano"

        Para entidade="escopo":
          - acao="criar" (default): cria/atualiza um escopo. Requer nome, tipo_obra,
            localizacao, data_inicio, data_termino.
          - acao="editar_roster_mo" (ADR-173 F3): adiciona ou edita um membro do
            roster real de MO por `individuo_id` — merge raso, nunca remove um
            registro já presente (desligamento é `data_desligamento` setada, não
            remoção). Requer `roster_mo_membro` com ao menos `individuo_id`.
          - acao="editar_roster_eq" (ADR-174 F1): mesma semântica, para o roster
            real de equipamento, por `ativo_id`. Requer `roster_eq_ativo` com ao
            menos `ativo_id`.
          - logistica_consumiveis (ADR-128 F5, opcional): capacidade logística real por
            insumo_id para o cronograma automático considerar estoque de consumíveis
            (diesel/material) — ex.: {"MA-DIESEL-S10": {"capacidade_armazenamento": 15000,
            "estoque_inicial": 5000, "taxa_reabastecimento_max": 3000}}. Aceita também
            `deficit_provisionado_externamente` (ADR-151, quantidade estrutural a suprir
            de fora) e `preco_provisionamento_externo` (ADR-184, preço dessa quantidade —
            sem ele o déficit é custeado como zero e um aviso é emitido).
          - roster_mo_membro (ADR-173, opcional, só para acao="editar_roster_mo"):
            dict com `individuo_id` (obrigatório) + campos de `MembroEquipeReal`
            (`funcao_id`, `salario_base_mensal`, `data_admissao`, `data_desligamento`,
            ...). `individuo_id` é um identificador opaco de simulação — não precisa
            (e não deve) ser CPF/nome real.
          - roster_eq_ativo (ADR-174, opcional, só para acao="editar_roster_eq"):
            dict com `ativo_id` (obrigatório) + campos de `AtivoEquipamentoReal`
            (`equip_id`, `custo_locacao_mensal_real`, `custo_manutencao_mensal_real`,
            `data_contrato_inicio`, `data_contrato_fim`, ...).

        Para entidade="plano":
          - acao="criar": cria plano no escopo. Requer nome.
          - acao="aprovar": aprova plano. Requer plano_id.
          - acao="arquivar": arquiva plano. Requer plano_id.
        """
        store = _project(project_id)

        if entidade == "escopo":
            if acao == "editar_roster_mo":
                if not roster_mo_membro:
                    return {"erro": "roster_mo_membro obrigatório (ao menos individuo_id) para acao='editar_roster_mo'"}
                try:
                    store.escopo(escopo_id).upsert_roster_mo_membro(roster_mo_membro)
                except Exception as e:
                    return {"erro": str(e)}
                return _wrap_response({"status": "OK", "escopo_id": escopo_id})
            if acao == "editar_roster_eq":
                if not roster_eq_ativo:
                    return {"erro": "roster_eq_ativo obrigatório (ao menos ativo_id) para acao='editar_roster_eq'"}
                try:
                    store.escopo(escopo_id).upsert_roster_eq_ativo(roster_eq_ativo)
                except Exception as e:
                    return {"erro": str(e)}
                return _wrap_response({"status": "OK", "escopo_id": escopo_id})
            try:
                es = store.create_escopo(
                    escopo_id=escopo_id,
                    nome=nome or escopo_id,
                    tipo_obra=tipo_obra or "",
                    localizacao=localizacao or "",
                    coordenadas_lat=coordenadas_lat,
                    coordenadas_lng=coordenadas_lng,
                    data_inicio=data_inicio or "",
                    data_termino=data_termino or "",
                    dias_semana=dias_semana,
                    horas_dia=horas_dia,
                    horas_improdutivas_dia=horas_improdutivas_dia,
                    logistica_consumiveis=logistica_consumiveis,
                )
            except Exception as e:
                return {"erro": str(e)}
            return _wrap_response({"status": "OK", "escopo_id": es.escopo_id})

        elif entidade == "plano":
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
                es.plan(plano_id).archive()
                return _wrap_response({"status": "ARQUIVADO", "plano_id": plano_id})
            return {"erro": f"acao '{acao}' inválida para plano. Use: criar | aprovar | arquivar"}

        return {"erro": f"entidade '{entidade}' inválida. Use: escopo | plano"}
