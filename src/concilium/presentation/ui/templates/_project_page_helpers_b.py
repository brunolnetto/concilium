"""Helpers extracted from project_page.py.

Atomic design templates - Full page layouts.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

try:
    from ..atoms.form_contracts import CPU_EDITABLE_FIELDS, CPU_READONLY_FIELDS, render_typed_form
    from ..config import DEFAULT_ACTOR, DEFAULT_BASE_URL
    from ..infra.api import api_call
    from ..molecules.common import render_page_heading
    from ..organisms.layout import (
        render_artifacts_tab,
        render_audit,
        render_backtracking_pe,
        render_bdi_tab,
        render_compare,
        render_cpu_composition_override,
        render_cpu_productivity_override,
        render_deliverables_config,
        render_diagnostico_pe,
        render_history,
        render_indiretos_config,
        render_ops_audit_tab,
        render_overview_tab,
        render_pipeline_monitor,
        render_planning_tab,
        render_run,
        render_saved_override,
        render_version_management,
    )
except ImportError:
    src_root = Path(__file__).resolve().parents[4]
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))
    from concilium.presentation.ui.infra.api import api_call


def _render_overrides_section(base_url: str, project_id: str, actor: str, overrides: dict) -> None:
    if overrides:
        st.caption(f"**Overrides deste projeto** — {len(overrides)} CPU(s) customizada(s)")
        ov_rows = [
            {
                "Código": k,
                "Descrição": (v.get("descricao") or "")[:50],
                "Unidade": v.get("unidade", ""),
                "Prod. Hor.": v.get("producao_horaria") or "—",
            }
            for k, v in overrides.items()
            if isinstance(v, dict)
        ]
        ov_sel = st.dataframe(
            ov_rows,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key=f"proj-ov-table-{project_id}",
        )
        ov_sel_rows = (ov_sel.selection.rows or []) if hasattr(ov_sel, "selection") else []
        if ov_sel_rows:
            sel_code = ov_rows[ov_sel_rows[0]]["Código"]
            sel_data = overrides.get(sel_code, {})
            st.divider()
            _render_project_cpu_editor(
                base_url, project_id, actor, sel_code, sel_data, label="Editar override existente"
            )
        st.divider()
    else:
        st.caption("Nenhum override de CPU neste projeto ainda.")


def _load_catalog_cpus(project_id: str, base_url: str, actor: str) -> tuple[str, str, list]:
    try:
        project_meta = api_call("GET", f"/api/projects/{project_id}", base_url=base_url, actor=actor)
    except Exception:
        project_meta = {}
    catalog_id = project_meta.get("contexto_id", "mendeslobo")
    cache_key = f"proj-cat-cpus-{project_id}"
    if cache_key not in st.session_state:
        try:
            resp = api_call(
                "GET", f"/api/catalogs/{catalog_id}/cpus", params={"limit": 500}, base_url=base_url, actor=actor
            )
            st.session_state[cache_key] = resp.get("items", [])
        except Exception:
            st.session_state[cache_key] = []
    return catalog_id, cache_key, st.session_state[cache_key]


def _cpu_matches_query(c: dict, ql: str) -> bool:
    return ql in (c.get("codigo") or "").lower() or ql in (c.get("descricao") or "").lower()


def _filter_catalog_cpus(all_cpus: list, q: str, sel_cats: list) -> list:
    filtered = all_cpus
    if q:
        ql = q.lower()
        filtered = [c for c in filtered if _cpu_matches_query(c, ql)]
    if sel_cats:
        filtered = [c for c in filtered if c.get("categoria") in sel_cats]
    return filtered


def _render_catalog_filter_row(project_id: str, all_cpus: list, cache_key: str) -> tuple[str, list]:
    col_q, col_cats, col_ref = st.columns([3, 2, 1])
    q = col_q.text_input(
        "Buscar CPU", placeholder="Código ou descrição…", key=f"proj-cat-q-{project_id}", label_visibility="collapsed"
    )
    categorias = sorted({str(c.get("categoria") or "") for c in all_cpus if c.get("categoria")})
    sel_cats = col_cats.multiselect(
        "Categoria",
        options=categorias,
        key=f"proj-cat-cats-{project_id}",
        label_visibility="collapsed",
        placeholder="Todas as categorias",
    )
    if col_ref.button("↺", key=f"proj-cat-reload-{project_id}", help="Recarregar catálogo"):
        st.session_state.pop(cache_key, None)
        st.rerun()
    return q, sel_cats


def _render_project_catalog_section(base_url: str, project_id: str, actor: str) -> None:
    """Seção de catálogo do projeto focada em overrides salvos."""
    st.caption(
        "Visualize as customizações de CPU já aplicadas neste projeto. "
        "As edições detalhadas permanecem no Painel de Planejamento."
    )
    render_saved_override(base_url, project_id, actor)
