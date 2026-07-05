"""Atomic design molecules - Combinations of basic atoms."""

from __future__ import annotations

from html import escape

import streamlit as st

from ..atoms.elements import render_caption, render_info, render_selectbox


def render_project_selector(
    projects: list[dict],
    key_prefix: str = "project-selector",
    label: str = "Projeto ativo",
) -> dict | None:
    """Render project selection molecule."""
    if not projects:
        render_info("Nenhum projeto encontrado.")
        return None

    labels = [f"{p['nome']} [{p.get('tipo_projeto', 'hot_project')}]" for p in projects]
    idx = render_selectbox(
        label,
        options=list(range(len(labels))),
        index=0,
        key=f"{key_prefix}-select",
    )

    project = projects[idx]
    render_caption(f"**Projeto:** {project['nome']}")
    render_caption(f"**Versão:** {project.get('current_version') or '-'}")

    return project


def render_version_selector(
    versions: list[str],
    current: str | None = None,
    key_prefix: str = "version-selector",
) -> str:
    """Render version selection molecule."""
    if not versions:
        return current or "v1"

    default_idx = 0
    if current and current in versions:
        default_idx = versions.index(current)

    return render_selectbox(
        "Versão",
        options=versions,
        index=default_idx,
        key=f"{key_prefix}-select",
    )


def render_stat_row(metrics: list[tuple[str, str | int | float]]) -> None:
    """Render horizontal stat row (multiple metrics)."""
    cols = st.columns(len(metrics))
    for col, (label, value) in zip(cols, metrics, strict=False):
        col.metric(label, value)


def render_info_row(items: list[tuple[str, str]]) -> None:
    """Render horizontal info row (key-value pairs)."""
    cols = st.columns(len(items))
    for col, (label, value) in zip(cols, items, strict=False):
        with col:
            st.caption(f"**{label}:** {value}")


def render_tab_header(title: str, description: str | None = None) -> None:
    """Render tab header with optional description."""
    st.header(title)
    if description:
        st.caption(description)


def render_page_heading(title: str, subtitle: str | None = None) -> None:
    """Render standardized page heading with visual hierarchy."""
    subtitle_html = f"<p class='subtitle'>{escape(subtitle)}</p>" if subtitle else ""
    st.markdown(
        (f"<section class='ui-page-hero'><p class='title'>{escape(title)}</p>{subtitle_html}</section>"),
        unsafe_allow_html=True,
    )


def render_kpi_cards(metrics: list[dict[str, str | int | float]]) -> None:
    """Render reusable KPI cards."""
    if not metrics:
        return
    cols = st.columns(len(metrics))
    for idx, (col, metric) in enumerate(zip(cols, metrics, strict=False)):
        label = escape(str(metric.get("label", "-")))
        value = escape(str(metric.get("value", "-")))
        delta_raw = metric.get("delta")
        delta_html = ""
        if delta_raw not in (None, ""):
            delta_html = f"<div class='ui-kpi-delta'>{escape(str(delta_raw))}</div>"
        with col:
            st.markdown(
                (
                    f"<article class='ui-kpi-card' style='--ui-stagger-index:{idx};'>"
                    f"<div class='ui-kpi-label'>{label}</div>"
                    f"<div class='ui-kpi-value'>{value}</div>"
                    f"{delta_html}"
                    "</article>"
                ),
                unsafe_allow_html=True,
            )


def render_standard_table(
    title: str,
    rows: list[dict],
    empty_message: str = "Sem dados para exibir.",
    height: int = 320,
) -> None:
    """Render standardized table used across UI pages."""
    st.markdown(f"<p class='ui-table-title'>{escape(title)}</p>", unsafe_allow_html=True)
    if not rows:
        st.info(empty_message)
        return
    st.dataframe(
        rows,
        width="stretch",
        hide_index=True,
        height=height,
    )


# ── Paginação reutilizável ─────────────────────────────────────────────────────

_DEFAULT_PAGE_SIZE = 25


def render_paginated_table(
    items: list,
    page_key: str,
    columns: list[str] | None = None,
    page_size: int = _DEFAULT_PAGE_SIZE,
    label: str = "",
    hide_index: bool = True,
    use_container_width: bool = True,
    on_select: str | None = None,
) -> tuple[list, object | None]:
    """Renders a paginated st.dataframe with prev/next navigation.

    Returns (current_page_items, dataframe_result).
    dataframe_result has .selection if on_select is set.
    """
    total = len(items)
    n_pages = max(1, (total + page_size - 1) // page_size)

    if page_key not in st.session_state:
        st.session_state[page_key] = 0
    page = min(int(st.session_state[page_key]), n_pages - 1)
    st.session_state[page_key] = page

    start = page * page_size
    page_items = items[start : start + page_size]

    # Sempre 3 colunas [1, 5, 1] — botões só aparecem quando aplicáveis.
    # Garante info sempre centralizado, sem deslocamento.
    has_prev = page > 0
    has_next = page < n_pages - 1
    suffix = f" {label}" if label else ""
    # HTML: <strong> em vez de **markdown** (markdown não renderiza dentro de <div>)
    info_html = (
        f"<div style='text-align:center;padding:0.35rem 0;font-size:0.85rem;'>"
        f"<strong>{total}</strong>{suffix} &nbsp;·&nbsp; página {page + 1}/{n_pages}"
        f"</div>"
    )

    col_prev, col_info, col_next = st.columns([1, 5, 1])
    with col_prev:
        if has_prev and st.button("←", key=f"{page_key}-prev", type="secondary", use_container_width=True):
            st.session_state[page_key] = page - 1
            st.rerun()
    col_info.markdown(info_html, unsafe_allow_html=True)
    with col_next:
        if has_next and st.button("→", key=f"{page_key}-next", type="secondary", use_container_width=True):
            st.session_state[page_key] = page + 1
            st.rerun()

    kwargs: dict = {"use_container_width": use_container_width, "hide_index": hide_index}
    if on_select:
        kwargs["on_select"] = on_select
        kwargs["selection_mode"] = "single-row"
        kwargs["key"] = f"{page_key}-df-p{page}"

    result = st.dataframe(page_items, **kwargs)
    return page_items, result


def invalidate_page(page_key: str) -> None:
    """Reset page counter to 0 (call when filter changes)."""
    st.session_state[page_key] = 0
