"""Compressão de cronograma RCPSP por k-scaling de equipes.

NEP-038: Criticidade RCPSP e Teoria de Compressão de Cronograma.

Invariante fundamental:
    custo_direto(k) = k · c_i · (d_i / k) = c_i · d_i   (constante em k)

Apenas o custo de instâncias de pool (mob/demob/idle) aumenta com k.
O benefício vem da redução de overhead do projeto × semanas ganhas.

Três categorias de criticidade:
    PC  — Precedência-Crítica: TF_CPM = 0, γ ≈ 1
    RC  — Recurso-Crítica: TF_CPM > 0, TF_RCPSP ≈ 0, γ > 0
    GW  — Gateway: TF_RCPSP > 0, γ > 0 (libera recursos que o solver reotimiza)
    Bloqueada: γ < 0 (k-scaling satura pool compartilhado e piora o schedule)
    Livre: γ ≈ 0 (float absorve toda a compressão)
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

from .models import Activity, ActivityDAG, ResourcePool, ScheduleOutput

_log = logging.getLogger(__name__)

# ── Dataclasses de resultado ──────────────────────────────────────────────────


@dataclass
class KScaleResult:
    """Resultado de k-scaling para um valor de k específico."""

    k: int
    duration_new: int  # d_i(k) = ⌈d_i/k⌉
    makespan_new: int  # C_max após re-resolver RCPSP
    delta_makespan: int  # C_max^* - C_max(k)  (>0 = melhora)
    delta_duration: int  # d_i - d_i(k)
    gamma: float  # ΔC_max / Δd  ∈ [-∞, 1]
    cost_extra: float  # R$ mob+demob+idle de instâncias extras
    poupanca: float  # C_semana × delta_makespan
    roi: float  # poupanca / cost_extra

    @property
    def viable(self) -> bool:
        return self.roi > 1.0 and self.delta_makespan > 0


@dataclass
class CompressionResult:
    """Análise de compressão de uma atividade para múltiplos k."""

    activity_id: str
    tipo_recurso_bottleneck: str  # recurso com maior r_{ir}
    n_base: int  # unidades de pool usadas no baseline
    duration_base: int  # duração produtiva base (semanas)
    start_base: int  # início na solução RCPSP base
    makespan_base: int
    float_rcpsp: float  # TF na solução RCPSP atual
    float_cpm: float  # TF no CPM sem restrição de recursos
    resource_delay: float  # start^RCPSP - ES^CPM (atraso por recurso)
    criticality_class: str  # "PC" | "RC" | "GW" | "Bloqueada" | "Livre"
    by_k: dict[int, KScaleResult] = field(default_factory=dict)

    @property
    def best_roi(self) -> float:
        viable = [r for r in self.by_k.values() if r.delta_makespan > 0]
        return max((r.roi for r in viable), default=0.0)

    @property
    def best_k(self) -> int | None:
        viable = [r for r in self.by_k.values() if r.viable]
        if not viable:
            return None
        return max(viable, key=lambda r: r.roi).k

    @property
    def max_gamma(self) -> float:
        return max((r.gamma for r in self.by_k.values()), default=0.0)


# ── Helpers internos ─────────────────────────────────────────────────────────


def _cpm_forward_backward(
    dag: ActivityDAG,
    makespan: int,
) -> tuple[dict[str, float], dict[str, float]]:
    """CPM sem restrição de recursos.

    Returns:
        (es_map, tf_map) onde es_map[aid] = earliest start CPM,
        tf_map[aid] = total float CPM.
    """
    acts = {a.activity_id: a for a in dag.activities}

    # Forward pass
    es: dict[str, float] = {}
    for aid in dag.topological_order():
        preds = dag.predecessors(aid)
        if not preds:
            es[aid] = 0.0
        else:
            unlock = 0.0
            for p in preds:
                theta = dag.get_threshold(p, aid)
                d_p = acts[p].duration_weeks
                unlock = max(unlock, es[p] + math.ceil(d_p * theta))
            es[aid] = unlock

    c_max_cpm = max(es[a] + acts[a].duration_weeks for a in acts)

    # Backward pass
    ls: dict[str, float] = {}
    for aid in reversed(dag.topological_order()):
        succs = dag.successors(aid)
        d = acts[aid].duration_weeks
        if not succs:
            ls[aid] = c_max_cpm - d
        else:
            ls[aid] = min(ls[s] for s in succs) - d

    tf = {aid: ls[aid] - es[aid] for aid in acts}
    return es, tf


def _rcpsp_backward(
    sched_output: ScheduleOutput,
    dag: ActivityDAG,
) -> dict[str, float]:
    """Float na solução RCPSP via backward pass a partir do makespan real."""
    sa_map = {sa.activity_id: sa for sa in sched_output.scheduled_activities}
    c_max = sched_output.makespan

    ls: dict[str, float] = {}
    for aid in reversed(dag.topological_order()):
        if aid not in sa_map:
            continue
        d = sa_map[aid].duration_weeks
        succs = [s for s in dag.successors(aid) if s in sa_map]
        if not succs:
            ls[aid] = float(c_max - d)
        else:
            ls[aid] = min(ls[s] for s in succs if s in ls) - d

    return {aid: ls.get(aid, 0.0) - sa_map[aid].start_week for aid in sa_map if aid in ls}


def _build_scaled_activities(
    dag: ActivityDAG,
    scale_id: str,
    k: int,
) -> list[Activity]:
    """Reconstrói lista de Activity com scale_id escalado por k."""
    result = []
    for act in dag.activities:
        if act.activity_id == scale_id:
            result.append(
                Activity(
                    activity_id=act.activity_id,
                    description=act.description,
                    duration_weeks=max(1, math.ceil(act.duration_weeks / k)),
                    required_resources={r: v * k for r, v in act.required_resources.items()},
                    window_weeks=act.window_weeks,
                    ramp_profile=act.ramp_profile,
                )
            )
        else:
            result.append(act)
    return result


def _pool_for_activities(
    activities: list[Activity],
    base_pool: ResourcePool,
) -> ResourcePool:
    """Pool mínimo que acomoda o pico de demanda das atividades escaladas."""
    needed = dict(base_pool.resources)
    for act in activities:
        for r, n in act.required_resources.items():
            needed[r] = max(needed.get(r, 0), n)
    return ResourcePool(resources=needed)


def _classify(
    tf_cpm: float,
    tf_rcpsp: float,
    max_gamma: float,
) -> str:
    if tf_cpm < 0.5:
        return "PC"
    if max_gamma < -0.01:
        return "Bloqueada"
    if max_gamma > 0.01 and tf_rcpsp < 0.5:
        return "RC"
    if max_gamma > 0.01:
        return "GW"
    return "Livre"


# ── API pública ───────────────────────────────────────────────────────────────


def compute_compression_sensitivities(
    sched_output: ScheduleOutput,
    dag: ActivityDAG,
    pool: ResourcePool,
    contratos: dict[str, dict],
    custo_semana: float,
    k_values: tuple[int, ...] = (2, 3, 4),
    scheduler_timeout: float = 45.0,
    idle_fraction: float = 0.20,
) -> list[CompressionResult]:
    """Calcula γ_i(k), ROI e classe de criticidade para cada atividade.

    Args:
        sched_output:     Solução RCPSP base (makespan, start times).
        dag:              DAG com atividades e precedências.
        pool:             Pool de recursos do baseline.
        contratos:        {tipo_id: {"custo_mob_unit": x, "custo_demob_unit": y,
                          "custo_idle_semanal_unit": z}}.
        custo_semana:     Custo semanal do projeto (preco_venda / makespan).
        k_values:         Fatores de escala a testar (default: 2, 3, 4).
        scheduler_timeout: Timeout do CP-SAT por chamada (segundos).
        idle_fraction:    Fração de idle estimado durante atividade (≈0.20).

    Returns:
        Lista de CompressionResult ordenada por best_roi decrescente.
    """
    from concilium.application.scheduling.cpsat_scheduler import CpSatScheduler

    makespan_base = sched_output.makespan
    sa_map = {sa.activity_id: sa for sa in sched_output.scheduled_activities}

    # Floats CPM (sem recurso) e RCPSP (com recurso)
    cpm_es, cpm_tf = _cpm_forward_backward(dag, makespan_base)
    rcpsp_tf = _rcpsp_backward(sched_output, dag)

    scheduler = CpSatScheduler(
        timeout_seconds=scheduler_timeout,
        horizon_weeks=makespan_base * 3,
    )

    results: list[CompressionResult] = []

    for act in dag.activities:
        sa = sa_map.get(act.activity_id)
        if sa is None or not act.required_resources:
            continue

        tipo_bot = max(act.required_resources, key=lambda t: act.required_resources[t])
        n_base = act.required_resources[tipo_bot]
        ct = contratos.get(tipo_bot, {})
        mob = float(ct.get("custo_mob_unit", 0))
        demob = float(ct.get("custo_demob_unit", 0))
        idle_w = float(ct.get("custo_idle_semanal_unit", ct.get("custo_standby_unit", 0)))

        tf_cpm = float(cpm_tf.get(act.activity_id, 99.0))
        tf_rcpsp = float(rcpsp_tf.get(act.activity_id, 99.0))
        rd = max(0.0, sa.start_week - cpm_es.get(act.activity_id, 0.0))

        by_k: dict[int, KScaleResult] = {}
        for k in k_values:
            d_new = max(1, math.ceil(act.duration_weeks / k))
            delta_d = act.duration_weeks - d_new
            if delta_d <= 0:
                continue

            scaled_acts = _build_scaled_activities(dag, act.activity_id, k)
            pool_k = _pool_for_activities(scaled_acts, pool)
            dag_k = ActivityDAG(
                activities=scaled_acts,
                precedence=dag.precedence,
                thresholds=dag.thresholds,
            )

            try:
                out_k = scheduler.schedule(dag=dag_k, pool=pool_k)
                mksp_new = out_k.makespan if out_k.feasible else None
            except Exception:
                # Infeasibility (out_k.feasible=False) já é tratada acima sem exceção —
                # chegar aqui é uma falha inesperada do scheduler para este k, não um
                # candidato simplesmente ruim. Loga pra não mascarar bug real no solver.
                _log.warning(
                    "Falha ao agendar k=%d para atividade '%s' — candidato descartado",
                    k,
                    act.activity_id,
                    exc_info=True,
                )
                mksp_new = None

            if mksp_new is None:
                continue

            delta_ms = makespan_base - mksp_new
            gamma = delta_ms / delta_d if delta_d else 0.0

            n_extra = n_base * (k - 1)
            cost_extra = n_extra * (mob + demob + idle_w * d_new * idle_fraction)
            poupanca = delta_ms * custo_semana
            if cost_extra > 0:
                roi = poupanca / cost_extra if delta_ms > 0 else 0.0
            else:
                roi = math.inf if delta_ms > 0 else 0.0

            by_k[k] = KScaleResult(
                k=k,
                duration_new=d_new,
                makespan_new=mksp_new,
                delta_makespan=delta_ms,
                delta_duration=delta_d,
                gamma=gamma,
                cost_extra=cost_extra,
                poupanca=poupanca,
                roi=roi,
            )

        max_gamma = max((r.gamma for r in by_k.values()), default=0.0)
        cls = _classify(tf_cpm, tf_rcpsp, max_gamma)

        results.append(
            CompressionResult(
                activity_id=act.activity_id,
                tipo_recurso_bottleneck=tipo_bot,
                n_base=n_base,
                duration_base=act.duration_weeks,
                start_base=sa.start_week,
                makespan_base=makespan_base,
                float_rcpsp=tf_rcpsp,
                float_cpm=tf_cpm,
                resource_delay=rd,
                criticality_class=cls,
                by_k=by_k,
            )
        )

    return sorted(results, key=lambda r: -r.best_roi)


def format_compression_table(results: list[CompressionResult]) -> str:
    """Formata tabela de resultados para exibição em texto."""
    lines = [
        f"{'Atividade':12s} {'Recurso':>10s} {'d':>4s} {'Float':>6s} {'Classe':>10s} "
        f"{'k*':>4s} {'Mksp(k*)':>9s} {'Δw':>5s} {'γ':>6s} {'ROI':>7s}",
        "─" * 75,
    ]
    for r in results:
        if r.best_k is None:
            k_str = "—"
            mksp_s = "—"
            dw_s = "—"
            gamma_s = "—"
            roi_s = "—"
        else:
            kr = r.by_k[r.best_k]
            k_str = str(r.best_k)
            mksp_s = str(kr.makespan_new)
            dw_s = f"-{kr.delta_makespan}w" if kr.delta_makespan > 0 else "0w"
            gamma_s = f"{kr.gamma:.2f}"
            roi_s = f"{kr.roi:.1f}x" if kr.roi < 1000 else "∞"
        lines.append(
            f"{r.activity_id:12s} {r.tipo_recurso_bottleneck:>10s} {r.duration_base:>4d} "
            f"{r.float_rcpsp:>6.1f} {r.criticality_class:>10s} "
            f"{k_str:>4s} {mksp_s:>9s} {dw_s:>5s} {gamma_s:>6s} {roi_s:>7s}"
        )
    return "\n".join(lines)
