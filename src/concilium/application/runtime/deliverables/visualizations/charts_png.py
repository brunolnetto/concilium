"""Geracao de visualizacoes PNG de histogramas, cronograma e fluxo financeiro.

Delegates to the charts subpackage - one leaf module per PNG artifact.
"""

from __future__ import annotations

from .charts import build_all as build_chart_png_files

__all__ = ["build_chart_png_files"]
