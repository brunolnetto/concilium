"""P15-C: bounded physical re-resolution wired to actual Skill 04 output."""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Literal

from concilium.application.scheduling.physical_resolver import (
    MAX_PHYSICAL_RCPSP_STATES,
    PhysicalEvidenceUnknown,
    resolve_bounded_physical_calendar,
)
from concilium.application.scheduling.physical_validator import (
    PhysicalActivity,
    PhysicalPrecedence,
    validate_materialized_calendar,
)
from concilium.application.scheduling.skill04_physical_bridge import (
    materialize_skill04_physical_activity,
)
from concilium.domain.models.canonical import CanonicalModel, ScheduleCandidateCanonical, ValidacaoItem

from ._calendario import _build_item_to_activity_map, _resolve_productivity  # ty: ignore[unresolved-import]
from ._custos import _origem_capacidade  # ty: ignore[unresolved-import]
from ._scheduling import (  # ty: ignore[unresolved-import]
    _build_activity_distribuicao,
    _compute_activity_n_max,
    _convert_schedule_to_distribuicao,
)

ResolveRuntimeStatus = Literal["NOT_APPLICABLE", "PASS", "FAIL", "UNKNOWN"]


@dataclass(frozen=True)
class Skill04PhysicalResolution:
    status: ResolveRuntimeStatus
    schedule_selected: ScheduleCandidateCanonical | None
    distribution_by_item: dict[str, dict]
    fallback_item_ids: set[str]
    attempts: int
    reason: str
    violation_details: tuple[str, ...] = ()
    complete_search: bool | None = None
    audit_status: Literal["PASS", "FAIL", "UNKNOWN"] | None = None


def _explicit_physical_pool(
    canonical: CanonicalModel,
    inputs: dict[str, Any],
) -> tuple[dict[str, Fraction] | None, str | None]:
    """Return only declared capacity; a pool inferred by the scheduler is not evidence."""
    canonical_pool: dict[str, Fraction] = {}
    for pool in canonical.recurso_pool or []:
        if pool.proveniencia != "CONFIGURADO":
            continue
        canonical_pool[pool.tipo_id] = canonical_pool.get(pool.tipo_id, Fraction()) + Fraction(
            pool.quantidade_total
        )

    spec = inputs.get("rcpsp_spec")
    spec_pool: dict[str, Fraction] | None = None
    if isinstance(spec, dict) and spec.get("resource_pool") and not spec.get("pool_inferido_diag"):
        raw = spec.get("resource_pool")
        if not isinstance(raw, dict):
            return None, "rcpsp_spec.resource_pool is not an explicit mapping"
        spec_pool = {}
        for resource, quantity in raw.items():
            if not isinstance(resource, str) or not resource:
                return None, "rcpsp_spec contains an empty/non-string resource identifier"
            if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 0:
                return None, f"invalid explicit resource capacity for {resource!r}"
            spec_pool[resource] = Fraction(quantity)

    if canonical_pool and spec_pool is not None and canonical_pool != spec_pool:
        return None, (
            "conflicting configured physical pool declarations between CanonicalModel and rcpsp_spec"
        )
    chosen = spec_pool if spec_pool is not None else canonical_pool
    if not chosen:
        return None, "no explicit physical resource pool; inferred/default pools are not capacity evidence"
    return chosen, None


def _physical_precedences(canonical: CanonicalModel) -> tuple[PhysicalPrecedence, ...]:
    edges: list[PhysicalPrecedence] = []
    for successor in canonical.eap or []:
        for predecessor in successor.predecessores_tipados():
            kind = str(getattr(predecessor, "tipo", "FS") or "FS").upper()
            if kind not in ("FS", "SS", "FF"):
                raise ValueError(
                    f"{successor.item_id}: unsupported physical predecessor relation {kind!r}"
                )
            lag = getattr(predecessor, "lag", 0) or 0
            threshold = getattr(predecessor, "completion_threshold_pct", 1)
            if isinstance(lag, bool) or not isinstance(lag, int) or lag < 0:
                raise ValueError(f"{successor.item_id}: invalid physical predecessor lag")
            try:
                theta = Fraction(str(threshold))
            except (TypeError, ValueError, ZeroDivisionError) as exc:
                raise ValueError(f"{successor.item_id}: invalid physical completion threshold") from exc
            edges.append(
                PhysicalPrecedence(
                    predecessor=str(predecessor.item_id),
                    successor=str(successor.item_id),
                    kind=kind,
                    lag_weeks=lag,
                    completion_threshold=theta,
                )
            )
    return tuple(edges)


def resolve_skill04_physical_schedule(
    *,
    canonical: CanonicalModel,
    inputs: dict[str, Any],
    mode: str | None,
    schedule_selected: ScheduleCandidateCanonical | None,
    distribution_by_item: dict[str, dict],
    fallback_item_ids: set[str],
    weeks: list[str],
    cpu_lookup: dict[str, dict],
    production_lookup: dict[str, dict],
    regime: Any,
    practicability_weekly: dict[str, float],
    practicability_monthly: dict[str, float],
    calendar_factor_weekly: dict[str, float],
    validacoes: list[ValidacaoItem],
) -> Skill04PhysicalResolution:
    """Resolve AUTO candidates by re-materializing real Skill 04 weekly cells.

    Candidate starts are bounded below by the selected RCPSP week and may
    move only later within the declared project horizon. Each trial recomputes
    throughput using that week's climate/calendar and the existing F(m) law; it
    never moves an old Q series unchanged. Resource reservations come from the
    actual selected RCPSP assignments and a declared pool. PASS establishes one
    feasible witness only, not global optimality or financial GO.
    """
    if not mode or not mode.startswith("AUTO") or schedule_selected is None:
        return Skill04PhysicalResolution(
            "NOT_APPLICABLE", schedule_selected, distribution_by_item,
            fallback_item_ids, 0, "no AUTO schedule candidate",
        )
    if not weeks or not schedule_selected.scheduled_activities:
        return Skill04PhysicalResolution(
            "UNKNOWN", schedule_selected, distribution_by_item,
            fallback_item_ids, 0, "empty calendar or AUTO schedule candidate",
        )

    pool_capacity, pool_error = _explicit_physical_pool(canonical, inputs)
    if pool_capacity is None:
        return Skill04PhysicalResolution(
            "UNKNOWN", schedule_selected, distribution_by_item,
            fallback_item_ids, 0, pool_error or "physical pool is unknown",
        )

    item_to_activity = _build_item_to_activity_map(canonical)
    # Skill 04 scheduler IDs are activity IDs, while the physical validator
    # and EAP precedence edges are keyed by item IDs.
    activity_to_item = {activity_id: item_id for item_id, activity_id in item_to_activity.items()}
    eap_by_id = {item.item_id: item for item in canonical.eap or []}
    selected_by_item: dict[str, Any] = {}
    assigned_by_item: dict[str, dict[str, int]] = {}
    for scheduled in schedule_selected.scheduled_activities:
        item_id = activity_to_item.get(scheduled.activity_id, scheduled.activity_id)
        if item_id in selected_by_item:
            return Skill04PhysicalResolution(
                "FAIL", schedule_selected, distribution_by_item,
                fallback_item_ids, 0, f"duplicate scheduled activity mapping for {item_id}",
            )
        selected_by_item[item_id] = scheduled
        assignment = getattr(scheduled, "assigned_resources", None)
        if not isinstance(assignment, dict) or not assignment:
            return Skill04PhysicalResolution(
                "UNKNOWN", schedule_selected, distribution_by_item,
                fallback_item_ids, 0, f"{item_id}: no explicit assigned_resources witness",
            )
        clean_assignment: dict[str, int] = {}
        for resource, count in assignment.items():
            if not isinstance(resource, str) or not resource:
                return Skill04PhysicalResolution(
                    "UNKNOWN", schedule_selected, distribution_by_item,
                    fallback_item_ids, 0, f"{item_id}: invalid resource identifier",
                )
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                return Skill04PhysicalResolution(
                    "UNKNOWN", schedule_selected, distribution_by_item,
                    fallback_item_ids, 0, f"{item_id}/{resource}: invalid physical resource count",
                )
            if count:
                clean_assignment[resource] = count
        if not clean_assignment:
            return Skill04PhysicalResolution(
                "UNKNOWN", schedule_selected, distribution_by_item,
                fallback_item_ids, 0, f"{item_id}: assigned_resources has no positive demand",
            )
        assigned_by_item[item_id] = clean_assignment

    item_ids = tuple(sorted(selected_by_item))
    if any(item_id not in eap_by_id for item_id in item_ids):
        missing = sorted(set(item_ids) - set(eap_by_id))
        return Skill04PhysicalResolution(
            "UNKNOWN", schedule_selected, distribution_by_item,
            fallback_item_ids, 0, f"scheduled items lack EAP scope: {missing}",
        )
    eap_item_ids = {item.item_id for item in canonical.eap or []}
    if set(item_ids) != eap_item_ids:
        missing = sorted(eap_item_ids - set(item_ids))
        extra = sorted(set(item_ids) - eap_item_ids)
        return Skill04PhysicalResolution(
            "UNKNOWN", schedule_selected, distribution_by_item,
            fallback_item_ids, 0,
            f"AUTO candidate does not cover the exact EAP scope; missing={missing}, extra={extra}",
        )

    # P15 re-resolves the selected RCPSP candidate; it is not allowed to erase
    # hard lower bounds already imposed by the scheduler (e.g. replenishment
    # delays). Physical evidence may push an activity later, never earlier.
    allowed_starts: dict[str, tuple[int, ...]] = {}
    for item_id in item_ids:
        selected_start = getattr(selected_by_item[item_id], "start_week", None)
        if (
            isinstance(selected_start, bool)
            or not isinstance(selected_start, int)
            or not 0 <= selected_start < len(weeks)
        ):
            return Skill04PhysicalResolution(
                "UNKNOWN", schedule_selected, distribution_by_item,
                fallback_item_ids, 0,
                f"{item_id}: selected scheduler start week is outside the declared calendar",
            )
        allowed_starts[item_id] = tuple(range(selected_start, len(weeks)))

    # An explicit pool is a complete inventory. A missing resource key therefore
    # has capacity zero, not an optimistic/unbounded capacity.
    pool_capacity = {
        **pool_capacity,
        **{
            resource: Fraction(0)
            for assignment in assigned_by_item.values()
            for resource in assignment
            if resource not in pool_capacity
        },
    }

    max_states = inputs.get("physical_rcpsp_max_states", 10_000)
    if type(max_states) is not int or not 1 <= max_states <= MAX_PHYSICAL_RCPSP_STATES:
        return Skill04PhysicalResolution(
            "FAIL", schedule_selected, distribution_by_item,
            fallback_item_ids, 0,
            "physical_rcpsp_max_states must be an integer between "
            f"1 and {MAX_PHYSICAL_RCPSP_STATES}",
        )

    hours_week = float(regime.horas_dia) * float(regime.dias_semana)
    item_cache: dict[str, tuple[Any, dict, float, bool, dict, int]] = {}
    for item_id in item_ids:
        scheduled = selected_by_item[item_id]
        item = eap_by_id[item_id]
        cpu = cpu_lookup.get(item.cpu_id) or {
            "codigo": item.cpu_id,
            "descricao": f"CPU sintética para {item_id}",
            "producao_id_ref": None,
        }
        local_validations: list[ValidacaoItem] = []
        productivity, is_fallback = _resolve_productivity(cpu, production_lookup, local_validations)
        if not isinstance(productivity, (int, float)) or not float(productivity) > 0:
            return Skill04PhysicalResolution(
                "UNKNOWN", schedule_selected, distribution_by_item,
                fallback_item_ids, 0, f"{item_id}: productivity cannot be materialized",
            )
        n_max = _compute_activity_n_max(scheduled, cpu, scheduled.ramp_profile)
        item_cache[item_id] = (
            scheduled, cpu, float(productivity), is_fallback,
            production_lookup.get(cpu.get("producao_id_ref")) or {}, max(1, n_max),
        )

    def materialize(item_id: str, start: int) -> PhysicalActivity | None:
        scheduled, cpu, productivity, is_fallback, _prod_item, n_max = item_cache[item_id]
        item = eap_by_id[item_id]
        candidate = scheduled.model_copy(update={"start_week": start})
        try:
            distribution, _delivered = _build_activity_distribuicao(
                candidate,
                item,
                cpu,
                scheduled.ramp_profile,
                n_max,
                productivity * hours_week,
                weeks,
                canonical,
                practicability_weekly,
                practicability_monthly,
                calendar_factor_weekly,
                fator_jornada=float(regime.eta_jornada),
                producao_lookup=production_lookup,
                horas_semana=hours_week,
                origem_produtividade=_origem_capacidade(
                    production_lookup.get(cpu.get("producao_id_ref")),
                    is_fallback=is_fallback,
                ),
            )
            if not distribution:
                return None
            # Preserve partial real-calendar delivery as diagnostic evidence.
            # The independent physical validator must reject the unclosed scope
            # and retain its exact residual; dropping this candidate here would
            # turn a known Q/sum_q mismatch into a generic "no admissible schedule".
            demand_by_week = {
                week: assigned_by_item[item_id]
                for week in distribution
            }
            return materialize_skill04_physical_activity(
                item_id=item_id,
                scope=item.quantitativo,
                calendar_weeks=weeks,
                distribution=distribution,
                demand_by_week=demand_by_week,
            )
        except (KeyError, TypeError, ValueError, OverflowError, ZeroDivisionError) as exc:
            # The start was not proven infeasible: the physical witness itself was invalid.
            raise PhysicalEvidenceUnknown(
                f"{item_id}@{start}: physical materialization evidence invalid: {exc}"
            ) from exc

    try:
        precedences = _physical_precedences(canonical)
        resolution = resolve_bounded_physical_calendar(
            item_ids,
            allowed_starts,
            materialize,
            precedences,
            calendar_horizon_weeks=len(weeks),
            pool_capacity=pool_capacity,
            max_states=max_states,
        )
    except (KeyError, TypeError, ValueError, OverflowError, ZeroDivisionError) as exc:
        return Skill04PhysicalResolution(
            "UNKNOWN", schedule_selected, distribution_by_item,
            fallback_item_ids, 0, f"physical resolver input invalid: {exc}",
        )

    if resolution.status != "PASS" or not resolution.activities:
        violations = tuple(
            f"{v.code}:{v.item_id}:{v.week}:{v.reason}"
            for v in (resolution.last_audit.violations if resolution.last_audit else ())
        )
        details = list(violations)
        if resolution.unknown_reason:
            details.insert(0, "materialization UNKNOWN: " + resolution.unknown_reason)
        reason = (
            "no admissible fully materialized physical calendar"
            if not details else "; ".join(details[:8])
        )
        return Skill04PhysicalResolution(
            resolution.status, schedule_selected, distribution_by_item,
            fallback_item_ids, resolution.attempts,
            reason,
            violations,
            resolution.complete_search,
            audit_status=resolution.last_audit.status if resolution.last_audit else None,
        )

    physical_by_item = {activity.item_id: activity for activity in resolution.activities}
    updated_scheduled = []
    for scheduled in schedule_selected.scheduled_activities:
        item_id = activity_to_item.get(scheduled.activity_id, scheduled.activity_id)
        physical = physical_by_item[item_id]
        duration = physical.end_week_exclusive - physical.start_week
        updated_scheduled.append(
            scheduled.model_copy(update={
                "start_week": physical.start_week,
                "end_week": physical.end_week_exclusive - 1,
                "duration_weeks": duration,
                "distribuicao_semanal": {},
            })
        )
    selected = schedule_selected.model_copy(update={
        "scheduled_activities": updated_scheduled,
        "makespan": max(a.end_week_exclusive for a in resolution.activities),
    })

    prior_validation_count = len(validacoes)
    rematerialized, rematerialized_fallback = _convert_schedule_to_distribuicao(
        selected,
        canonical,
        weeks,
        cpu_lookup,
        production_lookup,
        regime,
        practicability_weekly,
        practicability_monthly,
        calendar_factor_weekly,
        validacoes,
    )
    new_errors = [
        v for v in validacoes[prior_validation_count:]
        if v.status == "ERRO"
    ]
    if new_errors or set(rematerialized) != set(item_ids) or any(not rematerialized.get(i) for i in item_ids):
        return Skill04PhysicalResolution(
            "FAIL", selected, rematerialized, rematerialized_fallback,
            resolution.attempts,
            "Skill 04 failed to materialize the selected physical witness after RCPSP resolution",
            tuple(f"{v.codigo}:{v.mensagem}" for v in new_errors),
            resolution.complete_search,
        )

    actual_activities: list[PhysicalActivity] = []
    try:
        for item_id in item_ids:
            actual_activities.append(
                materialize_skill04_physical_activity(
                    item_id=item_id,
                    scope=eap_by_id[item_id].quantitativo,
                    calendar_weeks=weeks,
                    distribution=rematerialized[item_id],
                    demand_by_week={
                        week: assigned_by_item[item_id]
                        for week in rematerialized[item_id]
                    },
                )
            )
        audit = validate_materialized_calendar(
            actual_activities,
            precedences,
            calendar_horizon_weeks=len(weeks),
            pool_capacity=pool_capacity,
            require_weekly_capacity=True,
        )
    except (KeyError, TypeError, ValueError, OverflowError, ZeroDivisionError) as exc:
        return Skill04PhysicalResolution(
            "FAIL", selected, rematerialized, rematerialized_fallback,
            resolution.attempts, f"post-rematerialization physical audit failed: {exc}",
            (), resolution.complete_search, audit_status="FAIL",
        )

    if audit.status != "PASS":
        violations = tuple(
            f"{v.code}:{v.item_id}:{v.week}:{v.reason}" for v in audit.violations
        )
        return Skill04PhysicalResolution(
            "FAIL" if audit.status == "FAIL" else "UNKNOWN",
            selected, rematerialized, rematerialized_fallback,
            resolution.attempts, "post-rematerialization Skill 04/05 audit did not PASS",
            violations,
            resolution.complete_search,
            audit_status=audit.status,
        )

    # The initial AUTO pass may have reported an under-delivery or Q-precedence
    # error that this joint re-solve repaired. Remove only those pre-re-solve
    # errors after the same final materialization independently passes.
    validacoes[:] = [
        value for index, value in enumerate(validacoes)
        if not (
            index < prior_validation_count
            and value.status == "ERRO"
            and value.codigo in {"VAL-CRON-01", "VAL-CRON-PRECEDENCIA"}
        )
    ]
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-RCPSP-RESOLVED",
            status="OK",
            mensagem=(
                f"P15: calendário físico re-materializado e validado em {resolution.attempts} "
                f"tentativas; busca_completa={resolution.complete_search}. "
                "Este é um testemunho físico local, não prova financeira/global GO."
            ),
        )
    )

    # Synchronize canonical schedule coordinates with the re-materialized output.
    by_item_weeks = {
        item_id: sorted(
            (weeks.index(week), week) for week in rematerialized[item_id]
        )
        for item_id in item_ids
    }
    final_scheduled = []
    for scheduled in selected.scheduled_activities:
        item_id = activity_to_item.get(scheduled.activity_id, scheduled.activity_id)
        rows = by_item_weeks[item_id]
        start, end_exclusive = rows[0][0], rows[-1][0] + 1
        final_scheduled.append(
            scheduled.model_copy(update={
                "start_week": start,
                "end_week": end_exclusive - 1,
                "duration_weeks": end_exclusive - start,
                "distribuicao_semanal": rematerialized[item_id],
            })
        )
    final_makespan = max(
        weeks.index(week) + 1
        for distribution in rematerialized.values()
        for week in distribution
    )
    selected = selected.model_copy(update={
        "scheduled_activities": final_scheduled,
        "makespan": max(1, final_makespan),
    })
    return Skill04PhysicalResolution(
        "PASS", selected, rematerialized, rematerialized_fallback,
        resolution.attempts,
        "bounded exact physical feasibility witness",
        (), resolution.complete_search, audit_status=audit.status,
    )
