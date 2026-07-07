"""Skill 07 — Adapter de Saída (gera JSON + Excel .xlsm).

Skill 07 produz o output principal:
1. JSON estruturado (para validação, logs, API)
2. Excel .xlsm auditável (para stakeholders, relatórios)

Estrutura Excel gerada:
  - RESUMO: metadados do projeto + indicadores financeiros
  - PLANEJAMENTO: itens da EAP com preços, BDI, subtotais
  - EQUIPES: composição, custos e ponto de equilíbrio
  - INDIRETOS: custos indiretos por categoria
  - RESULTADO: resultado financeiro consolidado
"""

from datetime import UTC, date, datetime
from typing import Any

from concilium.domain.models.canonical import CanonicalModel, SubtotalSemBdiComBdi, ValidacaoItem
from concilium.infrastructure.adapters.excel_adapter import ExcelRenderer

_MESES_PT = {
    1: "Jan",
    2: "Fev",
    3: "Mar",
    4: "Abr",
    5: "Mai",
    6: "Jun",
    7: "Jul",
    8: "Ago",
    9: "Set",
    10: "Out",
    11: "Nov",
    12: "Dez",
}


def _add_criticidade_validacoes(
    canonical_in: CanonicalModel, has_criticidade: bool, criticidade_lookup: dict, validacoes: list
) -> None:
    if has_criticidade:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-ADAPTER-CRITICIDADE",
                status="OK",
                mensagem=f"Criticidade aplicada em {len(criticidade_lookup)} atividades.",
            )
        )
    else:
        # Emite AVISO seja quando o relatório está ausente ou quando está presente
        # mas sem atividades classificadas que correspondam à EAP atual.
        if canonical_in.cost_criticality_report is not None:
            msg = "Relatório de criticidade presente, mas sem atividades classificadas."
        else:
            msg = "Relatório de criticidade ausente. Execute skill-15 (diagnóstico) para enriquecer o relatório."
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-ADAPTER-CRITICIDADE",
                status="AVISO",
                mensagem=msg,
            )
        )


def _pe_field(pe: Any, attr: str, default: float) -> float:
    """Lê um atributo numérico do ponto_equilibrio com fallback seguro quando pe é None."""
    return float(getattr(pe, attr, default) or default) if pe else default


def _build_planejamento_row(
    p: Any,
    eap_item: Any,
    pe: Any,
    criticidade_lookup: dict[str, str],
    has_criticidade: bool,
) -> dict:
    """Constrói uma linha de PLANEJAMENTO (item + camadas de precificação NEP-042)."""
    subtotal = p.subtotal if p.subtotal is not None else SubtotalSemBdiComBdi()
    row = {
        "item_id": p.item_id,
        "cpu_id": p.cpu_id,
        "descricao": (eap_item.descricao if eap_item else ""),
        "unidade": (eap_item.unidade if eap_item else ""),
        "quantitativo": p.quantitativo,
        "subtotal_sem_bdi_mo": subtotal.sem_bdi.mao_obra,
        "subtotal_sem_bdi_eq": subtotal.sem_bdi.equipamentos,
        "subtotal_sem_bdi_diesel": subtotal.sem_bdi.diesel,
        "subtotal_sem_bdi_mat": subtotal.sem_bdi.material,
        "subtotal_sem_bdi": subtotal.sem_bdi.total,
        "subtotal_com_bdi": subtotal.com_bdi.total,
        # Camada 1 — catálogo
        "pu_total_sem_bdi": p.preco_unitario.total,
        "pu_total_com_bdi": p.preco_unitario_com_bdi.total,
        # NEP-042: Camada 2 — operacional autônomo
        "pu_op_autonomo": _pe_field(pe, "pu_operacional_autonomo", 0.0),
        "frentes_necessarias": _pe_field(pe, "frentes_equivalentes_necessarias", 1.0),
        "eta_real": _pe_field(pe, "eta_real", 1.0),
        # NEP-042: Camada 3 — burden de permanência instancial
        "burden_pool": _pe_field(pe, "custo_pool_total", 0.0),
        "economia_pool_abs": _pe_field(pe, "economia_pool_abs", 0.0),
    }
    if has_criticidade:
        row["criticidade"] = criticidade_lookup.get(p.item_id, "-")
    return row


def _build_planejamento_rows(
    canonical_in: CanonicalModel, criticidade_lookup: dict[str, str], has_criticidade: bool
) -> list[dict]:
    eap_by_item_id = {e.item_id: e for e in canonical_in.eap}
    # NEP-042: join com ponto_equilibrio para expor as três camadas de precificação
    pe_by_item = {pe.item_id: pe for pe in (canonical_in.ponto_equilibrio or []) if pe.item_id}
    return [
        _build_planejamento_row(
            p, eap_by_item_id.get(p.item_id), pe_by_item.get(p.item_id), criticidade_lookup, has_criticidade
        )
        for p in canonical_in.planejamento
    ]


def _build_tres_camadas_row(p: Any, eap_item: Any, pe: Any) -> dict:
    """Constrói uma linha da view consolidada das três camadas de precificação (NEP-042 D4)."""
    pu_op = _pe_field(pe, "pu_operacional_autonomo", 0.0)
    economia = _pe_field(pe, "economia_pool_abs", 0.0)
    custo_autonomo = pu_op * p.quantitativo if p.quantitativo else 0.0
    economia_pct = (economia / custo_autonomo) if custo_autonomo > 0 else 0.0
    return {
        "item_id": p.item_id,
        "cpu_id": p.cpu_id,
        "descricao": eap_item.descricao if eap_item else "",
        "unidade": eap_item.unidade if eap_item else "",
        "quantitativo": p.quantitativo,
        # Camada 1 — catálogo
        "pu_cat": float(p.preco_unitario.total or 0.0),
        # Camada 2 — operacional autônomo
        "pu_op_autonomo": pu_op,
        "frentes_necessarias": _pe_field(pe, "frentes_equivalentes_necessarias", 1.0),
        "eta_real": _pe_field(pe, "eta_real", 1.0),
        # Camada 3 — burden de permanência instancial
        "pu_pool": _pe_field(pe, "custo_pool_por_unidade", 0.0),
        "economia_pool_abs": economia,
        "economia_pool_pct": round(economia_pct, 4),
    }


def _build_tres_camadas_rows(canonical_in: CanonicalModel) -> list[dict]:
    """NEP-042 D4 — view consolidada das três camadas de precificação por item.

    Apresenta lado a lado: PU_cat (catálogo), PU_op_autonomo (operacional),
    PU_pool (burden instancial), + frentes_necessarias, eta_real e economia de pool.
    Cada linha é um item da EAP com planejamento; itens sem ponto_equilibrio
    expõem apenas a camada de catálogo.
    """
    eap_by_item = {e.item_id: e for e in canonical_in.eap}
    pe_by_item = {pe.item_id: pe for pe in (canonical_in.ponto_equilibrio or []) if pe.item_id}
    return [
        _build_tres_camadas_row(p, eap_by_item.get(p.item_id), pe_by_item.get(p.item_id))
        for p in canonical_in.planejamento
    ]


def _ber_acao_sugerida(gap: float, dominante: str) -> str:
    """Sugere uma ação corretiva com base no gap operacional e no componente dominante."""
    if gap >= 0:
        return "Manter baseline"
    if dominante == "Diesel":
        return "Rever logística e consumo de combustível"
    if dominante == "Mão de Obra":
        return "Ajustar produtividade/equipe"
    if dominante == "Equipamentos":
        return "Otimizar frota e utilização"
    if dominante == "Materiais":
        return "Rever traço e perdas de material"
    return "Rebalancear composição operacional"


def _ber_componentes_operacionais(eq: Any, custo_operacional: float) -> dict[str, float]:
    """Distribui o custo_operacional_real pelos componentes mensais da equipe (proporcional)."""
    mensal = {
        "Mão de Obra": float(eq.custo_mao_obra_mensal or 0.0),
        "Encargos Sociais": float(getattr(eq, "custo_encargos_mensal", 0.0) or 0.0),
        "Equipamentos": float(eq.custo_equipamentos_mensal or 0.0),
        "Materiais": float(eq.custo_material_mensal or 0.0),
        "Diesel": float(eq.custo_combustivel_total_mensal or 0.0),
    }
    base = sum(mensal.values())
    if base <= 0 or custo_operacional <= 0:
        return {k: 0.0 for k in mensal}
    fator = custo_operacional / base
    return {k: v * fator for k, v in mensal.items()}


def _ber_componentes_referencia(item_id: str, plan_by_item: dict) -> dict[str, float] | None:
    """Extrai os componentes de custo de referência (subtotal sem BDI) do planejamento."""
    plan = plan_by_item.get(item_id)
    if plan is None or plan.subtotal is None or plan.subtotal.sem_bdi is None:
        return None
    sem = plan.subtotal.sem_bdi
    return {
        "Mão de Obra": float(sem.mao_obra or 0.0),
        "Equipamentos": float(sem.equipamentos or 0.0),
        "Materiais": float(sem.material or 0.0),
        "Diesel": float(sem.diesel or 0.0),
    }


def _ber_componente_dominante(eq: Any, custo_operacional: float, gap_operacional: float, plan_by_item: dict) -> str:
    """Identifica o componente de custo que mais explica o gap operacional vs. referência."""
    componentes_op = _ber_componentes_operacionais(eq, custo_operacional)
    referencia = _ber_componentes_referencia(eq.item_id, plan_by_item)
    if referencia:
        delta_comp = {k: componentes_op[k] - referencia.get(k, 0.0) for k in componentes_op}
        if gap_operacional < 0:
            # Déficit: dominante é o componente que mais contribui para estouro vs referência.
            positivos = {k: v for k, v in delta_comp.items() if v > 0}
            if positivos:
                return max(positivos.items(), key=lambda kv: kv[1])[0]
        else:
            # Superávit: dominante é o componente com maior economia vs referência.
            economias = {k: -v for k, v in delta_comp.items() if v < 0}
            if economias:
                return max(economias.items(), key=lambda kv: kv[1])[0]
    # Fallback estável quando não há referência por componente.
    return max(componentes_op.items(), key=lambda kv: kv[1])[0]


def _ber_build_rows(eq: Any, pe: Any, plan_by_item: dict) -> tuple[dict, dict]:
    """Constrói (equipe_row, analise_composicional_row) para uma equipe direta."""
    custo_operacional = float(getattr(pe, "custo_operacional_real", 0.0) if pe is not None else eq.custo_total or 0.0)
    custo_venda = float(getattr(pe, "custo_venda_cpu", 0.0) if pe is not None else 0.0)
    gap_operacional = round(custo_venda - custo_operacional, 2)
    # Gap percentual relativo ao custo operacional (mais interpretável para eficiência real).
    gap_pct = (gap_operacional / custo_operacional) if custo_operacional > 0 else 0.0
    dominante = _ber_componente_dominante(eq, custo_operacional, gap_operacional, plan_by_item)

    equipe_row = {
        "equipe_id": eq.equipe_id,
        "item_id": eq.item_id,
        "cpu_id": eq.cpu_id,
        "custo_fixo_total": round(eq.custo_fixo_mensal * (eq.permanencia_meses or 0.0), 2),
        "custo_total": eq.custo_total,
        "permanencia_meses": eq.permanencia_meses,
        "delta_pct": (getattr(pe, "delta_pct", None) if pe is not None else None),
        "status_pe": (getattr(pe, "status_validacao", "N/A") if pe is not None else "N/A"),
        # custo_venda_cpu: None quando não há ponto de equilíbrio calculado para o item
        "custo_venda_cpu": (getattr(pe, "custo_venda_cpu", None) if pe is not None else None),
    }
    analise_row = {
        "item_id": eq.item_id,
        "custo_venda_cpu": round(custo_venda, 2),
        "custo_operacional_real": round(custo_operacional, 2),
        "gap_operacional": gap_operacional,
        "gap_pct": round(gap_pct, 6),
        "dominante": dominante,
        "acao_sugerida": _ber_acao_sugerida(gap_operacional, dominante),
        "custo_mao_obra": eq.custo_mao_obra_mensal,
        "custo_equipamentos": eq.custo_equipamentos_mensal,
        "custo_materiais": eq.custo_material_mensal,
        "custo_diesel": eq.custo_combustivel_total_mensal,
    }
    return equipe_row, analise_row


def _build_equipe_rows(canonical_in: CanonicalModel) -> tuple[list[dict], list[dict]]:
    equipe_rows: list[dict] = []
    analise_composicional: list[dict] = []
    pe_by_item = {pe.item_id: pe for pe in (canonical_in.ponto_equilibrio or []) if pe.item_id}
    plan_by_item = {p.item_id: p for p in canonical_in.planejamento if p.item_id}

    for eq in canonical_in.equipes_diretas:
        pe = pe_by_item.get(eq.item_id)
        equipe_row, analise_row = _ber_build_rows(eq, pe, plan_by_item)
        equipe_rows.append(equipe_row)
        analise_composicional.append(analise_row)
    return equipe_rows, analise_composicional


def _build_indireto_rows(canonical_in: CanonicalModel, inputs: dict[str, Any]) -> list[dict]:
    _ = inputs
    rows: list[dict] = []
    for ind in canonical_in.indiretos:
        rows.append(
            {
                "categoria": ind.categoria,
                "descricao": ind.descricao,
                "permanencia_meses": ind.permanencia_meses,
                "custo_total": ind.custo_total,
            }
        )
    return rows


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
        from ._skill_helpers_b import (  # ty: ignore[unresolved-import]  # runtime-only: sibling loaded via importlib in skill.py
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


def _gerar_excel_bytes(canonical_in: CanonicalModel, validacoes: list, gerar_excel: bool) -> bytes | None:
    if not gerar_excel:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-ADAPTER-EXCEL",
                status="AVISO",
                mensagem="Geração de Excel relatório desabilitada por input 'gerar_excel=false'",
            )
        )
        return None
    try:
        excel_bytes = ExcelRenderer(canonical_in).to_bytes()
        validacoes.append(
            ValidacaoItem(codigo="VAL-ADAPTER-EXCEL", status="OK", mensagem="Excel relatório gerado com sucesso")
        )
        return excel_bytes
    except Exception as e:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-ADAPTER-EXCEL", status="AVISO", mensagem=f"Erro ao gerar Excel relatório: {str(e)}"
            )
        )
        return None


def _gerar_live_model(canonical_in: CanonicalModel, validacoes: list, gerar_modelo_vivo: bool) -> bytes | None:
    """Formulação referencial migrada para MEMORIAL.CATALOGO + REFERÊNCIA no ExcelRenderer.

    O modelo vivo separado (live_model.py) foi descontinuado. As abas MEMORIAL.CATALOGO
    e REFERÊNCIA do adapter principal já expõem os parâmetros de catálogo e a auditoria
    de cálculo que o live_model fornecia.
    """
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-ADAPTER-EXCEL-LIVE",
            status="AVISO",
            mensagem=(
                "Modelo vivo descontinuado. Formulação referencial disponível nas abas "
                "MEMORIAL.CATALOGO e REFERÊNCIA do relatório Excel principal."
            ),
        )
    )
    return None


def _gerar_memorial_json_bytes(canonical_in: CanonicalModel) -> bytes | None:
    if canonical_in.memorial_calculo_bdi is None:
        return None
    try:
        import json as _json

        return _json.dumps(
            canonical_in.memorial_calculo_bdi.to_dict(), indent=2, ensure_ascii=False, default=str
        ).encode("utf-8")
    except Exception as _mem_exc:
        import logging as _logging

        _logging.getLogger(__name__).warning("memorial_bdi.json falhou: %s", _mem_exc)
        return None


def _rra_build_criticidade_lookup(canonical_in: CanonicalModel) -> dict[str, str]:
    """Builds criticidade_lookup from cost_criticality_report."""
    lookup: dict[str, str] = {}
    if canonical_in.cost_criticality_report is not None:
        for prof in canonical_in.cost_criticality_report.atividades:
            lookup[prof.atividade_id] = prof.classe
    return lookup


def _rra_safe_float(value: Any) -> float:
    """Converte para float com fallback seguro (None/erro -> 0.0)."""
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def _rra_particao_by_item(canonical_in: CanonicalModel) -> dict[str, dict[str, float]]:
    """Agrega custo produtivo/mob_demob/ociosidade particionado por item a partir dos contratos."""
    _f = _rra_safe_float
    particao_by_item: dict[str, dict[str, float]] = {}
    for contrato in canonical_in.contratos_recurso or []:
        for part in getattr(contrato, "particao_por_item", None) or []:
            item_id = getattr(part, "item_id", None)
            if not item_id:
                continue
            acc = particao_by_item.setdefault(
                item_id,
                {
                    "produtivo": 0.0,
                    "mob_demob": 0.0,
                    "ociosidade": 0.0,
                },
            )
            acc["produtivo"] += _f(getattr(part, "custo_produtivo", 0.0))
            acc["mob_demob"] += _f(getattr(part, "custo_mob_imputado", 0.0)) + _f(
                getattr(part, "custo_demob_imputado", 0.0)
            )
            acc["ociosidade"] += _f(getattr(part, "custo_ocioso_imputado", 0.0))
    return particao_by_item


def _rra_totais_globais(
    canonical_in: CanonicalModel, resultado_section: dict[str, Any] | None
) -> tuple[float, float, float]:
    """Resolve venda/custo_direto/custo_indireto globais, com fallback para canonical_in.resultado."""
    _f = _rra_safe_float
    venda_global = _f((resultado_section or {}).get("preco_venda_total"))
    custo_direto_global = _f((resultado_section or {}).get("custo_direto"))
    custo_indireto_global = _f((resultado_section or {}).get("custo_indireto"))

    if venda_global <= 0 and canonical_in.resultado is not None:
        venda_global = _f(canonical_in.resultado.venda.total_com_bdi)
    if custo_direto_global <= 0 and canonical_in.resultado is not None:
        custo_direto_global = _f(canonical_in.resultado.custo.direto_equipes)
    if custo_indireto_global <= 0 and canonical_in.resultado is not None:
        custo_indireto_global = (
            _f(canonical_in.resultado.custo.indireto_adm)
            + _f(canonical_in.resultado.custo.indireto_top)
            + _f(canonical_in.resultado.custo.indireto_lab)
            + _f(canonical_in.resultado.custo.indireto_qsms)
            + _f(canonical_in.resultado.custo.indireto_mob)
        )
    return venda_global, custo_direto_global, custo_indireto_global


def _rra_gap_particionado(
    deficit: float, custo_produtivo: float, custo_mob_demob: float, custo_ociosidade: float
) -> tuple[float, float, float]:
    """Rateia o déficit operacional pelos componentes de custo particionados por item."""
    base_particao = custo_produtivo + custo_mob_demob + custo_ociosidade
    if deficit > 0 and base_particao > 0:
        gap_produtivo = deficit * (custo_produtivo / base_particao)
        gap_mob_demob = deficit * (custo_mob_demob / base_particao)
        gap_ociosidade = deficit * (custo_ociosidade / base_particao)
    else:
        gap_produtivo = 0.0
        gap_mob_demob = 0.0
        gap_ociosidade = 0.0
    return gap_produtivo, gap_mob_demob, gap_ociosidade


def _rra_build_pe_row(
    pe: Any,
    venda_global: float,
    custo_direto_global: float,
    custo_indireto_global: float,
    soma_venda_itens: float,
    n_items: int,
    particao_by_item: dict[str, dict[str, float]],
) -> dict:
    """Constrói uma linha da tabela ponto_equilibrio com margens reconciliadas e gap decomposto."""
    _f = _rra_safe_float
    venda_item = _f(pe.custo_venda_cpu)
    op_item = _f(getattr(pe, "custo_operacional_real", 0.0))
    gap_operacional = venda_item - op_item
    margem_operacional_direta = (gap_operacional / venda_item) if venda_item > 0 else 0.0

    share_receita = (venda_item / soma_venda_itens) if soma_venda_itens > 0 else (1.0 / n_items)
    receita_atribuida = venda_global * share_receita
    custo_direto_atribuido = custo_direto_global * share_receita
    custo_indireto_atribuido = custo_indireto_global * share_receita
    resultado_total_atribuido = receita_atribuida - custo_direto_atribuido - custo_indireto_atribuido
    margem_total_atribuida = (resultado_total_atribuido / receita_atribuida) if receita_atribuida > 0 else 0.0

    part = particao_by_item.get(pe.item_id, {})
    custo_produtivo = _f(part.get("produtivo", 0.0))
    custo_mob_demob = _f(part.get("mob_demob", 0.0))
    custo_ociosidade = _f(part.get("ociosidade", 0.0))

    deficit = max(0.0, op_item - venda_item)
    gap_produtivo, gap_mob_demob, gap_ociosidade = _rra_gap_particionado(
        deficit, custo_produtivo, custo_mob_demob, custo_ociosidade
    )

    return {
        "item_id": pe.item_id,
        "custo_fixo_equipe": pe.custo_fixo_equipe,
        "custo_operacional_real": round(op_item, 2),
        "custo_venda_cpu": round(venda_item, 2),
        "frentes_equivalentes": getattr(pe, "frentes_equivalentes", 1.0),
        "status_validacao": pe.status_validacao,
        "margem_operacional_direta": round(margem_operacional_direta, 6),
        "margem_total_atribuida": round(margem_total_atribuida, 6),
        "receita_atribuida": round(receita_atribuida, 2),
        "custo_direto_atribuido": round(custo_direto_atribuido, 2),
        "custo_indireto_atribuido": round(custo_indireto_atribuido, 2),
        "resultado_total_atribuido": round(resultado_total_atribuido, 2),
        "gap_operacional": round(gap_operacional, 2),
        "gap_produtivo": round(gap_produtivo, 2),
        "gap_mob_demob": round(gap_mob_demob, 2),
        "gap_ociosidade": round(gap_ociosidade, 2),
        "custo_produtivo_particionado": round(custo_produtivo, 2),
        "custo_mob_demob_particionado": round(custo_mob_demob, 2),
        "custo_ociosidade_particionado": round(custo_ociosidade, 2),
        # NEP-042: três camadas de precificação
        "pu_cat": _f(getattr(pe, "pu_catalogo_unitario", 0.0)),
        "pu_op_autonomo": _f(getattr(pe, "pu_operacional_autonomo", 0.0)),
        "frentes_necessarias": _f(getattr(pe, "frentes_equivalentes_necessarias", 1.0)),
        "eta_real": _f(getattr(pe, "eta_real", 1.0)),
        "machine_weeks_brutas": _f(getattr(pe, "machine_weeks_brutas", 0.0)),
        "machine_weeks_efetivas": _f(getattr(pe, "machine_weeks_efetivas", 0.0)),
        "burden_pool": _f(getattr(pe, "custo_pool_total", 0.0)),
        "economia_pool_abs": _f(getattr(pe, "economia_pool_abs", 0.0)),
    }


def _rra_build_pe_rows(canonical_in: CanonicalModel, resultado_section: dict[str, Any] | None = None) -> list[dict]:
    """Builds ponto_equilibrio list for report with reconciled margins and gap decomposition."""

    pe_items = list(canonical_in.ponto_equilibrio or [])
    if not pe_items:
        return []

    particao_by_item = _rra_particao_by_item(canonical_in)
    venda_global, custo_direto_global, custo_indireto_global = _rra_totais_globais(canonical_in, resultado_section)

    soma_venda_itens = sum(_rra_safe_float(pe.custo_venda_cpu) for pe in pe_items)
    n_items = max(1, len(pe_items))

    return [
        _rra_build_pe_row(
            pe,
            venda_global,
            custo_direto_global,
            custo_indireto_global,
            soma_venda_itens,
            n_items,
            particao_by_item,
        )
        for pe in pe_items
    ]


def _rrs_num(value: Any) -> float | None:
    """Converte para float, retornando None em caso de valor ausente ou inválido."""
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _rrs_delta_pct(tool: float, ref: float) -> float | None:
    """Calcula a variação percentual da ferramenta em relação à referência."""
    return round((tool - ref) / ref * 100, 2) if ref and ref > 0 else None


def _rrs_custo_indireto_calc(res: Any) -> float:
    """Soma os componentes de custo indireto (adm/top/lab/qsms/mob) do resultado."""
    return (
        float(res.custo.indireto_adm or 0.0)
        + float(res.custo.indireto_top or 0.0)
        + float(res.custo.indireto_lab or 0.0)
        + float(res.custo.indireto_qsms or 0.0)
        + float(res.custo.indireto_mob or 0.0)
    )


def _rrs_preco_venda_e_custo_total(
    res: Any, custo_direto_auth: float, custo_indireto_calc: float
) -> tuple[float, float]:
    """Calcula preco_venda_total (operacional) e custo_total_calc (canônico, com fallback local)."""
    # ADR-085/ADR-114: preço de venda é o OPERACIONAL (total_custo_plus = custo_instancial×BDI + indiretos),
    # NÃO o de catálogo (total_com_bdi = PU_catalogo×Q×BDI). A margem é calculada sobre o preço que
    # a empresa cobra pelo que realmente executa — o catálogo serve como referência de mercado, não
    # como base de precificação operacional.
    preco_venda_total = float(
        getattr(res.venda, "total_custo_plus", None) or getattr(res.venda, "total_com_bdi", None) or 0.0
    )
    # Usar custo.total do modelo como fonte autoritativa (inclui todos os componentes
    # calculados por skill-08). Fallback para recálculo local apenas quando ausente.
    custo_total_canonical = float(res.custo.total or 0.0) if res.custo.total else None
    custo_total_calc = (
        custo_total_canonical if custo_total_canonical is not None else custo_direto_auth + custo_indireto_calc
    )
    return preco_venda_total, custo_total_calc


def _rrs_compute_custos(res: Any) -> tuple[float, float, float, float, float]:
    """Calcula direto_equipes, custo_direto_auth, custo_indireto_calc, preco_venda_total e custo_total_calc."""
    direto_equipes = float(res.custo.direto_equipes or 0.0)
    # Fonte autoritativa única do relatório: custo direto operacional instancial (direto_equipes).
    custo_direto_auth = direto_equipes

    custo_indireto_calc = _rrs_custo_indireto_calc(res)
    preco_venda_total, custo_total_calc = _rrs_preco_venda_e_custo_total(res, custo_direto_auth, custo_indireto_calc)
    return direto_equipes, custo_direto_auth, custo_indireto_calc, preco_venda_total, custo_total_calc


def _rrs_compute_razao_margem(
    custo_direto_auth: float, custo_indireto_calc: float, preco_venda_total: float, custo_total_calc: float
) -> tuple[float, float]:
    """Calcula razao_indireto_direto e margem_pct a partir dos valores centrais do resultado."""
    # Valores calculados são sempre a fonte primária do relatório (NEP-030).
    # A referência fica armazenada separadamente para a seção de confronto.
    razao_id = custo_indireto_calc / custo_direto_auth if custo_direto_auth > 0 else 0
    margem_pct = (preco_venda_total - custo_total_calc) / preco_venda_total if preco_venda_total > 0 else 0
    return razao_id, margem_pct


def _rrs_compute_core(res: Any) -> tuple[float, float, float, float, float, float, float]:
    """Calcula os valores centrais (custos, preço de venda, razão e margem) do resultado."""
    direto_equipes, custo_direto_auth, custo_indireto_calc, preco_venda_total, custo_total_calc = _rrs_compute_custos(
        res
    )
    razao_id, margem_pct = _rrs_compute_razao_margem(
        custo_direto_auth, custo_indireto_calc, preco_venda_total, custo_total_calc
    )
    return (
        direto_equipes,
        custo_direto_auth,
        custo_indireto_calc,
        preco_venda_total,
        custo_total_calc,
        razao_id,
        margem_pct,
    )


def _rrs_build_referencia(
    benchmark_reference_projection: dict[str, Any] | None,
    custo_direto_auth: float,
    custo_indireto_calc: float,
    preco_venda_total: float,
) -> dict | None:
    """Extrai a seção de confronto (apenas exibição) a partir da projeção de referência."""
    if not isinstance(benchmark_reference_projection, dict):
        return None
    ref_direto = _rrs_num(benchmark_reference_projection.get("custo_direto"))
    ref_indireto = _rrs_num(benchmark_reference_projection.get("custo_indireto"))
    ref_total = _rrs_num(benchmark_reference_projection.get("custo_total"))
    ref_preco = _rrs_num(benchmark_reference_projection.get("preco_venda"))
    if not (ref_preco and ref_preco > 0):
        return None
    return {
        "custo_direto": ref_direto,
        "custo_indireto": ref_indireto,
        "custo_total": ref_total,
        "preco_venda": ref_preco,
        "delta_custo_direto_pct": _rrs_delta_pct(custo_direto_auth, ref_direto) if ref_direto else None,
        "delta_custo_indireto_pct": _rrs_delta_pct(custo_indireto_calc, ref_indireto) if ref_indireto else None,
        "delta_preco_venda_pct": _rrs_delta_pct(preco_venda_total, ref_preco),
    }


def _rra_build_resultado_section(
    res: Any,
    benchmark_mode: bool = False,
    benchmark_reference_projection: dict[str, Any] | None = None,
) -> dict:
    """Builds resultado section dict."""
    (
        direto_equipes,
        custo_direto_auth,
        custo_indireto_calc,
        preco_venda_total,
        custo_total_calc,
        razao_id,
        margem_pct,
    ) = _rrs_compute_core(res)
    custo_direto_fonte = "operacional_equipes"

    referencia = _rrs_build_referencia(
        benchmark_reference_projection, custo_direto_auth, custo_indireto_calc, preco_venda_total
    )

    return {
        "preco_venda_total": preco_venda_total,
        "custo_total": custo_total_calc,
        "custo_direto": custo_direto_auth,
        "custo_direto_equipes": direto_equipes,
        "custo_direto_fonte": custo_direto_fonte,
        "benchmark_guard_aplicado": False,  # guard removido (NEP-030)
        "custo_indireto": custo_indireto_calc,
        "razao_indireto_direto": razao_id,
        "resultado_bruto": preco_venda_total - custo_total_calc,
        "margem_pct": margem_pct,
        "status_margem": res.status_margem,
        "referencia": referencia,
    }


def _rra_build_actionable_insights(canonical_in: Any) -> dict:
    """Builds ACTIONABLE_INSIGHTS dict."""

    def _dump(obj: Any) -> Any:
        return obj.model_dump(mode="json") if obj else None

    return {
        "criticidade": _dump(canonical_in.relatorio_criticidade),
        "sensibilidade": _dump(canonical_in.relatorio_sensibilidade),
        "intervencao": _dump(canonical_in.relatorio_intervencao),
    }


def _rra_build_relatorio(
    canonical_in: Any,
    proj: Any,
    res: Any,
    planejamento_rows: list,
    equipe_rows: list,
    analise_composicional: list,
    indireto_rows: list,
    graficos: Any,
    eap_by_item_id: dict,
    project_months: list,
    benchmark_mode: bool = False,
    benchmark_reference_projection: dict[str, Any] | None = None,
) -> dict:
    """Assembles the full relatorio dict."""
    resultado_section = _rra_build_resultado_section(
        res,
        benchmark_mode=benchmark_mode,
        benchmark_reference_projection=benchmark_reference_projection,
    )
    validacoes_pipeline = [{"codigo": v.codigo, "status": v.status, "mensagem": v.mensagem} for v in res.validacoes]
    return {
        "meta": {
            "gerado_em": datetime.now(UTC).isoformat(),
            "framework": "concilium",
            "adapter": "relatorio_validacao_v1",
            "nota": "Relatório de validação na ausência do template .xlsm original.",
        },
        "resumo": {
            "projeto": proj.nome,
            "tipo_obra": proj.tipo_obra,
            "localizacao": (
                f"lat={proj.localizacao.lat:.5f}, lng={proj.localizacao.lng:.5f}"
                if hasattr(proj.localizacao, "lat")
                else proj.localizacao
            ),
            "periodo": f"{proj.data_inicio} -> {proj.data_termino}",
            "status": proj.status,
        },
        "PLANEJAMENTO": planejamento_rows,
        "EQUIPE": equipe_rows,
        "analise_composicional": analise_composicional,
        "INDIRETOS": indireto_rows,
        "RESULTADO": resultado_section,
        "GRAFICOS": graficos,
        "ponto_equilibrio": _rra_build_pe_rows(canonical_in, resultado_section),
        # NEP-042 D4: view consolidada das três camadas de precificação por item
        "PRECO_UNITARIO_TRES_CAMADAS": _build_tres_camadas_rows(canonical_in),
        "ACTIONABLE_INSIGHTS": _rra_build_actionable_insights(canonical_in),
        "validacoes_pipeline": validacoes_pipeline,
        # ADR-077: mapa instancial de utilização
        "resumo_utilizacao_contratos": [r.model_dump() for r in (canonical_in.resumo_utilizacao_contratos or [])],
        "instancias_recurso": [i.model_dump() for i in (canonical_in.instancias_recurso or [])],
        # ADR-086: decomposição explorável de pool (faces físicas + causais + narrativa honesta)
        "decomposicao_pool": _rra_build_decomposicao_pool(canonical_in),
        # ADR-078: pré-processamento estrutural de compartilhamento
        "relatorio_oportunidades": (
            canonical_in.relatorio_oportunidades.model_dump() if canonical_in.relatorio_oportunidades else None
        ),
        # NEP-038: análise de compressão de cronograma por k-scaling
        "COMPRESSAO_CRONOGRAMA": _rra_build_compressao_cronograma(canonical_in),
    }


def _rcc_build_scheduled_activities(cronograma: Any) -> list:
    """Reconstrói a lista de ScheduledActivity a partir do cronograma canônico."""
    from concilium.application.scheduling import ScheduledActivity

    return [
        ScheduledActivity(
            activity_id=sa.activity_id,
            start_week=sa.start_week,
            end_week=sa.end_week,
            duration_weeks=sa.duration_weeks,
            assigned_resources=dict(sa.assigned_resources or {}),
            ramp_profile=sa.ramp_profile,
        )
        for sa in cronograma.scheduled_activities
        if sa.assigned_resources
    ]


def _rcc_build_schedule_output(sched_acts_sched: list, makespan: int) -> Any:
    """Constrói o ScheduleOutput (com métricas) a partir das atividades reconstruídas."""
    from concilium.application.scheduling import ScheduleMetrics, ScheduleOutput

    metrics = ScheduleMetrics(
        makespan=makespan,
        resource_leveling_score=0.0,
        idle_time=0,
        activity_fragmentation=0,
        critical_path_slack_min=0.0,
        resource_utilization_avg=0.0,
    )
    return ScheduleOutput(
        scheduled_activities=sched_acts_sched,
        makespan=makespan,
        feasible=True,
        metrics=metrics,
    )


def _rcc_add_predecessor(
    pred: Any,
    iid: str,
    aid_set: set[str],
    prec: list[tuple[str, str]],
    thresh: dict[tuple[str, str], float],
) -> None:
    """Adiciona (in-place) a precedência tipada de `pred` -> `iid`, se válida e ainda não presente."""
    pid = getattr(pred, "predecessor_id", None) or getattr(pred, "item_id", None)
    if pid and pid in aid_set and (pid, iid) not in set(prec):
        prec.append((pid, iid))
        th = getattr(pred, "completion_threshold_pct", None) or getattr(pred, "threshold", None) or 1.0
        thresh[(pid, iid)] = float(th)


def _rcc_build_precedencias(
    canonical_in: CanonicalModel, aid_set: set[str]
) -> tuple[list[tuple[str, str]], dict[tuple[str, str], float]]:
    """Extrai as precedências tipadas (e thresholds) da EAP restritas ao conjunto de activity_ids."""
    prec: list[tuple[str, str]] = []
    thresh: dict[tuple[str, str], float] = {}
    for item in canonical_in.eap or []:
        iid = item.item_id
        if iid not in aid_set:
            continue
        for pred in item.predecessores or []:
            _rcc_add_predecessor(pred, iid, aid_set, prec, thresh)
    return prec, thresh


def _rcc_build_dag(canonical_in: CanonicalModel, sched_acts_sched: list) -> Any:
    """Reconstrói a ActivityDAG (atividades + precedências tipadas) a partir do canônico."""
    from concilium.application.scheduling import Activity, ActivityDAG

    acts = [
        Activity(
            activity_id=sa.activity_id,
            description=sa.activity_id,
            duration_weeks=sa.duration_weeks,
            required_resources=dict(sa.assigned_resources or {}),
        )
        for sa in sched_acts_sched
    ]
    aid_set = {a.activity_id for a in acts}
    prec, thresh = _rcc_build_precedencias(canonical_in, aid_set)

    return ActivityDAG(activities=acts, precedence=prec, thresholds=thresh)


def _rcc_build_pool(sched_acts_sched: list, contratos_raw: list) -> Any:
    """Monta o ResourcePool base a partir das alocações e do piso contratual."""
    from concilium.application.scheduling import ResourcePool

    pool_resources: dict[str, int] = {}
    for sa in sched_acts_sched:
        for r, n in (sa.assigned_resources or {}).items():
            pool_resources[r] = max(pool_resources.get(r, 0), n)
    # Aplica pool dos contratos como piso
    for ct in contratos_raw:
        tid = getattr(ct, "tipo_id", None)
        qty = getattr(ct, "quantidade_contratada", None) or getattr(ct, "pool_size", None) or 0
        if tid and int(qty or 0) > 0:
            pool_resources[tid] = max(pool_resources.get(tid, 0), int(qty))
    return ResourcePool(resources=pool_resources)


def _rcc_build_contratos_dict(contratos_raw: list) -> dict[str, dict]:
    """Monta o dict de custos de instância por tipo de contrato de recurso."""
    contratos_dict: dict[str, dict] = {}
    for ct in contratos_raw:
        tid = getattr(ct, "tipo_id", None)
        if not tid:
            continue
        contratos_dict[tid] = {
            "custo_mob_unit": float(getattr(ct, "custo_mob_unit", 0) or 0),
            "custo_demob_unit": float(getattr(ct, "custo_demob_unit", 0) or 0),
            "custo_idle_semanal_unit": float(
                getattr(ct, "custo_idle_semanal_unit", None) or getattr(ct, "custo_standby_unit", 0) or 0
            ),
        }
    return contratos_dict


def _rcc_compute_preco_venda(canonical_in: CanonicalModel) -> float:
    """Extrai o preço de venda total do resultado, priorizando preco_venda_total."""
    res = canonical_in.resultado
    preco_venda = 0.0
    if res:
        for attr in ("preco_venda_total", "total_com_bdi"):
            v = getattr(res, attr, None)
            if v and float(v) > 0:
                preco_venda = float(v)
                break
    return preco_venda


def _rcc_serialize_itens(results: list) -> list[dict]:
    """Serializa os resultados de compute_compression_sensitivities em entradas do relatório."""
    itens = []
    for r in results:
        entry: dict[str, Any] = {
            "activity_id": r.activity_id,
            "tipo_recurso": r.tipo_recurso_bottleneck,
            "n_base": r.n_base,
            "duration_base": r.duration_base,
            "float_rcpsp": round(r.float_rcpsp, 1),
            "float_cpm": round(r.float_cpm, 1),
            "criticality_class": r.criticality_class,
            "k_otimo": r.best_k,
            "gamma_otimo": round(r.max_gamma, 3) if r.best_k else None,
            "delta_makespan": r.by_k[r.best_k].delta_makespan if r.best_k else 0,
            "poupanca": round(r.by_k[r.best_k].poupanca) if r.best_k else 0,
            "roi": round(r.by_k[r.best_k].roi, 1) if r.best_k and r.by_k[r.best_k].roi < 1e9 else None,
            "by_k": {
                str(k): {
                    "duration_new": kr.duration_new,
                    "makespan_new": kr.makespan_new,
                    "delta_makespan": kr.delta_makespan,
                    "gamma": round(kr.gamma, 3),
                    "cost_extra": round(kr.cost_extra),
                    "poupanca": round(kr.poupanca),
                    "roi": round(kr.roi, 1) if kr.roi < 1e9 else None,
                    "viable": kr.viable,
                }
                for k, kr in r.by_k.items()
            },
        }
        itens.append(entry)
    return itens


def _rcc_prepare_context(canonical_in: CanonicalModel) -> tuple | None:
    """Monta o contexto (schedule/DAG/pool/contratos/custo_semana) para a análise de compressão.

    Retorna None quando faltam pré-requisitos (cronograma, contratos, ortools ou preço de venda
    válido) — os mesmos guards que existiam inline em _rra_build_compressao_cronograma.
    """
    cronograma = canonical_in.cronograma
    if not cronograma or not cronograma.scheduled_activities:
        return None

    contratos_raw = canonical_in.contratos_recurso or []
    if not contratos_raw:
        return None

    try:
        from concilium.application.scheduling import (
            compute_compression_sensitivities,
            format_compression_table,
        )
        from concilium.application.scheduling.cpsat_scheduler import (
            CpSatScheduler,  # noqa: F401 – verifica que ortools está disponível
        )
    except ImportError:
        return None

    makespan = cronograma.makespan_weeks

    # ── Reconstrói ScheduleOutput ────────────────────────────────────────────
    sched_acts_sched = _rcc_build_scheduled_activities(cronograma)
    if not sched_acts_sched:
        return None

    sched_output = _rcc_build_schedule_output(sched_acts_sched, makespan)

    # ── Reconstrói ActivityDAG ───────────────────────────────────────────────
    dag = _rcc_build_dag(canonical_in, sched_acts_sched)

    # ── Pool base ────────────────────────────────────────────────────────────
    pool = _rcc_build_pool(sched_acts_sched, contratos_raw)

    # ── Contratos para custo de instâncias ───────────────────────────────────
    contratos_dict = _rcc_build_contratos_dict(contratos_raw)

    # ── custo_semana ────────────────────────────────────────────────────────
    preco_venda = _rcc_compute_preco_venda(canonical_in)
    if preco_venda <= 0:
        return None
    custo_semana = preco_venda / makespan

    return (
        makespan,
        sched_output,
        dag,
        pool,
        contratos_dict,
        custo_semana,
        compute_compression_sensitivities,
        format_compression_table,
    )


def _rcc_serialize_relatorio(results: list, makespan: int, custo_semana: float, format_compression_table: Any) -> dict:
    """Serializa a lista de results de compute_compression_sensitivities no dict do relatório."""
    viáveis = [r for r in results if r.best_k is not None]
    makespan_otimo = (
        min(r.by_k[bk].makespan_new for r in viáveis if (bk := r.best_k) is not None) if viáveis else makespan
    )

    itens = _rcc_serialize_itens(results)

    return {
        "makespan_base": makespan,
        "makespan_otimo": makespan_otimo,
        "delta_makespan_max": makespan - makespan_otimo,
        "custo_semana": round(custo_semana),
        "poupanca_total_max": round((makespan - makespan_otimo) * custo_semana),
        "n_viáveis": len(viáveis),
        "itens": itens,
        "tabela_texto": format_compression_table(results),
    }


def _rra_build_compressao_cronograma(canonical_in: CanonicalModel) -> dict | None:
    """NEP-038: análise de compressão de cronograma por k-scaling de equipes.

    Reconstrói ScheduleOutput + ActivityDAG a partir do canônico e chama
    compute_compression_sensitivities com CP-SAT.

    Retorna None quando não há cronograma ou contratos suficientes.
    Falhas do CP-SAT são silenciosas (retorna None) para não bloquear o relatório.
    """
    ctx = _rcc_prepare_context(canonical_in)
    if ctx is None:
        return None
    (
        makespan,
        sched_output,
        dag,
        pool,
        contratos_dict,
        custo_semana,
        compute_compression_sensitivities,
        format_compression_table,
    ) = ctx

    # ── Roda análise ────────────────────────────────────────────────────────
    try:
        results = compute_compression_sensitivities(
            sched_output=sched_output,
            dag=dag,
            pool=pool,
            contratos=contratos_dict,
            custo_semana=custo_semana,
            k_values=(2, 3),
            scheduler_timeout=30.0,
        )
    except Exception:
        return None

    if not results:
        return None

    # ── Serializa para o dict do relatório ───────────────────────────────────
    return _rcc_serialize_relatorio(results, makespan, custo_semana, format_compression_table)


def _rra_build_decomposicao_pool(canonical_in: CanonicalModel) -> dict | None:
    """ADR-086: seção de decomposição explorável de pool de recursos.

    Agrega as faces-chave (ciclo de vida, custo por estado×componente, economia vs. autônomo,
    cadeias de perpetuação) com narrativa honesta. Retorna None quando não há pool.
    """
    if not (canonical_in.contratos_recurso or canonical_in.instancias_recurso):
        return None
    try:
        from concilium.application.services.analytics.cubo_pool_projection import (
            resolve_cubo_pool_projection,
        )
    except Exception:
        return None

    faces = [
        "instancia_ciclo_vida",
        "custo_estado_componente",
        "economia_pool",
        "cadeia_perpetuacao",
    ]
    secoes: dict[str, dict] = {}
    primeiro_totais: dict | None = None
    for face in faces:
        try:
            proj = resolve_cubo_pool_projection(canonical_in, face=face, granularidade="mes")
        except Exception:
            continue
        if primeiro_totais is None:
            primeiro_totais = proj.get("totais")
        secoes[face] = {
            "natureza": proj.get("natureza"),
            "columns": proj.get("columns"),
            "rows": proj.get("rows"),
            "narrativa": proj.get("narrativa"),
            "operator_meta": proj.get("operator_meta"),
        }
    if not secoes:
        return None
    return {
        "totais": primeiro_totais,
        "faces": secoes,
        "nota": (
            "Decomposição honesta: faces físicas descrevem o que cada slot fez (prod/ocioso/off); "
            "faces causais imputam custo a atividades com baseline autônomo explícito (ADR-086)."
        ),
    }


def _cash_flow_rows(canonical_in: CanonicalModel, project_months: list[tuple[int, int]]) -> list[dict]:
    if not project_months:
        return []
    receita_total = float(canonical_in.resultado.venda.total_com_bdi) if canonical_in.resultado else 0.0
    despesa_total = float(canonical_in.resultado.custo.total) if canonical_in.resultado else 0.0
    n = max(1, len(project_months))
    rec_m = receita_total / n
    des_m = despesa_total / n
    acc = 0.0
    rows: list[dict] = []
    for ym in project_months:
        saldo = rec_m - des_m
        acc += saldo
        rows.append(
            {
                "mes": ym,
                "mes_label": _fmt_mes(ym),
                "receita": round(rec_m, 2),
                "despesa": round(des_m, 2),
                "saldo": round(saldo, 2),
                "exposicao": round(acc, 2),
            }
        )
    return rows


def _week_to_month(week_key: str) -> tuple[int, int]:
    year_str, week_str = week_key.split("-W")
    monday = date.fromisocalendar(int(year_str), int(week_str), 1)
    return monday.year, monday.month


def _fmt_mes(ym: tuple[int, int]) -> str:
    return f"{_MESES_PT[ym[1]]}/{str(ym[0])[-2:]}"


def _next_month(ym: tuple[int, int]) -> tuple[int, int]:
    year, month = ym
    return (year + 1, 1) if month == 12 else (year, month + 1)
