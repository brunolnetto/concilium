"""Skill 04 — Contabilização canônica de consumíveis (ADR-128 F6, parte extraída de skill.py)."""

from __future__ import annotations

from concilium.application.scheduling.models import ReplenishableResource, ScheduledActivity
from concilium.application.scheduling.replenishable import (
    custo_deficit_provisionado,
    project_estoque_semanal,
    project_overflow_semanal,
)
from concilium.domain.models.canonical import (
    DisponibilidadeConsumivelCanonical,
    EstoqueDelayCanonical,
    RecursoConsumivelCanonical,
    ResumoEstoqueConsumivel,
    ScheduledActivityCanonical,
)


def _to_scheduled_activity(sa: ScheduledActivityCanonical) -> ScheduledActivity:
    return ScheduledActivity(
        activity_id=sa.activity_id,
        start_week=sa.start_week,
        end_week=sa.end_week,
        duration_weeks=sa.duration_weeks,
    )


def _build_resumo_estoque(
    resource: ReplenishableResource,
    niveis: dict[int, float],
    overflow: dict[int, float],
    delays_do_recurso: list[EstoqueDelayCanonical],
) -> ResumoEstoqueConsumivel:
    """Deriva ResumoEstoqueConsumivel a partir das projeções físicas (ADR-128 F6).

    Regra de status (existence-based, não banda percentual como pool 65%/35% — a
    projeção é recomputada contra o cronograma FINAL, pós-reparo):

        CRITICO  se estoque_minimo < 0   (irreparável — mesmo caso de VAL-ESTOQUE-DELAY-02)
        AVISO    elif delay_total_semanas > 0 ou overflow_total > 0
        OK       caso contrário
    """
    estoque_inicial = resource.disponibilidade.estoque_inicial
    valores = list(niveis.values())
    estoque_medio = sum(valores) / len(valores) if valores else estoque_inicial
    estoque_minimo = min(valores) if valores else estoque_inicial
    estoque_final = niveis[max(niveis)] if niveis else estoque_inicial

    overflow_total = round(sum(overflow.values()), 6)
    n_semanas_overflow = sum(1 for v in overflow.values() if v > 0)

    delay_total_semanas = sum(d.delay_weeks for d in delays_do_recurso)
    n_atividades_atrasadas = len(delays_do_recurso)

    if estoque_minimo < 0:
        status: str = "CRITICO"
    elif delay_total_semanas > 0 or overflow_total > 0:
        status = "AVISO"
    else:
        status = "OK"

    return ResumoEstoqueConsumivel(
        resource_id=resource.resource_id,
        estoque_inicial=estoque_inicial,
        capacidade_armazenamento=resource.disponibilidade.capacidade_armazenamento,
        estoque_medio=round(estoque_medio, 6),
        estoque_minimo=round(estoque_minimo, 6),
        estoque_final=round(estoque_final, 6),
        overflow_total=overflow_total,
        n_semanas_overflow=n_semanas_overflow,
        delay_total_semanas=delay_total_semanas,
        n_atividades_atrasadas=n_atividades_atrasadas,
        status_estoque=status,  # type: ignore[arg-type]
        custo_deficit_externo=round(custo_deficit_provisionado(resource.disponibilidade), 2),
    )


def build_estoque_consumivel_canonical(
    replenishable_resources: list[ReplenishableResource] | None,
    scheduled_activities_canonical: list[ScheduledActivityCanonical],
    estoque_delays: list[EstoqueDelayCanonical],
) -> tuple[list[RecursoConsumivelCanonical], list[ResumoEstoqueConsumivel]]:
    """Persiste a contabilização canônica de consumíveis (ADR-128 F6) — análogo a
    ``contratos_recurso``/``resumo_utilizacao_contratos`` para pool.

    Retorna ``([], [])`` rápido quando ``replenishable_resources`` é ``None``/vazio —
    opt-in, zero mudança de comportamento (ADR-128 D1/F5).
    """
    if not replenishable_resources:
        return [], []

    scheduled = [_to_scheduled_activity(sa) for sa in scheduled_activities_canonical]
    delays_by_resource: dict[str, list[EstoqueDelayCanonical]] = {}
    for d in estoque_delays:
        delays_by_resource.setdefault(d.resource_id, []).append(d)

    recursos_out: list[RecursoConsumivelCanonical] = []
    resumos_out: list[ResumoEstoqueConsumivel] = []
    for resource in replenishable_resources:
        recursos_out.append(
            RecursoConsumivelCanonical(
                resource_id=resource.resource_id,
                disponibilidade=DisponibilidadeConsumivelCanonical(
                    capacidade_armazenamento=resource.disponibilidade.capacidade_armazenamento,
                    estoque_inicial=resource.disponibilidade.estoque_inicial,
                    taxa_reabastecimento_max=resource.disponibilidade.taxa_reabastecimento_max,
                    lead_time_reabastecimento_dias=resource.disponibilidade.lead_time_reabastecimento_dias,
                    deficit_provisionado_externamente=resource.disponibilidade.deficit_provisionado_externamente,
                    preco_provisionamento_externo=resource.disponibilidade.preco_provisionamento_externo,
                ),
                consumo_por_semana=dict(resource.consumo_por_semana),
                producao_por_semana=dict(resource.producao_por_semana),
            )
        )
        niveis = project_estoque_semanal(resource, scheduled)
        overflow = project_overflow_semanal(resource, scheduled)
        resumos_out.append(
            _build_resumo_estoque(resource, niveis, overflow, delays_by_resource.get(resource.resource_id, []))
        )

    return recursos_out, resumos_out


__all__ = ["build_estoque_consumivel_canonical"]
