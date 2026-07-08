"""NEP-036 — Nível 4: Heatmap RESTRITO ao Top-N atividades.

Evita o problema do heatmap 200×80 = 16.000 células inelegível (Seção 9 do
modelo). Exibe apenas as Top-N atividades por perda total × as semanas em que
elas estiveram ativas.

Público-alvo: engenharia (análise sob demanda).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from concilium.domain.services.analytics.eficiencia_field_builder import CampoEficiencia


def _resolve_field_map(campo: CampoEficiencia) -> dict[str, Any]:
    """Monta o mapa fator -> campo semanal, com fallbacks para controle sem planejamento.

    ADR-124: os fatores de planejamento são ``Eta_plan``, ``Eta_clima`` e ``Delta``.
    O antigo alias ``P_r`` (praticabilidade) foi renomeado para ``Eta_plan`` — o
    conteúdo semântico é idêntico (η_plan = η_clima · δ). Os fatores de controle
    (E/S/W) permanecem no mapa e caem para ``Eta_plan`` enquanto forem None.
    """
    return {
        "Eta_plan": campo.Eta_plan,
        "Eta_clima": campo.Eta_clima,
        "Delta": campo.Delta,
        # controle (None no planejamento — fallback para Eta_plan)
        "E": campo.E or campo.Eta_plan,
        "S": campo.S or campo.Eta_plan,
        "W": campo.W or campo.Eta_plan,
    }


def _compute_semanas_ativas(campo: CampoEficiencia, field: dict, top_ids: list) -> list[str]:
    """Semanas onde ao menos uma atividade Top-N está ativa."""
    semanas_ativas: list[str] = []
    for sem in campo.semanas:
        if any((field.get(iid) or {}).get(sem) is not None for iid in top_ids):
            semanas_ativas.append(sem)
    return semanas_ativas


def _build_top_n_matrix(field: dict, top_ids: list, semanas_ativas: list[str]) -> list[list[float]]:
    """Monta a matrix Top-N x semanas."""
    return [[(field.get(iid) or {}).get(sem, float("nan")) for sem in semanas_ativas] for iid in top_ids]


_FATOR_SIMBOLO = {
    "Eta_plan": "η_plan",
    "Eta_clima": "η_clima",
    "Delta": "δ",
    "E": "η",
    "S": "η_s",
    "W": "η_w",
}


def _fator_simbolo(fator: str) -> str:
    """Rótulo de exibição do fator — Delta é δ, não η_Delta (ADR-124)."""
    return _FATOR_SIMBOLO.get(fator, f"η_{fator}")


def _render_top_n_heatmap(
    plt: Any,
    mcolors: Any,
    matrix: list[list[float]],
    top_ids: list,
    semanas_ativas: list[str],
    fator: str,
    title: str | None,
    n_atividades_total: int,
) -> Any:
    """Renderiza a figura matplotlib do heatmap Top-N."""
    simbolo = _fator_simbolo(fator)
    fig, ax = plt.subplots(figsize=(max(6, len(semanas_ativas) * 0.25), max(3, len(top_ids) * 0.45)))
    cmap = plt.get_cmap("RdYlGn")  # vermelho (ineficiente) → verde (eficiente)
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
    plt.colorbar(im, ax=ax, label=f"{simbolo} (0=ineficiente, 1=pleno)")
    _title = title or f"Campo {simbolo} — Top {len(top_ids)} atividades por perda"
    ax.set_title(f"{_title}\n(restrito: {len(top_ids)} de {n_atividades_total} atividades)")
    fig.tight_layout()
    return fig


def plot_heatmap_top_n(
    campo: CampoEficiencia,
    *,
    top_n: int = 10,
    fator: str = "E",
    title: str | None = None,
) -> Any:
    """Heatmap de eficiência restrito ao Top-N atividades por perda.

    ADR-124 (planejamento): `fator` pode ser "Eta_plan" (η_plan = η_clima · δ),
    "Eta_clima" (praticabilidade climática) ou "Delta" (δ, calendário).
    Fatores de controle "E"/"S"/"W" caem para Eta_plan enquanto None (sem execução real).
    Título inclui aviso explícito de restrição.
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
    field_map = _resolve_field_map(campo)
    field = field_map.get(fator, campo.Eta_plan)

    semanas_ativas = _compute_semanas_ativas(campo, field, top_ids)
    if not semanas_ativas:
        return None

    matrix = _build_top_n_matrix(field, top_ids, semanas_ativas)

    return _render_top_n_heatmap(plt, mcolors, matrix, top_ids, semanas_ativas, fator, title, len(campo.atividades))
