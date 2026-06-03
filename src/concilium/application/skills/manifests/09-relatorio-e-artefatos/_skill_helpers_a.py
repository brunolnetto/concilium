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
    elif canonical_in.cost_criticality_report is not None:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-ADAPTER-CRITICIDADE",
                status="AVISO",
                mensagem="Relatório de criticidade presente, mas sem atividades classificadas.",
            )
        )


def _build_planejamento_rows(
    canonical_in: CanonicalModel, criticidade_lookup: dict[str, str], has_criticidade: bool
) -> list[dict]:
    rows: list[dict] = []
    for p in canonical_in.planejamento:
        row = {
            "item_id": p.item_id,
            "cpu_id": p.cpu_id,
            "quantitativo": p.quantitativo,
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
    for eq in canonical_in.equipes_diretas:
        pe = pe_by_item.get(eq.item_id)
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
            }
        )
        analise_composicional.append(
            {
                "item_id": eq.item_id,
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


def _rra_build_pe_rows(canonical_in: CanonicalModel) -> list[dict]:
    """Builds ponto_equilibrio list for report."""
    rows = []
    for pe in canonical_in.ponto_equilibrio:
        rows.append(
            {
                "item_id": pe.item_id,
                "custo_fixo_equipe": pe.custo_fixo_equipe,
                "custo_operacional_real": getattr(pe, "custo_operacional_real", 0.0),
                "custo_venda_cpu": pe.custo_venda_cpu,
                "frentes_equivalentes": getattr(pe, "frentes_equivalentes", 1.0),
                "status_validacao": pe.status_validacao,
            }
        )
    return rows


def _rra_build_resultado_section(res: Any) -> dict:
    """Builds resultado section dict."""
    custo_direto_auth = res.custo.direto_catalogo if res.custo.direto_catalogo > 0 else res.custo.direto_equipes
    custo_indireto_calc = res.custo.total - custo_direto_auth
    razao_id = custo_indireto_calc / custo_direto_auth if custo_direto_auth > 0 else 0
    margem_pct = (
        (res.venda.total_com_bdi - res.custo.total) / res.venda.total_com_bdi if res.venda.total_com_bdi > 0 else 0
    )
    return {
        "preco_venda_total": res.venda.total_com_bdi,
        "custo_total": res.custo.total,
        "custo_direto": custo_direto_auth,
        "custo_indireto": custo_indireto_calc,
        "razao_indireto_direto": razao_id,
        "resultado_bruto": res.venda.total_com_bdi - res.custo.total,
        "margem_pct": margem_pct,
        "status_margem": res.status_margem,
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
) -> dict:
    """Assembles the full relatorio dict."""
    resultado_section = _rra_build_resultado_section(res)
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
        "ponto_equilibrio": _rra_build_pe_rows(canonical_in),
        "ACTIONABLE_INSIGHTS": _rra_build_actionable_insights(canonical_in),
        "validacoes_pipeline": validacoes_pipeline,
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
