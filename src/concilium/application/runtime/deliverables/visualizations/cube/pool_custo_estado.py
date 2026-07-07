"""pool_custo_estado.png — Custo do Pool por Estado × Componente.

Evidencia a diferença de composição de custo entre estado produtivo (todos os
componentes) e ocioso (MO integral obrigatório por CLT + EQ a taxa de locação
reduzida; combustível e material zerados sem operação).
"""

from __future__ import annotations

from ._common import COLORS, init_mpl

_COMP_LABELS = {
    "mo": "Mão-de-obra",
    "eq": "Equipamento",
    "comb": "Combustível",
    "mat": "Material",
}
_ESTADO_LABELS = {"prod": "Produtivo", "idle": "Ocioso", "off": "Desmobilizado"}


def _normalize_component_key(raw: str) -> str:
    txt = str(raw or "").strip().lower()
    if txt in {"mo", "mão-de-obra", "mao-de-obra", "mao_obra", "mão de obra", "mao de obra"}:
        return "mo"
    if txt in {"eq", "equipamento", "equipamentos"}:
        return "eq"
    if txt in {"comb", "combustivel", "combustível", "diesel"}:
        return "comb"
    if txt in {"mat", "material", "materiais"}:
        return "mat"
    return txt


def _normalize_state_key(raw: str) -> str:
    txt = str(raw or "").strip().lower()
    if txt in {"prod", "produtivo"}:
        return "prod"
    if txt in {"idle", "ocioso"}:
        return "idle"
    if txt in {"off", "desmobilizado"}:
        return "off"
    return txt


def _build_estado_componente_matrix(rows: list[dict]) -> dict[str, dict[str, float]]:
    """Constrói a matriz estado → {componente → valor} a partir das rows da projeção."""
    from collections import defaultdict

    matrix: dict[str, dict[str, float]] = defaultdict(dict)
    for r in rows:
        estado = _normalize_state_key(r.get("estado", ""))
        comp = _normalize_component_key(r.get("componente", ""))
        val = float(r.get("valor_rs", 0.0) or 0.0)
        matrix[estado][comp] = val
    return matrix


def _plot_estado_componente_bars(
    ax, estados: list[str], comp_keys: list[str], matrix: dict[str, dict[str, float]]
) -> None:
    """Desenha as barras empilhadas de custo por estado × componente sobre `ax`."""
    bar_width = 0.35
    x = list(range(len(estados)))
    bottoms = [0.0] * len(estados)

    for ci, comp_key in enumerate(comp_keys):
        comp_label = _COMP_LABELS[comp_key]
        vals = [matrix[e].get(comp_key, 0.0) / 1e6 for e in estados]
        ax.bar(x, vals, bar_width, bottom=bottoms, color=COLORS[ci % len(COLORS)], alpha=0.85, label=comp_label)
        bottoms = [b + v for b, v in zip(bottoms, vals, strict=False)]

    ax.set_xticks(x)
    ax.set_xticklabels([_ESTADO_LABELS[e] for e in estados], fontsize=10)
    ax.set_ylabel("Custo (R$ M)", fontsize=10)
    ax.set_title("Custo do Pool por Estado e Componente", fontsize=11, fontweight="bold")
    ax.legend(fontsize=9, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=4, frameon=False)
    ax.grid(axis="y", alpha=0.3)


def _add_narrativa_footer(fig, proj: dict, matrix: dict[str, dict[str, float]], estados: list[str]) -> None:
    """Adiciona a narrativa (esquerda) e as notas de componentes zerados (direita) ao rodapé da figura."""
    narrativa = proj.get("narrativa") or []
    if narrativa:
        fig.text(
            0.01,
            0.01,
            narrativa[0],
            fontsize=7.5,
            color="#555",
            ha="left",
            wrap=True,
        )
    total_comb = sum(matrix[e].get("comb", 0.0) for e in estados)
    total_mat = sum(matrix[e].get("mat", 0.0) for e in estados)
    if total_comb <= 0.0 or total_mat <= 0.0:
        notas = []
        if total_comb <= 0.0:
            notas.append("Combustível = R$ 0")
        if total_mat <= 0.0:
            notas.append("Material = R$ 0")
        fig.text(
            0.99,
            0.01,
            " · ".join(notas) + " no dataset desta execução.",
            fontsize=7.3,
            color="#555",
            ha="right",
            wrap=True,
        )


def build(canonical, cubo=None) -> bytes | None:
    try:
        from concilium.application.services.analytics.cubo_pool_projection import resolve_cubo_pool_projection

        proj = resolve_cubo_pool_projection(canonical, face="custo_estado_componente")
    except Exception:
        return None

    rows = proj.get("rows") or []
    if not rows:
        return None

    try:
        plt, fig_to_bytes = init_mpl()
    except ImportError:
        return None

    try:
        matrix = _build_estado_componente_matrix(rows)

        estados = [e for e in ("prod", "idle") if e in matrix and sum(matrix[e].values()) > 0]
        if not estados:
            return None

        comp_keys = list(_COMP_LABELS.keys())

        fig, ax = plt.subplots(figsize=(9, 5))
        _plot_estado_componente_bars(ax, estados, comp_keys, matrix)
        _add_narrativa_footer(fig, proj, matrix, estados)

        fig.tight_layout(rect=(0, 0.07, 1, 1))
        return fig_to_bytes(fig)
    except Exception:
        plt.close("all")
        return None
