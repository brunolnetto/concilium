"""ADR-082: Tornado chart de levers de ponto de equilíbrio."""

from __future__ import annotations

from ._common import init_mpl


def build_painel_equilibrio(data: dict) -> bytes | None:
    levers = data.get("levers") or []
    if not levers:
        return None
    try:
        from matplotlib.lines import Line2D
        from matplotlib.patches import Patch

        plt, fig_to_bytes = init_mpl()
    except ImportError:
        return None

    delta_total = float(data.get("delta_total", 0.0))
    break_even_alcancavel = bool(data.get("break_even_alcancavel", False))
    combinacoes = data.get("combinacoes_break_even") or []
    deficit_mi = delta_total / 1e6
    frentes_nec_media = float(data.get("frentes_nec_media", 0.0))

    solo_ids: set[str] = {lid for c in combinacoes if c.get("tier") == 1 for lid in c.get("levers_ids", [])}
    combo_only_ids: set[str] = {
        lid for c in combinacoes if c.get("tier", 1) > 1 for lid in c.get("levers_ids", [])
    } - solo_ids

    values = [float(lv.get("delta_margin_total", 0.0)) / 1e6 for lv in levers]
    tipos = [lv.get("tipo", "custo") for lv in levers]
    solo_flags = [lv.get("break_even_solo", False) for lv in levers]

    acao_potencial = {
        "praticabilidade": 0.0,
        "escala_operacional": 0.0,
        "pool_eficiencia": 0.0,
    }
    for lv in levers:
        lid = str(lv.get("id", ""))
        delta = float(lv.get("delta_margin_total", 0.0) or 0.0)
        if lid == "fechar_gap_praticabilidade":
            acao_potencial["praticabilidade"] += delta
        elif lid == "fechar_gap_escala":
            acao_potencial["escala_operacional"] += delta
        elif lid == "fechar_gap_pool":
            acao_potencial["pool_eficiencia"] += delta

    labels = []
    restricoes_by_pos: dict[int, list[str]] = {}
    for i, lv in enumerate(levers):
        lid = lv["id"]
        descricao = lv.get("descricao") or lid.replace("_", " ")
        # Wrap descricao to ~30 chars per line for readability
        words = descricao.split()
        lines: list[str] = []
        current = ""
        for word in words:
            if current and len(current) + 1 + len(word) > 30:
                lines.append(current)
                current = word
            else:
                current = (current + " " + word).strip()
        if current:
            lines.append(current)
        base = "\n".join(lines)
        if lv.get("break_even_solo"):
            labels.append(f"★ {base}")
        elif lid in combo_only_ids:
            labels.append(f"◎ {base}")
        else:
            labels.append(base)
        restricoes = lv.get("restricoes") or []
        if restricoes:
            restricoes_by_pos[i] = restricoes

    colors_bar = ["#2e6da4" if t == "custo" else "#c05c18" for t in tipos]
    edge_colors = ["#f5c518" if s else "white" for s in solo_flags]
    edge_widths = [2.0 if s else 0.5 for s in solo_flags]

    try:
        fig, ax = plt.subplots(figsize=(10, max(4.0, 1.6 * len(levers) + 2.5)))
        y_pos = list(range(len(levers)))
        bars = ax.barh(
            y_pos,
            values,
            color=colors_bar,
            height=0.55,
            edgecolor=edge_colors,
            linewidth=edge_widths,
        )
        max_val = max(abs(v) for v in values) if values else 1e-9
        for bar, val, solo in zip(bars, values, solo_flags, strict=False):
            sign = "+" if val >= 0 else ""
            suffix = " ★" if solo else ""
            ax.text(
                bar.get_width() + 0.01 * max_val,
                bar.get_y() + bar.get_height() / 2,
                f"{sign}{val:.2f} Mi{suffix}",
                va="center",
                ha="left",
                fontsize=8,
                fontweight="bold" if solo else "normal",
            )
        ax.axvline(0, color="#222", linewidth=1.2, linestyle="-", alpha=0.8, zorder=3)
        if deficit_mi < 0:
            ax.axvline(abs(deficit_mi), color="#e74c3c", linewidth=1.5, linestyle="--", alpha=0.9, zorder=4)
            ax.axvspan(0, abs(deficit_mi), alpha=0.06, color="#e74c3c", zorder=0)
        ax.set_yticks(y_pos)
        ax.set_yticklabels(labels, fontsize=8)
        # Annotate restricoes below each lever bar
        for pos, restr_list in restricoes_by_pos.items():
            restr_text = " | ".join(restr_list)
            ax.text(
                0.01 * max_val,
                pos - 0.35,
                f"  ⚠ {restr_text}",
                va="top",
                ha="left",
                fontsize=6.5,
                color="#c05c18",
                style="italic",
            )
        ax.set_xlabel("Potencial de recuperacao de margem (R$ Mi)", fontsize=9)
        be_color = "#27ae60" if break_even_alcancavel else "#e74c3c"
        be_label = "Break-even alcancavel" if break_even_alcancavel else "Insuficiente para break-even"
        n_tier1 = sum(1 for c in combinacoes if c.get("tier") == 1)
        n_tier2 = sum(1 for c in combinacoes if c.get("tier") == 2)
        combo_summary = ""
        if n_tier1:
            combo_summary = f"{n_tier1} fator(es) individual(is) suficiente(s)"
            if n_tier2:
                combo_summary += f" | {n_tier2} par(es)"
        elif n_tier2:
            combo_summary = f"{n_tier2} par(es) suficiente(s)"
        pu_line = f"PU efetivo medio: {frentes_nec_media:.2f}x catalogo  |  " if frentes_nec_media > 1.01 else ""
        title_lines = ["Decomposicao de Ineficiencia: PU Efetivo vs Catalogo", f"{pu_line}{be_label}"]
        if combo_summary:
            title_lines.append(combo_summary)
        ax.set_title("\n".join(title_lines), fontsize=10, fontweight="bold", color=be_color)
        legend_elements = [
            Patch(facecolor="#2e6da4", label="Lever de custo"),
            Patch(facecolor="#c05c18", label="Lever de preco"),
            Patch(facecolor="none", edgecolor="#f5c518", linewidth=2, label="★ Break-even solo"),
        ]
        if deficit_mi < 0:
            legend_elements.append(
                Line2D(
                    [0], [0], color="#e74c3c", linestyle="--", linewidth=1.5, label=f"Deficit: {abs(deficit_mi):.2f} Mi"
                )
            )
        ax.legend(handles=legend_elements, fontsize=8, loc="lower right")
        ax.grid(axis="x", alpha=0.3)
        params_note = (
            "Leitura dos levers: praticabilidade (condicoes operacionais), escala operacional e eficiencia do pool.\n"
            "Tributos e premissas exogenas nao sao ajustados neste painel."
        )
        acao_lines = ["Acoes possiveis (potencial agregado):"]
        if acao_potencial["praticabilidade"]:
            acao_lines.append(f"- Praticabilidade: R$ {acao_potencial['praticabilidade'] / 1e6:.2f} Mi")
        if acao_potencial["escala_operacional"]:
            acao_lines.append(f"- Escala operacional: R$ {acao_potencial['escala_operacional'] / 1e6:.2f} Mi")
        if acao_potencial["pool_eficiencia"]:
            acao_lines.append(
                f"- Eficiencia de pool (ociosidade/mob-demob): R$ {acao_potencial['pool_eficiencia'] / 1e6:.2f} Mi"
            )
        if len(acao_lines) == 1:
            acao_lines.append("- Sem alavancas ativas no cenário atual")
        footer_text = params_note + "\n\n" + "\n".join(acao_lines)
        fig.text(
            0.02,
            0.01,
            footer_text,
            ha="left",
            va="bottom",
            fontsize=7.3,
            color="#1f2d3d",
            bbox=dict(facecolor="#f7fbff", alpha=0.96, edgecolor="#8bb3e8", boxstyle="round,pad=0.4"),
        )
        fig.subplots_adjust(bottom=0.24)
        fig.tight_layout(rect=[0, 0.2, 1, 1])
        return fig_to_bytes(fig)
    except Exception:
        plt.close("all")
        return None
