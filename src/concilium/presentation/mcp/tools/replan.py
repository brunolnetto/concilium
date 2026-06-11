"""Ferramentas MCP de Replanejamento e Simulação — ADR-037 / ADR-101 F4."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP


def _simular_lever_adjust(canonical: Any, parametros: dict) -> dict:
    """Estimativa linear do impacto de levers sobre os PEs sem re-executar o pipeline.

    Modela o efeito de mudanças de regime (horas/dia, dias/semana) e
    de capacidade (fator_equipes) sobre frentes_equivalentes_necessarias.

    Não substitui a execução do pipeline — fornece feedback imediato ao
    engenheiro antes de decidir se vale re-planejar formalmente.
    """
    fator_eq = float(parametros.get("fator_equipes", 1.0))
    horas_dia = int(parametros.get("horas_dia", 0)) or None
    dias_sem   = int(parametros.get("dias_semana", 0)) or None
    meta_margem = float(parametros.get("meta_margem_pct", 0.10))

    regime = getattr(canonical, "projeto", None)
    regime = getattr(regime, "regime_trabalho", None) if regime else None
    base_horas = float(getattr(regime, "horas_dia", 8) or 8)
    base_dias  = float(getattr(regime, "dias_semana", 6) or 6)

    horas_novo = float(horas_dia) if horas_dia else base_horas
    dias_novo  = float(dias_sem)  if dias_sem  else base_dias

    prod_factor = (fator_eq * horas_novo * dias_novo) / (1.0 * base_horas * base_dias)

    pes = list(getattr(canonical, "ponto_equilibrio", []) or [])
    resultado = getattr(canonical, "resultado", None)

    itens_sim = []
    total_custo_atual = 0.0
    total_custo_novo  = 0.0

    for pe in pes:
        fe_atual = float(getattr(pe, "frentes_equivalentes_necessarias", 1.0) or 1.0)
        fe_novo  = fe_atual / prod_factor if prod_factor > 0 else fe_atual
        c_atual  = float(getattr(pe, "custo_operacional_real", 0.0) or 0.0)
        c_novo   = c_atual * prod_factor
        total_custo_atual += c_atual
        total_custo_novo  += c_novo
        status_novo = "OK" if fe_novo <= 1.25 else ("AVISO" if fe_novo <= 1.5 else "CRITICO")
        itens_sim.append({
            "item_id": pe.item_id,
            "fe_nec_atual":  round(fe_atual, 3),
            "fe_nec_estimado": round(fe_novo, 3),
            "custo_atual": round(c_atual, 2),
            "custo_estimado": round(c_novo, 2),
            "status_frentes_estimado": status_novo,
        })

    n_crit_atual = sum(1 for it in itens_sim if it["fe_nec_atual"] > 1.25)
    n_crit_novo  = sum(1 for it in itens_sim if it["fe_nec_estimado"] > 1.25)
    fe_med_atual = (sum(it["fe_nec_atual"] for it in itens_sim) / len(itens_sim)) if itens_sim else 0
    fe_med_novo  = (sum(it["fe_nec_estimado"] for it in itens_sim) / len(itens_sim)) if itens_sim else 0

    custo_indireto = 0.0
    if resultado and resultado.custo:
        for k in ("indireto_adm", "indireto_top", "indireto_lab", "indireto_qsms", "indireto_mob"):
            custo_indireto += float(getattr(resultado.custo, k, 0.0) or 0.0)

    venda = float(getattr(getattr(resultado, "venda", None), "total_com_bdi", 0.0) or 0.0) if resultado else 0.0
    margem_atual = (venda - total_custo_atual - custo_indireto) / venda if venda > 0 else 0.0
    margem_nova  = (venda - total_custo_novo  - custo_indireto) / venda if venda > 0 else 0.0

    return {
        "tipo": "lever_adjust",
        "parametros_aplicados": {
            "fator_equipes": fator_eq,
            "horas_dia_novo": horas_novo,
            "dias_semana_novo": dias_novo,
            "prod_factor": round(prod_factor, 4),
        },
        "resumo": {
            "fe_nec_medio_atual": round(fe_med_atual, 3),
            "fe_nec_medio_estimado": round(fe_med_novo, 3),
            "itens_criticos_atual": n_crit_atual,
            "itens_criticos_estimado": n_crit_novo,
            "custo_direto_atual": round(total_custo_atual, 2),
            "custo_direto_estimado": round(total_custo_novo, 2),
            "delta_custo": round(total_custo_novo - total_custo_atual, 2),
            "margem_pct_atual": round(margem_atual, 4),
            "margem_pct_estimada": round(margem_nova, 4),
            "meta_margem_pct": meta_margem,
            "meta_atingida_estimada": margem_nova >= meta_margem,
        },
        "itens": itens_sim,
        "nota": (
            "Estimativa linear sem re-execução do pipeline. "
            "Para resultado definitivo use avancar_pipeline após aplicar parâmetros."
        ),
    }


def register(server: FastMCP) -> None:
    """Registra as ferramentas consolidadas de replanejamento."""

    @server.tool()
    def simular_cenario_replan(
        project_id: str,
        tipo: str,
        parametros: dict[str, Any],
        incluir_indiretos: bool = True,
    ) -> dict[str, Any]:
        """Simula o impacto de mudanças de levers operacionais sem re-executar o pipeline.

        Tipos suportados:
          - ``lever_adjust``: ajuste de fator_equipes, horas_dia, dias_semana, meta_margem_pct

        Para replanejamento definitivo, use ``avancar_pipeline`` após confirmar os parâmetros.
        """
        try:
            from concilium.application.services.project_service import ProjectService

            svc = ProjectService()
            canonical = svc.load_canonical_latest(project_id)
            if canonical is None:
                return {"erro": f"Canonical não encontrado para projeto '{project_id}'."}

            if tipo == "lever_adjust":
                return _simular_lever_adjust(canonical, parametros)

            return {
                "erro": f"Tipo '{tipo}' não suportado. Use 'lever_adjust'.",
                "tipos_suportados": ["lever_adjust"],
            }
        except Exception as exc:
            return {"erro": f"Erro ao simular cenário: {exc}"}

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
