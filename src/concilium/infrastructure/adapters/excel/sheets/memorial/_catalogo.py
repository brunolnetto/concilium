"""Excel adapter — abas MEMORIAL — render_memorial_catalogo (composição por item: EAP, equipes, equipamentos)."""

from __future__ import annotations

from typing import Any

from ...styles import (
    _C,
    _align,
    _border,
    _fill,
    _font,
    _header_row,
    _section_row,
    _set_col_widths,
    _title_row,
)


def _xl_catalogo_write_row_cells(ws: Any, row: int, vals: list, fmts: list, fill: Any, right_from_col: int) -> None:
    """Escreve uma linha de células com fill/border/alignment/font/number_format padrão."""
    for col, (v, fmt) in enumerate(zip(vals, fmts, strict=False), 1):
        cell = ws.cell(row=row, column=col, value=v)
        cell.fill = fill
        cell.border = _border()
        cell.alignment = _align("right" if col >= right_from_col else "left")
        cell.font = _font(size=9)
        if fmt:
            cell.number_format = fmt


def _xl_catalogo_fv(obj: Any, field: str, default: float = 0.0) -> float:
    try:
        return float(getattr(obj, field, None) or default)
    except Exception:
        return default


def _xl_catalogo_secao1_header(ws: Any, row: int, NCOLS: int) -> int:
    """Título e cabeçalho da Seção 1 (parâmetros por item); retorna row apos header."""
    _section_row(ws, row, "1. PARÂMETROS DE CATÁLOGO — POR ITEM EAP", NCOLS)
    row += 1
    _header_row(
        ws,
        row,
        [
            "Item ID",
            "CPU ID",
            "Descrição",
            "Un.",
            "Qtd.",
            "P_i (un/h)",
            "PU MO s/BDI",
            "PU EQ s/BDI",
            "PU Diesel s/BDI",
            "PU Total s/BDI",
            "PU Total c/BDI",
            "nEq",
            "Custo Fixo/Mês",
            "Perm. Efet. (m)",
        ],
    )
    return row + 1


def _xl_catalogo_secao1_row(ws: Any, row: int, item: Any, p: Any, eq: Any, fill: Any) -> None:
    pu = getattr(p, "preco_unitario", None) if p else None
    pu_bdi = getattr(p, "preco_unitario_com_bdi", None) if p else None

    vals = [
        item.item_id,
        item.cpu_id,
        getattr(item, "descricao", "") or item.cpu_id,
        getattr(item, "unidade", ""),
        _xl_catalogo_fv(item, "quantitativo"),
        _xl_catalogo_fv(eq, "producao_horaria") if eq else 0.0,
        _xl_catalogo_fv(pu, "mao_obra"),
        _xl_catalogo_fv(pu, "equipamentos"),
        _xl_catalogo_fv(pu, "diesel"),
        _xl_catalogo_fv(pu, "total"),
        _xl_catalogo_fv(pu_bdi, "total"),
        int(_xl_catalogo_fv(eq, "num_equipes_base", 1)) if eq else 1,
        _xl_catalogo_fv(eq, "custo_fixo_mensal"),
        _xl_catalogo_fv(eq, "permanencia_efetiva_meses"),
    ]
    fmts = [
        None,
        None,
        None,
        None,
        "#,##0.##",
        "0.0000",
        "#,##0.0000",
        "#,##0.0000",
        "#,##0.0000",
        "#,##0.0000",
        "#,##0.0000",
        "0",
        "#,##0.00",
        "0.00",
    ]

    _xl_catalogo_write_row_cells(ws, row, vals, fmts, fill, right_from_col=5)


def _xl_catalogo_secao1(ws: Any, row: int, eap: list, plan_map: dict, equipe_map: dict, fills: list, NCOLS: int) -> int:
    """Seção 1: parâmetros de catálogo por item EAP; retorna row apos a seção + blank."""
    row = _xl_catalogo_secao1_header(ws, row, NCOLS)
    for i, item in enumerate(eap):
        fill = fills[i % 2]
        p = plan_map.get(item.item_id)
        eq = equipe_map.get(item.item_id)
        _xl_catalogo_secao1_row(ws, row, item, p, eq, fill)
        row += 1
    return row + 1


def _xl_catalogo_secao2_header(ws: Any, row: int, NCOLS: int) -> int:
    """Título e cabeçalho da Seção 2 (composição de equipes — funções)."""
    _section_row(ws, row, "2. COMPOSIÇÃO DE EQUIPES — FUNÇÕES (MÃO DE OBRA)", NCOLS)
    row += 1
    _header_row(
        ws,
        row,
        [
            "Item ID",
            "CPU ID",
            "Função ID",
            "Descrição",
            "Num. Pessoas",
            "Custo Unit. Mensal (R$)",
            "Custo Total Mensal (R$)",
            "Encargos Separados",
            "Cat. Sindical",
            "",
            "",
            "",
            "",
            "",
        ],
    )
    return row + 1


def _xl_catalogo_secao2_row(ws: Any, row: int, item: Any, func: Any, j: int, fill: Any) -> None:
    n_pessoas = int(getattr(func, "num_pessoas", 1) or 1)
    custo_unit = float(getattr(func, "custo_mensal_unitario", 0) or 0)
    custo_enc = float(getattr(func, "custo_encargos_mensal", 0) or 0)
    cat = getattr(func, "categoria_sindical", "") or ""
    vals = [
        item.item_id if j == 0 else "",
        item.cpu_id if j == 0 else "",
        getattr(func, "funcao_id", ""),
        getattr(func, "descricao", "") or getattr(func, "funcao_id", ""),
        n_pessoas,
        custo_unit,
        round(n_pessoas * custo_unit, 2),
        custo_enc,
        cat,
    ]
    fmts = [None, None, None, None, "0", "#,##0.00", "#,##0.00", "#,##0.00", None]
    _xl_catalogo_write_row_cells(ws, row, vals, fmts, fill, right_from_col=5)


def _xl_catalogo_secao2(ws: Any, row: int, eap: list, equipe_map: dict, fills: list, NCOLS: int) -> int:
    """Seção 2: composição de equipes por funções; retorna row apos a seção + blank."""
    row = _xl_catalogo_secao2_header(ws, row, NCOLS)
    for i, item in enumerate(eap):
        eq = equipe_map.get(item.item_id)
        if not eq:
            continue
        for j, func in enumerate(eq.funcoes or []):
            fill = fills[(i + j) % 2]
            _xl_catalogo_secao2_row(ws, row, item, func, j, fill)
            row += 1
    return row + 1


def _xl_catalogo_secao3_header(ws: Any, row: int, NCOLS: int) -> int:
    """Título e cabeçalho da Seção 3 (composição de equipes — equipamentos)."""
    _section_row(ws, row, "3. COMPOSIÇÃO DE EQUIPES — EQUIPAMENTOS", NCOLS)
    row += 1
    _header_row(
        ws,
        row,
        [
            "Item ID",
            "CPU ID",
            "Equip. ID",
            "Descrição",
            "Num. Unidades",
            "Aluguel Mensal/Unid. (R$)",
            "Manutenção Mensal/Unid. (R$)",
            "Comb. Mensal/Unid. (R$)",
            "Total Mensal (R$)",
            "",
            "",
            "",
            "",
            "",
        ],
    )
    return row + 1


def _xl_catalogo_secao3_row(ws: Any, row: int, item: Any, equip: Any, j: int, fill: Any) -> None:
    n_unid = int(getattr(equip, "num_unidades", 1) or 1)
    alug = float(getattr(equip, "custo_locacao_mensal", 0) or 0)
    manut = float(getattr(equip, "custo_manutencao_mensal", 0) or 0)
    comb = float(getattr(equip, "custo_combustivel_mensal", 0) or 0)
    total = n_unid * (alug + manut + comb)
    vals = [
        item.item_id if j == 0 else "",
        item.cpu_id if j == 0 else "",
        getattr(equip, "equip_id", ""),
        getattr(equip, "descricao", "") or getattr(equip, "equip_id", ""),
        n_unid,
        alug,
        manut,
        comb,
        round(total, 2),
    ]
    fmts = [None, None, None, None, "0", "#,##0.00", "#,##0.00", "#,##0.00", "#,##0.00"]
    _xl_catalogo_write_row_cells(ws, row, vals, fmts, fill, right_from_col=5)


def _xl_catalogo_secao3(ws: Any, row: int, eap: list, equipe_map: dict, fills: list, NCOLS: int) -> int:
    """Seção 3: composição de equipes por equipamentos; retorna row apos a seção."""
    row = _xl_catalogo_secao3_header(ws, row, NCOLS)
    for i, item in enumerate(eap):
        eq = equipe_map.get(item.item_id)
        if not eq:
            continue
        for j, equip in enumerate(eq.equipamentos or []):
            fill = fills[(i + j) % 2]
            _xl_catalogo_secao3_row(ws, row, item, equip, j, fill)
            row += 1
    return row


def render_memorial_catalogo(wb, canonical) -> None:
    """MEMORIAL.CATALOGO — parâmetros de catálogo por item EAP (formulação referencial).

    Porta a essência das abas PARÂMETROS e RECURSOS do live_model:
    produtividade, preços unitários, composição de equipe (funcoes + equipamentos)
    para cada item da EAP. Permite auditar como os valores do canonical foram
    construídos a partir do catálogo.
    """
    ws = wb.create_sheet("MEMORIAL.CATALOGO")
    NCOLS = 14
    _set_col_widths(ws, [18, 16, 30, 6, 14, 10, 12, 12, 12, 12, 12, 10, 12, 14])

    plan_map = {p.item_id: p for p in (canonical.planejamento or [])}
    equipe_map = {e.item_id: e for e in (canonical.equipes_diretas or [])}
    eap = canonical.eap or []

    fills = [_fill(_C["white"]), _fill(_C["row_alt"])]
    row = 1

    _title_row(ws, row, "MEMORIAL DO CATÁLOGO — PARÂMETROS DE PRODUTIVIDADE E COMPOSIÇÃO POR ITEM EAP", NCOLS)
    row += 2

    row = _xl_catalogo_secao1(ws, row, eap, plan_map, equipe_map, fills, NCOLS)
    row = _xl_catalogo_secao2(ws, row, eap, equipe_map, fills, NCOLS)
    _xl_catalogo_secao3(ws, row, eap, equipe_map, fills, NCOLS)

    ws.freeze_panes = "A4"


