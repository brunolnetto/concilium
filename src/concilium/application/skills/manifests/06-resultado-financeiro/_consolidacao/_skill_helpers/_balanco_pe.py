"""Skill 06 (_consolidacao) — Consolidação Financeira (parte extraída de _skill_helpers_a.py)."""

from __future__ import annotations

from typing import Any

from concilium.domain.models.canonical import (
    CanonicalModel,
    CustoParticionadoItem,
    PontoEquilibrio,
    ValidacaoItem,
)

from ._ponto_equilibrio import (  # ty: ignore[unresolved-import]
    _apply_pe_mitigacao,
    _build_pe_for_equipe,
    _validate_frentes_necessarias,
    _validate_pe_duplo_risco,
    _validate_pe_particao,
    _validate_prod_pu_fallback_desync,
    _validate_prod_vs_pu,
)


def _bpe_process_equipe(
    equipe: Any,
    venda_por_item: dict,
    validacoes: list,
    planejamento_por_item: dict | None = None,
    sched_por_item: dict | None = None,
    particao_por_item: dict | None = None,
    idle_por_item: dict | None = None,
    pool_total_por_item: dict | None = None,
) -> PontoEquilibrio | None:
    """Builds and validates PE for a single equipe; returns None if skipped."""
    if not equipe.item_id:
        return None
    pe = _build_pe_for_equipe(
        equipe,
        venda_por_item,
        planejamento_por_item,
        sched_por_item,
        particao_por_item,
        idle_por_item,
        pool_total_por_item,
    )
    if pe is None:
        return None
    _validate_pe_duplo_risco(pe, validacoes)
    if pe.custo_operacional_real > 0:
        _validate_pe_particao(pe, validacoes)
    _validate_frentes_necessarias(pe, validacoes)
    _validate_prod_vs_pu(pe, validacoes)
    _validate_prod_pu_fallback_desync(equipe.item_id, sched_por_item, planejamento_por_item, validacoes)
    return pe


def _bpe_build_sched_por_item(canonical_in: CanonicalModel) -> dict:
    """Mapa activity_id → ScheduledActivityCanonical para extrair fatores de lesão climática."""
    sched_por_item: dict = {}
    if canonical_in.cronograma and canonical_in.cronograma.scheduled_activities:
        for sa in canonical_in.cronograma.scheduled_activities:
            sched_por_item[sa.activity_id] = sa
    return sched_por_item


def _bpe_build_particao_por_item(canonical_in: CanonicalModel) -> dict[str, CustoParticionadoItem]:
    """ADR-083: particao causal de custo por item (hub: item_id → CustoParticionadoItem)."""
    particao_por_item: dict[str, CustoParticionadoItem] = {}
    for contrato in canonical_in.contratos_recurso:
        for part in contrato.particao_por_item:
            particao_por_item[part.item_id] = part
    return particao_por_item


def _bpe_build_pool_total_por_item(canonical_in: CanonicalModel) -> dict[str, float]:
    """NEP-042 D3: custo pool total por item — soma custo_total_particionado sobre TODOS os contratos."""
    pool_total_por_item: dict[str, float] = {}
    for contrato in canonical_in.contratos_recurso:
        for part in contrato.particao_por_item:
            pool_total_por_item[part.item_id] = pool_total_por_item.get(part.item_id, 0.0) + float(
                getattr(part, "custo_total_particionado", 0.0) or 0.0
            )
    return pool_total_por_item


def _bpe_build_idle_por_item(canonical_in: CanonicalModel) -> dict[str, float]:
    """Idle real por item: Σ(custo_idle_mo + custo_idle_eq) das instâncias do pool.

    Quando a política de late hire / early dismissal está ativa e não há standby,
    esse valor é 0 — e o lever ResourcePool no painel_equilibrio desaparece.
    """
    idle_por_item: dict[str, float] = {}
    for inst in canonical_in.instancias_recurso or []:
        idle = float(getattr(inst, "custo_idle_mo", 0.0) or 0.0) + float(getattr(inst, "custo_idle_eq", 0.0) or 0.0)
        if idle > 0:
            for ativ in getattr(inst, "atividades_cobertas", []) or []:
                idle_por_item[str(ativ)] = idle_por_item.get(str(ativ), 0.0) + idle
    return idle_por_item


def _bpe_build_lookup_maps(canonical_in: CanonicalModel) -> tuple[dict, dict, dict]:
    venda_por_item = {
        p.item_id: p.subtotal.com_bdi.total for p in canonical_in.planejamento if p.item_id and p.subtotal
    }
    planejamento_por_item = {p.item_id: p for p in canonical_in.planejamento if p.item_id}
    equipe_by_item = {e.item_id: e for e in canonical_in.equipes_diretas if e.item_id}
    return venda_por_item, planejamento_por_item, equipe_by_item


def _bpe_collect_pe_items(
    canonical_in: CanonicalModel,
    venda_por_item: dict,
    validacoes: list,
    planejamento_por_item: dict,
    sched_por_item: dict,
    particao_por_item: dict,
    idle_por_item: dict,
    pool_total_por_item: dict,
) -> list[PontoEquilibrio]:
    pe_items: list[PontoEquilibrio] = []
    for e in canonical_in.equipes_diretas:
        pe = _bpe_process_equipe(
            e,
            venda_por_item,
            validacoes,
            planejamento_por_item,
            sched_por_item,
            particao_por_item,
            idle_por_item,
            pool_total_por_item,
        )
        if pe is not None:
            pe_items.append(pe)
    return pe_items


def _build_ponto_equilibrio(canonical_in: CanonicalModel, validacoes: list) -> list[PontoEquilibrio]:
    """Calcula ponto de equilíbrio para todas as equipes diretas."""
    venda_por_item, planejamento_por_item, equipe_by_item = _bpe_build_lookup_maps(canonical_in)
    sched_por_item = _bpe_build_sched_por_item(canonical_in)
    particao_por_item = _bpe_build_particao_por_item(canonical_in)
    pool_total_por_item = _bpe_build_pool_total_por_item(canonical_in)
    idle_por_item = _bpe_build_idle_por_item(canonical_in)

    pe_items = _bpe_collect_pe_items(
        canonical_in,
        venda_por_item,
        validacoes,
        planejamento_por_item,
        sched_por_item,
        particao_por_item,
        idle_por_item,
        pool_total_por_item,
    )
    if pe_items:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-PONTO-EQUILIBRIO",
                status="OK",
                mensagem=f"Ponto de equilíbrio calculado para {len(pe_items)} equipes.",
            )
        )
        _apply_pe_mitigacao(pe_items, equipe_by_item, validacoes)
    return pe_items


