"""Skill 05 — Equipes e Alocação (helpers A, parte extraída de _skill_helpers_a.py)."""

from __future__ import annotations

from concilium.domain.models.canonical import (
    CadeiaPerpetuacao,
    InstanciaRecurso,
    RecursoContrato,
)

from ._pool_contrato_demanda import _week_idx  # ty: ignore[unresolved-import]


def _last_week_idx_for_act(segmentos: list, activity_id: str) -> int | None:
    """Returns max week_idx of semana_fim for segments matching activity_id, or None."""
    result = None
    for seg in segmentos:
        if seg.activity_id == activity_id:
            idx = _week_idx(seg.semana_fim)
            result = idx if result is None else max(result, idx)
    return result


def _first_week_idx_for_act(segmentos: list, activity_id: str) -> int | None:
    """Returns min week_idx of semana_inicio for segments matching activity_id, or None."""
    result = None
    for seg in segmentos:
        if seg.activity_id == activity_id:
            idx = _week_idx(seg.semana_inicio)
            result = idx if result is None else min(result, idx)
    return result


def _compute_gap_for_inst(inst, pred_id: str, succ_id: str) -> int:
    """Returns idle weeks between pred and succ in this instance slot."""
    pred_last_idx = _last_week_idx_for_act(inst.segmentos_atividade, pred_id)
    succ_first_idx = _first_week_idx_for_act(inst.segmentos_atividade, succ_id)
    if pred_last_idx is not None and succ_first_idx is not None:
        return max(0, succ_first_idx - pred_last_idx - 1)
    return 0


def _enrich_particao_overhead(
    contratos: list[RecursoContrato],
    cadeias: list[CadeiaPerpetuacao],
    instancias: list[InstanciaRecurso],
) -> None:
    """Atualiza overhead_ocioso / custo_ocioso_imputado em CustoParticionadoItem — ADR-083.

    Usa os segmentos contínuos reais de cada slot (gerados por _build_instancias_recurso)
    para calcular os gaps efetivos entre atividades consecutivas na cadeia, imputando o
    custo de ociosidade ao item *sucessor* (princípio de causalidade do ADR-083).

    Parâmetros
    ----------
    contratos   : contratos de pool com particao_por_item já inicializada
    cadeias     : cadeias de perpetuação (ADR-073) — fornecem a ordem H → I
    instancias  : slots instanciais com segmentos_atividade preenchidos (ADR-077/083)
    """
    # tipo_id → list[InstanciaRecurso]
    insts_por_tipo: dict[str, list[InstanciaRecurso]] = {}
    for inst in instancias:
        insts_por_tipo.setdefault(inst.tipo_id, []).append(inst)

    # tipo_id → {item_id: predecessor_item_id} — apenas itens com antecessor na cadeia
    predecessor_por_tipo: dict[str, dict[str, str]] = {}
    for cadeia in cadeias:
        tipo = cadeia.tipo_id
        for k, iid in enumerate(cadeia.item_ids):
            if k > 0:
                predecessor_por_tipo.setdefault(tipo, {})[iid] = cadeia.item_ids[k - 1]

    for contrato in contratos:
        tipo = contrato.tipo_id
        insts = insts_por_tipo.get(tipo, [])
        preds = predecessor_por_tipo.get(tipo, {})
        unit_cost = contrato.custo_unit_semanal

        for part in contrato.particao_por_item:
            pred_id = preds.get(part.item_id)
            if pred_id is None:
                continue  # primeiro item da cadeia — sem gap para imputar

            total_idle_weeks = sum(_compute_gap_for_inst(inst, pred_id, part.item_id) for inst in insts)

            overhead = round(unit_cost * total_idle_weeks, 2)
            part.custo_ocioso_imputado = overhead
            part.overhead_ocioso = overhead


