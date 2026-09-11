"""Skill 04 — Cronograma (parte extraída de skill.py)."""

from __future__ import annotations

import math
from hashlib import sha1
from typing import Any

from concilium.application.scheduling import (
    Activity,
    ActivityDAG,
    ResourcePool,
)
from concilium.domain.models.canonical import (
    CanonicalModel,
    EstoqueDelayCanonical,
    ScheduleCandidateCanonical,
    ScheduledActivityCanonical,
    ValidacaoItem,
)

from ._calendario import _compute_productive_weeks, _compute_ramp_profile  # ty: ignore[unresolved-import]


def _funcao_tokens_composicao(funcs: list) -> list[str]:
    """Tokens F:<funcao_id>:<qtd> ordenados, para a assinatura de composição."""
    tokens: list[str] = []
    for f in sorted(funcs, key=lambda x: str(x.get("funcao_id") or "")):
        fid = str(f.get("funcao_id") or "").strip().upper()
        qtd = round(float(f.get("num_pessoas", 1) or 1), 4)
        if fid:
            tokens.append(f"F:{fid}:{qtd}")
    return tokens


def _equipamento_tokens_composicao(equip: list) -> list[str]:
    """Tokens E:<equip_id>:<qtd> ordenados, para a assinatura de composição."""
    tokens: list[str] = []
    for e in sorted(equip, key=lambda x: str(x.get("equip_id") or "")):
        eid = str(e.get("equip_id") or "").strip().upper()
        qtd = round(float(e.get("num_unidades", 1) or 1), 4)
        if eid:
            tokens.append(f"E:{eid}:{qtd}")
    return tokens


def _tipo_recurso_fungivel(cpu_id: str, composicao: dict[str, Any]) -> str:
    """Deriva tipo fungível por assinatura de composição (não por regex de CPU id)."""
    # O único call site (_enrich_activity_resources_from_catalog) já garante
    # `comp.get("equipamentos") or comp.get("funcoes")` truthy antes de chamar
    # esta função, então `equip`/`funcs` nunca são ambos vazios aqui.
    tokens = _funcao_tokens_composicao(composicao.get("funcoes") or [])
    tokens += _equipamento_tokens_composicao(composicao.get("equipamentos") or [])
    if tokens:
        signature = "|".join(tokens)
        digest = sha1(signature.encode("utf-8")).hexdigest()[:12]
        return f"EQUIPE-COMP-{digest}"
    raw = str(cpu_id or "").strip().upper()
    return f"EQUIPE-CPU-{raw}" if raw else "EQUIPE"


def _dimensionar_frentes_atividade(
    a: dict, Q: float, P: float, horas_semana: float, deadline_weeks: int
) -> tuple[int, int]:
    """Dimensiona (n_frentes, duration) de uma atividade (ADR-072 + ADR-091).

    dur_1frente = ceil(Q / (P × horas_semana))
    n_frentes   = n_max de ramp_params, ou o mínimo para caber no prazo
    duration    = ceil(dur_1frente / n_frentes)
    """
    dur_1frente = max(1, math.ceil(Q / (P * horas_semana)))
    # Usa n_max de ramp_params quando disponível (plano do projetista).
    # Sem n_max, infere o mínimo de frentes para caber no prazo.
    rp_pre = a.get("ramp_params") or {}
    n_max_spec = int(rp_pre.get("n_max") or 0)
    n_frentes = n_max_spec if n_max_spec > 0 else max(1, math.ceil(dur_1frente / deadline_weeks))

    # Busca formal de N_i quando há perfil de rampa explícito:
    # Q <= P * horas_semana * Σ_j(n_j), com n_j = n_frentes * ramp_profile[j].
    if isinstance(rp_pre, dict) and n_max_spec > 0 and P > 0 and horas_semana > 0:
        duration_min = max(1, math.ceil(dur_1frente / n_frentes))
        duration_max = max(duration_min, deadline_weeks * 2, duration_min * 4)
        for n_i in range(duration_min, duration_max + 1):
            profile = _compute_ramp_profile(n_i, rp_pre, n_frentes)
            soma_frentes_equivalentes = float(sum(profile)) * n_frentes
            capacidade = P * horas_semana * soma_frentes_equivalentes
            if capacidade >= Q:
                return n_frentes, n_i

    duration = max(1, math.ceil(dur_1frente / n_frentes))
    return n_frentes, duration


def _resolve_producao_do_item(item: Any, cpu_lookup: dict, producao_lookup: dict) -> tuple[float, dict] | None:
    """Resolve (Q, producao) via CPU do item, ou None se CPU/producao ausentes/inválidos."""
    Q = float(getattr(item, "quantitativo", 0) or 0)
    cpu = cpu_lookup.get(getattr(item, "cpu_id", "") or "")
    if not cpu or Q <= 0:
        return None
    prod = producao_lookup.get(cpu.get("producao_id_ref") or "")
    if not prod:
        return None
    return Q, prod


def _build_producoes_por_atividade(eap_items: list, cpu_lookup: dict, producao_lookup: dict) -> dict[str, Any]:
    """Pareamento atividade→Producao (ADR-139 D5) para build_replenishable_resources.

    Reaproveita ``_resolve_producao_do_item`` — o mesmo pareamento CPU→Producao já
    usado para dimensionar n_frentes/duration, aqui reexposto por atividade em vez
    de descartado após o cálculo (ADR-128 F5)."""
    result: dict[str, Any] = {}
    for item in eap_items:
        resolved = _resolve_producao_do_item(item, cpu_lookup, producao_lookup)
        if resolved is None:
            continue
        _q, prod = resolved
        result[item.item_id] = prod
    return result


def _composicao_tem_recursos(comp: dict) -> bool:
    """True se a composição declara ao menos um equipamento ou função (pool-relevante)."""
    # Granularidade do pool: UMA equipe-tipo por CPU. Equipes da mesma CPU são
    # fungíveis (compartilham o pool). A composicao_padrao_equipe (funções +
    # equipamentos) alimenta o breakdown de custo da equipe (skill-05), não
    # dimensões separadas de pool — evita double-counting do custo do item por
    # tipo de recurso. required_resources = nº de frentes paralelas.
    return bool(comp.get("equipamentos") or comp.get("funcoes"))


def _resolve_producao_context_atividade(
    item: Any, cpu_lookup: dict, producao_lookup: dict
) -> tuple[float, dict, float] | None:
    """Resolve (Q, comp, P) da produção associada ao item via catálogo, ou None se
    algum elo da cadeia (CPU→producao→composicao_padrao_equipe) faltar/for inválido."""
    resolved = _resolve_producao_do_item(item, cpu_lookup, producao_lookup)
    if resolved is None:
        return None
    Q, prod = resolved
    P = float(prod.get("producao_horaria") or 0)
    comp = prod.get("composicao_padrao_equipe") or {}
    if P <= 0 or not comp or not _composicao_tem_recursos(comp):
        return None
    return Q, comp, P


def _apply_activity_resource_enrichment(a: dict, tipo: str, n_frentes: int, duration: int) -> None:
    """Grava required_resources/duration/ramp_profile computados na atividade."""
    a["required_resources"] = {tipo: n_frentes}
    a["duration_weeks"] = duration
    a["n_frentes"] = n_frentes
    a["_catalog_resources"] = True

    # ramp_params com duration final → propagado via ramp_lookup em _build_scheduled_activities
    rp = a.get("ramp_params")
    if isinstance(rp, dict) and rp.get("n_max", 0) > 0:
        a["ramp_profile_computed"] = _compute_ramp_profile(duration, rp, int(rp["n_max"]))


def _enrich_activity_resources_from_catalog(
    a: dict, item: Any, cpu_lookup: dict, producao_lookup: dict, horas_semana: float, deadline_weeks: int
) -> bool:
    """Enriquece uma atividade da spec com required_resources/duration a partir do
    catálogo (CPU→producao→composicao_padrao_equipe). Retorna True se enriquecida."""
    ctx = _resolve_producao_context_atividade(item, cpu_lookup, producao_lookup)
    if ctx is None:
        return False
    Q, comp, P = ctx

    n_frentes, duration = _dimensionar_frentes_atividade(a, Q, P, horas_semana, deadline_weeks)
    tipo = _tipo_recurso_fungivel(str(item.cpu_id or ""), comp)
    _apply_activity_resource_enrichment(a, tipo, n_frentes, duration)
    return True


def _resolve_horas_semana_enriquecimento(
    spec: dict, canonical_in: CanonicalModel, activities: list, deadline_weeks: int
) -> float | None:
    """Retorna horas_semana quando o enriquecimento por catálogo é elegível, ou None
    quando a spec já tem resource_pool/required_resources explícitos, não tem
    atividades, ou o regime de trabalho/deadline é inválido."""
    if not activities:
        return None
    # Não sobrescreve required_resources/resource_pool quando já explícitos
    if spec.get("resource_pool") or any(a.get("required_resources") for a in activities):
        return None
    regime = canonical_in.projeto.regime_trabalho
    horas_semana = regime.horas_dia * regime.dias_semana
    if horas_semana <= 0 or deadline_weeks <= 0:
        return None
    return horas_semana


def _enrich_spec_resources_from_catalog(
    spec: dict,
    canonical_in: CanonicalModel,
    cpu_lookup: dict,
    producao_lookup: dict,
    deadline_weeks: int,
    validacoes: list,
) -> None:
    """Constrói required_resources + resource_pool + duração a partir do catálogo.

    Modelo (pool renovável fungível): a composicao_padrao_equipe da PRODUÇÃO
    (CPU.producao_id_ref → producao) é a receita de UMA frente. Cada equip_id e
    funcao_id é um tipo de recurso renovável; a atividade consome
    ``composição × n_frentes`` enquanto ativa e libera ao terminar.

    Só atua quando a spec não traz required_resources/resource_pool explícitos
    (preserva specs explícitas). Grava de volta em ``spec`` para que
    _extract_activities_from_spec e _extract_pool_from_spec consumam.
    """
    activities = spec.get("activities") or []
    horas_semana = _resolve_horas_semana_enriquecimento(spec, canonical_in, activities, deadline_weeks)
    if horas_semana is None:
        return

    eap_by_id = {item.item_id: item for item in (canonical_in.eap or [])}
    enriquecidas = 0

    for a in activities:
        item = eap_by_id.get(a.get("item_id"))
        if item is None:
            continue
        if _enrich_activity_resources_from_catalog(a, item, cpu_lookup, producao_lookup, horas_semana, deadline_weeks):
            enriquecidas += 1

    if enriquecidas:
        # resource_pool deixado para inferir_pool_minimo_from_spec (pico concorrente,
        # não soma) via _extract_pool_from_spec — evita super-provisionar contratos.
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-CRON-CATALOGO-RES",
                status="OK",
                mensagem=(
                    f"rcpsp_spec enriquecido do catálogo: {enriquecidas} atividades "
                    f"com required_resources (composicao_padrao_equipe)."
                ),
            )
        )


def _resolve_spec_activity_productive_weeks(
    a: dict,
    window_w: int,
    use_productive: bool,
    canonical_in: CanonicalModel | None,
    cpu_lookup: dict | None,
    producao_lookup: dict | None,
    validacoes: list | None,
) -> int:
    """Resolve a duração produtiva de uma atividade da spec (ADR-072)."""
    if a.get("_catalog_resources"):
        # Duração já dimensionada por _enrich_spec_resources_from_catalog
        # (productive com n_frentes). Usar direto — sem recompute.
        return window_w
    if not use_productive:
        return window_w  # fallback: sem alteração

    # use_productive == True garante (ver call site) que os três são não-None.
    assert canonical_in is not None
    assert cpu_lookup is not None
    assert producao_lookup is not None

    n_res = max(1, sum(a.get("required_resources", {}).values()))
    computed = _compute_productive_weeks(
        a["item_id"],
        n_res,
        canonical_in,
        cpu_lookup,
        producao_lookup,
        validacoes or [],
    )
    if computed is not None and computed < window_w:
        return computed
    return window_w  # fallback


def _resolve_spec_activity_ramp_profile(a: dict, productive_w: int) -> list[float] | None:
    """Resolve o ramp_profile de uma atividade da spec (ADR-074), com prioridade ao pré-computado."""
    # ADR-074: derive ramp_profile from ramp_params if present.
    # Prioridade: ramp_profile_computed (calculado no _enrich com duration final).
    # Fallback: calcular com productive_w (specs sem enriquecimento de catálogo).
    ramp_profile: list[float] | None = a.get("ramp_profile_computed") or None
    if ramp_profile is None:
        ramp_params = a.get("ramp_params")
        if ramp_params and isinstance(ramp_params, dict) and productive_w > 0:
            n_pico = int(ramp_params.get("n_max") or 1)
            if n_pico > 0:
                ramp_profile = _compute_ramp_profile(productive_w, ramp_params, n_pico)
    return ramp_profile


def _resolve_eap_item_for_activity_id(activity_id: str, canonical_in: CanonicalModel):
    """Traduz `activity_id` (o id usado no RCPSP) para o `EapItem` correspondente.

    ADR-181 F2: `activity_id` é `EapItem.item_id` direto no modo AUTO (RCPSP
    auto-derivado — mesmo caso que `_compute_productive_weeks` já cobre), mas pode
    ser `Atividade.atividade_id` (UUID) no modo MANUAL, quando `rcpsp_spec` é
    fornecido com atividades explícitas — mesma ambiguidade item_id↔atividade_id
    documentada em `_validacao._build_activity_item_map` (issue #125/#142).
    Replicada localmente (em vez de importada) porque `_validacao.py` já importa
    de `_spec.py` — importar de volta criaria ciclo.
    """
    eap_item = next((e for e in canonical_in.eap if e.item_id == activity_id), None)
    if eap_item is not None:
        return eap_item
    for act in getattr(canonical_in, "atividades", None) or []:
        if act.atividade_id == activity_id:
            return next((e for e in canonical_in.eap if e.item_id == act.eap_item_id), None)
    return None


def _resolve_spec_activity_readiness_weeks(a: dict, canonical_in: CanonicalModel | None) -> int:
    """ADR-181 F1/F2: resolve `readiness_weeks` (aquisição + mobilização física) do
    `EapItem` correspondente à entrada de spec — cobre tanto o modo AUTO (`a["item_id"]`
    == `EapItem.item_id`) quanto o modo MANUAL (`a["item_id"]` == `Atividade.atividade_id`,
    UUID explícito).

    Sem `canonical_in` (spec bare, sem enriquecimento) ou sem override no item,
    retorna 0 — backward compat, nenhuma constraint nova.
    """
    if canonical_in is None:
        return 0
    eap_item = _resolve_eap_item_for_activity_id(a["item_id"], canonical_in)
    if eap_item is None:
        return 0
    # getattr defensivo: alguns testes usam fakes/mocks de EapItem sem todos os
    # campos (mesmo padrão de _compute_productive_weeks em _calendario.py).
    aquisicao = getattr(eap_item, "leadtime_aquisicao_semanas", None) or 0
    mob = getattr(eap_item, "leadtime_mob_semanas", None) or 0
    return aquisicao + mob


def _build_activity_from_spec_entry(
    a: dict,
    use_productive: bool,
    canonical_in: CanonicalModel | None,
    cpu_lookup: dict | None,
    producao_lookup: dict | None,
    validacoes: list | None,
) -> Activity:
    """Constrói uma Activity a partir de uma entrada de rcpsp_spec['activities']."""
    window_w = int(a["duration_weeks"])
    productive_w = _resolve_spec_activity_productive_weeks(
        a, window_w, use_productive, canonical_in, cpu_lookup, producao_lookup, validacoes
    )

    ramp_profile = _resolve_spec_activity_ramp_profile(a, productive_w)
    readiness_weeks = _resolve_spec_activity_readiness_weeks(a, canonical_in)
    # Limpar campo temporário para não poluir o dict serializado
    a.pop("ramp_profile_computed", None)

    return Activity(
        activity_id=a["item_id"],
        description=a.get("descricao", a["item_id"]),
        duration_weeks=productive_w,
        required_resources=dict(a.get("required_resources", {})),
        window_weeks=window_w if productive_w < window_w else None,
        ramp_profile=ramp_profile,
        ramp_params=dict(a["ramp_params"]) if isinstance(a.get("ramp_params"), dict) else None,
        readiness_weeks=readiness_weeks,
    )


def _extract_activities_from_spec(
    spec: dict,
    canonical_in: CanonicalModel | None = None,
    cpu_lookup: dict | None = None,
    producao_lookup: dict | None = None,
    validacoes: list | None = None,
) -> list[Activity]:
    """Extrai atividades a partir de rcpsp_spec (ADR-046, ADR-072, ADR-074).

    Quando ``canonical_in``, ``cpu_lookup`` e ``producao_lookup`` são
    fornecidos, aplica Direção A (ADR-072): substitui ``duration_weeks`` pela
    duração produtiva calculada a partir de Q / taxa de produção, mantendo a
    janela original em ``window_weeks`` para restrição de corredor.

    ADR-074: Quando ``ramp_params`` presente na atividade da spec, deriva
    ``ramp_profile`` normalizado (lista de floats [0,1] com length = duration_weeks).
    O ramp é aplicado após a redução de duração para a duração produtiva.
    """
    use_productive = canonical_in is not None and cpu_lookup is not None and producao_lookup is not None
    return [
        _build_activity_from_spec_entry(a, use_productive, canonical_in, cpu_lookup, producao_lookup, validacoes)
        for a in spec["activities"]
    ]


def _extract_pool_from_spec(spec: dict, canonical_in: CanonicalModel | None = None) -> ResourcePool:
    """Extrai (ou infere) o pool de recursos a partir de rcpsp_spec.

    ADR-046: pool explícito é usado como está.
    ADR-091: quando ``resource_pool`` está ausente/vazio, o pool é *derivado* do
    problema (atividades + precedência + objetivo de negócio em ``pool_config``).
    Atividades sem ``required_resources`` na spec têm ``e_{i,r}`` derivado de
    ``EquipeDireta.equipamentos`` (Fase 1). O pool inferido é gravado de volta em
    ``spec['resource_pool']`` — assim skill-05 e a persistência enxergam o mesmo
    pool — e o diagnóstico do tradeoff tempo×custo fica em ``spec['pool_inferido_diag']``.
    """
    explicit = spec.get("resource_pool") or {}
    if explicit:
        return ResourcePool(resources={k: int(v) for k, v in explicit.items()})

    from concilium.application.scheduling import inferir_pool_minimo_from_spec

    equipes = list(getattr(canonical_in, "equipes_diretas", []) or []) if canonical_in else None
    pool, diag = inferir_pool_minimo_from_spec(spec, equipes=equipes)
    spec["resource_pool"] = dict(pool)
    spec["pool_inferido_diag"] = diag
    return ResourcePool(resources={k: int(v) for k, v in pool.items()})


def _extract_dag_from_spec(
    spec: dict,
    activities: list[Activity],
    eap_items: list | None = None,
) -> ActivityDAG:
    """ADR-081: Extrai DAG de precedência do rcpsp_spec e/ou da EAP.

    Fontes (por prioridade):
    1. eap[].predecessores  — fonte canônica, inclui completion_threshold_pct
    2. rcpsp_spec.precedence — override/suplemento (para par já na EAP, prevalece)

    Formato suportado para rcpsp_spec.precedence:
      - [pred_id, succ_id]            → θ=1.0 (FS clássico)
      - [pred_id, succ_id, theta]     → θ=float fornecido
    """
    from ._dag import extract_dag_from_spec_or_eap  # ty: ignore[unresolved-import]

    return extract_dag_from_spec_or_eap(spec, activities, eap_items)


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
                ramp_profile=a.ramp_profile,  # ADR-074: propagate for distribuicao_semanal
                ramp_params=a.ramp_params,
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
        estoque_delays=[
            EstoqueDelayCanonical(resource_id=d.resource_id, activity_id=d.activity_id, delay_weeks=d.delay_weeks)
            for d in getattr(schedule_output, "estoque_delays", None) or []
        ],
    )


__all__ = [
    "_apply_activity_resource_enrichment",
    "_build_activity_from_spec_entry",
    "_build_producoes_por_atividade",
    "_composicao_tem_recursos",
    "_dimensionar_frentes_atividade",
    "_enrich_activity_resources_from_catalog",
    "_enrich_spec_resources_from_catalog",
    "_equipamento_tokens_composicao",
    "_extract_activities_from_spec",
    "_extract_dag_from_spec",
    "_extract_pool_from_spec",
    "_funcao_tokens_composicao",
    "_resolve_horas_semana_enriquecimento",
    "_resolve_producao_context_atividade",
    "_resolve_producao_do_item",
    "_resolve_spec_activity_productive_weeks",
    "_resolve_spec_activity_ramp_profile",
    "_tipo_recurso_fungivel",
    "_to_canonical_candidate",
]
