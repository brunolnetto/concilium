"""bar_tempo_natureza.png — Custo Direto vs. Indireto por Período."""

from __future__ import annotations

from ._common import build_payload, init_mpl
from ._renderers import render_stacked_bar


def build(canonical, cubo) -> bytes | None:
    try:
        payload = build_payload("tempo_natureza", "mes", 120, canonical, cubo)
    except Exception:
        return None

    rows = payload.get("rows")
    if not rows:
        return None

    columns = payload.get("columns", [])
    unit_type = payload.get("unit_type", "currency_brl")
    use_millions = unit_type == "currency_brl"

    try:
        plt, fig_to_bytes = init_mpl()
    except ImportError:
        return None

    try:
        fig = render_stacked_bar(
            plt,
            rows,
            columns,
            "Custo Direto vs. Indireto por Período",
            use_millions,
        )
        if fig is None:
            return None
        return fig_to_bytes(fig)
    except Exception:
        import matplotlib.pyplot as _mpl

        try:
            _mpl.close("all")
        except Exception:
            pass
        return None
