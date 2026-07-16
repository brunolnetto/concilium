"""Skill 04 — Cronograma (parte extraída de skill.py)."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any, Literal

from concilium.application.scheduling.mob_scheduling import infer_mob_windows
from concilium.application.scheduling.models import ReplenishableResource
from concilium.domain.models.canonical import (
    AtividadeIntervalo,
    CanonicalModel,
    Cronograma,
    RegimeTrabalho,
    ScheduleCandidateCanonical,
    ScheduledActivityCanonical,
    ValidacaoItem,
)

from ._calendario import _build_fator_calendario_semanal  # ty: ignore[unresolved-import]
from ._custos import (  # ty: ignore[unresolved-import]
    _build_cpu_lookup,
    _build_insumos_lookup,
    _build_producao_lookup,
    _enrich_producao_canonico,
    _semanas_entre,
    _week_offset,
)
from ._scheduling import (  # ty: ignore[unresolved-import]
    _convert_schedule_to_distribuicao,
    _process_single_wmp_policy,
    _run_auto_schedule_fallback_chain,
)
from ._validacao import _can_extract_dag, _execute_manual_mode  # ty: ignore[unresolved-import]

if TYPE_CHECKING:
    pass


def _extract_praticabilidade(canonical_in: CanonicalModel) -> tuple[dict, dict]:
    p = getattr(canonical_in, "praticabilidade", None)
    prat_semanal = (p.percentual_produtivo_semanal if p else {}) or {}
    prat_mensal = (p.percentual_produtivo_mensal if p else {}) or {}
    return prat_semanal, prat_mensal


def _determine_mode_and_distribuicao(
    canonical_in: CanonicalModel,
    inputs: dict,
    num_equipes_por_item: dict[str, dict[str, int]] | None,
    semanas_obra: list,
    cpu_lookup: dict,
    producao_lookup: dict,
    regime: RegimeTrabalho,
    prat_semanal: dict,
    prat_mensal: dict,
    fator_calendario_semanal: dict[str, float],
    catalogo: dict,
    validacoes: list,
    insumos_lookup: dict | None = None,
) -> tuple[str | None, dict, list, ScheduleCandidateCanonical | None, bool, list[ReplenishableResource]]:
    """Returns (mode, distribuicao_por_item, schedule_candidates, schedule_selected, failed,
    replenishable_resources) — o 6º elemento (ADR-128 F6) é vazio em MANUAL_ALLOCATION e no
    caso "nenhum modo detectado", já que só o path AUTO_SCHEDULE constrói ReplenishableResource.
    """
    rcpsp_spec = inputs.get("rcpsp_spec")
    if rcpsp_spec and isinstance(rcpsp_spec, dict):
        mode = "AUTO_SCHEDULE (rcpsp_spec)"
        validacoes.append(ValidacaoItem(codigo="VAL-CRON-MODE", status="OK", mensagem="Modo AUTO (rcpsp_spec)."))
        # ADR-072: pass lookups for productive-duration derivation
        schedule_candidates, schedule_selected, replenishable_resources = _run_auto_schedule_fallback_chain(
            canonical_in, inputs, validacoes, cpu_lookup, producao_lookup, insumos_lookup
        )
        if not schedule_selected:
            return mode, {}, schedule_candidates, None, True, []
        distribuicao_por_item = _convert_schedule_to_distribuicao(
            schedule_selected,
            canonical_in,
            semanas_obra,
            cpu_lookup,
            producao_lookup,
            regime,
            prat_semanal,
            prat_mensal,
            fator_calendario_semanal,
            validacoes,
        )
        return mode, distribuicao_por_item, schedule_candidates, schedule_selected, False, replenishable_resources

    elif num_equipes_por_item is not None and isinstance(num_equipes_por_item, dict):
        mode = "MANUAL_ALLOCATION"
        validacoes.append(ValidacaoItem(codigo="VAL-CRON-MODE", status="OK", mensagem="Modo MANUAL."))
        distribuicao_por_item = _execute_manual_mode(
            canonical_in,
            num_equipes_por_item,
            semanas_obra,
            cpu_lookup,
            producao_lookup,
            regime,
            prat_semanal,
            prat_mensal,
            fator_calendario_semanal,
            catalogo,
            validacoes,
        )
        return mode, distribuicao_por_item, [], None, False, []

    elif _can_extract_dag(canonical_in):
        mode = "AUTO_SCHEDULE"
        validacoes.append(ValidacaoItem(codigo="VAL-CRON-MODE", status="OK", mensagem="Modo AUTO."))
        # ADR-072: pass lookups for productive-duration derivation
        schedule_candidates, schedule_selected, replenishable_resources = _run_auto_schedule_fallback_chain(
            canonical_in, inputs, validacoes, cpu_lookup, producao_lookup, insumos_lookup
        )
        if not schedule_selected:
            return mode, {}, schedule_candidates, None, True, []
        distribuicao_por_item = _convert_schedule_to_distribuicao(
            schedule_selected,
            canonical_in,
            semanas_obra,
            cpu_lookup,
            producao_lookup,
            regime,
            prat_semanal,
            prat_mensal,
            fator_calendario_semanal,
            validacoes,
        )
        return mode, distribuicao_por_item, schedule_candidates, schedule_selected, False, replenishable_resources

    else:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-CRON-MODE",
                status="ERRO",
                mensagem="Nenhum modo detectado: forneca 'num_equipes_por_item' ou DAG + recursos.",
            )
        )
        return None, {}, [], None, True, []


def _build_assigned_resources_lookup(schedule_selected: ScheduleCandidateCanonical | None) -> dict[str, dict]:
    """Constrói o lookup activity_id → assigned_resources a partir do scheduler.

    In AUTO mode, schedule_selected is a ScheduleCandidateCanonical whose
    scheduled_activities carry the RCPSP resource assignments.  In MANUAL mode
    schedule_selected is None (or has no activities), so assigned_resources stays
    empty — which is correct, as manual allocation doesn't model RCPSP resources.
    """
    assigned_lookup: dict[str, dict] = {}
    if schedule_selected is not None:
        for sa in getattr(schedule_selected, "scheduled_activities", []):
            ar = getattr(sa, "assigned_resources", None)
            if ar:
                assigned_lookup[sa.activity_id] = dict(ar)
    return assigned_lookup


def _build_duration_and_ramp_lookup(
    schedule_selected: ScheduleCandidateCanonical | None,
) -> tuple[dict[str, int], dict[str, list[float] | None]]:
    """Constrói os mapas item_id → duration_weeks/ramp_profile do schedule_selected (ADR-072).

    activity_id do scheduler tem formato "item_id-atv-1", need to extract item_id.
    """
    duration_lookup: dict[str, int] = {}
    ramp_lookup: dict[str, list[float] | None] = {}
    if schedule_selected is not None and getattr(schedule_selected, "scheduled_activities", None):
        for sa in schedule_selected.scheduled_activities:
            activity_id = getattr(sa, "activity_id", None)
            duration = getattr(sa, "duration_weeks", None)
            if activity_id and duration:
                if "-atv-" in activity_id:
                    item_id = activity_id.rsplit("-atv-", 1)[0]
                else:
                    item_id = activity_id
                duration_lookup[item_id] = duration
                ramp_lookup[item_id] = getattr(sa, "ramp_profile", None)
    return duration_lookup, ramp_lookup


def _build_scheduled_activity_for_item(
    item: Any,
    distribuicao_por_item: dict,
    semanas_obra: list,
    canonical_in: CanonicalModel,
    assigned_lookup: dict[str, dict],
    duration_lookup: dict[str, int],
    ramp_lookup: dict[str, list[float] | None],
) -> Any:
    """Constrói o ScheduledActivityCanonical de um item da EAP a partir da distribuição semanal."""

    distribuicao_semanal = distribuicao_por_item.get(item.item_id, {})
    semanas_com_producao = [s for s, d in distribuicao_semanal.items() if d.qtd_executada > 0]
    _di = canonical_in.projeto.data_inicio
    start_week = _week_offset(semanas_com_producao[0], semanas_obra, _di) if semanas_com_producao else 0
    end_week = _week_offset(semanas_com_producao[-1], semanas_obra, _di) if semanas_com_producao else 0
    data_inicio = canonical_in.projeto.data_inicio + timedelta(weeks=start_week)
    data_fim = canonical_in.projeto.data_inicio + timedelta(weeks=end_week + 1)

    # ADR-072: Use original duration from scheduler if available
    duration_from_scheduler = duration_lookup.get(item.item_id, None)
    if duration_from_scheduler is not None:
        duration_weeks = duration_from_scheduler
    else:
        # Fallback: calculate from scheduled weeks if no scheduler duration
        duration_weeks = max(1, end_week - start_week + 1)

    return ScheduledActivityCanonical(
        activity_id=item.item_id,
        start_week=start_week,
        end_week=end_week,
        duration_weeks=duration_weeks,
        data_inicio=data_inicio,
        data_fim=data_fim,
        distribuicao_semanal=distribuicao_semanal,
        assigned_resources=assigned_lookup.get(item.item_id, {}),
        ramp_profile=ramp_lookup.get(item.item_id),
    )


def _build_scheduled_activities(
    canonical_in: CanonicalModel,
    distribuicao_por_item: dict,
    semanas_obra: list,
    schedule_selected: ScheduleCandidateCanonical | None = None,
) -> list:
    # Build lookup: activity_id → assigned_resources from the scheduler output.
    assigned_lookup = _build_assigned_resources_lookup(schedule_selected)

    # ADR-072: Preservar duração original do scheduler em vez de recalcular
    duration_lookup, ramp_lookup = _build_duration_and_ramp_lookup(schedule_selected)

    scheduled_activities_out = [
        _build_scheduled_activity_for_item(
            item, distribuicao_por_item, semanas_obra, canonical_in, assigned_lookup, duration_lookup, ramp_lookup
        )
        for item in canonical_in.eap
    ]
    return scheduled_activities_out


def _resolve_cronograma_algorithm(
    mode: str | None, heuristic: str | None
) -> Literal["manual_allocation", "MINSLK", "LPT", "MAXRES", "ES", "GR", "MILP", "CP-SAT", "LNS"]:
    """Resolve o algoritmo do Cronograma a partir do modo e da heurística selecionada."""
    if mode == "MANUAL_ALLOCATION":
        return "manual_allocation"
    match heuristic:
        case "MINSLK":
            return "MINSLK"
        case "LPT":
            return "LPT"
        case "MAXRES":
            return "MAXRES"
        case "ES":
            return "ES"
        case "GR":
            return "GR"
        case "CP-SAT":
            return "CP-SAT"
        case "LNS":
            return "LNS"
        case _:
            return "MINSLK"


def _build_cronograma_out(
    mode: str | None,
    schedule_selected: ScheduleCandidateCanonical | None,
    scheduled_activities_out: list,
    semanas_obra: list,
    distribuicao_mensal: dict,
    validacoes: list,
) -> Cronograma:
    heuristic = schedule_selected.heuristic if schedule_selected is not None else None
    _algo = _resolve_cronograma_algorithm(mode, heuristic)

    return Cronograma(
        algorithm=_algo,
        quality_score=schedule_selected.quality_score if schedule_selected is not None else 0.0,
        makespan_weeks=schedule_selected.makespan if schedule_selected is not None else len(semanas_obra),
        is_feasible=not any(v.status == "ERRO" for v in validacoes),
        was_relaxed=schedule_selected.relaxed if schedule_selected is not None else False,
        scheduled_activities=scheduled_activities_out,
        distribuicao_mensal=distribuicao_mensal,
        pct_completude=1.0,
        estoque_delays=getattr(schedule_selected, "estoque_delays", None) or [],
    )


def _build_intervalos_and_campanhas(
    canonical_in: CanonicalModel,
    cronograma_out: Cronograma,
    scheduled_activities_out: list,
    validacoes: list,
) -> tuple[list, object]:
    intervalos = []
    for sa in scheduled_activities_out:
        intervalos.extend(AtividadeIntervalo.from_scheduled_activity(sa))

    analise_campanhas = None
    try:
        from concilium.domain.services.campaign.campanha_equipamento_builder import CampanhaEquipamentoBuilder

        _temp = canonical_in.model_copy(update={"cronograma": cronograma_out})
        analise_campanhas = CampanhaEquipamentoBuilder().build(_temp)
        if analise_campanhas.alertas_custo_duplicado:
            for alert in analise_campanhas.alertas_custo_duplicado:
                validacoes.append(ValidacaoItem(codigo="VAL-CAMP-01", status="AVISO", mensagem=alert))
    except Exception as _camp_exc:
        import logging as _camp_log

        _camp_log.getLogger(__name__).warning("CampanhaEquipamento falhou (best-effort): %s", _camp_exc)

    return intervalos, analise_campanhas


def _expand_mobilizacao_policies(
    canonical_in: CanonicalModel,
    policies: dict[str, dict],
    existing_allocation: dict[str, dict[str, int]] | None,
    semanas_obra: list[str],
    cpu_lookup: dict[str, dict],
    producao_lookup: dict[str, dict],
    regime: Any,
    prat_semanal: dict[str, float],
    validacoes: list[ValidacaoItem],
) -> tuple[dict[str, dict[str, int]], list]:
    """ADR-054 Phase 3: Convert WMP policies into per-week team allocations for MANUAL mode."""
    from concilium.domain.services.planning.mobilizacao_simulator import WorkforcePolicySimulator

    result: dict[str, dict[str, int]] = dict(existing_allocation or {})
    curves: list = []
    semanas_set = set(semanas_obra)
    eap_lookup = {item.item_id: item for item in (canonical_in.eap or [])}
    pool = {r.tipo_id: r.quantidade_total for r in (canonical_in.recurso_pool or [])}
    sim = WorkforcePolicySimulator()

    merged_policies: dict[str, dict] = dict(policies)
    for atividade in canonical_in.atividades or []:
        if atividade.mobilizacao_policy is not None:
            merged_policies[atividade.eap_item_id] = atividade.mobilizacao_policy.model_dump()

    for item_id, policy_dict in merged_policies.items():
        _process_single_wmp_policy(
            item_id,
            policy_dict,
            eap_lookup,
            cpu_lookup,
            producao_lookup,
            pool,
            sim,
            regime,
            prat_semanal,
            semanas_obra,
            semanas_set,
            result,
            curves,
            validacoes,
        )

    return result, curves


def _run_cronograma_build_context(
    canonical_in: CanonicalModel, inputs: dict[str, Any], catalogo: dict[str, Any], validacoes: list[ValidacaoItem]
) -> tuple[Any, list, dict, dict, dict, dict, list]:
    """Monta lookups/regime/calendário e enriquece producao_lookup com P_canonico
    (NEP-029 D2). Retorna (regime, semanas_obra, cpu_lookup, producao_lookup,
    insumos_lookup, fator_calendario_semanal, calendario_operacional).

    ADR-128 F5: insumos_lookup (já construído aqui para _enrich_producao_canonico)
    passa a ser retornado também para uso em _build_replenishable_resources_if_any.
    """
    regime = canonical_in.projeto.regime_trabalho
    semanas_obra = _semanas_entre(canonical_in.projeto.data_inicio, canonical_in.projeto.data_termino)
    cpu_lookup = _build_cpu_lookup(catalogo)
    producao_lookup = _build_producao_lookup(catalogo)

    # NEP-029 D2: enriquece producao_lookup com P_canonico = custo_hora/PU_sbdi.
    # IMPORTANTE: P_canonico fica em 'valor_horario_canonico' mas NÃO substitui
    # 'valor_horario' para o scheduling (_resolve_productivity não o consome).
    # Finalidade: indicador diagnóstico de calibração — fe_nec_ajustado via PE builder.
    # Atualização de catálogo é passo manual explícito, não automático de runtime.
    insumos_lookup = _build_insumos_lookup(catalogo)
    horas_mes = regime.horas_dia * regime.dias_semana * 4.345  # semanas/mês
    taxa_encargos = float(inputs.get("taxa_encargos_mo", 1.0))  # default 100% encargos

    # Restringir validação de P_canonico apenas às CPUs do EAP deste projeto,
    # evitando avisos espúrios de CPUs do catálogo não usadas aqui.
    eap_cpu_ids = {item.cpu_id for item in (canonical_in.eap or []) if getattr(item, "cpu_id", None)}
    eap_cpu_lookup = {k: v for k, v in cpu_lookup.items() if k in eap_cpu_ids} if eap_cpu_ids else cpu_lookup
    _enrich_producao_canonico(eap_cpu_lookup, producao_lookup, insumos_lookup, horas_mes, taxa_encargos, validacoes)

    calendario_config = (
        inputs.get("calendario_operacional") if isinstance(inputs.get("calendario_operacional"), dict) else {}
    )
    fator_calendario_semanal, calendario_operacional = _build_fator_calendario_semanal(
        semanas_obra,
        canonical_in.projeto.data_inicio,
        regime.dias_semana,
        calendario_config,
    )
    return (
        regime,
        semanas_obra,
        cpu_lookup,
        producao_lookup,
        insumos_lookup,
        fator_calendario_semanal,
        calendario_operacional,
    )


def _run_cronograma_validate_num_equipes_formato(num_equipes_por_item: Any, validacoes: list[ValidacaoItem]) -> bool:
    """Valida que num_equipes_por_item é dict[item_id, dict[semana_iso, int]].
    Retorna False (e registra VAL-CRON-EQUIPES-FORMATO) se algum valor for plano."""
    if num_equipes_por_item is None or not isinstance(num_equipes_por_item, dict):
        return True
    flat_items = [k for k, v in num_equipes_por_item.items() if not isinstance(v, dict)]
    if not flat_items:
        return True
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-CRON-EQUIPES-FORMATO",
            status="ERRO",
            mensagem=(
                f"num_equipes_por_item: valor deve ser dict[semana_iso, int], não int. "
                f"Itens com formato errado: {flat_items[:3]}. "
                f'Esperado: {{"item_id": {{"2025-W01": 2, "2025-W02": 3}}}}'
            ),
        )
    )
    return False


def _run_cronograma_infer_mob_schedule(canonical_in: CanonicalModel, validacoes: list[ValidacaoItem]) -> Any:
    """ADR-105: infere janelas de mobilização automaticamente a partir do EAP.
    Retorna None (e registra VAL-MOB-SCHEDULE-ERRO) em caso de falha."""
    try:
        meta_dict = {
            "data_inicio": canonical_in.projeto.data_inicio.isoformat(),
            "data_termino": canonical_in.projeto.data_termino.isoformat(),
        }
        eap_list = [
            {
                "item_id": item.item_id,
                "predecessores": [{"item_id": p.item_id} for p in item.predecessores_tipados()],
            }
            for item in canonical_in.eap
        ]
        mob_schedule = infer_mob_windows(meta_dict, eap_list)
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-MOB-SCHEDULE-OK",
                status="OK",
                mensagem="Janelas de mobilização inferidas com sucesso.",
            )
        )
        return mob_schedule
    except Exception as e:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-MOB-SCHEDULE-ERRO",
                status="AVISO",
                mensagem=f"Falha ao inferir janelas de mobilização: {str(e)}",
            )
        )
        return None


__all__ = [
    "_build_assigned_resources_lookup",
    "_build_cronograma_out",
    "_build_duration_and_ramp_lookup",
    "_build_intervalos_and_campanhas",
    "_build_scheduled_activities",
    "_build_scheduled_activity_for_item",
    "_determine_mode_and_distribuicao",
    "_expand_mobilizacao_policies",
    "_extract_praticabilidade",
    "_resolve_cronograma_algorithm",
    "_run_cronograma_build_context",
    "_run_cronograma_infer_mob_schedule",
    "_run_cronograma_validate_num_equipes_formato",
]
