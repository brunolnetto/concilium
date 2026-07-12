"""ADR-128 Fase 2b — Repropagação de atraso para sucessores no DAG de precedências.

Fecha a limitação conhecida e documentada em `replenishable.py`/`cpsat_scheduler.py`:
`apply_replenishable_delay` (ADR-128 §D2) desloca apenas a atividade que consome o
recurso consumível cujo estoque projetado ficaria negativo — sem repropagar esse atraso
para sucessores no DAG de precedências (`ActivityDAG.precedence` + `ExtendedPrecedence`
SS/FF/FS+lag). Esta função implementa a segunda passada determinística de reparo:
percorre o grafo em ordem topológica e empurra (nunca puxa) qualquer sucessor cuja
posição atual viole a precedência contra seu predecessor (possivelmente já deslocado),
propagando transitivamente ao longo da cadeia.

Decisão de design (ver nota de implementação da ADR-128, Fase 2b): reparo
pós-processamento determinístico sobre o DAG, análogo em espírito ao reparo de estoque
já existente — não um reservoir constraint nativo no CP-SAT (avaliado e rejeitado
anteriormente por escopo). Esta função conhece apenas precedência; não sabe nada sobre
recursos/estoque — a orquestração entre as duas passadas (reparo de estoque → reparo de
precedência → repetir até ponto fixo) vive em `CpSatScheduler.schedule()`.
"""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Sequence
from typing import TYPE_CHECKING

from concilium.application.scheduling.models import ActivityDAG, ScheduledActivity

if TYPE_CHECKING:
    from concilium.application.scheduling.cpsat_scheduler import ExtendedPrecedence


def _topological_order_with_extended(
    dag: ActivityDAG, extended: Sequence[ExtendedPrecedence]
) -> list[str]:
    """Ordem topológica que respeita `dag.precedence` *e* arestas SS/FF/FS+lag.

    `ActivityDAG.topological_order()` só enxerga `dag.precedence` — como precedências
    estendidas costumam ser declaradas sem uma entrada correspondente em
    `dag.precedence` (ver testes de `cpsat_scheduler`), usar aquele método sozinho
    poderia processar um sucessor antes do predecessor estendido já ter sido deslocado.
    Constrói um Kahn's algorithm local sobre a união das duas listas de arestas.
    """
    node_ids = [a.activity_id for a in dag.activities]
    edges: list[tuple[str, str]] = list(dag.precedence)
    edges.extend((ep.pred, ep.succ) for ep in extended)

    successors: dict[str, list[str]] = {aid: [] for aid in node_ids}
    in_degree: dict[str, int] = dict.fromkeys(node_ids, 0)
    for pred_id, succ_id in edges:
        if pred_id not in successors or succ_id not in in_degree:
            continue
        successors[pred_id].append(succ_id)
        in_degree[succ_id] += 1

    queue: deque[str] = deque(aid for aid in node_ids if in_degree[aid] == 0)
    order: list[str] = []
    seen_in_degree = dict(in_degree)
    while queue:
        node = queue.popleft()
        order.append(node)
        for succ_id in successors[node]:
            seen_in_degree[succ_id] -= 1
            if seen_in_degree[succ_id] == 0:
                queue.append(succ_id)

    if len(order) != len(node_ids):
        # Ciclo (não deveria acontecer numa solução que o CP-SAT já validou como
        # feasible) — não é papel deste reparo detectar/lançar; devolve a ordem
        # original dos nós restantes para não travar, na pior hipótese produzindo
        # uma repropagação incompleta que `_validate_repaired_schedule` ainda pega.
        remaining = [aid for aid in node_ids if aid not in order]
        order.extend(remaining)
    return order


def repropagate_precedence_delays(
    scheduled_activities: Sequence[ScheduledActivity],
    dag: ActivityDAG,
    extended_precedences: Sequence[ExtendedPrecedence] | None = None,
) -> list[ScheduledActivity]:
    """Empurra sucessores para frente para preservar precedência após um atraso.

    Percorre `dag` em ordem topológica (considerando `dag.precedence` e as
    precedências estendidas SS/FF/FS+lag, tanto `dag.extended_precedences` quanto
    as passadas explicitamente); para cada atividade, calcula o início (ou, para
    FF, o fim) mínimo exigido por cada predecessor e, se a posição atual violar
    essa exigência, desloca a atividade inteira (start e end, preservando
    `duration_weeks`) pelo déficit exato — nunca antecipa, apenas atrasa, e nunca
    além do necessário para satisfazer a maior exigência entre todos os
    predecessores.

    Não modifica as instâncias originais — retorna uma nova lista de
    `ScheduledActivity`. Não conhece recursos/estoque — só precedência.
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
    acts_by_id = {a.activity_id: a for a in dag.activities}

    all_extended = list(getattr(dag, "extended_precedences", None) or [])
    all_extended.extend(extended_precedences or [])
    extended_by_succ: dict[str, list] = {}
    for ep in all_extended:
        extended_by_succ.setdefault(ep.succ, []).append(ep)

    order = _topological_order_with_extended(dag, all_extended)

    for activity_id in order:
        succ = activities.get(activity_id)
        if succ is None:
            continue

        min_start = succ.start_week
        min_end = succ.end_week

        # Precedências FS clássicas (ActivityDAG.precedence + thresholds, ADR-081) —
        # mesma fórmula de lag usada por `_validate_repaired_schedule`.
        for pred_id in dag.predecessors(activity_id):
            pred = activities.get(pred_id)
            if pred is None:
                continue
            theta = dag.get_threshold(pred_id, activity_id)
            if theta >= 1.0:
                required_start = pred.end_week
            else:
                pred_activity = acts_by_id.get(pred_id)
                pred_duration = pred_activity.duration_weeks if pred_activity else pred.duration_weeks
                lag = math.ceil(theta * pred_duration)
                required_start = pred.start_week + lag
            min_start = max(min_start, required_start)

        # Precedências estendidas SS/FF/FS+lag (NEP-031 L4).
        for ep in extended_by_succ.get(activity_id, []):
            pred = activities.get(ep.pred)
            if pred is None:
                continue
            if ep.tipo == "FS":
                min_start = max(min_start, pred.end_week + ep.lag)
            elif ep.tipo == "SS":
                min_start = max(min_start, pred.start_week + ep.lag)
            elif ep.tipo == "FF":
                min_end = max(min_end, pred.end_week + ep.lag)

        # Déficit = maior deslocamento exigido entre início e fim (FF via fim);
        # nunca negativo (nunca antecipa).
        start_deficit = min_start - succ.start_week
        end_deficit = min_end - succ.end_week
        deficit = max(start_deficit, end_deficit, 0)
        if deficit > 0:
            succ.start_week += deficit
            succ.end_week += deficit

    return list(activities.values())
