"""bar_tempo_indireto_categoria.png — Custo Indireto por Categoria no Tempo."""

from __future__ import annotations

from ._common import build_payload, init_mpl
from ._renderers import render_stacked_bar


def build(canonical, cubo) -> bytes | None:
    try:
        payload = build_payload("indireto_temporal_categoria", "mes", 360, canonical, cubo)
    except Exception:
        return None

    rows = payload.get("rows") or []
    columns = payload.get("columns") or []
    if not rows:
        return None

    use_millions = payload.get("unit_type") == "currency_brl"
    try:
        plt, fig_to_bytes = init_mpl()
    except ImportError:
        return None

    try:
        fig = render_stacked_bar(
            plt,
            rows,
            columns,
            "Custo Indireto no Tempo por Categoria",
            use_millions,
            show_normalized=False,
            annotate_bdi=False,
        )
        return fig_to_bytes(fig) if fig is not None else None
    except Exception:
        try:
            import matplotlib.pyplot as _plt

            _plt.close("all")
        except Exception:
            pass
        return None
