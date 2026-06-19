"""bar_combustivel_tipo_temporal.png — Consumo de combustível por tipo no tempo."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from ._common import COLORS, init_mpl


def _normalize_fuel_label(raw: object) -> str:
    txt = str(raw or "").strip()
    if not txt:
        return "combustivel_nao_informado"
    norm = txt.lower().replace(" ", "_")
    if norm in {"combustivel_nao_informado", "nao_informado", "unknown", "none", "null"}:
        return "combustivel_nao_informado"
    return txt


def _week_of_month_index(day: date) -> int:
    first_day = day.replace(day=1)
    first_week_end = first_day + timedelta(days=(5 - first_day.weekday()) % 7)
    if day <= first_week_end:
        return 1
    second_week_start = first_week_end + timedelta(days=1)
    return 2 + ((day - second_week_start).days // 7)


def _week_months_contribution(week_iso: str, fuel_total_liters: float) -> dict[tuple[str, int], float]:
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


def build(canonical, cubo=None) -> bytes | None:
    try:
        plt, fig_to_bytes = init_mpl()
    except ImportError:
        return None

    try:
        cron = getattr(canonical, "cronograma", None)
        equipes = getattr(canonical, "equipes_diretas", None) or []
        if not cron or not getattr(cron, "scheduled_activities", None) or not equipes:
            return None

        regime = getattr(getattr(canonical, "projeto", None), "regime_trabalho", None)
        horas_semana = float((getattr(regime, "horas_dia", 0) or 0) * (getattr(regime, "dias_semana", 0) or 0))
        if horas_semana <= 0:
            return None

        eq_by_item = {e.item_id: e for e in equipes}
        liters_by_week_and_fuel: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

        for sa in cron.scheduled_activities:
            equipe = eq_by_item.get(sa.activity_id)
            if equipe is None:
                continue
            dist = getattr(sa, "distribuicao_semanal", None) or {}
            for semana_iso, d in dist.items():
                n_eq = float(getattr(d, "num_equipes", 0) or 0)
                if n_eq <= 0:
                    continue
                eficiencia = float(getattr(d, "eficiencia", 1.0) or 1.0)
                for equip in equipe.equipamentos:
                    consumo_lh = float(getattr(equip, "consumo_litros_hora", 0.0) or 0.0)
                    if consumo_lh <= 0:
                        continue
                    fuel = _normalize_fuel_label(getattr(equip, "tipo_combustivel", None))
                    litros = consumo_lh * float(getattr(equip, "num_unidades", 0) or 0) * horas_semana * n_eq * eficiencia
                    liters_by_week_and_fuel[str(semana_iso)][fuel] += litros

        if not liters_by_week_and_fuel:
            return None

        fuels = sorted({f for m in liters_by_week_and_fuel.values() for f in m.keys()})
        if not fuels:
            return None

        by_fuel_monthly_wom: dict[str, dict[str, dict[int, float]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
        for semana_iso, fuel_map in liters_by_week_and_fuel.items():
            for fuel, liters in fuel_map.items():
                if liters <= 0:
                    continue
                for (bucket, wom), portion in _week_months_contribution(semana_iso, liters).items():
                    by_fuel_monthly_wom[fuel][bucket][wom] += portion

        periodos = sorted({bucket for fuels_map in by_fuel_monthly_wom.values() for bucket in fuels_map.keys()})
        if not periodos:
            return None
        all_woms = sorted({w for fuels_map in by_fuel_monthly_wom.values() for wom_map in fuels_map.values() for w in wom_map})
        if not all_woms:
            return None

        num_fuels = len(fuels)
        x = list(range(len(periodos)))
        fig_w = max(10, len(periodos) * 0.8 + 2)
        fig_h = max(3.0, 2.6 * num_fuels + 1.5)
        fig, axes = plt.subplots(num_fuels, 1, sharex=True, figsize=(fig_w, fig_h))
        if num_fuels == 1:
            axes = [axes]

        for idx, fuel in enumerate(fuels):
            ax = axes[idx]
            baseline = [0.0] * len(periodos)
            for wom_idx in all_woms:
                values = [by_fuel_monthly_wom[fuel][per].get(wom_idx, 0.0) / 1000.0 for per in periodos]
                ax.bar(
                    x,
                    values,
                    bottom=baseline,
                    color=COLORS[(wom_idx - 1) % len(COLORS)],
                    alpha=0.85,
                    width=0.72,
                    label=f"WOM #{wom_idx}",
                )
                baseline = [b + v for b, v in zip(baseline, values)]

            total_fuel_kl = sum(sum(v.values()) for v in by_fuel_monthly_wom[fuel].values()) / 1000.0
            ax.set_title(f"{fuel} - {total_fuel_kl:.1f} kL", fontsize=10, loc="left", fontweight="bold")
            ax.set_ylabel("kL", fontsize=8)
            ax.grid(axis="y", alpha=0.25)

        axes[0].legend(loc="upper right", fontsize=8, title="Semana do mês", title_fontsize=8)
        axes[-1].set_xlabel("Mês", fontsize=9)
        axes[-1].set_xticks(x)
        axes[-1].set_xticklabels(periodos, rotation=45, ha="right", fontsize=8)

        total_kL = sum(sum(m.values()) for m in liters_by_week_and_fuel.values()) / 1000.0
        unknown_liters = sum(
            sum(wom_map.values())
            for wom_map in by_fuel_monthly_wom.get("combustivel_nao_informado", {}).values()
        )
        fig.suptitle("Consumo de Combustível no Tempo por Tipo (subplots)", fontsize=12, fontweight="bold", y=0.995)
        fig.text(0.01, 0.01, f"Total no horizonte: {total_kL:.1f} kL", fontsize=8, color="#555", ha="left")
        if unknown_liters > 0:
            fig.text(
                0.99,
                0.01,
                f"Auditoria pendente: combustivel_nao_informado = {unknown_liters/1000.0:.1f} kL",
                fontsize=8,
                color="#a94442",
                ha="right",
            )
        fig.tight_layout(rect=(0, 0.03, 1, 0.98))
        return fig_to_bytes(fig)
    except Exception:
        try:
            import matplotlib.pyplot as _plt

            _plt.close("all")
        except Exception:
            pass
        return None
