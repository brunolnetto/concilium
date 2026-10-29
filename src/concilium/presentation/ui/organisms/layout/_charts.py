"""Camada de apresentação — layout Streamlit (parte extraída de layout.py)."""

from __future__ import annotations

from typing import Any, cast

import streamlit as st


def _to_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None


def _format_currency(value: object) -> str:
    parsed = _to_float(value)
    if parsed is None:
        return "-"
    abs_value = abs(parsed)
    if abs_value >= 1_000_000_000:
        return f"R$ {parsed / 1_000_000_000:,.2f} bi"
    if abs_value >= 1_000_000:
        return f"R$ {parsed / 1_000_000:,.2f} mi"
    return f"R$ {parsed:,.2f}"


def _format_percent(value: object) -> str:
    parsed = _to_float(value)
    if parsed is None:
        return "-"
    return f"{parsed * 100:,.2f}%"


def _format_int(value: object) -> str:
    parsed = _to_float(value)
    if parsed is None:
        return "-"
    return f"{int(round(parsed)):,}"


def _emoji_status(gap_rs: float) -> str:
    if gap_rs >= 0:
        return "✅"
    if gap_rs >= -5000:
        return "⚠️"
    return "🔴"


def _render_cube_line_chart(face: str, df: Any) -> None:
    """Renderiza o line chart para as combinações de face/colunas suportadas."""
    if face == "s_curve_custo" and {"periodo", "custo_acumulado_rs"}.issubset(df.columns):
        series = df.set_index("periodo")["custo_acumulado_rs"]
        st.line_chart(series)
        return
    if face == "recursos_ativos_tempo" and {"periodo", "n_equipes_totais", "equipamentos_unidades_ativas"}.issubset(
        df.columns
    ):
        multi = df.set_index("periodo")[["n_equipes_totais", "equipamentos_unidades_ativas"]]
        st.line_chart(multi)
        return
    if face == "diesel_temporal" and {"periodo", "consumo_diesel_l"}.issubset(df.columns):
        series = df.groupby("periodo", as_index=True)["consumo_diesel_l"].sum()
        st.line_chart(series)
        return
    if {"periodo", "componente_bdi", "valor_rs"}.issubset(df.columns):
        pivot = df.pivot_table(
            index="periodo",
            columns="componente_bdi",
            values="valor_rs",
            aggfunc="sum",
            fill_value=0,
        ).sort_index()
        st.line_chart(pivot)


def _render_cube_bar_stacked_chart(df: Any) -> None:
    """Renderiza o bar chart empilhado periodo × natureza."""
    if {"periodo", "natureza", "valor_rs"}.issubset(df.columns):
        pivot = df.pivot_table(
            index="periodo",
            columns="natureza",
            values="valor_rs",
            aggfunc="sum",
            fill_value=0,
        ).sort_index()
        st.bar_chart(pivot)


def _render_cube_bar_chart(df: Any) -> None:
    """Renderiza o bar chart por insumo (curva ABC)."""
    if {"insumo_id", "custo_total_rs"}.issubset(df.columns):
        series = df.set_index("insumo_id")["custo_total_rs"]
        st.bar_chart(series)


def _render_cube_heatmap_chart(df: Any) -> None:
    """Renderiza o heatmap categoria/atividade × componente BDI, com fallback se Altair indisponível."""
    try:
        import altair as alt
    except Exception:
        st.caption("Altair indisponível no ambiente; exibindo somente tabela.")
        return

    if {"categoria", "componente_bdi", "valor_rs"}.issubset(df.columns):
        heatmap = (
            cast(Any, alt.Chart(df))
            .mark_rect()
            .encode(
                x=alt.X("componente_bdi:N", title="Componente BDI"),
                y=alt.Y("categoria:N", title="Categoria"),
                color=alt.Color("valor_rs:Q", title="Valor (R$)"),
                tooltip=["categoria", "componente_bdi", alt.Tooltip("valor_rs:Q", format=",.2f")],
            )
        )
        st.altair_chart(heatmap, use_container_width=True)
        return

    if {"atividade_id", "componente_bdi", "valor_rs"}.issubset(df.columns):
        heatmap = (
            cast(Any, alt.Chart(df))
            .mark_rect()
            .encode(
                x=alt.X("componente_bdi:N", title="Componente BDI"),
                y=alt.Y("atividade_id:N", title="Atividade"),
                color=alt.Color("valor_rs:Q", title="Valor (R$)"),
                tooltip=["atividade_id", "componente_bdi", alt.Tooltip("valor_rs:Q", format=",.2f")],
            )
        )
        st.altair_chart(heatmap, use_container_width=True)


def _render_cube_projection_chart(face: str, chart_hint: str, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    try:
        import pandas as pd
    except Exception:
        st.caption("Pandas indisponível no ambiente; exibindo somente tabela.")
        return

    df = pd.DataFrame(rows)
    if df.empty:
        return

    if chart_hint == "line":
        _render_cube_line_chart(face, df)
    elif chart_hint == "bar_stacked":
        _render_cube_bar_stacked_chart(df)
    elif chart_hint == "bar":
        _render_cube_bar_chart(df)
    elif chart_hint == "heatmap":
        _render_cube_heatmap_chart(df)


