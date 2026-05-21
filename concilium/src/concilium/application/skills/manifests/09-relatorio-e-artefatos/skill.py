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

import math
from datetime import UTC, date, datetime
from typing import Any

from concilium.application.skills.base import SkillResult
from concilium.domain.models.canonical import CanonicalModel, ValidacaoItem
from concilium.infrastructure.adapters.excel_adapter import ExcelRenderer


def _week_to_month(week_key: str) -> tuple[int, int]:
    year_str, week_str = week_key.split("-W")
    monday = date.fromisocalendar(int(year_str), int(week_str), 1)
    return monday.year, monday.month


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


def _fmt_mes(ym: tuple[int, int]) -> str:
    return f"{_MESES_PT[ym[1]]}/{str(ym[0])[-2:]}"


def _next_month(ym: tuple[int, int]) -> tuple[int, int]:
    year, month = ym
    return (year + 1, 1) if month == 12 else (year, month + 1)


def _monthly_direct_costs(canonical_in: CanonicalModel, project_months: list) -> dict:
    result: dict[tuple[int, int], float] = {ym: 0.0 for ym in project_months}
    if not project_months or not canonical_in.cronograma or not canonical_in.planejamento:
        return result
    cost_per_unit: dict[str, float] = {}
    for p in canonical_in.planejamento:
        total = p.subtotal.sem_bdi.total if p.subtotal else 0.0
        qty = p.quantitativo or 1.0
        cost_per_unit[p.item_id] = total / qty if qty > 0 else 0.0
    for act in canonical_in.cronograma.scheduled_activities:
        cpu = cost_per_unit.get(act.activity_id, 0.0)
        if cpu <= 0:
            continue
        for week_key, dist in act.distribuicao_semanal.items():
            qtd = float(getattr(dist, "qtd_executada", 0.0) or 0.0)
            if qtd <= 0:
                continue
            ym = _week_to_month(week_key)
            if ym in result:
                result[ym] += cpu * qtd
    return result


def _monthly_indirect_costs(canonical_in: CanonicalModel, project_months: list) -> dict:
    result: dict[tuple[int, int], float] = {ym: 0.0 for ym in project_months}
    if not project_months:
        return result
    n = len(project_months)
    for ind in canonical_in.indiretos:
        if ind.categoria == "MOB":
            result[project_months[0]] += ind.custo_total
            continue
        perm = int(ind.permanencia_meses or n)
        meses_ativos = project_months[: min(perm, n)]
        if meses_ativos:
            por_mes = ind.custo_total / len(meses_ativos)
            for ym in meses_ativos:
                result[ym] += por_mes
    return result


def _cash_flow_rows(canonical_in: CanonicalModel, project_months: list) -> list[dict]:
    if not project_months or canonical_in.resultado is None:
        return []
    n = len(project_months)
    venda_total = canonical_in.resultado.venda.total_com_bdi
    parcela_base = math.floor(venda_total / n) if n else 0
    residuo = venda_total - parcela_base * (n - 1)
    all_months = project_months + [_next_month(project_months[-1])]
    receitas = [0.0] + [float(parcela_base)] * (n - 1) + [float(residuo)]
    direct = _monthly_direct_costs(canonical_in, project_months)
    indirect = _monthly_indirect_costs(canonical_in, project_months)
    rows: list[dict] = []
    despesa_acumulada = 0.0
    receita_acumulada = 0.0
    for idx, ym in enumerate(all_months):
        despesa = direct.get(ym, 0.0) + indirect.get(ym, 0.0)
        receita = receitas[idx]
        despesa_acumulada += despesa
        receita_acumulada += receita
        rows.append(
            {
                "mes_label": _fmt_mes(ym),
                "despesa": despesa,
                "receita": receita,
                "saldo": receita - despesa,
                "exposicao": despesa_acumulada - receita_acumulada,
            }
        )
    return rows


def _add_criticidade_validacoes(
    canonical_in: CanonicalModel, has_criticidade: bool, criticidade_lookup: dict, validacoes: list
) -> None:
    if has_criticidade:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-ADAPTER-CRITICIDADE",
                status="OK",
                mensagem=f"Coluna Criticidade embutida na planilha PLANEJAMENTO ({len(criticidade_lookup)} atividades classificadas de 09-cost-criticality — ADR-026 §D5)",
            )
        )
    elif "09-cost-criticality" in (canonical_in.pipeline_blocked_from or []):
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-ADAPTER-CRITICIDADE",
                status="AVISO",
                mensagem="Coluna Criticidade ausente: 09-cost-criticality em pipeline_blocked_from. Planilha gerada sem enriquecimento de criticidade (ADR-026 §D5).",
            )
        )
    else:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-ADAPTER-CRITICIDADE",
                status="AVISO",
                mensagem="Coluna Criticidade ausente: cost_criticality_report não preenchido. Execute 09-cost-criticality antes de 09-relatorio-e-artefatos (ADR-026 §D5).",
            )
        )


def _build_planejamento_rows(canonical_in: CanonicalModel, criticidade_lookup: dict, has_criticidade: bool) -> list:
    eap_by_item_id = {e.item_id: e for e in canonical_in.eap}
    rows = []
    for p in canonical_in.planejamento:
        eap_item = eap_by_item_id.get(p.item_id)
        row: dict[str, Any] = {
            "item_id": p.item_id,
            "cpu_id": p.cpu_id,
            "descricao": eap_item.descricao if eap_item else p.cpu_id,
            "unidade": eap_item.unidade if eap_item else "?",
            "quantitativo": p.quantitativo,
            "preco_unit_mao_obra": p.preco_unitario.mao_obra,
            "preco_unit_servicos": p.preco_unitario.equipamentos,
            "preco_unit_material": p.preco_unitario.material,
            "preco_unit_diesel": p.preco_unitario.diesel,
            "bdi_servicos": p.bdi.equipamentos,
            "bdi_material": p.bdi.material,
            "bdi_diesel": p.bdi.diesel,
            "subtotal_mo": p.subtotal.sem_bdi.mao_obra,
            "subtotal_eq": p.subtotal.sem_bdi.equipamentos,
            "subtotal_diesel": p.subtotal.sem_bdi.diesel,
            "subtotal_mat": p.subtotal.sem_bdi.material,
            "subtotal_sem_bdi": p.subtotal.sem_bdi.total,
            "subtotal_com_bdi": p.subtotal.com_bdi.total,
        }
        if has_criticidade:
            row["criticidade"] = criticidade_lookup.get(p.item_id, "--")
        rows.append(row)
    return rows


def _acao_sugerida_equipe(gap_operacional: float, dominante: str) -> str:
    if gap_operacional < 0:
        return "Aumentar preco de venda ou reduzir a base operacional"
    if dominante == "equipamentos":
        return "Substituir maquinario, reduzir ociosidade ou compartilhar frota"
    if dominante == "mao_obra":
        return "Enxugar equipe, remover integrantes menos relevantes ou aumentar produtividade"
    if dominante == "combustivel":
        return "Melhorar produtividade, reduzir deslocamentos e usar maquinas mais eficientes"
    return "Renegociar materiais, reduzir perdas e ajustar consumo direto"


def _build_equipe_rows(canonical_in: CanonicalModel) -> tuple[list, list]:
    pe_by_item_id = {pe.item_id: pe for pe in canonical_in.ponto_equilibrio}
    equipe_rows: list = []
    analise_composicional: list = []
    for eq in canonical_in.equipes_diretas:
        pe = pe_by_item_id.get(eq.item_id)
        permanencia = float(eq.permanencia_meses or 0.0)
        mo_total = float(eq.custo_mao_obra_mensal or 0.0) * permanencia
        eq_total = float(eq.custo_equipamentos_mensal or 0.0) * permanencia
        combustivel_total = float(eq.custo_combustivel_total_mensal or 0.0) * permanencia
        material_total = float(eq.custo_material_mensal or 0.0) * permanencia
        custo_operacional = float(eq.custo_total or 0.0)
        venda_total = float(pe.custo_venda_cpu if pe else 0.0)
        gap_operacional = venda_total - custo_operacional
        gap_pct = (gap_operacional / venda_total) if venda_total > 0 else 0.0
        componentes = {
            "mao_obra": mo_total,
            "equipamentos": eq_total,
            "combustivel": combustivel_total,
            "material": material_total,
        }
        dominante = max(componentes, key=componentes.get) if any(componentes.values()) else "mao_obra"
        shares = {k: (v / custo_operacional if custo_operacional > 0 else 0.0) for k, v in componentes.items()}
        equipe_rows.append(
            {
                "equipe_id": eq.equipe_id,
                "item_id": eq.item_id,
                "num_funcoes": sum(f.num_pessoas for f in eq.funcoes),
                "permanencia_meses": eq.permanencia_meses,
                "custo_fixo_mensal": eq.custo_fixo_mensal,
                "custo_fixo_total": eq.custo_total,
                "custo_venda_cpu": pe.custo_venda_cpu if pe else None,
                "delta_pct": pe.delta_pct if pe else None,
                "status_pe": pe.status_validacao if pe else "N/A",
            }
        )
        analise_composicional.append(
            {
                "item_id": eq.item_id,
                "custo_venda_cpu": venda_total,
                "custo_operacional_real": custo_operacional,
                "gap_operacional": gap_operacional,
                "gap_pct": gap_pct,
                "mao_obra_total": mo_total,
                "equipamentos_total": eq_total,
                "combustivel_total": combustivel_total,
                "material_total": material_total,
                "share_mao_obra": shares["mao_obra"],
                "share_equipamentos": shares["equipamentos"],
                "share_combustivel": shares["combustivel"],
                "share_material": shares["material"],
                "dominante": dominante,
                "acao_sugerida": _acao_sugerida_equipe(gap_operacional, dominante),
            }
        )
    return equipe_rows, analise_composicional


def _build_indireto_rows(canonical_in: CanonicalModel, inputs: dict) -> list:
    indiretos_det_ref = inputs.get("indiretos_detalhados") or {}
    rows = []
    for i in canonical_in.indiretos:
        row: dict[str, Any] = {
            "categoria": i.categoria,
            "descricao": i.descricao,
            "permanencia_meses": i.permanencia_meses,
            "custo_total": i.custo_total,
            "funcoes": i.funcoes,
            "equipamentos": i.equipamentos,
            "verbas_mensais": i.verbas_mensais,
            "verbas_fixas": i.verbas_fixas,
            "mobilizacoes": [m.model_dump() for m in i.mobilizacoes],
        }
        det = indiretos_det_ref.get(i.categoria.lower())
        if det:
            row["detalhamento"] = det
        rows.append(row)
    return rows


def _bgs_get_equipe(act, equipes_diretas: list):
    """Finds the equipe_direta matching act.activity_id."""
    return next((item for item in equipes_diretas if item.item_id == act.activity_id), None)


def _bgs_gantt_task(act, weeks: list, eap_by_item_id: dict) -> dict:
    """Builds a gantt task dict from a scheduled activity."""
    from datetime import date as _date

    eap_item = eap_by_item_id.get(act.activity_id)
    year_str, week_str = weeks[0].split("-W")
    return {
        "item_id": act.activity_id,
        "name": eap_item.descricao if eap_item else act.activity_id,
        "start": _date.fromisocalendar(int(year_str), int(week_str), 1).isoformat(),
        "duration_days": len(weeks) * 7,
    }


def _bgs_min_units(eq) -> float:
    """Computes min num_unidades across equipamentos (>0), default 1."""
    if not eq.equipamentos:
        return 1
    return min((e.num_unidades for e in eq.equipamentos if (e.num_unidades or 0) > 0), default=1)


def _bgs_accumulate_week(wk: str, dist, eq, equip_totals: dict, mo_totals: dict, min_units: float) -> None:
    """Accumulates weekly equipment and labour totals from a distribution entry."""
    n = float(getattr(dist, "num_equipes", 0) or 0.0)
    if n <= 0:
        return
    equip_totals[wk] = equip_totals.get(wk, 0.0) + sum(
        (n / min_units) * float(e.num_unidades or 0.0) for e in eq.equipamentos
    )
    mo_totals[wk] = mo_totals.get(wk, 0.0) + sum((n / min_units) * float(f.num_pessoas or 0.0) for f in eq.funcoes)


def _bgs_build_graficos_dict(equip_totals: dict, mo_totals: dict, gantt_tasks: list) -> dict:
    """Builds the base graficos dict with equipamentos, mao_obra and cronograma keys."""
    return {
        "equipamentos": {
            "labels": [str(wk) for wk in sorted(equip_totals)],
            "values": [equip_totals[wk] for wk in sorted(equip_totals)],
        },
        "mao_obra": {
            "labels": [str(wk) for wk in sorted(mo_totals)],
            "values": [mo_totals[wk] for wk in sorted(mo_totals)],
        },
        "cronograma": {"tasks": gantt_tasks},
    }


def _bgs_add_financeiro(graficos: dict, canonical_in, project_months: list) -> None:
    """Adds 'financeiro' key to graficos dict if cash_flow_rows are available."""
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
            _bgs_accumulate_week(wk, dist, eq, equip_totals, mo_totals, min_units)
    graficos = _bgs_build_graficos_dict(equip_totals, mo_totals, gantt_tasks)
    _bgs_add_financeiro(graficos, canonical_in, project_months)
    return graficos


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
                mensagem="Geração de modelo vivo desabilitada (padrão). Use input 'gerar_modelo_vivo=true' para habilitar.",
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


def run_relatorio_e_artefatos(
    canonical_in: CanonicalModel,
    inputs: dict[str, Any],
    perfil: dict[str, Any] | None = None,
) -> SkillResult:
    """Produz relatório estruturado baseado em template."""
    validacoes: list[ValidacaoItem] = []
    gerar_excel = bool(inputs.get("gerar_excel", True))
    gerar_modelo_vivo = bool(inputs.get("gerar_modelo_vivo", False))

    if canonical_in.resultado is None:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-ADAPTER-PRECONDICAO",
                status="ERRO",
                mensagem="Adapter requer resultado consolidado (skill 06)",
            )
        )
        return SkillResult(canonical_in, validacoes)

    proj = canonical_in.projeto
    res = canonical_in.resultado

    criticidade_lookup: dict[str, str] = {}
    if canonical_in.cost_criticality_report is not None:
        for prof in canonical_in.cost_criticality_report.atividades:
            criticidade_lookup[prof.atividade_id] = prof.classe
    has_criticidade = bool(criticidade_lookup)
    _add_criticidade_validacoes(canonical_in, has_criticidade, criticidade_lookup, validacoes)

    eap_by_item_id = {e.item_id: e for e in canonical_in.eap}
    planejamento_rows = _build_planejamento_rows(canonical_in, criticidade_lookup, has_criticidade)
    equipe_rows, analise_composicional = _build_equipe_rows(canonical_in)
    indireto_rows = _build_indireto_rows(canonical_in, inputs)

    custo_direto_auth = res.custo.direto_catalogo if res.custo.direto_catalogo > 0 else res.custo.direto_equipes
    custo_indireto_calc = res.custo.total - custo_direto_auth
    resultado_section = {
        "preco_venda_total": res.venda.total_com_bdi,
        "custo_total": res.custo.total,
        "custo_direto": custo_direto_auth,
        "custo_indireto": custo_indireto_calc,
        "razao_indireto_direto": custo_indireto_calc / custo_direto_auth if custo_direto_auth > 0 else 0,
        "resultado_bruto": res.venda.total_com_bdi - res.custo.total,
        "margem_pct": (res.venda.total_com_bdi - res.custo.total) / res.venda.total_com_bdi
        if res.venda.total_com_bdi > 0
        else 0,
        "status_margem": res.status_margem,
    }

    if not canonical_in.planejamento:
        validacoes.append(
            ValidacaoItem(codigo="VAL-ADAPTER-01", status="AVISO", mensagem="Planejamento vazio — relatório parcial")
        )
    else:
        validacoes.append(ValidacaoItem(codigo="VAL-ADAPTER-01", status="OK"))

    acts = canonical_in.cronograma.scheduled_activities if canonical_in.cronograma else []
    project_months = sorted(
        {month for act in acts for month in (_week_to_month(wk) for wk in act.distribuicao_semanal)}
    )
    graficos = _build_graficos_section(canonical_in, eap_by_item_id, project_months)

    relatorio = {
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
        "ponto_equilibrio": [
            {
                "item_id": pe.item_id,
                "custo_fixo_equipe": pe.custo_fixo_equipe,
                "custo_operacional_real": getattr(pe, "custo_operacional_real", 0.0),
                "custo_venda_cpu": pe.custo_venda_cpu,
                "frentes_equivalentes": getattr(pe, "frentes_equivalentes", 1.0),
                "status_validacao": pe.status_validacao,
            }
            for pe in canonical_in.ponto_equilibrio
        ],
        "ACTIONABLE_INSIGHTS": {
            "criticidade": canonical_in.relatorio_criticidade.model_dump(mode="json")
            if canonical_in.relatorio_criticidade
            else None,
            "sensibilidade": canonical_in.relatorio_sensibilidade.model_dump(mode="json")
            if canonical_in.relatorio_sensibilidade
            else None,
            "intervencao": canonical_in.relatorio_intervencao.model_dump(mode="json")
            if canonical_in.relatorio_intervencao
            else None,
        },
        "validacoes_pipeline": [
            {"codigo": v.codigo, "status": v.status, "mensagem": v.mensagem} for v in res.validacoes
        ],
    }

    novo = canonical_in.model_copy(update={})
    novo._relatorio_saida = relatorio  # type: ignore[attr-defined]

    excel_bytes = _gerar_excel_bytes(canonical_in, validacoes, gerar_excel)
    live_bytes = _gerar_live_model(canonical_in, validacoes, gerar_modelo_vivo)
    memorial_json_bytes = _gerar_memorial_json_bytes(canonical_in)

    result = SkillResult(novo, validacoes)
    result.relatorio = relatorio  # type: ignore[attr-defined]
    result.excel_bytes = excel_bytes  # type: ignore[attr-defined]
    result.excel_live_bytes = live_bytes  # type: ignore[attr-defined]
    result.memorial_bdi_json = memorial_json_bytes  # type: ignore[attr-defined]
    return result
