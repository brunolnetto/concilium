"""Skill 10 — Adapter de Saída (gera JSON + Excel .xlsm) — ponto de equilíbrio particionado por item."""

from typing import Any

from concilium.domain.models.canonical import CanonicalModel


def _rra_build_criticidade_lookup(canonical_in: CanonicalModel) -> dict[str, str]:
    """Builds criticidade_lookup from cost_criticality_report."""
    lookup: dict[str, str] = {}
    if canonical_in.cost_criticality_report is not None:
        for prof in canonical_in.cost_criticality_report.atividades:
            lookup[prof.atividade_id] = prof.classe
    return lookup


def _rra_safe_float(value: Any) -> float:
    """Converte para float com fallback seguro (None/erro -> 0.0)."""
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def _rra_particao_by_item(canonical_in: CanonicalModel) -> dict[str, dict[str, float]]:
    """Agrega custo produtivo/mob_demob/ociosidade particionado por item a partir dos contratos."""
    _f = _rra_safe_float
    particao_by_item: dict[str, dict[str, float]] = {}
    for contrato in canonical_in.contratos_recurso or []:
        for part in getattr(contrato, "particao_por_item", None) or []:
            item_id = getattr(part, "item_id", None)
            if not item_id:
                continue
            acc = particao_by_item.setdefault(
                item_id,
                {
                    "produtivo": 0.0,
                    "mob_demob": 0.0,
                    "ociosidade": 0.0,
                },
            )
            acc["produtivo"] += _f(getattr(part, "custo_produtivo", 0.0))
            acc["mob_demob"] += _f(getattr(part, "custo_mob_imputado", 0.0)) + _f(
                getattr(part, "custo_demob_imputado", 0.0)
            )
            acc["ociosidade"] += _f(getattr(part, "custo_ocioso_imputado", 0.0))
    return particao_by_item


def _rra_totais_globais(
    canonical_in: CanonicalModel, resultado_section: dict[str, Any] | None
) -> tuple[float, float, float]:
    """Resolve venda/custo_direto/custo_indireto globais, com fallback para canonical_in.resultado."""
    _f = _rra_safe_float
    venda_global = _f((resultado_section or {}).get("preco_venda_total"))
    custo_direto_global = _f((resultado_section or {}).get("custo_direto"))
    custo_indireto_global = _f((resultado_section or {}).get("custo_indireto"))

    if venda_global <= 0 and canonical_in.resultado is not None:
        venda_global = _f(canonical_in.resultado.venda.total_com_bdi)
    if custo_direto_global <= 0 and canonical_in.resultado is not None:
        custo_direto_global = _f(canonical_in.resultado.custo.direto_equipes)
    if custo_indireto_global <= 0 and canonical_in.resultado is not None:
        custo_indireto_global = (
            _f(canonical_in.resultado.custo.indireto_adm)
            + _f(canonical_in.resultado.custo.indireto_top)
            + _f(canonical_in.resultado.custo.indireto_lab)
            + _f(canonical_in.resultado.custo.indireto_qsms)
            + _f(canonical_in.resultado.custo.indireto_mob)
        )
    return venda_global, custo_direto_global, custo_indireto_global


def _rra_gap_particionado(
    deficit: float, custo_produtivo: float, custo_mob_demob: float, custo_ociosidade: float
) -> tuple[float, float, float]:
    """Rateia o déficit operacional pelos componentes de custo particionados por item."""
    base_particao = custo_produtivo + custo_mob_demob + custo_ociosidade
    if deficit > 0 and base_particao > 0:
        gap_produtivo = deficit * (custo_produtivo / base_particao)
        gap_mob_demob = deficit * (custo_mob_demob / base_particao)
        gap_ociosidade = deficit * (custo_ociosidade / base_particao)
    else:
        gap_produtivo = 0.0
        gap_mob_demob = 0.0
        gap_ociosidade = 0.0
    return gap_produtivo, gap_mob_demob, gap_ociosidade


def _rra_build_pe_row(
    pe: Any,
    venda_global: float,
    custo_direto_global: float,
    custo_indireto_global: float,
    soma_venda_itens: float,
    n_items: int,
    particao_by_item: dict[str, dict[str, float]],
) -> dict:
    """Constrói uma linha da tabela ponto_equilibrio com margens reconciliadas e gap decomposto."""
    _f = _rra_safe_float
    venda_item = _f(pe.custo_venda_cpu)
    op_item = _f(getattr(pe, "custo_operacional_real", 0.0))
    gap_operacional = venda_item - op_item
    margem_operacional_direta = (gap_operacional / venda_item) if venda_item > 0 else 0.0

    share_receita = (venda_item / soma_venda_itens) if soma_venda_itens > 0 else (1.0 / n_items)
    receita_atribuida = venda_global * share_receita
    custo_direto_atribuido = custo_direto_global * share_receita
    custo_indireto_atribuido = custo_indireto_global * share_receita
    resultado_total_atribuido = receita_atribuida - custo_direto_atribuido - custo_indireto_atribuido
    margem_total_atribuida = (resultado_total_atribuido / receita_atribuida) if receita_atribuida > 0 else 0.0

    part = particao_by_item.get(pe.item_id, {})
    custo_produtivo = _f(part.get("produtivo", 0.0))
    custo_mob_demob = _f(part.get("mob_demob", 0.0))
    custo_ociosidade = _f(part.get("ociosidade", 0.0))

    deficit = max(0.0, op_item - venda_item)
    gap_produtivo, gap_mob_demob, gap_ociosidade = _rra_gap_particionado(
        deficit, custo_produtivo, custo_mob_demob, custo_ociosidade
    )

    return {
        "item_id": pe.item_id,
        "custo_fixo_equipe": pe.custo_fixo_equipe,
        "custo_operacional_real": round(op_item, 2),
        "custo_venda_cpu": round(venda_item, 2),
        "frentes_equivalentes": getattr(pe, "frentes_equivalentes", 1.0),
        "status_validacao": pe.status_validacao,
        "margem_operacional_direta": round(margem_operacional_direta, 6),
        "margem_total_atribuida": round(margem_total_atribuida, 6),
        "receita_atribuida": round(receita_atribuida, 2),
        "custo_direto_atribuido": round(custo_direto_atribuido, 2),
        "custo_indireto_atribuido": round(custo_indireto_atribuido, 2),
        "resultado_total_atribuido": round(resultado_total_atribuido, 2),
        "gap_operacional": round(gap_operacional, 2),
        "gap_produtivo": round(gap_produtivo, 2),
        "gap_mob_demob": round(gap_mob_demob, 2),
        "gap_ociosidade": round(gap_ociosidade, 2),
        "custo_produtivo_particionado": round(custo_produtivo, 2),
        "custo_mob_demob_particionado": round(custo_mob_demob, 2),
        "custo_ociosidade_particionado": round(custo_ociosidade, 2),
        # NEP-042: três camadas de precificação
        "pu_cat": _f(getattr(pe, "pu_catalogo_unitario", 0.0)),
        "pu_op_autonomo": _f(getattr(pe, "pu_operacional_autonomo", 0.0)),
        "frentes_necessarias": _f(getattr(pe, "frentes_equivalentes_necessarias", 1.0)),
        "eta_real": _f(getattr(pe, "eta_real", 1.0)),
        "machine_weeks_brutas": _f(getattr(pe, "machine_weeks_brutas", 0.0)),
        "machine_weeks_efetivas": _f(getattr(pe, "machine_weeks_efetivas", 0.0)),
        "burden_pool": _f(getattr(pe, "custo_pool_total", 0.0)),
        "economia_pool_abs": _f(getattr(pe, "economia_pool_abs", 0.0)),
        # ADR-162 D1/D3: diagnóstico causal (cronograma × precificação) e intervalo de
        # horas reais tolerado por Γ — None quando não resolvível (H_i/ρ_i ausentes ou Γ
        # não configurado no perfil), nunca um valor inventado.
        "causa_dominante": getattr(pe, "causa_dominante", "INDETERMINADO"),
        "horas_reais_min": getattr(pe, "horas_reais_min", None),
        "horas_reais_max": getattr(pe, "horas_reais_max", None),
    }


def _rra_build_pe_rows(canonical_in: CanonicalModel, resultado_section: dict[str, Any] | None = None) -> list[dict]:
    """Builds ponto_equilibrio list for report with reconciled margins and gap decomposition."""

    pe_items = list(canonical_in.ponto_equilibrio or [])
    if not pe_items:
        return []

    particao_by_item = _rra_particao_by_item(canonical_in)
    venda_global, custo_direto_global, custo_indireto_global = _rra_totais_globais(canonical_in, resultado_section)

    soma_venda_itens = sum(_rra_safe_float(pe.custo_venda_cpu) for pe in pe_items)
    n_items = max(1, len(pe_items))

    return [
        _rra_build_pe_row(
            pe,
            venda_global,
            custo_direto_global,
            custo_indireto_global,
            soma_venda_itens,
            n_items,
            particao_by_item,
        )
        for pe in pe_items
    ]


