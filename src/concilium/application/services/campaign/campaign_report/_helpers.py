"""ADR-070 — Campaign report generation — helpers de formatação e extração de vetores."""

from __future__ import annotations

import html


def _safe(v: object) -> str:
    return html.escape(str(v or ""), quote=False)


def _fmt_pct(v: float | None) -> str:
    if v is None:
        return "-"
    x = float(v)
    if -1.0 <= x <= 1.0:
        x *= 100.0
    return f"{x:.1f}%"


def _fmt_f2(v: float | None) -> str:
    return f"{v:.2f}" if v is not None else "-"


def _fmt_f3(v: float | None) -> str:
    return f"{v:.3f}" if v is not None else "-"


def _fmt_int(v: int | float | None) -> str:
    return str(int(v)) if v is not None else "-"


def _vetor_O_dict(v) -> dict:
    return {
        "prazo_semanas": v.prazo_semanas,
        "folga_semanas": v.folga_semanas,
        "fe_nec_medio": v.fe_nec_medio,
        "itens_criticos_pct": v.itens_criticos_pct,
        "gap_pool_total": v.gap_pool_total,
        "custo_mob_window_total": v.custo_mob_window_total,
        "utilizacao_recursos_pct": v.utilizacao_recursos_pct,
        "paralelismo_medio": v.paralelismo_medio,
        "idle_pool_pct": v.idle_pool_pct,
    }


def _vetor_EF_dict(v) -> dict:
    return {
        "margem_pct": v.margem_pct,
        "custo_execucao_pool": v.custo_execucao_pool,
        "custo_indireto": v.custo_indireto,
        "preco_venda": v.preco_venda,
        "ratio_pool_vs_cat": v.ratio_pool_vs_cat,
        "fidelidade_gates": v.fidelidade_gates,
        "share_mo_pct": v.share_mo_pct,
        "share_eq_pct": v.share_eq_pct,
        "share_comb_pct": v.share_comb_pct,
        "concentracao_atividade": v.concentracao_atividade,
    }


