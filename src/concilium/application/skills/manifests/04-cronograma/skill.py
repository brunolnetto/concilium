"""Skill 02 — Cronograma Unificado (Semanal com Agregação Mensal).

Dual-mode scheduling:
  Mode 1: MANUAL_ALLOCATION — Planejador fornece num_equipes_por_item
          Usa lógica Skill 02 (cálculo de produção)

  Mode 2: AUTO_SCHEDULE — Otimização automática (DAG + recursos + prazo)
          Fallback chain: heurísticas -> relax -> MILP

Saída unificada: Cronograma com scheduled_activities (semanal) + distribuicao_mensal (mensal)

DEPRECATION NOTICE (ADR-105):
  spec.rcpsp_spec is deprecated in favor of automatic MOB window inference.
  Use infer_mob_windows() with meta.data_inicio/termino + spec.eap.predecessores.
  Target removal: v4.0. Migration guide: docs/engineering/ADR-105-migration.md
"""

from __future__ import annotations

from typing import Any

from concilium.application.skills.base import SkillResult
from concilium.domain.models.canonical import CanonicalModel, ValidacaoItem

try:
    from . import _skill_helpers_assembly as _mod_assembly  # ty: ignore[unresolved-import]
    from . import _skill_helpers_calendario as _mod_calendario  # ty: ignore[unresolved-import]
    from . import _skill_helpers_custos as _mod_custos  # ty: ignore[unresolved-import]
    from . import _skill_helpers_scheduling as _mod_scheduling  # ty: ignore[unresolved-import]
    from . import _skill_helpers_spec as _mod_spec  # ty: ignore[unresolved-import]
    from . import _skill_helpers_validacao as _mod_validacao  # ty: ignore[unresolved-import]
    from ._skill_helpers_assembly import (  # ty: ignore[unresolved-import]  # runtime-only: loaded via importlib below
        _build_assigned_resources_lookup,
        _build_cronograma_out,
        _build_duration_and_ramp_lookup,
        _build_intervalos_and_campanhas,
        _build_scheduled_activities,
        _build_scheduled_activity_for_item,
        _determine_mode_and_distribuicao,
        _expand_mobilizacao_policies,
        _extract_praticabilidade,
        _resolve_cronograma_algorithm,
        _run_cronograma_build_context,
        _run_cronograma_infer_mob_schedule,
        _run_cronograma_validate_num_equipes_formato,
    )
    from ._skill_helpers_calendario import (  # ty: ignore[unresolved-import]  # runtime-only: loaded via importlib below
        _build_fator_calendario_semanal,
        _compute_dias_uteis_efetivos_semana,
        _compute_productive_weeks,
        _compute_ramp_profile,
        _event_occurs_on_day,
        _extract_activities,
        _extract_dag,
        _extract_edge_thresholds_from_eap,
        _extract_pool,
        _infer_linear_edge_thresholds,
        _mean_praticabilidade,
        _relax_pool,
        _resolve_productivity,
        _resolve_productivity_from_cpu_meta,
        _resolve_productivity_from_lookup,
        _warn_legacy_productivity_fields,
        _week_to_month,
        _weeks_between,
    )
    from ._skill_helpers_custos import (  # ty: ignore[unresolved-import]  # runtime-only: loaded via importlib below
        _apply_producao_canonico,
        _build_cpu_lookup,
        _build_dist_cell,
        _build_insumos_lookup,
        _build_producao_lookup,
        _custo_hora_combustivel_equip,
        _custo_hora_equipamentos,
        _custo_hora_equipe,
        _custo_hora_mao_de_obra,
        _enrich_producao_canonico,
        _iso_week_key,
        _lookup_eficiencia,
        _resolve_cpu_producao_context,
        _resolve_diesel_insumo,
        _semanas_entre,
        _week_offset,
    )
    from ._skill_helpers_scheduling import (  # ty: ignore[unresolved-import]  # runtime-only: loaded via importlib below
        _build_activity_distribuicao,
        _build_wmp_policy,
        _check_pool_violations,
        _check_wmp_desmob,
        _check_wmp_pool,
        _compute_activity_n_max,
        _convert_schedule_to_distribuicao,
        _cpv_build_usage,
        _cpv_get_equip_needed,
        _cpv_process_violations,
        _process_single_wmp_policy,
        _resolve_cpu_for_item,
        _resolve_item_for_scheduled_activity,
        _run_auto_schedule_fallback_chain,
        _run_wmp_simulation,
        _warn_if_activity_underdelivers,
    )
    from ._skill_helpers_spec import (  # ty: ignore[unresolved-import]  # runtime-only: loaded via importlib below
        _apply_activity_resource_enrichment,
        _build_activity_from_spec_entry,
        _composicao_tem_recursos,
        _dimensionar_frentes_atividade,
        _enrich_activity_resources_from_catalog,
        _enrich_spec_resources_from_catalog,
        _equipamento_tokens_composicao,
        _extract_activities_from_spec,
        _extract_dag_from_spec,
        _extract_pool_from_spec,
        _funcao_tokens_composicao,
        _resolve_horas_semana_enriquecimento,
        _resolve_producao_context_atividade,
        _resolve_producao_do_item,
        _resolve_spec_activity_productive_weeks,
        _resolve_spec_activity_ramp_profile,
        _tipo_recurso_fungivel,
        _to_canonical_candidate,
    )
    from ._skill_helpers_validacao import (  # ty: ignore[unresolved-import]  # runtime-only: loaded via importlib below
        _aggregate_to_monthly,
        _build_activity_item_map,
        _can_extract_dag,
        _emm_find_vazios,
        _emm_process_item,
        _execute_manual_mode,
        _find_item_by_id,
        _infer_teams_from_resources,
        _rasfc_enrich_from_catalog_if_available,
        _rasfc_extract_from_canonical,
        _rasfc_extract_from_spec,
        _rasfc_extract_inputs,
        _rasfc_propagate_pool_config,
        _rasfc_report_pool_inferido_diag,
        _rasfc_run_heuristics,
        _validate_preconditions,
    )
except ImportError:
    import importlib.util
    import sys
    import types
    from pathlib import Path

    _here = Path(__file__).resolve().parent

    # Os submódulos de helpers fazem imports relativos entre si (ex.:
    # _skill_helpers_assembly importa de _skill_helpers_validacao). Para que
    # essas referências resolvam quando skill.py é carregado standalone (sem
    # o pacote sintético normal via concilium.application.skills), criamos
    # aqui um pacote sintético mínimo próprio — mesma técnica de
    # `_ensure_skill_package` em application/skills/__init__.py.
    _pkg_name = "_skill04_cronograma_helpers"
    if _pkg_name not in sys.modules:
        _pkg = types.ModuleType(_pkg_name)
        _pkg.__path__ = [str(_here)]
        _pkg.__package__ = _pkg_name
        sys.modules[_pkg_name] = _pkg

    def _load_sibling(short_name: str, filename: str):
        mod_name = f"{_pkg_name}.{short_name}"
        if mod_name in sys.modules:
            return sys.modules[mod_name]
        spec = importlib.util.spec_from_file_location(mod_name, _here / filename)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load {filename} via importlib") from None
        mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)
        return mod

    _mod_custos = _load_sibling("_skill_helpers_custos", "_skill_helpers_custos.py")
    _mod_calendario = _load_sibling("_skill_helpers_calendario", "_skill_helpers_calendario.py")
    _mod_spec = _load_sibling("_skill_helpers_spec", "_skill_helpers_spec.py")
    _mod_validacao = _load_sibling("_skill_helpers_validacao", "_skill_helpers_validacao.py")
    _mod_scheduling = _load_sibling("_skill_helpers_scheduling", "_skill_helpers_scheduling.py")
    _mod_assembly = _load_sibling("_skill_helpers_assembly", "_skill_helpers_assembly.py")

    _apply_producao_canonico = _mod_custos._apply_producao_canonico
    _build_cpu_lookup = _mod_custos._build_cpu_lookup
    _build_dist_cell = _mod_custos._build_dist_cell
    _build_insumos_lookup = _mod_custos._build_insumos_lookup
    _build_producao_lookup = _mod_custos._build_producao_lookup
    _custo_hora_combustivel_equip = _mod_custos._custo_hora_combustivel_equip
    _custo_hora_equipamentos = _mod_custos._custo_hora_equipamentos
    _custo_hora_equipe = _mod_custos._custo_hora_equipe
    _custo_hora_mao_de_obra = _mod_custos._custo_hora_mao_de_obra
    _enrich_producao_canonico = _mod_custos._enrich_producao_canonico
    _iso_week_key = _mod_custos._iso_week_key
    _lookup_eficiencia = _mod_custos._lookup_eficiencia
    _resolve_cpu_producao_context = _mod_custos._resolve_cpu_producao_context
    _resolve_diesel_insumo = _mod_custos._resolve_diesel_insumo
    _semanas_entre = _mod_custos._semanas_entre
    _week_offset = _mod_custos._week_offset
    _build_fator_calendario_semanal = _mod_calendario._build_fator_calendario_semanal
    _compute_dias_uteis_efetivos_semana = _mod_calendario._compute_dias_uteis_efetivos_semana
    _compute_productive_weeks = _mod_calendario._compute_productive_weeks
    _compute_ramp_profile = _mod_calendario._compute_ramp_profile
    _event_occurs_on_day = _mod_calendario._event_occurs_on_day
    _extract_activities = _mod_calendario._extract_activities
    _extract_dag = _mod_calendario._extract_dag
    _extract_edge_thresholds_from_eap = _mod_calendario._extract_edge_thresholds_from_eap
    _extract_pool = _mod_calendario._extract_pool
    _infer_linear_edge_thresholds = _mod_calendario._infer_linear_edge_thresholds
    _mean_praticabilidade = _mod_calendario._mean_praticabilidade
    _relax_pool = _mod_calendario._relax_pool
    _resolve_productivity = _mod_calendario._resolve_productivity
    _resolve_productivity_from_cpu_meta = _mod_calendario._resolve_productivity_from_cpu_meta
    _resolve_productivity_from_lookup = _mod_calendario._resolve_productivity_from_lookup
    _warn_legacy_productivity_fields = _mod_calendario._warn_legacy_productivity_fields
    _week_to_month = _mod_calendario._week_to_month
    _weeks_between = _mod_calendario._weeks_between
    _apply_activity_resource_enrichment = _mod_spec._apply_activity_resource_enrichment
    _build_activity_from_spec_entry = _mod_spec._build_activity_from_spec_entry
    _composicao_tem_recursos = _mod_spec._composicao_tem_recursos
    _dimensionar_frentes_atividade = _mod_spec._dimensionar_frentes_atividade
    _enrich_activity_resources_from_catalog = _mod_spec._enrich_activity_resources_from_catalog
    _enrich_spec_resources_from_catalog = _mod_spec._enrich_spec_resources_from_catalog
    _equipamento_tokens_composicao = _mod_spec._equipamento_tokens_composicao
    _extract_activities_from_spec = _mod_spec._extract_activities_from_spec
    _extract_dag_from_spec = _mod_spec._extract_dag_from_spec
    _extract_pool_from_spec = _mod_spec._extract_pool_from_spec
    _funcao_tokens_composicao = _mod_spec._funcao_tokens_composicao
    _resolve_horas_semana_enriquecimento = _mod_spec._resolve_horas_semana_enriquecimento
    _resolve_producao_context_atividade = _mod_spec._resolve_producao_context_atividade
    _resolve_producao_do_item = _mod_spec._resolve_producao_do_item
    _resolve_spec_activity_productive_weeks = _mod_spec._resolve_spec_activity_productive_weeks
    _resolve_spec_activity_ramp_profile = _mod_spec._resolve_spec_activity_ramp_profile
    _tipo_recurso_fungivel = _mod_spec._tipo_recurso_fungivel
    _to_canonical_candidate = _mod_spec._to_canonical_candidate
    _aggregate_to_monthly = _mod_validacao._aggregate_to_monthly
    _build_activity_item_map = _mod_validacao._build_activity_item_map
    _can_extract_dag = _mod_validacao._can_extract_dag
    _emm_find_vazios = _mod_validacao._emm_find_vazios
    _emm_process_item = _mod_validacao._emm_process_item
    _execute_manual_mode = _mod_validacao._execute_manual_mode
    _find_item_by_id = _mod_validacao._find_item_by_id
    _infer_teams_from_resources = _mod_validacao._infer_teams_from_resources
    _rasfc_enrich_from_catalog_if_available = _mod_validacao._rasfc_enrich_from_catalog_if_available
    _rasfc_extract_from_canonical = _mod_validacao._rasfc_extract_from_canonical
    _rasfc_extract_from_spec = _mod_validacao._rasfc_extract_from_spec
    _rasfc_extract_inputs = _mod_validacao._rasfc_extract_inputs
    _rasfc_propagate_pool_config = _mod_validacao._rasfc_propagate_pool_config
    _rasfc_report_pool_inferido_diag = _mod_validacao._rasfc_report_pool_inferido_diag
    _rasfc_run_heuristics = _mod_validacao._rasfc_run_heuristics
    _validate_preconditions = _mod_validacao._validate_preconditions
    _build_activity_distribuicao = _mod_scheduling._build_activity_distribuicao
    _build_wmp_policy = _mod_scheduling._build_wmp_policy
    _check_pool_violations = _mod_scheduling._check_pool_violations
    _check_wmp_desmob = _mod_scheduling._check_wmp_desmob
    _check_wmp_pool = _mod_scheduling._check_wmp_pool
    _compute_activity_n_max = _mod_scheduling._compute_activity_n_max
    _convert_schedule_to_distribuicao = _mod_scheduling._convert_schedule_to_distribuicao
    _cpv_build_usage = _mod_scheduling._cpv_build_usage
    _cpv_get_equip_needed = _mod_scheduling._cpv_get_equip_needed
    _cpv_process_violations = _mod_scheduling._cpv_process_violations
    _process_single_wmp_policy = _mod_scheduling._process_single_wmp_policy
    _resolve_cpu_for_item = _mod_scheduling._resolve_cpu_for_item
    _resolve_item_for_scheduled_activity = _mod_scheduling._resolve_item_for_scheduled_activity
    _run_auto_schedule_fallback_chain = _mod_scheduling._run_auto_schedule_fallback_chain
    _run_wmp_simulation = _mod_scheduling._run_wmp_simulation
    _warn_if_activity_underdelivers = _mod_scheduling._warn_if_activity_underdelivers
    _build_assigned_resources_lookup = _mod_assembly._build_assigned_resources_lookup
    _build_cronograma_out = _mod_assembly._build_cronograma_out
    _build_duration_and_ramp_lookup = _mod_assembly._build_duration_and_ramp_lookup
    _build_intervalos_and_campanhas = _mod_assembly._build_intervalos_and_campanhas
    _build_scheduled_activities = _mod_assembly._build_scheduled_activities
    _build_scheduled_activity_for_item = _mod_assembly._build_scheduled_activity_for_item
    _determine_mode_and_distribuicao = _mod_assembly._determine_mode_and_distribuicao
    _expand_mobilizacao_policies = _mod_assembly._expand_mobilizacao_policies
    _extract_praticabilidade = _mod_assembly._extract_praticabilidade
    _resolve_cronograma_algorithm = _mod_assembly._resolve_cronograma_algorithm
    _run_cronograma_build_context = _mod_assembly._run_cronograma_build_context
    _run_cronograma_infer_mob_schedule = _mod_assembly._run_cronograma_infer_mob_schedule
    _run_cronograma_validate_num_equipes_formato = _mod_assembly._run_cronograma_validate_num_equipes_formato


def run_cronograma(
    canonical_in: CanonicalModel,
    inputs: dict[str, Any],
    catalogo: dict[str, Any] | None = None,
    **_kwargs: Any,
) -> SkillResult:
    """Gera cronograma semanal unificado com agregacao mensal. Modo: manual ou automatico."""
    validacoes: list[ValidacaoItem] = []
    catalogo = catalogo or {}

    if not _validate_preconditions(canonical_in, validacoes):
        return SkillResult(canonical_in, validacoes)

    regime, semanas_obra, cpu_lookup, producao_lookup, fator_calendario_semanal, calendario_operacional = (
        _run_cronograma_build_context(canonical_in, inputs, catalogo, validacoes)
    )
    prat_semanal, prat_mensal = _extract_praticabilidade(canonical_in)

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
        )

    mode, distribuicao_por_item, schedule_candidates, schedule_selected, failed = _determine_mode_and_distribuicao(
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
    )
    if failed:
        return SkillResult(canonical_in, validacoes)

    pool_violations = _check_pool_violations(canonical_in, distribuicao_por_item, cpu_lookup, validacoes)
    scheduled_activities_out = _build_scheduled_activities(
        canonical_in, distribuicao_por_item, semanas_obra, schedule_selected
    )
    distribuicao_mensal = _aggregate_to_monthly(distribuicao_por_item)
    cronograma_out = _build_cronograma_out(
        mode, schedule_selected, scheduled_activities_out, semanas_obra, distribuicao_mensal, validacoes
    )
    intervalos, analise_campanhas = _build_intervalos_and_campanhas(
        canonical_in, cronograma_out, scheduled_activities_out, validacoes
    )

    mob_schedule = _run_cronograma_infer_mob_schedule(canonical_in, validacoes)

    update_dict = {
        "cronograma": cronograma_out,
        "intervalos_atividade": intervalos,
        "fator_calendario_semanal": fator_calendario_semanal,
        "calendario_operacional": calendario_operacional,
        "constraint_violations": pool_violations if pool_violations else canonical_in.constraint_violations,
        "curvas_forca": wmp_curves if wmp_curves else canonical_in.curvas_forca,
        "analise_campanhas": analise_campanhas,
    }
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


