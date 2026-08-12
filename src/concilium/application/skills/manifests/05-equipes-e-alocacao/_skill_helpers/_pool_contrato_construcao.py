"""Skill 05 — Equipes e Alocação (helpers A, parte extraída de _pool_contrato.py)."""

from __future__ import annotations

import math
from hashlib import sha1
from typing import Any

from concilium.domain.models.canonical import (
    CadeiaPerpetuacao,
    CanonicalModel,
    EquipeDireta,
    RecursoContrato,
)

from ._causal_cost_partition import particionar_contrato  # ty: ignore[unresolved-import]
from ._dimensionamento_itens import _accum_mob_costs_list  # ty: ignore[unresolved-import]
from ._perpetuation_chains import _build_perpetuation_chains  # ty: ignore[unresolved-import]
from ._pool_contrato_demanda import (  # ty: ignore[unresolved-import]
    _collect_tipo_items_and_demands,
    _compute_custo_unit_fracs,
    _compute_fracs_locacao_manut,
    _fill_atribuicao,
    _resolve_gap_max_e_idle_efetivo,
    _week_idx,
)


def _build_contrato_entry(
    tipo: str,
    items: list,
    week_demand: dict,
    pool: dict,
    mw_list: list,
    total_mw: float,
    custo_unit_semanal: float,
    cus_mo: float,
    cus_eq: float,
    cus_comb: float,
    cus_mat: float,
    cus_locacao: float,
    cus_manutencao: float,
    tipo_costs: dict,
    resource_costs: dict,
    atribuicao: dict,
    delta_max: int,
    todas_cadeias: list,
    equipe_map: dict,
    resource_costs_absent: bool = False,
    validacoes: list | None = None,
) -> RecursoContrato:
    """Constrói um RecursoContrato completo para o tipo dado."""
    all_weeks_sorted = sorted(week_demand.keys(), key=_week_idx)
    semana_inicio = all_weeks_sorted[0]
    semana_fim = all_weeks_sorted[-1]
    semanas_contrato = _week_idx(semana_fim) - _week_idx(semana_inicio) + 1
    peak_demand = max(week_demand.values())
    pool_cap = int(pool.get(tipo, peak_demand))
    quantidade_contratada = min(peak_demand, pool_cap)
    custo_total_contrato = quantidade_contratada * custo_unit_semanal * semanas_contrato
    c_mob = float(tipo_costs.get("custo_mob_unit", 0.0))
    c_demob = float(tipo_costs.get("custo_demob_unit", 0.0))
    c_idle = float(tipo_costs.get("custo_idle_semanal_unit", 0.0))
    c_idle, gap_max = _resolve_gap_max_e_idle_efetivo(
        c_mob, c_demob, c_idle, resource_costs_absent, cus_mo, cus_locacao
    )
    cadeias = _build_perpetuation_chains(
        tipo_id=tipo,
        items=items,
        custo_mob_unit=c_mob,
        custo_demob_unit=c_demob,
        custo_standby_unit=c_idle,
        delta_max=delta_max,
        gap_max=gap_max,
        validacoes=validacoes,
    )
    todas_cadeias.extend(cadeias)
    _fill_atribuicao(atribuicao, mw_list, custo_total_contrato, tipo)
    r_naive = sum(it["required"] for it in items)
    custo_mob_desmob = (
        round(len(cadeias) * (c_mob + c_demob) * quantidade_contratada, 2) if (c_mob + c_demob) > 0 else 0.0
    )
    return RecursoContrato(
        contrato_id=f"contrato-{tipo.lower().replace('-', '_')}",
        tipo_id=tipo,
        quantidade_contratada=quantidade_contratada,
        semana_inicio=semana_inicio,
        semana_fim=semana_fim,
        semanas_contrato=semanas_contrato,
        custo_unit_semanal=round(custo_unit_semanal, 4),
        custo_total_contrato=round(custo_total_contrato, 2),
        items_cobertos=[iid for iid, _, _ in mw_list],
        n_cadeias=len(cadeias),
        custo_mob_desmob_contrato=custo_mob_desmob,
        custo_standby_total=round(sum(c.custo_standby for c in cadeias), 2),
        r_naive=r_naive,
        custo_mob_unit=c_mob,
        custo_demob_unit=c_demob,
        custo_idle_semanal_unit=c_idle,
        unidade_faturamento=str(tipo_costs.get("unidade_faturamento", "hora_prod")),
        gap_max_economico=gap_max,
        custo_unit_semanal_mo=cus_mo,
        custo_unit_semanal_eq=cus_eq,
        custo_unit_semanal_comb=cus_comb,
        custo_unit_semanal_mat=cus_mat,
        rho_idle_eq=round(c_idle / cus_eq, 4) if cus_eq > 0 else 1.0,
        custo_unit_semanal_locacao=cus_locacao,
        custo_unit_semanal_manutencao=cus_manutencao,
        particao_por_item=particionar_contrato(
            items_com_janela=[{**it, "T_start": float(it["start_idx"]), "T_end": float(it["end_idx"])} for it in items],
            c_mob=c_mob,
            c_demob=c_demob,
            c_unit_semana=custo_unit_semanal,
            quantidade_contratada=quantidade_contratada,
            T_contrato_start=float(_week_idx(semana_inicio)),
            T_contrato_end=float(_week_idx(semana_fim) + 1),
            atribuicao=atribuicao,
            cadeias=cadeias,
        ),
    )


def _build_tipo_contrato(
    tipo: str,
    items: list,
    week_demand: dict,
    pool: dict,
    mw_list: list,
    total_mw: int,
    tipo_costs: dict,
    resource_costs: dict,
    equipe_map: dict,
    atribuicao: dict,
    delta_max: int,
    todas_cadeias: list,
    resource_costs_absent: bool = False,
    validacoes: list | None = None,
) -> RecursoContrato:
    """Builds one RecursoContrato entry from tipo/items data."""
    custo_unit_semanal, fmo, feq, fcomb, fmat = _compute_custo_unit_fracs(mw_list)
    cus_mo = round(custo_unit_semanal * fmo, 4)
    cus_eq = round(custo_unit_semanal * feq, 4)
    cus_comb = round(custo_unit_semanal * fcomb, 4)
    cus_mat = round(custo_unit_semanal * fmat, 4)
    cus_locacao, cus_manutencao = _compute_fracs_locacao_manut(mw_list, equipe_map, cus_eq)
    return _build_contrato_entry(
        tipo,
        items,
        week_demand,
        pool,
        mw_list,
        total_mw,
        custo_unit_semanal,
        cus_mo,
        cus_eq,
        cus_comb,
        cus_mat,
        cus_locacao,
        cus_manutencao,
        tipo_costs,
        resource_costs,
        atribuicao,
        delta_max,
        todas_cadeias,
        equipe_map,
        resource_costs_absent=resource_costs_absent,
        validacoes=validacoes,
    )


def _build_item_tipo_map(activities: list) -> dict:
    """Returns {item_id: {tipo: required}} from rcpsp activities."""
    item_tipo_map: dict[str, dict[str, int]] = {}
    for act in activities:
        iid = act.get("item_id")
        rr = act.get("required_resources", {})
        if iid and rr:
            item_tipo_map[iid] = {k: int(v) for k, v in rr.items()}
    return item_tipo_map


def _safe_str_val(v: Any) -> str:
    """Converte um valor potencialmente None/vazio em string limpa (sem espaços nas pontas)."""
    return str(v or "").strip()


def _safe_str_field(d: dict | None, key: str) -> str:
    """Lê `d[key]` com segurança contra `d`/valor None, retornando string limpa."""
    return _safe_str_val((d or {}).get(key))


def _positive_qty(d: dict | None, key: str, default: float = 1.0) -> float:
    """Lê uma quantidade numérica de `d[key]`, com fallback para `default` quando ausente/zero."""
    return round(float((d or {}).get(key, default) or default), 4)


def _tipo_recurso_fungivel(cpu_id: str, composicao: dict[str, Any]) -> str:
    """Deriva o tipo_id fungível de uma equipe a partir da assinatura da sua composição.

    CPUs iguais ou com mesma composição (funções + equipamentos + quantidades)
    compartilham recurso sem depender de regex sobre cpu_id.
    """
    equip = composicao.get("equipamentos") or []
    funcs = composicao.get("funcoes") or []
    # Invariante do único call site: composicao sempre tem ao menos um de
    # equipamentos/funcoes não-vazio antes de chegar aqui — guard "equip or funcs"
    # removido por ser sempre verdadeiro nesse ponto.
    tokens: list[str] = []
    for f in sorted(funcs, key=lambda x: _safe_str_field(x, "funcao_id")):
        fid = _safe_str_field(f, "funcao_id").upper()
        qtd = _positive_qty(f, "num_pessoas")
        if fid:
            tokens.append(f"F:{fid}:{qtd}")
    for e in sorted(equip, key=lambda x: _safe_str_field(x, "equip_id")):
        eid = _safe_str_field(e, "equip_id").upper()
        qtd = _positive_qty(e, "num_unidades")
        if eid:
            tokens.append(f"E:{eid}:{qtd}")
    if tokens:
        signature = "|".join(tokens)
        digest = sha1(signature.encode("utf-8")).hexdigest()[:12]
        return f"EQUIPE-COMP-{digest}"
    raw = _safe_str_val(cpu_id).upper()
    return f"EQUIPE-CPU-{raw}" if raw else "EQUIPE"


def _build_cpu_prod_lookups_rcpsp(catalogo: dict) -> tuple[dict, dict]:
    """Constrói os lookups de CPU e produção/produtividade a partir do catálogo."""
    cpu_lookup: dict = {c["codigo"]: c for c in catalogo.get("cpus", []) if c.get("codigo")}
    prod_lookup: dict = {
        p.get("id") or p.get("codigo", ""): p
        for p in (catalogo.get("producoes") or catalogo.get("produtividades") or [])
    }
    return cpu_lookup, prod_lookup


def _derive_item_tipo_requerido(
    item: Any, sa: Any, cpu_lookup: dict, prod_lookup: dict
) -> tuple[str, int, dict] | None:
    """Deriva (tipo_fungivel, required, composicao) para um item de EAP; None se sem composição válida.

    ADR-176 F4: `composicao` (o dict `composicao_padrao_equipe`) é retornado além de
    `tipo`/`required` para permitir ao chamador derivar o custo unitário de
    mob/demob do tipo (`_custo_mob_demob_unit_composicao`) sem repetir a mesma
    cadeia de lookup cpu→produção→composição.
    """
    cpu = cpu_lookup.get(item.cpu_id, {})
    prod_id = cpu.get("producao_id_ref")
    prod = prod_lookup.get(prod_id or "", {})
    equipe = prod.get("composicao_padrao_equipe", {}) if prod else {}
    if not (equipe.get("equipamentos") or equipe.get("funcoes")):
        return None
    dist = getattr(sa, "distribuicao_semanal", None) or {}
    required = max((int(math.ceil(float(getattr(d, "num_equipes", 0) or 0.0))) for d in dist.values()), default=1)
    required = max(1, required)
    tipo = _tipo_recurso_fungivel(str(item.cpu_id or ""), equipe)
    return tipo, required, equipe


def _custo_mob_demob_unit_composicao(composicao: dict) -> tuple[float, float]:
    """ADR-176 F4: custo de mobilização/desmobilização de UMA unidade do tipo de
    recurso fungível, a partir dos mesmos campos `custo_mobilizacao`/
    `custo_desmobilizacao` por função/equipamento embutidos na composição
    (`composicao_padrao_equipe`) — mesmo dado de catálogo já consumido pelo custo
    direto (`_calc_custo_mob_desmob_split`, skill-05) e pelo indireto de projeto
    (`_accum_mob_costs_list`, skill-06). Reaproveita `_accum_mob_costs_list`
    (mesma fórmula, zero divergência) em vez de reimplementar a soma.
    """
    c_mob_fn, c_demob_fn = _accum_mob_costs_list(composicao.get("funcoes") or [], "num_pessoas")
    c_mob_eq, c_demob_eq = _accum_mob_costs_list(composicao.get("equipamentos") or [], "num_unidades")
    return round(c_mob_fn + c_mob_eq, 2), round(c_demob_fn + c_demob_eq, 2)


def _collect_item_tipo_ids_and_pool_caps(
    eap_items: Any, sched_lookup: dict, cpu_lookup: dict, prod_lookup: dict
) -> tuple[dict[str, tuple[str, int]], dict[str, int], dict[str, tuple[float, float]]]:
    """Percorre a EAP e coleta (tipo, required) por item, a capacidade de pool por
    tipo, e o custo unitário de mob/demob por tipo (ADR-176 F4)."""
    sched_ids = set(sched_lookup)
    item_tipo_ids: dict[str, tuple[str, int]] = {}
    pool_caps: dict[str, int] = {}
    tipo_mob_demob: dict[str, tuple[float, float]] = {}

    for item in eap_items:
        if item.item_id not in sched_ids:
            continue
        # sched_ids == set(sched_lookup) (definido acima), logo a checagem de
        # pertinência já garante que a chave existe — sem necessidade de guard.
        sa = sched_lookup[item.item_id]
        resultado = _derive_item_tipo_requerido(item, sa, cpu_lookup, prod_lookup)
        if resultado is None:
            continue
        tipo, required, equipe = resultado
        item_tipo_ids[item.item_id] = (tipo, required)
        pool_caps[tipo] = max(pool_caps.get(tipo, 0), required)
        if tipo not in tipo_mob_demob:
            tipo_mob_demob[tipo] = _custo_mob_demob_unit_composicao(equipe)

    return item_tipo_ids, pool_caps, tipo_mob_demob


def _derive_rcpsp_from_canonical(canonical_in: CanonicalModel, catalogo: dict) -> dict | None:
    """Deriva rcpsp_spec a partir do canônico quando não fornecido nos inputs.

    Convenção de tipo_id: família fungível da equipe, derivada da assinatura da
    composição padrão (funções + equipamentos + quantidades). Assim, CPUs iguais
    ou com mesma composição compartilham recurso sem depender de regex sobre cpu_id.

    custo_unit_semanal é sempre derivado bottom-up (custo_total_item / machine_weeks,
    ver _compute_custo_unit_fracs) — resource_costs aqui só carrega
    custo_mob_unit/custo_demob_unit por tipo (ADR-176 F4), nunca custo_unit_semanal.

    resource_costs[tipo]["custo_mob_unit"/"custo_demob_unit"] (ADR-176 F4, D4):
    somados dos mesmos campos custo_mobilizacao/custo_desmobilizacao por função/
    equipamento embutidos na composição do tipo — mesma fonte já usada pelo custo
    direto (EquipeDireta, skill-05) e pelo indireto de projeto (skill-06). Antes
    desta ADR, resource_costs era omitido propositalmente e
    RecursoContrato.custo_mob_unit/custo_demob_unit ficavam sempre 0.0 quando o
    rcpsp_spec era auto-derivado (ADR-137 P1) — a decisão de perpetuação (ADR-073)
    rodava sempre em modo heurístico de tempo, nunca econômico. Nenhum tipo ganha
    custo_idle_semanal_unit aqui — o fallback ADR-085 (`cus_mo + cus_locacao`)
    continua se aplicando normalmente (ver `_setup_contratos_context`).

    Capacidades declaradas explicitamente em canonical_in.recurso_pool (skill 03) são
    respeitadas quando o tipo_id coincide com o equip_id (convenção natural).

    Retorna None quando não há cronograma ou EAP suficientes para derivar o spec.
    """
    sched_acts = canonical_in.cronograma.scheduled_activities if canonical_in.cronograma else []
    if not sched_acts:
        return None

    eap_items = canonical_in.eap
    if not eap_items:
        return None

    sched_lookup = {sa.activity_id: sa for sa in sched_acts}
    cpu_lookup, prod_lookup = _build_cpu_prod_lookups_rcpsp(catalogo)

    item_tipo_ids, pool_caps, tipo_mob_demob = _collect_item_tipo_ids_and_pool_caps(
        eap_items, sched_lookup, cpu_lookup, prod_lookup
    )

    if not pool_caps:
        return None

    resource_pool = dict(pool_caps)
    # item_tipo_ids e pool_caps são preenchidos na mesma iteração do loop acima
    # (nunca um sem o outro), logo pool_caps não-vazio garante item_tipo_ids
    # não-vazio — `activities` abaixo nunca fica vazio quando chegamos aqui.
    activities = [
        {
            "item_id": iid,
            "required_resources": {tipo: required},
        }
        for iid, (tipo, required) in item_tipo_ids.items()
    ]
    resource_costs = {
        tipo: {"custo_mob_unit": c_mob, "custo_demob_unit": c_demob}
        for tipo, (c_mob, c_demob) in tipo_mob_demob.items()
        if c_mob > 0 or c_demob > 0
    }

    result: dict[str, Any] = {"resource_pool": resource_pool, "activities": activities}
    if resource_costs:
        result["resource_costs"] = resource_costs
    return result


def _setup_contratos_context(equipes: list, rcpsp_spec: dict) -> tuple:
    """Extracts pool/activities/item_tipo_map/equipe_map/delta_max/resource_costs from rcpsp_spec."""
    pool = rcpsp_spec.get("resource_pool", {})
    activities = rcpsp_spec.get("activities", [])
    if not pool and activities:
        from concilium.application.scheduling import inferir_pool_minimo_from_spec

        pool, _diag = inferir_pool_minimo_from_spec(rcpsp_spec)
        rcpsp_spec["resource_pool"] = dict(pool)
    item_tipo_map = _build_item_tipo_map(activities)
    equipe_map: dict[str, EquipeDireta] = {eq.item_id: eq for eq in equipes}
    delta_max = int(rcpsp_spec.get("delta_perpetuacao_semanas", 2))
    _raw = rcpsp_spec.get("resource_costs", {})
    resource_costs: dict = _raw if isinstance(_raw, dict) else {}
    # Três casos, não dois (ADR-176 F4 estende o contrato original):
    # 1. Chave "resource_costs" ausente do spec → catálogo sem custos explícitos,
    #    usa fallback (True) — comportamento original, preservado.
    # 2. "resource_costs": {} presente explicitamente (vazio) → sentinela de
    #    retrocompatibilidade ADR-071: desliga o fallback de propósito, mantém o
    #    contrato monolítico (False) — comportamento original, preservado.
    # 3. "resource_costs" presente e não-vazio (ADR-176 F4): `_derive_rcpsp_from_canonical`
    #    pode popular só custo_mob_unit/custo_demob_unit reais do catálogo, sem
    #    custo_idle_semanal_unit — nesse caso o fallback de idle (ADR-085,
    #    `cus_mo + cus_locacao`) ainda deve engajar; só desliga quando pelo menos um
    #    tipo tiver custo_idle_semanal_unit explícito.
    if "resource_costs" not in rcpsp_spec:
        resource_costs_absent = True
    elif not resource_costs:
        resource_costs_absent = False
    else:
        resource_costs_absent = not any(
            isinstance(v, dict) and "custo_idle_semanal_unit" in v for v in resource_costs.values()
        )
    return pool, activities, item_tipo_map, equipe_map, delta_max, resource_costs, resource_costs_absent


def _build_contratos_por_tipo(
    tipo_items: dict,
    tipo_week_demand: dict,
    pool: dict,
    resource_costs: dict,
    equipe_map: dict,
    atribuicao: dict,
    delta_max: int,
    todas_cadeias: list,
    resource_costs_absent: bool,
    validacoes: list | None = None,
) -> list[RecursoContrato]:
    """Constrói um RecursoContrato por tipo de pool com machine-weeks > 0."""
    contratos: list[RecursoContrato] = []
    for tipo, items in tipo_items.items():
        # tipo_items[tipo] e tipo_week_demand[tipo] são sempre populados juntos
        # em _add_tipo_item_demand (mesmo active_weeks não-vazio), logo um tipo
        # presente em tipo_items nunca tem week_demand vazio aqui.
        week_demand = tipo_week_demand[tipo]
        mw_list: list[tuple[str, int, dict]] = [(it["item_id"], it["machine_weeks"], it) for it in items]
        total_mw = sum(mw for _, mw, _ in mw_list)
        if total_mw == 0:
            continue
        tipo_costs = resource_costs.get(tipo, {})
        if not isinstance(tipo_costs, dict):
            tipo_costs = {}
        contratos.append(
            _build_tipo_contrato(
                tipo,
                items,
                week_demand,
                pool,
                mw_list,
                total_mw,
                tipo_costs,
                resource_costs,
                equipe_map,
                atribuicao,
                delta_max,
                todas_cadeias,
                resource_costs_absent=resource_costs_absent,
                validacoes=validacoes,
            )
        )
    return contratos


def _accumulate_atribuicao_total(contratos: list[RecursoContrato]) -> dict[str, tuple[float, str, float]]:
    """TD-1: acumula atribuição total por item sobre todos os contratos.

    _fill_atribuicao sobrescreve por contrato (correto para particao_por_item).
    Aqui somamos as contribuições de cada contrato para cada item.
    """
    atribuicao_total: dict[str, tuple[float, str, float]] = {}
    for contrato in contratos:
        for part in contrato.particao_por_item:
            iid = part.item_id
            custo_part = float(getattr(part, "custo_total_particionado", 0.0) or 0.0)
            prev_custo, prev_tipo, prev_frac = atribuicao_total.get(iid, (0.0, contrato.tipo_id, 0.0))
            novo_tipo = contrato.tipo_id if custo_part >= prev_custo else prev_tipo
            atribuicao_total[iid] = (
                round(prev_custo + custo_part, 2),
                novo_tipo,
                round(prev_frac, 6),
            )
    return atribuicao_total


def _build_contratos_recurso(
    equipes: list[EquipeDireta],
    rcpsp_spec: dict,
    sched_lookup: dict,
    validacoes: list,
) -> tuple[list[RecursoContrato], dict[str, tuple[float, str, float]], list[CadeiaPerpetuacao]]:
    """Calcula contratos de pool e retorna (contratos, atribuicao_por_item, cadeias).

    ADR-071: O custo real do contrato de um tipo de recurso é:

        peak_demand × custo_unit_semanal × semanas_contrato

    onde peak_demand = max demanda simultânea observada no cronograma RCPSP
    (≤ pool_size, que é o limite superior de capacidade).

    O custo por item é uma atribuição proporcional ao uso (machine-weeks):

        custo_item = custo_contrato × (R_i × active_weeks_i) / total_machine_weeks

    Parâmetros
    ----------
    equipes       : lista de EquipeDireta com custo_total já calculado (passo anterior)
    rcpsp_spec    : dict com 'resource_pool' e 'activities[].required_resources'
    sched_lookup  : {activity_id: ScheduledActivity} do cronograma RCPSP
    validacoes    : lista acumulada de validações (append de INFOs/AVISOs)

    Retorna
    -------
    contratos    : list[RecursoContrato] — um por tipo de pool com atividades ativas
    atribuicao   : {item_id: (custo_atribuido, tipo_id, fracao)} — por item coberto
    cadeias      : list[CadeiaPerpetuacao] — cadeias de perpetuação ADR-073
    """
    pool, activities, item_tipo_map, equipe_map, delta_max, resource_costs, resource_costs_absent = (
        _setup_contratos_context(equipes, rcpsp_spec)
    )
    if not pool or not activities:
        return [], {}, []

    tipo_items, tipo_week_demand = _collect_tipo_items_and_demands(
        item_tipo_map,
        equipe_map,
        pool,
        sched_lookup,
        validacoes,
    )

    atribuicao: dict[str, tuple[float, str, float]] = {}
    todas_cadeias: list[CadeiaPerpetuacao] = []

    contratos = _build_contratos_por_tipo(
        tipo_items,
        tipo_week_demand,
        pool,
        resource_costs,
        equipe_map,
        atribuicao,
        delta_max,
        todas_cadeias,
        resource_costs_absent,
        validacoes=validacoes,
    )

    atribuicao_total = _accumulate_atribuicao_total(contratos)

    return contratos, atribuicao_total, todas_cadeias


