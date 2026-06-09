from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _bfc_custo_indireto(custo: object) -> float:
    return round(
        (getattr(custo, "indireto_adm", 0) or 0)
        + (getattr(custo, "indireto_top", 0) or 0)
        + (getattr(custo, "indireto_lab", 0) or 0)
        + (getattr(custo, "indireto_qsms", 0) or 0)
        + (getattr(custo, "indireto_mob", 0) or 0),
        2,
    )


def _bfc_custo_direto_total(custo: object, custo_indireto: float) -> tuple[float | None, float | None]:
    custo_direto = getattr(custo, "direto_equipes", None)
    if custo_direto is not None and custo_indireto is not None:
        return custo_direto, round(custo_direto + custo_indireto, 2)
    return custo_direto, getattr(custo, "total", None)


def _bfc_preco_venda(venda: object, custo_total: float | None) -> tuple[float | None, float | None]:
    """Retorna (raw_bdi_lucro, preco_venda).

    Fonte primária: ``total_com_bdi`` — o preço operacional honesto (custo instancial × BDI,
    conforme ADR-085 D5 / refactoring de pricing). O catálogo (``total_custo_plus_catalogo``)
    fica como campo diagnóstico ``preco_venda_catalogo`` no ferramenta.
    """
    raw_bdi_lucro = getattr(venda, "bdi_lucro_impostos", None) if venda else None
    # Preço operacional honesto (total_com_bdi = venda_plus após refactoring)
    preco_venda_op = getattr(venda, "total_com_bdi", None) if venda else None
    if preco_venda_op is not None:
        return raw_bdi_lucro, round(preco_venda_op, 2)
    # Fallback: catálogo ou derivado do markup
    preco_venda_cat = getattr(venda, "total_custo_plus_catalogo", None) if venda else None
    if preco_venda_cat is not None:
        return raw_bdi_lucro, round(preco_venda_cat, 2)
    if raw_bdi_lucro is not None and custo_total is not None:
        return raw_bdi_lucro, round(custo_total * (1 + raw_bdi_lucro), 2)
    return raw_bdi_lucro, None


def _bfc_bdi_lucro(preco_venda: float | None, custo_total: float | None, raw_bdi_lucro: float | None) -> float:
    """Retorna o markup efetivo (BDI + lucro + impostos) como fração.

    Prefere ``raw_bdi_lucro`` de ``Venda.bdi_lucro_impostos``, que já é calculado sobre
    o custo operacional real (``venda_plus / custo_operacional_real − 1``, skill-08).
    Isso evita o erro de usar custo de catálogo (R$66M) como denominador de um preço
    operacional (R$103M), que geraria markup artificialmente inflado (≈55%).
    """
    if raw_bdi_lucro is not None:
        return raw_bdi_lucro  # já correto: venda_plus / custo_op_real − 1
    if preco_venda is not None and custo_total:
        return (preco_venda / custo_total) - 1
    return 0.15


def _build_ferramenta_custo(custo: Any, venda: Any) -> tuple[dict[str, Any], float | None, float | None]:
    """Retorna (ferramenta_dict, custo_direto, custo_indireto)."""
    custo_indireto = _bfc_custo_indireto(custo)
    custo_direto, custo_total = _bfc_custo_direto_total(custo, custo_indireto)
    raw_bdi_lucro, preco_venda = _bfc_preco_venda(venda, custo_total)
    bdi_lucro = _bfc_bdi_lucro(preco_venda, custo_total, raw_bdi_lucro)
    ferramenta = {
        "custo_direto": custo_direto,
        "custo_direto_equipes": getattr(custo, "direto_equipes", None),
        "custo_direto_pu_q": getattr(venda, "total_sem_bdi", None) if venda else None,
        "custo_indireto": custo_indireto,
        "custo_total": custo_total,
        "preco_venda": preco_venda,
        "preco_venda_plus_eq": getattr(venda, "total_custo_plus", None) if venda else None,
        # preco_venda_catalogo: referência de benchmarking (PU×Q×BDI) — total_custo_plus_catalogo
        # total_com_bdi agora é o preço operacional honesto (custo instancial × BDI)
        "preco_venda_catalogo": getattr(venda, "total_custo_plus_catalogo", None) if venda else None,
        "preco_venda_operacional": getattr(venda, "total_com_bdi", None) if venda else None,
        "bdi_lucro_impostos": bdi_lucro,
    }
    return ferramenta, custo_direto, custo_indireto


def _build_breakdown_indireto(custo: Any, custo_indireto: float | None) -> dict[str, Any]:
    return {
        "adm": round(getattr(custo, "indireto_adm", 0.0) or 0.0, 2),
        "top": round(getattr(custo, "indireto_top", 0.0) or 0.0, 2),
        "lab": round(getattr(custo, "indireto_lab", 0.0) or 0.0, 2),
        "qsms": round(getattr(custo, "indireto_qsms", 0.0) or 0.0, 2),
        "mob": round(getattr(custo, "indireto_mob", 0.0) or 0.0, 2),
        "total": round(custo_indireto or 0.0, 2),
    }


def _build_breakdown_direto_pu_q(cat_totals: dict[str, float], custo_direto: Any, eq_total: float) -> dict[str, Any]:
    cat_total = cat_totals["total"]
    total_from_components = (
        cat_totals["mao_obra"] + cat_totals["equipamentos"] + cat_totals["diesel"] + cat_totals["materiais"]
    )
    computed_catalog_total = cat_total if cat_total > 0 else total_from_components
    primary_total = float(custo_direto) if custo_direto is not None else computed_catalog_total
    return {
        "base": "pu_q",
        "mao_obra_total": round(cat_totals["mao_obra"], 2),
        "equipamentos_total": round(cat_totals["equipamentos"], 2),
        "diesel_total": round(cat_totals["diesel"], 2),
        "materiais_total": round(cat_totals["materiais"], 2),
        "direto_total": round(primary_total, 2),
        "direto_total_pu_q": round(computed_catalog_total, 2),
        "direto_total_equipes": round(eq_total, 2),
    }


def _build_breakdown_direto_equipes(eq_totals: dict[str, float]) -> dict[str, Any]:
    return {
        "base": "equipes",
        "mao_obra_total": round(eq_totals["mao_obra"], 2),
        "equipamentos_total": round(eq_totals["equipamentos"], 2),
        "diesel_total": round(eq_totals["diesel"], 2),
        "materiais_total": round(eq_totals["materiais"], 2),
        "direto_total": round(eq_totals["total"], 2),
        "direto_total_equipes": round(eq_totals["total"], 2),
    }


def _accumulate_planejamento(planejamento: list) -> tuple[bool, dict[str, float]]:
    totals = {"mao_obra": 0.0, "equipamentos": 0.0, "diesel": 0.0, "materiais": 0.0, "total": 0.0}
    has_catalog = False
    for plan_item in planejamento:
        subtotal = getattr(plan_item, "subtotal", None)
        sem_bdi = getattr(subtotal, "sem_bdi", None) if subtotal is not None else None
        if sem_bdi is None:
            continue
        has_catalog = True
        totals["mao_obra"] += float(getattr(sem_bdi, "mao_obra", 0.0) or 0.0)
        totals["equipamentos"] += float(getattr(sem_bdi, "equipamentos", 0.0) or 0.0)
        totals["diesel"] += float(getattr(sem_bdi, "diesel", 0.0) or 0.0)
        totals["materiais"] += float(getattr(sem_bdi, "material", 0.0) or 0.0)
        totals["total"] += float(getattr(sem_bdi, "total", 0.0) or 0.0)
    return has_catalog, totals


def _accumulate_equipes(equipes_diretas: list) -> dict[str, float]:
    """Acumula custos por categoria a partir de custo_inst_* quando disponível.

    Dois paths:
    1. Estágio 4 (com pool contracts): usa custo_inst_* (decomposição oficial — ADR-104)
    2. Estágio 1/3 (sem pool): fallback heurístico — menos preciso mas funciona
    """
    totals = {"mao_obra": 0.0, "equipamentos": 0.0, "diesel": 0.0, "materiais": 0.0, "total": 0.0}

    for equipe in equipes_diretas:
        # PATH 1: Se tem decomposição instancial (Estágio 4), usar dados oficiais (ADR-104)
        if equipe.custo_inst_mo is not None:
            totals["mao_obra"] += equipe.custo_inst_mo
            totals["equipamentos"] += equipe.custo_inst_eq
            totals["diesel"] += equipe.custo_inst_comb
            totals["materiais"] += equipe.custo_inst_mat
            # custo_inst_mob_demob já está em custo_total, não somar separado
        # PATH 2: Sem decomposição, fallback (Estágio 1/3, sem pool contracts)
        else:
            if equipe.custo_fixo_mensal > 0:
                fator = equipe.custo_total / equipe.custo_fixo_mensal
                totals["mao_obra"] += equipe.custo_mao_obra_mensal * fator
                totals["equipamentos"] += equipe.custo_equipamentos_mensal * fator
                totals["diesel"] += equipe.custo_combustivel_total_mensal * fator
                totals["materiais"] += getattr(equipe, "custo_material_mensal", 0.0) * fator

    # ADR-091: Multiplicar custo_total por num_equipes_base para agregação correta
    totals["total"] = sum(
        equipe.custo_total * max(1, getattr(equipe, "num_equipes_base", 1) or 1) for equipe in equipes_diretas
    )
    return totals


def _build_actionable_insights(canonical: Any) -> dict[str, Any]:
    insights: dict[str, Any] = {}
    _bai_fill_criticidade(insights, canonical)
    _bai_fill_sensibilidade(insights, canonical)
    _bai_fill_intervencao(insights, canonical)
    return insights


def _bai_fill_criticidade(insights: dict, canonical: Any) -> None:
    report = getattr(canonical, "cost_criticality_report", None)
    if report is None:
        return
    ats = report.atividades
    count_a = sum(1 for a in ats if a.classe == "A")
    count_b = sum(1 for a in ats if a.classe == "B")
    count_c = sum(1 for a in ats if a.classe == "C")
    insights["criticidade"] = f"{count_a} A, {count_b} B, {count_c} C"


def _bai_fill_sensibilidade(insights: dict, canonical: Any) -> None:
    rel = getattr(canonical, "relatorio_sensibilidade", None)
    if rel is None:
        return
    n_rep = len(getattr(rel, "passos_repair", []))
    n_opp = len(getattr(rel, "oportunidades", []))
    insights["sensibilidade"] = f"{n_rep} alavancas corretivas, {n_opp} oportunidades"


def _bai_fill_intervencao(insights: dict, canonical: Any) -> None:
    relatorio = getattr(canonical, "relatorio_executivo", None) or getattr(canonical, "relatorio_intervencao", None)
    if relatorio is None:
        return
    rec = relatorio.recomendacao_primaria
    insights["intervencao"] = f"Recomendacao Principal: {rec.nome if rec else 'Nenhuma'}"


@dataclass
class BenchmarkProjection:
    ferramenta: dict[str, Any] = field(default_factory=dict)
    ponto_equilibrio_ferramenta: dict[str, Any] | None = None
    ferramenta_breakdown_direto: dict[str, Any] | None = None
    ferramenta_breakdown_indireto: dict[str, Any] | None = None
    actionable_insights: dict[str, Any] | None = None

    def _populate_resultado(self, resultado: Any) -> tuple[Any, Any]:
        """Popula ferramenta, breakdown_indireto e PE. Retorna (custo_direto, custo_indireto)."""
        custo = getattr(resultado, "custo", None)
        venda = getattr(resultado, "venda", None)
        custo_direto = None
        custo_indireto = None
        if custo is not None:
            self.ferramenta, custo_direto, custo_indireto = _build_ferramenta_custo(custo, venda)
            self.ferramenta_breakdown_indireto = _build_breakdown_indireto(custo, custo_indireto)
        balanco_pe = getattr(resultado, "balanco_ponto_equilibrio", None)
        if balanco_pe:
            self.ponto_equilibrio_ferramenta = {
                "total_hc_operacional": getattr(balanco_pe, "total_hc_operacional", None),
                "total_hc_indireto": getattr(balanco_pe, "total_hc_indireto", None),
                "total_hc": getattr(balanco_pe, "total_hc", None),
                "custo_fixo_mensal": getattr(balanco_pe, "custo_fixo_mensal", None),
                "custo_fixo_total": getattr(balanco_pe, "custo_fixo_total", None),
                "equipes": getattr(balanco_pe, "numero_equipes_diretas", None),
            }
        return custo_direto, custo_indireto

    def _populate_breakdown_direto(self, canonical: Any, custo_direto: Any) -> None:
        equipes_diretas = getattr(canonical, "equipes_diretas", None) or []
        planejamento = getattr(canonical, "planejamento", None) or []
        has_catalog, cat_totals = _accumulate_planejamento(planejamento)
        eq_totals = _accumulate_equipes(equipes_diretas) if equipes_diretas else {}
        eq_total = eq_totals.get("total", 0.0)
        if has_catalog:
            self.ferramenta_breakdown_direto = _build_breakdown_direto_pu_q(cat_totals, custo_direto, eq_total)
        elif equipes_diretas:
            self.ferramenta_breakdown_direto = _build_breakdown_direto_equipes(eq_totals)

    @classmethod
    def from_canonical(cls, canonical: Any) -> BenchmarkProjection:
        projection = cls()
        if canonical is None:
            return projection
        resultado = getattr(canonical, "resultado", None)
        custo_direto = None
        if resultado is not None:
            custo_direto, _ = projection._populate_resultado(resultado)
        projection._populate_breakdown_direto(canonical, custo_direto)
        insights = _build_actionable_insights(canonical)
        if insights:
            projection.actionable_insights = insights
        return projection
