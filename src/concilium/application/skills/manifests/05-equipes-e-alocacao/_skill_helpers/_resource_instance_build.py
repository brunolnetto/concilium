"""Skill 05 — Equipes e Alocação (helpers A, parte extraída de _resource_instance_utilization.py)."""

from __future__ import annotations

from concilium.domain.models.canonical import (
    ComposicaoEquipeAtividade,
    InstanciaRecurso,
    RecursoContrato,
    ResumoUtilizacaoContrato,
)

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


def _build_instancias_for_tipo(
    tipo_id: str, contrato, item_tipo_required: dict, item_total_peak: dict, sched_lookup: dict, validacoes: list
) -> tuple:
    """Builds instancias/composicoes/resumo for a single tipo_id contrato."""
    n = contrato.quantidade_contratada
    if n <= 0:
        return [], [], []
    exact = contrato.demanda_por_item_semanal or None
    if exact is None:
        from concilium.domain.models.canonical import ValidacaoItem

        validacoes.append(
            ValidacaoItem(
                codigo="VAL-POOL-DEMANDA-LEGADO",
                status="AVISO",
                mensagem=(
                    f"Contrato {contrato.contrato_id}: instâncias sem tensor físico "
                    "a_i,g(m_ij) verificável; uso legado NÃO CERTIFICADO."
                ),
            )
        )
    items_data = _collect_items_data_for_tipo(
        tipo_id, item_tipo_required, item_total_peak, sched_lookup,
        demand_by_item=exact,
    )
    if exact is not None:
        rebuilt, _ = _build_week_demand_maps(items_data)
        expected = {w: d for w, d in contrato.demanda_fisica_semanal.items() if d > 0}
        if rebuilt != expected:
            raise ValueError(
                f"VAL-POOL-DEMANDA-02: contract {contrato.contrato_id} physical "
                f"weekly demand disagrees with instance inputs: {rebuilt} != {expected}"
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
    if not contratos or not activities:
        return [], [], []

    item_tipo_required, item_total_peak = _build_item_resource_maps(activities)

    contrato_map = {c.tipo_id: c for c in contratos}
    all_instancias: list[InstanciaRecurso] = []
    all_composicoes: list[ComposicaoEquipeAtividade] = []
    all_resumos: list[ResumoUtilizacaoContrato] = []

    for tipo_id, contrato in contrato_map.items():
        insts, comps, resumos = _build_instancias_for_tipo(
            tipo_id, contrato, item_tipo_required, item_total_peak, sched_lookup, validacoes
        )
        all_instancias.extend(insts)
        all_composicoes.extend(comps)
        all_resumos.extend(resumos)

    return all_instancias, all_composicoes, all_resumos


