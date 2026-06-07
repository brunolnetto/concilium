"""Modelo Excel Vivo — formula-driven, PARÂMETROS como única fonte de verdade.

Sheets:
  PARÂMETROS   — todos os dados brutos editáveis (regime, BDI, EAP+P+neq, indiretos,
                  praticabilidade semanal, alocação semanal)
  RECURSOS     — taxas de mão de obra e equipamentos + matriz de composição por item
  CUSTOS DIR.  — custo mensal das equipes via fórmulas (SUMPRODUCT sobre RECURSOS)
  ORÇAMENTO    — preços unitários e subtotais via fórmulas (BDI sobre PARÂMETROS)
  CRONOGRAMA   — produção semanal, % acumulado, curva S, validação de fechamento
  INDIRETOS    — custo total indireto via fórmulas
  CONSOLIDAÇÃO — preço de venda e margem via fórmulas cross-sheet
  FLUXO DE CX  — receitas e despesas mensais via fórmulas
  REFERÊNCIA   — valores de benchmark e deltas vs CONSOLIDAÇÃO
"""

from __future__ import annotations

from functools import cache
from io import BytesIO
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# ── Paleta ─────────────────────────────────────────────────────────────────────
_C = {
    "hdr": "1F4E79",  # azul escuro — cabeçalhos de seção
    "label": "D6E4F0",  # azul claro  — rótulos
    "inp": "FFF2CC",  # amarelo     — células editáveis
    "form": "E2EFDA",  # verde claro — fórmulas
    "tot": "D9D9D9",  # cinza       — totais
    "ref": "F4CCCC",  # rosa        — referência
    "ok": "D9EAD3",  # verde       — delta OK
    "warn": "FCE8D5",  # laranja     — delta fora
    "white": "FFFFFF",
    "dark": "000000",
}


@cache
def _fill(hex_c: str) -> PatternFill:
    return PatternFill("solid", fgColor=hex_c)


@cache
def _fnt(bold=False, size=10, color="000000") -> Font:
    return Font(bold=bold, size=size, color=color)


@cache
def _brd() -> Border:
    s = Side(style="thin", color="AAAAAA")
    return Border(left=s, right=s, top=s, bottom=s)


@cache
def _aln(h="left", v="center", wrap=False) -> Alignment:
    return Alignment(horizontal=h, vertical=v, wrap_text=wrap)


def _col(n: int) -> str:
    return get_column_letter(n)


def _hdr(ws, row, col, txt, span=1):
    c = ws.cell(row=row, column=col, value=txt)
    c.font = _fnt(bold=True, size=10, color="FFFFFF")
    c.fill = _fill(_C["hdr"])
    c.alignment = _aln("center")
    c.border = _brd()
    if span > 1:
        ws.merge_cells(f"{_col(col)}{row}:{_col(col + span - 1)}{row}")


def _lbl(ws, row, col, txt):
    c = ws.cell(row=row, column=col, value=txt)
    c.font = _fnt(size=9)
    c.fill = _fill(_C["label"])
    c.alignment = _aln()
    c.border = _brd()


def _inp(ws, row, col, val, fmt="General"):
    c = ws.cell(row=row, column=col, value=val)
    c.font = _fnt(size=10)
    c.fill = _fill(_C["inp"])
    c.alignment = _aln("right")
    c.border = _brd()
    if fmt != "General":
        c.number_format = fmt
    return c


def _frm(ws, row, col, formula, fmt="#,##0.00"):
    c = ws.cell(row=row, column=col, value=formula)
    c.font = _fnt(size=10)
    c.fill = _fill(_C["form"])
    c.alignment = _aln("right")
    c.border = _brd()
    c.number_format = fmt
    return c


def _ref_cell(ws, row, col, val, fmt="#,##0.00"):
    c = ws.cell(row=row, column=col, value=val)
    c.font = _fnt(size=10)
    c.fill = _fill(_C["ref"])
    c.alignment = _aln("right")
    c.border = _brd()
    c.number_format = fmt


def _title(ws, row, txt, ncols=8):
    c = ws.cell(row=row, column=1, value=txt)
    c.font = _fnt(bold=True, size=12, color="FFFFFF")
    c.fill = _fill(_C["hdr"])
    c.alignment = _aln("center")
    ws.merge_cells(f"A{row}:{_col(ncols)}{row}")


# ── Helper: get catalog producao_horaria ────────────────────────────────────────


def _lm_render_cron_item_labels(ws, base: int, item) -> None:
    for sub, label in [(0, "Produção semanal"), (1, "Acumulado"), (2, "% Completude")]:
        r = base + sub
        ws.cell(row=r, column=1, value=item.item_id if sub == 0 else "").fill = _fill(_C["label"])
        ws.cell(row=r, column=2, value=getattr(item, "descricao", "")[:25] if sub == 0 else "").fill = _fill(
            _C["label"]
        )
        ws.cell(row=r, column=6, value=label).fill = _fill(_C["label"])
        for ci in [1, 2, 6]:
            ws.cell(row=r, column=ci).border = _brd()
            ws.cell(row=r, column=ci).alignment = _aln()
            ws.cell(row=r, column=ci).font = _fnt(size=8)


def _lm_render_cron_item(
    ws, base: int, item, p: str, eap_rows, alloc_ir, alloc_cols, prat_rows, week_item_cols, H_r, D_r
) -> None:
    r_eap = eap_rows[item.item_id]
    r_alloc = alloc_ir[item.item_id]
    P_ref = f"{p}!E{r_eap}"
    qtd_ref = f"{p}!D{r_eap}"
    _lm_render_cron_item_labels(ws, base, item)
    _frm(ws, base, 3, f"={qtd_ref}", "#,##0.##")
    for col_off in [base + 1, base + 2]:
        ws.cell(row=col_off, column=3).fill = _fill(_C["label"])
        ws.cell(row=col_off, column=3).border = _brd()
    for wk, col in week_item_cols.items():
        alloc_c = alloc_cols.get(wk)
        prat_c = prat_rows.get(wk)
        eq_ref = f"{p}!{_col(alloc_c)}{r_alloc}" if alloc_c else "0"
        p_ref = f"{p}!$B${prat_c}" if prat_c else "1"
        _frm(ws, base, col, f"=IFERROR({eq_ref}*{P_ref}*{H_r}*{D_r}*{p_ref},0)", "#,##0.0")
    week_vals = list(week_item_cols.values())
    for j, col in enumerate(week_vals):
        if j == 0:
            acum_f = f"={_col(col)}{base}"
        else:
            acum_f = f"={_col(week_vals[j - 1])}{base + 1}+{_col(col)}{base}"
        _frm(ws, base + 1, col, acum_f, "#,##0.0")
        _frm(ws, base + 2, col, f"=IF({qtd_ref}>0,{_col(col)}{base + 1}/{qtd_ref},0)", "0.0%")
    first_wk_col = week_vals[0]
    last_wk_col = week_vals[-1]
    _frm(ws, base, 4, f"=SUM({_col(first_wk_col)}{base}:{_col(last_wk_col)}{base})", "#,##0.0")
    for col_off in [base + 1, base + 2]:
        ws.cell(row=col_off, column=4).fill = _fill(_C["label"])
        ws.cell(row=col_off, column=4).border = _brd()
        ws.cell(row=col_off, column=5).fill = _fill(_C["label"])
        ws.cell(row=col_off, column=5).border = _brd()
    _frm(ws, base, 5, f"=IF(C{base}>0,(D{base}-C{base})/C{base},0)", "0.0%")


def _lm_render_curva_s(ws, s_title_row: int, eap, p: str, eap_rows, week_item_cols, item_pct_row) -> None:
    qtd_total_formula = "+".join([f"{p}!D{eap_rows[item.item_id]}" for item in eap])
    for j, (wk, col) in enumerate(week_item_cols.items()):
        row = s_title_row + 2 + j
        ws.cell(row=row, column=1, value=wk).fill = _fill(_C["label"])
        ws.cell(row=row, column=1).border = _brd()
        ws.cell(row=row, column=1).font = _fnt(size=8)
        pct_refs = [f"{p}!D{eap_rows[item.item_id]}*{_col(col)}{item_pct_row[item.item_id]}" for item in eap]
        s_formula = f"=IF(({qtd_total_formula})>0,({'+'.join(pct_refs)})/({qtd_total_formula}),0)"
        _frm(ws, row, 2, s_formula, "0.00%")


def _lm_sv(field: str, obj) -> float:
    """Safe float getter for consolidacao reference values."""
    try:
        return float(getattr(obj, field, 0) or 0)
    except Exception:
        return 0.0


def _lm_render_consol_row(ws, r: int, label: str, formula, ref_val) -> None:
    ws.cell(row=r, column=1, value=label).border = _brd()
    ws.cell(row=r, column=1).fill = _fill(_C["hdr"] if not formula else _C["label"])
    ws.cell(row=r, column=1).font = _fnt(bold=not formula, color="FFFFFF" if not formula else "000000")
    ws.cell(row=r, column=1).alignment = _aln()
    if formula:
        fmt = "0.00%" if "MARGEM" in label else "#,##0.00"
        _frm(ws, r, 2, formula, fmt)
        if ref_val is not None:
            _ref_cell(ws, r, 3, ref_val, fmt)
            _frm(ws, r, 4, f"=B{r}-C{r}", "#,##0.00")
            _frm(ws, r, 5, f"=IF(C{r}<>0,(B{r}-C{r})/C{r},0)", "0.00%")


def _lm_render_func_rows(ws, all_funcoes: list, start_row: int) -> dict:
    func_rows = {}
    for i, f in enumerate(all_funcoes):
        row = start_row + i
        func_rows[f["id"]] = row
        ws.cell(row=row, column=1, value=f["id"]).fill = _fill(_C["label"])
        ws.cell(row=row, column=2, value=f["desc"]).fill = _fill(_C["label"])
        for ci in [1, 2]:
            ws.cell(row=row, column=ci).border = _brd()
            ws.cell(row=row, column=ci).alignment = _aln()
            ws.cell(row=row, column=ci).font = _fnt(size=9)
        _inp(ws, row, 3, round(f["mensal"], 2), "#,##0.00")
    return func_rows


def _lm_render_equip_rows(ws, all_equips: list, start_row: int) -> dict:
    equip_rows = {}
    for i, e in enumerate(all_equips):
        row = start_row + i
        equip_rows[e["id"]] = row
        ws.cell(row=row, column=1, value=e["id"]).fill = _fill(_C["label"])
        ws.cell(row=row, column=2, value=e["desc"]).fill = _fill(_C["label"])
        for ci in [1, 2]:
            ws.cell(row=row, column=ci).border = _brd()
            ws.cell(row=row, column=ci).alignment = _aln()
            ws.cell(row=row, column=ci).font = _fnt(size=9)
        _inp(ws, row, 3, round(e["mensal"], 2), "#,##0.00")
        _inp(ws, row, 4, round(e["comb_mensal"], 2), "#,##0.00")
    return equip_rows


def _lm_build_equipe_maps(equipes, item_id: str):
    eq = equipes.get(item_id)
    if eq is None:
        return {}, {}
    func_map = {}
    for f in eq.funcoes or []:
        func_map[f.funcao_id] = f.num_pessoas
    equip_map = {}
    for e in eq.equipamentos or []:
        equip_map[e.equip_id] = e.num_unidades
    return func_map, equip_map


def _lm_render_comp_item_row(ws, row: int, item, equipes, res_cols, all_res) -> None:
    ws.cell(row=row, column=1, value=item.item_id).fill = _fill(_C["label"])
    ws.cell(row=row, column=2, value=getattr(item, "descricao", "")[:25]).fill = _fill(_C["label"])
    for ci in [1, 2]:
        ws.cell(row=row, column=ci).border = _brd()
        ws.cell(row=row, column=ci).alignment = _aln()
        ws.cell(row=row, column=ci).font = _fnt(size=8)
    func_map, equip_map = _lm_build_equipe_maps(equipes, item.item_id)
    for r_info in all_res:
        col = res_cols[r_info["id"]]
        n = func_map.get(r_info["id"], equip_map.get(r_info["id"], 0))
        val = n if n else None
        c_cell = ws.cell(row=row, column=col, value=val)
        c_cell.fill = _fill(_C["inp"] if n else "F5F5F5")
        c_cell.border = _brd()
        c_cell.alignment = _aln("center")
        c_cell.font = _fnt(size=9)
        c_cell.number_format = "0"


def _lm_render_comp_items(ws, eap, equipes, res_cols, all_res, start_row: int) -> dict:
    comp_item_rows = {}
    for i, item in enumerate(eap):
        row = start_row + i
        comp_item_rows[item.item_id] = row
        _lm_render_comp_item_row(ws, row, item, equipes, res_cols, all_res)
    return comp_item_rows


def _lm_build_cd_formulas(comp_r, all_funcoes, all_equips, func_rows, equip_rows, res_cols):
    mo_terms = [f"RECURSOS!{_col(res_cols[f['id']])}{comp_r}*RECURSOS!$C${func_rows[f['id']]}" for f in all_funcoes]
    eq_terms = [f"RECURSOS!{_col(res_cols[e['id']])}{comp_r}*RECURSOS!$C${equip_rows[e['id']]}" for e in all_equips]
    comb_terms = [f"RECURSOS!{_col(res_cols[e['id']])}{comp_r}*RECURSOS!$D${equip_rows[e['id']]}" for e in all_equips]
    mo_formula = "=" + "+".join(mo_terms) if mo_terms else "=0"
    eq_formula = "=" + "+".join(eq_terms) if eq_terms else "=0"
    comb_formula = "=" + "+".join(comb_terms) if comb_terms else "=0"
    return mo_formula, eq_formula, comb_formula


def _lm_render_cd_rows(
    ws, eap, all_funcoes, all_equips, func_rows, equip_rows, res_cols, comp_item_rows, eap_rows
) -> dict:
    cd_rows = {}
    for i, item in enumerate(eap):
        row = 3 + i
        cd_rows[item.item_id] = row
        comp_r = comp_item_rows[item.item_id]
        mo_formula, eq_formula, comb_formula = _lm_build_cd_formulas(
            comp_r, all_funcoes, all_equips, func_rows, equip_rows, res_cols
        )
        ws.cell(row=row, column=1, value=item.item_id).fill = _fill(_C["label"])
        ws.cell(row=row, column=2, value=getattr(item, "descricao", "")[:22]).fill = _fill(_C["label"])
        for ci in [1, 2]:
            ws.cell(row=row, column=ci).border = _brd()
            ws.cell(row=row, column=ci).alignment = _aln()
            ws.cell(row=row, column=ci).font = _fnt(size=8)
        _frm(ws, row, 3, mo_formula, "#,##0.00")
        _frm(ws, row, 4, eq_formula, "#,##0.00")
        _frm(ws, row, 5, comb_formula, "#,##0.00")
        _frm(ws, row, 6, f"=C{row}+D{row}+E{row}", "#,##0.00")
        eap_r = eap_rows[item.item_id]
        _frm(ws, row, 7, f"=PARÂMETROS!I{eap_r}", "0")
        _frm(ws, row, 8, f"=G{row}/4.348", "0.00")
        _frm(ws, row, 9, f"=F{row}*H{row}", "#,##0.00")
    return cd_rows


def _lm_render_ind_rows(ws, indiretos, start_row: int) -> dict:
    ind_rows = {}
    for i, ind in enumerate(indiretos):
        row = start_row + i
        ind_rows[ind.categoria] = row
        ws.cell(row=row, column=1, value=ind.categoria).fill = _fill(_C["label"])
        ws.cell(row=row, column=1).border = _brd()
        ws.cell(row=row, column=1).alignment = _aln()
        monthly = (
            round(ind.custo_total / max(ind.permanencia_meses or 1, 0.01), 2)
            if ind.permanencia_meses
            else ind.custo_total
        )
        _inp(ws, row, 2, monthly, "#,##0.00")
        _inp(ws, row, 3, round(ind.permanencia_meses or 0, 2), "0.00")
    return ind_rows


def _lm_render_prat_rows(ws, weeks, prat_data, start_row: int) -> dict:
    prat_rows = {}
    for i, wk in enumerate(weeks):
        row = start_row + i
        prat_rows[wk] = row
        ws.cell(row=row, column=1, value=wk).fill = _fill(_C["label"])
        ws.cell(row=row, column=1).border = _brd()
        ws.cell(row=row, column=1).alignment = _aln()
        ws.cell(row=row, column=1).font = _fnt(size=8)
        fator = prat_data.get(wk, 1.0)
        _inp(ws, row, 2, round(fator, 4), "0.00%")
    return prat_rows


def _lm_write_dur_formulas(ws, eap, eap_rows, pos, prat_first: int, prat_last: int) -> None:
    H_r = pos["HORAS_DIA"]
    D_r = pos["DIAS_SEMANA"]
    prat_ref = f"AVERAGE(PARÂMETROS!$B${prat_first}:$B${prat_last})"
    for item in eap:
        row = eap_rows[item.item_id]
        qtd_r = f"D{row}"
        P_r = f"E{row}"
        neq_r = f"H{row}"
        dur_formula = f'=IF(AND({P_r}>0,{neq_r}>0),CEILING({qtd_r}/({P_r}*{H_r}*{D_r}*{prat_ref}*{neq_r}),1),"N/D")'
        ws.cell(row=row, column=9).value = dur_formula


def _prod_h_filter_weeks(dist: dict) -> list:
    result = []
    for d in dist.values():
        if d.num_equipes and d.qtd_executada and d.eficiencia:
            result.append((d.num_equipes, d.qtd_executada, d.eficiencia))
    return result


def _prod_h_compute_samples(weeks_with_data: list, regime) -> list:
    H = regime.horas_dia if regime else 8
    D = regime.dias_semana if regime else 6
    samples = []
    for n, q, p in weeks_with_data:
        if n > 0 and p > 0:
            samples.append(q / (n * H * D * p))
    return samples


def _prod_h_from_canonical(canonical: Any, item_id: str) -> float:
    """Resolve production rate from schedule (divide by H×D)."""
    if not canonical.cronograma:
        return 0.0
    regime = canonical.projeto.regime_trabalho if canonical.projeto else None
    for act in canonical.cronograma.scheduled_activities or []:
        if act.activity_id != item_id:
            continue
        dist = act.distribuicao_semanal or {}
        weeks_with_data = _prod_h_filter_weeks(dist)
        if not weeks_with_data:
            continue
        samples = _prod_h_compute_samples(weeks_with_data, regime)
        if samples:
            return round(sum(samples) / len(samples), 4)
    return 0.0


# ── Main renderer ──────────────────────────────────────────────────────────────


def _fluxo_row_label(ws, row: int, label: str, bold: bool = False) -> None:
    ws.cell(row=row, column=1, value=label).fill = _fill(_C["label"])
    ws.cell(row=row, column=1).border = _brd()
    ws.cell(row=row, column=1).alignment = _aln()
    ws.cell(row=row, column=1).font = _fnt(bold=bold)


def _build_months_from_weeks(weeks: list) -> list[str]:
    from datetime import date

    months_set: set = set()
    for wk in weeks:
        y, w = int(wk[:4]), int(wk[6:])
        d = date.fromisocalendar(y, w, 1)
        months_set.add(f"{d.year}-{d.month:02d}")
    return sorted(months_set)


def _compute_monthly_revenues(c: object, plan: dict, weeks: list) -> dict:
    from collections import defaultdict
    from datetime import date as _d2

    monthly_rev: dict = defaultdict(float)
    cronograma = getattr(c, "cronograma", None)
    if not (cronograma and cronograma.scheduled_activities):
        return monthly_rev
    for act in cronograma.scheduled_activities:
        item_id = act.activity_id
        p = plan.get(item_id)
        pu_com_bdi = p.preco_unitario_com_bdi.total if (p and p.preco_unitario_com_bdi) else 0.0
        if not act.distribuicao_semanal:
            continue
        for wk, dist in act.distribuicao_semanal.items():
            y, w = int(wk[:4]), int(wk[6:])
            d = _d2.fromisocalendar(y, w, 1)
            m = f"{d.year}-{d.month:02d}"
            monthly_rev[m] += dist.qtd_executada * pu_com_bdi
    return monthly_rev


def _compute_monthly_indirects(indiretos: list, months: list) -> dict:
    from collections import defaultdict

    monthly_ind: dict = defaultdict(float)
    for ind in indiretos:
        perm = ind.permanencia_meses or 0
        if perm > 0:
            monthly_rate = ind.custo_total / perm
            for m in months:
                monthly_ind[m] += monthly_rate
    return monthly_ind


def _get_active_months_for_equipe(cronograma: object, equipe_item_id: str) -> set:
    from datetime import date as _d3

    for act in cronograma.scheduled_activities:  # type: ignore[union-attr]
        if act.activity_id != equipe_item_id:
            continue
        if act.distribuicao_semanal:
            active_weeks = {wk for wk, d in act.distribuicao_semanal.items() if d.num_equipes > 0}
            active_months: set = set()
            for wk in active_weeks:
                y2, w2 = int(wk[:4]), int(wk[6:])
                d3 = _d3.fromisocalendar(y2, w2, 1)
                active_months.add(f"{d3.year}-{d3.month:02d}")
            return active_months
    return set()


def _compute_monthly_direct_costs(equipes: dict, c: object, months: list) -> dict:
    from collections import defaultdict

    monthly_cost: dict = defaultdict(float)
    cronograma = getattr(c, "cronograma", None)
    for eq in equipes.values():
        fixo = eq.custo_fixo_mensal or 0
        perm = eq.permanencia_meses or 0
        if perm > 0 and cronograma:
            active_months = _get_active_months_for_equipe(cronograma, eq.item_id)
            for m in active_months:
                monthly_cost[m] += fixo
    return monthly_cost


def _write_monthly_grid(ws, months: list, monthly_rev: dict, monthly_cost: dict, monthly_ind: dict) -> None:
    n_months = len(months)
    for j, m in enumerate(months):
        col = 3 + j
        rev = round(monthly_rev.get(m, 0), 2)
        cost = round(monthly_cost.get(m, 0), 2)
        ind = round(monthly_ind.get(m, 0), 2)
        ws.cell(row=3, column=col, value=rev).number_format = "#,##0"
        ws.cell(row=4, column=col, value=cost).number_format = "#,##0"
        ws.cell(row=5, column=col, value=ind).number_format = "#,##0"
        for r in [3, 4, 5]:
            ws.cell(row=r, column=col).fill = _fill(_C["form"])
            ws.cell(row=r, column=col).border = _brd()
            ws.cell(row=r, column=col).alignment = _aln("right")
            ws.cell(row=r, column=col).font = _fnt(size=9)
        ws.cell(row=6, column=col, value=f"={_col(col)}3-{_col(col)}4-{_col(col)}5")
        ws.cell(row=6, column=col).fill = _fill(_C["form"])
        ws.cell(row=6, column=col).border = _brd()
        ws.cell(row=6, column=col).alignment = _aln("right")
        ws.cell(row=6, column=col).font = _fnt(bold=True)
        ws.cell(row=6, column=col).number_format = "#,##0"
        if j == 0:
            ws.cell(row=7, column=col, value=f"={_col(col)}6")
        else:
            prev = _col(2 + j)
            ws.cell(row=7, column=col, value=f"={prev}7+{_col(col)}6")
        ws.cell(row=7, column=col).fill = _fill(_C["form"])
        ws.cell(row=7, column=col).border = _brd()
        ws.cell(row=7, column=col).alignment = _aln("right")
        ws.cell(row=7, column=col).font = _fnt(bold=True)
        ws.cell(row=7, column=col).number_format = "#,##0"
    tc = 3 + n_months
    ws.column_dimensions[_col(tc)].width = 14
    ws.cell(row=2, column=tc, value="TOTAL").font = _fnt(bold=True, color="FFFFFF")
    ws.cell(row=2, column=tc).fill = _fill(_C["hdr"])
    ws.cell(row=2, column=tc).border = _brd()
    for r in [3, 4, 5, 6]:
        _frm(ws, r, tc, f"=SUM({_col(3)}{r}:{_col(3 + n_months - 1)}{r})", "#,##0")
        ws.cell(row=r, column=tc).font = _fnt(bold=True)


def _lm_build_funcoes(equipes: dict) -> list:
    """Build deduplicated list of all funcoes across equipes."""
    result: list = []
    seen_f: set = set()
    for eq in equipes.values():
        for f in eq.funcoes or []:
            if f.funcao_id not in seen_f:
                seen_f.add(f.funcao_id)
                result.append(
                    {"id": f.funcao_id, "desc": f.descricao or f.funcao_id, "mensal": f.custo_mensal_unitario or 0.0}
                )
    return result


def _lm_build_equips(equipes: dict) -> list:
    """Build deduplicated list of all equipamentos across equipes."""
    result: list = []
    seen_e: set = set()
    for eq in equipes.values():
        for e in eq.equipamentos or []:
            if e.equip_id not in seen_e:
                seen_e.add(e.equip_id)
                result.append(
                    {
                        "id": e.equip_id,
                        "desc": e.descricao or e.equip_id,
                        "mensal": e.custo_mensal or 0.0,
                        "comb_mensal": e.custo_combustivel_mensal or 0.0,
                    }
                )
    return result


def _lm_render_eap_data_rows(
    ws, eap, plan, prod_h, equipes, prat_avg_formula_template, first_row: int, pos: dict
) -> dict:
    """Write EAP data rows (quantitativos, produtividades). Returns eap_rows dict."""
    eap_rows: dict = {}
    for i, item in enumerate(eap):
        row = first_row + i
        eap_rows[item.item_id] = row
        p_unit = plan.get(item.item_id)
        pu_diesel = p_unit.preco_unitario.diesel if p_unit and p_unit.preco_unitario else 0.0
        pu_mo = p_unit.preco_unitario.mao_obra if p_unit and p_unit.preco_unitario else 0.0
        P_val = round(prod_h.get(item.item_id, 0.0), 4)
        eq = equipes.get(item.item_id)
        neq_val = eq.num_equipes_base if eq else 1
        ws.cell(row=row, column=1, value=item.item_id).fill = _fill(_C["label"])
        ws.cell(row=row, column=2, value=getattr(item, "descricao", item.cpu_id)).fill = _fill(_C["label"])
        ws.cell(row=row, column=3, value=getattr(item, "unidade", "")).fill = _fill(_C["label"])
        for ci in [1, 2, 3]:
            ws.cell(row=row, column=ci).border = _brd()
            ws.cell(row=row, column=ci).alignment = _aln()
            ws.cell(row=row, column=ci).font = _fnt(size=9)
        _inp(ws, row, 4, item.quantitativo, "#,##0.##")
        _inp(ws, row, 5, P_val, "#,##0.00")
        _inp(ws, row, 6, round(pu_diesel, 6), "#,##0.0000")
        _inp(ws, row, 7, round(pu_mo, 6), "#,##0.0000")
        _inp(ws, row, 8, neq_val, "0")
        qtd_r = f"D{row}"
        P_r = f"E{row}"
        H_r = pos["HORAS_DIA"]
        D_r = pos["DIAS_SEMANA"]
        neq_r = f"H{row}"
        dur_formula = (
            f"=IF(AND({P_r}>0,{neq_r}>0),"
            f'CEILING({qtd_r}/({P_r}*{H_r}*{D_r}*{prat_avg_formula_template}*{neq_r}),1),"N/D")'
        )
        _frm(ws, row, 9, dur_formula, "0")
    return eap_rows


def _lm_build_cron_map(c) -> dict:
    """Build activity_id -> {week: num_equipes} schedule map."""
    cron_map: dict = {}
    if c.cronograma and c.cronograma.scheduled_activities:
        for act in c.cronograma.scheduled_activities:
            if act.distribuicao_semanal:
                cron_map[act.activity_id] = {wk: dist.num_equipes for wk, dist in act.distribuicao_semanal.items()}
    return cron_map


def _lm_write_alloc_data_rows(ws, alloc_data_row: int, eap, alloc_cols: dict, cron_map: dict, eap_rows: dict) -> dict:
    """Write allocation data rows. Returns alloc_item_rows dict."""
    alloc_item_rows: dict = {}
    for i, item in enumerate(eap):
        row = alloc_data_row + i
        alloc_item_rows[item.item_id] = row
        ws.cell(row=row, column=1, value=item.item_id).fill = _fill(_C["label"])
        ws.cell(row=row, column=2, value=getattr(item, "descricao", "")[:25]).fill = _fill(_C["label"])
        for ci in [1, 2]:
            ws.cell(row=row, column=ci).border = _brd()
            ws.cell(row=row, column=ci).font = _fnt(size=8)
            ws.cell(row=row, column=ci).alignment = _aln()
        _frm(ws, row, 3, f"=PARÂMETROS!D{eap_rows[item.item_id]}", "#,##0.##")
        alloc = cron_map.get(item.item_id, {})
        for wk, col in alloc_cols.items():
            n = alloc.get(wk, 0)
            c_cell = ws.cell(row=row, column=col, value=n if n else None)
            c_cell.fill = _fill(_C["inp"] if n else "F5F5F5")
            c_cell.border = _brd()
            c_cell.alignment = _aln("center")
            c_cell.font = _fnt(size=8)
            c_cell.number_format = "0"
    return alloc_item_rows


class LiveModelRenderer:
    def __init__(self, canonical: Any) -> None:
        self.c = canonical
        regime = canonical.projeto.regime_trabalho if canonical.projeto else None
        self.H = regime.horas_dia if regime else 8
        self.D = regime.dias_semana if regime else 6
        self._build_indices()

    def _build_indices(self):
        """Pre-compute indices for cross-sheet formula generation."""
        c = self.c
        self.eap = list(c.eap or [])
        self.plan = {p.item_id: p for p in (c.planejamento or [])}
        self.equipes = {e.item_id: e for e in (c.equipes_diretas or [])}
        self.indiretos = list(c.indiretos or [])
        self.weeks = self._collect_weeks()

        # Prat data
        prat_obj = c.praticabilidade
        self.prat_data = prat_obj.percentual_produtivo_semanal if prat_obj else {}

        # Production rates per item
        self.prod_h = {item.item_id: _prod_h_from_canonical(c, item.item_id) for item in self.eap}

        # Unique funcoes and equips across all teams
        self.all_funcoes = _lm_build_funcoes(self.equipes)
        self.all_equips = _lm_build_equips(self.equipes)

    def _collect_weeks(self) -> list[str]:
        c = self.c
        weeks: set[str] = set()
        if c.cronograma and c.cronograma.scheduled_activities:
            for act in c.cronograma.scheduled_activities:
                if act.distribuicao_semanal:
                    weeks.update(act.distribuicao_semanal.keys())
        return sorted(weeks)

    def render(self) -> bytes:
        wb = Workbook()
        ws_p = wb.active
        ws_p.title = "PARÂMETROS"
        ws_r = wb.create_sheet("RECURSOS")
        ws_cd = wb.create_sheet("CUSTOS DIR.")
        ws_orc = wb.create_sheet("ORÇAMENTO")
        ws_cr = wb.create_sheet("CRONOGRAMA")
        ws_ind = wb.create_sheet("INDIRETOS")
        ws_con = wb.create_sheet("CONSOLIDAÇÃO")
        ws_fc = wb.create_sheet("FLUXO DE CX")
        ws_ref = wb.create_sheet("REFERÊNCIA")

        pm = self._render_parametros(ws_p)
        rm = self._render_recursos(ws_r)
        cm = self._render_custos_diretos(ws_cd, pm, rm)
        self._render_orcamento(ws_orc, pm)
        self._render_cronograma(ws_cr, pm)
        self._render_indiretos(ws_ind, pm)
        self._render_consolidacao(ws_con, pm)
        self._render_fluxo_cx(ws_fc, pm, cm)
        self._render_referencia(ws_ref)

        buf = BytesIO()
        wb.save(buf)
        return buf.getvalue()

    # ────────────────────────────────────────────────────────────────────────────
    # PARÂMETROS
    # ────────────────────────────────────────────────────────────────────────────

    def _render_parametros(self, ws) -> dict:
        """Returns a map of named positions for cross-sheet formula use."""
        pos = {}  # named positions: key → absolute cell ref

        # Column widths
        ws.column_dimensions["A"].width = 30
        for c in "BCDEFGHI":
            ws.column_dimensions[c].width = 16

        _title(ws, 1, "PARÂMETROS — ÚNICA FONTE DE VERDADE", 9)

        # ── Regime ──────────────────────────────────────────────────────────────
        _hdr(ws, 3, 1, "REGIME DE TRABALHO", 2)
        _lbl(ws, 4, 1, "Horas trabalhadas/dia (H)")
        _inp(ws, 4, 2, self.H, "0")
        pos["HORAS_DIA"] = "PARÂMETROS!$B$4"

        _lbl(ws, 5, 1, "Dias trabalhados/semana (D)")
        _inp(ws, 5, 2, self.D, "0")
        pos["DIAS_SEMANA"] = "PARÂMETROS!$B$5"

        _lbl(ws, 6, 1, "Preço Diesel (R$/L)")
        _inp(ws, 6, 2, 6.99, "#,##0.00")
        pos["PRECO_DIESEL"] = "PARÂMETROS!$B$6"

        # ── BDI ─────────────────────────────────────────────────────────────────
        _hdr(ws, 8, 1, "BDI POR CATEGORIA", 2)
        bdi_vals = self._bdi_rates()
        bdi_lbls = [
            ("BDI Diesel / Combustível (= BDI Material)", "BDI_DIESEL"),
            ("BDI Mão de Obra (TER)", "BDI_MO"),
            ("BDI Equipamentos", "BDI_EQ"),
            ("BDI Indiretos", "BDI_IND"),
        ]
        for i, ((label, key), val) in enumerate(zip(bdi_lbls, bdi_vals, strict=False)):
            row = 9 + i
            _lbl(ws, row, 1, label)
            _inp(ws, row, 2, val, "0.00%")
            pos[key] = f"PARÂMETROS!$B${row}"

        # ── EAP + Produtividades ─────────────────────────────────────────────────
        hdrs_eap = [
            "Item ID",
            "Descrição",
            "Un.",
            "Quantitativo",
            "P (un/h)",
            "P.U.Diesel (R$/un)",
            "P.U.MO (R$/un)",
            "nEq médio",
            "Duração calc. (sem.)",
        ]
        _hdr(ws, 14, 1, "ITENS EAP — QUANTITATIVOS, PRODUTIVIDADES E COMPOSIÇÃO", len(hdrs_eap))
        for ci, h in enumerate(hdrs_eap, 1):
            _hdr(ws, 15, ci, h)

        prat_first = 15 + len(self.eap) + 4
        prat_last = prat_first + len(self.weeks) - 1
        prat_avg_formula_template = f"=AVERAGE(PARÂMETROS!$B${prat_first}:$B${prat_last})"
        eap_rows = _lm_render_eap_data_rows(
            ws, self.eap, self.plan, self.prod_h, self.equipes, prat_avg_formula_template, 16, pos
        )

        pos["EAP_ROWS"] = eap_rows  # type: ignore[assignment]
        pos["EAP_FIRST_DATA_ROW"] = 16  # type: ignore[assignment]
        pos["EAP_LAST_DATA_ROW"] = 15 + len(self.eap)  # type: ignore[assignment]

        # ── Indiretos ────────────────────────────────────────────────────────────
        ind_title_row = 16 + len(self.eap) + 2
        _hdr(ws, ind_title_row, 1, "INDIRETOS — CUSTO FIXO MENSAL E PERMANÊNCIA", 3)
        _hdr(ws, ind_title_row + 1, 1, "Categoria")
        _hdr(ws, ind_title_row + 1, 2, "Custo Fixo Mensal (R$)")
        _hdr(ws, ind_title_row + 1, 3, "Permanência (meses)")
        ind_rows = _lm_render_ind_rows(ws, self.indiretos, ind_title_row + 2)
        pos["IND_ROWS"] = ind_rows  # type: ignore[assignment]

        # ── Praticabilidade semanal ───────────────────────────────────────────────
        prat_title_row = ind_title_row + 2 + len(self.indiretos) + 2
        prat_first = prat_title_row + 2
        prat_last = prat_first + len(self.weeks) - 1

        _hdr(ws, prat_title_row, 1, "PRATICABILIDADE SEMANAL (p_j) — VALORES REAIS", 2)
        _hdr(ws, prat_title_row + 1, 1, "Semana ISO")
        _hdr(ws, prat_title_row + 1, 2, "Fator [0,1]")

        prat_rows = _lm_render_prat_rows(ws, self.weeks, self.prat_data, prat_first)
        pos["PRAT_ROWS"] = prat_rows  # type: ignore[assignment]
        pos["PRAT_COL_FATOR"] = 2  # type: ignore[assignment]
        pos["PRAT_FIRST_ROW"] = prat_first  # type: ignore[assignment]
        pos["PRAT_LAST_ROW"] = prat_last  # type: ignore[assignment]

        # prat_media as named formula (computed over real data)
        pos["PRAT_MEDIA_FORMULA"] = f"AVERAGE(PARÂMETROS!$B${prat_first}:$B${prat_last})"

        # Update dur_calculada formulas now that we know prat rows
        _lm_write_dur_formulas(ws, self.eap, eap_rows, pos, prat_first, prat_last)

        # ── Alocação semanal ─────────────────────────────────────────────────────
        alloc_title_row = prat_last + 2
        alloc_data_row = alloc_title_row + 2  # header + items
        alloc_first_col = 4  # D onwards

        _hdr(ws, alloc_title_row, 1, "ALOCAÇÃO SEMANAL — NÚMERO DE EQUIPES E_{j,i}", 3)
        ws.merge_cells(f"A{alloc_title_row}:{_col(alloc_first_col + len(self.weeks))}{alloc_title_row}")

        _hdr(ws, alloc_title_row + 1, 1, "Item ID")
        _hdr(ws, alloc_title_row + 1, 2, "Desc.")
        _hdr(ws, alloc_title_row + 1, 3, "Qt. total")
        alloc_cols = {}
        for j, wk in enumerate(self.weeks):
            col = alloc_first_col + j
            alloc_cols[wk] = col
            c_h = ws.cell(row=alloc_title_row + 1, column=col, value=wk[:7])
            c_h.font = _fnt(bold=True, size=7)
            c_h.fill = _fill(_C["hdr"])
            c_h.alignment = _aln("center")
            c_h.border = _brd()
            ws.column_dimensions[_col(col)].width = 7

        # Build allocation from schedule
        cron_map = _lm_build_cron_map(self.c)
        alloc_item_rows = _lm_write_alloc_data_rows(ws, alloc_data_row, self.eap, alloc_cols, cron_map, eap_rows)

        pos["ALLOC_ITEM_ROWS"] = alloc_item_rows  # type: ignore[assignment]
        pos["ALLOC_COLS"] = alloc_cols  # type: ignore[assignment]
        pos["ALLOC_FIRST_COL"] = alloc_first_col  # type: ignore[assignment]
        pos["ALLOC_TITLE_ROW"] = alloc_title_row  # type: ignore[assignment]

        return pos

    # ────────────────────────────────────────────────────────────────────────────
    # RECURSOS — funcoes, equipamentos, composição
    # ────────────────────────────────────────────────────────────────────────────

    def _render_recursos(self, ws) -> dict:
        rm = {}  # resource map positions
        ws.column_dimensions["A"].width = 25
        ws.column_dimensions["B"].width = 35
        for c in "CDE":
            ws.column_dimensions[c].width = 18

        _title(ws, 1, "RECURSOS — TAXAS E COMPOSIÇÃO DAS EQUIPES", 8)

        # ── Funcoes ──────────────────────────────────────────────────────────────
        _hdr(ws, 3, 1, "MÃO DE OBRA — TAXAS MENSAIS", 4)
        _hdr(ws, 4, 1, "ID Função")
        _hdr(ws, 4, 2, "Descrição")
        _hdr(ws, 4, 3, "Custo Mensal Unitário (R$)")
        func_rows = _lm_render_func_rows(ws, self.all_funcoes, 5)
        rm["FUNC_ROWS"] = func_rows

        # ── Equipamentos ─────────────────────────────────────────────────────────
        eq_title_row = 5 + len(self.all_funcoes) + 2
        _hdr(ws, eq_title_row, 1, "EQUIPAMENTOS — TAXAS MENSAIS", 4)
        _hdr(ws, eq_title_row + 1, 1, "ID Equip.")
        _hdr(ws, eq_title_row + 1, 2, "Descrição")
        _hdr(ws, eq_title_row + 1, 3, "Aluguel Mensal (R$)")
        _hdr(ws, eq_title_row + 1, 4, "Comb. Mensal (R$) (por unidade)")
        equip_rows = _lm_render_equip_rows(ws, self.all_equips, eq_title_row + 2)
        rm["EQUIP_ROWS"] = equip_rows

        # ── Composição por item (matrix) ─────────────────────────────────────────
        comp_title_row = eq_title_row + 2 + len(self.all_equips) + 2
        all_res = self.all_funcoes + self.all_equips
        n_res = len(all_res)

        _hdr(ws, comp_title_row, 1, "COMPOSIÇÃO DAS EQUIPES — nº PESSOAS / UNIDADES POR ITEM", n_res + 2)
        ws.merge_cells(f"A{comp_title_row}:{_col(n_res + 2)}{comp_title_row}")

        _hdr(ws, comp_title_row + 1, 1, "Item ID")
        _hdr(ws, comp_title_row + 1, 2, "Descrição")
        res_cols = {}
        for j, r in enumerate(all_res):
            col = 3 + j
            res_cols[r["id"]] = col
            c_h = ws.cell(row=comp_title_row + 1, column=col, value=r["id"])
            c_h.font = _fnt(bold=True, size=8, color="FFFFFF")
            c_h.fill = _fill(_C["hdr"])
            c_h.alignment = _aln("center", wrap=True)
            c_h.border = _brd()
            ws.column_dimensions[_col(col)].width = 9
        rm["RES_COLS"] = res_cols

        comp_item_rows = _lm_render_comp_items(ws, self.eap, self.equipes, res_cols, all_res, comp_title_row + 2)
        rm["COMP_ITEM_ROWS"] = comp_item_rows
        rm["ALL_FUNCOES"] = self.all_funcoes  # type: ignore[assignment]
        rm["ALL_EQUIPS"] = self.all_equips  # type: ignore[assignment]
        rm["COMP_TITLE_ROW"] = comp_title_row  # type: ignore[assignment]
        rm["EQ_TITLE_ROW"] = eq_title_row  # type: ignore[assignment]
        return rm

    # ────────────────────────────────────────────────────────────────────────────
    # CUSTOS DIRETOS
    # ────────────────────────────────────────────────────────────────────────────

    def _render_custos_diretos(self, ws, pm: dict, rm: dict) -> dict:
        """Formula-driven: team costs from RECURSOS composition × rates."""
        cm = {}
        ws.column_dimensions["A"].width = 22
        for c in "BCDEFGHI":
            ws.column_dimensions[c].width = 18

        _title(ws, 1, "CUSTOS DIRETOS — EQUIPES POR ITEM (FÓRMULAS SOBRE RECURSOS)", 9)

        hdrs = [
            "Item ID",
            "Desc.",
            "MO Mensal (R$)",
            "EQ Mensal (R$)",
            "Comb. Mensal (R$)",
            "Total Fixo/Mês (R$)",
            "Permanência (sem.)",
            "Permanência (mes.)",
            "Custo Total (R$)",
        ]
        for ci, h in enumerate(hdrs, 1):
            _hdr(ws, 2, ci, h)

        func_rows = rm["FUNC_ROWS"]
        equip_rows = rm["EQUIP_ROWS"]
        res_cols = rm["RES_COLS"]
        comp_item_rows = rm["COMP_ITEM_ROWS"]
        all_funcoes = rm["ALL_FUNCOES"]
        all_equips = rm["ALL_EQUIPS"]
        eap_rows = pm["EAP_ROWS"]

        cd_rows = _lm_render_cd_rows(
            ws, self.eap, all_funcoes, all_equips, func_rows, equip_rows, res_cols, comp_item_rows, eap_rows
        )

        # Total row
        tr = 3 + len(self.eap)
        ws.cell(row=tr, column=1, value="TOTAL").font = _fnt(bold=True)
        for ci in range(1, 10):
            ws.cell(row=tr, column=ci).fill = _fill(_C["tot"])
            ws.cell(row=tr, column=ci).border = _brd()
        first, last = 3, tr - 1
        for ci in [3, 4, 5, 6, 9]:
            _frm(ws, tr, ci, f"=SUM({_col(ci)}{first}:{_col(ci)}{last})", "#,##0.00")
            ws.cell(row=tr, column=ci).fill = _fill(_C["tot"])
            ws.cell(row=tr, column=ci).font = _fnt(bold=True)

        cm["CD_ROWS"] = cd_rows
        cm["CD_TOTAL_ROW"] = tr  # type: ignore[assignment]
        return cm

    # ────────────────────────────────────────────────────────────────────────────
    # ORÇAMENTO
    # ────────────────────────────────────────────────────────────────────────────

    def _render_orcamento(self, ws, pm: dict):
        p = "PARÂMETROS"
        eap_rows = pm["EAP_ROWS"]
        _Lconst()

        ws.column_dimensions["A"].width = 18
        ws.column_dimensions["B"].width = 38
        ws.column_dimensions["C"].width = 7
        for c in "DEFGHIJK":
            ws.column_dimensions[c].width = 16

        _title(ws, 1, "ORÇAMENTO — PREÇOS UNITÁRIOS E SUBTOTAIS (FÓRMULAS)", 10)
        hdrs = [
            "Item ID",
            "Descrição",
            "Un.",
            "Quantitativo",
            "P.U. Diesel",
            "P.U. MO",
            "P.U. s/BDI",
            "P.U. c/BDI",
            "Subtotal s/BDI",
            "Subtotal c/BDI",
            "Δ Cronograma",
        ]
        for ci, h in enumerate(hdrs, 1):
            _hdr(ws, 2, ci, h)

        bdi_d = pm["BDI_DIESEL"]
        bdi_mo = pm["BDI_MO"]
        n_eap = len(self.eap)

        for i, item in enumerate(self.eap):
            row = 3 + i
            r_eap = eap_rows[item.item_id]

            ws.cell(row=row, column=1, value=f"={p}!A{r_eap}").fill = _fill(_C["form"])
            ws.cell(row=row, column=2, value=f"={p}!B{r_eap}").fill = _fill(_C["form"])
            ws.cell(row=row, column=3, value=f"={p}!C{r_eap}").fill = _fill(_C["form"])
            for ci in [1, 2, 3]:
                ws.cell(row=row, column=ci).border = _brd()
                ws.cell(row=row, column=ci).alignment = _aln()
                ws.cell(row=row, column=ci).font = _fnt(size=9)

            _frm(ws, row, 4, f"={p}!D{r_eap}", "#,##0.##")
            _frm(ws, row, 5, f"={p}!F{r_eap}", "#,##0.0000")
            _frm(ws, row, 6, f"={p}!G{r_eap}", "#,##0.0000")
            _frm(ws, row, 7, f"=E{row}+F{row}", "#,##0.0000")
            _frm(ws, row, 8, f"=E{row}*(1+{bdi_d})+F{row}*(1+{bdi_mo})", "#,##0.0000")
            _frm(ws, row, 9, f"=D{row}*G{row}", "#,##0.00")
            _frm(ws, row, 10, f"=D{row}*H{row}", "#,##0.00")

            # Validação cruzada: qtd programada do CRONOGRAMA vs qtd planejada
            # (filled after cronograma is created — placeholder)
            ws.cell(row=row, column=11, value="(ver CRONOGRAMA)").fill = _fill(_C["label"])
            ws.cell(row=row, column=11).border = _brd()
            ws.cell(row=row, column=11).font = _fnt(size=8)
            ws.cell(row=row, column=11).alignment = _aln("center")

        tr = 3 + n_eap
        ws.cell(row=tr, column=1, value="TOTAL").font = _fnt(bold=True)
        for ci in range(1, 11):
            ws.cell(row=tr, column=ci).fill = _fill(_C["tot"])
            ws.cell(row=tr, column=ci).border = _brd()
        row_first, row_last = 3, tr - 1
        _frm(ws, tr, 9, f"=SUM(I{row_first}:I{row_last})", "#,##0.00")
        _frm(ws, tr, 10, f"=SUM(J{row_first}:J{row_last})", "#,##0.00")
        for ci in [9, 10]:
            ws.cell(row=tr, column=ci).fill = _fill(_C["tot"])
            ws.cell(row=tr, column=ci).font = _fnt(bold=True)

    # ────────────────────────────────────────────────────────────────────────────
    # CRONOGRAMA
    # ────────────────────────────────────────────────────────────────────────────

    def _render_cronograma(self, ws, pm: dict):
        p = "PARÂMETROS"
        eap_rows = pm["EAP_ROWS"]
        prat_rows = pm["PRAT_ROWS"]
        pm["PRAT_FIRST_ROW"]
        pm["PRAT_LAST_ROW"]
        alloc_ir = pm["ALLOC_ITEM_ROWS"]
        alloc_cols = pm["ALLOC_COLS"]
        pm["ALLOC_FIRST_COL"]

        H_r = pm["HORAS_DIA"]
        D_r = pm["DIAS_SEMANA"]

        n_eap = len(self.eap)
        n_wks = len(self.weeks)

        ws.column_dimensions["A"].width = 18
        ws.column_dimensions["B"].width = 35
        ws.column_dimensions["C"].width = 14
        ws.column_dimensions["D"].width = 14
        ws.column_dimensions["E"].width = 12

        _title(ws, 1, "CRONOGRAMA — PRODUÇÃO E COMPLETUDE (E×P×H×D×p_j)", 6 + n_wks)

        # Fixed headers
        _hdr(ws, 2, 1, "Item ID")
        _hdr(ws, 2, 2, "Descrição")
        _hdr(ws, 2, 3, "Qtd. planif.")
        _hdr(ws, 2, 4, "Qtd. prog. total")
        _hdr(ws, 2, 5, "Δ fech. (%)")
        _hdr(ws, 2, 6, "Métrica")

        # Praticabilidade row
        ws.cell(row=3, column=1, value="Praticabilidade (p_j)").font = _fnt(bold=True)
        ws.cell(row=3, column=1).fill = _fill(_C["label"])
        ws.cell(row=3, column=1).border = _brd()
        ws.merge_cells("A3:F3")

        # Week headers (col 7 onwards)
        week_item_cols = {}
        for j, wk in enumerate(self.weeks):
            col = 7 + j
            week_item_cols[wk] = col
            c_h = ws.cell(row=2, column=col, value=wk[:7])
            c_h.font = _fnt(bold=True, size=7, color="FFFFFF")
            c_h.fill = _fill(_C["hdr"])
            c_h.alignment = _aln("center", wrap=True)
            c_h.border = _brd()
            ws.column_dimensions[_col(col)].width = 8

            # Praticabilidade row (row 3)
            pr_r = prat_rows.get(wk)
            if pr_r:
                _frm(ws, 3, col, f"={p}!$B${pr_r}", "0.00%")
            else:
                ws.cell(row=3, column=col, value=1.0).number_format = "0.00%"
                ws.cell(row=3, column=col).fill = _fill(_C["form"])
                ws.cell(row=3, column=col).border = _brd()

        # Data rows: 3 rows per item (produção, acumulado, %)
        # Layout: row_base = 4 + i*3  →  produção, acumulado, %
        item_prod_row = {}
        item_acum_row = {}
        item_pct_row = {}

        for i, item in enumerate(self.eap):
            base = 4 + i * 3
            item_prod_row[item.item_id] = base
            item_acum_row[item.item_id] = base + 1
            item_pct_row[item.item_id] = base + 2
            _lm_render_cron_item(ws, base, item, p, eap_rows, alloc_ir, alloc_cols, prat_rows, week_item_cols, H_r, D_r)

        # ── Curva S (summary para gráfico) ───────────────────────────────────────
        s_title_row = 4 + n_eap * 3 + 2
        _hdr(ws, s_title_row, 1, "CURVA S — PROGRESSÃO ACUMULADA TOTAL (%)", len(week_item_cols) + 2)
        ws.merge_cells(f"A{s_title_row}:{_col(7 + n_wks)}{s_title_row}")

        _hdr(ws, s_title_row + 1, 1, "Semana")
        _hdr(ws, s_title_row + 1, 2, "% Global Acumulado")

        # Weight each item by quantity fraction
        _lm_render_curva_s(ws, s_title_row, self.eap, p, eap_rows, week_item_cols, item_pct_row)

    # ────────────────────────────────────────────────────────────────────────────
    # INDIRETOS
    # ────────────────────────────────────────────────────────────────────────────

    def _render_indiretos(self, ws, pm: dict):
        p = "PARÂMETROS"
        ind_rows = pm["IND_ROWS"]
        bdi_ind = pm["BDI_IND"]

        ws.column_dimensions["A"].width = 18
        for c in "BCDEF":
            ws.column_dimensions[c].width = 20

        _title(ws, 1, "INDIRETOS — FÓRMULAS SOBRE PARÂMETROS", 6)
        for ci, h in enumerate(
            ["Categoria", "Custo Mensal", "Permanência (mes.)", "Total s/BDI", "BDI Indireto", "Total c/BDI"], 1
        ):
            _hdr(ws, 2, ci, h)

        for i, ind in enumerate(self.indiretos):
            row = 3 + i
            r = ind_rows[ind.categoria]
            ws.cell(row=row, column=1, value=f"={p}!A{r}").fill = _fill(_C["form"])
            ws.cell(row=row, column=1).border = _brd()
            ws.cell(row=row, column=1).alignment = _aln()
            _frm(ws, row, 2, f"={p}!B{r}", "#,##0.00")
            _frm(ws, row, 3, f"={p}!C{r}", "0.00")
            _frm(ws, row, 4, f"=B{row}*C{row}", "#,##0.00")
            _frm(ws, row, 5, f"={bdi_ind}", "0.00%")
            _frm(ws, row, 6, f"=D{row}*(1+E{row})", "#,##0.00")

        tr = 3 + len(self.indiretos)
        ws.cell(row=tr, column=1, value="TOTAL").font = _fnt(bold=True)
        for ci in range(1, 7):
            ws.cell(row=tr, column=ci).fill = _fill(_C["tot"])
            ws.cell(row=tr, column=ci).border = _brd()
        row_first, row_last = 3, tr - 1
        _frm(ws, tr, 4, f"=SUM(D{row_first}:D{row_last})", "#,##0.00")
        _frm(ws, tr, 6, f"=SUM(F{row_first}:F{row_last})", "#,##0.00")
        ws.cell(row=tr, column=4).font = _fnt(bold=True)
        ws.cell(row=tr, column=6).font = _fnt(bold=True)

    # ────────────────────────────────────────────────────────────────────────────
    # CONSOLIDAÇÃO
    # ────────────────────────────────────────────────────────────────────────────

    def _render_consolidacao(self, ws, pm: dict):
        n_eap = len(self.eap)
        n_ind = len(self.indiretos)
        orc_total = 3 + n_eap
        ind_total = 3 + n_ind
        cd_total = 3 + n_eap

        _title(ws, 1, "CONSOLIDAÇÃO FINANCEIRA — FÓRMULAS CROSS-SHEET", 4)
        for ci, h in enumerate(["Indicador", "Concilium (R$)", "Referência (R$)", "Delta (R$)", "Delta (%)"], 1):
            _hdr(ws, 2, ci, h)
        for c in "ABCDE":
            ws.column_dimensions[c].width = 38 if c == "A" else 18

        ref = self.c.resultado
        venda = getattr(ref, "venda", None) if ref else None
        custo = getattr(ref, "custo", None) if ref else None

        rows_def = [
            (4, "DIRETO", None, None),
            (5, "  s/BDI (equipes)", f"=ORÇAMENTO!I{orc_total}", _lm_sv("direto_equipes", custo)),
            (6, "  c/BDI", f"=ORÇAMENTO!J{orc_total}", _lm_sv("total_com_bdi", venda)),
            (7, "  Custo equipes (running)", f"='CUSTOS DIR.'!I{cd_total}", None),
            (9, "INDIRETO", None, None),
            (10, "  s/BDI", f"=INDIRETOS!D{ind_total}", None),
            (11, "  c/BDI", f"=INDIRETOS!F{ind_total}", None),
            (13, "CUSTO TOTAL (catálogo)", "=B5+B10", _lm_sv("total", custo)),
            (14, "PREÇO DE VENDA", "=B6+B11", _lm_sv("total_com_bdi", venda)),
            (16, "MARGEM", "=IF(B14>0,(B14-B13)/B14,0)", None),
        ]
        for r, label, formula, ref_val in rows_def:
            _lm_render_consol_row(ws, r, label, formula, ref_val)

    # ────────────────────────────────────────────────────────────────────────────
    # FLUXO DE CAIXA
    # ────────────────────────────────────────────────────────────────────────────

    def _render_fluxo_cx(self, ws, pm: dict, cm: dict) -> None:
        """Monthly cash flow: revenue = cronograma production x unit_price_com_bdi."""
        _title(ws, 1, "FLUXO DE CAIXA MENSAL - RECEITA E DESPESA (FORMULAS)", 16)
        ws.column_dimensions["A"].width = 22
        ws.column_dimensions["B"].width = 22

        if not self.weeks:
            ws.cell(row=3, column=1, value="Dados de cronograma insuficientes para fluxo de caixa.")
            return

        months = _build_months_from_weeks(self.weeks)
        for j, m in enumerate(months):
            col = 3 + j
            ws.column_dimensions[_col(col)].width = 10
            c_h = ws.cell(row=2, column=col, value=m)
            c_h.font = _fnt(bold=True, size=8, color="FFFFFF")
            c_h.fill = _fill(_C["hdr"])
            c_h.alignment = _aln("center")
            c_h.border = _brd()

        _fluxo_row_label(ws, 3, "RECEITA (cron. x P.U. c/BDI)", True)
        _fluxo_row_label(ws, 4, "CUSTO DIRETO (equipes)", True)
        _fluxo_row_label(ws, 5, "CUSTO INDIRETO (mensal)", True)
        _fluxo_row_label(ws, 6, "SALDO MENSAL", True)
        _fluxo_row_label(ws, 7, "SALDO ACUMULADO", True)

        monthly_rev = _compute_monthly_revenues(self.c, self.plan, self.weeks)
        monthly_ind = _compute_monthly_indirects(self.indiretos, months)
        monthly_cost = _compute_monthly_direct_costs(self.equipes, self.c, months)

        _write_monthly_grid(ws, months, monthly_rev, monthly_cost, monthly_ind)

    # ────────────────────────────────────────────────────────────────────────────
    # REFERÊNCIA
    # ────────────────────────────────────────────────────────────────────────────

    def _render_referencia(self, ws):
        _title(ws, 1, "REFERÊNCIA — VALORES CALCULADOS PELO CONCILIUM", 5)
        for ci, h in enumerate(["Indicador", "Valor calculado (R$)", "Base de cálculo"], 1):
            _hdr(ws, 2, ci, h)
        for c in "ABC":
            ws.column_dimensions[c].width = 38 if c == "A" else 22

        res = self.c.resultado
        venda = getattr(res, "venda", None) if res else None
        custo = getattr(res, "custo", None) if res else None

        def _sv(f, obj):
            try:
                return float(getattr(obj, f, 0) or 0)
            except Exception:
                return 0.0

        items = [
            ("Custo Direto (equipes)", _sv("direto_equipes", custo), "Σ(fixo_mensal × permanência instancial)"),
            ("Custo Direto — Equipes (running cost)", _sv("direto_equipes", custo), "Σ(fixo_mensal × permanência)"),
            ("Custo Indireto", _sv("total", None) or sum(i.custo_total for i in self.indiretos), "Σ por categoria"),
            ("Custo Total (catálogo + indireto)", _sv("total", custo), "direto_cat + indireto"),
            (
                "Preço de Venda (catálogo c/BDI + indireto)",
                _sv("total_com_bdi", venda),
                "Σ(qtd×P.U.c/BDI) + ind×(1+BDI_ind)",
            ),
            ("Margem", _sv("margem_pct", res), "(preco_venda - custo_total) / preco_venda"),
        ]
        for i, (label, val, note) in enumerate(items):
            row = 3 + i
            ws.cell(row=row, column=1, value=label).fill = _fill(_C["label"])
            ws.cell(row=row, column=1).border = _brd()
            ws.cell(row=row, column=1).alignment = _aln()
            fmt = "0.00%" if "Margem" in label else "#,##0.00"
            _ref_cell(ws, row, 2, val, fmt)
            ws.cell(row=row, column=3, value=note).fill = _fill(_C["label"])
            ws.cell(row=row, column=3).border = _brd()
            ws.cell(row=row, column=3).alignment = _aln()
            ws.cell(row=row, column=3).font = _fnt(size=9)

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _bdi_rates(self) -> list[float]:
        plan = list(self.c.planejamento or [])
        if plan:
            bdi = getattr(plan[0], "bdi", None)
            if bdi:
                return [
                    float(getattr(bdi, "diesel", 0.04) or 0.04),
                    float(getattr(bdi, "mao_obra", 0.29975) or 0.29975),
                    float(getattr(bdi, "equipamentos", 0.29975) or 0.29975),
                    float(getattr(bdi, "indireto", 0.25205) or 0.25205),
                ]
        return [0.04, 0.29975, 0.29975, 0.25205]


class _Lconst:
    COL_EAP_QTD = 4
    COL_EAP_PRODH = 5
    COL_EAP_DIESEL = 6
    COL_EAP_MO = 7
    COL_PARAM_VAL = 2
    ROW_BDI_DIESEL = 9
    ROW_BDI_MO = 10
    ROW_HORAS_DIA = 4
    ROW_DIAS_SEMANA = 5


def render_live_model(canonical: Any) -> bytes:
    return LiveModelRenderer(canonical).render()
