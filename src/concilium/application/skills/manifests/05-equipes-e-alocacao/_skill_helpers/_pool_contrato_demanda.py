"""Skill 05 — Equipes e Alocação (helpers A, parte extraída de _pool_contrato.py)."""

from __future__ import annotations

import math
from fractions import Fraction

from concilium.domain.models.canonical import ValidacaoItem

from .pre_metrics import _gap_max_economico  # ty: ignore[unresolved-import]
from .week_index import iso_week_index  # ty: ignore[unresolved-import]


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
        return iso_week_index(s)
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


def _integral_front_count(value: object, label: str) -> int:
    """Physical team count must be a finite, nonnegative integer."""
    # The scheduler stores normalized integer ramps as binary floats:
    # m_peak * (7 / 25) is 7.000000000000001. Recognize only IEEE-754
    # roundoff in *computed floats*. Exact strings/Decimal/Fraction with
    # fractional quantities stay invalid: no arbitrary resource rounding.
    if isinstance(value, float):
        if not math.isfinite(value) or value < 0 or value > 2**53:
            raise ValueError(f"VAL-POOL-DEMANDA-01: {label} has invalid team count")
        nearest = round(value)
        # Zero teams must be exactly zero. A subnormal positive allocation
        # is fractional physical demand, not an artifact of an integer ramp.
        if nearest == 0 and value != 0:
            raise ValueError(f"VAL-POOL-DEMANDA-01: {label} must be a nonnegative integer")
        bound = 2 * max(math.ulp(value), math.ulp(float(nearest)))
        if abs(value - nearest) > bound:
            raise ValueError(f"VAL-POOL-DEMANDA-01: {label} must be a nonnegative integer")
        return int(nearest)
    try:
        number = Fraction(str(value))
    except (ValueError, ZeroDivisionError, TypeError, OverflowError) as exc:
        raise ValueError(f"VAL-POOL-DEMANDA-01: {label} has invalid team count") from exc
    if number.denominator != 1 or number < 0:
        raise ValueError(f"VAL-POOL-DEMANDA-01: {label} must be a nonnegative integer")
    return int(number)


def _demand_from_team_profile(
    required: int,
    peak_frentes: int,
    fronts: object,
    tipo: str,
    profile: dict | None = None,
) -> int:
    """Evaluate the physical a_i,g(m) without inferring an unproved model.

    'required' is the resource count at the scheduled peak. A type with
    composite-team identity has one fungible team unit per front. Other types
    require either 'per_front' or a declared 'by_fronts' table whenever a
    subpeak week is scheduled. Integer divisibility by peak is NOT proof
    that a shared resource scales linearly with teams.
    """
    m = _integral_front_count(fronts, "m_ij")
    if not isinstance(required, int) or isinstance(required, bool) or required < 0:
        raise ValueError(f"VAL-POOL-DEMANDA-01: invalid peak demand of resource {tipo}")
    if peak_frentes <= 0 or m > peak_frentes:
        raise ValueError(f"VAL-POOL-DEMANDA-01: {tipo} fronts exceed or lack peak calibration")
    if m == 0:
        return 0

    if profile is not None:
        if not isinstance(profile, dict):
            raise ValueError(f"VAL-POOL-DEMANDA-01: {tipo} has invalid composition profile")
        if "per_front" in profile and "by_fronts" in profile:
            raise ValueError(f"VAL-POOL-DEMANDA-01: {tipo} has ambiguous composition model")
        if "per_front" in profile:
            count = _integral_front_count(profile["per_front"], f"{tipo}.per_front")
            if count * peak_frentes != required:
                raise ValueError(f"VAL-POOL-DEMANDA-01: {tipo} peak disagrees with per-front composition")
            return count * m
        if "by_fronts" in profile:
            table = profile["by_fronts"]
            if not isinstance(table, dict) or str(m) not in table or str(peak_frentes) not in table:
                raise ValueError(f"VAL-POOL-DEMANDA-01: {tipo} missing a_i,g(m) for demanded fronts")
            peak_count = _integral_front_count(table[str(peak_frentes)], f"{tipo}.peak")
            if peak_count != required:
                raise ValueError(f"VAL-POOL-DEMANDA-01: {tipo} peak disagrees with declared table")
            return _integral_front_count(table[str(m)], f"{tipo}.a(m)")
        raise ValueError(f"VAL-POOL-DEMANDA-01: {tipo} missing a_i,g(m) data")

    if tipo.startswith(("EQUIPE-COMP-", "EQUIPE-CPU-")):
        if required != peak_frentes:
            raise ValueError(f"VAL-POOL-DEMANDA-01: {tipo} must represent one composite team per front")
        return m

    # At peak the declared count is known; away from peak a nonlinear shared
    # resource is possible even when required/peak is an integer.
    if m == peak_frentes:
        return required
    raise ValueError(
        f"VAL-POOL-DEMANDA-01: {tipo} needs explicit a_i,g(m) "
        f"for m={m}, peak={peak_frentes}, required={required}"
    )


def _accum_week_demand(
    tipo_week_demand: dict,
    tipo: str,
    active_weeks: list,
    dist: dict,
    required: int,
    peak_frentes: int,
    *,
    weekly_counts: dict[str, int] | None = None,
    profile: dict | None = None,
) -> None:
    """Accumulate exact weekly demand for one homogeneous resource type."""
    counts = weekly_counts or {
        w: _demand_from_team_profile(required, peak_frentes, getattr(dist[w], "num_equipes", 0), tipo, profile)
        for w in active_weeks
    }
    week_demand = tipo_week_demand.setdefault(tipo, {})
    for w in active_weeks:
        week_demand[w] = week_demand.get(w, 0) + counts[w]


def _add_tipo_item_demand(
    tipo: str,
    iid: str,
    required: int,
    peak_frentes: int,
    active_weeks: list,
    eq,
    dist: dict,
    tipo_items: dict,
    tipo_week_demand: dict,
    *,
    weekly_counts: dict[str, int] | None = None,
    profile: dict | None = None,
) -> None:
    """Use the SAME integer counts for item machine-weeks and pool demand."""
    counts = weekly_counts if weekly_counts is not None else {
        w: _demand_from_team_profile(
            required, peak_frentes, getattr(dist[w], "num_equipes", 0), tipo, profile
        )
        for w in active_weeks
    }
    actual_mw = sum(counts.values())
    comp_mo, comp_eq, comp_comb, comp_mat = _eq_comp_floats(eq)
    tipo_items.setdefault(tipo, []).append(
        {
            "item_id": iid,
            "required": required,
            "active_weeks": active_weeks,
            "custo_total_item": _eq_custo_total_agregado(eq),
            "machine_weeks": actual_mw,
            "demand_per_week": dict(counts),  # exact physical source for instances
            "frentes_por_semana": {
                w: _integral_front_count(getattr(dist[w], "num_equipes", 0), f"{iid}/{w}")
                for w in active_weeks
            },
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
    _accum_week_demand(
        tipo_week_demand, tipo, active_weeks, dist, required, peak_frentes, weekly_counts=counts, profile=profile
    )


def _get_active_weeks(sa) -> list:
    """Returns sorted list of weeks with positive num_equipes from scheduled activity."""
    dist = getattr(sa, "distribuicao_semanal", None) or {}
    return sorted(
        [
            w
            for w, d in dist.items()
            if _integral_front_count(getattr(d, "num_equipes", 0), str(w)) > 0
        ],
        key=_week_idx,
    )


def _process_item_tipo_map(
    iid: str,
    tipo_map: dict,
    equipe_map: dict,
    pool: dict,
    sched_lookup: dict,
    tipo_items: dict,
    tipo_week_demand: dict,
    validacoes: list,
    profiles_by_type: dict | None = None,
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
    # Peak is a count of the activity's actual physical fronts, NOT the
    # dimensionally invalid sum of heterogeneous resource-type quantities.
    peak_frentes = max(
        _integral_front_count(getattr(dist[w], "num_equipes", 0), f"{iid}/{w}")
        for w in active_weeks
    )
    # Validate ALL eligible typed resource counts before writing ANY pool
    # entry: a malformed shared resource cannot leave a half-built contract.
    eligible = {tipo: required for tipo, required in tipo_map.items() if tipo in pool}
    profiles = profiles_by_type or {}
    counts_by_type = {
        tipo: {
            w: _demand_from_team_profile(
                required, peak_frentes, getattr(dist[w], "num_equipes", 0), tipo, profiles.get(tipo)
            )
            for w in active_weeks
        }
        for tipo, required in eligible.items()
    }
    for tipo, required in eligible.items():
        _add_tipo_item_demand(
            tipo,
            iid,
            required,
            peak_frentes,
            active_weeks,
            eq,
            dist,
            tipo_items,
            tipo_week_demand,
            weekly_counts=counts_by_type[tipo],
            profile=profiles.get(tipo),
        )


def _collect_tipo_items_and_demands(
    item_tipo_map: dict,
    equipe_map: dict,
    pool: dict,
    sched_lookup: dict,
    validacoes: list,
    resource_profiles: dict | None = None,
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
            (resource_profiles or {}).get(iid),
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
    # Single source of economic gap admissibility, shared with the
    # downstream opportunity evaluator. Include exact ties deterministically:
    # k*c_idle <= c_mob+c_demob. The unit passed here only selects the
    # calendar-billed regime; c_idle has already been resolved for this call.
    return c_idle, _gap_max_economico(c_mob, c_demob, c_idle, "dia_cal")


