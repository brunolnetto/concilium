"""Helpers extracted from project_page.py (parte extraída de _project_page_helpers_b.py, grupo _cpu_editor)."""

from __future__ import annotations

import streamlit as st

from ...atoms.form_contracts import (
    CPU_EDITABLE_FIELDS,
    CPU_READONLY_FIELDS,
    render_typed_form,
)
from ...helpers.helpers import dataframe_selected_rows
from ...infra.api import api_call


def _render_project_cpu_editor(
    base_url: str,
    project_id: str,
    actor: str,
    cpu_id: str,
    cpu_data: dict,
    label: str = "Editar CPU",
) -> None:
    """Editor de override de CPU no projeto (restaurado do project_page.py original)."""
    st.caption(f"**{label}:** `{cpu_id}` — {cpu_data.get('descricao', '')}")
    edited = render_typed_form(
        cpu_data, CPU_EDITABLE_FIELDS, CPU_READONLY_FIELDS, key=f"proj-cpu-form-{project_id}-{cpu_id}"
    )
    motivo = st.text_input("Motivo do override", key=f"proj-cpu-motivo-{project_id}-{cpu_id}")
    if st.button(
        "💾 Salvar override", type="primary", key=f"proj-cpu-save-{project_id}-{cpu_id}", disabled=not motivo.strip()
    ):
        payload = {**cpu_data, **edited}
        try:
            api_call(
                "POST",
                f"/api/projects/{project_id}/catalog/cpus/{cpu_id}",
                payload=payload,
                base_url=base_url,
                actor=actor,
                params={"motivo": motivo},
            )
            st.success(f"Override de `{cpu_id}` salvo!")
            st.session_state.pop(f"proj-cat-cpus-{project_id}", None)
            st.rerun()
        except Exception as exc:
            st.error(f"Erro: {exc}")


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
        ov_sel_rows = dataframe_selected_rows(ov_sel)
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


