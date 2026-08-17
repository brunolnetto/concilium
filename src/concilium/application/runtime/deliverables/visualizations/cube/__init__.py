"""Analytic cube charts package — one leaf module per face/PNG artifact."""

from __future__ import annotations

from collections.abc import Callable

from . import (
    area_tempo_componente,
    bar_atividade_componente,
    bar_categoria_componente,
    bar_combustivel_tipo_temporal,
    bar_diesel_temporal,
    bar_direto_atividade_temporal,
    bar_tempo_direto_categoria,
    bar_tempo_indireto_categoria,
    bar_tempo_natureza,
    estoque_temporal,
    linha_recursos_tempo,
    pool_ciclo_vida,
    pool_custo_estado,
    pool_economia,
    pool_utilizacao_temporal,
    scurve_custo,
)
from ._relatorio_fallback import build_relatorio_fallback

# (build_fn, filename, aceita_graficos_dict)
# linha_recursos_tempo aceita um graficos_dict opcional para enriquecimento de MO.
_FACE_BUILDERS: list[tuple[Callable[..., bytes | None], str, bool]] = [
    # ── Cubo analítico (ADR-069) ─────────────────────────────────────────
    (bar_tempo_natureza.build, "bar_tempo_natureza.png", False),
    (bar_tempo_direto_categoria.build, "bar_tempo_direto_categoria.png", False),
    (bar_tempo_indireto_categoria.build, "bar_tempo_indireto_categoria.png", False),
    (area_tempo_componente.build, "area_tempo_componente.png", False),
    (bar_categoria_componente.build, "bar_categoria_componente.png", False),
    (bar_atividade_componente.build, "bar_atividade_componente.png", False),
    (bar_direto_atividade_temporal.build, "bar_direto_atividade_temporal.png", False),
    (bar_diesel_temporal.build, "bar_diesel_temporal.png", False),
    (bar_combustivel_tipo_temporal.build, "bar_combustivel_tipo_temporal.png", False),
    (scurve_custo.build, "scurve_custo.png", False),
    (linha_recursos_tempo.build, "linha_recursos_tempo.png", True),
    # ── Cubo pool instancial (ADR-086) ────────────────────────────────────
    (pool_utilizacao_temporal.build, "pool_utilizacao_temporal.png", False),
    (pool_ciclo_vida.build, "pool_ciclo_vida.png", False),
    (pool_custo_estado.build, "pool_custo_estado.png", False),
    (pool_economia.build, "pool_economia.png", False),
    # ── Cubo estoque consumível (ADR-128 F6 / ADR-184) ────────────────────
    (estoque_temporal.build, "estoque_temporal.png", False),
]


def _resolve_cubo(canonical):
    cubo = getattr(canonical, "cubo_analitico", None)
    if cubo is not None:
        return cubo
    try:
        from concilium.domain.services.analytics.cubo_analitico_builder import CuboAnaliticoBuilder

        return CuboAnaliticoBuilder().build(canonical)
    except Exception:
        return None


def _build_graficos_dict(relatorio):
    if isinstance(relatorio, dict):
        return relatorio.get("GRAFICOS", {})
    return {}


def _build_faces(canonical, cubo, graficos_dict):
    result: dict[str, bytes] = {}
    for build_fn, fname, aceita_graficos in _FACE_BUILDERS:
        try:
            png = build_fn(canonical, cubo, graficos_dict) if aceita_graficos else build_fn(canonical, cubo)
            if png:
                result[fname] = png
        except Exception:
            pass
    return result


def build_all(
    relatorio: dict | None = None,
    canonical: object | None = None,
) -> dict[str, bytes]:
    """Build all analytic cube PNGs.

    Each face delegates to its own leaf module.  Falls back to relatorio-based
    charts when the canonical model is unavailable or all projections are empty.
    """
    if canonical is None:
        return {}
    cubo = _resolve_cubo(canonical)
    if cubo is None:
        return {}
    graficos_dict = _build_graficos_dict(relatorio)
    result = _build_faces(canonical, cubo, graficos_dict)
    if not result:
        result.update(build_relatorio_fallback(relatorio or {}))
    return result


__all__ = ["build_all"]
