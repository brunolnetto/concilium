"""linha_recursos_tempo.png — Recursos Ativos no Tempo (equipamentos, MO, equipes)."""

from __future__ import annotations

from ..chart_markdown_support import weekly_to_monthly_labels
from ._common import apply_monthly_ticks, build_payload, init_mpl, is_weekly_labels


def build(canonical, cubo, graficos_dict: dict | None = None) -> bytes | None:
    try:
        payload = build_payload("recursos_ativos_tempo", "semana", 120, canonical, cubo)
    except Exception:
        return None
    rows = payload.get("rows") or []
    if not rows:
        return None
    try:
        plt, fig_to_bytes = init_mpl()
    except ImportError:
        return None
    try:
        periods = [str(row.get("periodo", "")) for row in rows]
        x_axis = list(range(len(periods)))

        # MO data from graficos dict (histogram section)
        mo_data = (graficos_dict or {}).get("mao_obra", {}) if graficos_dict else {}
        mo_labels = mo_data.get("labels", []) if isinstance(mo_data, dict) else []
        mo_values = mo_data.get("values", []) if isinstance(mo_data, dict) else []
        mo_map = {str(lbl): float(v) for lbl, v in zip(mo_labels, mo_values)} if mo_labels else {}
        mo_aligned = [mo_map.get(p, 0.0) for p in periods]
        mo_by_funcao = mo_data.get("by_funcao", {}) if isinstance(mo_data, dict) else {}
        funcoes_unicas = (
            [
                float(sum(1 for serie in mo_by_funcao.values() if idx < len(serie) and float(serie[idx] or 0.0) > 0.0))
                for idx in range(len(periods))
            ]
            if isinstance(mo_by_funcao, dict) and mo_by_funcao
            else [0.0] * len(periods)
        )
        has_mo = any(v > 0 for v in mo_aligned)

        n_panels = 3 if has_mo else 2
        fig, axes = plt.subplots(n_panels, 1, figsize=(12, 4 * n_panels), sharex=True)
        ax_eq = axes[0]
        ax_mo = axes[1] if has_mo else None
        ax_team = axes[2] if has_mo else axes[1]

        # Panel 1: Equipamentos
        equip_unidades = [float(row.get("equipamentos_unidades_ativas", 0.0) or 0.0) for row in rows]
        equip_unicos = [float(row.get("n_equipamentos_unicos", 0.0) or 0.0) for row in rows]
        ax_eq.bar(x_axis, equip_unidades, color="#1a3a5c", alpha=0.7, label="Unidades Ativas")
        ax_eq.plot(x_axis, equip_unicos, color="#c05c18", linewidth=2, marker="o", markersize=4, label="Tipos Unicos")
        ax_eq.set_ylabel("Equipamentos (qtd)", fontsize=9)
        ax_eq.set_title("Equipamentos", fontsize=11, fontweight="bold")
        ax_eq.legend(fontsize=8)
        ax_eq.grid(axis="y", alpha=0.3)

        # Panel 2: Mão de Obra
        if ax_mo is not None:
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

        # Panel 3: Equipes
        teams = [float(row.get("n_equipes_totais", 0.0) or 0.0) for row in rows]
        ax_team.fill_between(x_axis, teams, 0, alpha=0.35, color="#2e6da4")
        ax_team.plot(x_axis, teams, color="#2e6da4", linewidth=2, marker="o", markersize=3)
        ax_team.set_ylabel("Equipes (no)", fontsize=9)
        ax_team.set_title("Equipes de Trabalho", fontsize=11, fontweight="bold")
        ax_team.grid(axis="y", alpha=0.3)

        apply_monthly_ticks(ax_team, periods, weekly_to_monthly_labels)
        if not is_weekly_labels(periods):
            ax_team.set_xticks(x_axis)
            ax_team.set_xticklabels(periods, rotation=45, ha="right", fontsize=8)
        ax_team.set_xlabel("Periodo", fontsize=9)

        fig.suptitle("Recursos Ativos no Tempo", fontsize=13, fontweight="bold")
        fig.tight_layout()
        return fig_to_bytes(fig)
    except Exception:
        plt.close("all")
        return None
