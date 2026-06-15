"""Excel export subpackage — renders CanonicalModel to a multi-sheet .xlsx workbook."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

from openpyxl import Workbook

from concilium.domain.models.canonical import CanonicalModel
from .styles import _auto_fit_columns, _C
from .sheets.operacional import (
    render_diretos,
    render_indiretos_ml,
    render_planejamento_ml,
    render_cronograma,
)
from .sheets.resultado import (
    render_fluxo_caixa,
    render_resultado_ml,
    render_bdi,
    render_diretos_res,
    render_indiretos_res,
    render_cronograma_res,
    render_equilibrio,
    render_referencia,
)
from .sheets.recursos import (
    render_calendario_operacional,
    render_equipe,
    render_equipe_indireto,
)
from .sheets.analise import (
    render_histograma_eq,
    render_histograma_mo,
    render_curva_abc,
    render_s_curve,
)
from .sheets.memorial import (
    render_memorial_bdi,
    render_memorial_mao_obra,
    render_memorial_equipamentos,
    render_memorial_materiais,
    render_memorial_catalogo,
)
from .sheets.graficos import (
    render_graficos,
    render_cubo_comp,
    render_campanha_frota,
)


def _reorder_workbook_tabs(wb: Workbook, preferred_order: list[str]) -> None:
    order_idx = {name: i for i, name in enumerate(preferred_order)}
    wb._sheets.sort(key=lambda ws: (order_idx.get(ws.title, len(preferred_order)), ws.title))


class ExcelRenderer:
    """Renderiza dados canônicos em planilha Excel MendesLobo (15 abas)."""

    def __init__(self, canonical: CanonicalModel):
        self.canonical = canonical
        self.wb = Workbook()
        self.wb.remove(self.wb.active)

    def render(self) -> Workbook:
        """Renderiza as abas na ordem definida e retorna workbook."""
        render_memorial_bdi(self.wb, self.canonical)
        render_memorial_catalogo(self.wb, self.canonical)
        render_memorial_mao_obra(self.wb, self.canonical)
        render_memorial_equipamentos(self.wb, self.canonical)
        render_memorial_materiais(self.wb, self.canonical)
        render_campanha_frota(self.wb, self.canonical)
        render_calendario_operacional(self.wb, self.canonical)
        render_cubo_comp(self.wb, self.canonical)
        render_curva_abc(self.wb, self.canonical)
        render_s_curve(self.wb, self.canonical)
        diretos_total_row = render_diretos(self.wb, self.canonical)
        render_diretos_res(self.wb, self.canonical)
        indiretos_refs = render_indiretos_ml(self.wb, self.canonical)
        render_indiretos_res(self.wb, self.canonical)
        planejamento_total_row = render_planejamento_ml(self.wb, self.canonical)
        render_cronograma(self.wb, self.canonical)
        render_cronograma_res(self.wb, self.canonical)
        render_equipe(self.wb, self.canonical)
        for cat in ("QSMS", "TOP", "LAB", "ADM"):
            render_equipe_indireto(self.wb, self.canonical, cat)
        render_equilibrio(self.wb, self.canonical)
        render_resultado_ml(
            self.wb,
            self.canonical,
            diretos_total_row=diretos_total_row,
            indiretos_refs=indiretos_refs,
            planejamento_total_row=planejamento_total_row,
        )
        render_fluxo_caixa(self.wb, self.canonical)
        render_referencia(self.wb, self.canonical)
        render_histograma_eq(self.wb, self.canonical)
        render_histograma_mo(self.wb, self.canonical)
        # CURVA.ABC já renderizada na posição 2 (acima) — removido condicional duplicado (P1)
        for ws in self.wb.worksheets:
            if ws.title not in {"MEMORIAL.BDI", "CUBO.COMP", "CAMPANHA.FROTA", "PLANEJAMENTO", "RESULTADO"}:
                _auto_fit_columns(ws)

        _reorder_workbook_tabs(
            self.wb,
            [
                "RESULTADO",
                "REFERÊNCIA",
                "EQUILIBRIO",
                "PLANEJAMENTO",
                "CRONOGRAMA.RES",
                "CRONOGRAMA.DET",
                "DIRETOS.RES",
                "DIRETOS.DET",
                "INDIRETOS.RES",
                "INDIRETOS.DET",
                "EQUIPE.DIRETO",
                "EQUIPE.INDIRETO.QSMS",
                "EQUIPE.INDIRETO.TOP",
                "EQUIPE.INDIRETO.LAB",
                "EQUIPE.INDIRETO.ADM",
                "MEMORIAL.CATALOGO",
                "MEMORIAL.BDI",
                "MEMORIAL.MAO_OBRA",
                "MEMORIAL.EQUIPAMENTOS",
                "MEMORIAL.MATERIAIS",
                "CAMPANHA.FROTA",
                "CALENDARIO.OP",
                "CUBO.COMP",
                "ANALISE.CURVA_ABC",
                "ANALISE.S_CURVE",
                "ANALISE.FC_CAIXA",
                "ANALISE.HIST_EQUIP",
                "ANALISE.HIST_MAO_OBRA",
            ],
        )
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
        from .helpers import coerce_to_cell_value
        return coerce_to_cell_value(value)


def render_excel_report(canonical: CanonicalModel) -> bytes:
    """Convenience function: render canonical model to Excel bytes."""
    return ExcelRenderer(canonical).to_bytes()
