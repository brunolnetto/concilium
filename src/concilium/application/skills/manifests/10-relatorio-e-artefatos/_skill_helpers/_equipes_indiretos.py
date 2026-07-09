"""Skill 10 — Adapter de Saída (gera JSON + Excel .xlsm) — linhas de EQUIPE (break-even) e INDIRETOS."""

from typing import Any

from concilium.domain.models.canonical import CanonicalModel


def _ber_acao_sugerida(gap: float, dominante: str) -> str:
    """Sugere uma ação corretiva com base no gap operacional e no componente dominante."""
    if gap >= 0:
        return "Manter baseline"
    if dominante == "Diesel":
        return "Rever logística e consumo de combustível"
    if dominante == "Mão de Obra":
        return "Ajustar produtividade/equipe"
    if dominante == "Equipamentos":
        return "Otimizar frota e utilização"
    if dominante == "Materiais":
        return "Rever traço e perdas de material"
    return "Rebalancear composição operacional"


def _ber_componentes_operacionais(eq: Any, custo_operacional: float) -> dict[str, float]:
    """Distribui o custo_operacional_real pelos componentes mensais da equipe (proporcional)."""
    mensal = {
        "Mão de Obra": float(eq.custo_mao_obra_mensal or 0.0),
        "Encargos Sociais": float(getattr(eq, "custo_encargos_mensal", 0.0) or 0.0),
        "Equipamentos": float(eq.custo_equipamentos_mensal or 0.0),
        "Materiais": float(eq.custo_material_mensal or 0.0),
        "Diesel": float(eq.custo_combustivel_total_mensal or 0.0),
    }
    base = sum(mensal.values())
    if base <= 0 or custo_operacional <= 0:
        return {k: 0.0 for k in mensal}
    fator = custo_operacional / base
    return {k: v * fator for k, v in mensal.items()}


def _ber_componentes_referencia(item_id: str, plan_by_item: dict) -> dict[str, float] | None:
    """Extrai os componentes de custo de referência (subtotal sem BDI) do planejamento."""
    plan = plan_by_item.get(item_id)
    if plan is None or plan.subtotal is None or plan.subtotal.sem_bdi is None:
        return None
    sem = plan.subtotal.sem_bdi
    return {
        "Mão de Obra": float(sem.mao_obra or 0.0),
        "Equipamentos": float(sem.equipamentos or 0.0),
        "Materiais": float(sem.material or 0.0),
        "Diesel": float(sem.diesel or 0.0),
    }


def _ber_componente_dominante(eq: Any, custo_operacional: float, gap_operacional: float, plan_by_item: dict) -> str:
    """Identifica o componente de custo que mais explica o gap operacional vs. referência."""
    componentes_op = _ber_componentes_operacionais(eq, custo_operacional)
    referencia = _ber_componentes_referencia(eq.item_id, plan_by_item)
    if referencia:
        delta_comp = {k: componentes_op[k] - referencia.get(k, 0.0) for k in componentes_op}
        if gap_operacional < 0:
            # Déficit: dominante é o componente que mais contribui para estouro vs referência.
            positivos = {k: v for k, v in delta_comp.items() if v > 0}
            if positivos:
                return max(positivos.items(), key=lambda kv: kv[1])[0]
        else:
            # Superávit: dominante é o componente com maior economia vs referência.
            economias = {k: -v for k, v in delta_comp.items() if v < 0}
            if economias:
                return max(economias.items(), key=lambda kv: kv[1])[0]
    # Fallback estável quando não há referência por componente.
    return max(componentes_op.items(), key=lambda kv: kv[1])[0]


def _ber_build_rows(eq: Any, pe: Any, plan_by_item: dict) -> tuple[dict, dict]:
    """Constrói (equipe_row, analise_composicional_row) para uma equipe direta."""
    custo_operacional = float(getattr(pe, "custo_operacional_real", 0.0) if pe is not None else eq.custo_total or 0.0)
    custo_venda = float(getattr(pe, "custo_venda_cpu", 0.0) if pe is not None else 0.0)
    gap_operacional = round(custo_venda - custo_operacional, 2)
    # Gap percentual relativo ao custo operacional (mais interpretável para eficiência real).
    gap_pct = (gap_operacional / custo_operacional) if custo_operacional > 0 else 0.0
    dominante = _ber_componente_dominante(eq, custo_operacional, gap_operacional, plan_by_item)

    equipe_row = {
        "equipe_id": eq.equipe_id,
        "item_id": eq.item_id,
        "cpu_id": eq.cpu_id,
        "custo_fixo_total": round(eq.custo_fixo_mensal * (eq.permanencia_meses or 0.0), 2),
        "custo_total": eq.custo_total,
        "permanencia_meses": eq.permanencia_meses,
        "delta_pct": (getattr(pe, "delta_pct", None) if pe is not None else None),
        "status_pe": (getattr(pe, "status_validacao", "N/A") if pe is not None else "N/A"),
        # custo_venda_cpu: None quando não há ponto de equilíbrio calculado para o item
        "custo_venda_cpu": (getattr(pe, "custo_venda_cpu", None) if pe is not None else None),
    }
    analise_row = {
        "item_id": eq.item_id,
        "custo_venda_cpu": round(custo_venda, 2),
        "custo_operacional_real": round(custo_operacional, 2),
        "gap_operacional": gap_operacional,
        "gap_pct": round(gap_pct, 6),
        "dominante": dominante,
        "acao_sugerida": _ber_acao_sugerida(gap_operacional, dominante),
        "custo_mao_obra": eq.custo_mao_obra_mensal,
        "custo_equipamentos": eq.custo_equipamentos_mensal,
        "custo_materiais": eq.custo_material_mensal,
        "custo_diesel": eq.custo_combustivel_total_mensal,
    }
    return equipe_row, analise_row


def _build_equipe_rows(canonical_in: CanonicalModel) -> tuple[list[dict], list[dict]]:
    equipe_rows: list[dict] = []
    analise_composicional: list[dict] = []
    pe_by_item = {pe.item_id: pe for pe in (canonical_in.ponto_equilibrio or []) if pe.item_id}
    plan_by_item = {p.item_id: p for p in canonical_in.planejamento if p.item_id}

    for eq in canonical_in.equipes_diretas:
        pe = pe_by_item.get(eq.item_id)
        equipe_row, analise_row = _ber_build_rows(eq, pe, plan_by_item)
        equipe_rows.append(equipe_row)
        analise_composicional.append(analise_row)
    return equipe_rows, analise_composicional


def _build_indireto_rows(canonical_in: CanonicalModel, inputs: dict[str, Any]) -> list[dict]:
    _ = inputs
    rows: list[dict] = []
    for ind in canonical_in.indiretos:
        rows.append(
            {
                "categoria": ind.categoria,
                "descricao": ind.descricao,
                "permanencia_meses": ind.permanencia_meses,
                "custo_total": ind.custo_total,
            }
        )
    return rows


