"""Ferramentas MCP de Replanejamento e Simulação — ADR-037 / ADR-101 F4."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from concilium.domain.constants import META_MARGEM_PADRAO
from concilium.infrastructure.auth.permission_guard import permission


def _lever_prod_factor(canonical: Any, parametros: dict) -> tuple[float, float, float, float]:
    """Resolve fator_equipes, novos horas/dia e dias/semana, e o prod_factor resultante."""
    fator_eq = float(parametros.get("fator_equipes", 1.0))
    horas_dia = int(parametros.get("horas_dia", 0)) or None
    dias_sem = int(parametros.get("dias_semana", 0)) or None

    regime = getattr(canonical, "projeto", None)
    regime = getattr(regime, "regime_trabalho", None) if regime else None
    base_horas = float(getattr(regime, "horas_dia", 8) or 8)
    base_dias = float(getattr(regime, "dias_semana", 6) or 6)

    horas_novo = float(horas_dia) if horas_dia else base_horas
    dias_novo = float(dias_sem) if dias_sem else base_dias

    prod_factor = (fator_eq * horas_novo * dias_novo) / (1.0 * base_horas * base_dias)
    return fator_eq, horas_novo, dias_novo, prod_factor


def _lever_status_frentes(fe_novo: float) -> str:
    if fe_novo <= 1.25:
        return "OK"
    return "AVISO" if fe_novo <= 1.5 else "CRITICO"


def _lever_simulate_item(pe: Any, prod_factor: float) -> tuple[dict[str, Any], float, float, float, float]:
    fe_atual = float(getattr(pe, "frentes_equivalentes_necessarias", 1.0) or 1.0)
    fe_novo = fe_atual / prod_factor if prod_factor > 0 else fe_atual
    c_atual = float(getattr(pe, "custo_operacional_real", 0.0) or 0.0)
    c_novo = c_atual * prod_factor
    item = {
        "item_id": pe.item_id,
        "fe_nec_atual": round(fe_atual, 3),
        "fe_nec_estimado": round(fe_novo, 3),
        "custo_atual": round(c_atual, 2),
        "custo_estimado": round(c_novo, 2),
        "status_frentes_estimado": _lever_status_frentes(fe_novo),
    }
    return item, round(fe_atual, 3), round(fe_novo, 3), c_atual, c_novo


def _lever_simulate_items(
    pes: list[Any], prod_factor: float
) -> tuple[list[dict[str, Any]], list[float], list[float], float, float]:
    itens_sim: list[dict[str, Any]] = []
    fe_atuais: list[float] = []
    fe_novos: list[float] = []
    total_custo_atual = 0.0
    total_custo_novo = 0.0

    for pe in pes:
        item, fe_atual, fe_novo, c_atual, c_novo = _lever_simulate_item(pe, prod_factor)
        itens_sim.append(item)
        fe_atuais.append(fe_atual)
        fe_novos.append(fe_novo)
        total_custo_atual += c_atual
        total_custo_novo += c_novo

    return itens_sim, fe_atuais, fe_novos, total_custo_atual, total_custo_novo


def _lever_custo_indireto(resultado: Any) -> float:
    custo_indireto = 0.0
    if resultado and resultado.custo:
        for k in ("indireto_adm", "indireto_top", "indireto_lab", "indireto_qsms", "indireto_mob"):
            custo_indireto += float(getattr(resultado.custo, k, 0.0) or 0.0)
    return custo_indireto


def _lever_margens(
    resultado: Any, total_custo_atual: float, total_custo_novo: float, custo_indireto: float
) -> tuple[float, float]:
    venda = float(getattr(getattr(resultado, "venda", None), "total_com_bdi", 0.0) or 0.0) if resultado else 0.0
    margem_atual = (venda - total_custo_atual - custo_indireto) / venda if venda > 0 else 0.0
    margem_nova = (venda - total_custo_novo - custo_indireto) / venda if venda > 0 else 0.0
    return margem_atual, margem_nova


def _simular_lever_adjust(canonical: Any, parametros: dict) -> dict:
    """Estimativa linear do impacto de levers sobre os PEs sem re-executar o pipeline.

    Modela o efeito de mudanças de regime (horas/dia, dias/semana) e
    de capacidade (fator_equipes) sobre frentes_equivalentes_necessarias.

    Não substitui a execução do pipeline — fornece feedback imediato ao
    engenheiro antes de decidir se vale re-planejar formalmente.
    """
    meta_margem = float(parametros.get("meta_margem_pct", META_MARGEM_PADRAO))
    fator_eq, horas_novo, dias_novo, prod_factor = _lever_prod_factor(canonical, parametros)

    pes = list(getattr(canonical, "ponto_equilibrio", []) or [])
    resultado = getattr(canonical, "resultado", None)

    itens_sim, fe_atuais, fe_novos, total_custo_atual, total_custo_novo = _lever_simulate_items(pes, prod_factor)

    n_crit_atual = sum(1 for fe in fe_atuais if fe > 1.25)
    n_crit_novo = sum(1 for fe in fe_novos if fe > 1.25)
    fe_med_atual = (sum(fe_atuais) / len(fe_atuais)) if fe_atuais else 0
    fe_med_novo = (sum(fe_novos) / len(fe_novos)) if fe_novos else 0

    custo_indireto = _lever_custo_indireto(resultado)
    margem_atual, margem_nova = _lever_margens(resultado, total_custo_atual, total_custo_novo, custo_indireto)

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
            "Para resultado definitivo use disparar_pipeline após aplicar parâmetros."
        ),
    }


def register(server: FastMCP) -> None:
    """Registra as ferramentas consolidadas de replanejamento."""

    @server.tool()
    @permission("project:run")
    def simular_cenario_replan(
        project_id: str,
        tipo: str,
        parametros: dict[str, Any],
        incluir_indiretos: bool = True,
    ) -> dict[str, Any]:
        """Simula o impacto de mudanças de levers operacionais sem re-executar o pipeline.

        Tipos suportados:
          - ``lever_adjust``: ajuste de fator_equipes, horas_dia, dias_semana, meta_margem_pct

        Para replanejamento definitivo, use ``disparar_pipeline`` após confirmar os parâmetros.
        """
        try:
            # ProjectService() sem dependências quebrava com TypeError (e o método
            # load_canonical_latest nunca existiu) — o except genérico abaixo mascarava
            # a tool inteira como "Erro ao simular cenário". Usa o mesmo padrão de
            # resolução escopo→plano das tools irmãs (analise.py), com fallback flat.
            from concilium.presentation.mcp._context import _project
            from concilium.presentation.mcp.tools.escopo import _resolve_escopo_id

            store = _project(project_id)
            canonical = None
            try:
                eid = _resolve_escopo_id(store, None)
                es = store.escopo(eid)
                active = es.active_plan()
                if active is not None:
                    canonical = es.plan(active.plano_id).load_canonical()
            except Exception:
                canonical = None
            if canonical is None:
                canonical = store.load_canonical()
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
