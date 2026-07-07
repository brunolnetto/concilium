"""Fallback charts from relatorio dict when cube projection yields no rows."""

from __future__ import annotations

from ._common import init_mpl


def _int0(v: int | float | str | None) -> int:
    """Coerce a possibly-None/falsy numeric value to int, defaulting to 0."""
    return int(v or 0)


def _float0(v: int | float | str | None) -> float:
    """Coerce a possibly-None/falsy numeric value to float, defaulting to 0."""
    return float(v or 0)


def _dict_rows(items: list | None) -> list[dict]:
    """Filter a (possibly None) sequence down to its dict entries."""
    return [row for row in (items or []) if isinstance(row, dict)]


def _build_bar_tempo_natureza(relatorio: dict, plt, fig_to_bytes) -> tuple[str, bytes] | None:
    """1) Utilizacao de contratos -> bar_tempo_natureza.png"""
    resumos = _dict_rows(relatorio.get("resumo_utilizacao_contratos"))
    if not resumos:
        return None
    try:
        tipos = [str(row.get("tipo_id", "?")) for row in resumos]
        ativos = [_int0(row.get("machine_weeks_usados", 0)) for row in resumos]
        standby = [_int0(row.get("machine_weeks_standby", 0)) for row in resumos]
        y = list(range(len(tipos)))
        fig, ax = plt.subplots(figsize=(12, max(4, len(tipos) * 0.75 + 2)))
        ax.barh(y, ativos, color="#1a3a5c", alpha=0.85, label="Ativos")
        ax.barh(y, standby, left=ativos, color="#c05c18", alpha=0.65, label="Standby")
        ax.set_yticks(y)
        ax.set_yticklabels(tipos, fontsize=9)
        ax.set_xlabel("Machine-Weeks", fontsize=9)
        ax.set_title("Utilizacao de Contratos", fontsize=12, fontweight="bold")
        ax.grid(axis="x", alpha=0.3)
        ax.legend(fontsize=8)
        fig.tight_layout()
        return "bar_tempo_natureza.png", fig_to_bytes(fig)
    except Exception:
        plt.close("all")
        return None


def _plot_instancia_axis(axis, tipo: str, rows_t: list[dict]) -> None:
    """Plota o subplot de ativas/standby para um único tipo de recurso."""
    rows_t = sorted(rows_t, key=lambda item: _int0(item.get("numero", 0)))
    xv = list(range(len(rows_t)))
    ativas = [_int0(item.get("semanas_ativas", 0)) for item in rows_t]
    standby = [_int0(item.get("semanas_standby", 0)) for item in rows_t]
    axis.bar(xv, ativas, color="#1a3a5c", alpha=0.85, label="Ativas")
    axis.bar(xv, standby, bottom=ativas, color="#c05c18", alpha=0.65, label="Standby")
    axis.set_xticks(xv)
    axis.set_xticklabels(
        [str(item.get("instancia_id", "")).split("-")[-1] for item in rows_t],
        fontsize=8,
    )
    axis.set_title(tipo, fontsize=10, fontweight="bold")
    axis.grid(axis="y", alpha=0.3)


def _build_linha_recursos_tempo(relatorio: dict, plt, fig_to_bytes) -> tuple[str, bytes] | None:
    """2) Instancias de recurso -> linha_recursos_tempo.png"""
    instancias = _dict_rows(relatorio.get("instancias_recurso"))
    if not instancias:
        return None
    try:
        from collections import defaultdict as _dd

        by_tipo: dict[str, list[dict]] = _dd(list)
        for row in instancias:
            by_tipo[str(row.get("tipo_id", "?"))].append(row)
        tipos = sorted(by_tipo.keys())
        n_cols = min(max(1, len(tipos)), 4)
        n_rows = (len(tipos) + n_cols - 1) // n_cols
        fig, axes = plt.subplots(
            n_rows,
            n_cols,
            figsize=(max(7, n_cols * 4.5), max(4, n_rows * 3.6)),
            squeeze=False,
        )
        flat_axes = [axes[r][c] for r in range(n_rows) for c in range(n_cols)]
        for axis, tipo in zip(flat_axes, tipos, strict=False):
            _plot_instancia_axis(axis, tipo, by_tipo[tipo])
        for axis in flat_axes[len(tipos) :]:
            axis.set_visible(False)
        fig.suptitle("Instancias de Recurso", fontsize=12, fontweight="bold")
        fig.tight_layout()
        return "linha_recursos_tempo.png", fig_to_bytes(fig)
    except Exception:
        plt.close("all")
        return None


def _build_bar_categoria_componente(relatorio: dict, plt, fig_to_bytes) -> tuple[str, bytes] | None:
    """3) Composicao por item -> bar_categoria_componente.png"""
    plano = _dict_rows(relatorio.get("PLANEJAMENTO"))
    if not plano:
        return None
    try:
        items = [str(row.get("item_id", "?")) for row in plano]
        mo = [_float0(row.get("subtotal_sem_bdi_mo", 0)) / 1e6 for row in plano]
        eq = [_float0(row.get("subtotal_sem_bdi_eq", 0)) / 1e6 for row in plano]
        diesel = [_float0(row.get("subtotal_sem_bdi_diesel", 0)) / 1e6 for row in plano]
        material = [_float0(row.get("subtotal_sem_bdi_mat", 0)) / 1e6 for row in plano]
        y = list(range(len(items)))
        fig, ax = plt.subplots(figsize=(12, max(4, len(items) * 0.65 + 2)))
        left_eq = mo
        left_diesel = [m + e for m, e in zip(mo, eq, strict=False)]
        left_material = [m + e + d for m, e, d in zip(mo, eq, diesel, strict=False)]
        ax.barh(y, mo, color="#1a3a5c", alpha=0.9, label="MO")
        ax.barh(y, eq, left=left_eq, color="#2e6da4", alpha=0.85, label="EQ")
        ax.barh(y, diesel, left=left_diesel, color="#e8a030", alpha=0.85, label="Diesel")
        ax.barh(y, material, left=left_material, color="#5aabdc", alpha=0.8, label="Material")
        ax.set_yticks(y)
        ax.set_yticklabels(items, fontsize=8)
        ax.set_xlabel("R$ (Mi)", fontsize=9)
        ax.set_title("Composicao de Custo por Item", fontsize=12, fontweight="bold")
        ax.grid(axis="x", alpha=0.3)
        ax.legend(fontsize=8)
        fig.tight_layout()
        return "bar_categoria_componente.png", fig_to_bytes(fig)
    except Exception:
        plt.close("all")
        return None


def _build_bar_atividade_componente(relatorio: dict, plt, fig_to_bytes) -> tuple[str, bytes] | None:
    """4) Ponto de equilibrio -> bar_atividade_componente.png"""
    pe_rows = _dict_rows(relatorio.get("ponto_equilibrio"))
    pe_rows = [row for row in pe_rows if _float0(row.get("custo_venda_cpu", 0)) > 0]
    if not pe_rows:
        return None
    try:
        items = [str(row.get("item_id", "?")) for row in pe_rows]
        venda = [_float0(row.get("custo_venda_cpu", 0)) / 1e6 for row in pe_rows]
        operacional = [_float0(row.get("custo_operacional_real", 0)) / 1e6 for row in pe_rows]
        y = list(range(len(items)))
        height = 0.35
        fig, ax = plt.subplots(figsize=(12, max(4, len(items) * 0.65 + 2)))
        ax.barh([idx + height / 2 for idx in y], venda, height, color="#1a3a5c", alpha=0.85, label="Venda")
        ax.barh([idx - height / 2 for idx in y], operacional, height, color="#c05c18", alpha=0.75, label="Operacional")
        ax.set_yticks(y)
        ax.set_yticklabels(items, fontsize=8)
        ax.set_xlabel("R$ (Mi)", fontsize=9)
        ax.set_title("Ponto de Equilibrio por Item", fontsize=12, fontweight="bold")
        ax.grid(axis="x", alpha=0.3)
        ax.legend(fontsize=8)
        fig.tight_layout()
        return "bar_atividade_componente.png", fig_to_bytes(fig)
    except Exception:
        plt.close("all")
        return None


def build_relatorio_fallback(relatorio: dict) -> dict[str, bytes]:
    if not isinstance(relatorio, dict):
        return {}
    try:
        plt, fig_to_bytes = init_mpl()
    except ImportError:
        return {}

    out: dict[str, bytes] = {}

    for builder in (
        _build_bar_tempo_natureza,
        _build_linha_recursos_tempo,
        _build_bar_categoria_componente,
        _build_bar_atividade_componente,
    ):
        result = builder(relatorio, plt, fig_to_bytes)
        if result is not None:
            name, data = result
            out[name] = data

    return out


__all__ = [
    "build_relatorio_fallback",
]
