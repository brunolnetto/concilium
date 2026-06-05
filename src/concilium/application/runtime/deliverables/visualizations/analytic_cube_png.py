"""Geracao de PNGs do cubo analitico.

Delegates to the cube subpackage - one leaf module per face/PNG artifact.
"""

from __future__ import annotations

from .cube import build_all as build_analytic_cube_png_files

__all__ = ["build_analytic_cube_png_files"]
