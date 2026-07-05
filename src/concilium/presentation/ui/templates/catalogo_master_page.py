"""Master catalog management page — browse CPUs, insumos, and search across catalogs."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

try:
    from ..config import DEFAULT_ACTOR, DEFAULT_BASE_URL
    from ..helpers.helpers import dataframe_selected_rows
    from ..infra.api import api_call
    from ..molecules.common import render_page_heading
except ImportError:
    src_root = Path(__file__).resolve().parents[4]
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))
    from concilium.presentation.ui.config import DEFAULT_ACTOR, DEFAULT_BASE_URL
    from concilium.presentation.ui.helpers.helpers import dataframe_selected_rows
    from concilium.presentation.ui.infra.api import api_call
    from concilium.presentation.ui.molecules.common import render_page_heading

from ._catalogo_master_helpers import (
    _cmb_build_cpu_rows,
    _cmb_build_insumo_rows,
    _cmb_clear_catalog_cache,
    _cmb_filter_cpus,
    _cmb_filter_insumos,
    _cmb_get_categorias,
    _cmb_handle_cpu_selection,
    _cmb_render_cpu_nav,
)

_PAGE_SIZE = 30


def render_catalogo_master_page() -> None:
    render_page_heading(
        "Catálogo Mestre",
        "Consulte e gerencie CPUs, insumos e produções do catálogo corporativo.",
    )

    base_url = DEFAULT_BASE_URL
    actor = DEFAULT_ACTOR

    try:
        resp = api_call("GET", "/api/catalogs", base_url=base_url, actor=actor)
        catalogs = [c["id"] for c in (resp.get("items") or []) if c.get("id")]
    except Exception as exc:
        st.error(f"Não foi possível listar catálogos: {exc}")
        return

    if not catalogs:
        st.warning("Nenhum catálogo encontrado em `config/catalogos/`.")
        return

    col_sel, col_n_cpus, col_n_ins = st.columns([4, 1, 1])
    with col_sel:
        catalog_id = st.selectbox("Catálogo", options=catalogs, key="master-cat-id")
    try:
        stat = api_call("GET", f"/api/catalogs/{catalog_id}", base_url=base_url, actor=actor)
        col_n_cpus.metric("CPUs", stat.get("n_cpus", "—"))
        col_n_ins.metric("Insumos", stat.get("n_insumos", "—"))
    except Exception:
        pass

    st.divider()
    tab_cpus, tab_insumos = st.tabs(["🔧 CPUs", "🧱 Insumos"])

    with tab_cpus:
        _render_cpu_browser(base_url, actor, catalog_id)

    with tab_insumos:
        _render_insumo_browser(base_url, actor, catalog_id)


# ─── CPUs ─────────────────────────────────────────────────────────────────────


def _render_cpu_browser(base_url: str, actor: str, catalog_id: str) -> None:
    cache_key = f"master-cpus-all-{catalog_id}"
    if cache_key not in st.session_state:
        try:
            resp = api_call(
                "GET", f"/api/catalogs/{catalog_id}/cpus", params={"limit": 500}, base_url=base_url, actor=actor
            )
            st.session_state[cache_key] = resp.get("items", [])
        except Exception as exc:
            st.error(f"Erro ao carregar CPUs: {exc}")
            return

    all_cpus: list[dict] = st.session_state[cache_key]

    col_q, col_cat, col_ref = st.columns([3, 2, 1])
    q = col_q.text_input(
        "Buscar", placeholder="Código ou descrição…", key=f"master-cpu-q-{catalog_id}", label_visibility="collapsed"
    )
    categorias = _cmb_get_categorias(all_cpus)
    sel_cats = col_cat.multiselect(
        "Categoria",
        options=categorias,
        key=f"master-cpu-cats-{catalog_id}",
        label_visibility="collapsed",
        placeholder="Todas as categorias",
    )
    if col_ref.button("↺ Recarregar", key=f"master-cpu-reload-{catalog_id}"):
        st.session_state.pop(cache_key, None)
        _cmb_clear_catalog_cache(catalog_id)
        st.rerun()

    filtered = _cmb_filter_cpus(all_cpus, q, sel_cats)
    total = len(filtered)

    page_key = f"master-cpu-page-{catalog_id}"
    if page_key not in st.session_state:
        st.session_state[page_key] = 0

    n_pages = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE)
    page = min(st.session_state[page_key], n_pages - 1)
    st.session_state[page_key] = page

    start = page * _PAGE_SIZE
    page_cpus = filtered[start : start + _PAGE_SIZE]

    _cmb_render_cpu_nav(page, n_pages, page_key, total, catalog_id)

    rows = _cmb_build_cpu_rows(page_cpus, catalog_id)
    selected_rows = st.dataframe(
        rows,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key=f"master-cpu-table-{catalog_id}-p{page}",
    )

    sel = dataframe_selected_rows(selected_rows)
    _cmb_handle_cpu_selection(sel, page_cpus, base_url, actor, catalog_id)


# ─── Insumos ──────────────────────────────────────────────────────────────────


def _render_insumo_browser(base_url: str, actor: str, catalog_id: str) -> None:
    cache_key = f"master-insumos-all-{catalog_id}"
    if cache_key not in st.session_state:
        try:
            resp = api_call(
                "GET", f"/api/catalogs/{catalog_id}/insumos", params={"limit": 500}, base_url=base_url, actor=actor
            )
            st.session_state[cache_key] = resp.get("items", [])
        except Exception as exc:
            st.error(f"Erro ao carregar insumos: {exc}")
            return

    all_insumos: list[dict] = st.session_state[cache_key]

    col_q, col_ref = st.columns([5, 1])
    q = col_q.text_input(
        "Buscar", placeholder="Código ou descrição…", key=f"master-ins-q-{catalog_id}", label_visibility="collapsed"
    )
    if col_ref.button("↺", key=f"master-ins-reload-{catalog_id}"):
        st.session_state.pop(cache_key, None)
        st.rerun()

    filtered = _cmb_filter_insumos(all_insumos, q)

    total = len(filtered)

    page_key = f"master-ins-page-{catalog_id}"
    if page_key not in st.session_state:
        st.session_state[page_key] = 0
    page = min(st.session_state[page_key], max(0, (total - 1) // _PAGE_SIZE))
    st.session_state[page_key] = page

    start = page * _PAGE_SIZE
    page_items = filtered[start : start + _PAGE_SIZE]
    n_pages = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE)

    has_prev = page > 0
    has_next = page < n_pages - 1
    info_html = (
        "<div style='text-align:center;padding:0.35rem 0;font-size:0.85rem;'>"
        f"<strong>{total}</strong> insumos &nbsp;·&nbsp; página {page + 1}/{n_pages}"
        "</div>"
    )
    col_prev, col_info, col_next = st.columns([1, 5, 1])
    with col_prev:
        if has_prev and st.button("←", key=f"master-ins-prev-{catalog_id}", type="secondary", use_container_width=True):
            st.session_state[page_key] = page - 1
            st.rerun()
    col_info.markdown(info_html, unsafe_allow_html=True)
    with col_next:
        if has_next and st.button("→", key=f"master-ins-next-{catalog_id}", type="secondary", use_container_width=True):
            st.session_state[page_key] = page + 1
            st.rerun()

    rows = _cmb_build_insumo_rows(page_items)
    st.dataframe(rows, use_container_width=True, hide_index=True)
