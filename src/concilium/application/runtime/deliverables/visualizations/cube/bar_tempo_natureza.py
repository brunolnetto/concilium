"""bar_tempo_natureza.png — Custo Direto vs. Indireto por Período."""

from __future__ import annotations

from ._common import build_payload, init_mpl
from ._renderers import render_stacked_bar


def build(canonical, cubo) -> bytes | None:
    try:
        payload = build_payload("tempo_natureza", "mes", 120, canonical, cubo)
    except Exception:
        return None
    rows = payload.get("rows") or []
    columns = payload.get("columns") or []
    if not rows:
        return None
    use_millions = payload.get("unit_type") == "currency_brl"
    try:
        plt, fig_to_bytes = init_mpl()
        fig = render_stacked_bar(plt, rows, columns, "Custo Direto vs. Indireto por Periodo", use_millions)
        return fig_to_bytes(fig) if fig is not None else None
    except Exception:
        try:
            import matplotlib.pyplot as _plt

            _plt.close("all")
        except Exception:
            pass
        return None
