"""Skill 05 — Equipes e Alocação (helpers A, parte extraída de _resource_instance_utilization.py)."""

from __future__ import annotations

from concilium.domain.models.canonical import (
    SegmentoAtividade,
    ValidacaoItem,
)
from concilium.domain.services.financial.equipe_custo_engine import LifecycleEngine
from concilium.domain.services.planning.week_sequence import enumerar_semanas

from ._pool_contrato_demanda import _week_idx  # ty: ignore[unresolved-import]

_STANDBY_THRESHOLD_PCT = 35.0


def _compress_to_segments(week_map: dict) -> list:
    """Comprime {semana: activity_id} em segmentos contínuos por atividade — ADR-083."""
    if not week_map:
        return []
    sorted_w = sorted(week_map.keys(), key=_week_idx)
    segs: list[SegmentoAtividade] = []
    cur_act = week_map[sorted_w[0]]
    cur_start = sorted_w[0]
    cur_end = sorted_w[0]
    count = 1
    for w in sorted_w[1:]:
        act = week_map[w]
        if act == cur_act:
            cur_end = w
            count += 1
        else:
            segs.append(
                SegmentoAtividade(activity_id=cur_act, semana_inicio=cur_start, semana_fim=cur_end, machine_weeks=count)
            )
            cur_act = act
            cur_start = w
            cur_end = w
            count = 1
    segs.append(
        SegmentoAtividade(activity_id=cur_act, semana_inicio=cur_start, semana_fim=cur_end, machine_weeks=count)
    )
    return segs


def _compute_instancia_idle_gaps(
    aw: list,
    contract_start_idx: int,
    contract_end_idx: int,
    c_mo: float,
    c_idle_unit: float,
    c_mob_unit: float,
    c_demob_unit: float,
) -> tuple:
    """Compute idle/off weeks and idle segments for ADR-085 per-instance lifecycle.

    Returns (idle_w, semanas_off, desmob_aplicada, idle_segs, sm_mob, sm_demob)
    """
    mob_idx = _week_idx(aw[0])
    last_idx = _week_idx(aw[-1])
    idle_week_cost = c_mo + c_idle_unit
    remob_cost = c_mob_unit + c_demob_unit
    idle_w = 0
    off_internal = 0
    idle_segs: list[SegmentoAtividade] = []
    for k in range(1, len(aw)):
        gap = _week_idx(aw[k]) - _week_idx(aw[k - 1]) - 1
        if gap <= 0:
            continue
        if idle_week_cost * gap <= remob_cost:
            idle_w += gap
            # gap > 0 (checado acima) garante que enumerar_semanas(...)[1:-1] tenha
            # exatamente `gap` elementos — nunca vazio para chaves de semana bem
            # formadas e no mesmo formato (invariante do cronograma canônico).
            between = enumerar_semanas(aw[k - 1], aw[k])[1:-1]
            idle_segs.append(
                SegmentoAtividade(
                    activity_id="__idle__",
                    semana_inicio=between[0],
                    semana_fim=between[-1],
                    machine_weeks=len(between),
                )
            )
        else:
            off_internal += gap
    leading_off = max(0, mob_idx - contract_start_idx)
    trailing_off = max(0, contract_end_idx - last_idx)
    semanas_off = leading_off + trailing_off + off_internal
    desmob_aplicada = trailing_off > 0
    return idle_w, semanas_off, desmob_aplicada, idle_segs


def _compute_instancia_lifecycle(
    i: int,
    instance_week_map: dict,
    contrato,
    contract_start_idx: int,
    contract_end_idx: int,
    apply_idle_gaps: bool,
    c_mo: float,
    c_eq: float,
    c_comb: float,
    c_mat: float,
    c_idle_unit: float,
    c_mob_unit: float,
    c_demob_unit: float,
    prod_w: int,
    mobilizacao_por_instancia: dict,
) -> tuple:
    """Compute ADR-085/ADR-136 lifecycle fields for one slot. Returns lifecycle tuple."""
    sm_mob = sm_demob = ""
    semanas_off = 0
    ca_mo = ca_eq = ca_comb = ca_mat = ci_mo = ci_eq = c_mob_i = c_demob_i = custo_inst_total = 0.0
    desmob_aplicada = False
    idle_segs: list[SegmentoAtividade] = []
    if not (apply_idle_gaps and instance_week_map[i]):
        return (
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
            idle_segs,
        )
    aw = sorted(instance_week_map[i].keys(), key=_week_idx)
    idle_w, semanas_off, desmob_aplicada, idle_segs = _compute_instancia_idle_gaps(
        aw, contract_start_idx, contract_end_idx, c_mo, c_idle_unit, c_mob_unit, c_demob_unit
    )
    # ADR-136 F3: mobilização é evento de entrada — sempre incorrida para uma instância
    # de fato utilizada (chegamos aqui só quando instance_week_map[i] é não-vazio).
    # Demobilização é "efetiva" (custo à parte) apenas quando a desmob antecipada foi
    # aplicada (ADR-085 D3 / ADR-080 §C); caso contrário, fica embutida no contrato.
    # ADR-136 F5: fórmula de custo delegada ao LifecycleEngine (ADR-106), consolidando
    # com o mesmo motor usado por DirectTeamCostStrategy/IndirectTeamCostStrategy —
    # c_demob_efetivo do skill-05 mapeia para o parâmetro homônimo do engine (é sempre
    # condicional, nunca o "c_demob normal" que o engine trata como evento incondicional).
    c_mob_efetivo = c_mob_unit
    c_demob_efetivo = c_demob_unit if desmob_aplicada else 0.0
    dec = LifecycleEngine().calcular(
        prod_weeks=prod_w,
        idle_weeks=idle_w,
        c_mo=c_mo,
        c_eq=c_eq,
        c_comb=c_comb,
        c_mat=c_mat,
        c_idle_eq=c_idle_unit,
        c_mob=c_mob_efetivo,
        c_demob_efetivo=c_demob_efetivo,
    )
    ca_mo, ca_eq, ca_comb, ca_mat = dec.ativo_mo, dec.ativo_eq, dec.ativo_comb, dec.ativo_mat
    ci_mo, ci_eq = dec.idle_mo, dec.idle_eq
    c_mob_i, c_demob_i = dec.mob, dec.demob
    custo_inst_total = dec.total
    sm_mob = aw[0]
    sm_demob = aw[-1] if desmob_aplicada else contrato.semana_fim
    mobilizacao_por_instancia[i] = sm_mob
    return (
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
        idle_segs,
    )


def _compute_desmob_antecipada(
    ultima_atividade: str, c_idle_unit: float, custo_demob_unit: float, contract_end_idx: int
) -> tuple:
    """Returns (semanas_antecipacao, economia_desmob) for ADR-079B."""
    if not ultima_atividade or c_idle_unit <= 0 or custo_demob_unit <= 0:
        return 0, 0.0
    trailing = contract_end_idx - _week_idx(ultima_atividade)
    if trailing <= 0:
        return 0, 0.0
    economia = c_idle_unit * trailing - custo_demob_unit
    return (trailing, round(economia, 2)) if economia > 0 else (0, 0.0)


def _build_demand_per_week(dist: dict, required: int, total_peak: int) -> dict:
    """Converts distribuicao_semanal into {week: demand_int} for a single tipo."""
    demand_per_week: dict[str, int] = {}
    for w, d in dist.items():
        ne = getattr(d, "num_equipes", 0) or 0
        if ne > 0:
            demand = max(0, round(ne * required / total_peak))
            if demand > 0:
                demand_per_week[w] = demand
    return demand_per_week


def _item_demand_for_tipo(
    iid: str, tipo_id: str, tipo_map: dict, item_total_peak: dict, sched_lookup: dict
) -> dict | None:
    """Returns demand_per_week dict for iid×tipo_id, or None to skip."""
    if tipo_id not in tipo_map:
        return None
    required = tipo_map[tipo_id]
    total_peak = item_total_peak.get(iid, 1) or 1
    sa = sched_lookup.get(iid)
    if not sa:
        return None
    dist = getattr(sa, "distribuicao_semanal", None) or {}
    demand_per_week = _build_demand_per_week(dist, required, total_peak)
    return demand_per_week if demand_per_week else None


def _collect_items_data_for_tipo(
    tipo_id: str,
    item_tipo_required: dict,
    item_total_peak: dict,
    sched_lookup: dict,
    *,
    demand_by_item: dict[str, dict[str, int]] | None = None,
) -> list:
    """Build typed items; exact contractual d_i,g,j overrides legacy estimates.

    The legacy fallback is retained for standalone consumers but MUST NOT be
    presented as certified evidence (callers emit VAL-POOL-DEMANDA-LEGADO).
    """
    items_data = []
    for iid, tipo_map in item_tipo_required.items():
        required = tipo_map.get(tipo_id)
        if required is None:
            continue
        sa = sched_lookup.get(iid)
        if sa is None:
            continue
        if demand_by_item is None:
            demand_per_week = _item_demand_for_tipo(
                iid, tipo_id, tipo_map, item_total_peak, sched_lookup
            )
        else:
            # The contract already carries this type's exact a_i,g(m) from
            # the original P16-C evaluation. Never recompute from resource sums.
            if iid not in demand_by_item:
                continue
            raw = demand_by_item[iid]
            if not isinstance(raw, dict):
                raise ValueError(f"VAL-POOL-DEMANDA-02: invalid profile for {iid}/{tipo_id}")
            dist = getattr(sa, "distribuicao_semanal", None) or {}
            from ._pool_contrato_demanda import _integral_front_count

            expected_weeks = {
                w for w, item in dist.items()
                if _integral_front_count(getattr(item, "num_equipes", 0), f"{iid}/{w}") > 0
            }
            if set(raw) != expected_weeks:
                raise ValueError(f"VAL-POOL-DEMANDA-02: incomplete weeks for {iid}/{tipo_id}")
            demand_per_week = {
                w: _integral_front_count(value, f"{iid}/{tipo_id}/{w}")
                for w, value in raw.items()
            }
            demand_per_week = {w: v for w, v in demand_per_week.items() if v > 0}
        if not demand_per_week:
            continue
        active_weeks_sorted = sorted(demand_per_week, key=_week_idx)
        items_data.append(
            {
                "item_id": iid,
                "required": required,
                "demand_per_week": demand_per_week,
                "active_weeks": active_weeks_sorted,
                "machine_weeks": sum(demand_per_week.values()),
                "start_idx": _week_idx(active_weeks_sorted[0]),
                "end_idx": _week_idx(active_weeks_sorted[-1]),
            }
        )
    return items_data


def _assign_week(
    week: str,
    week_activity_demand: dict,
    span_by_item: dict,
    n: int,
    instance_active: dict,
    instance_activities: dict,
    instance_last_active_week: dict,
    instance_week_map: dict,
    instance_standby: dict,
) -> None:
    """Greedy-assigns one week's activities to instance slots, rest get standby."""
    activities_in_week = week_activity_demand.get(week, {})
    sorted_acts_w = sorted(activities_in_week.items(), key=lambda kv: -span_by_item.get(kv[0], 0))
    cursor = 1
    for act_id, demand in sorted_acts_w:
        for j in range(cursor, min(cursor + demand, n + 1)):
            instance_active[j] += 1
            instance_activities[j].add(act_id)
            instance_last_active_week[j] = week
            instance_week_map[j][week] = act_id
        cursor = min(cursor + demand, n + 1)
    for j in range(cursor, n + 1):
        instance_standby[j] += 1


def _build_week_demand_maps(items_data: list) -> tuple:
    """Returns (week_demand, week_activity_demand) aggregated from items_data."""
    week_demand: dict[str, int] = {}
    week_activity_demand: dict[str, dict[str, int]] = {}
    for item in items_data:
        for w, d in item["demand_per_week"].items():
            week_demand[w] = week_demand.get(w, 0) + d
            week_activity_demand.setdefault(w, {})[item["item_id"]] = d
    return week_demand, week_activity_demand


def _init_instance_slots(n: int) -> tuple:
    """Initializes per-instance tracking dicts for n slots."""
    return (
        {i: 0 for i in range(1, n + 1)},
        {i: 0 for i in range(1, n + 1)},
        {i: set() for i in range(1, n + 1)},
        {i: "" for i in range(1, n + 1)},
        {i: {} for i in range(1, n + 1)},
    )


def _assign_instances(items_data: list, n: int, semanas_contrato: int) -> tuple:
    """Runs greedy instance assignment. Returns (instance_active, instance_standby, instance_activities,
    instance_last_active_week, instance_week_map, all_weeks_sorted)."""
    week_demand, week_activity_demand = _build_week_demand_maps(items_data)
    if any(demand > n for demand in week_demand.values()):
        raise ValueError("VAL-POOL-DEMANDA-02: physical demand exceeds contracted instance slots")
    all_weeks_sorted = sorted(week_demand.keys(), key=_week_idx)
    span_by_item = {it["item_id"]: it["end_idx"] - it["start_idx"] for it in items_data}
    instance_active, instance_standby, instance_activities, instance_last_active_week, instance_week_map = (
        _init_instance_slots(n)
    )
    for week in all_weeks_sorted:
        _assign_week(
            week,
            week_activity_demand,
            span_by_item,
            n,
            instance_active,
            instance_activities,
            instance_last_active_week,
            instance_week_map,
            instance_standby,
        )
    zero_demand_weeks = max(0, semanas_contrato - len(all_weeks_sorted))
    for i in range(1, n + 1):
        instance_standby[i] += zero_demand_weeks
    return (
        instance_active,
        instance_standby,
        instance_activities,
        instance_last_active_week,
        instance_week_map,
        all_weeks_sorted,
    )


def _emit_standby_validation(
    tipo_id: str,
    instancias_standby_alto: list,
    instance_active: dict,
    instance_standby: dict,
    n: int,
    taxa_geral: float,
    custo_standby_total: float,
    status_util: str,
    validacoes: list,
) -> None:
    """Emits VAL-SLOT-STANDBY-ALTO validation if there are high-standby instances."""
    if not instancias_standby_alto:
        return
    standby_detail = "; ".join(
        f"{tipo_id}-{i:02d}: {instance_standby[i]}w idle"
        for i in range(1, n + 1)
        if (instance_active[i] + instance_standby[i]) > 0
        and instance_standby[i] / (instance_active[i] + instance_standby[i]) * 100 > _STANDBY_THRESHOLD_PCT
    )
    val_status = "ERRO" if status_util == "CRITICO" else "AVISO"
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-SLOT-STANDBY-ALTO",
            status=val_status,
            mensagem=(
                f"ADR-077: Contrato {tipo_id} — {len(instancias_standby_alto)} instância(s) "
                f"com standby >{_STANDBY_THRESHOLD_PCT:.0f}%: {standby_detail}. "
                f"Taxa global: {taxa_geral:.1f}%. Custo standby: R$ {custo_standby_total:,.2f}."
            ),
        )
    )


