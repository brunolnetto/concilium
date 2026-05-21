"""Adapter de saída Excel — MendesLobo Construtora.

Módulo consolidado (ADR-029 Fase 4):
  • Paleta de cores e helpers de estilo
  • 6 abas: DIRETOS, INDIRETOS, PLANEJAMENTO, CRONOGRAMA, FLUXO DE CAIXA, RESULTADO
  • ExcelRenderer — orquestrador público (entry-point para consumidores externos)
  • coerce_to_cell_value — helper de coerção (mantido por retrocompatibilidade)

Importação pública canônica:
    from concilium.infrastructure.adapters.excel_adapter import ExcelRenderer
"""

from __future__ import annotations

import math
from datetime import date
from functools import cache
from io import BytesIO
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.workbook.defined_name import DefinedName

from concilium.domain.models.canonical import CanonicalModel

# ── Paleta MendesLobo ─────────────────────────────────────────────────────────

_C = {
    "nav_dk": "1A3A5C",  # azul marinho escuro — cabeçalhos principais
    "nav_md": "2B6CB0",  # azul médio — subcabeçalhos
    "orange": "C05C18",  # laranja queimado — totais, destaques
    "orange_lt": "F5E6D8",  # laranja claro — linhas de total
    "row_alt": "F0F5FA",  # azul quase branco — linha alternada
    "white": "FFFFFF",
    "verde": "276749",
    "verde_lt": "DCEEE5",
    "vermelho": "9B1C1C",
    "verm_lt": "FADDDD",
    "amarelo": "92400E",
    "amar_lt": "FEF3C7",
    "cinza_bd": "CBD5E0",  # borda
    "cinza_lt": "F7FAFC",  # cabeçalho de seção leve
    "preto": "1A202C",
}

MESES_PT = {
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
# SEMANAS_POR_MES importada de domain/constants (ADR-056 §T3) — removida definição local


# ── Utilitários de estilo ─────────────────────────────────────────────────────


@cache
def _fill(hex_color: str) -> PatternFill:
    return PatternFill(start_color=hex_color, end_color=hex_color, fill_type="solid")


@cache
def _font(bold: bool = False, color: str = "1A202C", size: int = 10, italic: bool = False) -> Font:
    return Font(bold=bold, color=color, size=size, italic=italic, name="Calibri")


@cache
def _border(style: str = "thin") -> Border:
    s = Side(style=style, color=_C["cinza_bd"])
    return Border(left=s, right=s, top=s, bottom=s)


@cache
def _align(h: str = "left", v: str = "center", wrap: bool = False) -> Alignment:
    return Alignment(horizontal=h, vertical=v, wrap_text=wrap)


def _money(
    ws: Any,
    row: int,
    col: int,
    value: float | str,
    fill: PatternFill | None = None,
    bold: bool = False,
    color: str | None = None,
) -> None:
    is_formula = isinstance(value, str) and value.startswith("=")
    cell_value = value if is_formula else round(float(value), 2)
    cell = ws.cell(row=row, column=col, value=cell_value)
    cell.number_format = "R$ #,##0.00"
    cell.alignment = _align("right")
    cell.border = _border()
    if fill:
        cell.fill = fill
    cell.font = _font(bold=bold, color=color or _C["preto"])


def _label(
    ws: Any,
    row: int,
    col: int,
    value: Any,
    fill: PatternFill | None = None,
    bold: bool = False,
    color: str | None = None,
    align: str = "left",
    wrap: bool = False,
) -> None:
    cell = ws.cell(row=row, column=col, value=value)
    cell.alignment = _align(align, wrap=wrap)
    cell.border = _border()
    if fill:
        cell.fill = fill
    cell.font = _font(bold=bold, color=color or _C["preto"])


def _header_row(ws: Any, row: int, labels: list[str], dark: bool = True) -> None:
    """Linha de cabeçalho colorida."""
    bg = _C["nav_dk"] if dark else _C["nav_md"]
    for col, text in enumerate(labels, 1):
        cell = ws.cell(row=row, column=col, value=text)
        cell.fill = _fill(bg)
        cell.font = _font(bold=True, color=_C["white"], size=10)
        cell.alignment = _align("center", wrap=True)
        cell.border = _border()


def _title_row(ws: Any, row: int, title: str, n_cols: int, color: str = "nav_dk") -> None:
    """Linha de título mesclada."""
    ws.cell(row=row, column=1, value=title).value = title
    if n_cols > 1:
        ws.merge_cells(
            start_row=row,
            start_column=1,
            end_row=row,
            end_column=n_cols,
        )
    cell = ws.cell(row=row, column=1)
    cell.fill = _fill(_C[color])
    cell.font = _font(bold=True, color=_C["white"], size=12)
    cell.alignment = _align("center")
    cell.border = _border()


def _section_row(ws: Any, row: int, title: str, n_cols: int) -> None:
    """Sub-cabeçalho de seção."""
    if n_cols > 1:
        ws.merge_cells(
            start_row=row,
            start_column=1,
            end_row=row,
            end_column=n_cols,
        )
    cell = ws.cell(row=row, column=1)
    cell.value = title
    cell.fill = _fill(_C["cinza_lt"])
    cell.font = _font(bold=True, color=_C["nav_dk"], size=10)
    cell.alignment = _align("left")
    cell.border = _border()


def _set_col_widths(ws: Any, widths: list[int | float]) -> None:
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w


def _auto_fit_columns(ws: Any, min_width: float = 8.0, max_width: float = 42.0, padding: float = 2.0) -> None:
    """Ajusta largura das colunas com base no maior valor textual visível."""
    for column_cells in ws.columns:
        max_len = 0
        column_letter = get_column_letter(column_cells[0].column)
        for cell in column_cells:
            if cell.value is None:
                continue
            value = cell.value
            if isinstance(value, (int, float)):
                text = f"{value:,.2f}"
            else:
                text = str(value)
            max_len = max(max_len, len(text))
        if max_len > 0:
            ws.column_dimensions[column_letter].width = min(max_width, max(min_width, max_len + padding))


def _freeze(ws: Any, cell: str) -> None:
    ws.freeze_panes = cell


def _fmt_mes(ym: tuple[int, int]) -> str:
    return f"{MESES_PT[ym[1]]}/{str(ym[0])[-2:]}"


# ── Cálculos de fluxo de caixa ────────────────────────────────────────────────


def _week_to_month(week_str: str) -> tuple[int, int]:
    """'2026-W23' -> (2026, 6) — mês da segunda-feira dessa semana ISO."""
    year_str, w_str = week_str.split("-W")
    monday = date.fromisocalendar(int(year_str), int(w_str), 1)
    return monday.year, monday.month


def _project_months(canonical: CanonicalModel) -> list[tuple[int, int]]:
    """Lista ordenada de (ano, mês) cobrindo todo o projeto."""
    months: set[tuple[int, int]] = set()
    if canonical.cronograma:
        for act in canonical.cronograma.scheduled_activities:
            for week_key in act.distribuicao_semanal:
                months.add(_week_to_month(week_key))
    if not months and canonical.projeto:
        p = canonical.projeto
        if p.data_inicio and p.data_termino:
            d = p.data_inicio
            while d <= p.data_termino:
                months.add((d.year, d.month))
                # Avança para o próximo mês
                if d.month == 12:
                    d = date(d.year + 1, 1, 1)
                else:
                    d = date(d.year, d.month + 1, 1)
    return sorted(months)


def _monthly_direct_costs(
    canonical: CanonicalModel,
    project_months: list[tuple[int, int]],
) -> dict[tuple[int, int], float]:
    """Despesa direta por mês: custo catálogo (s/BDI) distribuído
    proporcionalmente à quantidade executada por semana.
    """
    result: dict[tuple[int, int], float] = {ym: 0.0 for ym in project_months}
    if not canonical.cronograma or not canonical.planejamento:
        return result

    # Custo unitário catálogo (s/BDI) por item
    cost_per_unit: dict[str, float] = {}
    for p in canonical.planejamento:
        total = p.subtotal.sem_bdi.total if p.subtotal else 0.0
        qty = p.quantitativo or 1.0
        cost_per_unit[p.item_id] = total / qty if qty > 0 else 0.0

    for act in canonical.cronograma.scheduled_activities:
        cpu = cost_per_unit.get(act.activity_id, 0.0)
        if cpu <= 0:
            continue
        for week_key, dist in act.distribuicao_semanal.items():
            qtd = getattr(dist, "qtd_executada", 0.0)
            if qtd <= 0:
                continue
            ym = _week_to_month(week_key)
            if ym in result:
                result[ym] += cpu * qtd

    return result


def _monthly_indirect_costs(
    canonical: CanonicalModel,
    project_months: list[tuple[int, int]],
) -> dict[tuple[int, int], float]:
    """Despesa indireta por mês.

    MOB: concentrado no mês 1 (mobilização) e ignorado no final (simplificação).
    ADM/TOP/LAB/QSMS: distribuídos uniformemente pelos meses de permanência.
    """
    result: dict[tuple[int, int], float] = {ym: 0.0 for ym in project_months}
    n = len(project_months)
    if n == 0:
        return result

    for ind in canonical.indiretos:
        if ind.categoria == "MOB":
            result[project_months[0]] += ind.custo_total
        else:
            perm = int(ind.permanencia_meses or n)
            meses_ativos = project_months[: min(perm, n)]
            if meses_ativos:
                por_mes = ind.custo_total / len(meses_ativos)
                for ym in meses_ativos:
                    result[ym] += por_mes

    return result


def _next_month(ym: tuple[int, int]) -> tuple[int, int]:
    """Retorna o mês seguinte ao dado."""
    year, month = ym
    return (year + 1, 1) if month == 12 else (year, month + 1)


def _cash_flow(
    canonical: CanonicalModel,
) -> list[dict[str, Any]]:
    """Retorna lista de registros mensais de fluxo de caixa.

    Esquema de receita (n = duração do projeto em meses):
      • Mês 1          : receita = 0           (empresa inicia sem recebimento)
      • Meses 2 .. n   : receita = floor(M/n)  cada
      • Mês n+1        : receita = M − floor(M/n)×(n−1)  (resíduo, mês extra pós-execução)

    Total verificado: 0 + (n−1)×floor(M/n) + (M − floor(M/n)×(n−1)) = M ✓

    Exposição = despesa_acumulada − receita_acumulada.
    Positivo -> empresa desembolsou mais do que recebeu (necessidade de capital de giro).
    """
    project_months = _project_months(canonical)
    n = len(project_months)
    if n == 0 or canonical.resultado is None:
        return []

    M = canonical.resultado.venda.total_com_bdi
    parcela_base = math.floor(M / n)
    residuo = M - parcela_base * (n - 1)

    # Meses de execução + 1 mês extra para o resíduo
    all_months = project_months + [_next_month(project_months[-1])]

    # Receita por posição: índice 0 = mês 1 (zero), índices 1..n-1 = parcela_base, índice n = resíduo
    receitas: list[float] = [0.0] + [float(parcela_base)] * (n - 1) + [float(residuo)]

    direct = _monthly_direct_costs(canonical, project_months)
    indirect = _monthly_indirect_costs(canonical, project_months)

    rows = []
    acum_despesa = 0.0
    acum_receita = 0.0
    for i, ym in enumerate(all_months):
        despesa = direct.get(ym, 0.0) + indirect.get(ym, 0.0)
        receita = receitas[i]
        saldo = receita - despesa
        acum_despesa += despesa
        acum_receita += receita
        rows.append(
            {
                "mes_label": _fmt_mes(ym),
                "mes_ym": ym,
                "despesa": despesa,
                "receita": receita,
                "despesa_acumulada": acum_despesa,
                "receita_acumulada": acum_receita,
                "saldo": saldo,
                "saldo_atual": acum_receita - acum_despesa,  # = -(exposição)
                "exposicao_acumulada": acum_despesa - acum_receita,
            }
        )
    return rows


def _monthly_qty_by_item(
    canonical: CanonicalModel,
    project_months: list[tuple[int, int]],
) -> dict[str, dict[tuple[int, int], float]]:
    """Para cada activity_id, qtd executada por mês."""
    result: dict[str, dict[tuple[int, int], float]] = {}
    if not canonical.cronograma:
        return result
    for act in canonical.cronograma.scheduled_activities:
        per_month: dict[tuple[int, int], float] = {ym: 0.0 for ym in project_months}
        for week_key, dist in act.distribuicao_semanal.items():
            ym = _week_to_month(week_key)
            if ym in per_month:
                per_month[ym] += getattr(dist, "qtd_executada", 0.0)
        result[act.activity_id] = per_month
    return result


# ── Aba DIRETOS ───────────────────────────────────────────────────────────────


def _xl_diretos_labor(ws: object, row: int, eq: object, fill_base: object, PAPEL_COLOR: dict) -> int:
    for func in eq.funcoes:  # type: ignore[union-attr]
        custo_unit = func.custo_mensal_unitario if func.custo_mensal_unitario else 0.0
        papel = getattr(func, "papel", "direto") or "direto"
        papel_color = PAPEL_COLOR.get(papel, _C["preto"])
        _label(ws, row, 1, "MÃO DE OBRA", fill_base)
        _label(ws, row, 2, func.funcao_id, fill_base)
        _label(ws, row, 3, func.descricao or func.funcao_id, fill_base)
        _label(ws, row, 4, papel.upper(), fill_base, bold=True, color=papel_color, align="center")
        _label(ws, row, 5, func.num_pessoas, fill_base, align="right")
        _money(ws, row, 6, custo_unit, fill_base)
        _money(ws, row, 7, f"=E{row}*F{row}", fill_base)
        _label(ws, row, 8, round(eq.permanencia_meses, 2), fill_base, align="right")  # type: ignore[union-attr]
        _money(ws, row, 9, f"=G{row}*H{row}", fill_base)
        row += 1
    return row


def _xl_diretos_equip(ws: object, row: int, eq: object, fill_base: object) -> int:
    for equip in eq.equipamentos:  # type: ignore[union-attr]
        n_un = getattr(equip, "num_unidades", 1) or 1
        custo_equip_u = getattr(equip, "custo_mensal", 0.0) or 0.0
        _label(ws, row, 1, "EQUIPAMENTO", fill_base)
        _label(ws, row, 2, equip.equip_id, fill_base)
        _label(ws, row, 3, getattr(equip, "descricao", equip.equip_id), fill_base)
        _label(ws, row, 4, "—", fill_base, align="center")
        _label(ws, row, 5, n_un, fill_base, align="right")
        _money(ws, row, 6, custo_equip_u, fill_base)
        _money(ws, row, 7, f"=E{row}*F{row}", fill_base)
        _label(ws, row, 8, round(eq.permanencia_meses, 2), fill_base, align="right")  # type: ignore[union-attr]
        _money(ws, row, 9, f"=G{row}*H{row}", fill_base)
        row += 1
        custo_comb_u = getattr(equip, "custo_combustivel_mensal", 0.0) or 0.0
        if custo_comb_u > 0:
            consumo_str = f"{equip.consumo_litros_hora:.1f} L/h" if getattr(equip, "consumo_litros_hora", None) else "—"
            _label(ws, row, 1, "COMBUSTÍVEL", fill_base, bold=False, color=_C["orange"])
            _label(ws, row, 2, equip.equip_id, fill_base)
            _label(ws, row, 3, f"Diesel S-10 ({consumo_str})", fill_base)
            _label(ws, row, 4, "—", fill_base, align="center")
            _label(ws, row, 5, n_un, fill_base, align="right")
            _money(ws, row, 6, custo_comb_u, fill_base)
            _money(ws, row, 7, f"=E{row}*F{row}", fill_base)
            _label(ws, row, 8, round(eq.permanencia_meses, 2), fill_base, align="right")  # type: ignore[union-attr]
            _money(ws, row, 9, f"=G{row}*H{row}", fill_base)
            row += 1
    return row


def _xl_diretos_material(ws: object, row: int, eq: object, fill_base: object) -> int:
    custo_mat = getattr(eq, "custo_material_mensal", 0.0) or 0.0
    if custo_mat > 0:
        _label(ws, row, 1, "MATERIAL", fill_base, bold=False, color=_C["nav_md"])
        _label(ws, row, 2, eq.item_id, fill_base)  # type: ignore[union-attr]
        _label(ws, row, 3, "Materiais diretos", fill_base)
        _label(ws, row, 4, "—", fill_base, align="center")
        _label(ws, row, 5, 1, fill_base, align="right")
        _money(ws, row, 6, custo_mat, fill_base)
        _money(ws, row, 7, f"=E{row}*F{row}", fill_base)
        _label(ws, row, 8, round(eq.permanencia_meses, 2), fill_base, align="right")  # type: ignore[union-attr]
        _money(ws, row, 9, f"=G{row}*H{row}", fill_base)
        row += 1
    return row


def _xl_diretos_subtotal(
    ws: object, row: int, eq: object, fill_sub: object, start_row: int, subtotal_rows: list
) -> None:
    _label(ws, row, 1, f"Subtotal {eq.item_id}", fill_sub, bold=True)  # type: ignore[union-attr]
    for c in range(2, 9):
        ws.cell(row=row, column=c).fill = fill_sub  # type: ignore[union-attr]
        ws.cell(row=row, column=c).border = _border()  # type: ignore[union-attr]
    _money(ws, row, 7, f"=SUM(G{start_row}:G{row - 1})", fill_sub, bold=True, color=_C["orange"])
    _label(ws, row, 8, round(eq.permanencia_meses, 2), fill_sub, bold=True, align="right")  # type: ignore[union-attr]
    _money(ws, row, 9, f"=SUM(I{start_row}:I{row - 1})", fill_sub, bold=True, color=_C["orange"])
    subtotal_rows.append(row)


def render_diretos(wb: Workbook, canonical: CanonicalModel) -> int:
    """DIRETOS — composição granular por item EAP: mão de obra (com papel), equipamento,
    combustível (linha separada por equipamento) e materiais diretos.

    Retorna o número da linha do TOTAL DIRETO para referência cruzada em RESULTADO.
    """
    ws = wb.create_sheet("DIRETOS.DET")
    NCOLS = 9
    _set_col_widths(ws, [14, 20, 36, 10, 6, 16, 16, 10, 16])
    _freeze(ws, "A3")
    row = 1
    _title_row(ws, row, "DIRETOS — EQUIPES E RECURSOS", NCOLS)
    row += 1
    headers = [
        "Tipo",
        "Código",
        "Descrição",
        "Papel",
        "Qtd",
        "Custo Unit/Mês (R$)",
        "Custo Total/Mês (R$)",
        "Perm. (meses)",
        "Custo Total (R$)",
    ]
    _header_row(ws, row, headers)
    row += 1
    ws.freeze_panes = f"A{row}"
    _PAPEL_COLOR = {"direto": _C["verde"], "indireto": _C["nav_md"], "gestao": _C["orange"]}
    subtotal_rows: list[int] = []
    for i_eq, eq in enumerate(canonical.equipes_diretas):
        eap_item = next((e for e in canonical.eap if e.item_id == eq.item_id), None)
        descricao_item = eap_item.descricao if eap_item else eq.item_id
        _section_row(ws, row, f"{eq.item_id} — {descricao_item}", NCOLS)
        row += 1
        start_row = row
        fill_base = _fill(_C["white"]) if i_eq % 2 == 0 else _fill(_C["row_alt"])
        row = _xl_diretos_labor(ws, row, eq, fill_base, _PAPEL_COLOR)
        row = _xl_diretos_equip(ws, row, eq, fill_base)
        row = _xl_diretos_material(ws, row, eq, fill_base)
        fill_sub = _fill(_C["orange_lt"])
        _xl_diretos_subtotal(ws, row, eq, fill_sub, start_row, subtotal_rows)
        row += 1
    row += 1
    total_row = row
    fill_tot = _fill(_C["nav_dk"])
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=8)
    cell = ws.cell(row=row, column=1, value="TOTAL DIRETO")
    cell.fill = fill_tot
    cell.font = _font(bold=True, color=_C["white"], size=11)
    cell.alignment = _align("right")
    cell.border = _border()
    f_tot = f"={'+'.join(f'I{r}' for r in subtotal_rows)}" if subtotal_rows else 0.0
    _money(ws, row, 9, f_tot, fill_tot, bold=True, color=_C["white"])
    wb.defined_names["TOTAL_DIRETO"] = DefinedName(
        "TOTAL_DIRETO",
        attr_text=f"'DIRETOS.DET'!${get_column_letter(9)}${total_row}",
    )
    _auto_fit_columns(ws)
    return total_row


# ── Aba INDIRETOS ─────────────────────────────────────────────────────────────


def _xl_indirect_fallback_totals(resultado: Any) -> dict:
    """Build fallback totals dict from resultado.custo (6 ternaries)."""
    res_custo = resultado.custo if resultado else None
    return {
        "ADM": getattr(res_custo, "indireto_adm", 0.0) if res_custo else 0.0,
        "TOP": getattr(res_custo, "indireto_top", 0.0) if res_custo else 0.0,
        "LAB": getattr(res_custo, "indireto_lab", 0.0) if res_custo else 0.0,
        "QSMS": getattr(res_custo, "indireto_qsms", 0.0) if res_custo else 0.0,
        "MOB": getattr(res_custo, "indireto_mob", 0.0) if res_custo else 0.0,
    }


def _xl_indirect_funcoes_rows(ws: Any, row: int, ind: Any, cat: str, perm: int, fill_base: Any) -> int:
    """Write mao-de-obra rows for indirect category; returns updated row."""
    for func in ind.funcoes if ind is not None else []:
        qtd = func.get("quantidade", 1)
        custo_mes = func.get("custo_mensal", 0.0)
        nome_func = func.get("funcao", "—")
        _label(ws, row, 1, cat, fill_base, bold=True, color=_C["nav_dk"])
        _label(ws, row, 2, "MÃO DE OBRA", fill_base)
        _label(ws, row, 3, nome_func, fill_base)
        _label(ws, row, 4, nome_func, fill_base)
        _label(ws, row, 5, qtd, fill_base, align="right")
        _money(ws, row, 6, custo_mes, fill_base)
        _label(ws, row, 7, perm, fill_base, align="right")
        _money(ws, row, 8, f"=E{row}*F{row}*G{row}", fill_base)
        row += 1
    return row


def _xl_indirect_verbas_mensais_rows(ws: Any, row: int, ind: Any, cat: str, perm: int, fill_base: Any) -> int:
    """Write monthly-allowance rows; returns updated row."""
    for verba in ind.verbas_mensais if ind is not None else []:
        custo_mes = verba.get("valor_mensal", 0.0)
        desc = verba.get("descricao", "—")
        _label(ws, row, 1, cat, fill_base, bold=True, color=_C["nav_dk"])
        _label(ws, row, 2, "VERBA MENSAL", fill_base)
        _label(ws, row, 3, "—", fill_base)
        _label(ws, row, 4, desc, fill_base)
        _label(ws, row, 5, 1, fill_base, align="right")
        _money(ws, row, 6, custo_mes, fill_base)
        _label(ws, row, 7, perm, fill_base, align="right")
        _money(ws, row, 8, f"=E{row}*F{row}*G{row}", fill_base)
        row += 1
    return row


def _xl_indirect_verbas_fixas_rows(ws: Any, row: int, ind: Any, cat: str, perm: int, fill_base: Any) -> int:
    """Write fixed-allowance rows; returns updated row."""
    for verba in ind.verbas_fixas if ind is not None else []:
        custo_tot = verba.get("valor_total", verba.get("valor_mensal", 0.0))
        desc = verba.get("descricao", "—")
        _label(ws, row, 1, cat, fill_base, bold=True, color=_C["nav_dk"])
        _label(ws, row, 2, "VERBA FIXA", fill_base)
        _label(ws, row, 3, "—", fill_base)
        _label(ws, row, 4, desc, fill_base)
        _label(ws, row, 5, 1, fill_base, align="right")
        _money(ws, row, 6, 0.0, fill_base)
        _label(ws, row, 7, 1, fill_base, align="right")
        _money(ws, row, 8, custo_tot, fill_base)
        row += 1
    return row


def _xl_indirect_mob_rows(ws: Any, row: int, ind: Any, cat: str, fill_base: Any) -> int:
    """Write mobilization rows; returns updated row."""
    for mob in ind.mobilizacoes if ind is not None else []:
        rota = f"{mob.origem} -> {mob.destino} ({mob.distancia_km:.0f} km)"
        _label(ws, row, 1, cat, fill_base, bold=True, color=_C["nav_dk"])
        _label(ws, row, 2, "MOBILIZAÇÃO", fill_base)
        _label(ws, row, 3, rota, fill_base)
        _label(ws, row, 4, mob.descricao, fill_base)
        _label(ws, row, 5, mob.num_unidades, fill_base, align="right")
        _money(ws, row, 6, mob.custo_km * mob.distancia_km, fill_base)
        _label(ws, row, 7, 1, fill_base, align="right")
        _money(ws, row, 8, f"=E{row}*F{row}", fill_base)
        row += 1
    return row


def _xl_indirect_fallback_row(
    ws: Any, row: int, start_row: int, cat: str, cat_desc: str, cat_total: float, perm: int, fill_base: Any
) -> int:
    """Write summary fallback row when no detail lines were written."""
    if row == start_row:
        _label(ws, row, 1, cat, fill_base, bold=True, color=_C["nav_dk"])
        _label(ws, row, 2, "CUSTO TOTAL", fill_base)
        _label(ws, row, 3, "—", fill_base)
        _label(ws, row, 4, cat_desc, fill_base)
        _label(ws, row, 5, 1, fill_base, align="right")
        _money(ws, row, 6, 0.0, fill_base)
        _label(ws, row, 7, perm, fill_base, align="right")
        _money(ws, row, 8, cat_total, fill_base)
        row += 1
    return row


def _xl_indirect_subtotal_row(
    ws: Any, row: int, cat: str, start_row: int, cat_total_rows: dict, subtotal_rows: list, wb: Any
) -> int:
    """Write subtotal row for an indirect category; returns row+1."""
    fill_sub = _fill(_C["orange_lt"])
    _label(ws, row, 1, f"Subtotal {cat}", fill_sub, bold=True)
    for c in range(2, 8):
        ws.cell(row=row, column=c).fill = fill_sub
        ws.cell(row=row, column=c).border = _border()
    _money(ws, row, 8, f"=SUM(H{start_row}:H{row - 1})", fill_sub, bold=True, color=_C["orange"])
    cat_total_rows[cat] = row
    subtotal_rows.append(row)
    wb.defined_names[f"TOTAL_{cat}"] = DefinedName(
        f"TOTAL_{cat}",
        attr_text=f"'INDIRETOS.DET'!${get_column_letter(8)}${row}",
    )
    return row + 1


def _xl_indirect_monthly_section(ws: Any, row: int, project_months: list, indirect_monthly: dict, NCOLS: int) -> None:
    """Write the auxiliary monthly distribution table."""
    if project_months:
        row += 3
        _section_row(ws, row, "Distribuição Mensal de Indiretos", NCOLS)
        row += 1
        _header_row(ws, row, ["Mês", "Despesa Indireta (R$)"] + [""] * (NCOLS - 2), dark=False)
        row += 1
        for ym in project_months:
            v = indirect_monthly.get(ym, 0.0)
            fill_row = _fill(_C["white"]) if ym[1] % 2 == 0 else _fill(_C["row_alt"])
            _label(ws, row, 1, _fmt_mes(ym), fill_row)
            _money(ws, row, 2, v, fill_row)
            for c in range(3, NCOLS + 1):
                ws.cell(row=row, column=c).fill = fill_row
                ws.cell(row=row, column=c).border = _border()
            row += 1


def render_indiretos_ml(wb: Workbook, canonical: CanonicalModel) -> dict[str, int]:
    """INDIRETOS — composição granular por categoria.

    Cada categoria é expandida em linhas individuais: mão de obra, verbas mensais,
    verbas fixas e mobilizações. Subtotais por categoria e total geral.

    Colunas: Categoria | Tipo | Código/Função | Descrição | Qtd |
             Custo Mensal | Custo Total

    Retorna {cat: subtotal_row, 'total': overall_total_row} para referências
    cruzadas na aba RESULTADO via named ranges "TOTAL_{CAT}" / "TOTAL_INDIRETO".
    """
    ws = wb.create_sheet("INDIRETOS.DET")

    project_months = _project_months(canonical)
    indirect_monthly = _monthly_indirect_costs(canonical, project_months)

    NCOLS = 8
    _set_col_widths(ws, [12, 16, 22, 36, 6, 18, 10, 18])
    _freeze(ws, "A3")

    row = 1
    _title_row(ws, row, "INDIRETOS — CUSTOS INDIRETOS DETALHADOS", NCOLS)
    row += 1

    headers = [
        "Categoria",
        "Tipo",
        "Código/Função",
        "Descrição",
        "Qtd",
        "Custo Mensal (R$)",
        "Perm. (m)",
        "Custo Total (R$)",
    ]
    _header_row(ws, row, headers)
    row += 1
    ws.freeze_panes = f"A{row}"

    ORDEM_CAT = ["ADM", "TOP", "LAB", "QSMS", "MOB"]
    inds_by_cat = {ind.categoria: ind for ind in canonical.indiretos}
    fallback_totals = _xl_indirect_fallback_totals(canonical.resultado)

    cat_total_rows: dict[str, int] = {}
    subtotal_rows = []

    for i_cat, cat in enumerate(ORDEM_CAT):
        ind = inds_by_cat.get(cat)  # type: ignore[call-overload]
        fallback_total = fallback_totals.get(cat, 0.0)

        perm = (ind.permanencia_meses if ind is not None else 0) or max(len(project_months), 1)
        cat_desc = ind.descricao if ind is not None else "Sem detalhamento na fonte — subtotal da categoria"
        cat_total = ind.custo_total if ind is not None else fallback_total
        fill_base = _fill(_C["white"]) if i_cat % 2 == 0 else _fill(_C["row_alt"])

        _section_row(ws, row, f"{cat} — {cat_desc}", NCOLS)
        row += 1
        start_row = row
        row = _xl_indirect_funcoes_rows(ws, row, ind, cat, perm, fill_base)
        row = _xl_indirect_verbas_mensais_rows(ws, row, ind, cat, perm, fill_base)
        row = _xl_indirect_verbas_fixas_rows(ws, row, ind, cat, perm, fill_base)
        row = _xl_indirect_mob_rows(ws, row, ind, cat, fill_base)
        row = _xl_indirect_fallback_row(ws, row, start_row, cat, cat_desc, cat_total, perm, fill_base)
        row = _xl_indirect_subtotal_row(ws, row, cat, start_row, cat_total_rows, subtotal_rows, wb)

    # ── Total geral ──────────────────────────────────────────────────────────
    row += 1
    total_row = row
    fill_tot = _fill(_C["nav_dk"])
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=7)
    cell = ws.cell(row=row, column=1, value="TOTAL INDIRETO")
    cell.fill = fill_tot
    cell.font = _font(bold=True, color=_C["white"], size=11)
    cell.alignment = _align("right")
    cell.border = _border()
    f_tot = f"={'+'.join(f'H{r}' for r in subtotal_rows)}" if subtotal_rows else 0.0
    _money(ws, row, 8, f_tot, fill_tot, bold=True, color=_C["white"])

    wb.defined_names["TOTAL_INDIRETO"] = DefinedName(
        "TOTAL_INDIRETO",
        attr_text=f"'INDIRETOS.DET'!${get_column_letter(8)}${total_row}",
    )
    cat_total_rows["total"] = total_row

    _xl_indirect_monthly_section(ws, row, project_months, indirect_monthly, NCOLS)
    return cat_total_rows


def _xl_plan_sem_vals(sem: Any) -> tuple[float, float, float, float]:
    """s/BDI component values (mo, eq, diesel, mat) — 4 ternaries."""
    return (
        sem.mao_obra if sem else 0.0,
        sem.equipamentos if sem else 0.0,
        sem.diesel if sem else 0.0,
        sem.material if sem else 0.0,
    )


def _xl_plan_row_fill(i: int, classe: str | None, CRIT_HEX: dict) -> Any:
    """Row fill based on criticidade class."""
    crit_hex = CRIT_HEX.get(classe) if classe else None
    return _fill(crit_hex) if crit_hex else (_fill(_C["white"]) if i % 2 == 0 else _fill(_C["row_alt"]))


def _xl_plan_row_vals(
    p: Any,
    eap_item: Any,
    classe: str | None,
    row: int,
    has_crit: bool,
    mo_s: float,
    eq_s: float,
    dsl_s: float,
    mat_s: float,
) -> list[Any]:
    """Construct the values list for one planning row."""
    tot_s = f"=E{row}+G{row}+I{row}+K{row}"
    tot_c = f"=F{row}+H{row}+J{row}+L{row}"
    mo_c = f"=E{row}*(1+BDI!$M$3)"
    eq_c = f"=G{row}*(1+BDI!$M$5)"
    dsl_c = f"=I{row}*(1+BDI!$M$7)"
    mat_c = f"=K{row}*(1+BDI!$M$4)"
    vals: list[Any] = [
        p.item_id,
        eap_item.descricao if eap_item else p.cpu_id,
        eap_item.unidade if eap_item else "un",
        p.quantitativo,
        mo_s,
        mo_c,
        eq_s,
        eq_c,
        dsl_s,
        dsl_c,
        mat_s,
        mat_c,
        tot_s,
        tot_c,
    ]
    if has_crit:
        vals.append(classe or "—")
    return vals


def _xl_plan_write_data_row(ws: Any, row: int, vals: list[Any], row_fill: Any) -> None:
    """Write one planning row with numeric formatting."""
    for col, v in enumerate(vals, 1):
        cell = ws.cell(row=row, column=col, value=v)
        cell.fill = row_fill
        cell.border = _border()
        if 5 <= col <= 14:
            cell.number_format = "#,##0.00"
            cell.alignment = _align("right")
        elif col == 4:
            cell.number_format = "#,##0.##"
            cell.alignment = _align("right")
        else:
            cell.alignment = _align("left")


def _xl_plan_data_rows(
    ws: Any,
    row: int,
    planejamento_sorted: list[Any],
    canonical_eap: list[Any],
    has_crit: bool,
    criticidade_lookup: dict,
    CRIT_HEX: dict,
) -> int:
    """Write all EAP planning data rows; returns updated row."""
    for i, p in enumerate(planejamento_sorted):
        eap_item = next((e for e in canonical_eap if e.item_id == p.item_id), None)
        sem = p.subtotal.sem_bdi if p.subtotal else None
        classe = criticidade_lookup.get(p.item_id) if has_crit else None
        mo_s, eq_s, dsl_s, mat_s = _xl_plan_sem_vals(sem)
        row_fill = _xl_plan_row_fill(i, classe, CRIT_HEX)
        vals = _xl_plan_row_vals(p, eap_item, classe, row, has_crit, mo_s, eq_s, dsl_s, mat_s)
        _xl_plan_write_data_row(ws, row, vals, row_fill)
        row += 1
    return row


def render_planejamento_ml(wb: Workbook, canonical: CanonicalModel) -> int | None:
    """PLANEJAMENTO — EAP ordenada topologicamente, componentes s/BDI e c/BDI por item.

      Colunas (sem criticidade = 14, com criticidade = 15):
    1  Item ID
    2  Descrição
    3  Un.
    4  Quantitativo
          5  MO s/BDI
          6  MO c/BDI
          7  EQ s/BDI
          8  EQ c/BDI
          9  Combustível s/BDI
          10 Combustível c/BDI
          11 Material s/BDI
          12 Material c/BDI
          13 Total s/BDI
          14 Total c/BDI         ← TOTAL_COM_BDI
    15 Criticidade (se disponível)
    """
    ws = wb.create_sheet("PLANEJAMENTO")

    criticidade_lookup: dict[str, str] = {}
    if canonical.cost_criticality_report is not None:
        for prof in canonical.cost_criticality_report.atividades:
            criticidade_lookup[prof.atividade_id] = prof.classe
    has_crit = bool(criticidade_lookup)

    _CRIT_HEX = {"A+": "FF4444", "A": "FFA500", "B": "FFFF33"}

    # Ordenação topológica pelo campo EapItem.ordem
    eap_ordem: dict[str, int] = {e.item_id: e.ordem for e in canonical.eap}
    planejamento_sorted = sorted(
        canonical.planejamento,
        key=lambda p: eap_ordem.get(p.item_id, 9999),
    )

    NCOLS = 15 if has_crit else 14
    _set_col_widths(ws, [12, 42, 6, 13, 15, 15, 13, 13, 17, 15, 15, 13, 13, 17, 12][:NCOLS])  # type: ignore[arg-type]
    _freeze(ws, "C3")

    row = 1
    _title_row(ws, row, "PLANEJAMENTO — ORÇAMENTO POR EAP (COMPONENTES s/BDI e c/BDI)", NCOLS)
    row += 1

    headers = [
        "Item ID",
        "Descrição",
        "Un.",
        "Quantitativo",
        "MO s/BDI (R$)",
        "MO c/BDI (R$)",
        "EQ s/BDI (R$)",
        "EQ c/BDI (R$)",
        "Comb. s/BDI (R$)",
        "Comb. c/BDI (R$)",
        "MAT s/BDI (R$)",
        "MAT c/BDI (R$)",
        "Total s/BDI (R$)",
        "Total c/BDI (R$)",
    ]
    if has_crit:
        headers.append("Criticidade")
    _header_row(ws, row, headers)
    row += 1
    ws.freeze_panes = f"C{row}"

    data_start = row
    row = _xl_plan_data_rows(ws, row, planejamento_sorted, canonical.eap, has_crit, criticidade_lookup, _CRIT_HEX)

    # Linha em branco + total
    row += 1
    total_row = row
    fill_tot = _fill(_C["nav_dk"])
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
    cell = ws.cell(row=row, column=1, value="TOTAL")
    cell.fill = fill_tot
    cell.font = _font(bold=True, color=_C["white"], size=11)
    cell.alignment = _align("right")
    cell.border = _border()
    for c in range(5, 15):
        col_letter = get_column_letter(c)
        _money(
            ws, row, c, f"=SUM({col_letter}{data_start}:{col_letter}{row - 1})", fill_tot, bold=True, color=_C["white"]
        )

    # Named ranges — col 13 = sem_bdi, col 14 = com_bdi (para aba RESULTADO)
    wb.defined_names["TOTAL_SEM_BDI"] = DefinedName(
        "TOTAL_SEM_BDI",
        attr_text=f"PLANEJAMENTO!${get_column_letter(13)}${total_row}",
    )
    wb.defined_names["TOTAL_COM_BDI"] = DefinedName(
        "TOTAL_COM_BDI",
        attr_text=f"PLANEJAMENTO!${get_column_letter(14)}${total_row}",
    )
    _auto_fit_columns(ws)
    return total_row


# ── Aba CRONOGRAMA — helpers ─────────────────────────────────────────────────

_CRONOGRAMA_METRICS = [
    ("Dias Trabalhados", "dias", "0"),
    ("Nº De Equipes", "n_eq", "0"),
    ("Qtd. Planejada", "qtd_exec", "#,##0.00"),
    ("Qtd Plan. Acumulada", "qtd_acum", "#,##0.00"),
    ("% Semanal", "pct_sem", "0.00%"),
    ("% Acumulado", "pct_acum", "0.00%"),
]


def _wk_label(wk: str) -> str:
    yr, wn = wk.split("-W")
    mon = date.fromisocalendar(int(yr), int(wn), 1)
    return f"{mon.day:02d}/{MESES_PT[mon.month]}"


def _compute_pct(qtd: float, total_item: float) -> Any | None:
    if total_item > 0 and qtd > 0:
        return round(qtd / total_item, 4)
    return None


def _cronograma_qtd_val(key: str, wk_entry: dict, accum_prop: dict, wk: str) -> Any:
    v = wk_entry.get("qtd_exec", 0.0) if key == "qtd_exec" else accum_prop.get(wk, 0.0)
    return round(v, 2) if v else None


def _compute_cell_metric(
    key: str,
    wk_entry: dict,
    accum_prop: dict,
    wk: str,
    total_item: float,
    dias_semana: int,
) -> Any:
    n_eq = wk_entry.get("n_eq", 0)
    if key == "dias":
        return dias_semana if n_eq > 0 else None
    if key == "n_eq":
        return n_eq if n_eq > 0 else None
    if key in ("qtd_exec", "qtd_acum"):
        return _cronograma_qtd_val(key, wk_entry, accum_prop, wk)
    if key == "pct_sem":
        return _compute_pct(wk_entry.get("qtd_exec", 0.0), total_item)
    if key == "pct_acum":
        return _compute_pct(accum_prop.get(wk, 0.0), total_item)
    return None


def _build_act_lookup_and_totals(acts: list) -> tuple[dict, dict, list[str]]:
    act_lookup: dict[str, dict[str, Any]] = {}
    item_totals: dict[str, float] = {}
    all_weeks_set: set[str] = set()
    for act in acts:
        all_weeks_set.update(act.distribuicao_semanal.keys())
        act_lookup[act.activity_id] = {
            wk: {
                "n_eq": getattr(d, "num_equipes", 0),
                "qtd_exec": getattr(d, "qtd_executada", 0.0),
                "qtd_acum": getattr(d, "qtd_acumulada", 0.0),
            }
            for wk, d in act.distribuicao_semanal.items()
        }
        if act.distribuicao_semanal:
            last_week = sorted(act.distribuicao_semanal.keys())[-1]
            item_totals[act.activity_id] = getattr(act.distribuicao_semanal[last_week], "qtd_acumulada", 0.0)
    return act_lookup, item_totals, sorted(all_weeks_set)


def _compute_accum_prop(wk_data: dict, all_weeks: list) -> tuple[dict, float]:
    accum_prop: dict[str, float] = {}
    last_acum = 0.0
    for wk in all_weeks:
        wk_entry = wk_data.get(wk, {})
        acum_wk = float(wk_entry.get("qtd_acum", 0.0) or 0.0)
        if acum_wk > 0:
            last_acum = acum_wk
        accum_prop[wk] = last_acum
    return accum_prop, last_acum


def _get_pratic_map(canonical: CanonicalModel) -> dict:
    if canonical.praticabilidade:
        return canonical.praticabilidade.percentual_produtivo_semanal or {}
    return {}


def _render_praticabilidade_row(ws: Any, row: int, all_weeks: list, pratic_map: dict) -> None:
    pratic_fill = _fill(_C["amar_lt"])
    for col_p, wk_p in enumerate(["", "", "", "", "Praticabilidade"] + list(all_weeks), 1):
        cell_p = ws.cell(row=row, column=col_p)
        cell_p.fill = pratic_fill
        cell_p.border = _border()
        if isinstance(wk_p, str) and wk_p.startswith("20") and "-W" in wk_p:
            v_p = pratic_map.get(wk_p, 1.0)
            cell_p.value = v_p
            cell_p.number_format = "0%"
            cell_p.alignment = _align("center")
            cell_p.font = _font(bold=(v_p < 1.0), color=_C["orange"] if v_p < 1.0 else _C["preto"])
        elif wk_p == "Praticabilidade":
            cell_p.value = wk_p
            cell_p.font = _font(bold=True, color=_C["amarelo"])
            cell_p.alignment = _align("left")


def _render_item_metrics_rows(
    ws: Any,
    row: int,
    item: Any,
    wk_data: dict,
    accum_prop: dict,
    total_item: float,
    all_weeks: list,
    ncols_fixed: int,
    dias_semana: int,
    fill_item_hdr: Any,
    fill_sub: Any,
) -> int:
    for i_met, (label, key, fmt) in enumerate(_CRONOGRAMA_METRICS):
        is_hdr = i_met == 0
        f = fill_item_hdr if is_hdr else fill_sub
        _label(ws, row, 1, item.item_id if is_hdr else None, f, bold=is_hdr)
        _label(ws, row, 2, item.descricao if is_hdr else None, f, bold=is_hdr)
        _label(ws, row, 3, item.unidade if is_hdr else None, f, align="center")
        _label(ws, row, 4, item.quantitativo if is_hdr else None, f, align="right")
        _label(ws, row, 5, label, f, bold=False, color=_C["nav_dk"])
        for j_wk, wk in enumerate(all_weeks):
            wk_entry = wk_data.get(wk, {})
            val = _compute_cell_metric(key, wk_entry, accum_prop, wk, total_item, dias_semana)
            cell = ws.cell(row=row, column=ncols_fixed + 1 + j_wk, value=val)
            cell.fill = f
            cell.border = _border()
            cell.alignment = _align("right")
            if val is not None:
                cell.number_format = fmt
        row += 1
    return row


# ── Aba CRONOGRAMA ────────────────────────────────────────────────────────────


def render_cronograma(wb: Workbook, canonical: CanonicalModel) -> None:
    """CRONOGRAMA SEMANAL — matriz itens × semanas.

    Colunas: semanas ISO ordenadas cronologicamente.
        Por item EAP, 6 sub-linhas:
      1. Dias Trabalhados   2. Nº De Equipes
            3. Qtd. Planejada     4. Qtd Plan. Acumulada
            5. % Semanal          6. % Acumulado
    Cabeçalho da semana: DD/MMM (data da segunda-feira).
    """
    ws = wb.create_sheet("CRONOGRAMA.DET")

    acts = canonical.cronograma.scheduled_activities if canonical.cronograma else []
    act_lookup, item_totals, all_weeks = _build_act_lookup_and_totals(acts)
    n_weeks = len(all_weeks)

    if n_weeks == 0:
        ws.cell(row=1, column=1).value = "Sem dados de cronograma semanal."
        return

    dias_semana: int = canonical.projeto.regime_trabalho.dias_semana if canonical.projeto else 6

    NCOLS_FIXED = 5  # Item ID | Descrição | Un. | Quantitativo | Métrica
    NCOLS = NCOLS_FIXED + n_weeks
    _set_col_widths(ws, [10, 30, 6, 12, 22] + [13] * n_weeks)  # type: ignore[arg-type]

    row = 1
    _title_row(ws, row, "CRONOGRAMA SEMANAL — ACOMPANHAMENTO FÍSICO DE PRODUÇÃO", NCOLS)
    row += 1
    col_headers = ["Item ID", "Descrição", "Un.", "Quantitativo", "Métrica"] + [_wk_label(wk) for wk in all_weeks]
    _header_row(ws, row, col_headers)
    row += 1
    pratic_map = _get_pratic_map(canonical)
    _render_praticabilidade_row(ws, row, all_weeks, pratic_map)
    row += 1
    ws.freeze_panes = f"F{row}"

    FILL_ITEM_EVEN = _fill(_C["orange_lt"])
    FILL_ITEM_ODD = PatternFill(start_color="EAD9C3", end_color="EAD9C3", fill_type="solid")

    for i_item, item in enumerate(canonical.eap):
        wk_data = act_lookup.get(item.item_id, {})
        total_item = item_totals.get(item.item_id, 0.0)
        accum_prop, last_acum = _compute_accum_prop(wk_data, all_weeks)
        if total_item <= 0 and last_acum > 0:
            total_item = last_acum
        fill_item_hdr = FILL_ITEM_EVEN if i_item % 2 == 0 else FILL_ITEM_ODD
        fill_sub = _fill(_C["white"]) if i_item % 2 == 0 else _fill(_C["row_alt"])
        row = _render_item_metrics_rows(
            ws,
            row,
            item,
            wk_data,
            accum_prop,
            total_item,
            all_weeks,
            NCOLS_FIXED,
            dias_semana,
            fill_item_hdr,
            fill_sub,
        )


# ── Aba FLUXO DE CAIXA ────────────────────────────────────────────────────────


def _xl_cashflow_row_styling(rec: dict) -> tuple:
    """Return (fill_saldo, color_saldo, fill_sa, color_sa, fill_exp, color_exp)."""
    saldo = rec["saldo"]
    fill_saldo = _fill(_C["verde_lt"]) if saldo >= 0 else _fill(_C["verm_lt"])
    color_saldo = _C["verde"] if saldo >= 0 else _C["vermelho"]
    saldo_atual = rec["saldo_atual"]
    fill_sa = _fill(_C["verde_lt"]) if saldo_atual >= 0 else _fill(_C["verm_lt"])
    color_sa = _C["verde"] if saldo_atual >= 0 else _C["vermelho"]
    exp = rec["exposicao_acumulada"]
    fill_exp = _fill(_C["verm_lt"]) if exp > 0 else _fill(_C["verde_lt"])
    color_exp = _C["vermelho"] if exp > 0 else _C["verde"]
    return fill_saldo, color_saldo, fill_sa, color_sa, fill_exp, color_exp


def _xl_cashflow_metrics_block(ws: object, row: int, metricas: list, NCOLS: int) -> int:
    for label, valor in metricas:
        fill_m = _fill(_C["cinza_lt"])
        _label(ws, row, 1, label, fill_m, bold=True)
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=2)  # type: ignore[union-attr]
        cell_v = ws.cell(row=row, column=3, value=valor)  # type: ignore[union-attr]
        cell_v.border = _border()
        cell_v.alignment = _align("right")
        if isinstance(valor, float):
            cell_v.number_format = "R$ #,##0.00"
            is_bad = (label == "Exposição máxima" and valor > 0) or (label == "Saldo final do projeto" and valor < 0)
            cell_v.font = _font(bold=True, color=_C["vermelho"] if is_bad else _C["verde"])
            cell_v.fill = _fill(_C["verm_lt"] if is_bad else _C["verde_lt"])
        else:
            cell_v.font = _font(bold=True)
            cell_v.fill = fill_m
        ws.merge_cells(start_row=row, start_column=3, end_row=row, end_column=NCOLS)  # type: ignore[union-attr]
        row += 1
    return row


def _xl_cashflow_render_row(ws: object, row: int, rec: dict, i: int) -> None:
    fill_base = _fill(_C["white"]) if i % 2 == 0 else _fill(_C["row_alt"])
    fill_saldo, color_saldo, fill_sa, color_sa, fill_exp, color_exp = _xl_cashflow_row_styling(rec)
    _label(ws, row, 1, rec["mes_label"], fill_base, bold=False, align="center")
    _money(ws, row, 2, rec["despesa"], fill_base)
    _money(ws, row, 3, rec["receita"], fill_base)
    _money(ws, row, 4, rec["receita_acumulada"], fill_base)
    _money(ws, row, 5, rec["saldo"], fill_saldo, color=color_saldo)
    _money(ws, row, 6, rec["saldo_atual"], fill_sa, color=color_sa)
    _money(ws, row, 7, rec["exposicao_acumulada"], fill_exp, color=color_exp)


def render_fluxo_caixa(wb: Workbook, canonical: CanonicalModel) -> None:
    """FLUXO DE CAIXA — despesa, receita, saldo e exposição acumulada por mês."""
    ws = wb.create_sheet("ANALISE.FC_CAIXA")
    cf = _cash_flow(canonical)
    n_exec = len(_project_months(canonical))
    NCOLS = 7
    _set_col_widths(ws, [10, 18, 18, 18, 16, 16, 20])
    _freeze(ws, "A3")
    row = 1
    _title_row(ws, row, "FLUXO DE CAIXA — ACOMPANHAMENTO MENSAL", NCOLS)
    row += 1
    headers = [
        "Mês",
        "Despesa (R$)",
        "Receita (R$)",
        "Rec. Acumulada (R$)",
        "Saldo do Mês (R$)",
        "Saldo Atual (R$)",
        "Exposição Acum. (R$)",
    ]
    _header_row(ws, row, headers)
    row += 1
    ws.freeze_panes = f"A{row}"
    total_despesa = 0.0
    total_receita = 0.0
    max_exposicao = 0.0
    mes_max_exp = ""
    for i, rec in enumerate(cf):
        _xl_cashflow_render_row(ws, row, rec, i)
        total_despesa += rec["despesa"]
        total_receita += rec["receita"]
        if rec["exposicao_acumulada"] > max_exposicao:
            max_exposicao = rec["exposicao_acumulada"]
            mes_max_exp = rec["mes_label"]
        row += 1
    row += 1
    fill_tot = _fill(_C["nav_dk"])
    _label(ws, row, 1, "TOTAL", fill_tot, bold=True, color=_C["white"], align="center")
    _money(ws, row, 2, total_despesa, fill_tot, bold=True, color=_C["white"])
    _money(ws, row, 3, total_receita, fill_tot, bold=True, color=_C["white"])
    _money(ws, row, 4, total_receita, fill_tot, bold=True, color=_C["white"])
    saldo_final = total_receita - total_despesa
    _money(ws, row, 5, saldo_final, fill_tot, bold=True, color=_C["verde"] if saldo_final >= 0 else _C["orange"])
    _money(ws, row, 6, saldo_final, fill_tot, bold=True, color=_C["verde"] if saldo_final >= 0 else _C["orange"])
    ws.cell(row=row, column=7).fill = fill_tot
    ws.cell(row=row, column=7).border = _border()
    row += 3
    _section_row(ws, row, "MÉTRICAS DO FLUXO DE CAIXA", NCOLS)
    row += 1
    M_val = canonical.resultado.venda.total_com_bdi if canonical.resultado else 0.0
    metricas = [
        ("Duração da execução (meses)", n_exec),
        ("Parcela mensal (meses 2 a n)", math.floor(M_val / n_exec) if n_exec and canonical.resultado else "—"),
        (
            "Resíduo (mês n+1)",
            M_val - math.floor(M_val / n_exec) * (n_exec - 1) if n_exec and canonical.resultado else "—",
        ),
        ("Exposição máxima", max_exposicao),
        ("Mês da exposição máxima", mes_max_exp),
        ("Saldo final do projeto", saldo_final),
    ]
    row = _xl_cashflow_metrics_block(ws, row, metricas, NCOLS)
    row += 1
    nota = (
        "Mês 1: receita = 0.  Meses 2..n: ⌊M/n⌋ cada.  Mês n+1: resíduo M − ⌊M/n⌋×(n−1).  "
        "Saldo Atual = Rec. Acumulada − Desp. Acumulada.  "
        "Exposição Acum. = −Saldo Atual (positivo = empresa precisa de capital de giro)."
    )
    cell_nota = ws.cell(row=row, column=1, value=nota)
    cell_nota.font = _font(italic=True, size=9, color="555555")
    cell_nota.alignment = _align("left", wrap=True)
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=NCOLS)
    ws.row_dimensions[row].height = 36


# ── Aba RESULTADO ─────────────────────────────────────────────────────────────


def _xl_resultado_ref(sheet: str, col: int, ref_row: int | None, fallback: Any) -> Any:
    """Cross-sheet formula reference when ref_row is known."""
    if ref_row is not None:
        import re as _re

        sheet_ref = f"'{sheet}'" if not _re.fullmatch(r"[A-Za-z0-9_]+", sheet) else sheet
        return f"={sheet_ref}!${get_column_letter(col)}${ref_row}"
    return fallback


def _xl_resultado_indirect_cats(res: Any, indiretos_refs: dict | None, linha_fn: Any) -> None:
    """Write each indirect cost category row (for cat, attr in [...])."""
    for cat, attr in [
        ("ADM", "indireto_adm"),
        ("TOP", "indireto_top"),
        ("LAB", "indireto_lab"),
        ("QSMS", "indireto_qsms"),
        ("MOB", "indireto_mob"),
    ]:
        fallback = getattr(res.custo, attr, 0.0) if hasattr(res.custo, attr) else 0.0
        cat_row = (indiretos_refs or {}).get(cat)
        linha_fn(f"  {cat}", _xl_resultado_xl_resultado_ref("INDIRETOS.DET", 8, cat_row, fallback))


def _xl_resultado_custo_composicao(res: Any, planejamento_total_row: int | None, linha_fn: Any) -> float:
    """COMPOSIÇÃO DE CUSTO block — returns cd (direto base value)."""
    if not res:
        return 0.0
    cd = res.custo.direto_catalogo or res.custo.direto_equipes
    ci_total = res.custo.total - cd
    pvt = res.venda.total_com_bdi
    razao = ci_total / cd if cd > 0 else 0.0
    ci_pvt = ci_total / pvt if pvt > 0 else 0.0
    linha_fn(
        "Total Direto (catálogo s/BDI)",
        _xl_resultado_xl_resultado_ref("PLANEJAMENTO", 13, planejamento_total_row, res.venda.total_sem_bdi),
    )
    linha_fn("Total Direto (c/BDI)", res.venda.total_com_bdi)
    linha_fn("RAZÃO CI / CD (%)", round(razao * 100, 2), pct=True, is_money=False)
    linha_fn("CI / PVT (%)", round(ci_pvt * 100, 2), pct=True, is_money=False)
    return cd


def _xl_resultado_cap_giro_rows(n_exec: int, canonical: Any, linha_fn: Any) -> None:
    """Parcela and residuo rows for capital de giro — only when n_exec > 0."""
    if n_exec > 0 and canonical.resultado:
        M = canonical.resultado.venda.total_com_bdi
        linha_fn("Parcela mensal (meses 2 a n)", math.floor(M / n_exec))
        linha_fn("Resíduo (mês n+1)", M - math.floor(M / n_exec) * (n_exec - 1))


def _compute_resultado_alavancas(canonical: Any) -> tuple:
    """Compute alavancas metrics for RESULTADO sheet."""
    custo_equipes_total = sum(eq.custo_total for eq in canonical.equipes_diretas)
    custo_fixo_mensal_total = sum(eq.custo_fixo_mensal for eq in canonical.equipes_diretas)
    permanencia_media = (
        sum(eq.permanencia_meses for eq in canonical.equipes_diretas) / len(canonical.equipes_diretas)
        if canonical.equipes_diretas
        else 0.0
    )
    pico_equipes = max((eq.num_equipes_base for eq in canonical.equipes_diretas), default=0)
    pratic_media = 0.0
    if canonical.praticabilidade and canonical.praticabilidade.percentual_produtivo_semanal:
        vals = list(canonical.praticabilidade.percentual_produtivo_semanal.values())
        pratic_media = sum(vals) / len(vals) if vals else 0.0
    return custo_equipes_total, custo_fixo_mensal_total, permanencia_media, pico_equipes, pratic_media


def render_resultado_ml(
    wb: Workbook,
    canonical: CanonicalModel,
    diretos_total_row: int | None = None,
    indiretos_refs: dict[str, int] | None = None,
    planejamento_total_row: int | None = None,
) -> None:
    """RESULTADO — resumo financeiro consolidado.

    Quando diretos_total_row / indiretos_refs / planejamento_total_row são
    fornecidos, as células de custo e receita contém fórmulas de referência
    cruzada (=DIRETOS!$I$N etc.) em vez de valores estáticos, tornando a
    planilha autoajustável sem precisa ser regenerada após ajustes manuais
    nas abas de origem.
    """
    ws = wb.create_sheet("RESULTADO")

    _set_col_widths(ws, [38, 22, 10])
    _freeze(ws, "A3")

    row = 1
    _title_row(ws, row, "RESULTADO FINANCEIRO — MENDESLOBO CONSTRUTORA", 3)
    row += 2

    res = canonical.resultado
    if res is None:
        ws.cell(row=row, column=1, value="Resultado não disponível.")
        return

    proj = canonical.projeto
    cf = _cash_flow(canonical)
    max_exp = max((r["exposicao_acumulada"] for r in cf), default=0.0)

    STATUS_COLOR = {
        "VERDE": (_C["verde"], _C["verde_lt"]),
        "AMARELO": (_C["amarelo"], _C["amar_lt"]),
        "VERMELHO": (_C["vermelho"], _C["verm_lt"]),
    }
    s_color, s_bg = STATUS_COLOR.get(res.status_margem, (_C["preto"], _C["cinza_lt"]))

    def bloco(titulo: str) -> None:
        nonlocal row
        _section_row(ws, row, titulo, 3)
        row += 1

    def linha(
        label: str,
        valor: Any,
        destaque: bool = False,
        is_money: bool = True,
        pct: bool = False,
        color_override: str | None = None,
    ) -> None:
        nonlocal row
        fill = _fill(_C["white"]) if row % 2 == 0 else _fill(_C["row_alt"])
        _label(ws, row, 1, label, fill, bold=destaque)
        cell = ws.cell(row=row, column=2, value=valor)
        cell.fill = fill
        cell.border = _border()
        cell.font = _font(bold=destaque, color=color_override or _C["preto"])
        is_formula = isinstance(valor, str) and valor.startswith("=")
        if is_money and (isinstance(valor, (int, float)) or is_formula):
            cell.number_format = "R$ #,##0.00"
            cell.alignment = _align("right")
        elif pct and isinstance(valor, (int, float)):
            cell.number_format = '0.00"%"'
            cell.alignment = _align("right")
        else:
            cell.alignment = _align("left")
        ws.cell(row=row, column=3).fill = fill
        ws.cell(row=row, column=3).border = _border()
        row += 1

    def linha_alavanca(label: str, valor: Any, nota: str, *, is_money: bool = True, pct: bool = False) -> None:
        nonlocal row
        fill = _fill(_C["white"]) if row % 2 == 0 else _fill(_C["row_alt"])
        _label(ws, row, 1, label, fill, bold=False)
        cell = ws.cell(row=row, column=2, value=valor)
        cell.fill = fill
        cell.border = _border()
        cell.alignment = _align("right" if (is_money or pct or isinstance(valor, (int, float))) else "left")
        if is_money and (isinstance(valor, (int, float)) or (isinstance(valor, str) and valor.startswith("="))):
            cell.number_format = "R$ #,##0.00"
        elif pct and isinstance(valor, (int, float)):
            cell.number_format = '0.00"%"'
        _label(ws, row, 3, nota, fill, color=_C["nav_md"])
        row += 1

    # Identificação do projeto
    bloco("PROJETO")
    linha("Nome", proj.nome, is_money=False)
    linha("Tipo de obra", proj.tipo_obra, is_money=False)
    linha("Localização", proj.localizacao, is_money=False)
    linha("Período", f"{proj.data_inicio} -> {proj.data_termino}", is_money=False)
    linha(
        "Regime",
        f"{proj.regime_trabalho.dias_semana} dias/sem · {proj.regime_trabalho.horas_dia} h/dia",
        is_money=False,
    )
    row += 1

    # Receita
    bloco("RECEITA CONTRATUAL (COM BDI)")
    linha(
        "Preço de venda s/ BDI", _xl_resultado_ref("PLANEJAMENTO", 13, planejamento_total_row, res.venda.total_sem_bdi)
    )
    row_venda = row
    linha("Preço de venda c/ BDI", res.venda.total_com_bdi, destaque=True)
    row += 1

    # Custos — com referências cruzadas para DIRETOS e INDIRETOS
    bloco("CUSTOS")
    row_custo_direto = row
    linha(
        "Custo direto (catálogo s/BDI)",
        _xl_resultado_ref(
            "PLANEJAMENTO", 13, planejamento_total_row, res.custo.direto_catalogo or res.custo.direto_equipes
        ),
    )
    _xl_resultado_indirect_cats(res, indiretos_refs, linha)
    custo_ind = res.custo.total - (res.custo.direto_catalogo or res.custo.direto_equipes)
    row_custo_indireto = row
    linha(
        "Custo indireto (subtotal)",
        _xl_resultado_ref("INDIRETOS.DET", 8, (indiretos_refs or {}).get("total"), custo_ind),
    )
    row_custo_total = row
    linha("CUSTO TOTAL", f"=B{row_custo_direto}+B{row_custo_indireto}", destaque=True)
    row += 1

    # Resultado
    bloco("RESULTADO")
    row_resultado_bruto = row
    linha(
        "Resultado bruto (R$)",
        f"=B{row_venda}-B{row_custo_total}",
        destaque=True,
        color_override=_C["verde"] if res.resultado_financeiro >= 0 else _C["vermelho"],
    )
    linha(
        "Margem bruta (%)",
        f"=IF(B{row_venda}>0, B{row_resultado_bruto}/B{row_venda}, 0)",
        destaque=True,
        pct=True,
        color_override=s_color,
    )
    row += 1

    # Status em caixa colorido
    fill_status = _fill(s_bg)
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=3)
    cell_st = ws.cell(row=row, column=1, value=f"STATUS: {res.status_margem}")
    cell_st.fill = fill_status
    cell_st.font = _font(bold=True, color=s_color, size=14)
    cell_st.alignment = _align("center")
    cell_st.border = _border()
    row += 2

    # Composicao de custo
    bloco("COMPOSIÇÃO DE CUSTO")
    cd = _xl_resultado_custo_composicao(res, planejamento_total_row, linha)
    row += 1

    # Capital de giro
    bloco("CAPITAL DE GIRO")
    linha("Exposição máxima", max_exp, color_override=_C["vermelho"] if max_exp > 0 else _C["verde"])
    n_exec = len(_project_months(canonical))
    _xl_resultado_cap_giro_rows(n_exec, canonical, linha)
    linha("Duração da execução (meses)", n_exec, is_money=False)

    # Alavancas de reajuste para iteração manual
    bloco("ALAVANCAS DE REAJUSTE")
    custo_equipes_total, custo_fixo_mensal_total, permanencia_media, pico_equipes, pratic_media = (
        _compute_resultado_alavancas(canonical)
    )
    linha_alavanca("Preço de venda total", res.venda.total_com_bdi, "Depende de MO/EQ/MAT/DIESEL + BDI indireto")
    linha_alavanca("Base catálogo s/BDI", cd, "Knob de partida para precificação", is_money=True)
    linha_alavanca(
        "Markup efetivo",
        res.venda.bdi_lucro_impostos,
        "Resultado consolidado, não a fórmula de composição",
        pct=True,
        is_money=False,
    )
    linha_alavanca(
        "Custo direto de equipes", custo_equipes_total, "Sensível a permanência, produtividade e nº de frentes"
    )
    linha_alavanca("Custo fixo mensal de equipes", custo_fixo_mensal_total, "Multiplica diretamente pela permanência")
    linha_alavanca(
        "Permanência média (meses)", permanencia_media, "Reduzir prazo reduz custo fixo e mobilização", is_money=False
    )
    linha_alavanca("Pico de equipes", pico_equipes, "Se subir, pressiona custo fixo e mobilização", is_money=False)
    linha_alavanca(
        "Praticabilidade média", pratic_media, "Baixa praticabilidade aumenta permanência", pct=True, is_money=False
    )
    _auto_fit_columns(ws)


# ── Aba BDI ───────────────────────────────────────────────────────────────────


def render_bdi(wb: Workbook, canonical: CanonicalModel) -> None:
    """BDI — Decomposição TCU Ac.2622/2013 por categoria (MO, MAT, SERV, IND, DIESEL)."""
    from concilium.domain.models.bdi import DEFAULT_BDI_TABELA  # lazy import

    ws = wb.create_sheet("BDI")
    NCOLS = 13
    _set_col_widths(ws, [18, 8, 8, 8, 8, 10, 8, 8, 8, 8, 8, 12, 12])
    row = 1
    _title_row(ws, row, "BDI — BONIFICAÇÕES E DESPESAS INDIRETAS (FÓRMULA TCU AC.2622/2013)", NCOLS)
    row += 1
    _header_row(
        ws,
        row,
        [
            "Categoria",
            "AC (%)",
            "DF (%)",
            "R (%)",
            "CR (%)",
            "Lucro L (%)",
            "COFINS (%)",
            "ISS (%)",
            "PIS (%)",
            "CSSL (%)",
            "IR (%)",
            "T=Tributos (%)",
            "BDI Total (%)",
        ],
    )
    row += 1
    ws.freeze_panes = f"A{row}"
    tbl = DEFAULT_BDI_TABELA
    cats = [
        ("MÃO DE OBRA", tbl.mao_obra),
        ("MATERIAL", tbl.material),
        ("SERVIÇOS", tbl.servicos),
        ("INDIRETO", tbl.indireto),
        ("DIESEL", tbl.diesel),
    ]
    fill_colors = [_fill(_C["white"]), _fill(_C["row_alt"])]
    for i, (nome, comp) in enumerate(cats):
        fill = fill_colors[i % 2]
        bdi_pct = round(comp.bdi_total * 100, 2)
        trib_pct = round(comp.tributos * 100, 2)
        _label(ws, row, 1, nome, fill, bold=True, color=_C["nav_dk"])
        for j, v in enumerate(
            [
                comp.ac * 100,
                comp.df * 100,
                comp.r * 100,
                comp.cr * 100,
                comp.l * 100,
                comp.cofins * 100,
                comp.iss * 100,
                comp.pis * 100,
                comp.cssl * 100,
                comp.ir * 100,
                trib_pct,
                bdi_pct,
            ],
            2,
        ):
            cell = ws.cell(row=row, column=j, value=round(v, 4))
            cell.fill = fill
            cell.border = _border()
            cell.number_format = '0.00"%"'
            cell.alignment = _align("right")
            if j == 13:
                cell.font = _font(bold=True, color=_C["orange"])
        row += 1
    # Nota TCU
    row += 1
    _section_row(
        ws, row, "Fórmula: BDI = (1 + AC + DF + R + CR + L) / (1 - T) - 1  |  T = COFINS+ISS+PIS+CSSL+IR", NCOLS
    )
    row += 1


# ── Aba DIRETOS.RES ───────────────────────────────────────────────────────────


def _xl_dr_sem_vals(sem: object) -> tuple:
    return (
        sem.mao_obra if sem else 0.0,
        sem.equipamentos if sem else 0.0,
        sem.diesel if sem else 0.0,
        sem.material if sem else 0.0,
        sem.total if sem else 0.0,
    )


def _xl_dr_com_vals(com: object) -> tuple:
    return (
        com.mao_obra if com else 0.0,
        com.equipamentos if com else 0.0,
        com.diesel if com else 0.0,
        com.material if com else 0.0,
        com.total if com else 0.0,
    )


def _xl_dr_write_cell(ws: object, row: int, col: int, v: object, fill: object) -> None:
    cell = ws.cell(row=row, column=col, value=v)  # type: ignore[union-attr]
    cell.fill = fill
    cell.border = _border()
    if col >= 5 and isinstance(v, float):
        cell.number_format = "#,##0.00"
        cell.alignment = _align("right")
    elif col == 4:
        cell.number_format = "#,##0.##"
        cell.alignment = _align("right")
    else:
        cell.alignment = _align("left")


def _xl_dr_totals_row(ws: object, row: int, data_start: int, NCOLS: int, fill_tot: object) -> None:
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)  # type: ignore[union-attr]
    cell = ws.cell(row=row, column=1, value="TOTAL DIRETO")  # type: ignore[union-attr]
    cell.fill = fill_tot
    cell.font = _font(bold=True, color=_C["white"], size=11)
    cell.alignment = _align("right")
    cell.border = _border()
    for c in range(5, NCOLS + 1):
        col_letter = get_column_letter(c)
        _money(
            ws, row, c, f"=SUM({col_letter}{data_start}:{col_letter}{row - 1})", fill_tot, bold=True, color=_C["white"]
        )


def _xl_dr_write_data_row(
    ws: object, row: int, p: object, eap_item: object, sem: object, com: object, fill: object
) -> None:
    vals: list = [
        p.item_id,  # type: ignore[union-attr]
        eap_item.descricao if eap_item else p.item_id,  # type: ignore[union-attr]
        eap_item.unidade if eap_item else "un",  # type: ignore[union-attr]
        p.quantitativo,  # type: ignore[union-attr]
        *_xl_dr_sem_vals(sem),
        *_xl_dr_com_vals(com),
    ]
    for col, v in enumerate(vals, 1):
        _xl_dr_write_cell(ws, row, col, v, fill)


def render_diretos_res(wb: Workbook, canonical: CanonicalModel) -> int | None:
    """DIRETOS.RES — Custos diretos resumidos por EAP (MO/EQ/COMB/MAT s/BDI e c/BDI)."""
    ws = wb.create_sheet("DIRETOS.RES")
    eap_ordem = {e.item_id: e.ordem for e in canonical.eap}
    plan_sorted = sorted(canonical.planejamento, key=lambda p: eap_ordem.get(p.item_id, 9999))
    NCOLS = 14
    _set_col_widths(ws, [12, 42, 6, 13, 15, 15, 13, 13, 17, 15, 15, 13, 13, 17])
    _freeze(ws, "C3")
    row = 1
    _title_row(ws, row, "DIRETOS RESUMIDO — COMPONENTES MO/EQ/COMB/MAT s/BDI e c/BDI", NCOLS)
    row += 1
    _header_row(
        ws,
        row,
        [
            "Item ID",
            "Descrição",
            "Un.",
            "Quantitativo",
            "MO s/BDI",
            "EQ s/BDI",
            "Comb. s/BDI",
            "MAT s/BDI",
            "Total s/BDI",
            "MO c/BDI",
            "EQ c/BDI",
            "Comb. c/BDI",
            "MAT c/BDI",
            "Total c/BDI",
        ],
    )
    row += 1
    ws.freeze_panes = f"C{row}"
    data_start = row
    for i, p in enumerate(plan_sorted):
        eap_item = next((e for e in canonical.eap if e.item_id == p.item_id), None)
        sem = p.subtotal.sem_bdi if p.subtotal else None
        com = p.subtotal.com_bdi if p.subtotal else None
        fill = _fill(_C["white"]) if i % 2 == 0 else _fill(_C["row_alt"])
        _xl_dr_write_data_row(ws, row, p, eap_item, sem, com, fill)
        row += 1
    row += 1
    total_row = row
    _xl_dr_totals_row(ws, row, data_start, NCOLS, _fill(_C["nav_dk"]))
    wb.defined_names["DIRETOS_RES_SEM_BDI"] = DefinedName(
        "DIRETOS_RES_SEM_BDI", attr_text=f"'DIRETOS.RES'!${get_column_letter(9)}${total_row}"
    )
    wb.defined_names["DIRETOS_RES_COM_BDI"] = DefinedName(
        "DIRETOS_RES_COM_BDI", attr_text=f"'DIRETOS.RES'!${get_column_letter(14)}${total_row}"
    )
    return total_row


# ── Aba INDIRETOS.RES ─────────────────────────────────────────────────────────


def render_indiretos_res(wb: Workbook, canonical: CanonicalModel) -> None:
    """INDIRETOS.RES — Custos indiretos resumidos por categoria + KPIs de composição."""
    ws = wb.create_sheet("INDIRETOS.RES")
    NCOLS = 6
    _set_col_widths(ws, [14, 36, 18, 10, 18, 14])
    _freeze(ws, "A3")
    row = 1
    _title_row(ws, row, "INDIRETOS RESUMIDO — CATEGORIAS + INDICADORES", NCOLS)
    row += 1
    _header_row(ws, row, ["Categoria", "Descrição", "Custo s/BDI (R$)", "BDI (%)", "Custo c/BDI (R$)", "% do Total"])
    row += 1
    ws.freeze_panes = f"A{row}"
    ORDEM_CAT = ["ADM", "TOP", "LAB", "QSMS", "MOB"]
    inds_by_cat = {ind.categoria: ind for ind in canonical.indiretos}
    bdi_by_cat = {ibd.categoria: ibd for ibd in canonical.indiretos_com_bdi}
    total_sem = sum(ind.custo_total for ind in canonical.indiretos) or 1.0
    fill_colors = [_fill(_C["white"]), _fill(_C["row_alt"])]
    subtotal_rows_sem: list[int] = []
    subtotal_rows_com: list[int] = []
    for i, cat in enumerate(ORDEM_CAT):
        ind = inds_by_cat.get(cat)  # type: ignore[call-overload]
        if not ind:
            continue
        ibd = bdi_by_cat.get(cat)  # type: ignore[call-overload]
        fill = fill_colors[i % 2]
        custo_sem = ind.custo_total
        bdi_val = ibd.bdi_aplicado if ibd else 0.0
        custo_com = ibd.custo_com_bdi if ibd else custo_sem
        pct = custo_sem / total_sem * 100
        _label(ws, row, 1, cat, fill, bold=True, color=_C["nav_dk"])
        _label(ws, row, 2, ind.descricao, fill)
        _money(ws, row, 3, custo_sem, fill)
        cell = ws.cell(row=row, column=4, value=round(bdi_val * 100, 2))
        cell.fill = fill
        cell.border = _border()
        cell.number_format = '0.00"%"'
        cell.alignment = _align("right")
        _money(ws, row, 5, custo_com, fill)
        cell = ws.cell(row=row, column=6, value=round(pct, 2))
        cell.fill = fill
        cell.border = _border()
        cell.number_format = '0.00"%"'
        cell.alignment = _align("right")
        subtotal_rows_sem.append(row)
        subtotal_rows_com.append(row)
        row += 1
    row += 1
    fill_tot = _fill(_C["nav_dk"])
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=2)
    cell = ws.cell(row=row, column=1, value="TOTAL INDIRETO")
    cell.fill = fill_tot
    cell.font = _font(bold=True, color=_C["white"], size=11)
    cell.alignment = _align("right")
    cell.border = _border()
    f_sem = ("=" + "+".join(f"C{r}" for r in subtotal_rows_sem)) if subtotal_rows_sem else "0"
    f_com = ("=" + "+".join(f"E{r}" for r in subtotal_rows_com)) if subtotal_rows_com else "0"
    _money(ws, row, 3, f_sem, fill_tot, bold=True, color=_C["white"])
    ws.cell(row=row, column=4).fill = fill_tot
    ws.cell(row=row, column=4).border = _border()
    _money(ws, row, 5, f_com, fill_tot, bold=True, color=_C["white"])
    ws.cell(row=row, column=6).fill = fill_tot
    ws.cell(row=row, column=6).border = _border()
    row += 3
    _section_row(ws, row, "INDICADORES DE COMPOSIÇÃO DE CUSTO", NCOLS)
    row += 1
    res = canonical.resultado
    if res:
        cd = res.custo.direto_catalogo or res.custo.direto_equipes
        ci = res.custo.total - cd
        pvt = res.venda.total_com_bdi
        kpis = [
            ("TOTAL DIRETO (catálogo s/BDI)", cd, False),
            ("TOTAL INDIRETO s/BDI", ci, False),
            ("RAZÃO CI / CD", ci / cd * 100 if cd > 0 else 0.0, True),
            ("PREÇO DE VENDA TOTAL", pvt, False),
            ("CI / PVT", ci / pvt * 100 if pvt > 0 else 0.0, True),
        ]
        for label, val, is_pct in kpis:
            fm = _fill(_C["cinza_lt"])
            _label(ws, row, 1, label, fm, bold=True)
            ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=2)
            if is_pct:
                cell = ws.cell(row=row, column=3, value=round(val, 2))
                cell.fill = fm
                cell.border = _border()
                cell.number_format = '0.00"%"'
                cell.alignment = _align("right")
            else:
                _money(ws, row, 3, val, fm, bold=True)
            ws.merge_cells(start_row=row, start_column=3, end_row=row, end_column=NCOLS)
            row += 1


# ── Aba CRONOGRAMA.RES ────────────────────────────────────────────────────────


def render_cronograma_res(wb: Workbook, canonical: CanonicalModel) -> None:
    """CRONOGRAMA.RES — Resumo mensal de produção física por item EAP."""
    ws = wb.create_sheet("CRONOGRAMA.RES")
    project_months = _project_months(canonical)
    if not project_months:
        ws.cell(row=1, column=1).value = "Sem dados de cronograma."
        return
    qty_by_item: dict[str, dict[tuple, float]] = {}
    if canonical.cronograma:
        for act in canonical.cronograma.scheduled_activities:
            if act.activity_id not in qty_by_item:
                qty_by_item[act.activity_id] = {ym: 0.0 for ym in project_months}
            for wk, dist in act.distribuicao_semanal.items():
                ym = _week_to_month(wk)
                if ym in qty_by_item[act.activity_id]:
                    qty_by_item[act.activity_id][ym] += getattr(dist, "qtd_executada", 0.0)
    NCOLS = 4 + len(project_months)
    _set_col_widths(ws, [10, 30, 6, 12] + [12] * len(project_months))  # type: ignore[arg-type]
    _freeze(ws, "E3")
    row = 1
    _title_row(ws, row, "CRONOGRAMA RESUMIDO — PRODUÇÃO MENSAL POR EAP", NCOLS)
    row += 1
    _header_row(ws, row, ["Item ID", "Descrição", "Un.", "Total Qtd"] + [_fmt_mes(ym) for ym in project_months])
    row += 1
    ws.freeze_panes = f"E{row}"
    fill_colors = [_fill(_C["white"]), _fill(_C["row_alt"])]
    for i, item in enumerate(canonical.eap):
        fill = fill_colors[i % 2]
        monthly = qty_by_item.get(item.item_id, {ym: 0.0 for ym in project_months})
        _label(ws, row, 1, item.item_id, fill)
        _label(ws, row, 2, item.descricao, fill, wrap=True)
        _label(ws, row, 3, item.unidade, fill, align="center")
        cell = ws.cell(row=row, column=4, value=item.quantitativo)
        cell.fill = fill
        cell.border = _border()
        cell.number_format = "#,##0.##"
        cell.alignment = _align("right")
        for j, ym in enumerate(project_months):
            v = monthly.get(ym, 0.0)
            cell = ws.cell(row=row, column=5 + j, value=round(v, 2) if v else None)
            cell.fill = fill
            cell.border = _border()
            if v:
                cell.number_format = "#,##0.##"
                cell.alignment = _align("right")
        row += 1


# ── Aba EQUIPE ────────────────────────────────────────────────────────────────


def render_equipe(wb: Workbook, canonical: CanonicalModel) -> None:
    """EQUIPE — Composição detalhada de funções e equipamentos por equipe direta."""
    ws = wb.create_sheet("EQUIPE")
    NCOLS = 9
    _set_col_widths(ws, [12, 16, 28, 8, 6, 18, 10, 8, 18])
    _freeze(ws, "A3")
    row = 1
    _title_row(ws, row, "EQUIPE — COMPOSIÇÃO DE RECURSOS DIRETOS POR ATIVIDADE", NCOLS)
    row += 1
    _header_row(
        ws,
        row,
        [
            "Item ID",
            "CPU ID",
            "Nome / Tipo",
            "Papel",
            "Qtd",
            "Custo Mensal (R$)",
            "Perm. (m)",
            "Nº Eq.",
            "Custo Total (R$)",
        ],
    )
    row += 1
    ws.freeze_panes = f"A{row}"
    _PAPEL_COLOR = {"direto": _C["verde"], "indireto": _C["nav_md"], "gestao": _C["orange"]}
    equipe_total_rows = []
    for i_eq, eq in enumerate(canonical.equipes_diretas):
        eap_item = next((e for e in canonical.eap if e.item_id == eq.item_id), None)
        item_label = f"{eq.item_id} — {eap_item.descricao if eap_item else eq.item_id}"
        _section_row(ws, row, item_label, NCOLS)
        row += 1
        fill = _fill(_C["white"]) if i_eq % 2 == 0 else _fill(_C["row_alt"])
        for func in eq.funcoes:
            papel = getattr(func, "papel", "direto") or "direto"
            cm = func.custo_mensal_unitario * func.num_pessoas
            _label(ws, row, 1, eq.item_id, fill)
            _label(ws, row, 2, eq.cpu_id, fill)
            _label(ws, row, 3, func.descricao or func.funcao_id, fill)
            _label(
                ws, row, 4, papel.upper(), fill, bold=True, color=_PAPEL_COLOR.get(papel, _C["preto"]), align="center"
            )
            _label(ws, row, 5, func.num_pessoas, fill, align="right")
            _money(ws, row, 6, cm, fill)
            _label(ws, row, 7, round(eq.permanencia_meses, 2), fill, align="right")
            _label(ws, row, 8, eq.num_equipes_base, fill, align="right")
            _money(ws, row, 9, cm * eq.permanencia_meses * eq.num_equipes_base, fill)
            row += 1
        for equip in eq.equipamentos:
            cm_eq = getattr(equip, "custo_mensal", 0.0) or 0.0
            _label(ws, row, 1, eq.item_id, fill)
            _label(ws, row, 2, equip.equip_id, fill)
            _label(ws, row, 3, (getattr(equip, "descricao", equip.equip_id) or equip.equip_id) + " [EQ]", fill)
            _label(ws, row, 4, "EQ", fill, align="center", color=_C["nav_dk"])
            _label(ws, row, 5, equip.num_unidades, fill, align="right")
            _money(ws, row, 6, cm_eq, fill)
            _label(ws, row, 7, round(eq.permanencia_meses, 2), fill, align="right")
            _label(ws, row, 8, eq.num_equipes_base, fill, align="right")
            _money(ws, row, 9, cm_eq * eq.permanencia_meses * eq.num_equipes_base, fill)
            row += 1
            comb = getattr(equip, "custo_combustivel_mensal", 0.0) or 0.0
            if comb > 0:
                _label(ws, row, 1, eq.item_id, fill)
                _label(ws, row, 2, equip.equip_id, fill)
                _label(ws, row, 3, f"Diesel — {getattr(equip, 'descricao', equip.equip_id)}", fill, color=_C["orange"])
                _label(ws, row, 4, "COMB", fill, align="center", color=_C["orange"])
                _label(ws, row, 5, equip.num_unidades, fill, align="right")
                _money(ws, row, 6, comb, fill)
                _label(ws, row, 7, round(eq.permanencia_meses, 2), fill, align="right")
                _label(ws, row, 8, eq.num_equipes_base, fill, align="right")
                _money(ws, row, 9, comb * eq.permanencia_meses * eq.num_equipes_base, fill)
                row += 1
        fill_sub = _fill(_C["orange_lt"])
        _label(ws, row, 1, f"Subtotal {eq.item_id}", fill_sub, bold=True)
        for c in range(2, NCOLS):
            ws.cell(row=row, column=c).fill = fill_sub
            ws.cell(row=row, column=c).border = _border()
        _money(ws, row, NCOLS, eq.custo_total, fill_sub, bold=True, color=_C["orange"])
        equipe_total_rows.append(row)
        row += 1
    row += 1
    fill_tot = _fill(_C["nav_dk"])
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=NCOLS - 1)
    cell = ws.cell(row=row, column=1, value="TOTAL EQUIPES DIRETAS")
    cell.fill = fill_tot
    cell.font = _font(bold=True, color=_C["white"], size=11)
    cell.alignment = _align("right")
    cell.border = _border()
    f_tot = ("=" + "+".join(f"I{r}" for r in equipe_total_rows)) if equipe_total_rows else "0"
    _money(ws, row, NCOLS, f_tot, fill_tot, bold=True, color=_C["white"])


# ── Aba EQUILIBRIO ────────────────────────────────────────────────────────────


def render_equilibrio(wb: Workbook, canonical: CanonicalModel) -> None:
    """EQUILIBRIO — Ponto de equilíbrio por EAP e balanço estrutural."""
    ws = wb.create_sheet("EQUILIBRIO")
    NCOLS = 6
    _set_col_widths(ws, [12, 42, 18, 18, 16, 12])
    _freeze(ws, "A3")
    row = 1
    _title_row(ws, row, "PONTO DE EQUILÍBRIO — CUSTO FIXO vs PREÇO DE VENDA (CPU)", NCOLS)
    row += 1
    _header_row(
        ws, row, ["Item ID", "CPU ID", "Custo Fixo Equipe (R$)", "Preço Venda CPU (R$)", "Delta (R$)", "Status"]
    )
    row += 1
    ws.freeze_panes = f"A{row}"
    _ST_CLR = {"OK": _C["verde"], "AVISO": _C["amarelo"], "ERRO": _C["vermelho"], "INFO": _C["nav_dk"]}
    _ST_BG = {"OK": _C["verde_lt"], "AVISO": _C["amar_lt"], "ERRO": _C["verm_lt"], "INFO": _C["row_alt"]}
    fill_colors = [_fill(_C["white"]), _fill(_C["row_alt"])]
    for i, pe in enumerate(canonical.ponto_equilibrio):
        st = pe.status_validacao
        fill = _fill(_ST_BG.get(st, _C["white"])) if st in ("ERRO", "AVISO") else fill_colors[i % 2]
        eap_item = next((e for e in canonical.eap if e.item_id == pe.item_id), None)
        _label(ws, row, 1, pe.item_id, fill)
        _label(ws, row, 2, eap_item.cpu_id if eap_item else pe.item_id, fill)
        _money(ws, row, 3, pe.custo_fixo_equipe, fill)
        _money(ws, row, 4, pe.custo_venda_cpu, fill)
        _money(ws, row, 5, pe.delta, fill, bold=True, color=_ST_CLR.get(st, _C["preto"]))
        _label(ws, row, 6, st, fill, bold=True, color=_ST_CLR.get(st, _C["preto"]), align="center")
        row += 1
    bpe = canonical.resultado.balanco_ponto_equilibrio if canonical.resultado else None
    if bpe:
        row += 2
        _section_row(ws, row, "BALANÇO DE PONTO DE EQUILÍBRIO", NCOLS)
        row += 1
        metricas = [
            ("HC Operacional (direto)", bpe.total_hc_operacional, False),
            ("HC Indireto", bpe.total_hc_indireto, False),
            ("HC Total", bpe.total_hc, False),
            ("Custo Fixo Mensal", bpe.custo_fixo_mensal, True),
            ("Custo Fixo Total", bpe.custo_fixo_total, True),
            ("Nº Equipes Diretas", bpe.numero_equipes_diretas, False),
        ]
        for label, val, is_money_val in metricas:
            fm = _fill(_C["cinza_lt"])
            _label(ws, row, 1, label, fm, bold=True)
            ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=2)
            if is_money_val:
                _money(ws, row, 3, val, fm, bold=True)
            else:
                cell = ws.cell(row=row, column=3, value=val)
                cell.fill = fm
                cell.border = _border()
                cell.font = _font(bold=True)
                cell.alignment = _align("right")
            ws.merge_cells(start_row=row, start_column=3, end_row=row, end_column=NCOLS)
            row += 1


# ── Aba HIST.EQUIPAMENTOS ─────────────────────────────────────────────────────


def _compute_equip_min_units(eq: object) -> int:
    """Normalize by minimum equipment unit count to recover composite-front count."""
    if not eq.equipamentos:  # type: ignore[union-attr]
        return 1
    return min(
        (e.num_unidades for e in eq.equipamentos if (e.num_unidades or 0) > 0),  # type: ignore[union-attr]
        default=1,
    )


def _aggregate_equip_demand(act: object, eq: object, all_weeks: list, equip_data: dict) -> None:
    """Accumulate equipment demand from one scheduled activity into equip_data."""
    _min_units = _compute_equip_min_units(eq)
    for equip in eq.equipamentos:  # type: ignore[union-attr]
        if equip.equip_id not in equip_data:
            equip_data[equip.equip_id] = {
                "descricao": getattr(equip, "descricao", equip.equip_id) or equip.equip_id,
                "per_week": {wk: 0 for wk in all_weeks},
            }
        for wk, dist in act.distribuicao_semanal.items():  # type: ignore[union-attr]
            n = getattr(dist, "num_equipes", 0)
            if n > 0 and wk in equip_data[equip.equip_id]["per_week"]:
                equip_data[equip.equip_id]["per_week"][wk] += round((n / _min_units) * equip.num_unidades)


def _write_hist_data_row(
    ws: object, row: int, id_key: str, data: dict, unit_label: str, all_weeks: list, fill: object, week_totals: dict
) -> None:
    _label(ws, row, 1, id_key, fill)
    _label(ws, row, 2, data["descricao"], fill)
    _label(ws, row, 3, unit_label, fill, align="center")
    for j, wk in enumerate(all_weeks):
        v = data["per_week"].get(wk, 0)
        cell = ws.cell(row=row, column=4 + j, value=v if v > 0 else None)  # type: ignore[union-attr]
        cell.fill = fill
        cell.border = _border()
        if v > 0:
            cell.alignment = _align("right")
            cell.number_format = "0"
        week_totals[wk] += v


def _write_hist_totals_row(ws: object, row: int, all_weeks: list, fill_tot: object, week_totals: dict) -> None:
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=3)  # type: ignore[union-attr]
    cell = ws.cell(row=row, column=1, value="TOTAL SEMANAL")  # type: ignore[union-attr]
    cell.fill = fill_tot
    cell.font = _font(bold=True, color=_C["white"])
    cell.alignment = _align("right")
    cell.border = _border()
    for j, wk in enumerate(all_weeks):
        v = week_totals[wk]
        cell = ws.cell(row=row, column=4 + j, value=v if v > 0 else None)  # type: ignore[union-attr]
        cell.fill = fill_tot
        cell.border = _border()
        if v > 0:
            cell.font = _font(bold=True, color=_C["white"])
            cell.alignment = _align("right")
            cell.number_format = "0"


def render_histograma_eq(wb: Workbook, canonical: CanonicalModel) -> None:
    """HIST.EQUIPAMENTOS — Demanda semanal de equipamentos (un. × semana ISO)."""
    ws = wb.create_sheet("HIST.EQUIPAMENTOS")
    acts = canonical.cronograma.scheduled_activities if canonical.cronograma else []
    all_weeks = sorted({w for act in acts for w in act.distribuicao_semanal})
    if not all_weeks:
        ws.cell(row=1, column=1).value = "Sem dados de cronograma."
        return
    equipe_by_item = {eq.item_id: eq for eq in canonical.equipes_diretas}
    equip_data: dict[str, dict] = {}
    for act in acts:
        eq = equipe_by_item.get(act.activity_id)
        if eq is None:
            continue
        _aggregate_equip_demand(act, eq, all_weeks, equip_data)
    NCOLS = 3 + len(all_weeks)
    _set_col_widths(ws, [14, 32, 6] + [10] * len(all_weeks))  # type: ignore[arg-type]
    _freeze(ws, "D3")
    row = 1
    _title_row(ws, row, "HISTOGRAMA DE EQUIPAMENTOS — DEMANDA SEMANAL (UN.)", NCOLS)
    row += 1
    _header_row(ws, row, ["Equip. ID", "Descrição", "Un."] + list(map(_wk_label, all_weeks)))
    row += 1
    ws.freeze_panes = f"D{row}"
    fill_colors = [_fill(_C["white"]), _fill(_C["row_alt"])]
    week_totals = dict.fromkeys(all_weeks, 0)
    for i, (eid, data) in enumerate(sorted(equip_data.items())):
        fill = fill_colors[i % 2]
        _write_hist_data_row(ws, row, eid, data, "un", all_weeks, fill, week_totals)
        row += 1
    row += 1
    _write_hist_totals_row(ws, row, all_weeks, _fill(_C["nav_dk"]), week_totals)


def _aggregate_labor_demand(act: object, eq: object, all_weeks: list, func_data: dict) -> None:
    """Accumulate labor demand from one scheduled activity into func_data."""
    _min_units = _compute_equip_min_units(eq)
    for func in eq.funcoes:  # type: ignore[union-attr]
        if func.funcao_id not in func_data:
            func_data[func.funcao_id] = {
                "descricao": func.descricao or func.funcao_id,
                "per_week": {wk: 0 for wk in all_weeks},
            }
        for wk, dist in act.distribuicao_semanal.items():  # type: ignore[union-attr]
            n = getattr(dist, "num_equipes", 0)
            if n > 0 and wk in func_data[func.funcao_id]["per_week"]:
                func_data[func.funcao_id]["per_week"][wk] += round((n / _min_units) * func.num_pessoas)


def render_histograma_mo(wb: Workbook, canonical: CanonicalModel) -> None:
    """HIST.MAO_OBRA — Demanda semanal de mão de obra (pessoas × semana ISO)."""
    ws = wb.create_sheet("HIST.MAO_OBRA")
    acts = canonical.cronograma.scheduled_activities if canonical.cronograma else []
    all_weeks = sorted({w for act in acts for w in act.distribuicao_semanal})
    if not all_weeks:
        ws.cell(row=1, column=1).value = "Sem dados de cronograma."
        return
    equipe_by_item = {eq.item_id: eq for eq in canonical.equipes_diretas}
    func_data: dict[str, dict] = {}
    for act in acts:
        eq = equipe_by_item.get(act.activity_id)
        if eq is None:
            continue
        _aggregate_labor_demand(act, eq, all_weeks, func_data)
    NCOLS = 3 + len(all_weeks)
    _set_col_widths(ws, [20, 32, 6] + [10] * len(all_weeks))  # type: ignore[arg-type]
    _freeze(ws, "D3")
    row = 1
    _title_row(ws, row, "HISTOGRAMA DE MÃO DE OBRA — DEMANDA SEMANAL (PESSOAS)", NCOLS)
    row += 1
    _header_row(ws, row, ["Função ID", "Descrição", "Un."] + list(map(_wk_label, all_weeks)))
    row += 1
    ws.freeze_panes = f"D{row}"
    fill_colors = [_fill(_C["white"]), _fill(_C["row_alt"])]
    week_totals = dict.fromkeys(all_weeks, 0)
    for i, (fid, data) in enumerate(sorted(func_data.items())):
        fill = fill_colors[i % 2]
        _write_hist_data_row(ws, row, fid, data, "pax", all_weeks, fill, week_totals)
        row += 1
    row += 1
    _write_hist_totals_row(ws, row, all_weeks, _fill(_C["nav_dk"]), week_totals)


def render_graficos(wb: Workbook, canonical: CanonicalModel) -> None:
    """GRAFICOS — painéis resumidos para histograma, Gantt e fluxo mensal."""
    ws = wb.create_sheet("GRAFICOS")
    _set_col_widths(ws, [18, 14, 18, 14, 18, 14, 18, 14, 18, 14, 18, 14])

    def _week_label(week_key: str) -> str:
        year_str, week_str = week_key.split("-W")
        monday = date.fromisocalendar(int(year_str), int(week_str), 1)
        return f"{monday.day:02d}/{MESES_PT[monday.month]}"

    def _histogram_totals(kind: str) -> tuple[list[str], list[float]]:
        acts = canonical.cronograma.scheduled_activities if canonical.cronograma else []
        all_weeks = sorted({week for act in acts for week in act.distribuicao_semanal})
        if not all_weeks:
            return [], []
        lookup = {eq.item_id: eq for eq in canonical.equipes_diretas}
        totals = {week: 0.0 for week in all_weeks}
        for act in acts:
            eq = lookup.get(act.activity_id)
            if eq is None:
                continue
            min_units = (
                min((e.num_unidades for e in eq.equipamentos if (e.num_unidades or 0) > 0), default=1)
                if eq.equipamentos
                else 1
            )
            scale = (
                sum(float(e.num_unidades or 0.0) for e in eq.equipamentos)
                if kind == "equipamentos"
                else sum(float(f.num_pessoas or 0.0) for f in eq.funcoes)
            )
            for week, dist in act.distribuicao_semanal.items():
                n_eq = float(getattr(dist, "num_equipes", 0) or 0.0)
                if n_eq > 0:
                    totals[week] += (n_eq / min_units) * scale
        return [_week_label(week) for week in all_weeks], [round(totals[week], 2) for week in all_weeks]

    def _gantt_rows() -> list[tuple[str, int, int]]:
        rows: list[tuple[str, int, int]] = []
        acts = canonical.cronograma.scheduled_activities if canonical.cronograma else []
        for act in acts:
            weeks = sorted(act.distribuicao_semanal.keys())
            if not weeks:
                continue
            year_str, week_str = weeks[0].split("-W")
            date.fromisocalendar(int(year_str), int(week_str), 1)
            rows.append((_week_label(weeks[0]), 0, len(weeks) * 7))
        return rows

    def _cash_flow_rows() -> list[dict[str, Any]]:
        rows = _cash_flow(canonical)
        result: list[dict[str, Any]] = []
        for row in rows:
            result.append(
                {
                    "mes": row["mes_label"],
                    "receita": float(row["receita"]),
                    "despesa": float(row["despesa"]),
                    "saldo": float(row["saldo"]),
                    "exposicao": float(row["exposicao_acumulada"]),
                }
            )
        return result

    def _write_two_col_block(start_col: int, title: str, labels: list[str], values: list[float]) -> int:
        get_column_letter(start_col)
        get_column_letter(start_col + 1)
        ws.cell(row=1, column=start_col, value=title)
        ws.cell(row=2, column=start_col, value="Categoria")
        ws.cell(row=2, column=start_col + 1, value="Valor")
        for idx, (label, value) in enumerate(zip(labels, values, strict=False), start=3):
            ws.cell(row=idx, column=start_col, value=label)
            cell = ws.cell(row=idx, column=start_col + 1, value=value)
            cell.number_format = "#,##0.00"
        return len(labels) + 2

    eq_labels, eq_values = _histogram_totals("equipamentos")
    mo_labels, mo_values = _histogram_totals("mao_obra")
    finance_rows = _cash_flow_rows()
    _gantt_rows()

    _write_two_col_block(1, "Histograma de Equipamentos", eq_labels, eq_values)
    _write_two_col_block(4, "Histograma de Mao de Obra", mo_labels, mo_values)

    gantt_col = 7
    ws.cell(row=1, column=gantt_col, value="Cronograma (Gantt)")
    ws.cell(row=2, column=gantt_col, value="Tarefa")
    ws.cell(row=2, column=gantt_col + 1, value="Inicio")
    ws.cell(row=2, column=gantt_col + 2, value="Duracao (dias)")
    acts = canonical.cronograma.scheduled_activities if canonical.cronograma else []
    gantt_map: list[tuple[str, int, int]] = []
    start_dates: list[date] = []
    for act in acts:
        weeks = sorted(act.distribuicao_semanal.keys())
        if not weeks:
            continue
        year_str, week_str = weeks[0].split("-W")
        start_dates.append(date.fromisocalendar(int(year_str), int(week_str), 1))
    gantt_origin = min(start_dates) if start_dates else None
    for act in acts:
        weeks = sorted(act.distribuicao_semanal.keys())
        if not weeks:
            continue
        year_str, week_str = weeks[0].split("-W")
        start = date.fromisocalendar(int(year_str), int(week_str), 1)
        start_offset = (start - gantt_origin).days if gantt_origin else 0
        gantt_map.append((act.activity_id, start_offset, len(weeks) * 7))
    for idx, (task, start_offset, duration_days) in enumerate(gantt_map, start=3):
        ws.cell(row=idx, column=gantt_col, value=task)
        ws.cell(row=idx, column=gantt_col + 1, value=start_offset)
        ws.cell(row=idx, column=gantt_col + 2, value=duration_days)

    finance_col = 1
    finance_row = 20
    ws.cell(row=finance_row, column=finance_col, value="Fluxo mensal")
    headers = ["Mes", "Receita", "Despesa", "Saldo", "Exposicao"]
    for offset, header in enumerate(headers):
        ws.cell(row=finance_row + 1, column=finance_col + offset, value=header)
    for idx, row in enumerate(finance_rows, start=finance_row + 2):
        ws.cell(row=idx, column=finance_col, value=row["mes"])
        for offset, key in enumerate(("receita", "despesa", "saldo", "exposicao"), start=1):
            cell = ws.cell(row=idx, column=finance_col + offset, value=row[key])
            cell.number_format = "#,##0.00"

    if eq_labels:
        chart = BarChart()
        chart.type = "col"
        chart.style = 10
        chart.title = "Histograma de Equipamentos"
        chart.y_axis.title = "Unidades"
        data = Reference(ws, min_col=2, min_row=2, max_row=1 + len(eq_labels) + 1)
        cats = Reference(ws, min_col=1, min_row=3, max_row=2 + len(eq_labels))
        chart.add_data(data, titles_from_data=True)
        chart.set_categories(cats)
        ws.add_chart(chart, "J2")

    if mo_labels:
        chart = BarChart()
        chart.type = "col"
        chart.style = 10
        chart.title = "Histograma de Mao de Obra"
        chart.y_axis.title = "Pessoas"
        data = Reference(ws, min_col=5, min_row=2, max_row=1 + len(mo_labels) + 1)
        cats = Reference(ws, min_col=4, min_row=3, max_row=2 + len(mo_labels))
        chart.add_data(data, titles_from_data=True)
        chart.set_categories(cats)
        ws.add_chart(chart, "J18")

    if gantt_map:
        chart = BarChart()
        chart.type = "bar"
        chart.style = 10
        chart.grouping = "stacked"
        chart.overlap = 100
        chart.title = "Cronograma Gantt"
        chart.x_axis.title = "Dias"
        chart.y_axis.title = "Atividades"
        data = Reference(ws, min_col=gantt_col + 1, min_row=2, max_col=gantt_col + 2, max_row=2 + len(gantt_map))
        cats = Reference(ws, min_col=gantt_col, min_row=3, max_row=2 + len(gantt_map))
        chart.add_data(data, titles_from_data=True)
        chart.set_categories(cats)
        if chart.series:
            chart.series[0].graphicalProperties.noFill = True
            chart.series[0].graphicalProperties.line.noFill = True
        ws.add_chart(chart, "J34")

    if finance_rows:
        finance_row + 1
        finance_end = finance_row + 1 + len(finance_rows)
        finance_metrics = [
            (2, "Receita Mensal"),
            (3, "Despesa Mensal"),
            (4, "Saldo Mensal"),
            (5, "Exposicao Acumulada"),
        ]
        chart_positions = ["A36", "J36", "A52", "J52"]
        for (col_idx, title), anchor in zip(finance_metrics, chart_positions, strict=False):
            chart = BarChart()
            chart.type = "col"
            chart.style = 10
            chart.title = title
            chart.y_axis.title = "R$"
            data = Reference(ws, min_col=col_idx, min_row=finance_row + 1, max_row=finance_end)
            cats = Reference(ws, min_col=finance_col, min_row=finance_row + 2, max_row=finance_end)
            chart.add_data(data, titles_from_data=True)
            chart.set_categories(cats)
            ws.add_chart(chart, anchor)


# ── Helpers de coerção (retrocompatibilidade com excel_styles) ────────────────


def coerce_to_cell_value(value: Any) -> Any:
    """Converte valor Python para tipo compatível com célula Excel."""
    if value is None:
        return None
    if isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, dict)):
        if isinstance(value, dict) and len(value) == 1:
            return list(value.values())[0]
        if isinstance(value, list) and len(value) == 1:
            return coerce_to_cell_value(value[0])
        s = str(value)
        if len(s) > 100:
            s = s[:97] + "..."
        return s
    return str(value)


def _xl_memorial_encargos(ws: Any, row: int, memorial: Any, fills: list, NCOLS: int) -> int:
    """Section 1: social charges A-F; returns updated row."""
    _section_row(ws, row, "1. ENCARGOS SOCIAIS - Grupos A-F + Judicial (vigencia abril/2026)", NCOLS)
    row += 1
    _header_row(ws, row, ["Regime", "Grp A", "Grp B", "Grp C", "Grp D", "Grp E", "Grp F", "Judicial", "TOTAL"])
    row += 1
    enc_pairs = [
        ("Horista CLT", getattr(memorial, "encargos_horista", None) if memorial else None),
        ("Mensalista CLT", getattr(memorial, "encargos_mensalista", None) if memorial else None),
    ]
    for i, (lbl, enc) in enumerate(enc_pairs):
        fill = fills[i % 2]
        ws.cell(row=row, column=1, value=lbl).fill = fill
        vals = (
            [enc.grupo_a, enc.grupo_b, enc.grupo_c, enc.grupo_d, enc.grupo_e, enc.grupo_f, enc.judicial, enc.total]
            if enc
            else [0.0] * 8
        )
        for j, v in enumerate(vals, 2):
            cell = ws.cell(row=row, column=j, value=round(v * 100, 2))
            cell.fill = fill
            cell.border = _border()
            cell.number_format = '0.00"%"'
            cell.alignment = _align("right")
            if j == 9:
                cell.font = _font(bold=True, color=_C["orange"])
        row += 1
    ws.cell(
        row=row, column=1, value="Nota: encargos aplicados ANTES do BDI. Custo MO = Salario x (1 + Encargos)"
    ).font = _font(italic=True, size=9)
    return row + 2


def _xl_memorial_bdi_cats(ws: Any, row: int, bdi_rows: list, memorial: Any, fills: list, NCOLS: int) -> int:
    """Section 2: BDI by category (TCU formula); returns updated row (before blank)."""
    _section_row(ws, row, "2. BDI POR CATEGORIA - Formulacao TCU Ac.2622/2013: BDI=(1+OH)/(1-T)-1", NCOLS)
    row += 1
    _header_row(
        ws,
        row,
        [
            "Categoria",
            "AC(%)",
            "DF(%)",
            "R(%)",
            "CR(%)",
            "L(%)",
            "OH(%)",
            "COFINS",
            "ISS",
            "PIS",
            "CSSL",
            "IR",
            "T(%)",
            "BDI(%)",
        ],
    )
    row += 1
    for i, (nome, cat, comp) in enumerate(bdi_rows):
        fill = fills[i % 2]
        mem_cat = memorial.bdi_por_categoria.get(cat) if memorial else None
        fonte_tag = f" [{mem_cat.fonte_bdi}]" if mem_cat else ""
        _label(ws, row, 1, nome + fonte_tag, fill, bold=True, color=_C["nav_dk"])
        for j, v in enumerate(
            [
                comp.ac * 100,
                comp.df * 100,
                comp.r * 100,
                comp.cr * 100,
                comp.l * 100,
                comp.overhead * 100,
                comp.cofins * 100,
                comp.iss * 100,
                comp.pis * 100,
                comp.cssl * 100,
                comp.ir * 100,
                comp.tributos * 100,
                comp.bdi_total * 100,
            ],
            2,
        ):
            cell = ws.cell(row=row, column=j, value=round(v, 4))
            cell.fill = fill
            cell.border = _border()
            cell.number_format = '0.0000"%"'
            cell.alignment = _align("right")
            if j in (7, 14):
                cell.font = _font(bold=True, color=_C["orange"])
        row += 1
    return row


def _xl_memorial_decomp(ws: Any, row: int, bdi_rows: list, fills: list, NCOLS: int) -> int:
    """Section 3: price decomposition per category; returns updated row (before blank)."""
    _section_row(ws, row, "3. DECOMPOSICAO NO PRECO DE VENDA - De cada R$1,00 cobrado", NCOLS)
    row += 1
    _header_row(
        ws,
        row,
        [
            "Categoria",
            "Custo Dir.",
            "OH-AC",
            "OH-DF",
            "OH-R",
            "OH-CR",
            "Margem L",
            "COFINS",
            "ISS",
            "PIS",
            "CSSL",
            "IR",
            "T Total",
            "SOMA",
        ],
    )
    row += 1
    for i, (nome, _cat, comp) in enumerate(bdi_rows):
        fill = fills[i % 2]
        d = comp.decomposicao_no_preco()
        soma = round(sum(d.values()), 4)
        t_total = d["tributo_cofins"] + d["tributo_iss"] + d["tributo_pis"] + d["tributo_cssl"] + d["tributo_ir"]
        _label(ws, row, 1, nome, fill, bold=True, color=_C["nav_dk"])
        for j, v in enumerate(
            [
                d["custo_direto"],
                d["overhead_ac"],
                d["overhead_df"],
                d["overhead_r"],
                d["overhead_cr"],
                d["margem_l"],
                d["tributo_cofins"],
                d["tributo_iss"],
                d["tributo_pis"],
                d["tributo_cssl"],
                d["tributo_ir"],
                t_total,
                soma,
            ],
            2,
        ):
            cell = ws.cell(row=row, column=j, value=round(v * 100, 2))
            cell.fill = fill
            cell.border = _border()
            cell.number_format = '0.00"%"'
            cell.alignment = _align("right")
            if j == 7:
                cell.font = _font(bold=True, color=_C["verde"])
            if j == 14:
                ok_color = _C["verde"] if abs(soma - 1.0) < 0.001 else _C["vermelho"]
                cell.font = _font(bold=True, color=ok_color)
        row += 1
    return row


def _xl_memorial_aplicacao(ws: Any, row: int, memorial: Any, fills: list, NCOLS: int) -> None:
    """Section 4: BDI application per EAP item."""
    _section_row(ws, row, "4. APLICACAO POR ITEM DA EAP - BDI efetivo x preco unitario", NCOLS)
    row += 1
    _header_row(
        ws,
        row,
        [
            "Item",
            "Descricao",
            "CPU",
            "Un.",
            "Qtd.",
            "PU s/BDI",
            "BDI(%)",
            "PU c/BDI",
            "Sub. s/BDI",
            "Sub. c/BDI",
            "MO (R$)",
            "EQ (R$)",
            "MAT (R$)",
            "DIESEL (R$)",
        ],
    )
    row += 1
    aplicacao = getattr(memorial, "aplicacao_por_item", None) or []
    for i, item in enumerate(aplicacao):
        fill = fills[i % 2]
        vals = [
            item.item_id,
            item.descricao,
            item.cpu_id,
            item.unidade,
            item.quantitativo,
            item.preco_unit_sem_bdi,
            round(item.bdi_aplicado * 100, 2),
            item.preco_unit_com_bdi,
            item.subtotal_sem_bdi,
            item.subtotal_com_bdi,
            item.custo_mao_obra,
            item.custo_equipamentos,
            item.custo_material,
            item.custo_diesel,
        ]
        for j, v in enumerate(vals, 1):
            cell = ws.cell(row=row, column=j, value=v)
            cell.fill = fill
            cell.border = _border()
            if j >= 5:
                cell.alignment = _align("right")
            if j in (6, 8, 9, 10, 11, 12, 13, 14):
                cell.number_format = "R$ #,##0.00"
            if j == 7:
                cell.number_format = '0.00"%"'
        row += 1


def render_memorial_bdi(wb, canonical) -> None:
    """MEMORIAL.BDI - Memorial de calculo BDI auditavel ponta a ponta (ADR-057).

    4 secoes: (1) Encargos A-F, (2) BDI por categoria,
    (3) Decomposicao no preco de venda, (4) Aplicacao por item EAP.
    """
    from concilium.domain.models.bdi import DEFAULT_BDI_TABELA
    from concilium.domain.services.memorial_bdi_builder import MemorialBDIBuilder

    memorial = getattr(canonical, "memorial_calculo_bdi", None)
    if memorial is None:
        try:
            memorial = MemorialBDIBuilder().build(
                canonical_in=canonical, bdi_fonte="DEFAULT_BDI_TABELA", regime_version="pre_reforma"
            )
        except Exception:
            pass

    ws = wb.create_sheet("MEMORIAL.BDI")
    NCOLS = 14
    _set_col_widths(ws, [22, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 18])
    tbl = DEFAULT_BDI_TABELA
    fills = [_fill(_C["white"]), _fill(_C["row_alt"])]
    row = 1

    _title_row(ws, row, "MEMORIAL DE CALCULO BDI - AUDITORIA PONTA A PONTA (ADR-057)", NCOLS)
    row += 1
    if memorial:
        meta = memorial.meta
        ws.cell(
            row=row,
            column=1,
            value=f"Projeto: {meta.projeto_id} | Gerado: {meta.gerado_em[:19]} | "
            f"Regime: {meta.regime_tributario} | Vigencia: {meta.vigencia_bdi}",
        ).font = _font(italic=True, size=9)
        row += 2

    # Secao 1: Encargos
    row = _xl_memorial_encargos(ws, row, memorial, fills, NCOLS)

    # Secao 2: BDI por categoria
    bdi_rows = [
        ("MAO DE OBRA", "mao_obra", tbl.mao_obra),
        ("MATERIAL", "material", tbl.material),
        ("SERVICOS", "servicos", tbl.servicos),
        ("INDIRETO", "indireto", tbl.indireto),
        ("DIESEL", "diesel", tbl.diesel),
    ]
    row = _xl_memorial_bdi_cats(ws, row, bdi_rows, memorial, fills, NCOLS)
    row += 1

    # Secao 3: Decomposicao no preco de venda
    row = _xl_memorial_decomp(ws, row, bdi_rows, fills, NCOLS)
    row += 1

    # Secao 4: Aplicacao por item
    _xl_memorial_aplicacao(ws, row, memorial, fills, NCOLS)
    ws.freeze_panes = "B4"


# ── ADR-058: Aba CURVA.ABC ────────────────────────────────────────────────────


def render_curva_abc(wb, canonical) -> None:
    """CURVA.ABC — ABC por insumo (funcao_id / equip_id) do projeto (ADR-058)."""
    from concilium.domain.services.curva_abc_builder import CurvaABCBuilder

    abc = getattr(canonical, "curva_abc_insumo", None)
    if abc is None:
        try:
            abc = CurvaABCBuilder().build(canonical)
        except Exception:
            return

    ws = wb.create_sheet("CURVA.ABC")
    NCOLS = 8
    _set_col_widths(ws, [22, 14, 12, 14, 14, 14, 8, 30])
    row = 1
    _title_row(ws, row, "CURVA ABC POR INSUMO — ANALISE DE PARETO (80/20) — ADR-058", NCOLS)
    row += 1
    ws.cell(
        row=row,
        column=1,
        value=f"Total custo direto: R$ {abc.total_custo_direto:,.2f}  |  "
        f"Classe A: {abc.n_itens_a} itens ({abc.pct_a * 100:.1f}%)  |  "
        f"B: {abc.n_itens_b}  |  C: {abc.n_itens_c}",
    ).font = _font(italic=True, size=9)
    row += 2

    _header_row(
        ws,
        row,
        ["Insumo ID", "Descricao", "Categoria", "Custo Total (R$)", "% Custo", "% Acumulado", "Classe", "Atividades"],
    )
    row += 1
    ws.freeze_panes = f"A{row}"

    fills = [_fill(_C["white"]), _fill(_C["row_alt"])]
    classe_colors = {"A": _C["vermelho"], "B": _C["amarelo"], "C": _C["verde"]}
    for i, item in enumerate(abc.itens):
        fill = fills[i % 2]
        for j, v in enumerate(
            [
                item.insumo_id,
                item.descricao,
                item.categoria,
                item.custo_total,
                item.pct_custo * 100,
                item.pct_custo_acumulado * 100,
                item.classe,
                ", ".join(item.atividades[:5]),
            ],
            1,
        ):
            cell = ws.cell(row=row, column=j, value=v)
            cell.fill = fill
            cell.border = _border()
            if j == 4:
                cell.number_format = "R$ #,##0.00"
            if j in (5, 6):
                cell.number_format = '0.00"%"'
                cell.alignment = _align("right")
            if j == 7:
                cell.font = _font(bold=True, color=classe_colors.get(str(v), _C["preto"]))
                cell.alignment = _align("center")
        row += 1


# ── ADR-058: Aba S-CURVE ──────────────────────────────────────────────────────


def render_s_curve(wb, canonical) -> None:
    """S-CURVE — Curva S de custo acumulado semana a semana (ADR-058)."""
    from concilium.domain.services.s_curve_builder import SCurveBuilder

    sc = getattr(canonical, "s_curve", None)
    if sc is None:
        try:
            sc = SCurveBuilder().build(canonical)
        except Exception:
            return
    if not sc.semanas_iso:
        return

    ws = wb.create_sheet("S-CURVE")
    NCOLS = 8
    _set_col_widths(ws, [14, 14, 14, 14, 14, 14, 14, 18])
    row = 1
    _title_row(ws, row, "CURVA S — DESEMBOLSO ACUMULADO PLANEJADO (ADR-058)", NCOLS)
    row += 1
    ws.cell(
        row=row,
        column=1,
        value=f"Total projeto: R$ {sc.total_projeto:,.2f}  |  "
        f"Direto: R$ {sc.total_custo_direto:,.2f}  |  "
        f"Indireto: R$ {sc.total_custo_indireto:,.2f}",
    ).font = _font(italic=True, size=9)
    row += 2
    _header_row(
        ws,
        row,
        [
            "Semana ISO",
            "Equip. Unicos",
            "Equipes Total",
            "Custo Semana (R$)",
            "Custo Acum. (R$)",
            "% Acumulado",
            "C. Direto",
            "C. Indireto",
        ],
    )
    row += 1
    ws.freeze_panes = f"A{row}"

    fills = [_fill(_C["white"]), _fill(_C["row_alt"])]
    for i, (semana, c_sem, c_acum, pct, agr) in enumerate(
        zip(sc.semanas_iso, sc.custo_semanal, sc.custo_acumulado, sc.pct_acumulado, sc.agregacao_semanal, strict=False)
    ):
        fill = fills[i % 2]
        for j, v in enumerate(
            [
                semana,
                agr.n_equipamentos_unicos,
                agr.n_equipes_totais,
                c_sem,
                c_acum,
                pct * 100,
                agr.custo_direto_semana,
                agr.custo_indireto_semana,
            ],
            1,
        ):
            cell = ws.cell(row=row, column=j, value=v)
            cell.fill = fill
            cell.border = _border()
            if j in (4, 5, 7, 8):
                cell.number_format = "R$ #,##0.00"
            if j == 6:
                cell.number_format = '0.00"%"'
                cell.alignment = _align("right")
        row += 1


# ── ADR-059: Aba CAMPANHA.FROTA ───────────────────────────────────────────────


def render_campanha_frota(wb, canonical) -> None:
    """CAMPANHA.FROTA — Plano de campanhas de permanência de equipamentos (ADR-059)."""
    from concilium.domain.services.campanha_equipamento_builder import CampanhaEquipamentoBuilder

    analise = getattr(canonical, "analise_campanhas", None)
    if analise is None:
        try:
            analise = CampanhaEquipamentoBuilder().build(canonical)
        except Exception:
            return

    ws = wb.create_sheet("CAMPANHA.FROTA")
    NCOLS = 12
    _set_col_widths(ws, [22, 14, 10, 10, 10, 10, 14, 14, 14, 14, 14, 30])
    row = 1
    _title_row(ws, row, "CAMPANHAS DE PERMANENCIA DE EQUIPAMENTOS (ADR-059)", NCOLS)
    row += 1
    ws.cell(
        row=row,
        column=1,
        value=f"Campanhas: {analise.n_campanhas}  |  "
        f"Economia vs. dismissal: R$ {analise.economia_total:,.2f}  |  "
        f"Standby total: R$ {analise.custo_standby_total:,.2f}  |  "
        f"Economia liquida: R$ {analise.economia_liquida:,.2f}",
    ).font = _font(italic=True, size=9)
    row += 2
    _header_row(
        ws,
        row,
        [
            "Instancia",
            "Tipo Equip.",
            "Sem. Entrada",
            "Sem. Saida",
            "Sem. Ativas",
            "Sem. Standby",
            "Mob (R$)",
            "Demob (R$)",
            "Standby Total",
            "Custo Camp.",
            "Economia",
            "Atividades",
        ],
    )
    row += 1
    ws.freeze_panes = f"A{row}"

    fills = [_fill(_C["white"]), _fill(_C["row_alt"])]
    for i, camp in enumerate(analise.campanhas):
        fill = fills[i % 2]
        economia_color = _C["verde"] if camp.economia_vs_dismissal > 0 else _C["preto"]
        for j, v in enumerate(
            [
                camp.instancia_id,
                camp.tipo_id,
                camp.semana_entrada,
                camp.semana_saida,
                camp.semanas_ativas,
                camp.semanas_standby,
                camp.custo_mob,
                camp.custo_demob,
                camp.custo_standby_total,
                camp.custo_campanha,
                camp.economia_vs_dismissal,
                " | ".join(camp.atividades),
            ],
            1,
        ):
            cell = ws.cell(row=row, column=j, value=v)
            cell.fill = fill
            cell.border = _border()
            if j in (7, 8, 9, 10):
                cell.number_format = "R$ #,##0.00"
            if j == 11:
                cell.number_format = "R$ #,##0.00"
                cell.font = _font(bold=True, color=economia_color)
        row += 1

    if analise.alertas_custo_duplicado:
        row += 1
        _section_row(ws, row, "ALERTAS VAL-CAMP-01 — Dismissals potencialmente mais caros que standby", NCOLS)
        row += 1
        for alert in analise.alertas_custo_duplicado:
            ws.cell(row=row, column=1, value=alert).font = _font(color=_C["amarelo"], size=9)
            row += 1


def render_cubo_comp(wb, canonical) -> None:
    """CUBO.COMP — Composicao do preco de venda ao longo do tempo (ADR-058 ext.).

    Exibe a decomposicao do preco de venda semanal em 4 grupos:
        Custo Direto | Overhead (AC+DF+R+CR) | Margem L | Tributos (ISS+COFINS+PIS+CSSL+IR)

    Permite identificar semanas de alta exposicao tributaria e pico de margem.
    """
    from concilium.domain.services.cubo_analitico_builder import CuboAnaliticoBuilder

    cubo = getattr(canonical, "cubo_analitico", None)
    if cubo is None:
        try:
            cubo = CuboAnaliticoBuilder().build(canonical)
        except Exception:
            return
    if not cubo.celulas:
        return

    ws = wb.create_sheet("CUBO.COMP")
    NCOLS = 12
    _set_col_widths(ws, [14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 12])
    row = 1

    _title_row(ws, row, "COMPOSICAO DO PRECO DE VENDA — CUBO 4D (CATEGORIA x ATIVIDADE x TEMPO x BDI)", NCOLS)
    row += 1
    ws.cell(
        row=row,
        column=1,
        value=f"Regime BDI: {cubo.regime_bdi}  |  Total PV: R$ {cubo.total_preco_venda:,.2f}  |  "
        f"Custo Direto: {cubo.total_custo_direto / cubo.total_preco_venda * 100:.1f}%  |  "
        f"Margem: {cubo.pct_margem * 100:.1f}%  |  Tributos: {cubo.pct_tributos * 100:.1f}%",
    ).font = _font(italic=True, size=9)
    row += 2

    # Secao 1: Sumario por componente
    _section_row(ws, row, "1. SUMARIO POR COMPONENTE BDI (total do projeto)", NCOLS)
    row += 1
    _header_row(ws, row, ["Componente", "R$ Total", "% PV"])
    row += 1
    grupos = [
        ("Custo Direto", cubo.total_custo_direto),
        ("Overhead Total", cubo.total_overhead),
        ("Margem L", cubo.total_margem),
        ("Tributos Total", cubo.total_tributos),
    ]
    fills = [_fill(_C["white"]), _fill(_C["row_alt"])]
    for i, (nome, val) in enumerate(grupos):
        fill = fills[i % 2]
        pct = val / cubo.total_preco_venda * 100 if cubo.total_preco_venda > 0 else 0
        _label(ws, row, 1, nome, fill, bold=True, color=_C["nav_dk"])
        cell_val = ws.cell(row=row, column=2, value=val)
        cell_val.fill = fill
        cell_val.border = _border()
        cell_val.number_format = "R$ #,##0.00"
        cell_pct = ws.cell(row=row, column=3, value=round(pct, 2))
        cell_pct.fill = fill
        cell_pct.border = _border()
        cell_pct.number_format = '0.00"%"'
        row += 1
    row += 1

    # Secao 2: Exposicao tributaria por tipo
    _section_row(ws, row, "2. EXPOSICAO TRIBUTARIA POR TIPO (projeto inteiro)", NCOLS)
    row += 1
    _header_row(ws, row, ["Tributo", "R$ Total", "% PV"])
    row += 1
    trib_map = cubo.exposicao_tributaria_por_tipo()
    for i, (trib, val) in enumerate(sorted(trib_map.items(), key=lambda kv: kv[1], reverse=True)):
        fill = fills[i % 2]
        pct = val / cubo.total_preco_venda * 100 if cubo.total_preco_venda > 0 else 0
        _label(ws, row, 1, trib.replace("tributo_", "").upper(), fill, color=_C["vermelho"])
        ws.cell(row=row, column=2, value=val).fill = fill
        ws.cell(row=row, column=2).border = _border()
        ws.cell(row=row, column=2).number_format = "R$ #,##0.00"
        cell_p = ws.cell(row=row, column=3, value=round(pct, 2))
        cell_p.fill = fill
        cell_p.border = _border()
        cell_p.number_format = '0.00"%"'
        row += 1
    row += 1

    # Secao 3: Margem por atividade
    _section_row(ws, row, "3. MARGEM (L) POR ATIVIDADE", NCOLS)
    row += 1
    _header_row(ws, row, ["Atividade", "Margem (R$)", "% Margem Total"])
    row += 1
    margem_ativ = cubo.margem_por_atividade()
    total_margem = cubo.total_margem or 1.0
    for i, (ativ, val) in enumerate(margem_ativ.items()):
        fill = fills[i % 2]
        pct = val / total_margem * 100
        _label(ws, row, 1, ativ, fill, color=_C["verde"])
        ws.cell(row=row, column=2, value=val).fill = fill
        ws.cell(row=row, column=2).border = _border()
        ws.cell(row=row, column=2).number_format = "R$ #,##0.00"
        cell_p = ws.cell(row=row, column=3, value=round(pct, 2))
        cell_p.fill = fill
        cell_p.border = _border()
        cell_p.number_format = '0.00"%"'
        row += 1
    row += 1

    # Secao 4: Composicao temporal (custo+overhead+margem+tributos por semana)
    _section_row(ws, row, "4. COMPOSICAO DO PRECO POR SEMANA (custo | overhead | margem | tributos)", NCOLS)
    row += 1
    _header_row(
        ws,
        row,
        [
            "Semana ISO",
            "Custo Direto",
            "Overhead",
            "Margem L",
            "Tributos",
            "Total Semana",
            "% Acumulado",
            "% Semana/Total",
        ],
    )
    row += 1
    ws.freeze_panes = f"A{row}"

    comp_temp = cubo.composicao_preco_temporal()
    total_pv = cubo.total_preco_venda or 1.0
    acum = 0.0
    for i, (semana, comps) in enumerate(comp_temp.items()):
        fill = fills[i % 2]
        c_dir = comps.get("custo_direto", 0.0)
        c_oh = sum(comps.get(k, 0.0) for k in ("overhead_ac", "overhead_df", "overhead_r", "overhead_cr"))
        c_marg = comps.get("margem_l", 0.0)
        c_trib = sum(
            comps.get(k, 0.0) for k in ("tributo_cofins", "tributo_iss", "tributo_pis", "tributo_cssl", "tributo_ir")
        )
        total_sem = c_dir + c_oh + c_marg + c_trib
        acum += total_sem
        pct_sem = total_sem / total_pv * 100
        pct_acum = acum / total_pv * 100
        for j, v in enumerate([semana, c_dir, c_oh, c_marg, c_trib, total_sem, pct_acum, pct_sem], 1):
            cell = ws.cell(row=row, column=j, value=round(v, 2) if isinstance(v, float) else v)
            cell.fill = fill
            cell.border = _border()
            if j in (2, 3, 4, 5, 6):
                cell.number_format = "R$ #,##0.00"
            if j in (7, 8):
                cell.number_format = '0.00"%"'
                cell.alignment = _align("right")
            if j == 4:
                cell.font = _font(color=_C["verde"])
            if j == 5:
                cell.font = _font(color=_C["vermelho"])
        row += 1


class ExcelRenderer:
    """Renderiza dados canônicos em planilha Excel MendesLobo (15 abas)."""

    def __init__(self, canonical: CanonicalModel):
        self.canonical = canonical
        self.wb = Workbook()
        self.wb.remove(self.wb.active)

    def render(self) -> Workbook:
        """Renderiza as 15 abas na ordem definida e retorna workbook."""
        render_memorial_bdi(self.wb, self.canonical)
        render_curva_abc(self.wb, self.canonical)
        render_s_curve(self.wb, self.canonical)
        render_campanha_frota(self.wb, self.canonical)
        render_cubo_comp(self.wb, self.canonical)
        diretos_total_row = render_diretos(self.wb, self.canonical)
        render_diretos_res(self.wb, self.canonical)
        indiretos_refs = render_indiretos_ml(self.wb, self.canonical)
        render_indiretos_res(self.wb, self.canonical)
        planejamento_total_row = render_planejamento_ml(self.wb, self.canonical)
        render_cronograma(self.wb, self.canonical)
        render_cronograma_res(self.wb, self.canonical)
        render_equipe(self.wb, self.canonical)
        render_equilibrio(self.wb, self.canonical)
        render_resultado_ml(
            self.wb,
            self.canonical,
            diretos_total_row=diretos_total_row,
            indiretos_refs=indiretos_refs,
            planejamento_total_row=planejamento_total_row,
        )
        render_fluxo_caixa(self.wb, self.canonical)
        render_histograma_eq(self.wb, self.canonical)
        render_histograma_mo(self.wb, self.canonical)
        # CURVA.ABC já renderizada na posição 2 (acima) — removido condicional duplicado (P1)
        render_graficos(self.wb, self.canonical)
        return self.wb

    def save(self, output_path: Path) -> None:
        """Salva workbook em arquivo .xlsx."""
        wb = self.render()
        wb.save(output_path)

    def to_bytes(self) -> bytes:
        """Retorna conteúdo workbook como bytes (para persistência)."""
        wb = self.render()
        buffer = BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        return buffer.getvalue()

    def _coerce_to_cell_value(self, value: Any) -> Any:
        """Converte valor para tipo compatível com célula Excel."""
        return coerce_to_cell_value(value)
