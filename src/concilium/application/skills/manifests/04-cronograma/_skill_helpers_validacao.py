"""Skill 04 — Cronograma (parte extraída de skill.py)."""

from __future__ import annotations

from typing import Any

from concilium.application.scheduling import (
    explore_schedules,
    select_scheduling_algorithm,
)
from concilium.domain.models.canonical import (
    CanonicalModel,
    DistribuicaoSemanal,
    ValidacaoItem,
)

from ._skill_helpers_calendario import (  # ty: ignore[unresolved-import]
    _extract_activities,
    _extract_dag,
    _extract_pool,
    _relax_pool,
    _resolve_productivity,
    _week_to_month,
    _weeks_between,
)
from ._skill_helpers_custos import _build_dist_cell, _lookup_eficiencia  # ty: ignore[unresolved-import]
from ._skill_helpers_spec import (  # ty: ignore[unresolved-import]
    _enrich_spec_resources_from_catalog,
    _extract_activities_from_spec,
    _extract_dag_from_spec,
    _extract_pool_from_spec,
    _to_canonical_candidate,
)


def _validate_preconditions(canonical: CanonicalModel, validacoes: list[ValidacaoItem]) -> bool:
    """Validações comuns a ambos os modos."""
    if not canonical.projeto:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-CRON-PRECONDICAO",
                status="ERRO",
                mensagem="Projeto não definido no canônico.",
            )
        )
        return False

    if not canonical.eap:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-CRON-PRECONDICAO",
                status="ERRO",
                mensagem="EAP vazia no canônico.",
            )
        )
        return False

    if not canonical.praticabilidade:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-CRON-PRECONDICAO",
                status="AVISO",
                mensagem="Praticabilidade não calculada; usando 100% de produtividade.",
            )
        )

    return True


def _can_extract_dag(canonical: CanonicalModel) -> bool:
    """Verifica se atividades ou DAG estão disponíveis para auto-schedule."""
    return bool(canonical.activity_dag or canonical.atividades or canonical.eap)


def _build_activity_item_map(canonical: CanonicalModel) -> dict[str, str]:
    """Mapeia activity_id -> item_id.

    Sempre inclui item_id→item_id como base (cobertura de AUTO/RCPSP onde o
    solver usa item_id como activity_id). Sobrepõe com atividade_id→eap_item_id
    quando atividades explícitas existem (modo MANUAL).
    """
    mapping: dict[str, str] = {}
    # Fallback: item_id direto (RCPSP/AUTO — activity_id == item_id)
    for item in canonical.eap:
        mapping[item.item_id] = item.item_id
    # Override: atividade_id → eap_item_id (MANUAL — UUIDs de atividades)
    if canonical.atividades:
        for act in canonical.atividades:
            mapping[act.atividade_id] = act.eap_item_id
    return mapping


def _find_item_by_id(eap: list, item_id: str):
    """Encontra item na EAP por item_id."""
    for item in eap:
        if item.item_id == item_id:
            return item
    return None


def _infer_teams_from_resources(
    assigned_resources: dict[str, int],
    cpu: dict,
    week_offset: int,
    total_weeks: int,
    ramp_profile: list[float] | None = None,
) -> int:
    """Infere num_equipes a partir de assigned_resources.

    ADR-046: assigned_resources é demanda por semana (unidades/semana),
    não total acumulado. Retorna a soma direta das unidades de recurso
    alocadas, que corresponde ao número de equipes ativas nessa semana.

    ADR-074: Quando ``ramp_profile`` é fornecido, escala a demanda peak pelo
    fator da semana. ``ramp_profile[week_offset]`` ∈ [0.0, 1.0] onde 1.0 = pico.

    Minimalista fallback: Quando assigned_resources está vazio (pool vazio em AUTO_SCHEDULE),
    retorna 1 equipe por semana para permitir que skill-05 calcule custos. Isso é uma
    heurística padrão que representa "1 equipe típica para essa atividade".
    """
    if not assigned_resources:
        return 1
    peak = int(sum(assigned_resources.values()))
    if ramp_profile is not None and week_offset < len(ramp_profile):
        # ramp_profile[t] = val/n_pico onde val é int → peak * (val/n_pico) = int exato
        # quando peak == n_pico. int() é seguro aqui; round() como fallback para floats
        # que não codificam inteiros perfeitos (specs legadas).
        return max(0, int(round(peak * ramp_profile[week_offset])))
    return peak


def _aggregate_to_monthly(distribuicao_por_item: dict[str, dict[str, DistribuicaoSemanal]]) -> dict[str, dict]:
    """Agrega distribuicao_semanal em distribuicao_mensal."""
    monthly_agg: dict[str, dict] = {}
    for item_id, distribuicao_semanal in distribuicao_por_item.items():
        for semana_key, dist_semanal in distribuicao_semanal.items():
            month_str = _week_to_month(semana_key)
            if month_str not in monthly_agg:
                monthly_agg[month_str] = {"qtd_executada": 0.0, "num_itens": 0, "atividades": []}
            monthly_agg[month_str]["qtd_executada"] += dist_semanal.qtd_executada
            if item_id not in monthly_agg[month_str]["atividades"]:
                monthly_agg[month_str]["atividades"].append(item_id)
            monthly_agg[month_str]["num_itens"] += 1
    return monthly_agg


def _emm_find_vazios(item_id: str, distribuicao: dict, semanas_obra: list) -> list[str]:
    """Finds gap weeks inside productive periods."""
    semanas_produtivas = [s for s, d in distribuicao.items() if d.num_equipes > 0]
    if len(semanas_produtivas) < 2:
        return []
    inicio_idx = semanas_obra.index(semanas_produtivas[0])
    fim_idx = semanas_obra.index(semanas_produtivas[-1])
    return [
        f"{item_id}@{semanas_obra[i]}"
        for i in range(inicio_idx + 1, fim_idx)
        if distribuicao[semanas_obra[i]].num_equipes == 0
    ]


def _emm_process_item(
    item: Any,
    cpu: dict,
    producao_lookup: dict,
    regime: Any,
    prat_semanal: dict,
    prat_mensal: dict,
    fator_calendario_semanal: dict[str, float],
    semanas_obra: list,
    num_equipes_por_item: dict,
    validacoes: list,
) -> tuple[dict, list, list]:
    """Computes distribuicao and error lists for a single EAP item."""
    P = _resolve_productivity(cpu, producao_lookup, validacoes)
    producao_semanal_base = P * regime.horas_dia * regime.dias_semana
    equipes_semanas = num_equipes_por_item.get(item.item_id, {})
    # NEP-035: n_max = pico de alocação planejado para a atividade (η_s = n_j / n_max)
    n_max = max((max(0, equipes_semanas.get(s, 0)) for s in semanas_obra), default=1) or 1
    distribuicao = {}
    qtd_acumulada = 0.0
    for semana_key in semanas_obra:
        num_eq = max(0, equipes_semanas.get(semana_key, 0))
        fator_clima = _lookup_eficiencia(semana_key, prat_semanal, prat_mensal)
        fator_calendario = fator_calendario_semanal.get(semana_key, 1.0)
        cell = _build_dist_cell(
            producao_semanal_base,
            num_eq,
            n_max,
            fator_clima,
            fator_calendario,
            item.quantitativo,
            qtd_acumulada,
        )
        qtd_acumulada = cell.qtd_acumulada
        distribuicao[semana_key] = cell
    erros_completude = []
    pct_completude = qtd_acumulada / item.quantitativo if item.quantitativo > 0 else 0.0
    if pct_completude < 0.999:
        erros_completude.append((item.item_id, round(pct_completude, 4)))
    erros_vazios = _emm_find_vazios(item.item_id, distribuicao, semanas_obra)
    return distribuicao, erros_completude, erros_vazios


def _execute_manual_mode(
    canonical_in: CanonicalModel,
    num_equipes_por_item: dict[str, dict[str, int]],
    semanas_obra: list[str],
    cpu_lookup: dict[str, dict],
    producao_lookup: dict[str, dict],
    regime: Any,
    prat_semanal: dict[str, float],
    prat_mensal: dict[str, float],
    fator_calendario_semanal: dict[str, float],
    catalogo: dict[str, Any],
    validacoes: list[ValidacaoItem],
) -> dict[str, dict[str, DistribuicaoSemanal]]:
    """Executa lógica Skill 02 (modo manual)."""
    distribuicao_por_item: dict[str, dict[str, DistribuicaoSemanal]] = {}
    erros_completude_all = []
    erros_vazios_all = []

    for item in canonical_in.eap:
        cpu = cpu_lookup.get(item.cpu_id)
        if not cpu:
            # CPU not found in catalog - create synthetic CPU with reasonable defaults
            # This allows scheduling to proceed with sensible assumptions
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-EAP-01",
                    status="AVISO",
                    mensagem=f"CPU {item.cpu_id} (item {item.item_id}) não encontrada no catálogo; "
                    f"usando CPU sintética.",
                )
            )
            # Create synthetic CPU with reasonable defaults for scheduling
            cpu = {
                "codigo": item.cpu_id,
                "descricao": f"CPU sintética para {item.item_id}",
                "producao_id_ref": None,  # Will trigger default productivity of 100.0
            }
        dist, erros_c, erros_v = _emm_process_item(
            item,
            cpu,
            producao_lookup,
            regime,
            prat_semanal,
            prat_mensal,
            fator_calendario_semanal,
            semanas_obra,
            num_equipes_por_item,
            validacoes,
        )
        distribuicao_por_item[item.item_id] = dist
        erros_completude_all.extend(erros_c)
        erros_vazios_all.extend(erros_v)

    if erros_completude_all:
        msg = "; ".join([f"{iid}={pct * 100:.1f}%" for iid, pct in erros_completude_all])
        # ADR-082: Incomplete items are warnings, not errors. Climate/schedule constraints
        # may reduce capacity below project requirements. Decision to extend schedule or add
        # teams is a business decision (ADR-091), not a technical blocker.
        validacoes.append(ValidacaoItem(codigo="VAL-CRON-01", status="ERRO", mensagem=f"Itens não completados: {msg}"))
    if erros_vazios_all:
        # ADR-082: Scheduling gaps are warnings, not errors. May indicate suboptimal
        # allocation but don't prevent schedule execution.
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-CRON-02", status="ERRO", mensagem=f"Gaps detectados: {'; '.join(erros_vazios_all[:5])}"
            )
        )
    return distribuicao_por_item


def _rasfc_propagate_pool_config(rcpsp_spec: dict, inputs: dict) -> None:
    """ADR-091 Fase 4: propaga pool_config (entrada first-class) para a spec
    antes da inferência, sem expor resource_pool ao usuário."""
    pool_config_in = inputs.get("pool_config")
    if isinstance(pool_config_in, dict) and "pool_config" not in rcpsp_spec:
        rcpsp_spec["pool_config"] = pool_config_in


def _rasfc_enrich_from_catalog_if_available(
    rcpsp_spec: dict,
    canonical_in: CanonicalModel,
    inputs: dict,
    validacoes: list,
    cpu_lookup: dict | None,
    producao_lookup: dict | None,
) -> None:
    """Constrói required_resources + resource_pool + duração do catálogo
    (composicao_padrao_equipe) — pré-requisito para o pool não degenerar."""
    if not (cpu_lookup and producao_lookup):
        return
    deadline = int(
        inputs.get("deadline_weeks")
        or rcpsp_spec.get("deadline_weeks")
        or _weeks_between(canonical_in.projeto.data_inicio, canonical_in.projeto.data_termino)
    )
    _enrich_spec_resources_from_catalog(rcpsp_spec, canonical_in, cpu_lookup, producao_lookup, deadline, validacoes)


def _rasfc_report_pool_inferido_diag(rcpsp_spec: dict, validacoes: list) -> None:
    """ADR-091: se o pool foi inferido, registra o tradeoff tempo×custo."""
    diag = rcpsp_spec.get("pool_inferido_diag")
    if not isinstance(diag, dict):
        return
    notas = "; ".join(diag.get("notas", [])) or "sem restrições adicionais"
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-POOL-INFER",
            status="OK",
            mensagem=(
                f"Pool inferido (objetivo={diag.get('objetivo')}): "
                f"{diag.get('pool_inferido')} | makespan~{diag.get('makespan_estimado_semanas')}sem "
                f"(mín {diag.get('makespan_minimo_semanas')}sem) | {notas}"
            ),
        )
    )


def _rasfc_extract_from_spec(
    rcpsp_spec: dict,
    canonical_in: CanonicalModel,
    inputs: dict,
    validacoes: list,
    cpu_lookup: dict | None,
    producao_lookup: dict | None,
) -> tuple[list, Any, Any] | None:
    """Extrai (activities, dag, pool) a partir de rcpsp_spec. Retorna None em erro."""
    _rasfc_propagate_pool_config(rcpsp_spec, inputs)
    _rasfc_enrich_from_catalog_if_available(rcpsp_spec, canonical_in, inputs, validacoes, cpu_lookup, producao_lookup)
    # ADR-072: pass lookups so productive duration is computed
    activities = _extract_activities_from_spec(rcpsp_spec, canonical_in, cpu_lookup, producao_lookup, validacoes)
    if not activities:
        validacoes.append(ValidacaoItem(codigo="VAL-SCHED-01", status="ERRO", mensagem="rcpsp_spec sem atividades."))
        return None
    pool = _extract_pool_from_spec(rcpsp_spec, canonical_in)
    _rasfc_report_pool_inferido_diag(rcpsp_spec, validacoes)
    # ADR-081: passa eap_items para derivar precedência com thresholds
    dag = _extract_dag_from_spec(rcpsp_spec, activities, eap_items=canonical_in.eap or [])
    return activities, dag, pool


def _rasfc_extract_from_canonical(
    canonical_in: CanonicalModel,
    cpu_lookup: dict | None,
    producao_lookup: dict | None,
    validacoes: list,
) -> tuple[list, Any, Any] | None:
    """Extrai (activities, dag, pool) a partir do canônico (sem rcpsp_spec). Retorna None em erro."""
    activities = _extract_activities(canonical_in, cpu_lookup, producao_lookup, validacoes)
    if not activities:
        validacoes.append(ValidacaoItem(codigo="VAL-SCHED-01", status="ERRO", mensagem="Sem atividades."))
        return None
    # ADR-072: pass pre-computed activities to preserve duration_weeks calculation
    dag = _extract_dag(canonical_in, [a.activity_id for a in activities], activities=activities)
    pool = _extract_pool(canonical_in)
    return activities, dag, pool


def _rasfc_extract_inputs(
    canonical_in: CanonicalModel,
    inputs: dict,
    validacoes: list,
    cpu_lookup: dict | None = None,
    producao_lookup: dict | None = None,
) -> tuple[list, Any, Any, int] | None:
    """Extracts (activities, dag, pool, deadline_weeks) from spec or canonical. Returns None on error."""
    rcpsp_spec = inputs.get("rcpsp_spec")
    if rcpsp_spec and isinstance(rcpsp_spec, dict):
        result = _rasfc_extract_from_spec(rcpsp_spec, canonical_in, inputs, validacoes, cpu_lookup, producao_lookup)
    else:
        result = _rasfc_extract_from_canonical(canonical_in, cpu_lookup, producao_lookup, validacoes)

    if result is None:
        return None
    activities, dag, pool = result

    if not pool.resources:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-SCHED-02", status="AVISO", mensagem="Pool vazio — agendando sem restrições de recursos."
            )
        )

    deadline_weeks = int(
        inputs.get("deadline_weeks")
        or (rcpsp_spec.get("deadline_weeks") if isinstance(rcpsp_spec, dict) else None)
        or _weeks_between(canonical_in.projeto.data_inicio, canonical_in.projeto.data_termino)
    )
    return activities, dag, pool, deadline_weeks


def _rasfc_run_heuristics(
    activities: list, dag: Any, pool: Any, deadline_weeks: int, inputs: dict, validacoes: list
) -> tuple[list, bool]:
    """Runs heuristic scheduling with optional pool relaxation. Returns (candidates_canonical, relaxed_flag)."""
    strategy = select_scheduling_algorithm(
        num_activities=len(activities),
        num_resource_types=max(1, len(pool.resources)),
        contract_duration_weeks=deadline_weeks,
        deadline_margin_pct=float(inputs.get("deadline_margin_pct", 0.2)),
        criticality=str(inputs.get("criticality", "medium")),
    )
    if inputs.get("algorithm"):
        strategy.algorithm = str(inputs["algorithm"])
    if inputs.get("heuristics"):
        strategy.heuristics = list(inputs["heuristics"])

    heuristics = strategy.heuristics or ["MINSLK"]
    explored = explore_schedules(
        activities=activities,
        dag=dag,
        pool=pool,
        deadline_weeks=deadline_weeks,
        heuristics=heuristics,
        top_n=int(inputs.get("top_n", 3)),
        strategy=strategy,
    )
    relaxed_flag = False

    if not explored:
        relaxed_pool = _relax_pool(pool)
        explored = explore_schedules(
            activities=activities,
            dag=dag,
            pool=relaxed_pool,
            deadline_weeks=deadline_weeks,
            heuristics=heuristics,
            top_n=3,
            strategy=strategy,
        )
        if explored:
            relaxed_flag = True
            validacoes.append(ValidacaoItem(codigo="VAL-SCHED-03", status="AVISO", mensagem="Pool relaxado 110%."))

    return [
        _to_canonical_candidate(r.heuristic, r.schedule, r.quality_score, relaxed_flag) for r in explored
    ], relaxed_flag



__all__ = [
    "_aggregate_to_monthly",
    "_build_activity_item_map",
    "_can_extract_dag",
    "_emm_find_vazios",
    "_emm_process_item",
    "_execute_manual_mode",
    "_find_item_by_id",
    "_infer_teams_from_resources",
    "_rasfc_enrich_from_catalog_if_available",
    "_rasfc_extract_from_canonical",
    "_rasfc_extract_from_spec",
    "_rasfc_extract_inputs",
    "_rasfc_propagate_pool_config",
    "_rasfc_report_pool_inferido_diag",
    "_rasfc_run_heuristics",
    "_validate_preconditions",
]
