"""ADR-078/ADR-133 — pré-processamento e detecção de oportunidades de compartilhamento.

Critical path method (early start / late finish).
"""

from __future__ import annotations

from typing import Any


def _cpm_early_start(dag: Any) -> dict[str, int]:
    """Forward pass CPM sem recursos — retorna ES por atividade."""
    acts: dict[str, Any] = {a.activity_id: a for a in dag.activities}
    order: list[str] = dag.topological_order()
    es: dict[str, int] = {aid: 0 for aid in order}
    for aid in order:
        ef_i = es[aid] + acts[aid].duration_weeks
        for succ in dag.successors(aid):
            if ef_i > es.get(succ, 0):
                es[succ] = ef_i
    return es


def _cpm_late_finish(dag: Any, makespan: int) -> dict[str, int]:
    """Backward pass CPM — retorna LF por atividade.

    LF(i) = makespan se sem sucessores, caso contrário min(LS(succ)).
    """
    acts: dict[str, Any] = {a.activity_id: a for a in dag.activities}
    order: list[str] = dag.topological_order()
    lf: dict[str, int] = {aid: makespan for aid in order}
    for aid in reversed(order):
        for succ in dag.successors(aid):
            ls_succ = lf[succ] - acts[succ].duration_weeks
            if ls_succ < lf[aid]:
                lf[aid] = ls_succ
    return lf


def _gap_coberto_por_recurso(sched: Any, tipo_id: str, t_start: int, t_end: int) -> bool:
    """True se [t_start, t_end) está totalmente coberto por atividades usando tipo_id."""
    if t_start >= t_end:
        return True
    covered: set[int] = set()
    for sa in sched.scheduled_activities:
        if sa.assigned_resources.get(tipo_id, 0) > 0:
            for w in range(max(t_start, sa.start_week), min(t_end, sa.end_week)):
                covered.add(w)
    return len(covered) == t_end - t_start


