"""Excel adapter — abas MEMORIAL — render_memorial_mao_obra."""

from __future__ import annotations

from typing import Any

from openpyxl import Workbook

from concilium.domain.models.canonical import CanonicalModel

from ...styles import (
    _C,
    _align,
    _auto_fit_columns,
    _border,
    _fill,
    _font,
    _header_row,
    _set_col_widths,
    _title_row,
)


def _xl_memorial_mao_obra_agg(canonical: CanonicalModel) -> dict[str, dict[str, Any]]:
    """Agrega mão de obra por funcao_id a partir das equipes diretas."""
    agg: dict[str, dict[str, Any]] = {}
    for eq in canonical.equipes_diretas or []:
        for f in eq.funcoes or []:
            key = str(f.funcao_id)
            rec = agg.setdefault(
                key,
                {
                    "descricao": f.descricao or key,
                    "papel": getattr(f, "papel", "direto") or "direto",
                    "qtd": 0.0,
                    "custo": float(getattr(f, "custo_mensal_unitario", 0.0) or 0.0),
                },
            )
            rec["qtd"] += float(getattr(f, "num_pessoas", 0.0) or 0.0) * float(
                getattr(eq, "num_equipes_base", 0.0) or 0.0
            )
    return agg


def _xl_memorial_mao_obra_row(ws: Any, row: int, func_id: str, rec: dict[str, Any], fill: Any) -> None:
    vals = [func_id, rec["descricao"], str(rec["papel"]).upper(), rec["qtd"], rec["custo"]]
    for col, val in enumerate(vals, 1):
        cell = ws.cell(row=row, column=col, value=val)
        cell.fill = fill
        cell.border = _border()
        if col == 5:
            cell.number_format = "R$ #,##0.00"
        if col == 4:
            cell.number_format = "0.00"
            cell.alignment = _align("right")


def render_memorial_mao_obra(wb: Workbook, canonical: CanonicalModel) -> None:
    """MEMORIAL.MAO_OBRA — base de mão de obra efetivamente usada no projeto."""
    ws = wb.create_sheet("MEMORIAL.MAO_OBRA")
    _set_col_widths(ws, [22, 32, 12, 14, 16])
    row = 1
    _title_row(ws, row, "MEMORIAL.MAO_OBRA — INSUMOS UTILIZADOS", 5)
    row += 1
    ws.cell(row=row, column=1, value="Fonte: composições de EQUIPE.DIRETO e indiretos por categoria.").font = _font(
        italic=True, size=9
    )
    row += 2
    _header_row(ws, row, ["Funcao ID", "Descricao", "Papel", "Qtd Base", "Custo Mensal Unit."])
    row += 1

    agg = _xl_memorial_mao_obra_agg(canonical)

    fills = [_fill(_C["white"]), _fill(_C["row_alt"])]
    if not agg:
        ws.cell(row=row, column=1, value="Sem dados de mão de obra para memorial.").font = _font(italic=True, size=9)
    for i, (func_id, rec) in enumerate(sorted(agg.items())):
        fill = fills[i % 2]
        _xl_memorial_mao_obra_row(ws, row, func_id, rec, fill)
        row += 1
    _auto_fit_columns(ws)


