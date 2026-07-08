"""Skill 07 — Adapter de Saída (gera JSON + Excel .xlsm) — compressão de cronograma e decomposição de pool."""

from typing import Any

from concilium.domain.models.canonical import CanonicalModel


def _rcc_build_scheduled_activities(cronograma: Any) -> list:
    """Reconstrói a lista de ScheduledActivity a partir do cronograma canônico."""
    from concilium.application.scheduling import ScheduledActivity

    return [
        ScheduledActivity(
            activity_id=sa.activity_id,
            start_week=sa.start_week,
            end_week=sa.end_week,
            duration_weeks=sa.duration_weeks,
            assigned_resources=dict(sa.assigned_resources or {}),
            ramp_profile=sa.ramp_profile,
        )
        for sa in cronograma.scheduled_activities
        if sa.assigned_resources
    ]


def _rcc_build_schedule_output(sched_acts_sched: list, makespan: int) -> Any:
    """Constrói o ScheduleOutput (com métricas) a partir das atividades reconstruídas."""
    from concilium.application.scheduling import ScheduleMetrics, ScheduleOutput

    metrics = ScheduleMetrics(
        makespan=makespan,
        resource_leveling_score=0.0,
        idle_time=0,
        activity_fragmentation=0,
        critical_path_slack_min=0.0,
        resource_utilization_avg=0.0,
    )
    return ScheduleOutput(
        scheduled_activities=sched_acts_sched,
        makespan=makespan,
        feasible=True,
        metrics=metrics,
    )


def _rcc_add_predecessor(
    pred: Any,
    iid: str,
    aid_set: set[str],
    prec: list[tuple[str, str]],
    thresh: dict[tuple[str, str], float],
) -> None:
    """Adiciona (in-place) a precedência tipada de `pred` -> `iid`, se válida e ainda não presente."""
    pid = getattr(pred, "predecessor_id", None) or getattr(pred, "item_id", None)
    if pid and pid in aid_set and (pid, iid) not in set(prec):
        prec.append((pid, iid))
        th = getattr(pred, "completion_threshold_pct", None) or getattr(pred, "threshold", None) or 1.0
        thresh[(pid, iid)] = float(th)


def _rcc_build_precedencias(
    canonical_in: CanonicalModel, aid_set: set[str]
) -> tuple[list[tuple[str, str]], dict[tuple[str, str], float]]:
    """Extrai as precedências tipadas (e thresholds) da EAP restritas ao conjunto de activity_ids."""
    prec: list[tuple[str, str]] = []
    thresh: dict[tuple[str, str], float] = {}
    for item in canonical_in.eap or []:
        iid = item.item_id
        if iid not in aid_set:
            continue
        for pred in item.predecessores or []:
            _rcc_add_predecessor(pred, iid, aid_set, prec, thresh)
    return prec, thresh


def _rcc_build_dag(canonical_in: CanonicalModel, sched_acts_sched: list) -> Any:
    """Reconstrói a ActivityDAG (atividades + precedências tipadas) a partir do canônico."""
    from concilium.application.scheduling import Activity, ActivityDAG

    acts = [
        Activity(
            activity_id=sa.activity_id,
            description=sa.activity_id,
            duration_weeks=sa.duration_weeks,
            required_resources=dict(sa.assigned_resources or {}),
        )
        for sa in sched_acts_sched
    ]
    aid_set = {a.activity_id for a in acts}
    prec, thresh = _rcc_build_precedencias(canonical_in, aid_set)

    return ActivityDAG(activities=acts, precedence=prec, thresholds=thresh)


def _rcc_build_pool(sched_acts_sched: list, contratos_raw: list) -> Any:
    """Monta o ResourcePool base a partir das alocações e do piso contratual."""
    from concilium.application.scheduling import ResourcePool

    pool_resources: dict[str, int] = {}
    for sa in sched_acts_sched:
        for r, n in (sa.assigned_resources or {}).items():
            pool_resources[r] = max(pool_resources.get(r, 0), n)
    # Aplica pool dos contratos como piso
    for ct in contratos_raw:
        tid = getattr(ct, "tipo_id", None)
        qty = getattr(ct, "quantidade_contratada", None) or getattr(ct, "pool_size", None) or 0
        if tid and int(qty or 0) > 0:
            pool_resources[tid] = max(pool_resources.get(tid, 0), int(qty))
    return ResourcePool(resources=pool_resources)


def _rcc_build_contratos_dict(contratos_raw: list) -> dict[str, dict]:
    """Monta o dict de custos de instância por tipo de contrato de recurso."""
    contratos_dict: dict[str, dict] = {}
    for ct in contratos_raw:
        tid = getattr(ct, "tipo_id", None)
        if not tid:
            continue
        contratos_dict[tid] = {
            "custo_mob_unit": float(getattr(ct, "custo_mob_unit", 0) or 0),
            "custo_demob_unit": float(getattr(ct, "custo_demob_unit", 0) or 0),
            "custo_idle_semanal_unit": float(
                getattr(ct, "custo_idle_semanal_unit", None) or getattr(ct, "custo_standby_unit", 0) or 0
            ),
        }
    return contratos_dict


def _rcc_compute_preco_venda(canonical_in: CanonicalModel) -> float:
    """Extrai o preço de venda total do resultado, priorizando preco_venda_total."""
    res = canonical_in.resultado
    preco_venda = 0.0
    if res:
        for attr in ("preco_venda_total", "total_com_bdi"):
            v = getattr(res, attr, None)
            if v and float(v) > 0:
                preco_venda = float(v)
                break
    return preco_venda


def _rcc_serialize_itens(results: list) -> list[dict]:
    """Serializa os resultados de compute_compression_sensitivities em entradas do relatório."""
    itens = []
    for r in results:
        entry: dict[str, Any] = {
            "activity_id": r.activity_id,
            "tipo_recurso": r.tipo_recurso_bottleneck,
            "n_base": r.n_base,
            "duration_base": r.duration_base,
            "float_rcpsp": round(r.float_rcpsp, 1),
            "float_cpm": round(r.float_cpm, 1),
            "criticality_class": r.criticality_class,
            "k_otimo": r.best_k,
            "gamma_otimo": round(r.max_gamma, 3) if r.best_k else None,
            "delta_makespan": r.by_k[r.best_k].delta_makespan if r.best_k else 0,
            "poupanca": round(r.by_k[r.best_k].poupanca) if r.best_k else 0,
            "roi": round(r.by_k[r.best_k].roi, 1) if r.best_k and r.by_k[r.best_k].roi < 1e9 else None,
            "by_k": {
                str(k): {
                    "duration_new": kr.duration_new,
                    "makespan_new": kr.makespan_new,
                    "delta_makespan": kr.delta_makespan,
                    "gamma": round(kr.gamma, 3),
                    "cost_extra": round(kr.cost_extra),
                    "poupanca": round(kr.poupanca),
                    "roi": round(kr.roi, 1) if kr.roi < 1e9 else None,
                    "viable": kr.viable,
                }
                for k, kr in r.by_k.items()
            },
        }
        itens.append(entry)
    return itens


def _rcc_prepare_context(canonical_in: CanonicalModel) -> tuple | None:
    """Monta o contexto (schedule/DAG/pool/contratos/custo_semana) para a análise de compressão.

    Retorna None quando faltam pré-requisitos (cronograma, contratos, ortools ou preço de venda
    válido) — os mesmos guards que existiam inline em _rra_build_compressao_cronograma.
    """
    cronograma = canonical_in.cronograma
    if not cronograma or not cronograma.scheduled_activities:
        return None

    contratos_raw = canonical_in.contratos_recurso or []
    if not contratos_raw:
        return None

    try:
        from concilium.application.scheduling import (
            compute_compression_sensitivities,
            format_compression_table,
        )
        from concilium.application.scheduling.cpsat_scheduler import (
            CpSatScheduler,  # noqa: F401 – verifica que ortools está disponível
        )
    except ImportError:
        return None

    makespan = cronograma.makespan_weeks

    # ── Reconstrói ScheduleOutput ────────────────────────────────────────────
    sched_acts_sched = _rcc_build_scheduled_activities(cronograma)
    if not sched_acts_sched:
        return None

    sched_output = _rcc_build_schedule_output(sched_acts_sched, makespan)

    # ── Reconstrói ActivityDAG ───────────────────────────────────────────────
    dag = _rcc_build_dag(canonical_in, sched_acts_sched)

    # ── Pool base ────────────────────────────────────────────────────────────
    pool = _rcc_build_pool(sched_acts_sched, contratos_raw)

    # ── Contratos para custo de instâncias ───────────────────────────────────
    contratos_dict = _rcc_build_contratos_dict(contratos_raw)

    # ── custo_semana ────────────────────────────────────────────────────────
    preco_venda = _rcc_compute_preco_venda(canonical_in)
    if preco_venda <= 0:
        return None
    custo_semana = preco_venda / makespan

    return (
        makespan,
        sched_output,
        dag,
        pool,
        contratos_dict,
        custo_semana,
        compute_compression_sensitivities,
        format_compression_table,
    )


def _rcc_serialize_relatorio(results: list, makespan: int, custo_semana: float, format_compression_table: Any) -> dict:
    """Serializa a lista de results de compute_compression_sensitivities no dict do relatório."""
    viáveis = [r for r in results if r.best_k is not None]
    makespan_otimo = (
        min(r.by_k[bk].makespan_new for r in viáveis if (bk := r.best_k) is not None) if viáveis else makespan
    )

    itens = _rcc_serialize_itens(results)

    return {
        "makespan_base": makespan,
        "makespan_otimo": makespan_otimo,
        "delta_makespan_max": makespan - makespan_otimo,
        "custo_semana": round(custo_semana),
        "poupanca_total_max": round((makespan - makespan_otimo) * custo_semana),
        "n_viáveis": len(viáveis),
        "itens": itens,
        "tabela_texto": format_compression_table(results),
    }


def _rra_build_compressao_cronograma(canonical_in: CanonicalModel) -> dict | None:
    """NEP-038: análise de compressão de cronograma por k-scaling de equipes.

    Reconstrói ScheduleOutput + ActivityDAG a partir do canônico e chama
    compute_compression_sensitivities com CP-SAT.

    Retorna None quando não há cronograma ou contratos suficientes.
    Falhas do CP-SAT são silenciosas (retorna None) para não bloquear o relatório.
    """
    ctx = _rcc_prepare_context(canonical_in)
    if ctx is None:
        return None
    (
        makespan,
        sched_output,
        dag,
        pool,
        contratos_dict,
        custo_semana,
        compute_compression_sensitivities,
        format_compression_table,
    ) = ctx

    # ── Roda análise ────────────────────────────────────────────────────────
    try:
        results = compute_compression_sensitivities(
            sched_output=sched_output,
            dag=dag,
            pool=pool,
            contratos=contratos_dict,
            custo_semana=custo_semana,
            k_values=(2, 3),
            scheduler_timeout=30.0,
        )
    except Exception:
        return None

    if not results:
        return None

    # ── Serializa para o dict do relatório ───────────────────────────────────
    return _rcc_serialize_relatorio(results, makespan, custo_semana, format_compression_table)


def _rra_build_decomposicao_pool(canonical_in: CanonicalModel) -> dict | None:
    """ADR-086: seção de decomposição explorável de pool de recursos.

    Agrega as faces-chave (ciclo de vida, custo por estado×componente, economia vs. autônomo,
    cadeias de perpetuação) com narrativa honesta. Retorna None quando não há pool.
    """
    if not (canonical_in.contratos_recurso or canonical_in.instancias_recurso):
        return None
    try:
        from concilium.application.services.analytics.cubo_pool_projection import (
            resolve_cubo_pool_projection,
        )
    except Exception:
        return None

    faces = [
        "instancia_ciclo_vida",
        "custo_estado_componente",
        "economia_pool",
        "cadeia_perpetuacao",
    ]
    secoes: dict[str, dict] = {}
    primeiro_totais: dict | None = None
    for face in faces:
        try:
            proj = resolve_cubo_pool_projection(canonical_in, face=face, granularidade="mes")
        except Exception:
            continue
        if primeiro_totais is None:
            primeiro_totais = proj.get("totais")
        secoes[face] = {
            "natureza": proj.get("natureza"),
            "columns": proj.get("columns"),
            "rows": proj.get("rows"),
            "narrativa": proj.get("narrativa"),
            "operator_meta": proj.get("operator_meta"),
        }
    if not secoes:
        return None
    return {
        "totais": primeiro_totais,
        "faces": secoes,
        "nota": (
            "Decomposição honesta: faces físicas descrevem o que cada slot fez (prod/ocioso/off); "
            "faces causais imputam custo a atividades com baseline autônomo explícito (ADR-086)."
        ),
    }


