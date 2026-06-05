"""ExtraÃ§Ã£o de dados de referÃªncia a partir de planilhas Excel."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _get_val_near_label(ws: Any, label: str, col_offset: int = 1, max_row: int = 100, max_col: int = 10) -> Any:
    for row in ws.iter_rows(max_row=max_row, max_col=max_col):
        for cell in row:
            if cell.value and isinstance(cell.value, str) and label.upper() in cell.value.upper():
                target = ws.cell(row=cell.row, column=cell.column + col_offset)
                if target.value is not None:
                    return target.value
    return None


def _extract_resultado(wb, sheet_names: list) -> dict:
    res_sheet = next((s for s in sheet_names if "RESULTADO" in s.upper()), None)
    if not res_sheet:
        return {}
    ws = wb[res_sheet]
    return {
        "custo_direto_total": _get_val_near_label(ws, "TOTAL DIRETO", 2) or _get_val_near_label(ws, "TOTAL DIRETO", 3),
        "custo_indireto_total": _get_val_near_label(ws, "TOTAL INDIRETO", 2)
        or _get_val_near_label(ws, "TOTAL INDIRETO", 3),
        "preco_venda_total": _get_val_near_label(ws, "PRECO DE VENDA TOTAL", 2)
        or _get_val_near_label(ws, "PRECO DE VENDA TOTAL", 3),
        "lucro_liquido": _get_val_near_label(ws, "RESULTADO", 1),
    }


def _extract_bdi(wb, sheet_names: list) -> dict:
    bdi_sheet = next((s for s in sheet_names if "BDI" in s.upper()), None)
    if not bdi_sheet:
        return {}
    ws = wb[bdi_sheet]
    return {
        "mao_de_obra": {
            "ac": _get_val_near_label(ws, "Administracao Central", 1),
            "df": _get_val_near_label(ws, "Despesas Financeiras", 1),
            "r": _get_val_near_label(ws, "Garantia / Risco", 1),
            "lucro": _get_val_near_label(ws, "Lucro", 1),
            "tributos_total": _get_val_near_label(ws, "Tributos (soma)", 1),
            "bdi_total": _get_val_near_label(ws, "Total do BDI", 1),
        },
        "materiais": {
            "ac": _get_val_near_label(ws, "Administracao Central", 5),
            "lucro": _get_val_near_label(ws, "Lucro", 5),
            "bdi_total": _get_val_near_label(ws, "Total do BDI", 5),
        },
    }


def _extract_indiretos(wb, sheet_names: list) -> dict:
    result: dict = {}
    for cat in ("ADM", "TOP", "LAB", "QSMS", "MOB"):
        sheet = next((s for s in sheet_names if cat == s.upper() or f" {cat}" in s.upper()), None)
        if not sheet:
            continue
        ws = wb[sheet]
        result[cat] = {
            "custo_fixo_mensal_total": (
                _get_val_near_label(ws, "CUSTO FIXO MENSAL", 2) or _get_val_near_label(ws, "CUSTO FIXO MENSAL", 1)
            ),
            "mao_de_obra_mensal": (
                _get_val_near_label(ws, "MAO DE OBRA", 2) or _get_val_near_label(ws, "MO DE OBRA", 2)
            ),
        }
    return result


def _extract_eap_col_map(ws) -> dict:
    for _i, row in enumerate(ws.iter_rows(max_row=15, values_only=True), 1):
        row_vals = [str(c).upper().strip() if c else "" for c in row]
        if any(k in row_vals for k in ("ITEM", "CODIGO", "DESCRICAO")):
            return {val: j for j, val in enumerate(row_vals)}
    return {}


def extract_reference_data(excel_path: Path | str) -> dict[str, Any]:
    """Extrai resultado, BDI, indiretos e EAP de uma planilha Excel de referencia."""
    import openpyxl

    excel_path = Path(excel_path)
    wb = openpyxl.load_workbook(excel_path, data_only=True, read_only=True)
    sheet_names = wb.sheetnames

    data: dict = {
        "resultado": _extract_resultado(wb, sheet_names),
        "bdi": _extract_bdi(wb, sheet_names),
        "indiretos_detalhamento": _extract_indiretos(wb, sheet_names),
        "eap": [],
    }

    orc_sheet = next((s for s in sheet_names if "ABC" == s.upper() or "CURVA ABC" in s.upper()), None)
    if not orc_sheet:
        orc_sheet = next(
            (s for s in sheet_names if "OR" in s.upper() and ("MENTO" in s.upper() or "PLAN" in s.upper())), None
        )

    if orc_sheet:
        ws = wb[orc_sheet]
        _extract_eap_col_map(ws)

    wb.close()
    return data
