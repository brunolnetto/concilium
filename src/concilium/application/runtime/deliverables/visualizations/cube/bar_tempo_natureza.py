"""bar_tempo_natureza.png — Custo Direto vs. Indireto por Período.

Usa as mesmas séries mensais canônicas do scurve_custo (planejamento + indiretos_semanal)
para garantir convergência entre os dois gráficos.
Meses com direto=0 e indireto>0 são marcados como período de pós-obra.
"""

from __future__ import annotations

from ._common import init_mpl
from .scurve_custo import _build_monthly_direto, _build_monthly_indireto
from datetime import date


def build(canonical, cubo) -> bytes | None:  # noqa: ARG001
    del cubo
    try:
        plt, fig_to_bytes = init_mpl()
    except ImportError:
        return None

    try:
        projeto = getattr(canonical, "projeto", None)
        data_inicio_str = getattr(projeto, "data_inicio", None) if projeto else None
        try:
            data_inicio = date.fromisoformat(str(data_inicio_str)) if data_inicio_str else date(2026, 1, 1)
        except (ValueError, TypeError):
            data_inicio = date(2026, 1, 1)

        direto_m   = _build_monthly_direto(canonical)
        indireto_m = _build_monthly_indireto(canonical, data_inicio)
        periodos   = sorted(set(direto_m) | set(indireto_m))
        if not periodos:
            return None

        scale  = 1e6
        direto   = [direto_m.get(p, 0.0) / scale   for p in periodos]
        indireto = [indireto_m.get(p, 0.0) / scale  for p in periodos]

        # Último mês com atividade direta
        ultimo_direto_idx = max(
            (i for i, v in enumerate(direto) if v > 0), default=None
        )

        # Cores: pós-obra recebe alpha reduzido
        x = list(range(len(periodos)))
        alphas_d = [0.88 if (direto[i] > 0) else 0.30 for i in x]
        alphas_i = [0.88 if (direto[i] > 0 or (i > 0 and direto[i - 1] > 0)) else 0.30 for i in x]

        fig, ax = plt.subplots(figsize=(max(10, len(periodos) * 0.9 + 2), 5))

        for i_bar, (d, ind, p) in enumerate(zip(direto, indireto, periodos)):
            a_d = 0.88 if d > 0 else 0.25
            a_i = 0.88 if d > 0 else 0.25
            ax.bar(i_bar, d,   color="#1a3a5c", alpha=a_d, width=0.7)
            ax.bar(i_bar, ind, bottom=d, color="#5adc8e", alpha=a_i, width=0.7)

        # Legenda manual
        from matplotlib.patches import Patch
        legend_elements = [
            Patch(facecolor="#1a3a5c", alpha=0.88, label="Direto"),
            Patch(facecolor="#5adc8e", alpha=0.88, label="Indireto"),
            Patch(facecolor="#999",    alpha=0.4,  label="Pós-obra (só indireto)"),
        ]
        ax.legend(handles=legend_elements, fontsize=8, loc="upper right")

        # Separador obra concluída
        if ultimo_direto_idx is not None and ultimo_direto_idx < len(periodos) - 1:
            ax.axvline(x=ultimo_direto_idx + 0.5, color="#555", linewidth=1.2,
                       linestyle=":", alpha=0.7)
            ax.text(ultimo_direto_idx + 0.6, ax.get_ylim()[1] * 0.92,
                    "← obra\n   pós-obra →",
                    fontsize=7, color="#555", va="top")

        ax.set_xticks(x)
        ax.set_xticklabels(periodos, rotation=45, ha="right", fontsize=8)
        ax.set_ylabel("R$ (Mi)", fontsize=9)
        ax.set_title("Custo Direto vs. Indireto por Período", fontsize=11, fontweight="bold")
        ax.grid(axis="y", alpha=0.3)
        fig.tight_layout()
        return fig_to_bytes(fig)
    except Exception:
        plt.close("all")
        return None
