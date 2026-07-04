"""bar_direto_atividade_temporal.png — Custo direto no tempo com breakdown por atividade."""

from __future__ import annotations

from collections import defaultdict

from concilium.application.services.analytics.cube_projection_views import _iter_scaled_cubo_cells

from ._common import COLORS, init_mpl, safe_close_mpl


def _bucket_from_week_iso(week_iso: str) -> str:
    from datetime import date

    year_str, week_str = week_iso.split("-W", 1)
    anchor = date.fromisocalendar(int(year_str), int(week_str), 1)
    return f"{anchor.year:04d}-{anchor.month:02d}"


def build(canonical, cubo) -> bytes | None:
    try:
        plt, fig_to_bytes = init_mpl()
    except ImportError:
        return None

    try:
        by_period_activity: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        total_by_activity: dict[str, float] = defaultdict(float)

        for celula, valor_cell in _iter_scaled_cubo_cells(canonical, cubo):
            if str(getattr(celula, "componente_bdi", "")) != "custo_direto":
                continue
            atividade_id = str(getattr(celula, "atividade_id", "") or "")
            if not atividade_id:
                continue
            bucket = _bucket_from_week_iso(str(celula.semana_iso))
            value = float(valor_cell or 0.0)
            by_period_activity[bucket][atividade_id] += value
            total_by_activity[atividade_id] += value

        periodos = sorted(by_period_activity.keys())
        if not periodos:
            return None

        top_atividades = sorted(total_by_activity, key=lambda a: -total_by_activity[a])[:8]
        if not top_atividades:  # pragma: no branch
            return None

        x = list(range(len(periodos)))
        baseline = [0.0] * len(periodos)
        scale = 1e6

        fig, ax = plt.subplots(figsize=(max(10, len(periodos) * 0.8 + 2), 6))
        for idx, atividade_id in enumerate(top_atividades):
            vals = [by_period_activity[p].get(atividade_id, 0.0) / scale for p in periodos]
            ax.bar(
                x,
                vals,
                bottom=baseline,
                color=COLORS[idx % len(COLORS)],
                alpha=0.88,
                width=0.72,
                label=atividade_id,
            )
            baseline = [b + v for b, v in zip(baseline, vals, strict=False)]

        ax.set_xticks(x)
        ax.set_xticklabels(periodos, rotation=45, ha="right", fontsize=8)
        ax.set_ylabel("Custo direto (R$ Mi)", fontsize=9)
        ax.set_xlabel("Mês", fontsize=9)
        ax.set_title("Custo Direto ao Longo do Tempo (breakdown por atividade)", fontsize=11, fontweight="bold")
        ax.grid(axis="y", alpha=0.3)
        ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize=8, title="Atividades")

        total_plot = sum(total_by_activity[a] for a in top_atividades)
        total_all = sum(total_by_activity.values())
        cobertura = (total_plot / total_all * 100.0) if total_all > 0 else 0.0
        fig.text(
            0.01,
            0.01,
            f"Top {len(top_atividades)} atividades cobrem {cobertura:.1f}% do custo direto total.",
            fontsize=7.5,
            color="#555",
            ha="left",
        )

        fig.tight_layout(rect=(0, 0.06, 0.84, 1))
        return fig_to_bytes(fig)
    except Exception:
        safe_close_mpl()
        return None
