"""bar_combustivel_tipo_temporal.png — Consumo de combustível por tipo no tempo."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from ._common import COLORS, init_mpl, safe_close_mpl


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


def _resolve_horas_semana(canonical) -> float:
    """Horas/semana do regime de trabalho do projeto (0.0 se indisponível)."""
    regime = getattr(getattr(canonical, "projeto", None), "regime_trabalho", None)
    return float((getattr(regime, "horas_dia", 0) or 0) * (getattr(regime, "dias_semana", 0) or 0))


def _accumulate_equipe_semana_consumo(
    week_bucket: dict[str, float],
    equipe,
    n_eq: float,
    eficiencia: float,
    horas_semana: float,
) -> None:
    """Soma, no bucket de uma semana, o consumo de combustível de todos os equipamentos da equipe."""
    for equip in equipe.equipamentos:
        consumo_lh = float(getattr(equip, "consumo_litros_hora", 0.0) or 0.0)
        if consumo_lh <= 0:
            continue
        fuel = _normalize_fuel_label(getattr(equip, "tipo_combustivel", None))
        litros = consumo_lh * float(getattr(equip, "num_unidades", 0) or 0) * horas_semana * n_eq * eficiencia
        week_bucket[fuel] += litros


def _compute_liters_by_week_and_fuel(cron, equipes, horas_semana: float) -> dict[str, dict[str, float]]:
    """Agrega litros de combustível consumidos por semana ISO e tipo de combustível."""
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
            _accumulate_equipe_semana_consumo(
                liters_by_week_and_fuel[str(semana_iso)], equipe, n_eq, eficiencia, horas_semana
            )

    return liters_by_week_and_fuel


def _aggregate_by_fuel_monthly_wom(
    liters_by_week_and_fuel: dict[str, dict[str, float]],
) -> dict[str, dict[str, dict[int, float]]]:
    """Redistribui litros semanais em buckets mensais por semana-do-mês (WOM)."""
    by_fuel_monthly_wom: dict[str, dict[str, dict[int, float]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(float))
    )
    for semana_iso, fuel_map in liters_by_week_and_fuel.items():
        for fuel, liters in fuel_map.items():
            if liters <= 0:
                continue
            for (bucket, wom), portion in _week_months_contribution(semana_iso, liters).items():
                by_fuel_monthly_wom[fuel][bucket][wom] += portion
    return by_fuel_monthly_wom


def _plot_fuel_stacked_bars(
    axes,
    fuels: list[str],
    periodos: list[str],
    all_woms: list[int],
    by_fuel_monthly_wom: dict[str, dict[str, dict[int, float]]],
    x: list[int],
) -> None:
    """Desenha, para cada combustível, as barras empilhadas por semana-do-mês."""
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
            baseline = [b + v for b, v in zip(baseline, values, strict=False)]

        total_fuel_kl = sum(sum(v.values()) for v in by_fuel_monthly_wom[fuel].values()) / 1000.0
        ax.set_title(f"{fuel} - {total_fuel_kl:.1f} kL", fontsize=10, loc="left", fontweight="bold")
        ax.set_ylabel("kL", fontsize=8)
        ax.grid(axis="y", alpha=0.25)


def _add_footer_annotations(
    fig,
    liters_by_week_and_fuel: dict[str, dict[str, float]],
    by_fuel_monthly_wom: dict[str, dict[str, dict[int, float]]],
) -> None:
    """Adiciona título, totais e aviso de auditoria pendente à figura."""
    total_kL = sum(sum(m.values()) for m in liters_by_week_and_fuel.values()) / 1000.0
    unknown_liters = sum(
        sum(wom_map.values()) for wom_map in by_fuel_monthly_wom.get("combustivel_nao_informado", {}).values()
    )
    fig.suptitle("Consumo de Combustível no Tempo por Tipo (subplots)", fontsize=12, fontweight="bold", y=0.995)
    fig.text(0.01, 0.01, f"Total no horizonte: {total_kL:.1f} kL", fontsize=8, color="#555", ha="left")
    if unknown_liters > 0:
        fig.text(
            0.99,
            0.01,
            f"Auditoria pendente: combustivel_nao_informado = {unknown_liters / 1000.0:.1f} kL",
            fontsize=8,
            color="#a94442",
            ha="right",
        )


def _derive_plot_dimensions(
    liters_by_week_and_fuel: dict[str, dict[str, float]],
) -> tuple[list[str], dict[str, dict[str, dict[int, float]]], list[str], list[int]] | None:
    """Deriva fuels/periodos/all_woms a partir do consumo semanal; None se não houver períodos."""
    # `fuels` é derivado do mesmo `liters_by_week_and_fuel` já garantido
    # não-vazio pelo chamador, então nunca é uma lista vazia aqui.
    fuels = sorted({f for m in liters_by_week_and_fuel.values() for f in m.keys()})

    by_fuel_monthly_wom = _aggregate_by_fuel_monthly_wom(liters_by_week_and_fuel)

    periodos = sorted({bucket for fuels_map in by_fuel_monthly_wom.values() for bucket in fuels_map.keys()})
    if not periodos:
        return None
    # Toda entrada de `periodos` (não-vazio pela guarda acima) veio de um
    # bucket com pelo menos um `wom` associado em `by_fuel_monthly_wom`,
    # então `all_woms` nunca é uma lista vazia aqui.
    all_woms = sorted(
        {w for fuels_map in by_fuel_monthly_wom.values() for wom_map in fuels_map.values() for w in wom_map}
    )
    return fuels, by_fuel_monthly_wom, periodos, all_woms


def _resolve_cron_e_equipes(canonical) -> tuple[object, list] | None:
    """Retorna (cronograma, equipes_diretas) válidos, ou None se algum estiver ausente."""
    cron = getattr(canonical, "cronograma", None)
    equipes = getattr(canonical, "equipes_diretas", None) or []
    if not cron or not getattr(cron, "scheduled_activities", None) or not equipes:
        return None
    return cron, equipes


def build(canonical, cubo=None) -> bytes | None:
    try:
        plt, fig_to_bytes = init_mpl()
    except ImportError:
        return None

    try:
        cron_equipes = _resolve_cron_e_equipes(canonical)
        if cron_equipes is None:
            return None
        cron, equipes = cron_equipes

        horas_semana = _resolve_horas_semana(canonical)
        if horas_semana <= 0:
            return None

        liters_by_week_and_fuel = _compute_liters_by_week_and_fuel(cron, equipes, horas_semana)

        if not liters_by_week_and_fuel:
            return None

        dims = _derive_plot_dimensions(liters_by_week_and_fuel)
        if dims is None:
            return None
        fuels, by_fuel_monthly_wom, periodos, all_woms = dims

        num_fuels = len(fuels)
        x = list(range(len(periodos)))
        fig_w = max(10, len(periodos) * 0.8 + 2)
        fig_h = max(3.0, 2.6 * num_fuels + 1.5)
        fig, axes = plt.subplots(num_fuels, 1, sharex=True, figsize=(fig_w, fig_h))
        if num_fuels == 1:
            axes = [axes]

        _plot_fuel_stacked_bars(axes, fuels, periodos, all_woms, by_fuel_monthly_wom, x)

        axes[0].legend(loc="upper right", fontsize=8, title="Semana do mês", title_fontsize=8)
        axes[-1].set_xlabel("Mês", fontsize=9)
        axes[-1].set_xticks(x)
        axes[-1].set_xticklabels(periodos, rotation=45, ha="right", fontsize=8)

        _add_footer_annotations(fig, liters_by_week_and_fuel, by_fuel_monthly_wom)
        fig.tight_layout(rect=(0, 0.03, 1, 0.98))
        return fig_to_bytes(fig)
    except Exception:
        safe_close_mpl()
        return None
