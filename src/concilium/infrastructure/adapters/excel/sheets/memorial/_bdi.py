"""Excel adapter — abas MEMORIAL — render_memorial_bdi (encargos, categorias BDI, decomposição, aplicação)."""

from __future__ import annotations

from typing import Any

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
    from concilium.domain.models.financial.bdi import DEFAULT_BDI_TABELA
    from concilium.domain.services.financial.memorial_bdi_builder import MemorialBDIBuilder

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


