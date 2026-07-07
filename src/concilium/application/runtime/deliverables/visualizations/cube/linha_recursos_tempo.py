"""linha_recursos_tempo.png — Recursos Ativos no Tempo (equipamentos, MO, equipes)."""

from __future__ import annotations

from ..chart_markdown_support import weekly_to_monthly_labels
from . import _common


def _mo_aligned_series(mo_data: dict, periods: list[str]) -> list[float]:
    mo_labels = mo_data.get("labels", []) if isinstance(mo_data, dict) else []
    mo_values = mo_data.get("values", []) if isinstance(mo_data, dict) else []
    mo_map = {str(lbl): float(v) for lbl, v in zip(mo_labels, mo_values, strict=False)} if mo_labels else {}
    return [mo_map.get(p, 0.0) for p in periods]


def _funcoes_unicas_series(mo_data: dict, periods: list[str]) -> list[float]:
    mo_by_funcao = mo_data.get("by_funcao", {}) if isinstance(mo_data, dict) else {}
    if not (isinstance(mo_by_funcao, dict) and mo_by_funcao):
        return [0.0] * len(periods)
    return [
        float(sum(1 for serie in mo_by_funcao.values() if idx < len(serie) and float(serie[idx] or 0.0) > 0.0))
        for idx in range(len(periods))
    ]


def _compute_mo_series(graficos_dict: dict | None, periods: list[str]) -> tuple[list[float], list[float], bool]:
    """Retorna (mo_aligned, funcoes_unicas, has_mo) a partir do dict de gráficos (histograma MO)."""
    mo_data = (graficos_dict or {}).get("mao_obra", {}) if graficos_dict else {}
    mo_aligned = _mo_aligned_series(mo_data, periods)
    funcoes_unicas = _funcoes_unicas_series(mo_data, periods)
    has_mo = any(v > 0 for v in mo_aligned)
    return mo_aligned, funcoes_unicas, has_mo


def _draw_panel_equipamentos(ax_eq, rows: list[dict], x_axis: list[int]) -> tuple[list[float], list[float]]:
    equip_unidades = [float(row.get("equipamentos_unidades_ativas", 0.0) or 0.0) for row in rows]
    equip_unicos = [float(row.get("n_equipamentos_unicos", 0.0) or 0.0) for row in rows]
    ax_eq.bar(x_axis, equip_unidades, color="#1a3a5c", alpha=0.7, label="Unidades Ativas")
    ax_eq.plot(x_axis, equip_unicos, color="#c05c18", linewidth=2, marker="o", markersize=4, label="Tipos Unicos")
    ax_eq.set_ylabel("Equipamentos (qtd)", fontsize=9)
    ax_eq.set_title("Equipamentos", fontsize=11, fontweight="bold")
    ax_eq.legend(fontsize=8)
    ax_eq.grid(axis="y", alpha=0.3)
    return equip_unidades, equip_unicos


def _draw_panel_mao_obra(ax_mo, x_axis: list[int], mo_aligned: list[float], funcoes_unicas: list[float]) -> None:
    if ax_mo is None:
        return
    ax_mo.bar(x_axis, mo_aligned, color="#1a3a5c", alpha=0.7, label="Trabalhadores Ativos")
    if any(v > 0 for v in funcoes_unicas):
        ax_mo.plot(
            x_axis,
            funcoes_unicas,
            color="#c05c18",
            linewidth=2,
            marker="o",
            markersize=4,
            label="Funcoes Unicas",
        )
    ax_mo.set_ylabel("Trabalhadores (no)", fontsize=9)
    ax_mo.set_title("Mao de Obra", fontsize=11, fontweight="bold")
    ax_mo.legend(fontsize=8)
    ax_mo.grid(axis="y", alpha=0.3)


def _compute_equipes_by_atividade(canonical, periods: list[str]) -> dict[str, list[float]]:
    """Fonte: cronograma.scheduled_activities.distribuicao_semanal.num_equipes."""
    cron = getattr(canonical, "cronograma", None)
    sched_acts = getattr(cron, "scheduled_activities", None) or []
    equipes_by_atv: dict[str, list[float]] = {}
    for sa in sched_acts:
        atv_id = str(getattr(sa, "activity_id", "") or "")
        dist = getattr(sa, "distribuicao_semanal", None) or {}
        if atv_id and isinstance(dist, dict):
            equipes_by_atv[atv_id] = [
                float((dist.get(p) and getattr(dist[p], "num_equipes", 0)) or 0.0) for p in periods
            ]
    return equipes_by_atv


def _draw_panel_equipes_stacked(ax_team, x_axis: list[int], equipes_by_atv: dict[str, list[float]]) -> None:
    import matplotlib.pyplot as _plt

    atv_ids_ordered = sorted(equipes_by_atv.keys())
    cmap = _plt.get_cmap("tab20")
    colors_atv = [cmap(i / max(len(atv_ids_ordered), 1)) for i in range(len(atv_ids_ordered))]
    bottoms = [0.0] * len(x_axis)
    for idx, atv in enumerate(atv_ids_ordered):
        vals = equipes_by_atv[atv]
        tops = [b + v for b, v in zip(bottoms, vals, strict=False)]
        ax_team.fill_between(x_axis, bottoms, tops, alpha=0.6, color=colors_atv[idx], label=atv.replace("eap-1_", "#"))
        bottoms = tops
    ax_team.legend(fontsize=6, loc="upper right", ncol=3)


def _draw_panel_equipes(
    ax_team,
    x_axis: list[int],
    teams: list[float],
    equipes_by_atv: dict[str, list[float]],
    periods: list[str],
) -> None:
    # Panel 3: Equipes por atividade direta (stacked area)
    if equipes_by_atv:
        _draw_panel_equipes_stacked(ax_team, x_axis, equipes_by_atv)
    else:
        ax_team.fill_between(x_axis, teams, 0, alpha=0.35, color="#2e6da4")
        ax_team.plot(x_axis, teams, color="#2e6da4", linewidth=2, marker="o", markersize=3)

    ax_team.set_ylabel("Equipes (no)", fontsize=9)
    ax_team.set_title("Equipes por Atividade Direta", fontsize=11, fontweight="bold")
    ax_team.grid(axis="y", alpha=0.3)

    _common.apply_monthly_ticks(ax_team, periods, weekly_to_monthly_labels)
    if not _common.is_weekly_labels(periods):
        ax_team.set_xticks(x_axis)
        ax_team.set_xticklabels(periods, rotation=45, ha="right", fontsize=8)
    ax_team.set_xlabel("Periodo", fontsize=9)


def _clip_x_axis_ultima_semana_ativa(
    axes_to_clip: list,
    x_axis: list[int],
    teams: list[float],
    equip_unidades: list[float],
    mo_aligned: list[float],
    has_mo: bool,
) -> None:
    """Clipa o eixo X na última semana com recursos ativos para evitar que
    o período de pós-obra (indiretos após atividades diretas) estenda o gráfico.
    """
    ultima_semana_ativa = max(
        (i for i, t in enumerate(teams) if t > 0 or equip_unidades[i] > 0 or (has_mo and mo_aligned[i] > 0)),
        default=len(x_axis) - 1,
    )
    if ultima_semana_ativa < len(x_axis) - 1:  # pragma: no cover
        margem = min(2, len(x_axis) - ultima_semana_ativa - 1)
        x_max = ultima_semana_ativa + margem
        for _ax in axes_to_clip:
            _ax.set_xlim(-0.5, x_max + 0.5)


def _render_recursos_ativos_tempo(plt, canonical, rows: list[dict], graficos_dict: dict | None):
    periods = [str(row.get("periodo", "")) for row in rows]
    x_axis = list(range(len(periods)))

    mo_aligned, funcoes_unicas, has_mo = _compute_mo_series(graficos_dict, periods)

    n_panels = 3 if has_mo else 2
    fig, axes = plt.subplots(n_panels, 1, figsize=(12, 4 * n_panels), sharex=True)
    ax_eq = axes[0]
    ax_mo = axes[1] if has_mo else None
    ax_team = axes[2] if has_mo else axes[1]

    equip_unidades, _equip_unicos = _draw_panel_equipamentos(ax_eq, rows, x_axis)
    _draw_panel_mao_obra(ax_mo, x_axis, mo_aligned, funcoes_unicas)

    teams = [float(row.get("n_equipes_totais", 0.0) or 0.0) for row in rows]
    equipes_by_atv = _compute_equipes_by_atividade(canonical, periods)
    _draw_panel_equipes(ax_team, x_axis, teams, equipes_by_atv, periods)

    axes_to_clip = [ax_eq, ax_team] + ([ax_mo] if ax_mo else [])
    _clip_x_axis_ultima_semana_ativa(axes_to_clip, x_axis, teams, equip_unidades, mo_aligned, has_mo)

    fig.suptitle("Recursos Ativos no Tempo", fontsize=13, fontweight="bold")
    fig.tight_layout()
    return fig


def build(canonical, cubo, graficos_dict: dict | None = None) -> bytes | None:
    try:
        payload = _common.build_payload("recursos_ativos_tempo", "semana", 120, canonical, cubo)
    except Exception:
        return None
    rows = payload.get("rows") or []
    if not rows:
        return None

    try:
        plt, fig_to_bytes = _common.init_mpl()
    except ImportError:
        return None

    fig = None

    try:
        fig = _render_recursos_ativos_tempo(plt, canonical, rows, graficos_dict)
        return fig_to_bytes(fig)
    except Exception:  # pragma: no cover
        if fig is not None:
            plt.close(fig)
        else:
            plt.close()
        return None
