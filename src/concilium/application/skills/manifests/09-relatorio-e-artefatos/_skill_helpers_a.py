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

from concilium.domain.models.canonical import CanonicalModel, ValidacaoItem
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


def _build_planejamento_rows(
    canonical_in: CanonicalModel, criticidade_lookup: dict[str, str], has_criticidade: bool
) -> list[dict]:
    rows: list[dict] = []
    eap_by_item_id = {e.item_id: e for e in canonical_in.eap}
    for p in canonical_in.planejamento:
        eap_item = eap_by_item_id.get(p.item_id)
        row = {
            "item_id": p.item_id,
            "cpu_id": p.cpu_id,
            "descricao": (eap_item.descricao if eap_item else ""),
            "unidade": (eap_item.unidade if eap_item else ""),
            "quantitativo": p.quantitativo,
            "subtotal_sem_bdi_mo": p.subtotal.sem_bdi.mao_obra,
            "subtotal_sem_bdi_eq": p.subtotal.sem_bdi.equipamentos,
            "subtotal_sem_bdi_diesel": p.subtotal.sem_bdi.diesel,
            "subtotal_sem_bdi_mat": p.subtotal.sem_bdi.material,
            "subtotal_sem_bdi": p.subtotal.sem_bdi.total,
            "subtotal_com_bdi": p.subtotal.com_bdi.total,
            "pu_total_sem_bdi": p.preco_unitario.total,
            "pu_total_com_bdi": p.preco_unitario_com_bdi.total,
        }
        if has_criticidade:
            row["criticidade"] = criticidade_lookup.get(p.item_id, "-")
        rows.append(row)
    return rows


def _build_equipe_rows(canonical_in: CanonicalModel) -> tuple[list[dict], list[dict]]:
    equipe_rows: list[dict] = []
    analise_composicional: list[dict] = []
    pe_by_item = {pe.item_id: pe for pe in (canonical_in.ponto_equilibrio or []) if pe.item_id}
    plan_by_item = {p.item_id: p for p in canonical_in.planejamento if p.item_id}

    def _acao_sugerida(gap: float, dominante: str) -> str:
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

    def _componentes_operacionais(eq: Any, custo_operacional: float) -> dict[str, float]:
        mensal = {
            "Mão de Obra": float(eq.custo_mao_obra_mensal or 0.0),
            "Equipamentos": float(eq.custo_equipamentos_mensal or 0.0),
            "Materiais": float(eq.custo_material_mensal or 0.0),
            "Diesel": float(eq.custo_combustivel_total_mensal or 0.0),
        }
        base = sum(mensal.values())
        if base <= 0 or custo_operacional <= 0:
            return {k: 0.0 for k in mensal}
        fator = custo_operacional / base
        return {k: v * fator for k, v in mensal.items()}

    def _componentes_referencia(item_id: str) -> dict[str, float] | None:
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

    def _componente_dominante(eq: Any, custo_operacional: float, gap_operacional: float) -> str:
        componentes_op = _componentes_operacionais(eq, custo_operacional)
        referencia = _componentes_referencia(eq.item_id)
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

    for eq in canonical_in.equipes_diretas:
        pe = pe_by_item.get(eq.item_id)
        custo_operacional = float(
            getattr(pe, "custo_operacional_real", 0.0) if pe is not None else eq.custo_total or 0.0
        )
        custo_venda = float(getattr(pe, "custo_venda_cpu", 0.0) if pe is not None else 0.0)
        gap_operacional = round(custo_venda - custo_operacional, 2)
        # Gap percentual relativo ao custo operacional (mais interpretável para eficiência real).
        gap_pct = (gap_operacional / custo_operacional) if custo_operacional > 0 else 0.0
        dominante = _componente_dominante(eq, custo_operacional, gap_operacional)
        equipe_rows.append(
            {
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
        )
        analise_composicional.append(
            {
                "item_id": eq.item_id,
                "custo_venda_cpu": round(custo_venda, 2),
                "custo_operacional_real": round(custo_operacional, 2),
                "gap_operacional": gap_operacional,
                "gap_pct": round(gap_pct, 6),
                "dominante": dominante,
                "acao_sugerida": _acao_sugerida(gap_operacional, dominante),
                "custo_mao_obra": eq.custo_mao_obra_mensal,
                "custo_equipamentos": eq.custo_equipamentos_mensal,
                "custo_materiais": eq.custo_material_mensal,
                "custo_diesel": eq.custo_combustivel_total_mensal,
            }
        )
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
    equip_totals[wk] = equip_totals.get(wk, 0.0) + sum(
        (n / min_units) * float(e.num_unidades or 0.0) for e in eq.equipamentos
    )
    mo_totals[wk] = mo_totals.get(wk, 0.0) + sum((n / min_units) * float(f.num_pessoas or 0.0) for f in eq.funcoes)
    if equip_by_id is not None:
        for e in eq.equipamentos:
            eid = e.descricao or e.equip_id or "?"
            equip_by_id.setdefault(eid, {})
            equip_by_id[eid][wk] = equip_by_id[eid].get(wk, 0.0) + (n / min_units) * float(e.num_unidades or 0.0)
    if mo_by_funcao is not None:
        for f in eq.funcoes:
            fid = f.descricao or f.funcao_id or "?"
            mo_by_funcao.setdefault(fid, {})
            mo_by_funcao[fid][wk] = mo_by_funcao[fid].get(wk, 0.0) + (n / min_units) * float(f.num_pessoas or 0.0)


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
    eq_section: dict = {
        "labels": [str(wk) for wk in eq_wks],
        "values": [equip_totals[wk] for wk in eq_wks],
    }
    if equip_by_id:
        eq_section["by_type"] = {eid: [wk_map.get(wk, 0.0) for wk in eq_wks] for eid, wk_map in equip_by_id.items()}
    mo_section: dict = {
        "labels": [str(wk) for wk in mo_wks],
        "values": [mo_totals[wk] for wk in mo_wks],
    }
    if mo_by_funcao:
        mo_section["by_funcao"] = {fid: [wk_map.get(wk, 0.0) for wk in mo_wks] for fid, wk_map in mo_by_funcao.items()}
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
        from ._skill_helpers_b import _cash_flow_rows as _cash_flow_rows_proportional

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
            # Minimality: nenhum subconjunto próprio já cobre o target
            is_minimal = not any(
                sum(levers[j]["delta_margin_total"] for j in sub) >= target
                for sub_size in range(1, size)
                for sub in _combns(combo, sub_size)
            )
            if is_minimal:
                result.append(
                    {
                        "tier": size,
                        "levers_ids": [levers[i]["id"] for i in combo],
                        "delta_disponivel": round(soma, 2),
                        "cobertura_pct": round(soma / target * 100, 1),
                    }
                )
    return sorted(result, key=lambda x: (x["tier"], x["cobertura_pct"]))


def _bgs_add_painel_equilibrio(graficos: dict, canonical_in: CanonicalModel) -> None:
    """ADR-082: Agrega levers_equilibrio de todos os itens de ponto_equilibrio no graficos dict."""
    pe_list = canonical_in.ponto_equilibrio or []
    if not pe_list:
        return

    delta_total = round(sum(pe.delta for pe in pe_list), 2)
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

    # "fechar_gap_escala" representa serializacao/paralelismo de frentes e tende a
    # gerar leitura ambigua no painel executivo. Mantemos foco em praticabilidade/pool.
    levers_visiveis = [lv for lv in levers_agg.values() if lv.get("id") != "fechar_gap_escala"]
    levers_sorted = sorted(levers_visiveis, key=lambda x: -x["delta_margin_total"])
    soma_levers = round(sum(lv["delta_margin_total"] for lv in levers_sorted), 2)
    combinacoes = _minimal_break_even_combinations(levers_sorted, delta_total)

    # Marca cada lever com sua participação nas combinações minimais
    levers_em_combinacoes_tier1: set[str] = {lid for c in combinacoes if c["tier"] == 1 for lid in c["levers_ids"]}
    levers_em_qualquer_combo: set[str] = {lid for c in combinacoes for lid in c["levers_ids"]}
    for lv in levers_sorted:
        lv["break_even_solo"] = lv["id"] in levers_em_combinacoes_tier1
        lv["participa_combo"] = lv["id"] in levers_em_qualquer_combo

    # Multiplicador médio de PU ponderado por custo_venda (frentes_nec media)
    total_venda = sum(pe.custo_venda_cpu for pe in pe_list if pe.custo_venda_cpu > 0)
    frentes_nec_media = (
        (
            sum(pe.frentes_equivalentes_necessarias * pe.custo_venda_cpu for pe in pe_list if pe.custo_venda_cpu > 0)
            / total_venda
        )
        if total_venda > 0
        else 1.0
    )

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
    if not gerar_modelo_vivo:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-ADAPTER-EXCEL-LIVE",
                status="AVISO",
                mensagem=(
                    "Geração de modelo vivo desabilitada (padrão). Use input 'gerar_modelo_vivo=true' para habilitar."
                ),
            )
        )
        return None
    try:
        from concilium.infrastructure.adapters.excel_live_model import render_live_model

        live_bytes = render_live_model(canonical_in)
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-ADAPTER-EXCEL-LIVE", status="OK", mensagem="Modelo vivo Excel (fórmulas) gerado com sucesso"
            )
        )
        return live_bytes
    except Exception as e:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-ADAPTER-EXCEL-LIVE", status="AVISO", mensagem=f"Erro ao gerar modelo vivo: {str(e)}"
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


def _rra_build_pe_rows(canonical_in: CanonicalModel, resultado_section: dict[str, Any] | None = None) -> list[dict]:
    """Builds ponto_equilibrio list for report with reconciled margins and gap decomposition."""

    def _f(value: Any) -> float:
        try:
            return float(value or 0.0)
        except Exception:
            return 0.0

    pe_items = list(canonical_in.ponto_equilibrio or [])
    if not pe_items:
        return []

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

    soma_venda_itens = sum(_f(pe.custo_venda_cpu) for pe in pe_items)
    n_items = max(1, len(pe_items))

    rows: list[dict] = []
    for pe in pe_items:
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
        base_particao = custo_produtivo + custo_mob_demob + custo_ociosidade
        if deficit > 0 and base_particao > 0:
            gap_produtivo = deficit * (custo_produtivo / base_particao)
            gap_mob_demob = deficit * (custo_mob_demob / base_particao)
            gap_ociosidade = deficit * (custo_ociosidade / base_particao)
        else:
            gap_produtivo = 0.0
            gap_mob_demob = 0.0
            gap_ociosidade = 0.0

        rows.append(
            {
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
            }
        )
    return rows


def _rra_build_resultado_section(
    res: Any,
    benchmark_mode: bool = False,
    benchmark_reference_projection: dict[str, Any] | None = None,
) -> dict:
    """Builds resultado section dict."""

    def _num(value: Any) -> float | None:
        try:
            if value is None:
                return None
            return float(value)
        except Exception:
            return None

    direto_equipes = float(res.custo.direto_equipes or 0.0)
    # Fonte autoritativa única do relatório: custo direto operacional instancial (direto_equipes).
    custo_direto_auth = direto_equipes
    custo_direto_fonte = "operacional_equipes"

    custo_indireto_calc = (
        float(res.custo.indireto_adm or 0.0)
        + float(res.custo.indireto_top or 0.0)
        + float(res.custo.indireto_lab or 0.0)
        + float(res.custo.indireto_qsms or 0.0)
        + float(res.custo.indireto_mob or 0.0)
    )
    preco_venda_total = float(res.venda.total_com_bdi or 0.0)
    # Usar custo.total do modelo como fonte autoritativa (inclui todos os componentes
    # calculados por skill-08). Fallback para recálculo local apenas quando ausente.
    custo_total_canonical = float(res.custo.total or 0.0) if res.custo.total else None
    custo_total_calc = (
        custo_total_canonical if custo_total_canonical is not None else custo_direto_auth + custo_indireto_calc
    )
    # Valores calculados são sempre a fonte primária do relatório (NEP-030).
    # A referência fica armazenada separadamente para a seção de confronto.
    razao_id = custo_indireto_calc / custo_direto_auth if custo_direto_auth > 0 else 0
    margem_pct = (preco_venda_total - custo_total_calc) / preco_venda_total if preco_venda_total > 0 else 0

    # Extrai referência para seção de confronto (apenas para exibição — não substitui calculado)
    referencia: dict | None = None
    if isinstance(benchmark_reference_projection, dict):
        ref_direto = _num(benchmark_reference_projection.get("custo_direto"))
        ref_indireto = _num(benchmark_reference_projection.get("custo_indireto"))
        ref_total = _num(benchmark_reference_projection.get("custo_total"))
        ref_preco = _num(benchmark_reference_projection.get("preco_venda"))
        if ref_preco and ref_preco > 0:

            def _delta_pct(tool: float, ref: float) -> float | None:
                return round((tool - ref) / ref * 100, 2) if ref and ref > 0 else None

            referencia = {
                "custo_direto": ref_direto,
                "custo_indireto": ref_indireto,
                "custo_total": ref_total,
                "preco_venda": ref_preco,
                "delta_custo_direto_pct": _delta_pct(custo_direto_auth, ref_direto) if ref_direto else None,
                "delta_custo_indireto_pct": _delta_pct(custo_indireto_calc, ref_indireto) if ref_indireto else None,
                "delta_preco_venda_pct": _delta_pct(preco_venda_total, ref_preco),
            }

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
            "localizacao": proj.localizacao,
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


def _rra_build_compressao_cronograma(canonical_in: CanonicalModel) -> dict | None:
    """NEP-038: análise de compressão de cronograma por k-scaling de equipes.

    Reconstrói ScheduleOutput + ActivityDAG a partir do canônico e chama
    compute_compression_sensitivities com CP-SAT.

    Retorna None quando não há cronograma ou contratos suficientes.
    Falhas do CP-SAT são silenciosas (retorna None) para não bloquear o relatório.
    """

    cronograma = canonical_in.cronograma
    if not cronograma or not cronograma.scheduled_activities:
        return None

    contratos_raw = canonical_in.contratos_recurso or []
    if not contratos_raw:
        return None

    try:
        from concilium.application.scheduling import (
            Activity,
            ActivityDAG,
            ResourcePool,
            ScheduledActivity,
            ScheduleMetrics,
            ScheduleOutput,
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
    sched_acts_sched = [
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
    if not sched_acts_sched:
        return None

    metrics = ScheduleMetrics(
        makespan=makespan,
        resource_leveling_score=0.0,
        idle_time=0,
        activity_fragmentation=0,
        critical_path_slack_min=0.0,
        resource_utilization_avg=0.0,
    )
    sched_output = ScheduleOutput(
        scheduled_activities=sched_acts_sched,
        makespan=makespan,
        feasible=True,
        metrics=metrics,
    )

    # ── Reconstrói ActivityDAG ───────────────────────────────────────────────
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
    prec: list[tuple[str, str]] = []
    thresh: dict[tuple[str, str], float] = {}
    for item in canonical_in.eap or []:
        iid = item.item_id
        if iid not in aid_set:
            continue
        for pred in item.predecessores or []:
            pid = getattr(pred, "predecessor_id", None) or getattr(pred, "item_id", None)
            if pid and pid in aid_set and (pid, iid) not in set(prec):
                prec.append((pid, iid))
                th = getattr(pred, "completion_threshold_pct", None) or getattr(pred, "threshold", None) or 1.0
                thresh[(pid, iid)] = float(th)

    dag = ActivityDAG(activities=acts, precedence=prec, thresholds=thresh)

    # ── Pool base ────────────────────────────────────────────────────────────
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
    pool = ResourcePool(resources=pool_resources)

    # ── Contratos para custo de instâncias ───────────────────────────────────
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

    # ── custo_semana ────────────────────────────────────────────────────────
    res = canonical_in.resultado
    preco_venda = 0.0
    if res:
        for attr in ("preco_venda_total", "total_com_bdi"):
            v = getattr(res, attr, None)
            if v and float(v) > 0:
                preco_venda = float(v)
                break
    if preco_venda <= 0:
        return None
    custo_semana = preco_venda / makespan

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
    viáveis = [r for r in results if r.best_k is not None]
    makespan_otimo = min(r.by_k[r.best_k].makespan_new for r in viáveis) if viáveis else makespan

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


def _rra_build_decomposicao_pool(canonical_in: CanonicalModel) -> dict | None:
    """ADR-086: seção de decomposição explorável de pool de recursos.

    Agrega as faces-chave (ciclo de vida, custo por estado×componente, economia vs. autônomo,
    cadeias de perpetuação) com narrativa honesta. Retorna None quando não há pool.
    """
    if not (canonical_in.contratos_recurso or canonical_in.instancias_recurso):
        return None
    try:
        from concilium.application.services.cubo_pool_projection import (
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
