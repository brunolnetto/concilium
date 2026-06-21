"""Shared helpers for runtime charts (histogramas, gantt, financeiro, etc.)."""

from __future__ import annotations

import io

HIST_COLORS = ["#1a3a5c", "#c05c18", "#5aabdc", "#e8a030", "#5adc8e", "#a07ad8", "#dc5a8e"]

_SERIES_LABEL_MAP: dict[str, str] = {
    "overhead_AC": "Adm. Central (AC)",
    "overhead_DF": "Desp. Financeiras (DF)",
    "overhead_R": "Risco / Seguro (R)",
    "overhead_L": "Lucro (L)",
    "tributo_ISS": "ISS",
    "tributo_CSSL": "Contrib. Social (CSLL)",
    "tributo_IR": "Imp. de Renda (IR)",
}


def clean_series_label(sname: str) -> str:
    return _SERIES_LABEL_MAP.get(sname, sname.replace("_", " ").title())


_mpl_plt = None


def init_mpl():
    """Bootstrap matplotlib Agg backend. Cacheado no módulo para evitar reimport.

    Returns (plt, fig_to_bytes_fn). Raises ImportError if matplotlib is absent.
    """
    global _mpl_plt
    if _mpl_plt is None:
        import matplotlib

        matplotlib.use("Agg")
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
