"""Skill 04 — Cronograma (parte extraída de skill.py)."""

from __future__ import annotations

from typing import Any

from concilium.application.scheduling import (
    explore_schedules,
    select_scheduling_algorithm,
)
from concilium.application.scheduling.models import ReplenishableResource
from concilium.application.scheduling.replenishable_builder import (
    _CAMPOS_DISPONIBILIDADE,
    build_replenishable_resources,
)
from concilium.domain.models.canonical import (
    CanonicalModel,
    DistribuicaoSemanal,
    ValidacaoItem,
)
from concilium.domain.models.catalog.disponibilidade_consumivel import DisponibilidadeConsumivel

from ._calendario import (  # ty: ignore[unresolved-import]
    _build_item_to_activity_map,
    _extract_activities,
    _extract_dag,
    _extract_pool,
    _relax_pool,
    _resolve_productivity,
    _week_to_month,
    _weeks_between,
)
from ._custos import _build_dist_cell, _capacidade_semanal_por_frentes, _lookup_eficiencia  # ty: ignore[unresolved-import]
from ._spec import (  # ty: ignore[unresolved-import]
    _build_producoes_por_atividade,
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


def _extract_taxa_desmobilizacao_fracao(ramp_profile: list[float] | None) -> float | None:
    """Recupera μ⁻ (taxa de desmobilização, fração do pico por semana) do trecho final
    decrescente de `ramp_profile`, se houver.

    `_compute_ramp_profile` (ADR-074) já embute ramp-up/platô/ramp-down num único array
    normalizado [0,1] — aqui só extraímos de volta a taxa do trecho decrescente, para
    reaplicar a MESMA política no momento certo (decidido por estado real, via
    `_producao_maxima_com_rampa_down`) em vez de confiar na posição pré-computada do
    array, que foi ancorada numa duração nominal que pode estar errada.

    Varre de trás para frente e para no primeiro par não-decrescente — isola exatamente
    o trecho de ramp-down, ignorando platô/ramp-up antes dele. Retorna None quando não há
    trecho decrescente identificável (perfil ausente, curto demais, ou monotonicamente
    não-decrescente) — nesse caso não há política de desmobilização declarada, e nenhuma
    é inventada.
    """
    if ramp_profile is None or len(ramp_profile) < 2:
        return None
    diffs: list[float] = []
    for i in range(len(ramp_profile) - 1, 0, -1):
        diff = ramp_profile[i - 1] - ramp_profile[i]
        if diff <= 0:
            break
        diffs.append(diff)
    if not diffs:
        return None
    return sum(diffs) / len(diffs)


def _producao_maxima_com_rampa_down(
    frac_atual: float, taxa_desmob_fracao: float, capacidade_pico_semanal: float
) -> float:
    """Produção total alcançável se a desmobilização (linear, `taxa_desmob_fracao` do
    pico por semana) começar AGORA, a partir de `frac_atual` (fração do pico em uso
    nesta semana) até zerar — área do triângulo fração×pico:

        capacidade_pico_semanal · frac_atual² / (2 · taxa_desmob_fracao)

    Usado por `_build_activity_distribuicao` para decidir, semana a semana, se é seguro
    reduzir a equipe agora — um look-ahead orientado a estado real (Q remanescente),
    não à posição no calendário: resolve a circularidade de "quando começar o
    ramp-down" sem precisar prever N_i, porque é recalculado a cada semana com dados
    já conhecidos (nunca clima futuro).
    """
    if taxa_desmob_fracao <= 0:
        return float("inf")
    return capacidade_pico_semanal * (frac_atual**2) / (2.0 * taxa_desmob_fracao)


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
) -> tuple[dict, list, list, bool]:
    """Computes distribuicao and error lists for a single EAP item.

    O 4º elemento (issue #132) é `is_fallback`: True quando a produtividade veio do
    default arbitrário (P=1000 un/h) — usado por `_execute_manual_mode` para marcar
    `produtividade_fallback_aplicada` no `ScheduledActivityCanonical` final.
    """
    P, is_fallback = _resolve_productivity(cpu, producao_lookup, validacoes)
    producao_semanal_base = P * regime.horas_dia * regime.dias_semana
    equipes_semanas = num_equipes_por_item.get(item.item_id, {})
    # n_max is the peak number of mobilized fronts, not an efficiency reference.
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
            fator_jornada=regime.eta_jornada,
            capacidade_fisica_semanal=_capacidade_semanal_por_frentes(
                producao_semanal_base, num_eq, n_max,
                producao_lookup.get(cpu.get("producao_id_ref")),
                horas_semana=regime.horas_dia * regime.dias_semana,
            ),
        )
        qtd_acumulada = cell.qtd_acumulada
        distribuicao[semana_key] = cell
    erros_completude = []
    pct_completude = qtd_acumulada / item.quantitativo if item.quantitativo > 0 else 0.0
    if qtd_acumulada < item.quantitativo:
        erros_completude.append((item.item_id, round(pct_completude, 4)))
    erros_vazios = _emm_find_vazios(item.item_id, distribuicao, semanas_obra)
    return distribuicao, erros_completude, erros_vazios, is_fallback


def _execute_manual_mode(
    canonical_in: CanonicalModel,
    num_equipes_por_item: dict[str, dict[str, float]],
    semanas_obra: list[str],
    cpu_lookup: dict[str, dict],
    producao_lookup: dict[str, dict],
    regime: Any,
    prat_semanal: dict[str, float],
    prat_mensal: dict[str, float],
    fator_calendario_semanal: dict[str, float],
    catalogo: dict[str, Any],
    validacoes: list[ValidacaoItem],
) -> tuple[dict[str, dict[str, DistribuicaoSemanal]], set[str]]:
    """Executa lógica Skill 04 (modo manual).

    Retorna também `fallback_item_ids` (issue #132) — mesma semântica de
    `_convert_schedule_to_distribuicao` (modo AUTO_SCHEDULE): item_ids cuja
    produtividade veio do default arbitrário (P=1000 un/h). Este modo é justamente
    onde a CPU sintética (linha ~244, sem `producao_id_ref`) força o fallback, então
    cobri-lo aqui é essencial — não é um call-site secundário.
    """
    distribuicao_por_item: dict[str, dict[str, DistribuicaoSemanal]] = {}
    fallback_item_ids: set[str] = set()
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
        dist, erros_c, erros_v, is_fallback = _emm_process_item(
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
        if is_fallback:
            fallback_item_ids.add(item.item_id)
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
    return distribuicao_por_item, fallback_item_ids


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


def _rasfc_warn_if_pool_vazio(pool: Any, validacoes: list) -> None:
    """VAL-SCHED-02 (AVISO) quando o pool extraído não tem nenhum recurso."""
    if not pool.resources:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-SCHED-02", status="AVISO", mensagem="Pool vazio — agendando sem restrições de recursos."
            )
        )


def _rasfc_compute_deadline_weeks(inputs: dict, rcpsp_spec: Any, canonical_in: CanonicalModel) -> int:
    """Resolve o prazo em semanas: ``inputs`` > ``rcpsp_spec`` > datas do projeto."""
    return int(
        inputs.get("deadline_weeks")
        or (rcpsp_spec.get("deadline_weeks") if isinstance(rcpsp_spec, dict) else None)
        or _weeks_between(canonical_in.projeto.data_inicio, canonical_in.projeto.data_termino)
    )


def _rasfc_build_producoes_por_atividade(
    canonical_in: CanonicalModel,
    cpu_lookup: dict | None,
    producao_lookup: dict | None,
    *,
    usa_atividade_id: bool = True,
) -> dict[str, Any]:
    """Pareamento atividade→Producao (ADR-139 D5); vazio sem ambos os lookups de catálogo.

    Traduz item_id -> atividade_id via `_build_item_to_activity_map` (mesmo
    mapeamento já usado por `_extract_edge_thresholds_from_eap` para as arestas
    de precedência) SÓ quando o DAG do CP-SAT de fato usa esse espaço de IDs —
    ou seja, quando `_rasfc_extract_from_canonical` construiu as atividades via
    `_extract_activities` (usa `atividade_id` se `canonical.atividades` estiver
    populado). Sem esta tradução nesse caso, `producao_por_semana`/
    `consumo_por_semana` do `ReplenishableResource` (chaveados por item_id puro)
    nunca batem com `acts` (chaveado por atividade_id), e `VAL-ESTOQUE-PROD-01`
    dispara sempre que há material gerado internamente — mesmo com a atividade
    de fato presente no DAG (issue #142).

    `usa_atividade_id=False` (issue #125, regressão do fix acima): quando
    `_rasfc_extract_from_spec` monta as atividades a partir de `rcpsp_spec`
    (`_build_activity_from_spec_entry`), `activity_id` é SEMPRE `item.item_id`
    puro — mesmo com `canonical.atividades` populado (caso comum, ex. AGIS). A
    tradução incondicional fazia `producao_por_semana` referenciar IDs
    (`-atv-N`) inexistentes nesse DAG, disparando `VAL-ESTOQUE-PROD-01` para
    todo projeto rcpsp_spec com material de geração interna. `_rasfc_extract_inputs`
    passa `usa_atividade_id=not bool(rcpsp_spec)` para escolher o espaço de IDs
    certo por chamada, em vez de assumir um único DAG-building path.
    """
    if not (cpu_lookup and producao_lookup):
        return {}
    por_item = _build_producoes_por_atividade(canonical_in.eap or [], cpu_lookup, producao_lookup)
    if not usa_atividade_id:
        return por_item
    item_to_activity = _build_item_to_activity_map(canonical_in)
    return {item_to_activity.get(item_id, item_id): prod for item_id, prod in por_item.items()}


def _rasfc_extract_inputs(
    canonical_in: CanonicalModel,
    inputs: dict,
    validacoes: list,
    cpu_lookup: dict | None = None,
    producao_lookup: dict | None = None,
) -> tuple[list, Any, Any, int, dict[str, Any]] | None:
    """Extracts (activities, dag, pool, deadline_weeks, producoes_por_atividade) from spec
    or canonical. Returns None on error.

    ADR-128 F5: ``producoes_por_atividade`` (pareamento atividade→Producao, ADR-139 D5)
    é construído aqui — reaproveitando o mesmo pareamento CPU→Producao já resolvido
    internamente para dimensionar n_frentes — e passado adiante para que
    ``_rasfc_run_heuristics`` possa montar ``ReplenishableResource`` sem refazer a
    resolução. Vazio quando ``cpu_lookup``/``producao_lookup`` não foram fornecidos.
    """
    rcpsp_spec = inputs.get("rcpsp_spec")
    if rcpsp_spec and isinstance(rcpsp_spec, dict):
        result = _rasfc_extract_from_spec(rcpsp_spec, canonical_in, inputs, validacoes, cpu_lookup, producao_lookup)
    else:
        result = _rasfc_extract_from_canonical(canonical_in, cpu_lookup, producao_lookup, validacoes)

    if result is None:
        return None
    activities, dag, pool = result

    _rasfc_warn_if_pool_vazio(pool, validacoes)

    deadline_weeks = _rasfc_compute_deadline_weeks(inputs, rcpsp_spec, canonical_in)
    # issue #125: só traduz item_id->atividade_id quando o DAG foi montado por
    # _rasfc_extract_from_canonical (usa atividade_id) — _rasfc_extract_from_spec
    # (rcpsp_spec presente) sempre usa item_id puro (_build_activity_from_spec_entry).
    usa_atividade_id = not (rcpsp_spec and isinstance(rcpsp_spec, dict))
    producoes_por_atividade = _rasfc_build_producoes_por_atividade(
        canonical_in, cpu_lookup, producao_lookup, usa_atividade_id=usa_atividade_id
    )
    return activities, dag, pool, deadline_weeks, producoes_por_atividade


def _parse_logistica_consumiveis_overrides(
    logistica_consumiveis: dict[str, Any] | None,
) -> dict[str, DisponibilidadeConsumivel] | None:
    """Converte ``Escopo.logistica_consumiveis`` (dict cru vindo de ``inputs``) em
    ``dict[insumo_id, DisponibilidadeConsumivel]`` (ADR-128 F5). ``None``/vazio/não-dict
    retorna ``None`` — ausência de configuração de projeto preserva o comportamento atual."""
    if not logistica_consumiveis or not isinstance(logistica_consumiveis, dict):
        return None
    overrides: dict[str, DisponibilidadeConsumivel] = {}
    for insumo_id, campos in logistica_consumiveis.items():
        if not isinstance(campos, dict):
            continue
        overrides[insumo_id] = DisponibilidadeConsumivel(
            **{k: campos[k] for k in _CAMPOS_DISPONIBILIDADE if k in campos}
        )
    return overrides or None


def _build_replenishable_resources_if_any(
    producoes_por_atividade: dict[str, Any] | None,
    insumos_lookup: dict | None,
    logistica_consumiveis: dict[str, Any] | None,
    validacoes: list,
) -> list[ReplenishableResource] | None:
    """ADR-128/139 F5: monta os ``ReplenishableResource`` do projeto, se houver
    algum sinal de restrição (produção/consumo de material + catálogo/config de
    projeto). Retorna ``None`` rápido quando não há nenhum pareamento
    atividade→Producao — preserva o comportamento pré-F5 sem custo adicional."""
    if not producoes_por_atividade or insumos_lookup is None:
        return None
    overrides = _parse_logistica_consumiveis_overrides(logistica_consumiveis)
    try:
        resources = build_replenishable_resources(
            producoes_por_atividade,
            insumos_lookup,
            disponibilidade_overrides=overrides,
        )
    except ValueError as exc:
        validacoes.append(ValidacaoItem(codigo="VAL-ESTOQUE-BUILD-01", status="ERRO", mensagem=str(exc)))
        return None
    # ADR-151: torna visível, no relatório do projeto, todo material com déficit
    # estrutural conhecido e já provisionado externamente — em vez de só o
    # cronograma fechar "magicamente", o engenheiro vê explicitamente o quê e
    # quanto precisa ser adquirido/providenciado além da produção interna pareada.
    for resource in resources:
        deficit = resource.disponibilidade.deficit_provisionado_externamente
        if deficit > 0:
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-ESTOQUE-PROVISIONAMENTO-01",
                    status="AVISO",
                    mensagem=(
                        f"{resource.resource_id}: {deficit:,.2f} provisionado externamente além da "
                        f"produção interna pareada — garanta a aquisição/logística correspondente."
                    ),
                )
            )
            # ADR-184 (continuação da ADR-151 D4): déficit sem preço declarado é
            # custeado como zero (transparente, não trava o cronograma) — torna
            # visível que o resultado financeiro está subestimando essa compra.
            if resource.disponibilidade.preco_provisionamento_externo is None:
                validacoes.append(
                    ValidacaoItem(
                        codigo="VAL-ESTOQUE-PROVISIONAMENTO-02",
                        status="AVISO",
                        mensagem=(
                            f"{resource.resource_id}: déficit provisionado externamente "
                            f"({deficit:,.2f}) sem preco_provisionamento_externo declarado — "
                            "custeado como R$ 0,00 no resultado financeiro. Informe o preço em "
                            "logistica_consumiveis para refletir o custo real da compra."
                        ),
                    )
                )
    return resources or None


def _merge_pool_deficits(explored: list) -> dict[str, int]:
    """ADR-128 F7 (issue #117): mescla `ScheduleOutput.pool_deficit` de todos os
    resultados explorados, tomando o pico máximo por recurso quando mais de um
    resultado reporta o mesmo recurso. Vazio quando nenhum resultado tem deficit
    (feasible=True, ou infeasible por motivo que não capacidade de pool)."""
    merged: dict[str, int] = {}
    for r in explored:
        for res, qty in (getattr(r.schedule, "pool_deficit", None) or {}).items():
            if qty > merged.get(res, 0):
                merged[res] = qty
    return merged


def _rasfc_report_estoque_delays(explored: list, validacoes: list) -> list:
    """ADR-128 F5: reporta causalmente atrasos por consumível e filtra resultados
    infeasible-por-estoque (``error == "estoque_insuficiente"``, ver
    ``selector._explore_cpsat``) para fora do fallback chain — só resultados sem
    erro seguem como candidatos. Feasible com atraso reparado vira AVISO
    (``VAL-ESTOQUE-DELAY-01``); infeasible por estoque vira ERRO
    (``VAL-ESTOQUE-DELAY-02``, bloqueia por ``gate=true``)."""
    kept = []
    for r in explored:
        delays = getattr(r.schedule, "estoque_delays", None)
        if not isinstance(delays, list):
            delays = []
        error = getattr(r, "error", None)
        if error == "estoque_insuficiente":
            causas = "; ".join(f"{d.resource_id}→{d.activity_id} (+{d.delay_weeks}sem)" for d in delays)
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-ESTOQUE-DELAY-02",
                    status="ERRO",
                    mensagem=f"Cronograma inviável após reparo de disponibilidade de consumíveis: {causas}.",
                )
            )
            continue
        if error is None and delays:
            causas = "; ".join(f"{d.resource_id}→{d.activity_id} (+{d.delay_weeks}sem)" for d in delays)
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-ESTOQUE-DELAY-01",
                    status="AVISO",
                    mensagem=f"Cronograma ajustado por disponibilidade de consumíveis: {causas}.",
                )
            )
        kept.append(r)
    return kept


def _rasfc_apply_algorithm_overrides(strategy: Any, inputs: dict) -> None:
    """Aplica overrides explícitos de ``inputs`` (``algorithm``/``heuristics``) sobre a
    estratégia inferida por ``select_scheduling_algorithm``."""
    if inputs.get("algorithm"):
        strategy.algorithm = str(inputs["algorithm"])
    if inputs.get("heuristics"):
        strategy.heuristics = list(inputs["heuristics"])


def _rasfc_disable_replenishable_if_incompatible(
    replenishable_resources: list[ReplenishableResource] | None,
    strategy: Any,
    validacoes: list,
) -> list[ReplenishableResource] | None:
    """ADR-128 F5: torna visível o caso "restrição declarada mas ignorada" em vez
    de um no-op silencioso — só o path CP-SAT (selector._explore_cpsat) aplica
    ReplenishableResource."""
    if replenishable_resources and strategy.algorithm != "CP-SAT":
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-ESTOQUE-ALGO-01",
                status="AVISO",
                mensagem=(
                    f"Restrição de estoque consumível não aplicada — algoritmo selecionado "
                    f"('{strategy.algorithm}') não suporta ADR-128. Force algorithm='CP-SAT' "
                    "para aplicar a restrição."
                ),
            )
        )
        return None
    return replenishable_resources


def _rasfc_retry_with_relaxed_pool(
    activities: list,
    dag: Any,
    pool: Any,
    deadline_weeks: int,
    heuristics: list,
    strategy: Any,
    replenishable_resources: list[ReplenishableResource] | None,
    pool_deficit: dict[str, int],
    validacoes: list,
) -> tuple[list, bool]:
    """Reexplora com pool relaxado quando o primeiro attempt não produziu nenhum
    candidato viável. ADR-128 F7: usa o pico real de demanda (``pool_deficit``) em
    vez do percentual cego de ``_relax_pool``. Retorna ``(explored, relaxed_flag)``."""
    relaxed_pool = _relax_pool(pool, deficit=pool_deficit)
    explored = explore_schedules(
        activities=activities,
        dag=dag,
        pool=relaxed_pool,
        deadline_weeks=deadline_weeks,
        heuristics=heuristics,
        top_n=3,
        strategy=strategy,
        replenishable_resources=replenishable_resources,
    )
    explored = _rasfc_report_estoque_delays(explored, validacoes)
    if not explored:
        return explored, False
    mensagem = (
        f"Pool ajustado ao pico real de demanda pós-reparo de estoque: {pool_deficit}."
        if pool_deficit
        else "Pool relaxado 110%."
    )
    validacoes.append(ValidacaoItem(codigo="VAL-SCHED-03", status="AVISO", mensagem=mensagem))
    return explored, True


def _rasfc_report_estoque_cap_violations(
    explored: list, replenishable_resources: list[ReplenishableResource] | None, validacoes: list
) -> None:
    """ADR-139/128: violation_estoque_acima_capacidade já existia mas nunca era
    chamada em produção — fecha essa lacuna junto (mesmo gatilho opt-in)."""
    if not (explored and replenishable_resources):
        return
    from concilium.application.scheduling.replenishable import violation_estoque_acima_capacidade

    top_schedule = explored[0].schedule
    for resource in replenishable_resources:
        v = violation_estoque_acima_capacidade(resource, top_schedule.scheduled_activities)
        if v is not None:
            validacoes.append(ValidacaoItem(codigo=v.code, status=v.status, mensagem=v.remediation_hint or ""))


def _rasfc_run_heuristics(
    activities: list,
    dag: Any,
    pool: Any,
    deadline_weeks: int,
    inputs: dict,
    validacoes: list,
    producoes_por_atividade: dict[str, Any] | None = None,
    insumos_lookup: dict | None = None,
    logistica_consumiveis: dict[str, Any] | None = None,
) -> tuple[list, bool, list[ReplenishableResource]]:
    """Runs heuristic scheduling with optional pool relaxation.

    Returns (candidates_canonical, relaxed_flag, replenishable_resources) — o 3º elemento
    (ADR-128 F6) é a lista de ReplenishableResource efetivamente aplicada (vazia quando
    nenhuma foi construída, ou quando VAL-ESTOQUE-ALGO-01 a descartou por incompatibilidade
    de algoritmo), usada por skill.py para persistir a contabilização canônica.
    """
    strategy = select_scheduling_algorithm(
        num_activities=len(activities),
        num_resource_types=max(1, len(pool.resources)),
        contract_duration_weeks=deadline_weeks,
        deadline_margin_pct=float(inputs.get("deadline_margin_pct", 0.2)),
        criticality=str(inputs.get("criticality", "medium")),
    )
    _rasfc_apply_algorithm_overrides(strategy, inputs)

    replenishable_resources = _build_replenishable_resources_if_any(
        producoes_por_atividade, insumos_lookup, logistica_consumiveis, validacoes
    )
    replenishable_resources = _rasfc_disable_replenishable_if_incompatible(
        replenishable_resources, strategy, validacoes
    )

    heuristics = strategy.heuristics or ["MINSLK"]
    first_attempt = explore_schedules(
        activities=activities,
        dag=dag,
        pool=pool,
        deadline_weeks=deadline_weeks,
        heuristics=heuristics,
        top_n=int(inputs.get("top_n", 3)),
        strategy=strategy,
        replenishable_resources=replenishable_resources,
    )
    # ADR-128 F7 (issue #117): captura o pico real de demanda por recurso ANTES do
    # filtro abaixo descartar o(s) resultado(s) infeasible — só assim o retry pode
    # usar o valor exato em vez do percentual cego de _relax_pool (que não cresce
    # nada para capacidades pequenas: int(4*1.1) == 4).
    pool_deficit = _merge_pool_deficits(first_attempt)
    explored = _rasfc_report_estoque_delays(first_attempt, validacoes)
    relaxed_flag = False

    if not explored:
        explored, relaxed_flag = _rasfc_retry_with_relaxed_pool(
            activities, dag, pool, deadline_weeks, heuristics, strategy, replenishable_resources, pool_deficit,
            validacoes,
        )

    _rasfc_report_estoque_cap_violations(explored, replenishable_resources, validacoes)

    return (
        [_to_canonical_candidate(r.heuristic, r.schedule, r.quality_score, relaxed_flag) for r in explored],
        relaxed_flag,
        replenishable_resources or [],
    )


__all__ = [
    "_aggregate_to_monthly",
    "_build_activity_item_map",
    "_build_replenishable_resources_if_any",
    "_can_extract_dag",
    "_emm_find_vazios",
    "_emm_process_item",
    "_execute_manual_mode",
    "_extract_taxa_desmobilizacao_fracao",
    "_find_item_by_id",
    "_infer_teams_from_resources",
    "_parse_logistica_consumiveis_overrides",
    "_producao_maxima_com_rampa_down",
    "_rasfc_enrich_from_catalog_if_available",
    "_rasfc_extract_from_canonical",
    "_rasfc_extract_from_spec",
    "_rasfc_extract_inputs",
    "_rasfc_propagate_pool_config",
    "_rasfc_report_estoque_delays",
    "_rasfc_report_pool_inferido_diag",
    "_rasfc_run_heuristics",
    "_validate_preconditions",
]
