"""Seções complementares de calibração e insights do relatório."""

from __future__ import annotations

from typing import Any


def _f(value: Any) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def _money(value: Any) -> str:
    return f"{_f(value):,.2f}"


def _pct(value: Any) -> str:
    return f"{_f(value) * 100:.2f}%"


def _sum_pe_field(rows: list, key: str) -> float:
    return sum(_f(row.get(key)) for row in rows)


def _format_insight_item(item: dict) -> str:
    titulo = item.get("titulo") or item.get("title") or "Insight"
    descricao = item.get("descricao") or item.get("description") or str(item)
    return f"- **{titulo}**: {descricao}"


def _render_dict_insights(insights: dict) -> list[str]:
    return [f"- **{key}**: {value}" for key, value in insights.items()]


def _render_list_insights(insights: list) -> list[str]:
    lines = []
    for item in insights:
        if isinstance(item, dict):
            lines.append(_format_insight_item(item))
        else:
            lines.append(f"- {item}")
    return lines


def render_equilibrium_section(
    ponto_equilibrio: list[dict[str, Any]], resultado: dict[str, Any] | None = None
) -> list[str]:
    if not isinstance(ponto_equilibrio, list) or not ponto_equilibrio:
        return []

    lines = [
        "## Ponto de Equilibrio",
        "",
        "> **Como interpretar ERRO por item sem distorcer o saldo global do projeto?**",
        ">",
        "> O campo `Operacional (R$)` deve refletir **custo alocado por item**, nao o custo bruto do pool inteiro. "
        "Em pool compartilhado, a base coerente e a permanencia efetiva da instancia (team-weeks / team-months) "
        "e o custo operacional correspondente de cada equipamento/equipe no periodo.",
        ">",
        "> Essa abordagem evita dupla contagem entre atividades atendidas pelo mesmo pool e mantem "
        "consistencia entre PE por item e consolidacao financeira do contrato.",
        ">",
        "> **Em resumo:** quando o custo operacional e particionado pela permanencia/capacidade efetiva, "
        "o diagnostico por item fica financeiramente honesto e o saldo final volta a representar a "
        "alocacao enxuta do resource pool sem inflacao artificial de custo.",
        ">",
        "> **Parametros operacionais de calibracao:** produtividade de CPU, numero maximo de equipes por "
        "atividade e perfis de permanencia/ramp-up. "
        "**Fatores exogenos:** praticabilidade (clima/terreno) devem ficar explicitos no diagnostico.",
        "",
        "| Item | Venda (R$) | Operacional (R$) | Margem Op. Direta | Margem Total Atribuida | Gap Produtivo (R$) | Gap Mob/Demob (R$) | Gap Ociosidade (R$) | Status |",
        "|------|-----------:|-----------------:|-------------------:|------------------------:|-------------------:|--------------------:|---------------------:|--------|",
    ]
    for row in ponto_equilibrio:
        lines.append(
            f"| {row.get('item_id', '-')} | {_money(row.get('custo_venda_cpu'))} | {_money(row.get('custo_operacional_real'))} "
            f"| {_pct(row.get('margem_operacional_direta'))} | {_pct(row.get('margem_total_atribuida'))} "
            f"| {_money(row.get('gap_produtivo'))} | {_money(row.get('gap_mob_demob'))} | {_money(row.get('gap_ociosidade'))} "
            f"| {row.get('status_validacao', '-')} |"
        )

    resultado = resultado if isinstance(resultado, dict) else {}
    soma_venda_itens = _sum_pe_field(ponto_equilibrio, "custo_venda_cpu")
    soma_op_itens = _sum_pe_field(ponto_equilibrio, "custo_operacional_real")
    soma_gap_produtivo = _sum_pe_field(ponto_equilibrio, "gap_produtivo")
    soma_gap_mob_demob = _sum_pe_field(ponto_equilibrio, "gap_mob_demob")
    soma_gap_ociosidade = _sum_pe_field(ponto_equilibrio, "gap_ociosidade")
    soma_resultado_atribuido = _sum_pe_field(ponto_equilibrio, "resultado_total_atribuido")

    receita_global = _f(resultado.get("preco_venda_total"))
    custo_total_global = _f(resultado.get("custo_total"))
    resultado_global = _f(resultado.get("resultado_bruto"))

    lines += [
        "",
        "### Reconciliacao Itens -> Resultado Global",
        "",
        "| Indicador | Soma Itens (R$) | Global (R$) | Delta (R$) |",
        "|-----------|----------------:|------------:|-----------:|",
        f"| Receita | {_money(soma_venda_itens)} | {_money(receita_global)} | {_money(soma_venda_itens - receita_global)} |",
        f"| Custo Operacional / Total | {_money(soma_op_itens)} | {_money(custo_total_global)} | {_money(soma_op_itens - custo_total_global)} |",
        f"| Resultado | {_money(soma_resultado_atribuido)} | {_money(resultado_global)} | {_money(soma_resultado_atribuido - resultado_global)} |",
        "",
        "> Observacao: `Margem Total Atribuida` e reconciliada por rateio de receita e custos globais (direto + indireto) com base na participacao de venda de cada item.",
        f"> Decomposicao do gap (itens deficitarios): produtivo={_money(soma_gap_produtivo)}, mob/demob={_money(soma_gap_mob_demob)}, ociosidade={_money(soma_gap_ociosidade)}.",
    ]
    lines += ["", "---", ""]
    return lines


def render_insights_section(insights: Any) -> list[str]:
    if not insights:
        return []
    lines = ["## Insights Acionaveis", ""]
    if isinstance(insights, dict):
        lines.extend(_render_dict_insights(insights))
    elif isinstance(insights, list):
        lines.extend(_render_list_insights(insights))
    lines += ["", "---", ""]
    return lines
