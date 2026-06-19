from __future__ import annotations

from datetime import date
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.workbook.defined_name import DefinedName

from concilium.domain.models.canonical import CanonicalModel

from ..cash_flow import _monthly_indirect_costs
from ..helpers import _find_eap_item, _fmt_mes, _project_months
from ..styles import (
    _C,
    MESES_PT,
    _align,
    _auto_fit_columns,
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
        eap_item = _find_eap_item(canonical.eap, eq.item_id)
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
    mo_c = f"=E{row}*(1+'MEMORIAL.BDI'!$M$3)"
    eq_c = f"=G{row}*(1+'MEMORIAL.BDI'!$M$5)"
    dsl_c = f"=I{row}*(1+'MEMORIAL.BDI'!$M$7)"
    mat_c = f"=K{row}*(1+'MEMORIAL.BDI'!$M$4)"
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
    eap_ordem: dict[str, int] = {e.item_id: (e.ordem if e.ordem is not None else 9999) for e in canonical.eap}
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
