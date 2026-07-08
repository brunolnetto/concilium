"""Skill 07 — Adapter de Saída (gera JSON + Excel .xlsm) — seção GRAFICOS.

Mão de obra, equipamentos, cronograma, painel de equilíbrio.
"""

from typing import Any

from concilium.domain.models.canonical import CanonicalModel

from ._cash_flow import _cash_flow_rows  # ty: ignore[unresolved-import]


def _bgs_get_equipe(act, equipes_diretas: list):
    """Finds the equipe_direta matching act.activity_id."""
    return next((item for item in equipes_diretas if item.item_id == act.activity_id), None)


def _bgs_gantt_task(act, weeks: list, eap_by_item_id: dict) -> dict:
    """Builds a gantt task dict from a scheduled activity."""
    from datetime import date as _date

    eap_item = eap_by_item_id.get(act.activity_id)
    year_str, week_str = weeks[0].split("-W")
    # Derive EAP level from item_id structure (e.g. "eap-1_0" -> level 1)
    parts = act.activity_id.replace("eap-", "").split("_")
    level = max(0, len(parts) - 1)
    # Collect typed predecessor IDs
    predecessores = []
    if eap_item is not None:
        for p in eap_item.predecessores_tipados():
            predecessores.append({"item_id": p.item_id, "tipo": p.tipo, "lag": p.lag})
    return {
        "item_id": act.activity_id,
        "name": eap_item.descricao if eap_item else act.activity_id,
        "start": _date.fromisocalendar(int(year_str), int(week_str), 1).isoformat(),
        "duration_days": len(weeks) * 7,
        "level": level,
        "predecessores": predecessores,
    }


def _bgs_min_units(eq) -> float:
    """Computes min num_unidades across equipamentos (>0), default 1."""
    if not eq.equipamentos:
        return 1
    return min((e.num_unidades for e in eq.equipamentos if (e.num_unidades or 0) > 0), default=1)


def _bgs_accumulate_equip_by_id(equip_by_id: dict, eq, wk: str, fator: float) -> None:
    """Acumula, por equipamento identificado, a quantidade alocada na semana `wk`."""
    for e in eq.equipamentos:
        eid = e.descricao or e.equip_id or "?"
        equip_by_id.setdefault(eid, {})
        equip_by_id[eid][wk] = equip_by_id[eid].get(wk, 0.0) + fator * float(e.num_unidades or 0.0)


def _bgs_accumulate_mo_by_funcao(mo_by_funcao: dict, eq, wk: str, fator: float) -> None:
    """Acumula, por função normalizada, a quantidade de pessoas alocadas na semana `wk`."""
    for f in eq.funcoes:
        fid = _bgs_normalize_funcao_label(f.descricao or f.funcao_id or "?")
        mo_by_funcao.setdefault(fid, {})
        mo_by_funcao[fid][wk] = mo_by_funcao[fid].get(wk, 0.0) + fator * float(f.num_pessoas or 0.0)


def _bgs_accumulate_week(
    wk: str,
    dist,
    eq,
    equip_totals: dict,
    mo_totals: dict,
    min_units: float,
    equip_by_id: dict | None = None,
    mo_by_funcao: dict | None = None,
) -> None:
    """Accumulates weekly equipment and labour totals from a distribution entry."""
    n = float(getattr(dist, "num_equipes", 0) or 0.0)
    if n <= 0:
        return
    fator = n / min_units
    equip_totals[wk] = equip_totals.get(wk, 0.0) + sum(fator * float(e.num_unidades or 0.0) for e in eq.equipamentos)
    mo_totals[wk] = mo_totals.get(wk, 0.0) + sum(fator * float(f.num_pessoas or 0.0) for f in eq.funcoes)
    if equip_by_id is not None:
        _bgs_accumulate_equip_by_id(equip_by_id, eq, wk, fator)
    if mo_by_funcao is not None:
        _bgs_accumulate_mo_by_funcao(mo_by_funcao, eq, wk, fator)


def _bgs_normalize_funcao_label(label: str) -> str:
    """Agrupa variantes diurno/noturno sob a função-base para leitura operacional."""
    txt = str(label or "?").strip()
    if not txt:
        return "?"
    if "(" not in txt or not txt.endswith(")"):
        return txt
    base, _, suffix = txt.rpartition("(")
    suffix_norm = suffix[:-1].strip().lower()
    if suffix_norm.startswith("diurno") or suffix_norm.startswith("noturno"):
        return base.rstrip(" ,-—")
    return txt


def _bgs_series_section(totals: dict, wks: list, by_group: dict | None, by_group_key: str) -> dict:
    """Constrói uma seção {labels, values, [by_group_key]} de série semanal para o gráfico."""
    section: dict = {
        "labels": [str(wk) for wk in wks],
        "values": [totals[wk] for wk in wks],
    }
    if by_group:
        section[by_group_key] = {gid: [wk_map.get(wk, 0.0) for wk in wks] for gid, wk_map in by_group.items()}
    return section


def _bgs_build_graficos_dict(
    equip_totals: dict,
    mo_totals: dict,
    gantt_tasks: list,
    equip_by_id: dict | None = None,
    mo_by_funcao: dict | None = None,
) -> dict:
    """Builds the base graficos dict with equipamentos, mao_obra and cronograma keys."""
    eq_wks = sorted(equip_totals)
    mo_wks = sorted(mo_totals)
    eq_section = _bgs_series_section(equip_totals, eq_wks, equip_by_id, "by_type")
    mo_section = _bgs_series_section(mo_totals, mo_wks, mo_by_funcao, "by_funcao")
    return {
        "equipamentos": eq_section,
        "mao_obra": mo_section,
        "cronograma": {"tasks": gantt_tasks},
    }


def _bgs_add_financeiro(graficos: dict, canonical_in, project_months: list) -> None:
    """Adds 'financeiro' key to graficos dict if cash_flow_rows are available.

    Usa a versão proporcional ao cronograma físico (_skill_helpers_b),
    não a distribuição uniforme (_cash_flow_rows local).
    """
    try:
        from .._skill_helpers_b import (  # ty: ignore[unresolved-import]  # runtime-only: sibling loaded via importlib in skill.py
            _cash_flow_rows as _cash_flow_rows_proportional,
        )

        cash_flow_rows = _cash_flow_rows_proportional(canonical_in, project_months)
    except Exception:
        cash_flow_rows = _cash_flow_rows(canonical_in, project_months)
    if not cash_flow_rows:
        return
    graficos["financeiro"] = {
        "labels": [row["mes_label"] for row in cash_flow_rows],
        "receita": [row["receita"] for row in cash_flow_rows],
        "despesa": [row["despesa"] for row in cash_flow_rows],
        "saldo": [row["saldo"] for row in cash_flow_rows],
        "exposicao": [row["exposicao"] for row in cash_flow_rows],
    }


def _build_graficos_section(canonical_in: CanonicalModel, eap_by_item_id: dict, project_months: list) -> dict:
    equip_totals: dict[str, float] = {}
    mo_totals: dict[str, float] = {}
    equip_by_id: dict[str, dict[str, float]] = {}
    mo_by_funcao: dict[str, dict[str, float]] = {}
    gantt_tasks: list[dict[str, Any]] = []
    acts = canonical_in.cronograma.scheduled_activities if canonical_in.cronograma else []
    for act in acts:
        eq = _bgs_get_equipe(act, canonical_in.equipes_diretas)
        if eq is None:
            continue
        weeks = sorted(act.distribuicao_semanal.keys())
        if weeks:
            gantt_tasks.append(_bgs_gantt_task(act, weeks, eap_by_item_id))
        min_units = _bgs_min_units(eq)
        for wk, dist in act.distribuicao_semanal.items():
            _bgs_accumulate_week(wk, dist, eq, equip_totals, mo_totals, min_units, equip_by_id, mo_by_funcao)
    graficos = _bgs_build_graficos_dict(equip_totals, mo_totals, gantt_tasks, equip_by_id, mo_by_funcao)
    _bgs_add_financeiro(graficos, canonical_in, project_months)
    _bgs_add_painel_equilibrio(graficos, canonical_in)
    return graficos


def _mbec_is_minimal(levers: list[dict], combo: tuple[int, ...], size: int, target: float) -> bool:
    """Verifica se nenhum subconjunto próprio de `combo` já cobre o target (minimalidade)."""
    from itertools import combinations as _combns

    return not any(
        sum(levers[j]["delta_margin_total"] for j in sub) >= target
        for sub_size in range(1, size)
        for sub in _combns(combo, sub_size)
    )


def _mbec_combo_entry(levers: list[dict], combo: tuple[int, ...], size: int, soma: float, target: float) -> dict:
    """Constrói a entrada de resultado (tier, levers_ids, cobertura) para uma combinação minimal."""
    return {
        "tier": size,
        "levers_ids": [levers[i]["id"] for i in combo],
        "delta_disponivel": round(soma, 2),
        "cobertura_pct": round(soma / target * 100, 1),
    }


def _minimal_break_even_combinations(levers: list[dict], deficit: float) -> list[dict]:
    """Retorna todos os subconjuntos minimais de levers suficientes para cobrir o deficit.

    Um subconjunto é *minimal* se nenhum subconjunto próprio seu também cobre o deficit.
    Resulta em uma hierarquia por tier (1 = ação individual, 2 = par, …).
    Ordenado por (tier ASC, cobertura_pct ASC) — caminho mais enxuto primeiro.
    """
    if deficit >= 0 or not levers:
        return []
    from itertools import combinations as _combns

    target = abs(deficit)
    result: list[dict] = []
    n = len(levers)
    for size in range(1, n + 1):
        for combo in _combns(range(n), size):
            soma = sum(levers[i]["delta_margin_total"] for i in combo)
            if soma < target:
                continue
            if _mbec_is_minimal(levers, combo, size, target):
                result.append(_mbec_combo_entry(levers, combo, size, soma, target))
    return sorted(result, key=lambda x: (x["tier"], x["cobertura_pct"]))


def _bgs_aggregate_levers(pe_list: list) -> dict[str, dict]:
    """Agrega levers_equilibrio de todos os itens somando delta_margin_total e item_count."""
    levers_agg: dict[str, dict] = {}
    for pe in pe_list:
        for lever in getattr(pe, "levers_equilibrio", []):
            if lever.id not in levers_agg:
                levers_agg[lever.id] = {
                    "id": lever.id,
                    "tipo": lever.tipo,
                    "descricao": lever.descricao,
                    "restricoes": list(lever.restricoes),
                    "delta_margin_total": 0.0,
                    "item_count": 0,
                }
            levers_agg[lever.id]["delta_margin_total"] = round(
                levers_agg[lever.id]["delta_margin_total"] + lever.delta_margin, 2
            )
            levers_agg[lever.id]["item_count"] += 1
    return levers_agg


def _bgs_mark_combinacoes(levers_sorted: list[dict], combinacoes: list[dict]) -> None:
    """Marca cada lever (in-place) com sua participação nas combinações minimais de break-even."""
    levers_em_combinacoes_tier1: set[str] = {lid for c in combinacoes if c["tier"] == 1 for lid in c["levers_ids"]}
    levers_em_qualquer_combo: set[str] = {lid for c in combinacoes for lid in c["levers_ids"]}
    for lv in levers_sorted:
        lv["break_even_solo"] = lv["id"] in levers_em_combinacoes_tier1
        lv["participa_combo"] = lv["id"] in levers_em_qualquer_combo


def _bgs_frentes_nec_media(pe_list: list) -> float:
    """Multiplicador médio de PU ponderado por custo_venda (frentes_nec media)."""
    total_venda = sum(pe.custo_venda_cpu for pe in pe_list if pe.custo_venda_cpu > 0)
    return (
        (
            sum(pe.frentes_equivalentes_necessarias * pe.custo_venda_cpu for pe in pe_list if pe.custo_venda_cpu > 0)
            / total_venda
        )
        if total_venda > 0
        else 1.0
    )


def _bgs_add_painel_equilibrio(graficos: dict, canonical_in: CanonicalModel) -> None:
    """ADR-082: Agrega levers_equilibrio de todos os itens de ponto_equilibrio no graficos dict."""
    pe_list = canonical_in.ponto_equilibrio or []
    if not pe_list:
        return

    delta_total = round(sum(pe.delta for pe in pe_list), 2)
    levers_agg = _bgs_aggregate_levers(pe_list)

    # "fechar_gap_escala" representa serializacao/paralelismo de frentes e tende a
    # gerar leitura ambigua no painel executivo. Mantemos foco em praticabilidade/pool.
    levers_visiveis = [lv for lv in levers_agg.values() if lv.get("id") != "fechar_gap_escala"]
    levers_sorted = sorted(levers_visiveis, key=lambda x: -x["delta_margin_total"])
    soma_levers = round(sum(lv["delta_margin_total"] for lv in levers_sorted), 2)
    combinacoes = _minimal_break_even_combinations(levers_sorted, delta_total)

    _bgs_mark_combinacoes(levers_sorted, combinacoes)
    frentes_nec_media = _bgs_frentes_nec_media(pe_list)

    graficos["painel_equilibrio"] = {
        "delta_total": delta_total,
        "soma_levers": soma_levers,
        "break_even_alcancavel": soma_levers >= abs(delta_total) if delta_total < 0 else True,
        "levers": levers_sorted,
        "combinacoes_break_even": combinacoes,
        "frentes_nec_media": round(frentes_nec_media, 3),
    }


