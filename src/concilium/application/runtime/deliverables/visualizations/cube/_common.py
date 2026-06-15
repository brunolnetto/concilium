"""Shared helpers for analytic cube charts."""

from __future__ import annotations

import io

COLORS = ["#1a3a5c", "#c05c18", "#5aabdc", "#e8a030", "#5adc8e", "#a07ad8", "#dc5a8e"]

SERIE_LABEL_MAP: dict[str, str] = {
    # Componentes BDI individuais (uppercase — renderizadores históricos)
    "overhead_AC": "Adm. Central (AC)",
    "overhead_DF": "Desp. Financeiras (DF)",
    "overhead_R": "Risco / Seguro (R)",
    "overhead_L": "Lucro (L)",
    "tributo_ISS": "ISS",
    "tributo_CSSL": "Contrib. Social (CSLL)",
    "tributo_IR": "Imp. de Renda (IR)",
    # Componentes BDI individuais (lowercase — cubo cells)
    "overhead_ac": "Adm. Central (AC)",
    "overhead_df": "Desp. Financeiras (DF)",
    "overhead_r": "Risco / Seguro (R)",
    "overhead_cr": "Risco / Seguro (R)",
    "margem_l": "Lucro (L)",
    "tributo_cofins": "COFINS",
    "tributo_iss": "ISS",
    "tributo_pis": "PIS",
    "tributo_cssl": "Contrib. Social (CSLL)",
    "tributo_ir": "Imp. de Renda (IR)",
    # Componentes agregados (novos — ADR-084 Fase 4)
    "overhead": "Overhead BDI",
    "tributos": "Tributos",
    # Custo direto e indireto
    "custo_direto": "Custo Direto",
    "custo_indireto": "Custo Indireto",
    # Categorias de equipe
    "equipamento": "Equipamentos",
    "mao_obra": "Mao de Obra",
    "material": "Material",
    "diesel": "Diesel",
    "servico": "Servicos",
    # Natureza
    "direto": "Custo Direto",
    "indireto": "Custo Indireto",
}


def get_column_id(columns: list[dict], role: str) -> str | None:
    for col in columns:
        if col.get("role") == role:
            return col.get("id")
    return None


def col_label(columns: list[dict], col_id: str | None) -> str:
    if not col_id:
        return ""
    for col in columns:
        if col.get("id") == col_id:
            return col.get("label", col_id)
    return col_id or ""


def is_weekly_labels(labels: list[str]) -> bool:
    return bool(labels) and "-W" in str(labels[0])


def apply_monthly_ticks(ax, labels: list[str], weekly_to_monthly_fn) -> None:
    if not is_weekly_labels(labels):
        return
    display = weekly_to_monthly_fn(labels)
    tick_positions = [i for i, lbl in enumerate(display) if lbl != "."]
    tick_labels = [lbl for lbl in display if lbl != "."]
    ax.set_xticks(tick_positions)
    ax.set_xticklabels(tick_labels, rotation=45, ha="right", fontsize=8)


def init_mpl():
    """Bootstrap matplotlib Agg backend. Returns (plt, fig_to_bytes). Raises ImportError."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    def fig_to_bytes(fig) -> bytes:
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        return buf.read()

    return plt, fig_to_bytes


def build_payload(face: str, granularidade: str, top_n: int, canonical, cubo) -> dict:
    """Convenience wrapper around build_cube_projection_payload."""
    from concilium.application.services.analytics.cube_projection_views import build_cube_projection_payload

    return build_cube_projection_payload(
        canonical=canonical,
        cubo=cubo,
        face=face,
        granularidade=granularidade,
        top_n=top_n,
    )
