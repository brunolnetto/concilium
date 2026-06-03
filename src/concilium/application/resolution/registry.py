"""ATTRIBUTE_REGISTRY — definições canônicas de atributos de CPU (ADR-002).

Cada AttributeDefinition descreve como normalizar um atributo
de entrada do cliente para a forma canônica usada no scoring.

Regras:
- Aliases são mapeados para canonical_name na ingestão.
- normalizer converte valor + unidade_origem para a unidade canônica.
- tolerance_pct define margem para match parcial no scoring.
- tolerance_pct == 0.0 -> somente match exato (para categóricos).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AttributeDefinition:
    """Definição de um atributo canônico."""

    canonical_name: str
    type_: type
    unit: str  # unidade canônica
    aliases: list[str] = field(default_factory=list)  # outros nomes no catálogo
    normalizer: Callable[[Any, str], Any] = field(
        default=lambda x, _: x,
        compare=False,
        hash=False,
        repr=False,
    )
    tolerance_pct: float = 0.0  # margem para match parcial (0.0 = exato)


def _identity(x: Any, _unit: str) -> Any:
    return x


def _mm_to_cm(x: float, src_unit: str) -> float:
    return x / 10.0 if src_unit == "mm" else float(x)


def _str_upper(x: Any, _unit: str) -> str:
    return str(x).upper()


ATTRIBUTE_REGISTRY: dict[str, AttributeDefinition] = {
    "thickness": AttributeDefinition(
        canonical_name="thickness",
        type_=float,
        unit="cm",
        aliases=["espessura", "thickness_mm", "espessura_cm", "thick", "espessura_mm"],
        normalizer=_mm_to_cm,
        tolerance_pct=0.15,
    ),
    "dmt": AttributeDefinition(
        canonical_name="dmt",
        type_=float,
        unit="m",
        aliases=[
            "dmt_min_metros",
            "dmt_max_metros",
            "distancia_media_transporte",
            "dmt_metros",
            "distancia_transporte",
        ],
        normalizer=_identity,
        tolerance_pct=0.20,
    ),
    "compaction_rate": AttributeDefinition(
        canonical_name="compaction_rate",
        type_=float,
        unit="pct",
        aliases=["grau_compactacao", "gc_pct", "proctor_normal"],
        normalizer=_identity,
        tolerance_pct=0.05,
    ),
    "soil_class": AttributeDefinition(
        canonical_name="soil_class",
        type_=str,
        unit="class",
        aliases=["categoria_material", "classe_solo", "cat_material"],
        normalizer=_str_upper,
        tolerance_pct=0.0,
    ),
    "pipe_diameter": AttributeDefinition(
        canonical_name="pipe_diameter",
        type_=float,
        unit="mm",
        aliases=["diametro", "dn", "diametro_nominal", "diametro_mm"],
        normalizer=_identity,
        tolerance_pct=0.05,
    ),
    "depth": AttributeDefinition(
        canonical_name="depth",
        type_=float,
        unit="m",
        aliases=["profundidade", "prof", "profundidade_metros"],
        normalizer=_identity,
        tolerance_pct=0.15,
    ),
}


def resolve_alias(raw_name: str) -> str | None:
    """Retorna o canonical_name correspondente ao alias, ou None se não encontrado."""
    raw_lower = raw_name.lower()
    for canon, attr_def in ATTRIBUTE_REGISTRY.items():
        if raw_lower == canon:
            return canon
        if raw_lower in [a.lower() for a in attr_def.aliases]:
            return canon
    return None


__all__ = ["AttributeDefinition", "ATTRIBUTE_REGISTRY", "resolve_alias"]
