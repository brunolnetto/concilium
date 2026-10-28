"""ADR-070 — Campaign service (parte extraída de campaign_service.py)."""

from __future__ import annotations

from typing import Any

from concilium.domain.models.campaign.campaign import (
    VetorEspacoEF,
    VetorEspacoO,
)


def _prazo_semanas_vetor_O(canonical: dict) -> int | None:
    cron = canonical.get("cronograma") or {}
    prazo = cron.get("makespan_semanas")
    # Fallback: max end_week from scheduled_activities
    if prazo is None:
        acts = cron.get("scheduled_activities") or []
        if acts:
            prazo = max((a.get("end_week") or 0) for a in acts)
    return prazo


def _fe_metrics_vetor_O(canonical: dict) -> tuple[float | None, float | None]:
    """Retorna (fe_nec_medio, itens_criticos_pct) a partir de ponto_equilibrio."""
    pes = canonical.get("ponto_equilibrio") or []
    fe_list = [
        pe.get("frentes_equivalentes_necessarias")
        for pe in pes
        if pe.get("frentes_equivalentes_necessarias") is not None
    ]
    fe_med = sum(fe_list) / len(fe_list) if fe_list else None
    n_crit = sum(1 for fe in fe_list if fe > 1.25) if fe_list else 0
    itens_crit_pct = n_crit / len(fe_list) if fe_list else None
    return fe_med, itens_crit_pct


def _montar_vetor_O(
    prazo: int | None,
    folga: float | None,
    fe_med: float | None,
    itens_crit_pct: float | None,
    gap_pool: float,
    mob_window: float,
    util: dict[str, Any],
) -> VetorEspacoO:
    return VetorEspacoO(
        prazo_semanas=prazo,
        folga_semanas=round(folga, 1) if folga is not None else None,
        fe_nec_medio=round(fe_med, 3) if fe_med is not None else None,
        itens_criticos_pct=round(itens_crit_pct, 3) if itens_crit_pct is not None else None,
        gap_pool_total=gap_pool,
        custo_mob_window_total=mob_window,
        utilizacao_recursos_pct=util.get("utilizacao"),
        paralelismo_medio=util.get("paralelismo"),
        idle_pool_pct=util.get("idle_pct"),
    )


def extrair_vetor_O(canonical: dict, prazo_contratual: int | None) -> VetorEspacoO:
    prazo = _prazo_semanas_vetor_O(canonical)
    folga = (prazo_contratual - prazo) if (prazo is not None and prazo_contratual) else None

    fe_med, itens_crit_pct = _fe_metrics_vetor_O(canonical)

    pes = canonical.get("ponto_equilibrio") or []
    gap_pool = round(sum(pe.get("gap_pool_overhead") or 0 for pe in pes), 2)

    eqs = canonical.get("equipes_diretas") or []
    mob_window = round(sum(e.get("custo_inst_mob_demob") or 0 for e in eqs), 2)

    # ADR-108: métricas de utilização e paralelismo do cronograma
    util = _cronograma_utilizacao(canonical)

    return _montar_vetor_O(prazo, folga, fe_med, itens_crit_pct, gap_pool, mob_window, util)


def _cubo_analitico_agregado(canonical: dict) -> dict[str, Any]:
    """Agrega cubo_analitico.celulas por categoria/propriedade (ADR-108).

    Retorna {share_mo, share_eq, share_comb, hhi} em [0,1].
    Retorna {} quando cubo vazio — caller atribui None (IC-4: sem falha silenciosa).
    """
    cubo = canonical.get("cubo_analitico") or {}
    celulas = cubo.get("celulas") or []
    if not celulas:
        return {}

    total, mo, eq, comb, por_atividade = _acumular_custos_por_categoria(celulas)

    if total <= 0:
        return {}

    hhi = round(sum((v / total) ** 2 for v in por_atividade.values()), 4) if por_atividade else None
    return {
        "share_mo": round(mo / total, 4),
        "share_eq": round(eq / total, 4),
        "share_comb": round(comb / total, 4),
        "hhi": hhi,
    }


def _acumular_uma_celula_custo(
    c: dict,
    acc: tuple[float, float, float, float, dict[str, float]],
) -> tuple[float, float, float, float, dict[str, float]]:
    total, mo, eq, comb, por_atividade = acc
    v = float(c.get("valor_rs") or 0.0)
    total += v
    cat = (c.get("categoria_insumo") or "").lower()
    prop = (c.get("propriedade") or "").lower()
    aid = c.get("atividade_id") or ""
    if cat == "mao_obra":
        mo += v
    elif cat == "equipamento":
        eq += v
    if prop == "combustivel":
        comb += v
    if aid:
        por_atividade[aid] = por_atividade.get(aid, 0.0) + v
    return total, mo, eq, comb, por_atividade


def _acumular_custos_por_categoria(
    celulas: list[dict],
) -> tuple[float, float, float, float, dict[str, float]]:
    """Acumula total/mao_obra/equipamento/combustivel e custo por atividade_id."""
    acc: tuple[float, float, float, float, dict[str, float]] = (0.0, 0.0, 0.0, 0.0, {})

    for c in celulas:
        if c.get("componente_bdi") != "custo_direto":
            continue
        acc = _acumular_uma_celula_custo(c, acc)

    return acc


def _cronograma_utilizacao(canonical: dict) -> dict[str, Any]:
    """Extrai métricas de utilização e paralelismo do cronograma (ADR-108)."""
    cron = canonical.get("cronograma") or {}
    acts = cron.get("scheduled_activities") or []
    if not acts:
        return {}

    utilizacao = _utilizacao_recursos(acts)
    paralelismo = _paralelismo_medio(acts)
    idle_pct = _idle_pool_pct(canonical)

    return {"utilizacao": utilizacao, "paralelismo": paralelismo, "idle_pct": idle_pct}


def _utilizacao_recursos(acts: list[dict]) -> float | None:
    total_mob = 0
    total_prod = 0
    for a in acts:
        dist = a.get("distribuicao_semanal") or {}
        total_mob += len(dist)
        total_prod += sum(1 for d in dist.values() if (d.get("num_equipes") or 0) > 0)
    return round(total_prod / total_mob, 4) if total_mob > 0 else None


def _paralelismo_medio(acts: list[dict]) -> float | None:
    semanas: dict[str, int] = {}
    for a in acts:
        for semana, d in (a.get("distribuicao_semanal") or {}).items():
            if (d.get("num_equipes") or 0) > 0:
                semanas[semana] = semanas.get(semana, 0) + 1
    return round(sum(semanas.values()) / len(semanas), 3) if semanas else None


def _idle_pool_pct(canonical: dict) -> float | None:
    """CuboPoolFace quando disponível (ADR-106 F8)."""
    pool_face = canonical.get("cubo_pool_face")
    idle_pct: float | None = None
    if pool_face and isinstance(pool_face, dict):
        celulas_pf = pool_face.get("celulas") or []
        total_pf = len(celulas_pf)
        idle_sem = sum(1 for c in celulas_pf if (c.get("estado") or "") == "idle")
        idle_pct = round(idle_sem / total_pf, 4) if total_pf > 0 else None
    return idle_pct


def _custo_indireto_total(custo: dict) -> float:
    return round(
        sum(v for k, v in custo.items() if "indireto" in k and isinstance(v, (int, float))),
        2,
    )


def _ratio_pool_vs_cat(custo_pool: float | None, pu_q: float | None) -> float | None:
    return round(custo_pool / pu_q, 4) if (custo_pool and pu_q and pu_q > 0) else None


def _fidelidade_gates(report: dict) -> bool | None:
    gates = (report.get("quality_gates") or {}) if report else {}
    decision = gates.get("decision")
    if not decision or decision == "NOT_EVALUATED":
        return None
    return decision in {"APROVADO", "APROVADO_COM_RESSALVAS"}


def _montar_vetor_EF(
    margem: float | None,
    custo_pool: float | None,
    custo_ind: float,
    preco_venda: float | None,
    ratio: float | None,
    comp: dict[str, Any],
    fidelidade: bool | None,
) -> VetorEspacoEF:
    return VetorEspacoEF(
        margem_pct=round(margem, 4) if margem is not None else None,
        custo_execucao_pool=custo_pool,
        custo_indireto=custo_ind if custo_ind else None,
        preco_venda=preco_venda,
        ratio_pool_vs_cat=ratio,
        share_mo_pct=comp.get("share_mo"),
        share_eq_pct=comp.get("share_eq"),
        share_comb_pct=comp.get("share_comb"),
        concentracao_atividade=comp.get("hhi"),
        fidelidade_gates=fidelidade,
    )


def extrair_vetor_EF(canonical: dict, report: dict) -> VetorEspacoEF:
    resultado = canonical.get("resultado") or {}
    custo = resultado.get("custo") or {}
    venda = resultado.get("venda") or {}

    margem = resultado.get("margem_pct")
    custo_pool = custo.get("direto_equipes")
    custo_ind = _custo_indireto_total(custo)
    preco_venda = venda.get("total_com_bdi")
    pu_q = venda.get("total_sem_bdi")
    ratio = _ratio_pool_vs_cat(custo_pool, pu_q)

    fidelidade = _fidelidade_gates(report)

    # ADR-108: composição de custo do cubo_analitico
    comp = _cubo_analitico_agregado(canonical)

    return _montar_vetor_EF(margem, custo_pool, custo_ind, preco_venda, ratio, comp, fidelidade)


