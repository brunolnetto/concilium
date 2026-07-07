"""pool_utilizacao_temporal.png — Utilização do Pool de Recursos no Tempo (prod / ocioso / off).

Mostra a distribuição de slot-semanas por estado ao longo do projeto. Linha divisória
entre o pool mobilizado (prod + idle) e o desmobilizado (off) evidencia a estratégia
de mobilização tardia e desmobilização antecipada do ADR-085/086.
"""

from __future__ import annotations

import math

from ..chart_markdown_support import weekly_to_monthly_labels
from ._common import apply_monthly_ticks, init_mpl, is_weekly_labels

_COLOR_PROD = "#1a6e3c"  # verde escuro — trabalho produtivo
_COLOR_IDLE = "#e8a030"  # âmbar — ocioso (custo de MO/EQ sem operação)
_COLOR_OFF = "#c8c8c8"  # cinza — desmobilizado (custo zero)
_COLOR_MOB = "#155a9c"  # azul — eventos de mobilização
_COLOR_DEMOB = "#8a2e0f"  # ferrugem — eventos de desmobilização


def _sparse_series(values: list[int]) -> list[float]:
    """Mantém apenas pontos >0 para evitar linha contínua em zero no eixo temporal."""
    return [float(v) if v > 0 else math.nan for v in values]


def _resolve_pool_utilizacao_proj(canonical) -> dict | None:
    try:
        from concilium.application.services.analytics.cubo_pool_projection import resolve_cubo_pool_projection

        proj = resolve_cubo_pool_projection(canonical, face="utilizacao_temporal", granularidade="mes", top_n=300)
    except Exception:
        return None

    rows = proj.get("rows") or []
    if not rows:
        return None
    # Só renderiza se houver instâncias de pool
    totais = proj.get("totais", {})
    if not (totais.get("semanas_por_estado", {}).get("prod", 0) or 0):
        return None
    return proj


def _int_column(rows: list, key: str) -> list[int]:
    return [int(r.get(key, 0) or 0) for r in rows]


def _pool_utilizacao_series(rows: list) -> tuple[list[str], list[int], list[int], list[int], list[int], list[int]]:
    periods = [str(r.get("periodo", "")) for r in rows]
    prod = _int_column(rows, "prod")
    idle = _int_column(rows, "idle")
    off = _int_column(rows, "off")
    mob = _int_column(rows, "mob")
    demob = _int_column(rows, "demob")
    return periods, prod, idle, off, mob, demob


def _draw_pool_utilizacao_bars(ax, x: list[int], prod: list[int], idle: list[int], off: list[int]) -> None:
    bottom_idle = prod
    bottom_off = [p + i for p, i in zip(prod, idle, strict=False)]

    ax.bar(x, prod, color=_COLOR_PROD, alpha=0.85, label="Produtivo")
    ax.bar(x, idle, bottom=bottom_idle, color=_COLOR_IDLE, alpha=0.85, label="Ocioso (CLT+EQ)")
    ax.bar(x, off, bottom=bottom_off, color=_COLOR_OFF, alpha=0.65, label="Desmobilizado (off)")


def _draw_pool_utilizacao_events(ax, x: list[int], mob: list[int], demob: list[int]) -> None:
    if any(mob):
        ax.plot(
            x,
            _sparse_series(mob),
            color=_COLOR_MOB,
            marker="o",
            linewidth=1.5,
            linestyle="--",
            label="MOB (eventos)",
        )
    if any(demob):
        ax.plot(
            x,
            _sparse_series(demob),
            color=_COLOR_DEMOB,
            marker="s",
            linewidth=1.5,
            linestyle=":",
            label="DESMOB (eventos)",
        )


def _finalize_pool_utilizacao_axes(fig, ax, periods: list[str], x: list[int], proj: dict) -> None:
    apply_monthly_ticks(ax, periods, weekly_to_monthly_labels)
    if not is_weekly_labels(periods):
        ax.set_xticks(x)
        ax.set_xticklabels(periods, rotation=45, ha="right", fontsize=8)

    ax.set_ylabel("Slot-semanas", fontsize=10)
    ax.set_xlabel("Período", fontsize=10)
    ax.set_title("Utilização do Pool de Recursos no Tempo\n(slot-semanas por estado)", fontsize=12, fontweight="bold")
    ax.legend(fontsize=9, loc="upper left", bbox_to_anchor=(1.01, 1.0), frameon=False)
    ax.grid(axis="y", alpha=0.3)

    # Narrativa como anotação
    narrativa = proj.get("narrativa") or []
    if narrativa:
        fig.text(0.01, 0.01, narrativa[0], fontsize=7.5, color="#555", ha="left", wrap=True)
    ax.text(
        0.99,
        0.01,
        "MOB/DESMOB = contagem de eventos no período; Desmobilizado (off) = estado de slot sem contrato ativo.",
        fontsize=7.2,
        color="#555",
        ha="right",
        va="bottom",
        transform=ax.transAxes,
        wrap=True,
    )


def build(canonical, cubo=None) -> bytes | None:
    proj = _resolve_pool_utilizacao_proj(canonical)
    if proj is None:
        return None

    try:
        plt, fig_to_bytes = init_mpl()
    except ImportError:
        return None

    try:
        rows = proj.get("rows") or []
        periods, prod, idle, off, mob, demob = _pool_utilizacao_series(rows)
        x = list(range(len(periods)))

        fig, ax = plt.subplots(figsize=(13, 5))

        _draw_pool_utilizacao_bars(ax, x, prod, idle, off)
        _draw_pool_utilizacao_events(ax, x, mob, demob)
        _finalize_pool_utilizacao_axes(fig, ax, periods, x, proj)

        fig.tight_layout(rect=(0, 0.08, 0.86, 1))
        return fig_to_bytes(fig)
    except Exception:
        plt.close("all")
        return None
