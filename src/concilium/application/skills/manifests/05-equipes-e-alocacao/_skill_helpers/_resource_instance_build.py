"""Skill 05 — Equipes e Alocação (helpers A, parte extraída de _resource_instance_utilization.py)."""

from __future__ import annotations

from collections.abc import Mapping

from concilium.application.scheduling.contractual_cost_ledger import ContractCategory, book_exact_pool
from concilium.application.scheduling.resource_demand_levels import normalize_weekly_resource_demand
from concilium.application.scheduling.resource_level_contracts import (
    ResourceTariff,
    exact_money,
    optimize_homogeneous_pool,
)
from concilium.domain.models.canonical import (
    ComposicaoEquipeAtividade,
    InstanciaRecurso,
    RecursoContrato,
    ResumoUtilizacaoContrato,
)
from concilium.domain.services.planning.week_sequence import enumerar_semanas

from ._pool_contrato_demanda import _week_idx  # ty: ignore[unresolved-import]
from ._resource_instance_assignment import (  # ty: ignore[unresolved-import]
    _STANDBY_THRESHOLD_PCT,
    _assign_instances,
    _build_week_demand_maps,
    _collect_items_data_for_tipo,
    _compress_to_segments,
    _compute_desmob_antecipada,
    _compute_instancia_lifecycle,
    _emit_standby_validation,
)


def _build_resumo_e_validacoes(
    tipo_id: str,
    contrato,
    n: int,
    instance_active: dict,
    instance_standby: dict,
    custo_standby_rate: float,
    validacoes: list,
) -> ResumoUtilizacaoContrato:
    """Build ResumoUtilizacaoContrato and emit standby validations."""
    mw_disponiveis = n * contrato.semanas_contrato
    mw_usados = sum(instance_active.values())
    mw_standby = sum(instance_standby.values())
    taxa_geral = round(mw_usados / mw_disponiveis * 100, 1) if mw_disponiveis > 0 else 100.0
    custo_standby_total = round(custo_standby_rate * mw_standby, 2)
    instancias_standby_alto = [
        f"{tipo_id}-{i:02d}"
        for i in range(1, n + 1)
        if (instance_active[i] + instance_standby[i]) > 0
        and instance_standby[i] / (instance_active[i] + instance_standby[i]) * 100 > _STANDBY_THRESHOLD_PCT
    ]
    if taxa_geral >= 65.0:
        status_util = "OK"
    elif taxa_geral >= 35.0:
        status_util = "AVISO"
    else:
        status_util = "CRITICO"
    resumo = ResumoUtilizacaoContrato(
        contrato_id=contrato.contrato_id,
        tipo_id=tipo_id,
        quantidade_contratada=n,
        semanas_contrato=contrato.semanas_contrato,
        machine_weeks_disponiveis=mw_disponiveis,
        machine_weeks_usados=mw_usados,
        machine_weeks_standby=mw_standby,
        taxa_utilizacao_pct=taxa_geral,
        custo_standby_total=custo_standby_total,
        instancias_standby_alto=instancias_standby_alto,
        status_utilizacao=status_util,
    )
    _emit_standby_validation(
        tipo_id,
        instancias_standby_alto,
        instance_active,
        instance_standby,
        n,
        taxa_geral,
        custo_standby_total,
        status_util,
        validacoes,
    )
    return resumo


def _build_instancia_slot(
    i: int,
    tipo_id: str,
    contrato,
    instance_active: dict,
    instance_standby: dict,
    instance_activities: dict,
    instance_last_active_week: dict,
    instance_week_map: dict,
    custo_standby_rate: float,
    c_idle_unit: float,
    apply_idle_gaps: bool,
    contract_start_idx: int,
    contract_end_idx: int,
    _c_mo: float,
    _c_eq: float,
    _c_comb: float,
    _c_mat: float,
    _c_mob_unit: float,
    _c_demob_unit: float,
    mobilizacao_por_instancia: dict,
) -> InstanciaRecurso:
    """Builds one InstanciaRecurso for slot i."""
    s_ativas = instance_active[i]
    s_standby = instance_standby[i]
    total_w = s_ativas + s_standby
    taxa = round(s_ativas / total_w * 100, 1) if total_w > 0 else 100.0
    custo_sb = round(custo_standby_rate * s_standby, 2)
    ultima_atividade = instance_last_active_week[i]
    semanas_antecipacao, economia_desmob = _compute_desmob_antecipada(
        ultima_atividade, c_idle_unit, contrato.custo_demob_unit, contract_end_idx
    )
    (
        sm_mob,
        sm_demob,
        semanas_off,
        ca_mo,
        ca_eq,
        ca_comb,
        ca_mat,
        ci_mo,
        ci_eq,
        c_mob_i,
        c_demob_i,
        desmob_aplicada,
        custo_inst_total,
        _idle_segs,
    ) = _compute_instancia_lifecycle(
        i,
        instance_week_map,
        contrato,
        contract_start_idx,
        contract_end_idx,
        apply_idle_gaps,
        _c_mo,
        _c_eq,
        _c_comb,
        _c_mat,
        c_idle_unit,
        _c_mob_unit,
        _c_demob_unit,
        s_ativas,
        mobilizacao_por_instancia,
    )
    return InstanciaRecurso(
        instancia_id=f"{tipo_id}-{i:02d}",
        contrato_id=contrato.contrato_id,
        tipo_id=tipo_id,
        numero=i,
        semana_entrada=contrato.semana_inicio,
        semana_saida=contrato.semana_fim,
        semanas_ativas=s_ativas,
        semanas_standby=s_standby,
        taxa_utilizacao_pct=taxa,
        custo_standby=custo_sb,
        atividades_cobertas=sorted(instance_activities[i]),
        semana_ultima_atividade=ultima_atividade,
        semanas_antecipacao_possivel=semanas_antecipacao,
        economia_desmobilizacao_antecipada=economia_desmob,
        desmob_antecipada_aplicada=desmob_aplicada,
        segmentos_atividade=_compress_to_segments(instance_week_map[i]),
        semana_mobilizacao=sm_mob,
        semana_desmobilizacao=sm_demob,
        semanas_off=semanas_off,
        custo_ativo_mo=ca_mo,
        custo_ativo_eq=ca_eq,
        custo_ativo_comb=ca_comb,
        custo_ativo_mat=ca_mat,
        custo_idle_mo=ci_mo,
        custo_idle_eq=ci_eq,
        custo_mob_instancia=c_mob_i,
        custo_demob_instancia=c_demob_i,
        custo_instancia_total=custo_inst_total,
        segmentos_idle=_idle_segs,
    )


def _build_composicao_entry(
    item: dict, tipo_id: str, contrato, n: int, instance_activities: dict
) -> ComposicaoEquipeAtividade:
    """Builds ComposicaoEquipeAtividade for a single item."""
    iid = item["item_id"]
    inst_nums = sorted(i for i in range(1, n + 1) if iid in instance_activities[i])
    return ComposicaoEquipeAtividade(
        activity_id=iid,
        tipo_id=tipo_id,
        contrato_id=contrato.contrato_id,
        pool_size=n,
        n_instancias=len(inst_nums),
        required=item["required"],
        instancias_numeros=inst_nums,
        semana_inicio=item["active_weeks"][0] if item["active_weeks"] else "",
        semana_fim=item["active_weeks"][-1] if item["active_weeks"] else "",
        machine_weeks=item["machine_weeks"],
    )


def _fraction_text(value) -> str:
    """Stable textual representation of an exact rational amount."""
    return str(value)


def _build_p16_global_assignment_witness(
    tipo_id: str,
    contrato: RecursoContrato,
    items_data: list[dict],
    tariff_spec: Mapping[str, object],
) -> dict[str, object]:
    """Persist an exact P16-E witness using Skill 05's verified physical tensor.

    The witness is conditional on fixed demand. It does not rewrite legacy
    monetary projections or certify project-wide GO.
    """
    if not isinstance(tariff_spec, Mapping):
        raise ValueError(f"P16-E {tipo_id}: exact tariff must be a mapping")

    source_id, currency, category = (
        tariff_spec.get("source_id"),
        tariff_spec.get("currency"),
        tariff_spec.get("category"),
    )
    if not isinstance(source_id, str) or not source_id.strip():
        raise ValueError(f"P16-E {tipo_id}: tariff source_id is required")
    if (
        not isinstance(currency, str)
        or len(currency) != 3
        or not currency.isalpha()
        or currency != currency.upper()
    ):
        raise ValueError(f"P16-E {tipo_id}: currency must be an explicit uppercase three-letter code")
    if not isinstance(category, str) or category not in {"MO", "EQ"}:
        raise ValueError(f"P16-E {tipo_id}: homogeneous resource category must be MO or EQ")
    # The membership check above narrows this to the ContractCategory literal union.

    rates: dict[str, str] = {}
    for name in ("active_week", "idle_week", "mobilize", "demobilize"):
        raw_rate = tariff_spec.get(name)
        if not isinstance(raw_rate, str):
            raise ValueError(f"P16-E {tipo_id}: {name} must be an exact decimal string")
        rates[name] = raw_rate

    declared_max_gap = tariff_spec.get("max_idle_gap")
    if type(declared_max_gap) is not int or declared_max_gap < 0:
        raise ValueError(f"P16-E {tipo_id}: max_idle_gap must be a nonnegative integer")
    gap_viavel = tariff_spec.get("gap_max_viavel")
    if type(gap_viavel) is not int or gap_viavel < 0:
        raise ValueError(f"P16-E {tipo_id}: gap_max_viavel must be a nonnegative integer")
    economic_gap_limit = getattr(contrato, "gap_max_economico", None)
    effective_max_gap = min(declared_max_gap, gap_viavel)
    tariff = ResourceTariff(
        active_week=exact_money(rates["active_week"]),
        idle_week=exact_money(rates["idle_week"]),
        mobilize=exact_money(rates["mobilize"]),
        demobilize=exact_money(rates["demobilize"]),
        max_idle_gap=effective_max_gap,
    )

    weeks = tuple(enumerar_semanas(contrato.semana_inicio, contrato.semana_fim))
    if not weeks or len(weeks) != contrato.semanas_contrato:
        raise ValueError(f"P16-E {tipo_id}: contract calendar is not a complete contiguous week span")

    demand_by_item = getattr(contrato, "demanda_por_item_semanal", None)
    fronts_by_item = getattr(contrato, "frentes_por_item_semanal", None)
    aggregate_demand = getattr(contrato, "demanda_fisica_semanal", None)
    if not isinstance(demand_by_item, dict) or not demand_by_item:
        raise ValueError(f"P16-E {tipo_id}: typed per-activity physical demand is required")
    if not isinstance(fronts_by_item, dict) or not fronts_by_item:
        raise ValueError(f"P16-E {tipo_id}: source mobilization m_i,j is required")
    if not isinstance(aggregate_demand, dict):
        raise ValueError(f"P16-E {tipo_id}: aggregate weekly physical demand is required")

    item_ids = {item["item_id"] for item in items_data}
    if item_ids != set(demand_by_item) or item_ids != set(fronts_by_item):
        raise ValueError(f"P16-E {tipo_id}: activity coverage differs from persisted demand/mobilization")

    by_activity: dict[str, dict[str, tuple[int, ...]]] = {}
    series_by_item: dict[str, tuple[int, ...]] = {}
    for item in sorted(items_data, key=lambda entry: entry["item_id"]):
        item_id = item["item_id"]
        observed = item.get("demand_per_week")
        persisted = demand_by_item[item_id]
        fronts = fronts_by_item[item_id]
        if not isinstance(observed, dict) or not isinstance(persisted, dict) or not isinstance(fronts, dict):
            raise ValueError(f"P16-E {tipo_id}/{item_id}: invalid physical provenance mapping")
        if set(observed) - set(weeks):
            raise ValueError(f"P16-E {tipo_id}/{item_id}: demand falls outside the contract calendar")
        observed_positive = {w: q for w, q in observed.items() if q > 0}
        persisted_positive = {w: q for w, q in persisted.items() if q > 0}
        if observed_positive != persisted_positive:
            raise ValueError(f"P16-E {tipo_id}/{item_id}: demand disagrees with persisted physical schedule")
        if set(fronts) != set(observed_positive):
            raise ValueError(f"P16-E {tipo_id}/{item_id}: mobilization provenance does not cover active demand weeks")
        if any(type(value) is not int or value < 0 for value in fronts.values()):
            raise ValueError(f"P16-E {tipo_id}/{item_id}: mobilization counts must be nonnegative integers")
        series = tuple(observed.get(week, 0) for week in weeks)
        if any(type(value) is not int or value < 0 for value in series):
            raise ValueError(f"P16-E {tipo_id}/{item_id}: demand must be nonnegative integer counts")
        series_by_item[item_id] = series
        by_activity[item_id] = {tipo_id: series}

    if set(aggregate_demand) - set(weeks):
        raise ValueError(f"P16-E {tipo_id}: aggregate demand falls outside the contract calendar")
    expected = tuple(aggregate_demand.get(week, 0) for week in weeks)
    if any(type(value) is not int or value < 0 for value in expected):
        raise ValueError(f"P16-E {tipo_id}: aggregate demand must be nonnegative integer counts")

    normalized = normalize_weekly_resource_demand(weeks, by_activity)
    actual = dict(normalized.demand_by_type).get(tipo_id)
    if actual is None or actual != expected:
        raise ValueError(f"P16-E {tipo_id}: d_gj != sum_i a_i,g(m_ij): {actual!r} != {expected!r}")
    if max(actual, default=0) > contrato.quantidade_contratada:
        raise ValueError(f"P16-E {tipo_id}: demand exceeds contracted instance count")

    pool = optimize_homogeneous_pool(normalized, {tipo_id: tariff})
    physical = next((entry for entry in pool.ledgers if entry.resource_type == tipo_id), None)
    if physical is None:
        raise ValueError(f"P16-E {tipo_id}: optimizer returned no resource ledger")
    booked = book_exact_pool(pool, {tipo_id: tariff}, {tipo_id: category})

    assignments: dict[int, dict[int, str]] = {chain.level: {} for chain in physical.chains}
    for index, week in enumerate(weeks):
        events = [
            item_id
            for item_id, series in sorted(series_by_item.items())
            for _ in range(series[index])
        ]
        active_chains = sorted(
            (chain for chain in physical.chains if index in chain.active_week_indices),
            key=lambda chain: chain.level,
        )
        if len(active_chains) != len(events):
            raise ValueError(f"P16-E {tipo_id}/{week}: paths do not reconstruct per-activity demand")
        for chain, item_id in zip(active_chains, events, strict=True):
            assignments[chain.level][index] = item_id

    chains = []
    for chain in sorted(physical.chains, key=lambda entry: entry.level):
        assigned = assignments[chain.level]
        chains.append({
            "instance_id": chain.level,
            "start_index": chain.start,
            "end_exclusive_index": chain.end,
            "start_week": weeks[chain.start],
            "end_week": weeks[chain.end - 1],
            "active_week_indices": list(chain.active_week_indices),
            "active_weeks": chain.active_weeks,
            "idle_weeks": chain.idle_weeks,
            "active_weeks_iso": [weeks[index] for index in chain.active_week_indices],
            "activity_by_week": {weeks[index]: item_id for index, item_id in sorted(assigned.items())},
        })
    postings = [{
        "event_id": list(post.event_id),
        "nature": post.nature.value,
        "category": post.category,
        "amount": _fraction_text(post.amount),
        "source": post.source,
        "week": post.week,
    } for post in booked.postings]

    return {
        "schema": "p16-global-instance-assignment/v1",
        "proof_scope": pool.proof_scope,
        "status": "EXACT_CONDITIONAL_ON_FIXED_PHYSICAL_DEMAND",
        "is_project_go_certificate": False,
        "legacy_financial_projection_overridden": False,
        "resource_type": tipo_id,
        "contract_id": contrato.contrato_id,
        "source_id": source_id,
        "currency": currency,
        "category": category,
        "tariff": {
            **rates,
            "max_idle_gap_declared": declared_max_gap,
            "gap_max_viavel": gap_viavel,
            "gap_max_economico_legado": economic_gap_limit,
            "max_idle_gap_effective": effective_max_gap,
        },
        "calendar_weeks": list(weeks),
        "demand_by_activity": {item_id: list(series) for item_id, series in sorted(series_by_item.items())},
        "demand": list(physical.demand),
        "presence": list(physical.presence),
        "standby": list(physical.standby),
        "chains": chains,
        "costs": {
            "active": _fraction_text(physical.active_cost),
            "standby": _fraction_text(physical.standby_cost),
            "mobility": _fraction_text(physical.mobility_cost),
            "pool_total": _fraction_text(pool.total),
        },
        "exclusive_ledger": {
            "contractual_k": _fraction_text(booked.contractual_k),
            "consumable_v": _fraction_text(booked.consumable_v),
            "indirect": _fraction_text(booked.indirect),
            "direct": _fraction_text(booked.direct),
            "total": _fraction_text(booked.total),
            "postings": postings,
        },
    }


def _build_instancias_for_tipo(
    tipo_id: str, contrato, item_tipo_required: dict, item_total_peak: dict, sched_lookup: dict, validacoes: list,
    p16_tariff_spec: dict | None = None,
) -> tuple:
    """Builds instancias/composicoes/resumo for a single tipo_id contrato."""
    n = contrato.quantidade_contratada
    contrato.p16_global_assignment = None
    if n <= 0:
        return [], [], []
    # Lightweight legacy contracts may predate these optional provenance fields.
    # Absence is explicitly unverified, never silently treated as certified.
    exact = getattr(contrato, "demanda_por_item_semanal", None) or None
    front_provenance = getattr(contrato, "frentes_por_item_semanal", None) or None
    contract_label = getattr(contrato, "contrato_id", tipo_id)
    if exact is not None and front_provenance is None:
        from concilium.domain.models.canonical import ValidacaoItem

        validacoes.append(
            ValidacaoItem(
                codigo="VAL-POOL-FRENTES-LEGADO",
                status="AVISO",
                mensagem=(
                    f"Contrato {contract_label}: tensor de demanda sem prova da mobilização "
                    "m_i,j que o gerou; paridade temporal NÃO CERTIFICADA."
                ),
            )
        )
    if exact is None:
        from concilium.domain.models.canonical import ValidacaoItem

        validacoes.append(
            ValidacaoItem(
                codigo="VAL-POOL-DEMANDA-LEGADO",
                status="AVISO",
                mensagem=(
                    f"Contrato {contract_label}: instâncias sem tensor físico "
                    "a_i,g(m_ij) verificável; uso legado NÃO CERTIFICADO."
                ),
            )
        )
    items_data = _collect_items_data_for_tipo(
        tipo_id, item_tipo_required, item_total_peak, sched_lookup,
        demand_by_item=exact,
        fronts_by_item=front_provenance if exact is not None else None,
    )
    if exact is not None:
        rebuilt, _ = _build_week_demand_maps(items_data)
        expected = {w: d for w, d in contrato.demanda_fisica_semanal.items() if d > 0}
        if rebuilt != expected:
            raise ValueError(
                f"VAL-POOL-DEMANDA-02: contract {contrato.contrato_id} physical "
                f"weekly demand disagrees with instance inputs: {rebuilt} != {expected}"
            )
    if p16_tariff_spec is not None:
        if not items_data:
            raise ValueError(f"P16-E {tipo_id}: exact tariff declared without active physical demand")
        contrato.p16_global_assignment = _build_p16_global_assignment_witness(
            tipo_id, contrato, items_data, p16_tariff_spec,
        )
    if not items_data:
        return [], [], []

    (
        instance_active,
        instance_standby,
        instance_activities,
        instance_last_active_week,
        instance_week_map,
        _all_weeks_sorted,
    ) = _assign_instances(items_data, n, contrato.semanas_contrato)
    c_idle_unit = contrato.custo_idle_semanal_unit
    custo_standby_rate = c_idle_unit if c_idle_unit > 0 else contrato.custo_unit_semanal
    contract_end_idx = _week_idx(contrato.semana_fim)
    apply_idle_gaps = c_idle_unit > 0
    contract_start_idx = _week_idx(contrato.semana_inicio)
    _c_mo = contrato.custo_unit_semanal_mo
    _c_eq = contrato.custo_unit_semanal_eq
    _c_comb = contrato.custo_unit_semanal_comb
    _c_mat = contrato.custo_unit_semanal_mat
    _c_mob_unit = contrato.custo_mob_unit
    _c_demob_unit = contrato.custo_demob_unit
    mobilizacao_por_instancia: dict[int, str] = {}

    instancias = [
        _build_instancia_slot(
            i,
            tipo_id,
            contrato,
            instance_active,
            instance_standby,
            instance_activities,
            instance_last_active_week,
            instance_week_map,
            custo_standby_rate,
            c_idle_unit,
            apply_idle_gaps,
            contract_start_idx,
            contract_end_idx,
            _c_mo,
            _c_eq,
            _c_comb,
            _c_mat,
            _c_mob_unit,
            _c_demob_unit,
            mobilizacao_por_instancia,
        )
        for i in range(1, n + 1)
    ]

    if mobilizacao_por_instancia:
        contrato.mobilizacao_por_instancia = dict(sorted(mobilizacao_por_instancia.items()))

    composicoes = [_build_composicao_entry(item, tipo_id, contrato, n, instance_activities) for item in items_data]

    resumo = _build_resumo_e_validacoes(
        tipo_id, contrato, n, instance_active, instance_standby, custo_standby_rate, validacoes
    )
    return instancias, composicoes, [resumo]


def _build_item_resource_maps(activities: list) -> tuple:
    """Returns (item_tipo_required, item_total_peak) from activities list."""
    item_tipo_required: dict[str, dict[str, int]] = {}
    item_total_peak: dict[str, int] = {}
    for act in activities:
        iid = act.get("item_id")
        rr = act.get("required_resources", {})
        if iid and rr:
            item_tipo_required[iid] = {k: int(v) for k, v in rr.items()}
            item_total_peak[iid] = sum(int(v) for v in rr.values()) or 1
    return item_tipo_required, item_total_peak


def _build_instancias_recurso(
    contratos: list[RecursoContrato],
    rcpsp_spec: dict,
    sched_lookup: dict,
    validacoes: list,
) -> tuple[list[InstanciaRecurso], list[ComposicaoEquipeAtividade], list[ResumoUtilizacaoContrato]]:
    """ADR-077: Constrói o mapa instancial de utilização de recursos.

    Para cada contrato de pool (tipo_id), cria N instâncias numeradas e rastreia
    seu ciclo de vida (ATIVO vs. STANDBY) baseado na demanda do cronograma RCPSP.

    Algoritmo de atribuição (guloso por prioridade):
    - Em cada semana, atividades são ordenadas por machine_weeks decrescentes.
    - Os slots de menor número são atribuídos às atividades de maior prioridade.
    - Slots restantes (além da demanda total) ficam STANDBY.

    Parâmetros
    ----------
    contratos    : contratos de pool já calculados por _build_contratos_recurso
    rcpsp_spec   : dict com 'resource_pool' e 'activities[].required_resources'
    sched_lookup : {activity_id: ScheduledActivityCanonical}
    validacoes   : lista acumulada — recebe VAL-SLOT-STANDBY-ALTO

    Retorna
    -------
    (instancias, composicoes, resumos) — um por slot, por atividade×tipo, por contrato
    """
    activities = rcpsp_spec.get("activities", [])
    raw_p16_tariffs = rcpsp_spec.get("p16_exact_tariffs")
    if raw_p16_tariffs is not None and not isinstance(raw_p16_tariffs, dict):
        raise ValueError("P16-E p16_exact_tariffs must be a resource-type mapping")
    p16_tariffs = raw_p16_tariffs or {}
    if any(not isinstance(resource, str) or not resource for resource in p16_tariffs):
        raise ValueError("P16-E tariff resource identifiers must be nonempty strings")

    contract_types = [contract.tipo_id for contract in contratos]
    contrato_map = {contract.tipo_id: contract for contract in contratos}
    unknown_p16_types = set(p16_tariffs) - set(contrato_map)
    if unknown_p16_types:
        raise ValueError(f"P16-E tariffs reference resources without a physical contract: {sorted(unknown_p16_types)}")
    duplicate_p16_types = set(p16_tariffs).intersection(
        tipo_id for tipo_id in contract_types if contract_types.count(tipo_id) > 1
    )
    if duplicate_p16_types:
        raise ValueError(
            f"P16-E requires one homogeneous contract per tariffed resource type: {sorted(duplicate_p16_types)}"
        )
    if p16_tariffs and not activities:
        raise ValueError("P16-E tariffs require an explicit nonempty activity schedule")
    if not contratos or not activities:
        return [], [], []

    item_tipo_required, item_total_peak = _build_item_resource_maps(activities)
    all_instancias: list[InstanciaRecurso] = []
    all_composicoes: list[ComposicaoEquipeAtividade] = []
    all_resumos: list[ResumoUtilizacaoContrato] = []
    validation_count_before_p16 = len(validacoes)
    previous_contract_state = [
        (
            contrato,
            contrato.p16_global_assignment,
            dict(contrato.mobilizacao_por_instancia),
        )
        for contrato in contrato_map.values()
    ]

    try:
        for tipo_id, contrato in contrato_map.items():
            insts, comps, resumos = _build_instancias_for_tipo(
                tipo_id, contrato, item_tipo_required, item_total_peak, sched_lookup, validacoes,
                p16_tariff_spec=p16_tariffs.get(tipo_id),
            )
            all_instancias.extend(insts)
            all_composicoes.extend(comps)
            all_resumos.extend(resumos)
    except Exception:
        # A multi-type P16 call is atomic: failure of one resource must not
        # persist a partial global witness or lifecycle projection for another.
        for contrato, prior_witness, prior_mobilizations in previous_contract_state:
            contrato.p16_global_assignment = prior_witness
            contrato.mobilizacao_por_instancia = prior_mobilizations
        del validacoes[validation_count_before_p16:]
        raise

    return all_instancias, all_composicoes, all_resumos


