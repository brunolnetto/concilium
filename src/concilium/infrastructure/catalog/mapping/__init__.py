"""Mapeamento e correção de CPUs no catálogo e referências."""

from .cpu_fixer import fix_referencia_mappings
from .cpu_mapper import apply_cpu_mappings, map_desc
from .equipes_normalizer import normalize_equipes_from_producoes
from .healer import heal_catalog

__all__ = [
    "map_desc",
    "apply_cpu_mappings",
    "fix_referencia_mappings",
    "heal_catalog",
    "normalize_equipes_from_producoes",
]
