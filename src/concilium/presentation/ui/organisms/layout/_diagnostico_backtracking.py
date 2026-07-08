"""Camada de apresentação — layout Streamlit (parte extraída de layout.py)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import streamlit as st

if TYPE_CHECKING:
    from collections.abc import Callable

    from concilium.domain.models.analytics.diagnostico_pe import DiagnosticoPEItem, DiagnosticoPERelatorio
    from concilium.domain.models.financial.backtracking_pe import (
        BacktrackingPEItem,
        BacktrackingPERelatorio,
        SolucaoInversa,
    )

from ._charts import _emoji_status


def render_diagnostico_pe(
    base_url: str,
    project_id: str,
    actor: str,
    diagnostico: DiagnosticoPERelatorio | None = None,  # type: ignore[name-defined]
) -> None:
    """Painel de equilíbrio financeiro em linguagem simples (ADR-060)."""
    if diagnostico is None:
        return
    if diagnostico.n_itens_deficit == 0:
        st.success("✅ Todas as atividades estão no equilíbrio financeiro.", icon=None)
        return
    with st.expander(
        f"⚠️ {diagnostico.n_itens_deficit} atividade(s) com custo acima do orçamento — "
        f"custo extra: R$ {abs(diagnostico.gap_total_rs):,.0f}",
        expanded=True,
    ):
        st.markdown("**Por que está custando mais?**")
        causas = diagnostico.resumo_causas
        total_causas = sum(causas.values()) or 1
        for label, valor in causas.items():
            pct = round(valor / total_causas * 100)
            barra = "█" * max(1, pct // 5) + "░" * (20 - max(1, pct // 5))
            st.markdown(f"`{barra}` **{label}** — R$ {valor:,.0f} ({pct}%)")
        if diagnostico.gap_evitavel_rs > 50:
            st.info(
                f"R$ {diagnostico.gap_evitavel_rs:,.0f} deste custo pode ser evitado"
                " com ajustes de cronograma ou mobilização.",
                icon=None,
            )
        if diagnostico.aviso_cross_term:
            st.warning(
                "⚠️ Em pelo menos uma atividade, a mobilização coincidiu com o período de pior clima."
                " Esse custo duplo pode ser evitado mudando a época de início."
            )
        st.markdown("---")
        st.markdown("**Detalhes por atividade:**")
        for item in diagnostico.itens_deficit:
            _render_diagnostico_item(item)


def _render_diagnostico_item(item: DiagnosticoPEItem) -> None:
    """Renders one deficit item in the diagnostico expander."""
    with st.expander(
        f"{_emoji_status(item.gap_rs)} {item.descricao[:60]} — custo extra: R$ {abs(item.gap_rs):,.0f}",
        expanded=False,
    ):
        col1, col2, col3 = st.columns(3)
        col1.metric(
            "Aproveitamento de campo",
            f"{item.aproveitamento_pct:.0f}%",
            help="Das horas em que a equipe esteve no canteiro, esta fração foi produtiva.",
        )
        col2.metric("Margem atual", f"{item.l_aplicado * 100:.1f}%")
        col3.metric(
            "Margem mínima necessária",
            f"{item.l_requerido * 100:.1f}%",
            delta=f"+{item.delta_l * 100:.1f}pp necessário",
            delta_color="inverse",
        )
        st.caption("Causas identificadas:")
        for f in item.fatores:
            evit = "✂️ evitável" if f.evitavel else "🔩 estrutural"
            st.markdown(f"- **{f.label}** — R$ {f.gap_rs:,.0f} ({f.pct_gap * 100:.0f}%) · {evit}")
            st.caption(f"  {f.descricao}")
        if not item.validez_aproximacao:  # type: ignore[union-attr]
            st.warning(
                "⚠️ A mobilização desta atividade coincidiu com o período de pior clima. "
                f"Isso criou um custo extra de R$ {abs(item.cov_n_p * item.n_total * 100):,.0f} "  # type: ignore[union-attr]
                "aproximado. Iniciar a mobilização na estação seca pode eliminar este custo.",
            )


def _render_sol_row(i: int, sol: SolucaoInversa, cols: list) -> None:
    """Renders one solution row in a backtracking expander."""
    cols[0].markdown(f"**{chr(65 + i)}** — {sol.label}")
    cols[0].caption(sol.descricao_delta)
    repasse = f"+{sol.impacto_preco_pct:.1f}%" if sol.impacto_preco_pct > 0.1 else "Nenhum"
    cols[1].metric("Repasse ao cliente", repasse)
    esforco = f"+{sol.impacto_produtividade_pct:.0f}%" if sol.impacto_produtividade_pct > 0.5 else "—"
    cols[2].metric("Esforço operacional", esforco)
    if sol.impacto_prazo_semanas != 0:
        direction = "−" if sol.impacto_prazo_semanas < 0 else "+"
        cols[3].metric("Prazo", f"{direction}{abs(sol.impacto_prazo_semanas):.0f} sem.")


def _render_backtrack_item_body(item: BacktrackingPEItem) -> None:
    """Renders the body of one backtracking item expander."""
    validas = [s for s in item.solucoes if s.roundtrip_valido]
    if not validas:
        st.info("Nenhuma solução foi confirmada automaticamente para esta atividade.")
        return
    st.caption(f"Gap atual: R$ {abs(item.pe_gap_atual):,.0f} | Alvo: equilíbrio (R$ 0)")
    for i, sol in enumerate(validas):
        cols = st.columns([5, 2, 2, 2])
        _render_sol_row(i, sol, cols)
    if item.solucao_recomendada:
        rec = item.solucao_recomendada
        idx = validas.index(rec) if rec in validas else 0
        st.success(f"✨ Opção recomendada: **{chr(65 + idx)} — {rec.label}** ({rec.impacto_cliente_descricao})")


def render_backtracking_pe(
    backtracking: BacktrackingPERelatorio | None = None,
    on_create_version: Callable[..., object] | None = None,
) -> None:
    """Painel de soluções para fechar o gap de PE (ADR-061)."""
    if backtracking is None or not backtracking.itens:
        return
    aviso = backtracking.aviso_consistencia
    if aviso:
        st.caption(f"ℹ️ {aviso}")
    for item in backtracking.itens:
        if not item.solucoes:
            continue
        with st.expander(f"💡 Como equilibrar: {item.descricao[:55]}", expanded=False):
            _render_backtrack_item_body(item)


