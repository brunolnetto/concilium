"""Legacy fallback charts from relatorio dict (used when cube projection yields no rows)."""

from __future__ import annotations

from ._common import init_mpl

SHIM_ID = "visualizations.cube.legacy_fallback"
SHIM_TARGET = "cube projection charts"
SHIM_SCOPE = "runtime-fallback"


def build_legacy_fallback(relatorio: dict) -> dict[str, bytes]:
    if not isinstance(relatorio, dict):
        return {}
    try:
        plt, fig_to_bytes = init_mpl()
    except ImportError:
        return {}

    out: dict[str, bytes] = {}

    # 1) Utilizacao de contratos -> bar_tempo_natureza.png
    resumos = [row for row in (relatorio.get("resumo_utilizacao_contratos") or []) if isinstance(row, dict)]
    if resumos:
        try:
            tipos = [str(row.get("tipo_id", "?")) for row in resumos]
            ativos = [int(row.get("machine_weeks_usados", 0) or 0) for row in resumos]
            standby = [int(row.get("machine_weeks_standby", 0) or 0) for row in resumos]
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
            out["bar_tempo_natureza.png"] = fig_to_bytes(fig)
        except Exception:
            plt.close("all")

    # 2) Instancias de recurso -> linha_recursos_tempo.png
    instancias = [row for row in (relatorio.get("instancias_recurso") or []) if isinstance(row, dict)]
    if instancias:
        try:
            from collections import defaultdict as _dd

            by_tipo: dict[str, list[dict]] = _dd(list)
            for row in instancias:
                by_tipo[str(row.get("tipo_id", "?"))].append(row)
            tipos = sorted(by_tipo.keys())
            n_cols = min(max(1, len(tipos)), 4)
            n_rows = (len(tipos) + n_cols - 1) // n_cols
            fig, axes = plt.subplots(
                n_rows, n_cols,
                figsize=(max(7, n_cols * 4.5), max(4, n_rows * 3.6)),
                squeeze=False,
            )
            flat_axes = [axes[r][c] for r in range(n_rows) for c in range(n_cols)]
            for axis, tipo in zip(flat_axes, tipos):
                rows_t = sorted(by_tipo[tipo], key=lambda item: int(item.get("numero", 0) or 0))
                xv = list(range(len(rows_t)))
                ativas = [int(item.get("semanas_ativas", 0) or 0) for item in rows_t]
                standby = [int(item.get("semanas_standby", 0) or 0) for item in rows_t]
                axis.bar(xv, ativas, color="#1a3a5c", alpha=0.85, label="Ativas")
                axis.bar(xv, standby, bottom=ativas, color="#c05c18", alpha=0.65, label="Standby")
                axis.set_xticks(xv)
                axis.set_xticklabels(
                    [str(item.get("instancia_id", "")).split("-")[-1] for item in rows_t],
                    fontsize=8,
                )
                axis.set_title(tipo, fontsize=10, fontweight="bold")
                axis.grid(axis="y", alpha=0.3)
            for axis in flat_axes[len(tipos):]:
                axis.set_visible(False)
            fig.suptitle("Instancias de Recurso", fontsize=12, fontweight="bold")
            fig.tight_layout()
            out["linha_recursos_tempo.png"] = fig_to_bytes(fig)
        except Exception:
            plt.close("all")

    # 3) Composicao por item -> bar_categoria_componente.png
    plano = [row for row in (relatorio.get("PLANEJAMENTO") or []) if isinstance(row, dict)]
    if plano:
        try:
            items = [str(row.get("item_id", "?")) for row in plano]
            mo = [float(row.get("subtotal_sem_bdi_mo", 0) or 0) / 1e6 for row in plano]
            eq = [float(row.get("subtotal_sem_bdi_eq", 0) or 0) / 1e6 for row in plano]
            diesel = [float(row.get("subtotal_sem_bdi_diesel", 0) or 0) / 1e6 for row in plano]
            material = [float(row.get("subtotal_sem_bdi_mat", 0) or 0) / 1e6 for row in plano]
            y = list(range(len(items)))
            fig, ax = plt.subplots(figsize=(12, max(4, len(items) * 0.65 + 2)))
            left_eq = mo
            left_diesel = [m + e for m, e in zip(mo, eq)]
            left_material = [m + e + d for m, e, d in zip(mo, eq, diesel)]
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
            out["bar_categoria_componente.png"] = fig_to_bytes(fig)
        except Exception:
            plt.close("all")

    # 4) Ponto de equilibrio -> bar_atividade_componente.png
    pe_rows = [row for row in (relatorio.get("ponto_equilibrio") or []) if isinstance(row, dict)]
    pe_rows = [row for row in pe_rows if float(row.get("custo_venda_cpu", 0) or 0) > 0]
    if pe_rows:
        try:
            items = [str(row.get("item_id", "?")) for row in pe_rows]
            venda = [float(row.get("custo_venda_cpu", 0) or 0) / 1e6 for row in pe_rows]
            operacional = [float(row.get("custo_operacional_real", 0) or 0) / 1e6 for row in pe_rows]
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
            out["bar_atividade_componente.png"] = fig_to_bytes(fig)
        except Exception:
            plt.close("all")

    return out


__all__ = [
    "SHIM_ID",
    "SHIM_TARGET",
    "SHIM_SCOPE",
    "build_legacy_fallback",
]
