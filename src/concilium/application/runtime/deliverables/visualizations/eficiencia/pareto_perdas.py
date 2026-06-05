"""NEP-036 — Nível 3: Pareto de perdas físicas por atividade.

Mostra as atividades com maior perda produtiva (m³, t, km perdidos)
em barras horizontais ordenadas. Público-alvo: planejamento, engenharia.

"Perdemos 3.500 m³ por impraticabilidade em eap-1_7" é mais acionável
que "a eficiência foi 0.78" (Seção 12 do modelo).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from concilium.domain.services.eficiencia_field_builder import CampoEficiencia


def plot_pareto_perdas(
    campo: CampoEficiencia,
    *,
    top_n: int = 10,
    title: str = "Pareto de Perdas Físicas por Atividade",
    unidade: str = "unid.",
) -> Any:
    """Barras horizontais: Top-N atividades por perda física total.

    Retorna figura matplotlib ou None.
    """
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    pareto = campo.pareto_perdas(top_n=top_n)
    if not pareto:
        return None

    pareto_sorted = sorted(pareto, key=lambda x: x["perda_fisica_total"])
    labels = [f"{p['item_id']} ({p['pct_perda']:.0f}%)" for p in pareto_sorted]
    values = [p["perda_fisica_total"] for p in pareto_sorted]

    fig, ax = plt.subplots(figsize=(9, max(3, len(pareto_sorted) * 0.45)))
    bars = ax.barh(labels, values, color="#FB8C00", alpha=0.85, edgecolor="white")
    for bar, val in zip(bars, values, strict=True):
        ax.text(bar.get_width() + max(values) * 0.01, bar.get_y() + bar.get_height() / 2,
                f"{val:,.0f} {unidade}", va="center", fontsize=8)
    ax.set_xlabel(f"Perda física total ({unidade})")
    ax.set_title(f"{title} (Top {len(pareto_sorted)})")
    ax.set_xlim(0, max(values) * 1.15 if values else 1)
    fig.tight_layout()
    return fig
