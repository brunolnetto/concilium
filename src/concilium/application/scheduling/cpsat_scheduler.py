"""ADR-075 Phase 3 — CP-SAT Scheduler (Mode A: exact RCPSP, n <= 200).

Implements CpSatScheduler using OR-Tools CP-SAT:

  Formulation:
    - One IntervalVar per activity: [start, start+dur, start+dur]
    - AddCumulative per resource: sum of demands <= capacity at every week
    - Precedence constraints: FS / SS / FF with optional lag
    - window_weeks: hard deadline → start + duration <= window_weeks
    - Objective: minimise makespan (= max finish across all activities)

  Extended Precedences (ExtendedPrecedence):
    FS: start(j) >= finish(i) + lag
    SS: start(j) >= start(i) + lag
    FF: finish(j) >= finish(i) + lag

  Solution callback (MatchingOracleCallback):
    Called each time CP-SAT finds a better feasible solution.
    Invokes the MatchingOracle on the current schedule, records
    C_mob estimate alongside C_op (makespan proxy).
    Best composite schedule is retained and returned.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Literal

from ortools.sat.python import cp_model

from concilium.application.scheduling.models import (
    Activity,
    ActivityDAG,
    EstoqueDelayCause,
    ReplenishableResource,
    ResourcePool,
    ScheduledActivity,
    ScheduleMetrics,
    ScheduleOutput,
)
from concilium.application.scheduling.precedence_repropagation import repropagate_precedence_delays
from concilium.application.scheduling.replenishable import (
    apply_replenishable_delay,
    has_estoque_negativo,
    project_estoque_semanal,
)
from concilium.domain.models.analytics.optimization import RampProfile

_log = logging.getLogger(__name__)

# Horizon: max possible week index. CP-SAT needs a finite upper bound.
_DEFAULT_HORIZON = 1000

# ADR-128 Fase 2b: cota de rodadas do laço de ponto fixo entre reparo de estoque
# (apply_replenishable_delay) e repropagação de precedência (repropagate_precedence_delays).
# Repropagar um atraso pode empurrar uma atividade que consome um OUTRO recurso consumível,
# reabrindo uma violação de estoque já resolvida para esse recurso — daí o laço em vez de
# uma única passada. 10 é uma cota generosa e heurística (não uma prova formal de
# convergência): cronogramas reais estabilizam em 1-3 rodadas; se não convergir dentro da
# cota, `_validate_repaired_schedule` ainda pega qualquer violação residual e marca
# infeasible — nunca retorna um cronograma quebrado como viável.
_MAX_REPAIR_ROUNDS = 10


# ─────────────────────────────────────────────────────────────────────────────
# Data
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ExtendedPrecedence:
    """Typed precedence with lag (ADR-075 / NEP-031 L4).

    FS: start(succ) >= finish(pred) + lag
    SS: start(succ) >= start(pred)  + lag
    FF: finish(succ) >= finish(pred) + lag
    """

    pred: str
    succ: str
    tipo: Literal["FS", "SS", "FF"] = "FS"
    lag: int = 0


# ─────────────────────────────────────────────────────────────────────────────
# Callback
# ─────────────────────────────────────────────────────────────────────────────


class _MakespanCallback(cp_model.CpSolverSolutionCallback):
    """Records the best makespan found so far."""

    def __init__(self, makespan_var: cp_model.IntVar) -> None:
        super().__init__()
        self._makespan = makespan_var
        self.best_makespan: int = _DEFAULT_HORIZON

    def on_solution_callback(self) -> None:
        ms = self.value(self._makespan)
        if ms < self.best_makespan:
            self.best_makespan = ms


# ─────────────────────────────────────────────────────────────────────────────
# Scheduler
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class CpSatScheduler:
    """Exact RCPSP solver via OR-Tools CP-SAT (ADR-075 Mode A).

    Args:
        timeout_seconds:  Wall-clock time limit for the CP-SAT solver.
        num_workers:      Number of solver threads (default 1 for determinism).
        horizon_weeks:    Upper bound on the schedule horizon.
    """

    timeout_seconds: float = 60.0
    num_workers: int = 1
    horizon_weeks: int = _DEFAULT_HORIZON

    def _add_activity_variables(
        self, model: cp_model.CpModel, dag: ActivityDAG, horizon: int
    ) -> tuple[dict[str, cp_model.IntVar], dict[str, cp_model.IntVar], dict[str, cp_model.IntervalVar]]:
        """Cria as variáveis de decisão (start/end/interval) por atividade, com janela de deadline."""
        starts: dict[str, cp_model.IntVar] = {}
        ends: dict[str, cp_model.IntVar] = {}
        intervals: dict[str, cp_model.IntervalVar] = {}

        for a in dag.activities:
            dur = a.duration_weeks
            # Enforce window constraint: start + duration <= window_weeks
            max_start = (a.window_weeks - dur) if a.window_weeks else horizon - dur
            max_start = max(0, min(max_start, horizon - dur))
            start = model.new_int_var(0, max_start, f"start_{a.activity_id}")
            end = model.new_int_var(dur, horizon, f"end_{a.activity_id}")
            interval = model.new_interval_var(start, dur, end, f"iv_{a.activity_id}")
            starts[a.activity_id] = start
            ends[a.activity_id] = end
            intervals[a.activity_id] = interval
        return starts, ends, intervals

    def _add_fs_precedence_constraints(
        self,
        model: cp_model.CpModel,
        dag: ActivityDAG,
        acts: dict[str, Activity],
        starts: dict[str, cp_model.IntVar],
        ends: dict[str, cp_model.IntVar],
    ) -> None:
        """Adiciona as precedências FS do ActivityDAG (ADR-081: completion_threshold_pct)."""
        for pred_id, succ_id in dag.precedence:
            theta = dag.get_threshold(pred_id, succ_id)
            if pred_id not in acts or succ_id not in acts:
                continue
            if theta >= 1.0:
                model.add(starts[succ_id] >= ends[pred_id])
            else:
                lag = math.ceil(theta * acts[pred_id].duration_weeks)
                model.add(starts[succ_id] >= starts[pred_id] + lag)

    def _add_extended_precedence_constraints(
        self,
        model: cp_model.CpModel,
        dag: ActivityDAG,
        extended_precedences: list[ExtendedPrecedence] | None,
        starts: dict[str, cp_model.IntVar],
        ends: dict[str, cp_model.IntVar],
    ) -> None:
        """Adiciona precedências estendidas SS/FF/FS+lag (NEP-031 L4)."""
        # NEP-031 L4: inclui extended_precedences do DAG (SS/FF da EAP) e
        # quaisquer precedências extra passadas diretamente pelo chamador.
        all_extended = list(getattr(dag, "extended_precedences", None) or [])
        all_extended.extend(extended_precedences or [])
        for ep in all_extended:
            pred_id, succ_id = ep.pred, ep.succ
            lag = ep.lag
            if ep.tipo == "FS":
                model.add(starts[succ_id] >= ends[pred_id] + lag)
            elif ep.tipo == "SS":
                model.add(starts[succ_id] >= starts[pred_id] + lag)
            elif ep.tipo == "FF":
                model.add(ends[succ_id] >= ends[pred_id] + lag)
            else:
                _log.warning("Unknown precedence type %s; skipping", ep.tipo)

    def _add_resource_constraints(
        self,
        model: cp_model.CpModel,
        dag: ActivityDAG,
        pool: ResourcePool,
        intervals: dict[str, cp_model.IntervalVar],
    ) -> None:
        """Adiciona restrições cumulativas de capacidade por recurso."""
        for res, cap in pool.resources.items():
            res_intervals: list[cp_model.IntervalVar] = []
            res_demands: list[int] = []
            for a in dag.activities:
                demand = a.required_resources.get(res, 0)
                if demand > 0:
                    res_intervals.append(intervals[a.activity_id])
                    res_demands.append(demand)
            if res_intervals:
                model.add_cumulative(res_intervals, res_demands, cap)

    @staticmethod
    def _validate_classic_precedence(
        dag: ActivityDAG,
        acts: dict[str, Activity],
        by_id: dict[str, ScheduledActivity],
    ) -> bool:
        """Precedências FS (ActivityDAG.precedence + thresholds, ADR-081)."""
        for pred_id, succ_id in dag.precedence:
            if pred_id not in by_id or succ_id not in by_id:
                continue
            theta = dag.get_threshold(pred_id, succ_id)
            pred, succ = by_id[pred_id], by_id[succ_id]
            if theta >= 1.0:
                if succ.start_week < pred.end_week:
                    return False
            else:
                lag = math.ceil(theta * acts[pred_id].duration_weeks)
                if succ.start_week < pred.start_week + lag:
                    return False
        return True

    @staticmethod
    def _is_extended_precedence_violated(
        ep: ExtendedPrecedence, pred: ScheduledActivity, succ: ScheduledActivity
    ) -> bool:
        """Checa um único vínculo estendido SS/FF/FS+lag (NEP-031 L4)."""
        if ep.tipo == "FS":
            return succ.start_week < pred.end_week + ep.lag
        if ep.tipo == "SS":
            return succ.start_week < pred.start_week + ep.lag
        if ep.tipo == "FF":
            return succ.end_week < pred.end_week + ep.lag
        return False

    @staticmethod
    def _validate_extended_precedence(
        dag: ActivityDAG,
        extended_precedences: list[ExtendedPrecedence] | None,
        by_id: dict[str, ScheduledActivity],
    ) -> bool:
        """Precedências estendidas SS/FF/FS+lag (NEP-031 L4)."""
        all_extended = list(getattr(dag, "extended_precedences", None) or [])
        all_extended.extend(extended_precedences or [])
        for ep in all_extended:
            if ep.pred not in by_id or ep.succ not in by_id:
                continue
            pred, succ = by_id[ep.pred], by_id[ep.succ]
            if CpSatScheduler._is_extended_precedence_violated(ep, pred, succ):
                return False
        return True

    def _validate_pool_capacity(self, scheduled: list[ScheduledActivity], pool: ResourcePool) -> bool:
        """Capacidade de ResourcePool (recursos reutilizáveis, não-consumíveis)."""
        weekly = self._compute_weekly_resource_usage(scheduled)
        for usages in weekly.values():
            for res, qty in usages.items():
                cap = pool.resources.get(res)
                if cap is not None and qty > cap:
                    return False
        return True

    def _validate_repaired_schedule(
        self,
        scheduled: list[ScheduledActivity],
        dag: ActivityDAG,
        extended_precedences: list[ExtendedPrecedence] | None,
        pool: ResourcePool,
        horizon: int,
    ) -> bool:
        """Revalida hard constraints após o reparo de disponibilidade (ADR-128).

        O CP-SAT garante precedência, capacidade de pool e horizonte na solução
        original — `apply_replenishable_delay` desloca atividades fora do solver e
        pode quebrar qualquer uma dessas garantias. Retorna False (infeasible) se
        alguma violação for detectada.
        """
        by_id = {sa.activity_id: sa for sa in scheduled}
        acts = {a.activity_id: a for a in dag.activities}

        # Horizonte
        if any(sa.end_week > horizon for sa in scheduled):
            return False

        if not self._validate_classic_precedence(dag, acts, by_id):
            return False

        if not self._validate_extended_precedence(dag, extended_precedences, by_id):
            return False

        return self._validate_pool_capacity(scheduled, pool)

    @staticmethod
    def _build_scheduled_activities(
        dag: ActivityDAG, solver: cp_model.CpSolver, starts: dict[str, cp_model.IntVar]
    ) -> list[ScheduledActivity]:
        """Converte os valores resolvidos de start em uma lista de ScheduledActivity."""
        scheduled: list[ScheduledActivity] = []
        for a in dag.activities:
            s = solver.value(starts[a.activity_id])
            e = s + a.duration_weeks
            scheduled.append(
                ScheduledActivity(
                    activity_id=a.activity_id,
                    start_week=s,
                    end_week=e,
                    duration_weeks=a.duration_weeks,
                    assigned_resources=dict(a.required_resources),
                    ramp_profile=a.ramp_profile,
                )
            )
        return scheduled

    @staticmethod
    def _validate_producao_reference(
        acts: dict[str, Activity], replenishable_resources: list[ReplenishableResource] | None
    ) -> None:
        """ADR-139 D4: valida referência de atividade produtora (fail loud).

        producao_por_semana é campo novo (sem legado): referência a atividade fora
        do DAG é sempre erro de montagem do projeto, nunca dado histórico tolerável.
        """
        for resource in replenishable_resources or []:
            desconhecidas = sorted(set(resource.producao_por_semana) - set(acts))
            if desconhecidas:
                raise ValueError(
                    f"VAL-ESTOQUE-PROD-01: producao_por_semana do recurso "
                    f"'{resource.resource_id}' referencia atividade(s) fora do DAG: "
                    f"{', '.join(desconhecidas)}"
                )

    def _build_model(
        self,
        dag: ActivityDAG,
        pool: ResourcePool,
        acts: dict[str, Activity],
        horizon: int,
        extended_precedences: list[ExtendedPrecedence] | None,
    ) -> tuple[cp_model.CpModel, dict[str, cp_model.IntVar], cp_model.IntVar]:
        """Monta o modelo CP-SAT completo: variáveis de decisão, precedências FS e
        estendidas, restrições de capacidade e o objetivo de minimizar o makespan."""
        model = cp_model.CpModel()
        starts, ends, intervals = self._add_activity_variables(model, dag, horizon)
        self._add_fs_precedence_constraints(model, dag, acts, starts, ends)
        self._add_extended_precedence_constraints(model, dag, extended_precedences, starts, ends)
        self._add_resource_constraints(model, dag, pool, intervals)

        makespan = model.new_int_var(0, horizon, "makespan")
        model.add_max_equality(makespan, list(ends.values()))
        model.minimize(makespan)
        return model, starts, makespan

    def _solve_model(
        self, model: cp_model.CpModel, makespan: cp_model.IntVar
    ) -> tuple[cp_model.CpSolver, cp_model.CpSolverStatus]:
        """Configura os parâmetros do solver CP-SAT e resolve o modelo."""
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = self.timeout_seconds
        solver.parameters.num_workers = self.num_workers
        solver.parameters.log_search_progress = False

        callback = _MakespanCallback(makespan)
        status = solver.solve(model, callback)
        return solver, status

    @staticmethod
    def _repair_replenishable_delays(
        scheduled: list[ScheduledActivity],
        dag: ActivityDAG,
        extended_precedences: list[ExtendedPrecedence] | None,
        replenishable_resources: list[ReplenishableResource] | None,
    ) -> tuple[list[ScheduledActivity], dict[tuple[str, str], int]]:
        """ADR-128: post-process consumable-resource delays (opt-in).

        Fase 2b: reparo de estoque e repropagação de precedência rodam em laço de
        ponto fixo — repropagar um atraso pode empurrar uma atividade que consome um
        OUTRO recurso consumível, reabrindo uma violação de estoque já resolvida para
        esse recurso (ver _MAX_REPAIR_ROUNDS acima).
        """
        delay_causes: dict[tuple[str, str], int] = {}
        for _round in range(_MAX_REPAIR_ROUNDS):
            before = [(sa.start_week, sa.end_week) for sa in scheduled]
            for resource in replenishable_resources or []:
                scheduled = apply_replenishable_delay(scheduled, resource, delay_causes)
            scheduled = repropagate_precedence_delays(scheduled, dag, extended_precedences)
            after = [(sa.start_week, sa.end_week) for sa in scheduled]
            if before == after:
                break
        return scheduled, delay_causes

    def _check_repair_feasibility(
        self,
        scheduled: list[ScheduledActivity],
        dag: ActivityDAG,
        extended_precedences: list[ExtendedPrecedence] | None,
        pool: ResourcePool,
        horizon: int,
        replenishable_resources: list[ReplenishableResource] | None,
    ) -> bool:
        """Revalida o cronograma reparado (ADR-128).

        O reparo de estoque desloca a atividade consumidora e a repropagação de
        precedência (ADR-128 Fase 2b) empurra seus sucessores no DAG para preservar
        FS/SS/FF/FS+lag — mas o laço de ponto fixo tem cota (`_MAX_REPAIR_ROUNDS`) e
        nenhuma das duas passadas sabe sobre capacidade de `ResourcePool` ou o
        horizonte. Marca infeasible em vez de devolver um cronograma potencialmente
        inválido como feasible=True — rede de segurança final.
        """
        if not self._validate_repaired_schedule(scheduled, dag, extended_precedences, pool, horizon):
            _log.warning(
                "CpSatScheduler: reparo de disponibilidade de consumíveis (ADR-128) "
                "violou precedência, capacidade de pool ou horizonte — output marcado "
                "como infeasible."
            )
            return False
        if any(
            has_estoque_negativo(project_estoque_semanal(resource, scheduled))
            for resource in replenishable_resources or []
        ):
            # ADR-128 F5: o laço de ponto fixo pode esgotar _MAX_REPAIR_ROUNDS sem
            # convergir — sem esta checagem, o estoque final poderia seguir negativo
            # para algum recurso e o cronograma ainda ser reportado feasible=True.
            _log.warning(
                "CpSatScheduler: reparo de disponibilidade de consumíveis (ADR-128) "
                "esgotou _MAX_REPAIR_ROUNDS sem eliminar estoque negativo — output "
                "marcado como infeasible."
            )
            return False
        return True

    def schedule(
        self,
        dag: ActivityDAG,
        pool: ResourcePool,
        ramp_profiles: dict[str, RampProfile] | None = None,
        extended_precedences: list[ExtendedPrecedence] | None = None,
        replenishable_resources: list[ReplenishableResource] | None = None,
    ) -> ScheduleOutput:
        """Solve RCPSP and return a ScheduleOutput.

        Args:
            dag:                   Activities and FS precedence list.
            pool:                  Resource capacities.
            ramp_profiles:         Optional ADR-075 ramp profiles (used for
                                   future mob-cost callback; not yet used for
                                   resource demand shaping in this version).
            extended_precedences:  Optional SS/FF/FS+lag constraints beyond the
                                   basic FS pairs in dag.precedence.
            replenishable_resources: Optional ADR-128 consumable resources (diesel/
                                   material) with stock/replenishment. When omitted
                                   (default), behaviour is unchanged from pre-ADR-128
                                   (unrestricted consumable availability). When
                                   present, activities whose consumption would drive
                                   the projected stock negative are delayed as a
                                   post-processing pass over the CP-SAT solution.
        """
        acts: dict[str, Activity] = {a.activity_id: a for a in dag.activities}
        H = self.horizon_weeks

        self._validate_producao_reference(acts, replenishable_resources)

        model, starts, makespan = self._build_model(dag, pool, acts, H, extended_precedences)

        solver, status = self._solve_model(model, makespan)
        feasible = status in (cp_model.OPTIMAL, cp_model.FEASIBLE)

        if not feasible:  # pragma: no branch
            _log.warning(
                "CpSatScheduler: no feasible solution found (status=%s) within %.1fs",
                solver.status_name(status),
                self.timeout_seconds,
            )
            # Return an empty but structurally valid ScheduleOutput
            return self._empty_output(dag)

        # ── build output ─────────────────────────────────────────────────
        scheduled = self._build_scheduled_activities(dag, solver, starts)

        repaired = bool(replenishable_resources)
        delay_causes: dict[tuple[str, str], int] = {}
        if repaired:
            scheduled, delay_causes = self._repair_replenishable_delays(
                scheduled, dag, extended_precedences, replenishable_resources
            )

        feasible = True
        if repaired and not self._check_repair_feasibility(
            scheduled, dag, extended_precedences, pool, H, replenishable_resources
        ):
            feasible = False

        ms_val = max((sa.end_week for sa in scheduled), default=solver.value(makespan))
        metrics = self._compute_metrics(scheduled, pool, ms_val)
        estoque_delays = [
            EstoqueDelayCause(resource_id=rid, activity_id=aid, delay_weeks=weeks)
            for (rid, aid), weeks in sorted(delay_causes.items())
        ]
        # ADR-128 F7: só há "quantidade que faltou" quando o reparo de fato quebrou
        # algo — feasible=True nunca reporta deficit (regressão zero).
        pool_deficit = self._compute_pool_deficit(scheduled, pool) if not feasible else {}

        return ScheduleOutput(
            scheduled_activities=scheduled,
            makespan=ms_val,
            feasible=feasible,
            metrics=metrics,
            heuristic="CP-SAT",
            estoque_delays=estoque_delays,
            pool_deficit=pool_deficit,
        )

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _compute_weekly_resource_usage(scheduled: list[ScheduledActivity]) -> dict[int, dict[str, int]]:
        """Agrega a demanda de recursos por semana ao longo do horizonte agendado."""
        weekly: dict[int, dict[str, int]] = {}
        for sa in scheduled:
            for t in range(sa.start_week, sa.end_week):
                for res, qty in sa.assigned_resources.items():
                    weekly.setdefault(t, {}).setdefault(res, 0)
                    weekly[t][res] += qty
        return weekly

    @staticmethod
    def _compute_pool_deficit(scheduled: list[ScheduledActivity], pool: ResourcePool) -> dict[str, int]:
        """ADR-128 F7: pico real de demanda por recurso, só para os que excedem a
        capacidade declarada em `pool` — não a capacidade atual, nem um percentual
        dela. Usado para reportar causalmente por que o reparo de disponibilidade
        (estoque + repropagação de precedência) quebrou capacidade de `ResourcePool`,
        permitindo ao chamador recalcular o pool exato necessário em vez de relaxar
        às cegas (issue #117)."""
        weekly = CpSatScheduler._compute_weekly_resource_usage(scheduled)
        peak: dict[str, int] = {}
        for usages in weekly.values():
            for res, qty in usages.items():
                if qty > peak.get(res, 0):
                    peak[res] = qty
        # Resource ausente de pool.resources = capacidade ilimitada (mesma convenção
        # de _validate_repaired_schedule: `cap is not None and qty > cap`) — nunca
        # entra como deficit.
        return {res: qty for res, qty in peak.items() if (cap := pool.resources.get(res)) is not None and qty > cap}

    @staticmethod
    def _compute_resource_leveling_score(pool: ResourcePool, weekly: dict[int, dict[str, int]], makespan: int) -> float:
        """Calcula o score de nivelamento (1 - variância relativa à capacidade) por recurso."""
        usages_per_res: dict[str, list[int]] = {}
        for res, _cap in pool.resources.items():
            usages_per_res[res] = [weekly.get(t, {}).get(res, 0) for t in range(makespan)]
        leveling_scores = []
        for res, vals in usages_per_res.items():
            cap = pool.resources[res]
            if cap > 0 and vals:
                mean = sum(vals) / len(vals)
                variance = sum((v - mean) ** 2 for v in vals) / len(vals)
                leveling_scores.append(max(0.0, 1.0 - math.sqrt(variance) / cap))
        return sum(leveling_scores) / len(leveling_scores) if leveling_scores else 1.0

    @classmethod
    def _compute_metrics(
        cls,
        scheduled: list[ScheduledActivity],
        pool: ResourcePool,
        makespan: int,
    ) -> ScheduleMetrics:
        if not scheduled or makespan == 0:
            return ScheduleMetrics(
                makespan=makespan,
                resource_leveling_score=1.0,
                idle_time=0,
                activity_fragmentation=0,
                critical_path_slack_min=0.0,
                resource_utilization_avg=0.0,
            )

        # Weekly resource usage
        weekly = cls._compute_weekly_resource_usage(scheduled)

        # Resource utilisation avg
        total_capacity = sum(pool.resources.values()) * makespan
        total_used = sum(qty for week_usage in weekly.values() for qty in week_usage.values())
        util_avg = total_used / total_capacity if total_capacity > 0 else 0.0

        # Leveling score: 1 - variance_ratio
        leveling = cls._compute_resource_leveling_score(pool, weekly, makespan)

        return ScheduleMetrics(
            makespan=makespan,
            resource_leveling_score=leveling,
            idle_time=0,
            activity_fragmentation=0,
            critical_path_slack_min=0.0,
            resource_utilization_avg=util_avg,
        )

    def _empty_output(self, dag: ActivityDAG) -> ScheduleOutput:
        return ScheduleOutput(
            scheduled_activities=[],
            makespan=0,
            feasible=False,
            metrics=ScheduleMetrics(
                makespan=0,
                resource_leveling_score=0.0,
                idle_time=0,
                activity_fragmentation=0,
                critical_path_slack_min=0.0,
                resource_utilization_avg=0.0,
            ),
            heuristic="CP-SAT",
        )
