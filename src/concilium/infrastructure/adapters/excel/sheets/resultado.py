from __future__ import annotations

import math
import re as _re
from typing import Any

from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from openpyxl.workbook.defined_name import DefinedName

from concilium.domain.models.canonical import CanonicalModel

from ..cash_flow import _cash_flow
from ..helpers import _fmt_mes, _project_months
from ..styles import (
    _C,
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


def _xl_resultado_ref(sheet: str, col: int, ref_row: int | None, fallback: Any) -> Any:
    """Cross-sheet formula reference when ref_row is known."""
    if ref_row is not None:
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
        linha_fn(f"  {cat}", _xl_resultado_ref("INDIRETOS.DET", 8, cat_row, fallback))


def _xl_resultado_custo_composicao(res: Any, planejamento_total_row: int | None, linha_fn: Any) -> float:
    """COMPOSIÇÃO DE CUSTO block — returns cd (direto base value)."""
    if not res:
        return 0.0
    cd = res.custo.direto_equipes
    ci_total = res.custo.total - cd
    pvt = res.venda.total_com_bdi
    razao = ci_total / cd if cd > 0 else 0.0
    ci_pvt = ci_total / pvt if pvt > 0 else 0.0
    linha_fn(
        "Total Direto (equipes)",
        _xl_resultado_ref("PLANEJAMENTO", 13, planejamento_total_row, res.venda.total_sem_bdi),
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
    linha("Localização", str(proj.localizacao) if proj.localizacao is not None else "", is_money=False)
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
        "Custo direto (equipes)",
        _xl_resultado_ref("PLANEJAMENTO", 13, planejamento_total_row, res.custo.direto_equipes),
    )
    _xl_resultado_indirect_cats(res, indiretos_refs, linha)
    custo_ind = res.custo.total - res.custo.direto_equipes
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


def render_bdi(wb: Workbook, canonical: CanonicalModel) -> None:
    """BDI — Decomposição TCU Ac.2622/2013 por categoria (MO, MAT, SERV, IND, DIESEL)."""
    from concilium.domain.models.financial.bdi import DEFAULT_BDI_TABELA  # lazy import

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
    eap_ordem = {e.item_id: (e.ordem if e.ordem is not None else 9999) for e in canonical.eap}
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


def _rir_build_lookups(canonical) -> tuple:
    """Build category lookup dicts and total_sem for render_indiretos_res."""
    inds_by_cat = {ind.categoria: ind for ind in canonical.indiretos}
    bdi_by_cat = {ibd.categoria: ibd for ibd in canonical.indiretos_com_bdi}
    total_sem = sum(ind.custo_total for ind in canonical.indiretos) or 1.0
    return inds_by_cat, bdi_by_cat, total_sem


def _rir_render_total_row(ws, row: int, subtotal_rows_sem: list, subtotal_rows_com: list, fill_tot) -> None:
    """Render totals row in INDIRETOS.RES."""
    f_sem = ("=" + "+".join(f"C{r}" for r in subtotal_rows_sem)) if subtotal_rows_sem else "0"
    f_com = ("=" + "+".join(f"E{r}" for r in subtotal_rows_com)) if subtotal_rows_com else "0"
    _money(ws, row, 3, f_sem, fill_tot, bold=True, color=_C["white"])
    ws.cell(row=row, column=4).fill = fill_tot
    ws.cell(row=row, column=4).border = _border()
    _money(ws, row, 5, f_com, fill_tot, bold=True, color=_C["white"])
    ws.cell(row=row, column=6).fill = fill_tot
    ws.cell(row=row, column=6).border = _border()


def _rir_render_cat_row(ws, row: int, cat: str, ind, ibd, fill, total_sem: float) -> int:
    """Render one indirect-cost category row. Returns next row."""
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
    return row + 1


def _rir_render_kpis(ws, row: int, res, ncols: int) -> int:
    """Render KPI indicators section in INDIRETOS.RES. Returns next row."""
    cd = res.custo.direto_equipes
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
        ws.merge_cells(start_row=row, start_column=3, end_row=row, end_column=ncols)
        row += 1
    return row


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
    inds_by_cat, bdi_by_cat, total_sem = _rir_build_lookups(canonical)
    fill_colors = [_fill(_C["white"]), _fill(_C["row_alt"])]
    subtotal_rows_sem: list[int] = []
    subtotal_rows_com: list[int] = []
    for i, cat in enumerate(ORDEM_CAT):
        ind = inds_by_cat.get(cat)  # type: ignore[call-overload]
        if not ind:
            continue
        ibd = bdi_by_cat.get(cat)  # type: ignore[call-overload]
        fill = fill_colors[i % 2]
        row = _rir_render_cat_row(ws, row, cat, ind, ibd, fill, total_sem)
        subtotal_rows_sem.append(row - 1)
        subtotal_rows_com.append(row - 1)
    row += 1
    fill_tot = _fill(_C["nav_dk"])
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=2)
    cell = ws.cell(row=row, column=1, value="TOTAL INDIRETO")
    cell.fill = fill_tot
    cell.font = _font(bold=True, color=_C["white"], size=11)
    cell.alignment = _align("right")
    cell.border = _border()
    _rir_render_total_row(ws, row, subtotal_rows_sem, subtotal_rows_com, fill_tot)
    row += 3
    _section_row(ws, row, "INDICADORES DE COMPOSIÇÃO DE CUSTO", NCOLS)
    row += 1
    res = canonical.resultado
    if res:
        row = _rir_render_kpis(ws, row, res, NCOLS)


def _rcr_build_qty_by_item(canonical, project_months: list) -> dict:
    """Build dict of {activity_id: {(year,month): qty}} from cronograma."""
    qty_by_item: dict = {}
    if not canonical.cronograma:
        return qty_by_item
    for act in canonical.cronograma.scheduled_activities:
        if act.activity_id not in qty_by_item:
            qty_by_item[act.activity_id] = {ym: 0.0 for ym in project_months}
        for wk, dist in act.distribuicao_semanal.items():
            from ..helpers import _week_to_month

            ym = _week_to_month(wk)
            if ym in qty_by_item[act.activity_id]:
                qty_by_item[act.activity_id][ym] += getattr(dist, "qtd_executada", 0.0)
    return qty_by_item


def _rcr_render_item_row(ws, row: int, item, fill, monthly: dict, project_months: list) -> int:
    """Render one EAP item row in CRONOGRAMA.RES sheet. Returns next row."""
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
    return row + 1


def render_cronograma_res(wb: Workbook, canonical: CanonicalModel) -> None:
    """CRONOGRAMA.RES — Resumo mensal de produção física por item EAP."""
    ws = wb.create_sheet("CRONOGRAMA.RES")
    project_months = _project_months(canonical)
    if not project_months:
        ws.cell(row=1, column=1).value = "Sem dados de cronograma."
        return
    qty_by_item = _rcr_build_qty_by_item(canonical, project_months)
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
        row = _rcr_render_item_row(ws, row, item, fill, monthly, project_months)


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


# ── REFERÊNCIA ───────────────────────────────────────────────────────────────


def render_referencia(wb, canonical) -> None:
    """REFERÊNCIA — valores calculados pelo Concilium com base de cálculo auditável.

    Porta a aba REFERÊNCIA do live_model: mostra os valores financeiros-chave
    do canonical com a explicação de como cada um é derivado, permitindo
    auditoria da formulação usada pelo sistema.
    """
    ws = wb.create_sheet("REFERÊNCIA")
    _set_col_widths(ws, [42, 20, 50])
    NCOLS = 3

    fills = [_fill(_C["white"]), _fill(_C["row_alt"])]
    row = 1

    _title_row(ws, row, "REFERÊNCIA — VALORES CALCULADOS PELO CONCILIUM (FORMULAÇÃO REFERENCIAL)", NCOLS)
    row += 2

    _section_row(ws, row, "RESULTADOS FINANCEIROS CALCULADOS", NCOLS)
    row += 1
    _header_row(ws, row, ["Indicador", "Valor Calculado (R$)", "Base de Cálculo / Formulação"])
    row += 1

    res = canonical.resultado
    venda = getattr(res, "venda", None) if res else None
    custo = getattr(res, "custo", None) if res else None

    def _sv(obj, field, default=0.0):
        try:
            return float(getattr(obj, field, None) or default)
        except Exception:
            return default

    indireto_total = sum(float(getattr(ind, "custo_total", 0) or 0) for ind in (canonical.indiretos or []))

    items = [
        # (label, value, formula_note, is_pct)
        (
            "Custo Direto — Equipes (catálogo)",
            _sv(custo, "direto_equipes"),
            "Σ(custo_fixo_mensal × permanência_efetiva_meses × nEq) por atividade",
            False,
        ),
        (
            "Custo Direto — Pool instancial (N3)",
            _sv(custo, "direto_pool") or _sv(custo, "direto_equipes"),
            "Σ(custo_pool_imputado × nEq) via contratos de pool (ADR-071)",
            False,
        ),
        (
            "Custo Indireto",
            indireto_total if indireto_total > 0 else _sv(custo, "indireto_total"),
            "Σ(custo_fixo_mensal × permanência) por categoria indireta",
            False,
        ),
        ("Custo Total (direto + indireto)", _sv(custo, "total"), "custo_direto + custo_indireto (sem BDI)", False),
        (
            "Preço de Venda — sem BDI",
            _sv(venda, "total_sem_bdi"),
            "Σ(quantitativo × PU_cat) por item EAP + indiretos s/BDI",
            False,
        ),
        (
            "Preço de Venda — com BDI",
            _sv(venda, "total_com_bdi"),
            "Σ(quantitativo × PU_cat × (1+BDI_cat)) por categoria + indiretos×(1+BDI_ind)",
            False,
        ),
        ("Margem Bruta", _sv(res, "margem_pct"), "(preco_venda_com_bdi - custo_total) / preco_venda_com_bdi", True),
    ]

    for i, (label, value, note, is_pct) in enumerate(items):
        fill = fills[i % 2]
        fmt = "0.00%" if is_pct else "#,##0.00"

        ws.cell(row=row, column=1, value=label).fill = fill
        ws.cell(row=row, column=1).border = _border()
        ws.cell(row=row, column=1).alignment = _align("left")
        ws.cell(row=row, column=1).font = _font(size=10)

        cell_val = ws.cell(row=row, column=2, value=value)
        cell_val.fill = fill
        cell_val.border = _border()
        cell_val.alignment = _align("right")
        cell_val.number_format = fmt
        cell_val.font = _font(bold=True, size=10)

        ws.cell(row=row, column=3, value=note).fill = fill
        ws.cell(row=row, column=3).border = _border()
        ws.cell(row=row, column=3).alignment = _align("left")
        ws.cell(row=row, column=3).font = _font(italic=True, size=9)
        row += 1

    row += 1

    # ── Seção 2: Bridge N1 → N2 → N3 ────────────────────────────────────────
    _section_row(ws, row, "BRIDGE DE PRECIFICAÇÃO N1 → N2 → N3 (NEP-042)", NCOLS)
    row += 1
    _header_row(ws, row, ["Camada", "Valor (R$)", "Interpretação"])
    row += 1

    pe_items = canonical.ponto_equilibrio or []
    n1 = sum(float(getattr(pe, "preco_venda_cpu", 0) or 0) for pe in pe_items)
    gap_escala = sum(float(getattr(pe, "gap_escala_abs", 0) or 0) for pe in pe_items)
    gap_prat = sum(float(getattr(pe, "gap_praticabilidade_abs", 0) or 0) for pe in pe_items)
    n2 = n1 + gap_escala
    n3 = n2 + gap_prat

    bridge_rows = [
        ("N1 — Catálogo puro (Σ PU_cat × Q)", n1, "Base de mercado: preço de referência sem considerar execução real"),
        (
            f"  Δ Gap de Escala (+ R$ {gap_escala:,.0f})",
            gap_escala,
            "Custo de paralelismo: frentes adicionais com produtividade marginal",
        ),
        ("N2 — Autônomo escalado", n2, "Custo se equipes fossem dedicadas (sem compartilhamento de pool)"),
        (
            f"  Δ Gap de Praticabilidade (+ R$ {gap_prat:,.0f})",
            gap_prat,
            "Perdas climáticas e de eficiência absorvidas pelo pool",
        ),
        ("N3 — Pool instancial", n3, "Custo real projetado com pool compartilhado (= N2 ± economia/custo pool)"),
    ]

    for i, (label, value, note) in enumerate(bridge_rows):
        fill = fills[i % 2]
        ws.cell(row=row, column=1, value=label).fill = fill
        ws.cell(row=row, column=1).border = _border()
        ws.cell(row=row, column=1).alignment = _align("left")
        ws.cell(row=row, column=1).font = _font(bold="N1" in label or "N2" in label or "N3" in label, size=10)

        cell_val = ws.cell(row=row, column=2, value=value)
        cell_val.fill = fill
        cell_val.border = _border()
        cell_val.alignment = _align("right")
        cell_val.number_format = "#,##0.00"
        cell_val.font = _font(bold="N1" in label or "N2" in label or "N3" in label, size=10)

        ws.cell(row=row, column=3, value=note).fill = fill
        ws.cell(row=row, column=3).border = _border()
        ws.cell(row=row, column=3).alignment = _align("left")
        ws.cell(row=row, column=3).font = _font(italic=True, size=9)
        row += 1

    ws.freeze_panes = "A4"
