"""bar_diesel_temporal.png — Consumo de Diesel no Tempo (barras mensais empilhadas por WOM)."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from ._common import COLORS, init_mpl


def _week_of_month_index(day: date) -> int:
    """Return the month week index using calendar weeks.

    The first week starts on day 1 and ends on the first Saturday on or after
    the first day of the month. From then on, weeks run Sunday-Saturday.
    This preserves partial WOM #1 and WOM #5 when the month begins/ends mid-week.
    """
    first_day = day.replace(day=1)
    first_week_end = first_day + timedelta(days=(5 - first_day.weekday()) % 7)
    if day <= first_week_end:
        return 1
    second_week_start = first_week_end + timedelta(days=1)
    return 2 + ((day - second_week_start).days // 7)


def _week_months_contribution(week_iso: str, diesel_total: float) -> dict[tuple[str, int], float]:
    """Split weekly diesel uniformly across calendar days, grouping by (month_bucket, wom_index).

    Weeks spanning month boundaries are split proportionally by day count.
    WOM index follows calendar month weeks: day 1 until the first Saturday is WOM#1,
    then weeks run Sunday-Saturday. This keeps partial WOM#1 and WOM#5 when a month
    starts or ends mid-week.
    """
    year_str, week_str = week_iso.split("-W", 1)
    monday = date.fromisocalendar(int(year_str), int(week_str), 1)
    per_day = diesel_total / 7.0
    contributions: dict[tuple[str, int], float] = {}
    for d in range(7):
        day = monday + timedelta(days=d)
        bucket = f"{day.year:04d}-{day.month:02d}"
        wom = _week_of_month_index(day)
        key = (bucket, wom)
        contributions[key] = contributions.get(key, 0.0) + per_day
    return contributions


def build(canonical, cubo) -> bytes | None:
    try:
        plt, fig_to_bytes = init_mpl()
    except ImportError:
        return None
    try:
        # Aggregate diesel consumption by (month, week-of-month index), splitting cross-month weeks
        monthly_wom: dict[str, dict[int, float]] = defaultdict(lambda: defaultdict(float))
        for celula in (getattr(cubo, "celulas", None) or []):
            diesel_l = float(getattr(celula, "consumo_diesel_L", 0.0) or 0.0)
            if diesel_l > 0:
                for (bucket, wom), portion in _week_months_contribution(
                    str(celula.semana_iso), diesel_l
                ).items():
                    monthly_wom[bucket][wom] += portion

        if not monthly_wom:
            return None

        periodos = sorted(monthly_wom.keys())
        # WOM indices present across all months (calendar weeks; partial WOM#1/WOM#5 can appear)
        all_woms = sorted({w for md in monthly_wom.values() for w in md})

        x = list(range(len(periodos)))
        fig_w = max(8, len(periodos) * 0.9 + 2)
        fig, ax = plt.subplots(figsize=(fig_w, 5))
        baseline = [0.0] * len(periodos)

        for wom_idx in all_woms:
            values = [monthly_wom[per].get(wom_idx, 0.0) for per in periodos]
            label = f"WOM #{wom_idx}"
            bars = ax.bar(
                x, values, bottom=baseline,
                color=COLORS[(wom_idx - 1) % len(COLORS)],
                alpha=0.85, label=label, width=0.7,
            )
            for bar, val in zip(bars, values):
                if val > 0:
                    mid_y = bar.get_y() + bar.get_height() / 2
                    ax.text(
                        bar.get_x() + bar.get_width() / 2,
                        mid_y,
                        f"{val:.0f}",
                        ha="center", va="center",
                        fontsize=7, color="white", fontweight="bold",
                    )
            baseline = [b + v for b, v in zip(baseline, values)]

        ax.set_title("Consumo de Diesel no Tempo (por Semana do Mes)", fontsize=13, fontweight="bold")
        ax.set_ylabel("Consumo (L)", fontsize=9)
        ax.set_xlabel("Mes", fontsize=9)
        ax.set_xticks(x)
        ax.set_xticklabels(periodos, rotation=45, ha="right", fontsize=8)
        ax.legend(loc="upper right", fontsize=8,
                  title="Semana do Mes", title_fontsize=8)
        ax.grid(axis="y", alpha=0.3)
        fig.tight_layout()
        return fig_to_bytes(fig)
    except Exception:
        try:
            import matplotlib.pyplot as _plt
            _plt.close("all")
        except Exception:
            pass
        return None

