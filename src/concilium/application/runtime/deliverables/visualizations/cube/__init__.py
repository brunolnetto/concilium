"""Analytic cube charts package — one leaf module per face/PNG artifact."""

from __future__ import annotations

from . import (
    area_tempo_componente,
    bar_atividade_componente,
    bar_categoria_componente,
    bar_diesel_temporal,
    bar_direto_atividade_temporal,
    bar_tempo_natureza,
    linha_recursos_tempo,
    pool_ciclo_vida,
    pool_custo_estado,
    pool_economia,
    pool_utilizacao_temporal,
    scurve_custo,
)
from ._relatorio_fallback import build_relatorio_fallback

# (module, filename)
_FACE_MODULES = [
    # ── Cubo analítico (ADR-069) ─────────────────────────────────────────
    (bar_tempo_natureza, "bar_tempo_natureza.png"),
    (area_tempo_componente, "area_tempo_componente.png"),
    (bar_categoria_componente, "bar_categoria_componente.png"),
    (bar_atividade_componente, "bar_atividade_componente.png"),
    (bar_direto_atividade_temporal, "bar_direto_atividade_temporal.png"),
    (bar_diesel_temporal, "bar_diesel_temporal.png"),
    (scurve_custo, "scurve_custo.png"),
    (linha_recursos_tempo, "linha_recursos_tempo.png"),
    # ── Cubo pool instancial (ADR-086) ────────────────────────────────────
    (pool_utilizacao_temporal, "pool_utilizacao_temporal.png"),
    (pool_ciclo_vida, "pool_ciclo_vida.png"),
    (pool_custo_estado, "pool_custo_estado.png"),
    (pool_economia, "pool_economia.png"),
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
    for module, fname in _FACE_MODULES:
        try:
            # linha_recursos_tempo accepts an optional graficos_dict for MO enrichment
            if module is linha_recursos_tempo:
                png = module.build(canonical, cubo, graficos_dict)
            else:
                png = module.build(canonical, cubo)
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
