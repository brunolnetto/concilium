"""Excel sheets — resultado (parte extraída de resultado.py, grupo _bdi)."""

from __future__ import annotations

from openpyxl import Workbook

from concilium.domain.models.canonical import CanonicalModel

from ...styles import (
    _C,
    _align,
    _border,
    _fill,
    _font,
    _header_row,
    _label,
    _section_row,
    _set_col_widths,
    _title_row,
)


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


