"""Excel adapter — aba OPERACIONAL — render_indiretos_ml (custos indiretos mensais)."""

from __future__ import annotations

from typing import Any

from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from openpyxl.workbook.defined_name import DefinedName

from concilium.domain.models.canonical import CanonicalModel

from ...cash_flow import _monthly_indirect_costs
from ...helpers import _fmt_mes, _project_months
from ...styles import (
    _C,
    _align,
    _border,
    _fill,
    _font,
    _freeze,
    _header_row,
    _label,
    _money,
    _section_row,
    _set_col_widths,
    _title_row,
)


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


def _xl_indirect_funcoes_rows(ws: Any, row: int, ind: Any, cat: str, perm: float, fill_base: Any) -> int:
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


def _xl_indirect_verbas_mensais_rows(ws: Any, row: int, ind: Any, cat: str, perm: float, fill_base: Any) -> int:
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


def _xl_indirect_verbas_fixas_rows(ws: Any, row: int, ind: Any, cat: str, perm: float, fill_base: Any) -> int:
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
    ws: Any, row: int, start_row: int, cat: str, cat_desc: str, cat_total: float, perm: float, fill_base: Any
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


