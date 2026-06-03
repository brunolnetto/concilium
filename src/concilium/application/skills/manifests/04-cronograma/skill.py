"""Skill 02 — Cronograma Unificado (Semanal com Agregação Mensal).

Dual-mode scheduling:
  Mode 1: MANUAL_ALLOCATION — Planejador fornece num_equipes_por_item
          Usa lógica Skill 02 (cálculo de produção)

  Mode 2: AUTO_SCHEDULE — Otimização automática (DAG + recursos + prazo)
          Fallback chain: heurísticas -> relax -> MILP

Saída unificada: Cronograma com scheduled_activities (semanal) + distribuicao_mensal (mensal)
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

from concilium.application.scheduling import (
    Activity,
    ActivityDAG,
    ResourcePool,
    explore_schedules,
    select_scheduling_algorithm,
)
from concilium.application.skills.base import SkillResult
from concilium.domain.models.canonical import (
    AtividadeIntervalo,
    CanonicalModel,
    Cronograma,
    DistribuicaoSemanal,
    ScheduleCandidateCanonical,
    ScheduledActivityCanonical,
    ValidacaoItem,
)

# ════════════════════════════════════════════════════════════════════════════════
# SECTION 1: HELPERS FROM SKILL 02 (Manual Mode — Weekly Calculation)
# ════════════════════════════════════════════════════════════════════════════════


def _iso_week_key(d: date) -> str:
    """Retorna a chave de semana ISO 'AAAA-Www' para uma data."""
    iso = d.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _semanas_entre(inicio: date, fim: date) -> list[str]:
    """Lista de chaves 'AAAA-Www' das semanas ISO que cobrem o intervalo [inicio, fim]."""
    semanas: list[str] = []
    seen: set[str] = set()
    d = inicio
    while d <= fim:
        key = _iso_week_key(d)
        if key not in seen:
            seen.add(key)
            semanas.append(key)
        d += timedelta(days=1)
    return semanas


def _build_cpu_lookup(catalogo: dict[str, Any]) -> dict[str, dict]:
    """Indexa CPUs do catálogo por código."""
    return {c["codigo"]: c for c in catalogo.get("cpus", [])}


def _build_producao_lookup(catalogo: dict[str, Any]) -> dict[str, dict]:
    """Indexa artefatos de produtividade por id (ADR-007)."""
    # Suporta tanto 'producoes' (ADR) quanto 'produtividades' (implementação)
    lista = catalogo.get("produtividades", []) or catalogo.get("producoes", [])
    return {p["id"]: p for p in lista}


def _lookup_eficiencia(
    semana_key: str,
    prat_semanal: dict[str, float],
    prat_mensal: dict[str, float],
) -> float:
    """Busca eficiência para a semana. Fallback: média mensal do mês correspondente."""
    if prat_semanal and semana_key in prat_semanal:
        return prat_semanal[semana_key]

    if prat_mensal:
        year_str, week_str = semana_key.split("-W")
        week_num = int(week_str)
        month_num = max(1, min(12, (week_num - 1) // 4 + 1))
        month_key = f"{month_num:02d}"
        if month_key in prat_mensal:
            return prat_mensal[month_key]

    return 1.0


def _week_to_month(semana_key: str) -> str:
    """Converte 'AAAA-Www' para 'MM-YYYY'."""
    year_str, week_str = semana_key.split("-W")
    week_num = int(week_str)
    month_num = max(1, min(12, (week_num - 1) // 4 + 1))
    return f"{month_num:02d}-{year_str}"


# ════════════════════════════════════════════════════════════════════════════════
# SECTION 2: HELPERS FOR AUTO MODE (Scheduling)
# ════════════════════════════════════════════════════════════════════════════════


def _weeks_between(start: date, end: date) -> int:
    """Conta semanas entre duas datas."""
    return max(1, ((end - start).days // 7) + 1)


def _extract_activities(canonical: CanonicalModel) -> list[Activity]:
    """Extrai atividades do canônico (atividades ou EAP)."""
    activities: list[Activity] = []
    if canonical.atividades:
        for act in canonical.atividades:
            activities.append(
                Activity(
                    activity_id=act.atividade_id,
                    description=act.descricao,
                    duration_weeks=1,
                    required_resources={},
                )
            )
        return activities

    for item in canonical.eap:
        activities.append(
            Activity(
                activity_id=item.item_id,
                description=item.descricao,
                duration_weeks=1,
                required_resources={},
            )
        )
    return activities


def _extract_dag(canonical: CanonicalModel, activity_ids: list[str]) -> ActivityDAG:
    """Extrai DAG do canônico ou infere sequência linear."""
    if canonical.activity_dag and canonical.activity_dag.arestas:
        precedence = [(edge.de, edge.para) for edge in canonical.activity_dag.arestas]
    else:
        precedence = [(activity_ids[i], activity_ids[i + 1]) for i in range(len(activity_ids) - 1)]

    acts = _extract_activities(canonical)
    return ActivityDAG(activities=acts, precedence=precedence)


def _extract_pool(canonical: CanonicalModel) -> ResourcePool:
    """Extrai pool de recursos."""
    if not canonical.recurso_pool:
        return ResourcePool(resources={})
    resources: dict[str, int] = {}
    for item in canonical.recurso_pool:
        resources[item.tipo_id] = resources.get(item.tipo_id, 0) + int(item.quantidade_total)
    return ResourcePool(resources=resources)


def _relax_pool(pool: ResourcePool, factor: float = 1.1) -> ResourcePool:
    """Retorna novo ResourcePool com capacidades multiplicadas por factor."""
    return ResourcePool(resources={k: max(1, int(v * factor)) for k, v in pool.resources.items()})


# ────────────────────────────────────────────────────────────────────────────
# Extratores baseados em rcpsp_spec (ADR-046)
# ────────────────────────────────────────────────────────────────────────────


def _extract_activities_from_spec(spec: dict) -> list[Activity]:
    """Extrai atividades a partir de rcpsp_spec (ADR-046)."""
    return [
        Activity(
            activity_id=a["item_id"],
            description=a.get("descricao", a["item_id"]),
            duration_weeks=int(a["duration_weeks"]),
            required_resources=dict(a["required_resources"]),
        )
        for a in spec["activities"]
    ]


def _extract_pool_from_spec(spec: dict) -> ResourcePool:
    """Extrai pool de recursos a partir de rcpsp_spec (ADR-046)."""
    return ResourcePool(resources={k: int(v) for k, v in spec["resource_pool"].items()})


def _extract_dag_from_spec(spec: dict, activities: list[Activity]) -> ActivityDAG:
    """Extrai DAG de precedência a partir de rcpsp_spec (ADR-046)."""
    precedence = [(str(p[0]), str(p[1])) for p in spec.get("precedence", [])]
    return ActivityDAG(activities=activities, precedence=precedence)


def _to_canonical_candidate(
    heuristic: str,
    schedule_output: Any,
    quality_score: float,
    relaxed: bool = False,
) -> ScheduleCandidateCanonical:
    """Converte schedule output para ScheduleCandidateCanonical."""
    return ScheduleCandidateCanonical(
        heuristic=heuristic,
        scheduled_activities=[
            ScheduledActivityCanonical(
                activity_id=a.activity_id,
                start_week=a.start_week,
                end_week=a.end_week,
                duration_weeks=a.duration_weeks,
                assigned_resources=dict(a.assigned_resources),
            )
            for a in schedule_output.scheduled_activities
        ],
        makespan=schedule_output.makespan,
        quality_score=round(quality_score, 6),
        metrics={
            "resource_leveling_score": schedule_output.metrics.resource_leveling_score,
            "idle_time": float(schedule_output.metrics.idle_time),
            "activity_fragmentation": float(schedule_output.metrics.activity_fragmentation),
            "critical_path_slack_min": schedule_output.metrics.critical_path_slack_min,
            "resource_utilization_avg": schedule_output.metrics.resource_utilization_avg,
        },
        relaxed=relaxed,
    )


def _try_milp(
    activities: list[Activity],
    dag: ActivityDAG,
    pool: ResourcePool,
    deadline_weeks: int,
    timeout_seconds: int = 30,
) -> ScheduleCandidateCanonical | None:
    """Tenta resolver com MILP (opcional, lazy import)."""
    try:
        from concilium.application.scheduling.milp import MILPScheduler

        scheduler = MILPScheduler(timeout_seconds=timeout_seconds)
        sched = scheduler.schedule(
            activities=activities,
            dag=dag,
            pool=pool,
            deadline_weeks=deadline_weeks,
        )
        quality = sched.metrics.quality_score(deadline_weeks=deadline_weeks)
        return _to_canonical_candidate("MILP", sched, quality, relaxed=False)
    except (ImportError, Exception):
        return None


# ════════════════════════════════════════════════════════════════════════════════
# SECTION 3: NEW BRIDGE HELPERS (Mode Execution & Aggregation)
# ════════════════════════════════════════════════════════════════════════════════


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


def _resolve_productivity(
    cpu: dict,
    producao_lookup: dict[str, dict],
    validacoes: list[ValidacaoItem],
) -> float:
    """Resolve produtividade da CPU via producao_id_ref (ADR-053 Fase 3)."""
    prod_id_ref = cpu.get("producao_id_ref")
    if prod_id_ref and prod_id_ref in producao_lookup:
        prod_item = producao_lookup[prod_id_ref]
        valor = prod_item.get("valor_horario")
        if valor is None:
            valor = prod_item.get("producao_horaria")
            if valor is not None:
                validacoes.append(
                    ValidacaoItem(
                        codigo="VAL-PROD-04-PROD-LEGACY",
                        status="AVISO",
                        mensagem=(
                            f"Produtividade {prod_id_ref} usa campo legado 'producao_horaria'. "
                            "Migre para 'valor_horario'."
                        ),
                    )
                )
        if valor is not None and isinstance(valor, (int, float)):
            return float(valor)

    if "producao_horaria" in cpu or "producao_id" in cpu:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-PROD-04-DEPRECATED",
                status="AVISO",
                mensagem=(
                    f"CPU {cpu.get('codigo')} usa campos legados (producao_horaria/producao_id). "
                    "Atualize para producao_id_ref."
                ),
            )
        )

    validacoes.append(
        ValidacaoItem(
            codigo="VAL-PROD-04",
            status="AVISO",
            mensagem=f"Produtividade não encontrada para CPU {cpu.get('codigo')} (producao_id_ref); assumindo 1.0.",
        )
    )
    return 1.0


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
) -> int:
    """Infere num_equipes a partir de assigned_resources.

    ADR-046: assigned_resources é demanda por semana (unidades/semana),
    não total acumulado. Retorna a soma direta das unidades de recurso
    alocadas, que corresponde ao número de equipes ativas nessa semana.
    """
    if not assigned_resources:
        return 0
    return int(sum(assigned_resources.values()))


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


# ════════════════════════════════════════════════════════════════════════════════
# SECTION 4: MODE EXECUTION FUNCTIONS (MERGED)
# ════════════════════════════════════════════════════════════════════════════════


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
    semanas_obra: list,
    num_equipes_por_item: dict,
    validacoes: list,
) -> tuple[dict, list, list]:
    """Computes distribuicao and error lists for a single EAP item."""
    P = _resolve_productivity(cpu, producao_lookup, validacoes)
    producao_semanal_base = P * regime.horas_dia * regime.dias_semana
    equipes_semanas = num_equipes_por_item.get(item.item_id, {})
    distribuicao = {}
    qtd_acumulada = 0.0
    for semana_key in semanas_obra:
        num_eq = max(0, equipes_semanas.get(semana_key, 0))
        eficiencia = _lookup_eficiencia(semana_key, prat_semanal, prat_mensal)
        qtd_executada = producao_semanal_base * eficiencia * num_eq
        qtd_remanescente = item.quantitativo - qtd_acumulada
        if qtd_executada > qtd_remanescente:
            qtd_executada = max(0.0, qtd_remanescente)
        qtd_acumulada += qtd_executada
        pct = qtd_acumulada / item.quantitativo if item.quantitativo > 0 else 0.0
        distribuicao[semana_key] = DistribuicaoSemanal(
            num_equipes=num_eq,
            qtd_executada=round(qtd_executada, 2),
            qtd_acumulada=round(qtd_acumulada, 2),
            pct=round(pct, 4),
            eficiencia=round(eficiencia, 4),
        )
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
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-EAP-01",
                    status="ERRO",
                    mensagem=f"CPU {item.cpu_id} (item {item.item_id}) não encontrada.",
                )
            )
            continue
        dist, erros_c, erros_v = _emm_process_item(
            item,
            cpu,
            producao_lookup,
            regime,
            prat_semanal,
            prat_mensal,
            semanas_obra,
            num_equipes_por_item,
            validacoes,
        )
        distribuicao_por_item[item.item_id] = dist
        erros_completude_all.extend(erros_c)
        erros_vazios_all.extend(erros_v)

    if erros_completude_all:
        msg = "; ".join([f"{iid}={pct * 100:.1f}%" for iid, pct in erros_completude_all])
        validacoes.append(ValidacaoItem(codigo="VAL-CRON-01", status="ERRO", mensagem=f"Itens não completados: {msg}"))
    if erros_vazios_all:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-CRON-02", status="ERRO", mensagem=f"Gaps detectados: {'; '.join(erros_vazios_all[:5])}"
            )
        )
    return distribuicao_por_item


def _rasfc_extract_inputs(
    canonical_in: CanonicalModel,
    inputs: dict,
    validacoes: list,
) -> tuple[list, Any, Any, int] | None:
    """Extracts (activities, dag, pool, deadline_weeks) from spec or canonical. Returns None on error."""
    rcpsp_spec = inputs.get("rcpsp_spec")
    if rcpsp_spec and isinstance(rcpsp_spec, dict):
        activities = _extract_activities_from_spec(rcpsp_spec)
        if not activities:
            validacoes.append(
                ValidacaoItem(codigo="VAL-SCHED-01", status="ERRO", mensagem="rcpsp_spec sem atividades.")
            )
            return None
        pool = _extract_pool_from_spec(rcpsp_spec)
        dag = _extract_dag_from_spec(rcpsp_spec, activities)
    else:
        activities = _extract_activities(canonical_in)
        if not activities:
            validacoes.append(ValidacaoItem(codigo="VAL-SCHED-01", status="ERRO", mensagem="Sem atividades."))
            return None
        dag = _extract_dag(canonical_in, [a.activity_id for a in activities])
        pool = _extract_pool(canonical_in)

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
        )
        if explored:
            relaxed_flag = True
            validacoes.append(ValidacaoItem(codigo="VAL-SCHED-03", status="AVISO", mensagem="Pool relaxado 110%."))

    return [
        _to_canonical_candidate(r.heuristic, r.schedule, r.quality_score, relaxed_flag) for r in explored
    ], relaxed_flag


def _run_auto_schedule_fallback_chain(
    canonical_in: CanonicalModel,
    inputs: dict[str, Any],
    validacoes: list[ValidacaoItem],
) -> tuple[list[ScheduleCandidateCanonical], ScheduleCandidateCanonical | None]:
    """Executa fallback chain (heurísticas -> relax -> MILP).

    ADR-046: se inputs contiver 'rcpsp_spec', usa extratores baseados na spec
    em vez de tentar derivar do canônico (que pode estar incompleto).
    """
    extracted = _rasfc_extract_inputs(canonical_in, inputs, validacoes)
    if extracted is None:
        return [], None
    activities, dag, pool, deadline_weeks = extracted

    candidates_canonical, _relaxed = _rasfc_run_heuristics(activities, dag, pool, deadline_weeks, inputs, validacoes)

    if not candidates_canonical:
        milp_candidate = _try_milp(activities, dag, pool, deadline_weeks, timeout_seconds=30)
        if milp_candidate:
            candidates_canonical = [milp_candidate]
            validacoes.append(ValidacaoItem(codigo="VAL-SCHED-04", status="AVISO", mensagem="MILP usado."))

    if not candidates_canonical:
        validacoes.append(ValidacaoItem(codigo="VAL-SCHED-05", status="ERRO", mensagem="Cronograma inviável."))
        return [], None

    best_candidate = candidates_canonical[0]
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-SCHED-OK",
            status="OK",
            mensagem=f"{best_candidate.heuristic} (qualidade {best_candidate.quality_score:.4f})",
        )
    )
    return candidates_canonical, best_candidate


def _convert_schedule_to_distribuicao(
    schedule_selected: ScheduleCandidateCanonical,
    canonical_in: CanonicalModel,
    semanas_obra: list[str],
    cpu_lookup: dict[str, dict],
    producao_lookup: dict[str, dict],
    regime: Any,
    prat_semanal: dict[str, float],
    prat_mensal: dict[str, float],
    validacoes: list[ValidacaoItem],
) -> dict[str, dict[str, DistribuicaoSemanal]]:
    """Converte scheduled activities para distribuicao_semanal."""

    distribuicao_por_item: dict[str, dict[str, DistribuicaoSemanal]] = {}
    activity_to_item = _build_activity_item_map(canonical_in)

    for sa in schedule_selected.scheduled_activities:
        item_id = activity_to_item.get(sa.activity_id)
        if not item_id:
            validacoes.append(
                ValidacaoItem(codigo="VAL-CRON-CONVERT", status="AVISO", mensagem=f"{sa.activity_id} não mapeada.")
            )
            continue

        item = _find_item_by_id(canonical_in.eap, item_id)
        if not item:
            continue

        cpu = cpu_lookup.get(item.cpu_id)
        if not cpu:
            validacoes.append(
                ValidacaoItem(codigo="VAL-EAP-01", status="ERRO", mensagem=f"CPU {item.cpu_id} não encontrada.")
            )
            continue

        P = _resolve_productivity(cpu, producao_lookup, validacoes)
        producao_semanal_base = P * regime.horas_dia * regime.dias_semana
        distribuicao = {}
        qtd_acumulada = 0.0

        for week_offset in range(sa.duration_weeks):
            week_num = sa.start_week + week_offset
            semana_key = (
                semanas_obra[week_num]
                if week_num < len(semanas_obra)
                else _iso_week_key(canonical_in.projeto.data_inicio + timedelta(weeks=week_num))
            )

            inferred_num_equipes = _infer_teams_from_resources(
                sa.assigned_resources, cpu, week_offset, sa.duration_weeks
            )
            eficiencia = _lookup_eficiencia(semana_key, prat_semanal, prat_mensal)
            qtd_executada = producao_semanal_base * eficiencia * inferred_num_equipes
            qtd_remanescente = item.quantitativo - qtd_acumulada
            if qtd_executada > qtd_remanescente:
                qtd_executada = max(0.0, qtd_remanescente)
            qtd_acumulada += qtd_executada
            pct = qtd_acumulada / item.quantitativo if item.quantitativo > 0 else 0.0

            distribuicao[semana_key] = DistribuicaoSemanal(
                num_equipes=inferred_num_equipes,
                qtd_executada=round(qtd_executada, 2),
                qtd_acumulada=round(qtd_acumulada, 2),
                pct=round(pct, 4),
                eficiencia=round(eficiencia, 4),
            )

        distribuicao_por_item[item_id] = distribuicao

    return distribuicao_por_item


# ════════════════════════════════════════════════════════════════════════════════
# SECTION 5: POOL CONSTRAINT CHECK
# ════════════════════════════════════════════════════════════════════════════════


def _cpv_get_equip_needed(cpu: dict) -> dict[str, int]:
    """Returns {equip_id: num_unidades} from CPU config."""
    team = cpu.get("equipe") or cpu.get("composicao_padrao_equipe") or {}
    return {e["equip_id"]: e["num_unidades"] for e in team.get("equipamentos", [])}


def _cpv_build_usage(
    canonical_in: CanonicalModel,
    cpu_lookup: dict[str, dict],
    distribuicao_por_item: dict[str, dict[str, DistribuicaoSemanal]],
) -> dict[str, dict[str, int]]:
    usage: dict[str, dict[str, int]] = {}
    for item in canonical_in.eap or []:
        cpu = cpu_lookup.get(item.cpu_id)
        if not cpu:
            continue
        equip_needed = _cpv_get_equip_needed(cpu)
        if not equip_needed:
            continue
        dist = distribuicao_por_item.get(item.item_id, {})
        for semana, d in dist.items():
            if d.num_equipes <= 0:
                continue
            week_usage = usage.setdefault(semana, {})
            for tipo_id, units_per_team in equip_needed.items():
                week_usage[tipo_id] = week_usage.get(tipo_id, 0) + d.num_equipes * units_per_team
    return usage


def _cpv_process_violations(
    usage: dict[str, dict[str, int]],
    pool: dict[str, int],
    validacoes: list[ValidacaoItem],
) -> list:
    from concilium.domain.models.constraint_violation import ConstraintViolation

    violations = []
    reported: set[str] = set()
    for semana, week_usage in sorted(usage.items()):
        for tipo_id, total_used in week_usage.items():
            available = pool.get(tipo_id)
            if available is None or total_used <= available:
                continue
            magnitude = float(total_used - available)
            violations.append(
                ConstraintViolation(
                    code="VAL-POOL-01",
                    status="ERRO",
                    magnitude=magnitude,
                    affected_items=[semana],
                    remediation_hint=f"Reduzir equipes de {tipo_id} em {semana} em {int(magnitude)}",
                )
            )
            key = f"{tipo_id}@{semana}"
            if key not in reported:
                reported.add(key)
                validacoes.append(
                    ValidacaoItem(
                        codigo="VAL-POOL-01",
                        status="ERRO",
                        mensagem=f"Pool excedido: {tipo_id} requer {total_used}, disponível {available} em {semana}",
                    )
                )
    return violations


def _check_pool_violations(
    canonical_in: CanonicalModel,
    distribuicao_por_item: dict[str, dict[str, DistribuicaoSemanal]],
    cpu_lookup: dict[str, dict],
    validacoes: list[ValidacaoItem],
):
    """Verifica violações de pool de recursos. Retorna lista de ConstraintViolation."""
    pool = {r.tipo_id: r.quantidade_total for r in (canonical_in.recurso_pool or [])}
    if not pool:
        return []
    usage = _cpv_build_usage(canonical_in, cpu_lookup, distribuicao_por_item)
    return _cpv_process_violations(usage, pool, validacoes)


# ════════════════════════════════════════════════════════════════════════════════
# SECTION 6: MAIN ENTRY POINT
# ════════════════════════════════════════════════════════════════════════════════


def _check_wmp_pool(
    item_id: str,
    cpu: dict,
    policy: object,
    pool: dict,
    validacoes: list,
) -> None:
    if not pool:
        return
    for e in (cpu.get("equipe") or {}).get("equipamentos", []):
        eid = e.get("equip_id") or e.get("tipo_id")
        if not eid or eid not in pool:
            continue
        units = int(e.get("num_unidades", 1))
        peak_demand = policy.n_maximo * units  # type: ignore[union-attr]
        if peak_demand > pool[eid]:
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-WMP-POOL",
                    status="AVISO",
                    mensagem=(
                        f"WMP '{item_id}': n_maximo={policy.n_maximo} x "  # type: ignore[union-attr]
                        f"{eid}({units}/equipe) -> demanda_pico={peak_demand} "
                        f"excede pool={pool[eid]}. Reduza n_maximo ou amplie o pool."
                    ),
                )
            )


def _check_wmp_desmob(
    item_id: str,
    curva: object,
    policy: object,
    Q: float,
    P: float,
    validacoes: list,
) -> None:
    if not curva.incompleta:  # type: ignore[union-attr]
        return
    if policy.semanas_plateau is not None and policy.taxa_desmobilizacao > 0:  # type: ignore[union-attr]
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-WMP-DESMOB",
                status="AVISO",
                mensagem=(
                    f"WMP '{item_id}': desmobilizacao forcada pelo plateau={policy.semanas_plateau} sem."
                    f" antes de entregar Q={Q:.0f}. Aumente n_maximo ou semanas_plateau."
                ),
            )
        )  # type: ignore[union-attr]
    else:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-WMP-05",
                status="AVISO",
                mensagem=(
                    f"WMP '{item_id}': simulacao nao completou Q={Q:.0f} (P={P:.2f} un/h)."
                    " Verifique produtividade e politica."
                ),
            )
        )


def _build_wmp_policy(item_id: str, policy_dict: dict, validacoes: list) -> object | None:
    from concilium.domain.models.mobilizacao import MobilizacaoPolicy

    try:
        return MobilizacaoPolicy(**{k: v for k, v in policy_dict.items() if v is not None or k == "semanas_plateau"})
    except Exception as exc:
        validacoes.append(
            ValidacaoItem(codigo="VAL-WMP-03", status="AVISO", mensagem=f"WMP '{item_id}': politica invalida ({exc}).")
        )
        return None


def _run_wmp_simulation(
    sim: object,
    policy: object,
    item_id: str,
    Q: float,
    P: float,
    regime: object,
    prat_semanal: dict,
    semanas_obra: list,
    guard: int,
) -> object:
    semanas_iso = {t: semanas_obra[t] for t in range(min(guard, len(semanas_obra)))}
    return sim.simulate(  # type: ignore[union-attr]
        policy=policy,
        atividade_id=item_id,
        quantitativo=Q,
        producao_horaria=P,
        dias_semana=regime.dias_semana,  # type: ignore[union-attr]
        horas_dia=regime.horas_dia,  # type: ignore[union-attr]
        prat_semanal=prat_semanal or None,
        semanas_iso_por_offset=semanas_iso,
    )


def _process_single_wmp_policy(
    item_id: str,
    policy_dict: dict,
    eap_lookup: dict,
    cpu_lookup: dict,
    producao_lookup: dict,
    pool: dict,
    sim: object,
    regime: object,
    prat_semanal: dict,
    semanas_obra: list,
    semanas_set: set,
    result: dict,
    curves: list,
    validacoes: list,
) -> None:
    if item_id in result:
        return

    eap_item = eap_lookup.get(item_id)
    if not eap_item:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-WMP-01",
                status="AVISO",
                mensagem=f"Politica WMP '{item_id}' ignorada - item nao encontrado na EAP.",
            )
        )
        return

    cpu_id = getattr(eap_item, "cpu_id", "") or ""
    cpu = cpu_lookup.get(cpu_id)
    if not cpu:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-WMP-02",
                status="AVISO",
                mensagem=f"WMP '{item_id}': CPU '{cpu_id}' nao encontrada no catalogo.",
            )
        )
        return

    policy = _build_wmp_policy(item_id, policy_dict, validacoes)
    if policy is None:
        return

    _check_wmp_pool(item_id, cpu, policy, pool, validacoes)

    P = _resolve_productivity(cpu, producao_lookup, validacoes)
    Q = float(getattr(eap_item, "quantitativo", 0))
    if Q <= 0:
        validacoes.append(
            ValidacaoItem(codigo="VAL-WMP-04", status="AVISO", mensagem=f"WMP '{item_id}': quantitativo={Q} invalido.")
        )
        return

    prod_base = P * regime.dias_semana * regime.horas_dia * policy.n_maximo  # type: ignore[union-attr]
    nominal = math.ceil(Q / prod_base) if prod_base > 0 else 1
    from concilium.domain.services.mobilizacao_simulator import WorkforcePolicySimulator

    guard = WorkforcePolicySimulator.MAX_MULTIPLIER * max(1, nominal)

    curva = _run_wmp_simulation(sim, policy, item_id, Q, P, regime, prat_semanal, semanas_obra, guard)
    _check_wmp_desmob(item_id, curva, policy, Q, P, validacoes)

    curves.append(curva)
    week_map = {k: v for k, v in curva.to_num_equipes_por_semana().items() if k in semanas_set}
    result[item_id] = week_map
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-WMP-OK",
            status="OK",
            mensagem=(
                f"WMP '{item_id}': {curva.duration_weeks} sem.,"
                f" pico={curva.peak_teams} equipes, completa={curva.is_complete}."
            ),
        )
    )


def _extract_praticabilidade(canonical_in: object) -> tuple[dict, dict]:
    p = getattr(canonical_in, "praticabilidade", None)
    prat_semanal = (p.percentual_produtivo_semanal if p else {}) or {}
    prat_mensal = (p.percentual_produtivo_mensal if p else {}) or {}
    return prat_semanal, prat_mensal


def _determine_mode_and_distribuicao(
    canonical_in: object,
    inputs: dict,
    num_equipes_por_item: object,
    semanas_obra: list,
    cpu_lookup: dict,
    producao_lookup: dict,
    regime: object,
    prat_semanal: dict,
    prat_mensal: dict,
    catalogo: dict,
    validacoes: list,
) -> tuple[str | None, dict, list, object, bool]:
    """Returns (mode, distribuicao_por_item, schedule_candidates, schedule_selected, failed)."""
    rcpsp_spec = inputs.get("rcpsp_spec")
    if rcpsp_spec and isinstance(rcpsp_spec, dict):
        mode = "AUTO_SCHEDULE"
        validacoes.append(ValidacaoItem(codigo="VAL-CRON-MODE", status="OK", mensagem="Modo AUTO (rcpsp_spec)."))
        schedule_candidates, schedule_selected = _run_auto_schedule_fallback_chain(canonical_in, inputs, validacoes)
        if not schedule_selected:
            return mode, {}, schedule_candidates, None, True
        distribuicao_por_item = _convert_schedule_to_distribuicao(
            schedule_selected,
            canonical_in,
            semanas_obra,
            cpu_lookup,
            producao_lookup,
            regime,
            prat_semanal,
            prat_mensal,
            validacoes,
        )
        return mode, distribuicao_por_item, schedule_candidates, schedule_selected, False

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
            catalogo,
            validacoes,
        )
        return mode, distribuicao_por_item, [], None, False

    elif _can_extract_dag(canonical_in):
        mode = "AUTO_SCHEDULE"
        validacoes.append(ValidacaoItem(codigo="VAL-CRON-MODE", status="OK", mensagem="Modo AUTO."))
        schedule_candidates, schedule_selected = _run_auto_schedule_fallback_chain(canonical_in, inputs, validacoes)
        if not schedule_selected:
            return mode, {}, schedule_candidates, None, True
        distribuicao_por_item = _convert_schedule_to_distribuicao(
            schedule_selected,
            canonical_in,
            semanas_obra,
            cpu_lookup,
            producao_lookup,
            regime,
            prat_semanal,
            prat_mensal,
            validacoes,
        )
        return mode, distribuicao_por_item, schedule_candidates, schedule_selected, False

    else:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-CRON-MODE",
                status="ERRO",
                mensagem="Nenhum modo detectado: forneca 'num_equipes_por_item' ou DAG + recursos.",
            )
        )
        return None, {}, [], None, True


def _build_scheduled_activities(
    canonical_in: object,
    distribuicao_por_item: dict,
    semanas_obra: list,
) -> list:
    from datetime import timedelta

    scheduled_activities_out = []
    for item in canonical_in.eap:  # type: ignore[union-attr]
        distribuicao_semanal = distribuicao_por_item.get(item.item_id, {})
        semanas_com_producao = [s for s, d in distribuicao_semanal.items() if d.qtd_executada > 0]
        start_week = semanas_obra.index(semanas_com_producao[0]) if semanas_com_producao else 0
        end_week = semanas_obra.index(semanas_com_producao[-1]) if semanas_com_producao else 0
        data_inicio = canonical_in.projeto.data_inicio + timedelta(weeks=start_week)  # type: ignore[union-attr]
        data_fim = canonical_in.projeto.data_inicio + timedelta(weeks=end_week + 1)  # type: ignore[union-attr]
        scheduled_activities_out.append(
            ScheduledActivityCanonical(
                activity_id=item.item_id,
                start_week=start_week,
                end_week=end_week,
                duration_weeks=max(1, end_week - start_week + 1),
                data_inicio=data_inicio,
                data_fim=data_fim,
                distribuicao_semanal=distribuicao_semanal,
            )
        )
    return scheduled_activities_out


def _build_cronograma_out(
    mode: str | None,
    schedule_selected: object,
    scheduled_activities_out: list,
    semanas_obra: list,
    distribuicao_mensal: dict,
    validacoes: list,
) -> object:
    AVAILABLE_SCHEDULE_ALGORITHMS = ("MINSLK", "LPT", "MAXRES", "ES", "GR", "MILP")
    if mode == "MANUAL_ALLOCATION":
        _algo = "manual_allocation"
    elif schedule_selected and schedule_selected.heuristic in AVAILABLE_SCHEDULE_ALGORITHMS:  # type: ignore[union-attr]
        _algo = schedule_selected.heuristic  # type: ignore[union-attr]
    else:
        _algo = "MINSLK"

    return Cronograma(
        algorithm=_algo,
        quality_score=schedule_selected.quality_score if schedule_selected else 0.0,  # type: ignore[union-attr]
        makespan_weeks=schedule_selected.makespan if schedule_selected else len(semanas_obra),  # type: ignore[union-attr]
        is_feasible=not any(v.status == "ERRO" for v in validacoes),
        was_relaxed=schedule_selected.relaxed if schedule_selected else False,  # type: ignore[union-attr]
        scheduled_activities=scheduled_activities_out,
        distribuicao_mensal=distribuicao_mensal,
        pct_completude=1.0,
    )


def _build_intervalos_and_campanhas(
    canonical_in: object,
    cronograma_out: object,
    scheduled_activities_out: list,
    validacoes: list,
) -> tuple[list, object]:
    intervalos = []
    for sa in scheduled_activities_out:
        intervalos.extend(AtividadeIntervalo.from_scheduled_activity(sa))

    analise_campanhas = None
    try:
        from concilium.domain.services.campanha_equipamento_builder import CampanhaEquipamentoBuilder

        _temp = canonical_in.model_copy(update={"cronograma": cronograma_out})  # type: ignore[union-attr]
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
    from concilium.domain.services.mobilizacao_simulator import WorkforcePolicySimulator

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

    regime = canonical_in.projeto.regime_trabalho
    semanas_obra = _semanas_entre(canonical_in.projeto.data_inicio, canonical_in.projeto.data_termino)
    cpu_lookup = _build_cpu_lookup(catalogo)
    producao_lookup = _build_producao_lookup(catalogo)
    prat_semanal, prat_mensal = _extract_praticabilidade(canonical_in)

    num_equipes_por_item = inputs.get("num_equipes_por_item")

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
        catalogo,
        validacoes,
    )
    if failed:
        return SkillResult(canonical_in, validacoes)

    pool_violations = _check_pool_violations(canonical_in, distribuicao_por_item, cpu_lookup, validacoes)
    scheduled_activities_out = _build_scheduled_activities(canonical_in, distribuicao_por_item, semanas_obra)
    distribuicao_mensal = _aggregate_to_monthly(distribuicao_por_item)
    cronograma_out = _build_cronograma_out(
        mode, schedule_selected, scheduled_activities_out, semanas_obra, distribuicao_mensal, validacoes
    )
    intervalos, analise_campanhas = _build_intervalos_and_campanhas(
        canonical_in, cronograma_out, scheduled_activities_out, validacoes
    )

    updated_canonical = canonical_in.model_copy(
        update={
            "cronograma": cronograma_out,
            "intervalos_atividade": intervalos,
            "constraint_violations": pool_violations if pool_violations else canonical_in.constraint_violations,
            "curvas_forca": wmp_curves if wmp_curves else canonical_in.curvas_forca,
            "analise_campanhas": analise_campanhas,
        }
    )

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
