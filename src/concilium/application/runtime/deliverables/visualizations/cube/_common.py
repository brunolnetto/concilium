"""Shared helpers for analytic cube charts."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from concilium.application.services.analytics.cube_projection_views import FaceGranularity

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
    # Categorias temporais (faces novas)
    "MAO_OBRA": "Mão-de-obra",
    "EQUIP": "Equipamento",
    "MAT": "Material",
    "COMB": "Combustível",
    "ADM": "ADM",
    "TOP": "TOP",
    "LAB": "LAB",
    "QSMS": "QSMS",
    "MOB": "MOB",
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


# Cache do módulo — evita reimportar matplotlib e reconfigurar o backend por chart.
_mpl_plt = None


def init_mpl():
    """Bootstrap matplotlib Agg backend. Returns (plt, fig_to_bytes). Raises ImportError.

    Cacheado no módulo para evitar reimport por chart (~500ms de overhead por chamada
    sem cache). O backend Agg e as rcParams são configurados na primeira chamada.
    """
    global _mpl_plt
    if _mpl_plt is None:
        import matplotlib

        matplotlib.use("Agg")
        # bbox_inches="tight" dispara get_tightbbox() que mede texto de cada tick label
        # (~0.5s/figura × 17 figuras = ~8.5s). Substituído por pad_inches com margem fixa.
        matplotlib.rcParams.update({"savefig.bbox": None, "savefig.pad_inches": 0.1})
        import matplotlib.pyplot as plt

        _mpl_plt = plt

    plt = _mpl_plt

    def fig_to_bytes(fig, dpi: int = 150) -> bytes:
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=dpi)
        plt.close(fig)
        buf.seek(0)
        return buf.read()

    return plt, fig_to_bytes


def safe_close_mpl() -> None:
    """Fecha todas as figuras matplotlib abertas, ignorando falhas (ex.: backend ausente)."""
    try:
        import matplotlib.pyplot as _plt

        _plt.close("all")
    except Exception:  # pragma: no cover
        pass


def build_payload(face: str, granularidade: FaceGranularity, top_n: int, canonical, cubo) -> dict:
    """Convenience wrapper around build_cube_projection_payload."""
    from concilium.application.services.analytics.cube_projection_views import build_cube_projection_payload

    return build_cube_projection_payload(
        canonical=canonical,
        cubo=cubo,
        face=face,
        granularidade=granularidade,
        top_n=top_n,
    )
