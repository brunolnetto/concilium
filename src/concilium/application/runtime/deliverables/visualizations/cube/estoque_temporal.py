"""estoque_temporal.png — Nível de Estoque de Recursos Consumíveis no Tempo (ADR-128 F6).

Uma linha por recurso restrito (ADR-128 D1), estoque médio por período. Linha zero
de referência: abaixo dela é déficit de fato (mesmo quando reparado por atraso/
provisionamento — ADR-151 — a projeção reconstruída aqui já reflete a correção,
ver `cubo_estoque_consumivel_builder._to_replenishable_resource`, ADR-184).
"""

from __future__ import annotations

from ._common import COLORS, init_mpl


def _resolve_estoque_temporal_rows(canonical) -> tuple[dict, list] | None:
    try:
        from concilium.application.services.analytics.cubo_estoque_consumivel_projection import (
            resolve_cubo_estoque_consumivel_projection,
        )

        proj = resolve_cubo_estoque_consumivel_projection(canonical, face="estoque_temporal", granularidade="mes")
    except Exception:
        return None

    rows = proj.get("rows") or []
    if not rows:
        return None
    return proj, rows


def _series_por_recurso(rows: list) -> dict[str, tuple[list[str], list[float]]]:
    por_recurso: dict[str, tuple[list[str], list[float]]] = {}
    agrupado: dict[str, list[tuple[str, float]]] = {}
    for row in rows:
        rid = str(row.get("resource_id", "") or "")
        periodo = str(row.get("periodo", "") or "")
        nivel = float(row.get("estoque_nivel_medio", 0.0) or 0.0)
        agrupado.setdefault(rid, []).append((periodo, nivel))
    for rid, pontos in agrupado.items():
        pontos.sort(key=lambda p: p[0])
        por_recurso[rid] = ([p[0] for p in pontos], [p[1] for p in pontos])
    return por_recurso


def _render_estoque_temporal_figure(plt, proj: dict, rows: list):
    por_recurso = _series_por_recurso(rows)
    fig, ax = plt.subplots(figsize=(12, 6))

    for i, (rid, (periodos, niveis)) in enumerate(sorted(por_recurso.items())):
        ax.plot(periodos, niveis, marker="o", markersize=3, linewidth=1.5, color=COLORS[i % len(COLORS)], label=rid)

    ax.axhline(0, color="#888", linewidth=0.8, linestyle="--")
    ax.set_ylabel("Estoque médio (unidade do recurso)", fontsize=9)
    ax.set_xlabel("Período", fontsize=9)
    ax.set_title("Estoque de Recursos Consumíveis no Tempo", fontsize=11, fontweight="bold")
    ax.tick_params(axis="x", rotation=45, labelsize=8)
    ax.grid(axis="y", alpha=0.3)
    ax.legend(fontsize=8, loc="best")

    totais = proj.get("totais") or {}
    consumo_total = totais.get("consumo_total", 0.0)
    producao_total = totais.get("producao_total", 0.0)
    fig.text(
        0.01,
        0.01,
        f"Consumo total: {consumo_total:,.2f}  |  Produção interna total: {producao_total:,.2f}",
        fontsize=8,
        color="#555",
        ha="left",
    )

    fig.tight_layout(rect=(0, 0.06, 1, 1))
    return fig


def build(canonical, cubo=None) -> bytes | None:
    resolved = _resolve_estoque_temporal_rows(canonical)
    if resolved is None:
        return None
    proj, rows = resolved

    try:
        plt, fig_to_bytes = init_mpl()
    except ImportError:
        return None

    try:
        fig = _render_estoque_temporal_figure(plt, proj, rows)
        return fig_to_bytes(fig)
    except Exception:
        plt.close("all")
        return None
