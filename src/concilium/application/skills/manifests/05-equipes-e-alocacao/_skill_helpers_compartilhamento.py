"""Skill 03 — Equipes e Alocação (parte extraída de skill.py).

Detecção de oportunidades de compartilhamento paralelo (ADR-110).
"""

from __future__ import annotations

from typing import Any

from concilium.domain.models.canonical import (
    CanonicalModel,
    RecursoContrato,
    ValidacaoItem,
)

from ._skill_helpers_planejamento import _or_chain  # ty: ignore[unresolved-import]


def _deve_processar_compartilhamento(contratos_recurso: list[RecursoContrato], rcpsp_spec: dict | None) -> bool:
    """ADR-078: só há pré-processamento de compartilhamento com contratos, spec e custos de recurso."""
    return bool(contratos_recurso and rcpsp_spec and rcpsp_spec.get("resource_costs"))


def _deve_detectar_oportunidades_paralelo(relatorio_oportunidades: Any, canonical_in: CanonicalModel) -> bool:
    """ADR-110: só detecta oportunidades paralelas com schedule, resource_costs e pool disponíveis."""
    return bool(
        relatorio_oportunidades is not None
        and canonical_in.cronograma is not None
        and canonical_in.cronograma.scheduled_activities
        and canonical_in.recurso_pool
    )


def _build_scheduled_activities_110(canonical_in: CanonicalModel, contratos_recurso: list[RecursoContrato]) -> list:
    """Reconstrói a lista de ScheduledActivity do scheduler a partir do cronograma canônico."""
    from concilium.application.scheduling.models import ScheduledActivity

    assert canonical_in.cronograma is not None  # noqa: S101 - garantido pelo chamador (guard de ADR-110)
    sched_acts = []
    for sa in canonical_in.cronograma.scheduled_activities:
        rr: dict = {}
        for cont in contratos_recurso:
            if sa.activity_id in cont.items_cobertos:
                rr[cont.tipo_id] = rr.get(cont.tipo_id, 0) + 1
        start_week = int(_or_chain(getattr(sa, "semana_inicio_idx", 0), 0))
        end_week = int(_or_chain(getattr(sa, "semana_fim_idx", 1), 1))
        sched_acts.append(
            ScheduledActivity(
                activity_id=sa.activity_id,
                start_week=start_week,
                end_week=end_week,
                duration_weeks=max(1, end_week - start_week),
                assigned_resources=rr,
            )
        )
    return sched_acts


def _build_activity_dag_110(rcpsp_spec: dict) -> Any:
    """Reconstrói o ActivityDAG do scheduler a partir do rcpsp_spec."""
    from concilium.application.scheduling.models import Activity, ActivityDAG

    act = []
    for a in _or_chain(rcpsp_spec.get("activities"), []):
        dur = max(1, int(_or_chain(a.get("duration_weeks"), 1)))
        rr_a = {str(k): int(v) for k, v in _or_chain(a.get("required_resources"), {}).items()}
        act.append(
            Activity(
                activity_id=str(_or_chain(a.get("item_id"), a.get("activity_id"), "")),
                description=str(a.get("descricao") or ""),
                duration_weeks=dur,
                required_resources=rr_a,
            )
        )
    prec = [
        (str(e[0]), str(e[1]))
        for e in _or_chain(rcpsp_spec.get("precedence"), [])
        if isinstance(e, (list, tuple)) and len(e) >= 2
    ]
    return ActivityDAG(activities=act, precedence=prec)


def _build_resource_pool_110(contratos_recurso: list[RecursoContrato]) -> Any:
    """Reconstrói o ResourcePool do scheduler a partir dos contratos de pool.

    ADR-071: RecursoContrato.quantidade_contratada é o pool_size do contrato
    (quantidade_total pertence a RecursoPool, não a RecursoContrato).
    """
    from concilium.application.scheduling.models import ResourcePool

    pool_res = {c.tipo_id: int(c.quantidade_contratada) for c in contratos_recurso}
    return ResourcePool(resources=pool_res)


def _custo_indireto_semanal(canonical_in: CanonicalModel) -> float:
    """Custo indireto médio por semana, usado na avaliação econômica de oportunidades paralelas."""
    if not canonical_in.indiretos:
        return 0.0
    custo_ind_sem = sum(i.custo_total for i in canonical_in.indiretos)
    makespan = canonical_in.cronograma.makespan_weeks if canonical_in.cronograma else None
    n_sem = max(1, makespan or 1)
    return custo_ind_sem / n_sem


def _aplicar_oportunidades_paralelo(
    relatorio_oportunidades: Any, opps_paralelo: list, validacoes: list[ValidacaoItem]
) -> Any:
    """Anexa oportunidades paralelas detectadas ao relatório e emite a validação OK correspondente."""
    if not opps_paralelo:
        return relatorio_oportunidades
    relatorio_oportunidades = relatorio_oportunidades.model_copy(update={"oportunidades_paralelo": opps_paralelo})
    n_viaveis_par = sum(1 for o in opps_paralelo if o.economicamente_viavel)
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-OPP-PARALELO-OK",
            status="OK",
            mensagem=(
                f"ADR-110: {len(opps_paralelo)} oportunidade(s) paralela(s) detectada(s) "
                f"— {n_viaveis_par} economicamente viável(is)."
            ),
        )
    )
    return relatorio_oportunidades


def _processar_oportunidades_paralelo(
    relatorio_oportunidades: Any,
    canonical_in: CanonicalModel,
    contratos_recurso: list[RecursoContrato],
    rcpsp_spec: dict | None,
    validacoes: list[ValidacaoItem],
) -> Any:
    """ADR-110: detecção automática de oportunidades de compartilhamento paralelo (best-effort)."""
    if not _deve_detectar_oportunidades_paralelo(relatorio_oportunidades, canonical_in):
        return relatorio_oportunidades
    # relatorio_oportunidades só é not-None quando _deve_processar_compartilhamento
    # (chamador) já provou rcpsp_spec truthy — mesma variável, checada antes de
    # construir relatorio_oportunidades via _build_pre_processamento_compartilhamento.
    assert rcpsp_spec is not None
    try:
        from concilium.application.scheduling.models import ScheduleMetrics, ScheduleOutput

        from ._skill_helpers_pre import (  # ty: ignore[unresolved-import]  # runtime-only: sibling loaded via importlib above
            _detectar_oportunidades_paralelo,
        )

        # Garantido por _deve_processar_compartilhamento (chamador só passa relatorio_oportunidades
        # não-None quando rcpsp_spec já foi validado como dict com resource_costs).
        assert rcpsp_spec is not None  # noqa: S101

        sched_acts = _build_scheduled_activities_110(canonical_in, contratos_recurso)
        makespan = max((s.end_week for s in sched_acts), default=0)
        metrics = ScheduleMetrics(
            makespan=makespan,
            resource_leveling_score=1.0,
            idle_time=0,
            activity_fragmentation=0,
            critical_path_slack_min=0.0,
            resource_utilization_avg=1.0,
        )
        sched_output = ScheduleOutput(
            scheduled_activities=sched_acts,
            makespan=makespan,
            feasible=True,
            metrics=metrics,
        )
        dag = _build_activity_dag_110(rcpsp_spec)
        pool = _build_resource_pool_110(contratos_recurso)
        resource_costs = rcpsp_spec.get("resource_costs") or {}
        custo_ind_sem = _custo_indireto_semanal(canonical_in)

        opps_paralelo = _detectar_oportunidades_paralelo(
            sched_output,
            dag,
            pool,
            resource_costs,
            custo_ind_sem,
        )
        relatorio_oportunidades = _aplicar_oportunidades_paralelo(relatorio_oportunidades, opps_paralelo, validacoes)
    except Exception:
        pass  # best-effort: não bloqueia o pipeline se o detector falhar
    return relatorio_oportunidades


