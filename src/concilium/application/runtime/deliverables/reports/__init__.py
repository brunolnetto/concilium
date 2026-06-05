"""Submódulo de reports de deliverables."""

from .financial_report_markdown import render_financial_report_markdown
from .memorial_bdi_markdown import render_memorial_bdi_markdown
from .pdf_renderer import render_markdown_pdf

__all__ = [
    "render_financial_report_markdown",
    "render_markdown_pdf",
    "render_memorial_bdi_markdown",
]
