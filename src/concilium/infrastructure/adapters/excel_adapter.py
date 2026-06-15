"""Backward-compatibility shim — conteúdo movido para adapters/excel/.

Importação pública canônica (continua funcionando):
    from concilium.infrastructure.adapters.excel_adapter import ExcelRenderer
"""

from .excel import ExcelRenderer, render_excel_report  # noqa: F401
from .excel.styles import _C, _fill, _font, _border, _align, _money, _label  # noqa: F401
from .excel.helpers import coerce_to_cell_value  # noqa: F401
from .excel.sheets.operacional import render_planejamento_ml  # noqa: F401

__all__ = [
    "ExcelRenderer",
    "render_excel_report",
    "coerce_to_cell_value",
    "render_planejamento_ml",
]
