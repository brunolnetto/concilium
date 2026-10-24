"""Skill 04 — Cronograma Unificado (Semanal com Agregação Mensal).

Dual-mode scheduling:
  Mode 1: MANUAL_ALLOCATION — Planejador fornece num_equipes_por_item
          Usa lógica Skill 04 (cálculo de produção)

  Mode 2: AUTO_SCHEDULE — Otimização automática (DAG + recursos + prazo)
          Fallback chain: heurísticas -> relax -> MILP

Saída unificada: Cronograma com scheduled_activities (semanal) + distribuicao_mensal (mensal)

DEPRECATION NOTICE (ADR-105):
  spec.rcpsp_spec is deprecated in favor of automatic MOB window inference.
  Use infer_mob_windows() with meta.data_inicio/termino + spec.eap.predecessores.
  Target removal: v4.0. Migration guide: docs/engineering/ADR-105-migration.md
"""

from __future__ import annotations

import math
from typing import Any

from concilium.application.skills.base import SkillResult
from concilium.domain.models.canonical import CanonicalModel, ValidacaoItem

from ._skill_helpers import _assembly as _mod_assembly  # ty: ignore[unresolved-import]  # noqa: F401 — test compat
from ._skill_helpers import _calendario as _mod_calendario  # ty: ignore[unresolved-import]
from ._skill_helpers import _custos as _mod_custos  # ty: ignore[unresolved-import]
from ._skill_helpers import _scheduling as _mod_scheduling  # ty: ignore[unresolved-import]
from ._skill_helpers import _spec as _mod_spec  # ty: ignore[unresolved-import]
from ._skill_helpers import _validacao as _mod_validacao  # ty: ignore[unresolved-import]
from ._skill_helpers._assembly import (  # ty: ignore[unresolved-import]
    _build_cronograma_out,
    _build_intervalos_and_campanhas,
    _build_scheduled_activities,
    _determine_mode_and_distribuicao,
    _expand_mobilizacao_policies,
    _extract_praticabilidade,
    _run_cronograma_build_context,
    _run_cronograma_infer_mob_schedule,
    _run_cronograma_validate_num_equipes_formato,
)
from ._skill_helpers._estoque_consumivel import (  # ty: ignore[unresolved-import]
    build_estoque_consumivel_canonical,
)
from ._skill_helpers._scheduling import (  # ty: ignore[unresolved-import]
    _check_pool_violations,
)
from ._skill_helpers._validacao import (  # ty: ignore[unresolved-import]
    _aggregate_to_monthly,
    _validate_preconditions,
)

# Re-exports abaixo são consumidos apenas por testes de cobertura que acessam
# funções internas dos helpers via este módulo (não usadas por run_cronograma).
_build_fator_calendario_semanal = _mod_calendario._build_fator_calendario_semanal
_compute_productive_weeks = _mod_calendario._compute_productive_weeks
_compute_ramp_profile = _mod_calendario._compute_ramp_profile
_event_occurs_on_day = _mod_calendario._event_occurs_on_day
_extract_activities = _mod_calendario._extract_activities
_extract_dag = _mod_calendario._extract_dag
_extract_edge_thresholds_from_eap = _mod_calendario._extract_edge_thresholds_from_eap
_mean_praticabilidade = _mod_calendario._mean_praticabilidade
_resolve_productivity = _mod_calendario._resolve_productivity
_week_to_month = _mod_calendario._week_to_month
_build_cpu_lookup = _mod_custos._build_cpu_lookup
_build_dist_cell = _mod_custos._build_dist_cell
_build_insumos_lookup = _mod_custos._build_insumos_lookup
_build_producao_lookup = _mod_custos._build_producao_lookup
_custo_hora_equipe = _mod_custos._custo_hora_equipe
_enrich_producao_canonico = _mod_custos._enrich_producao_canonico
_iso_week_key = _mod_custos._iso_week_key
_lookup_eficiencia = _mod_custos._lookup_eficiencia
_semanas_entre = _mod_custos._semanas_entre
_week_offset = _mod_custos._week_offset
_check_wmp_desmob = _mod_scheduling._check_wmp_desmob
_check_wmp_pool = _mod_scheduling._check_wmp_pool
_convert_schedule_to_distribuicao = _mod_scheduling._convert_schedule_to_distribuicao
_cpv_build_usage = _mod_scheduling._cpv_build_usage
_cpv_process_violations = _mod_scheduling._cpv_process_violations
_process_single_wmp_policy = _mod_scheduling._process_single_wmp_policy
_run_auto_schedule_fallback_chain = _mod_scheduling._run_auto_schedule_fallback_chain
_enrich_spec_resources_from_catalog = _mod_spec._enrich_spec_resources_from_catalog
_extract_activities_from_spec = _mod_spec._extract_activities_from_spec
_extract_pool_from_spec = _mod_spec._extract_pool_from_spec
_find_item_by_id = _mod_validacao._find_item_by_id
_infer_teams_from_resources = _mod_validacao._infer_teams_from_resources
_rasfc_extract_inputs = _mod_validacao._rasfc_extract_inputs
_rasfc_run_heuristics = _mod_validacao._rasfc_run_heuristics



def _invalidate_derived_costs() -> dict[str, Any]:
    """Clear stale economic outputs whenever Skill04 cannot certify provenance."""
    return {
        "resultado": None,
        "resultado_reconciliado": None,
        "ponto_equilibrio": [],
        "custos_atividades": [],
        "diagnostico_pe": None,
        "backtracking_pe": None,
        "memorial_calculo_bdi": None,
        "tabela_bdi_efetiva": None,
        "contratos_recurso": [],
        "cadeias_perpetuacao": [],
        "instancias_recurso": [],
        "resumo_utilizacao_contratos": [],
        "recursos_consumiveis": [],
        "resumo_estoque_consumiveis": [],
        "indiretos_semanal": [],
        "indiretos_com_bdi": [],
        "bridge_analysis": None,
        "cost_criticality_report": None,
        "criticality_report": None,
        "replan_suggestions": None,
        "plan_space_result": None,
        "cpu_exposure_perfis": [],
        "relatorio_criticidade": None,
        "relatorio_sensibilidade": None,
        "relatorio_intervencao": None,
        "curva_abc_insumo": None,
        "s_curve": None,
        "cubo_analitico": None,
    }


def _preflight_physical_productivity(
    canonical: CanonicalModel,
    cpu_lookup: dict,
    producao_lookup: dict,
    *,
    certified: bool,
    validacoes: list[ValidacaoItem],
) -> tuple[bool, bool]:
    """Validate real physical source and numeric rate before calling a solver.

    An identifier/field spelling is NOT a calibration. In the absence of
    graph + versioned external source, a rate is an exploratory assumption.
    The downstream project-wide GO certificate remains outside Skill04.
    """
    invalid = False
    unverified = False
    for item in canonical.eap or []:
        cpu = cpu_lookup.get(item.cpu_id) or {}
        meta = cpu.get("cpu_meta") or {}
        if not isinstance(meta, dict):
            meta = {}
        prod_id = cpu.get("producao_id_ref")
        prod = producao_lookup.get(prod_id) if prod_id else None
        if not isinstance(prod, dict):
            prod = {}
        for name, raw in (
            ("cpu_meta.producao_horaria", meta.get("producao_horaria")),
            ("producao_horaria", prod.get("producao_horaria")),
            ("valor_horario", prod.get("valor_horario")),
        ):
            if raw is not None and (
                isinstance(raw, bool)
                or not isinstance(raw, (int, float))
                or not math.isfinite(float(raw))
                or float(raw) <= 0
            ):
                invalid = True
                validacoes.append(
                    ValidacaoItem(
                        codigo="VAL-CRON-PROD-INVALID",
                        status="ERRO",
                        mensagem=f"F(m) inválido em {item.item_id}/{name}; exigir taxa física positiva e finita.",
                    )
                )
        # Independently inspect the *chosen* source, not merely the names of
        # the warnings emitted by the legacy productivity resolver.
        has_graph = isinstance(prod.get("grafo_sinergia"), dict) and bool(prod["grafo_sinergia"])
        source_info = prod.get("origem")
        audit_info = prod.get("auditoria")
        source_info = source_info if isinstance(source_info, dict) else {}
        audit_info = audit_info if isinstance(audit_info, dict) else {}
        origin = source_info.get("fonte_id") or prod.get("source_id") or prod.get("fonte")
        version = audit_info.get("versao") or prod.get("source_version") or prod.get("versao")
        # The versioned Producao contract stores these under origem/auditoria;
        # producao_horaria can be the derived output of a physical graph.
        # cpu_meta.producao_horaria overrides the graph and is not proof.
        source_proved = (
            bool(prod_id) and has_graph and isinstance(origin, str)
            and bool(origin.strip()) and isinstance(version, str)
            and bool(version.strip()) and "producao_horaria" not in meta
        )
        if not source_proved:
            unverified = True
            if certified:
                validacoes.append(
                    ValidacaoItem(
                        codigo="VAL-CRON-PROD-CERT",
                        status="ERRO",
                        mensagem=(
                            f"NOGO: {item.item_id} sem grafo F(m), versão/fonte física "
                            "documentada ou com taxa legada que substitui o grafo."
                        ),
                    )
                )
    return invalid, unverified



def run_cronograma(
    canonical_in: CanonicalModel,
    inputs: dict[str, Any],
    catalogo: dict[str, Any] | None = None,
    **_kwargs: Any,
) -> SkillResult:
    """Gera cronograma semanal unificado com agregacao mensal. Modo: manual ou automatico."""
    validacoes: list[ValidacaoItem] = []
    catalogo = catalogo or {}

    # P14-C: source-backed physical throughput is required to request certification.
    # The current full-pipeline GO authority remains a separate downstream gate.
    certification_intent = inputs.get("certification_intent", "PREVIEW")
    if certification_intent not in ("PREVIEW", "CERTIFIED"):
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-CRON-CERT-INTENT",
                status="ERRO",
                mensagem="certification_intent deve ser PREVIEW ou CERTIFIED; sem inferência de GO.",
            )
        )
        return SkillResult(canonical_in, validacoes)

    if not _validate_preconditions(canonical_in, validacoes):
        return SkillResult(canonical_in, validacoes)

    (
        regime,
        semanas_obra,
        cpu_lookup,
        producao_lookup,
        insumos_lookup,
        fator_calendario_semanal,
        calendario_operacional,
    ) = _run_cronograma_build_context(canonical_in, inputs, catalogo, validacoes)
    prat_semanal, prat_mensal = _extract_praticabilidade(canonical_in)

    invalid_productivity, unverified_productivity = _preflight_physical_productivity(
        canonical_in, cpu_lookup, producao_lookup,
        certified=certification_intent == "CERTIFIED",
        validacoes=validacoes,
    )
    if invalid_productivity or (certification_intent == "CERTIFIED" and unverified_productivity):
        return SkillResult(
            canonical_in.model_copy(
                update={"cronograma": None, "intervalos_atividade": [],
                        **_invalidate_derived_costs()}
            ),
            validacoes,
        )

    num_equipes_por_item = inputs.get("num_equipes_por_item")
    if not _run_cronograma_validate_num_equipes_formato(num_equipes_por_item, validacoes):
        return SkillResult(canonical_in, validacoes)

    wmp_curves: list = []
    mobilizacao_policies = inputs.get("mobilizacao_policies")
    if mobilizacao_policies and isinstance(mobilizacao_policies, dict):
        num_equipes_por_item, wmp_curves = _expand_mobilizacao_policies(
            canonical_in,
            mobilizacao_policies,
            num_equipes_por_item,
            semanas_obra,
            cpu_lookup,
            producao_lookup,
            regime,
            prat_semanal,
            validacoes,
            calendario_semanal=fator_calendario_semanal,
        )

    (
        mode,
        distribuicao_por_item,
        schedule_candidates,
        schedule_selected,
        failed,
        replenishable_resources,
        fallback_item_ids,
    ) = _determine_mode_and_distribuicao(
        canonical_in,
        inputs,
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
        insumos_lookup,
    )
    missing_productivity_evidence = unverified_productivity or bool(fallback_item_ids) or any(
        v.codigo in ("VAL-PROD-04", "VAL-PROD-04-PROD-LEGACY")
        for v in validacoes
    )
    if certification_intent == "CERTIFIED" and missing_productivity_evidence:
        # A historical P=1000 u/h placeholder must never become certified F(m).
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-CRON-PROD-CERT",
                status="ERRO",
                mensagem=(
                    "NOGO: produtividade física sem origem validada. "
                    "P=1000 e campos legados são apenas PREVIEW; "
                    f"itens afetados={sorted(fallback_item_ids)}."
                ),
            )
        )
        blocked = canonical_in.model_copy(
            update={"cronograma": None, "intervalos_atividade": [],
                    **_invalidate_derived_costs()}
        )
        return SkillResult(blocked, validacoes)
    if failed:
        return SkillResult(canonical_in, validacoes)

    # P14-B: never publish an authoritative schedule whose calendar/physical
    # predecessors failed. SkillResult.has_errors alone cannot protect consumers
    # if a partial cronograma is still included in the canonical output.
    blocking_codes = {"VAL-CRON-01", "VAL-CRON-PRECEDENCIA"}
    if any(v.status == "ERRO" and v.codigo in blocking_codes for v in validacoes):
        return SkillResult(canonical_in, validacoes)

    pool_violations = _check_pool_violations(canonical_in, distribuicao_por_item, cpu_lookup, validacoes)
    if pool_violations:
        # P15: shifting/extending physical activities after the nominal solver
        # can overbook a resource. An ERRO diagnostic alone is insufficient if
        # the stale/invalid schedule and its economic artifacts are published.
        # Never substitute zero cost or an optimistic GO for unavailable pool.
        blocked = canonical_in.model_copy(
            update={
                "cronograma": None,
                "intervalos_atividade": [],
                "resultado": None,
                "ponto_equilibrio": [],
                "custos_atividades": [],
                # These are *derived* from the rejected schedule, not exogenous
                # calendar/practicability or physical resource definitions.
                # Never publish previous inventory/costs as if they were
                # outcomes of a physically impossible new allocation.
                "recursos_consumiveis": [],
                "resumo_estoque_consumiveis": [],
                "curvas_forca": [],
                "analise_campanhas": None,
                "contratos_recurso": [],
                "cadeias_perpetuacao": [],
                "instancias_recurso": [],
                "resumo_utilizacao_contratos": [],
                "indiretos_semanal": [],
                "indiretos_com_bdi": [],
                "resultado_reconciliado": None,
                "memorial_calculo_bdi": None,
                "tabela_bdi_efetiva": None,
                "diagnostico_pe": None,
                "backtracking_pe": None,
                "bridge_analysis": None,
                "criticality_report": None,
                "cost_criticality_report": None,
                "replan_suggestions": None,
                "plan_space_result": None,
                "cpu_exposure_perfis": [],
                "relatorio_criticidade": None,
                "relatorio_sensibilidade": None,
                "relatorio_intervencao": None,
                "s_curve": None,
                "cubo_analitico": None,
                "curva_abc_insumo": None,
                "constraint_violations": [
                    *(canonical_in.constraint_violations or []),
                    *pool_violations,
                ],
            }
        )
        return SkillResult(blocked, validacoes)

    scheduled_activities_out = _build_scheduled_activities(
        canonical_in, distribuicao_por_item, semanas_obra, schedule_selected, fallback_item_ids
    )
    distribuicao_mensal = _aggregate_to_monthly(distribuicao_por_item)
    cronograma_out = _build_cronograma_out(
        mode, schedule_selected, scheduled_activities_out, semanas_obra, distribuicao_mensal, validacoes
    )
    if missing_productivity_evidence:
        # Physical feasibility and certification are orthogonal: a schedule
        # may satisfy all physical constraints yet lack audited F(m) inputs.
        # Report uncertified status separately, without falsifying the solver.
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-CRON-PROD-PREVIEW",
                status="AVISO",
                mensagem="Cronograma exploratório: produtividade não comprovada; NOT_PROJECT_GO.",
            )
        )
    intervalos, analise_campanhas = _build_intervalos_and_campanhas(
        canonical_in, cronograma_out, scheduled_activities_out, validacoes
    )

    mob_schedule = _run_cronograma_infer_mob_schedule(canonical_in, validacoes)

    # ADR-128 F6: contabilização canônica de consumíveis (paridade com pool) — opt-in,
    # vazio quando nenhum ReplenishableResource foi construído/aplicado.
    recursos_consumiveis_out, resumo_estoque_out = build_estoque_consumivel_canonical(
        replenishable_resources, cronograma_out.scheduled_activities, cronograma_out.estoque_delays
    )

    update_dict = {
        "cronograma": cronograma_out,
        "intervalos_atividade": intervalos,
        "fator_calendario_semanal": fator_calendario_semanal,
        "calendario_operacional": calendario_operacional,
        "constraint_violations": pool_violations if pool_violations else canonical_in.constraint_violations,
        "curvas_forca": wmp_curves if wmp_curves else canonical_in.curvas_forca,
        "analise_campanhas": analise_campanhas,
        "recursos_consumiveis": recursos_consumiveis_out,
        "resumo_estoque_consumiveis": resumo_estoque_out,
    }
    if missing_productivity_evidence:
        # Keep newly calculated physical consumables/stock even in preview.
        # They are exploratory artifacts, not a certified financial ledger.
        stale_financials = _invalidate_derived_costs()
        stale_financials.pop("recursos_consumiveis")
        stale_financials.pop("resumo_estoque_consumiveis")
        update_dict.update(stale_financials)
    if mob_schedule:
        update_dict["mob_schedule"] = mob_schedule

    updated_canonical = canonical_in.model_copy(update=update_dict)

    validacoes.append(
        ValidacaoItem(
            codigo="VAL-CRON-OK",
            status="OK",
            mensagem=(
                f"Cronograma ({mode}): {len(scheduled_activities_out)} atividades, {len(distribuicao_mensal)} meses."
            ),
        )
    )

    return SkillResult(updated_canonical, validacoes)
