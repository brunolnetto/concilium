"""Skill 05 — Equipes e Alocação (helpers A, parte extraída de _pool_contrato.py)."""

from __future__ import annotations

import math

from concilium.domain.models.canonical import ValidacaoItem


def _week_idx(semana: str) -> int:
    """Converte chave de semana para índice inteiro comparável.

    Suporta dois formatos:
    - "S052"      → 52  (índice sequencial do benchmark)
    - "2026-W48"  → número de semanas desde época fixa (ISO 8601)
    """
    s = str(semana).strip()
    # Formato S-index: "S001", "S052", etc.
    if s.startswith("S") and s[1:].isdigit():
        return int(s[1:])
    # Formato ISO: "2026-W48" ou "2026-W08"
    if "-W" in s:
        try:
            import datetime

            parts = s.split("-W")
            year, week = int(parts[0]), int(parts[1])
            monday = datetime.datetime.strptime(f"{year}-W{week:02d}-1", "%G-W%V-%u")
            epoch = datetime.datetime(2000, 1, 3)  # segunda-feira da semana 1 de 2000
            return (monday - epoch).days // 7
        except Exception:
            return 0
    # Fallback: tenta int direto
    try:
        return int(s.lstrip("0") or "0")
    except ValueError:
        return 0


def _eq_comp_floats(eq) -> tuple:
    """Returns (comp_mo, comp_eq, comp_comb, comp_mat) floats from equipe."""
    return (
        float(getattr(eq, "custo_mao_obra_mensal", 0.0) or 0.0),
        float(getattr(eq, "custo_equipamentos_mensal", 0.0) or 0.0),
        float(getattr(eq, "custo_combustivel_total_mensal", 0.0) or 0.0),
        float(getattr(eq, "custo_material_mensal", 0.0) or 0.0),
    )


def _eq_custo_total_agregado(eq) -> float:
    """Issue #139: `custo_total_item` precisa estar na MESMA base agregada que
    `machine_weeks` (que já soma `num_equipes` real por semana, todas as frentes) —
    `eq.custo_total` é sempre "1 frente" por convenção (ADR-091/ADR-162 D4), nunca
    multiplicado por `num_equipes`. Dividir esse numerador de 1 frente pelo `machine_weeks`
    agregado subestimava `custo_unit_semanal` sistematicamente (verificado: item sozinho
    no pool com NE=3 constante devolvia o valor de 1 frente inalterado, 1/3 do custo real).

    `custo_operacional_agregado` (ADR-172, skill 05, `_calc_custo_cron`) já é essa integral
    semana a semana — robusta a rampa por construção, mesma escala de `machine_weeks`.
    Fallback nominal (`custo_total × num_equipes_base`) só quando o campo novo não está
    disponível (dados antigos/testes que ainda não o populam) — nunca 0 silenciosamente.
    """
    agregado = float(getattr(eq, "custo_operacional_agregado", 0.0) or 0.0)
    if agregado > 0:
        return agregado
    n_frentes = max(1, int(getattr(eq, "num_equipes_base", 1) or 1))
    return float(getattr(eq, "custo_total", 0.0) or 0.0) * n_frentes


def _accum_week_demand(
    tipo_week_demand: dict, tipo: str, active_weeks: list, dist: dict, required: int, total_required_peak: int
) -> None:
    """Accumulates week demand entries into tipo_week_demand[tipo]."""
    week_demand = tipo_week_demand.setdefault(tipo, {})
    for w in active_weeks:
        raw = (getattr(dist[w], "num_equipes", 0) or 0) * required / total_required_peak
        demand_w = max(0, math.ceil(raw))
        week_demand[w] = week_demand.get(w, 0) + demand_w


def _add_tipo_item_demand(
    tipo: str,
    iid: str,
    required: int,
    total_required_peak: int,
    active_weeks: list,
    eq,
    dist: dict,
    tipo_items: dict,
    tipo_week_demand: dict,
) -> None:
    """Appends item entry and week demand for a single tipo."""
    actual_mw = sum(
        max(0, round((getattr(dist[w], "num_equipes", 0) or 0) * required / total_required_peak)) for w in active_weeks
    )
    if actual_mw == 0:
        actual_mw = required * len(active_weeks)
    comp_mo, comp_eq, comp_comb, comp_mat = _eq_comp_floats(eq)
    tipo_items.setdefault(tipo, []).append(
        {
            "item_id": iid,
            "required": required,
            "active_weeks": active_weeks,
            "custo_total_item": _eq_custo_total_agregado(eq),
            "machine_weeks": actual_mw,
            "start_idx": _week_idx(active_weeks[0]),
            "end_idx": _week_idx(active_weeks[-1]) + 1,
            "semana_inicio": active_weeks[0],
            "semana_fim": active_weeks[-1],
            "comp_mo": comp_mo,
            "comp_eq": comp_eq,
            "comp_comb": comp_comb,
            "comp_mat": comp_mat,
        }
    )
    _accum_week_demand(tipo_week_demand, tipo, active_weeks, dist, required, total_required_peak)


def _get_active_weeks(sa) -> list:
    """Returns sorted list of weeks with positive num_equipes from scheduled activity."""
    dist = getattr(sa, "distribuicao_semanal", None) or {}
    return sorted([w for w, d in dist.items() if (getattr(d, "num_equipes", 0) or 0) > 0], key=_week_idx)


def _process_item_tipo_map(
    iid: str,
    tipo_map: dict,
    equipe_map: dict,
    pool: dict,
    sched_lookup: dict,
    tipo_items: dict,
    tipo_week_demand: dict,
    validacoes: list,
) -> None:
    """Processes one iid from item_tipo_map, appending to tipo_items/tipo_week_demand."""
    eq = equipe_map.get(iid)
    sa = sched_lookup.get(iid)
    if not eq or not sa:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-POOL-CONTRATO-01",
                status="INFO",
                mensagem=(f"Item '{iid}' tem required_resources mas sem equipe ou schedule — mantendo custo autônomo."),
            )
        )
        return
    active_weeks = _get_active_weeks(sa)
    if not active_weeks:
        return
    dist = getattr(sa, "distribuicao_semanal", None) or {}
    total_required_peak = sum(tipo_map.values()) or 1
    for tipo, required in tipo_map.items():
        if tipo not in pool:
            continue
        _add_tipo_item_demand(
            tipo,
            iid,
            required,
            total_required_peak,
            active_weeks,
            eq,
            dist,
            tipo_items,
            tipo_week_demand,
        )


def _collect_tipo_items_and_demands(
    item_tipo_map: dict,
    equipe_map: dict,
    pool: dict,
    sched_lookup: dict,
    validacoes: list,
) -> tuple[dict, dict]:
    """Itera items e constrói tipo_items / tipo_week_demand."""
    tipo_items: dict[str, list[dict]] = {}
    tipo_week_demand: dict[str, dict[str, int]] = {}
    for iid, tipo_map in item_tipo_map.items():
        _process_item_tipo_map(
            iid,
            tipo_map,
            equipe_map,
            pool,
            sched_lookup,
            tipo_items,
            tipo_week_demand,
            validacoes,
        )
    return tipo_items, tipo_week_demand


def _compute_custo_unit_fracs(mw_list: list) -> tuple:
    """Retorna (custo_unit_semanal, frac_mo, frac_eq, frac_comb, frac_mat) via média ponderada.

    custo_unit_semanal é o custo de 1 recurso-tipo por 1 semana de trabalho ativo,
    sempre bottom-up: custo_total_item / machine_weeks (estimativa a partir da equipe
    dimensionada, skill-05). Sem atalho por referência de catálogo — removido porque
    a composição bottom-up (ADR-132) já reproduz o custo real por construção.

    Issue #139: `custo_total_item` (via `_eq_custo_total_agregado`) precisa estar na MESMA
    base agregada que `machine_weeks` (soma `num_equipes` real por semana, todas as
    frentes) — `eq.custo_total` sozinho é sempre "1 frente" (ADR-091/ADR-162 D4), e dividir
    esse numerador de 1 frente pelo `machine_weeks` agregado subestimava `custo_unit_semanal`
    sistematicamente sempre que algum item do pool tinha `num_equipes > 1`.
    """
    total_mw = sum(mw for _, mw, _ in mw_list)
    custo_unit_semanal = (
        sum(
            (it["custo_total_item"] / it["machine_weeks"] if it["machine_weeks"] > 0 else 0.0) * mw
            for _, mw, it in mw_list
        )
        / total_mw
        if total_mw > 0
        else 0.0
    )
    _acc = {"mo": 0.0, "eq": 0.0, "comb": 0.0, "mat": 0.0}
    for _, mw, it in mw_list:
        base_i = it["comp_mo"] + it["comp_eq"] + it["comp_comb"] + it["comp_mat"]
        if base_i <= 0 or mw <= 0:
            continue
        _acc["mo"] += (it["comp_mo"] / base_i) * mw
        _acc["eq"] += (it["comp_eq"] / base_i) * mw
        _acc["comb"] += (it["comp_comb"] / base_i) * mw
        _acc["mat"] += (it["comp_mat"] / base_i) * mw
    _soma = sum(_acc.values())
    if _soma > 0:
        fmo, feq, fcomb, fmat = _acc["mo"] / _soma, _acc["eq"] / _soma, _acc["comb"] / _soma, _acc["mat"] / _soma
    else:
        fmo, feq, fcomb, fmat = 1.0, 0.0, 0.0, 0.0
    return custo_unit_semanal, fmo, feq, fcomb, fmat


def _compute_fracs_locacao_manut(mw_list: list, equipe_map: dict, cus_eq: float) -> tuple:
    """Retorna (cus_locacao, cus_manutencao) com sub-decomposição ADR-088."""
    _acc_loc = 0.0
    _acc_manut = 0.0
    for _, mw, it in mw_list:
        _eq_i = it.get("comp_eq", 0.0)
        if _eq_i <= 0 or mw <= 0:
            continue
        _loc_i = getattr(equipe_map.get(it["item_id"]), "custo_locacao_mensal", _eq_i) or _eq_i
        _manut_i = getattr(equipe_map.get(it["item_id"]), "custo_manutencao_mensal", 0.0) or 0.0
        _base_eq = max(_loc_i + _manut_i, _eq_i)
        _acc_loc += (_loc_i / _base_eq) * mw
        _acc_manut += (_manut_i / _base_eq) * mw
    _soma_eq = _acc_loc + _acc_manut
    if _soma_eq > 0 and cus_eq > 0:
        _frac_loc = _acc_loc / _soma_eq
        return round(cus_eq * _frac_loc, 4), round(cus_eq * (1.0 - _frac_loc), 4)
    return cus_eq, 0.0


def _fill_atribuicao(atribuicao: dict, mw_list: list, custo_total_contrato: float, tipo: str) -> None:
    """Fills atribuicao[iid] = (cost, tipo, frac) para este contrato específico.

    IMPORTANTE: sobrescreve a entrada anterior — o acumulado multi-contrato é feito em
    _build_contratos_recurso após todos os contratos serem construídos (TD-1 fix).
    """
    total_mw = sum(mw for _, mw, _ in mw_list) or 1
    for iid, mw, _ in mw_list:
        frac = round(mw / total_mw, 6)
        atribuicao[iid] = (round(custo_total_contrato * frac, 2), tipo, frac)


def _resolve_gap_max_e_idle_efetivo(
    c_mob: float,
    c_demob: float,
    c_idle: float,
    resource_costs_absent: bool,
    cus_mo: float,
    cus_locacao: float,
) -> tuple[float, int]:
    """Resolve o custo idle efetivo (com fallback ADR-085) e o gap_max econômico.

    ADR-085: quando resource_costs não fornece taxa ociosa explícita, deriva do custo
    fixo da própria composição — mas SOMENTE se a chave resource_costs estava ausente
    no spec (catálogo sem custos explícitos). Se resource_costs={} foi passado
    explicitamente, preserva o comportamento monolítico ADR-071.
    """
    if c_idle <= 0.0 and resource_costs_absent:
        _c_idle_fallback = round(cus_mo + cus_locacao, 4)
        if _c_idle_fallback > 0.0:
            c_idle = _c_idle_fallback
    gap_max = int(math.ceil((c_mob + c_demob) / c_idle) - 1) if c_idle > 0 else 9999
    return c_idle, gap_max


