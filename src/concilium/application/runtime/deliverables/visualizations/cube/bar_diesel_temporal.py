"""bar_diesel_temporal.png — Consumo de combustível no tempo (kL, por WOM)."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from ._common import COLORS, init_mpl, safe_close_mpl


def _fallback_horas_semana(canonical) -> float:
    """Calcula horas/semana do regime de trabalho do projeto (0.0 se ausente ou inválido)."""
    regime = getattr(getattr(canonical, "projeto", None), "regime_trabalho", None)
    return float((getattr(regime, "horas_dia", 0) or 0) * (getattr(regime, "dias_semana", 0) or 0))


def _fallback_litros_atividade(sa, equipe, horas_semana: float, liters: dict[str, float]) -> None:
    """Acumula (in-place) os litros/semana de uma atividade agendada, por semana ISO."""
    for semana_iso, d in (getattr(sa, "distribuicao_semanal", None) or {}).items():
        n_eq = float(getattr(d, "num_equipes", 0) or 0)
        if n_eq <= 0:
            continue
        eficiencia = float(getattr(d, "eficiencia", 1.0) or 1.0)
        for equip in equipe.equipamentos:
            consumo_lh = float(getattr(equip, "consumo_litros_hora", 0.0) or 0.0)
            if consumo_lh <= 0:
                continue
            litros = consumo_lh * float(getattr(equip, "num_unidades", 0) or 0) * horas_semana * n_eq * eficiencia
            liters[str(semana_iso)] += litros


def _fallback_liters_from_canonical(canonical) -> dict[str, float]:
    """Fallback físico: calcula litros/semana a partir de equipes e cronograma."""
    cron = getattr(canonical, "cronograma", None)
    equipes = getattr(canonical, "equipes_diretas", None) or []
    if not cron or not getattr(cron, "scheduled_activities", None) or not equipes:
        return {}
    horas_semana = _fallback_horas_semana(canonical)
    if horas_semana <= 0:
        return {}

    by_item = {e.item_id: e for e in equipes}
    liters: dict[str, float] = defaultdict(float)
    for sa in cron.scheduled_activities:
        equipe = by_item.get(sa.activity_id)
        if equipe is None:
            continue
        _fallback_litros_atividade(sa, equipe, horas_semana, liters)
    return dict(liters)


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


def _week_months_contribution(week_iso: str, fuel_total_liters: float) -> dict[tuple[str, int], float]:
    """Split weekly fuel uniformly across calendar days, grouping by (month_bucket, wom_index).

    Weeks spanning month boundaries are split proportionally by day count.
    WOM index follows calendar month weeks: day 1 until the first Saturday is WOM#1,
    then weeks run Sunday-Saturday. This keeps partial WOM#1 and WOM#5 when a month
    starts or ends mid-week.
    """
    year_str, week_str = week_iso.split("-W", 1)
    monday = date.fromisocalendar(int(year_str), int(week_str), 1)
    per_day = fuel_total_liters / 7.0
    contributions: dict[tuple[str, int], float] = {}
    for d in range(7):
        day = monday + timedelta(days=d)
        bucket = f"{day.year:04d}-{day.month:02d}"
        wom = _week_of_month_index(day)
        key = (bucket, wom)
        contributions[key] = contributions.get(key, 0.0) + per_day
    return contributions


def _build_week_liters(canonical, cubo) -> dict[str, float]:
    """Agrega o consumo de diesel (litros) por semana ISO, a partir do cubo (ou fallback físico)."""
    week_liters: dict[str, float] = defaultdict(float)
    for celula in getattr(cubo, "celulas", None) or []:
        fuel_l = float(getattr(celula, "consumo_diesel_L", 0.0) or 0.0)
        if fuel_l > 0:
            week_liters[str(celula.semana_iso)] += fuel_l

    # Se o cubo monetário não carregou célula diesel (ex.: combustível embutido em equipamento),
    # preserva a leitura física em litros via canonical (equipes × cronograma).
    if not week_liters:
        week_liters.update(_fallback_liters_from_canonical(canonical))
    return week_liters


def _build_monthly_wom(week_liters: dict[str, float]) -> dict[str, dict[int, float]]:
    """Agrega litros/semana em litros por (mês, índice de semana do mês), dividindo semanas que cruzam meses."""
    monthly_wom: dict[str, dict[int, float]] = defaultdict(lambda: defaultdict(float))
    for semana_iso, liters in week_liters.items():
        if liters <= 0:  # pragma: no branch
            continue
        for (bucket, wom), portion in _week_months_contribution(semana_iso, liters).items():
            monthly_wom[bucket][wom] += portion
    return monthly_wom


def _plot_wom_stacked_bars(
    ax, x: list[int], periodos: list[str], monthly_wom: dict[str, dict[int, float]], all_woms: list[int]
) -> None:
    """Desenha as barras empilhadas por WOM (semana do mês), com rótulos de valor, sobre `ax`."""
    baseline = [0.0] * len(periodos)
    for wom_idx in all_woms:
        values = [monthly_wom[per].get(wom_idx, 0.0) / 1000.0 for per in periodos]
        label = f"WOM #{wom_idx}"
        bars = ax.bar(
            x,
            values,
            bottom=baseline,
            color=COLORS[(wom_idx - 1) % len(COLORS)],
            alpha=0.85,
            label=label,
            width=0.7,
        )
        for bar, val in zip(bars, values, strict=False):
            if val > 0:
                mid_y = bar.get_y() + bar.get_height() / 2
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    mid_y,
                    f"{val:.0f}",
                    ha="center",
                    va="center",
                    fontsize=7,
                    color="white",
                    fontweight="bold",
                )
        baseline = [b + v for b, v in zip(baseline, values, strict=False)]


def build(canonical, cubo) -> bytes | None:
    try:
        plt, fig_to_bytes = init_mpl()
    except ImportError:
        return None
    try:
        # Aggregate fuel consumption by (month, week-of-month index), splitting cross-month weeks.
        week_liters = _build_week_liters(canonical, cubo)
        monthly_wom = _build_monthly_wom(week_liters)

        if not monthly_wom:
            return None

        periodos = sorted(monthly_wom.keys())
        # WOM indices present across all months (calendar weeks; partial WOM#1/WOM#5 can appear)
        all_woms = sorted({w for md in monthly_wom.values() for w in md})

        x = list(range(len(periodos)))
        fig_w = max(8, len(periodos) * 0.9 + 2)
        fig, ax = plt.subplots(figsize=(fig_w, 5))

        _plot_wom_stacked_bars(ax, x, periodos, monthly_wom, all_woms)

        ax.set_title("Consumo de Combustível no Tempo (por Semana do Mês)", fontsize=13, fontweight="bold")
        ax.set_ylabel("Consumo (kL)", fontsize=9)
        ax.set_xlabel("Mes", fontsize=9)
        ax.set_xticks(x)
        ax.set_xticklabels(periodos, rotation=45, ha="right", fontsize=8)
        ax.legend(loc="upper right", fontsize=8, title="Semana do Mes", title_fontsize=8)
        ax.grid(axis="y", alpha=0.3)
        fig.tight_layout()
        return fig_to_bytes(fig)
    except Exception:
        safe_close_mpl()
        return None
