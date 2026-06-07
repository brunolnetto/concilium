"""pool_utilizacao_temporal.png — Utilização do Pool de Recursos no Tempo (prod / ocioso / off).

Mostra a distribuição de slot-semanas por estado ao longo do projeto. Linha divisória
entre o pool mobilizado (prod + idle) e o desmobilizado (off) evidencia a estratégia
de mobilização tardia e desmobilização antecipada do ADR-085/086.
"""

from __future__ import annotations

from ..chart_markdown_support import weekly_to_monthly_labels
from ._common import apply_monthly_ticks, init_mpl, is_weekly_labels

_COLOR_PROD = "#1a6e3c"  # verde escuro — trabalho produtivo
_COLOR_IDLE = "#e8a030"  # âmbar — ocioso (custo de MO/EQ sem operação)
_COLOR_OFF = "#c8c8c8"  # cinza — desmobilizado (custo zero)


def build(canonical, cubo=None) -> bytes | None:
    try:
        from concilium.application.services.cubo_pool_projection import resolve_cubo_pool_projection

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

    try:
        plt, fig_to_bytes = init_mpl()
    except ImportError:
        return None

    try:
        periods = [str(r.get("periodo", "")) for r in rows]
        prod = [int(r.get("prod", 0) or 0) for r in rows]
        idle = [int(r.get("idle", 0) or 0) for r in rows]
        off = [int(r.get("off", 0) or 0) for r in rows]
        x = list(range(len(periods)))

        fig, ax = plt.subplots(figsize=(13, 5))

        bottom_idle = prod
        bottom_off = [p + i for p, i in zip(prod, idle)]

        ax.bar(x, prod, color=_COLOR_PROD, alpha=0.85, label="Produtivo")
        ax.bar(x, idle, bottom=bottom_idle, color=_COLOR_IDLE, alpha=0.85, label="Ocioso (CLT+EQ)")
        ax.bar(x, off, bottom=bottom_off, color=_COLOR_OFF, alpha=0.65, label="Desmobilizado (off)")

        apply_monthly_ticks(ax, periods, weekly_to_monthly_labels)
        if not is_weekly_labels(periods):
            ax.set_xticks(x)
            ax.set_xticklabels(periods, rotation=45, ha="right", fontsize=8)

        ax.set_ylabel("Slot-semanas", fontsize=10)
        ax.set_xlabel("Período", fontsize=10)
        ax.set_title(
            "Utilização do Pool de Recursos no Tempo\n(slot-semanas por estado)", fontsize=12, fontweight="bold"
        )
        ax.legend(fontsize=9, loc="upper left", bbox_to_anchor=(1.01, 1.0), frameon=False)
        ax.grid(axis="y", alpha=0.3)

        # Narrativa como anotação
        narrativa = proj.get("narrativa") or []
        if narrativa:
            fig.text(0.01, 0.01, narrativa[0], fontsize=7.5, color="#555", ha="left", wrap=True)

        fig.tight_layout(rect=(0, 0.08, 0.86, 1))
        return fig_to_bytes(fig)
    except Exception:
        plt.close("all")
        return None
