"""NEP-036 — Nível 4: Heatmap RESTRITO ao Top-N atividades.

Evita o problema do heatmap 200×80 = 16.000 células inelegível (Seção 9 do
modelo). Exibe apenas as Top-N atividades por perda total × as semanas em que
elas estiveram ativas.

Público-alvo: engenharia (análise sob demanda).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from concilium.domain.services.eficiencia_field_builder import CampoEficiencia


def plot_heatmap_top_n(
    campo: CampoEficiencia,
    *,
    top_n: int = 10,
    fator: str = "E",
    title: str | None = None,
) -> Any:
    """Heatmap de eficiência restrito ao Top-N atividades por perda.

    `fator` pode ser "E" (total), "S" (alocação), "P_r" (praticabilidade)
    ou "W" (gestão). Título inclui aviso explícito de restrição.
    Retorna figura matplotlib ou None.
    """
    try:
        import matplotlib.colors as mcolors
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    pareto = campo.pareto_perdas(top_n=top_n)
    if not pareto:
        return None

    top_ids = [p["item_id"] for p in pareto]
    field_map = {"E": campo.E, "S": campo.S, "P_r": campo.P_r, "W": campo.W}
    field = field_map.get(fator, campo.E)

    # Semanas onde ao menos uma atividade Top-N está ativa
    semanas_ativas: list[str] = []
    for sem in campo.semanas:
        if any((field.get(iid) or {}).get(sem) is not None for iid in top_ids):
            semanas_ativas.append(sem)

    if not semanas_ativas:
        return None

    # Monta a matrix Top-N × semanas
    matrix = [[(field.get(iid) or {}).get(sem, float("nan")) for sem in semanas_ativas] for iid in top_ids]

    fig, ax = plt.subplots(figsize=(max(6, len(semanas_ativas) * 0.25), max(3, len(top_ids) * 0.45)))
    cmap = plt.cm.RdYlGn  # vermelho (ineficiente) → verde (eficiente)
    norm = mcolors.Normalize(vmin=0, vmax=1)
    im = ax.imshow(matrix, cmap=cmap, norm=norm, aspect="auto")
    ax.set_yticks(range(len(top_ids)))
    ax.set_yticklabels(top_ids, fontsize=8)
    ax.set_xticks(range(0, len(semanas_ativas), max(1, len(semanas_ativas) // 8)))
    ax.set_xticklabels(
        [semanas_ativas[i] for i in range(0, len(semanas_ativas), max(1, len(semanas_ativas) // 8))],
        rotation=45,
        ha="right",
        fontsize=7,
    )
    plt.colorbar(im, ax=ax, label=f"η_{fator} (0=ineficiente, 1=pleno)")
    _title = title or f"Campo η_{fator} — Top {len(top_ids)} atividades por perda"
    ax.set_title(f"{_title}\n(restrito: {len(top_ids)} de {len(campo.atividades)} atividades)")
    fig.tight_layout()
    return fig
