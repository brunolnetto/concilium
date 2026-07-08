"""ADR-128 D2 — Restrição de disponibilidade de recursos consumíveis no motor RCPSP.

Projeta o nível de estoque de um ``ReplenishableResource`` semana a semana ao longo de um
cronograma proposto e, quando o estoque projetado ficar negativo, aplica um atraso à
atividade consumidora até que o reabastecimento acumulado torne o consumo viável —
análogo ao tratamento de recurso reutilizável indisponível (`ResourcePool`), mas com
contabilidade de fluxo em vez de contagem de unidades (ADR-128 §D2).

Limitação conhecida (documentada honestamente na ADR): o reparo por atraso desta primeira
fase desloca apenas a(s) atividade(s) que consomem o recurso, sem repropagar o atraso para
sucessores no DAG de precedências. Cronogramas onde a atividade atrasada tem sucessores
dependentes exigem uma segunda passada de resolução de precedências (fora do escopo desta
fase — ver ADR-128 Fase 2, nota "escopo amplo").
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence

from concilium.application.scheduling.models import ReplenishableResource, ScheduledActivity

_MAX_DELAY_ITERATIONS = 500


def project_estoque_semanal(
    resource: ReplenishableResource, scheduled_activities: Iterable[ScheduledActivity]
) -> dict[int, float]:
    """Projeta ``estoque[t] = estoque[t-1] + reabastecimento[t] - consumo[t]`` por semana.

    ``reabastecimento[t]`` assume a taxa máxima declarada (``taxa_reabastecimento_max``,
    0.0 quando não declarada) todo período, limitado pela capacidade de armazenamento
    quando declarada. ``consumo[t]`` é a soma de ``consumo_por_semana`` das atividades
    ativas na semana ``t`` (ativa: ``start_week <= t < end_week``).

    Retorna ``{}`` quando não há atividades agendadas (sem cronograma para projetar).
    """
    scheduled = list(scheduled_activities)
    if not scheduled:
        return {}

    disp = resource.disponibilidade
    taxa_max = disp.taxa_reabastecimento_max or 0.0
    cap = disp.capacidade_armazenamento

    consumo_por_t: dict[int, float] = defaultdict(float)
    for sa in scheduled:
        taxa = resource.consumo_por_semana.get(sa.activity_id)
        if not taxa:
            continue
        for t in range(sa.start_week, sa.end_week):
            consumo_por_t[t] += taxa

    max_week = max(sa.end_week for sa in scheduled)
    niveis: dict[int, float] = {}
    estoque = disp.estoque_inicial
    for t in range(max_week):
        estoque = estoque + taxa_max
        if cap is not None:
            estoque = min(estoque, cap)
        estoque -= consumo_por_t.get(t, 0.0)
        niveis[t] = estoque
    return niveis


def has_estoque_negativo(niveis: dict[int, float]) -> bool:
    """True se algum nível de estoque projetado for negativo (cronograma inviável)."""
    return any(v < 0 for v in niveis.values())


def apply_replenishable_delay(
    scheduled_activities: Sequence[ScheduledActivity], resource: ReplenishableResource
) -> list[ScheduledActivity]:
    """Atrasa, iterativamente, a atividade consumidora que gera o primeiro estoque negativo.

    Estratégia (ADR-128 §D2): a cada iteração, projeta o estoque; se algum ponto ficar
    negativo, identifica a primeira semana ``t0`` inviável e adia em uma semana a
    atividade que consome o recurso, está ativa em ``t0`` e começa mais tarde entre as
    candidatas (heurística gulosa — análoga a resolução de conflito em SGS de RCPSP).
    Repete até o estoque projetado ser não-negativo ou até ``_MAX_DELAY_ITERATIONS``.

    Não modifica as instâncias originais — retorna uma nova lista de ``ScheduledActivity``.
    """
    activities: dict[str, ScheduledActivity] = {
        sa.activity_id: ScheduledActivity(
            activity_id=sa.activity_id,
            start_week=sa.start_week,
            end_week=sa.end_week,
            duration_weeks=sa.duration_weeks,
            assigned_resources=dict(sa.assigned_resources),
            ramp_profile=sa.ramp_profile,
        )
        for sa in scheduled_activities
    }

    for _ in range(_MAX_DELAY_ITERATIONS):
        niveis = project_estoque_semanal(resource, activities.values())
        if not has_estoque_negativo(niveis):
            break
        t0 = min(t for t, v in niveis.items() if v < 0)
        candidates = [
            sa
            for sa in activities.values()
            if sa.start_week <= t0 < sa.end_week and resource.consumo_por_semana.get(sa.activity_id, 0.0)
        ]
        if not candidates:
            # Estoque inviável sem nenhuma atividade candidata a atrasar (ex.: déficit
            # já presente antes de qualquer consumo agendável) — não há reparo possível
            # nesta estratégia; interrompe sem lançar exceção, preservando o cronograma.
            break
        target = max(candidates, key=lambda sa: sa.start_week)
        target.start_week += 1
        target.end_week += 1
    return list(activities.values())
