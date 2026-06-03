"""Unified PNG generation for runtime deliverable visualizations."""

from __future__ import annotations

from .analytic_cube_png import build_analytic_cube_png_files
from .charts_png import build_chart_png_files


def build_visualization_png_files(relatorio: dict, canonical: object | None = None) -> dict[str, bytes]:
	pngs: dict[str, bytes] = {}
	graficos = relatorio.get("GRAFICOS", {}) if isinstance(relatorio, dict) else {}
	if isinstance(graficos, dict) and graficos:
		pngs.update(build_chart_png_files(graficos))
	pngs.update(build_analytic_cube_png_files(relatorio=relatorio, canonical=canonical))
	return pngs


__all__ = ["build_visualization_png_files"]