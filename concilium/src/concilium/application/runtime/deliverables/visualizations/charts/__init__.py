"""Runtime charts package — one leaf module per PNG artifact."""

from __future__ import annotations

from .dependencia_eap import build_dependencia_eap
from .fluxo_financeiro import build_fluxo_financeiro
from .gantt import build_gantt
from .histogramas import build_hist_equipamentos, build_hist_mao_obra
from .painel_equilibrio import build_painel_equilibrio


def build_all(graficos: dict) -> dict[str, bytes]:
    """Build all runtime chart PNGs from the GRAFICOS section of a relatorio."""
    result: dict[str, bytes] = {}
    cronograma = graficos.get("cronograma") or {}

    builders = [
        ("hist_equipamentos.png", lambda: build_hist_equipamentos(graficos)),
        ("hist_mao_obra.png", lambda: build_hist_mao_obra(graficos)),
        ("gantt_cronograma.png", lambda: build_gantt(cronograma)),
        ("fluxo_financeiro.png", lambda: build_fluxo_financeiro(graficos.get("financeiro") or {})),
        ("painel_equilibrio.png", lambda: build_painel_equilibrio(graficos.get("painel_equilibrio") or {})),
        ("dependencia_eap.png", lambda: build_dependencia_eap(cronograma)),
    ]
    for fname, builder in builders:
        try:
            png = builder()
            if png:
                result[fname] = png
        except Exception:
            pass
    return result


__all__ = [
    "build_all",
    "build_hist_equipamentos",
    "build_hist_mao_obra",
    "build_gantt",
    "build_fluxo_financeiro",
    "build_painel_equilibrio",
    "build_dependencia_eap",
]
