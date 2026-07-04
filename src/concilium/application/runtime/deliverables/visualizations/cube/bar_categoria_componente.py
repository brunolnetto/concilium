"""bar_categoria_componente.png — Composição de Custo por Categoria (com anotação BDI)."""

from __future__ import annotations

from ._common import build_payload, init_mpl, safe_close_mpl
from ._renderers import render_stacked_bar


def build(canonical, cubo) -> bytes | None:
    try:
        payload = build_payload("categoria_componente", "mes", 120, canonical, cubo)
    except Exception:
        return None
    rows = payload.get("rows") or []
    columns = payload.get("columns") or []
    if not rows:
        return None
    use_millions = payload.get("unit_type") == "currency_brl"
    try:
        plt, fig_to_bytes = init_mpl()
        fig = render_stacked_bar(
            plt,
            rows,
            columns,
            "Composicao de Custo por Categoria",
            use_millions,
            show_normalized=False,
            annotate_bdi=False,
        )
        return fig_to_bytes(fig) if fig is not None else None
    except Exception:
        safe_close_mpl()
        return None
