"""Módulo de comparação granular de benchmarks (catálogo vs. engine, equipes detalhadas)."""

from .catalog_confronto import analyze_catalog_confronto, consolidate_all
from .equipes_detail import build_equipes_detail
from .granular import build_granular_comparison

__all__ = [
    "build_granular_comparison",
    "build_equipes_detail",
    "analyze_catalog_confronto",
    "consolidate_all",
]
