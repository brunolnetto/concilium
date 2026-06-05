"""Catalog page template."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

try:
    from ..atoms.form_contracts import (
        CPU_EDITABLE_FIELDS,
        CPU_READONLY_FIELDS,
        render_typed_form,
    )
    from ..config import DEFAULT_ACTOR, DEFAULT_BASE_URL
    from ..infra.api import api_call
    from ..molecules.common import render_page_heading
except ImportError:
    src_root = Path(__file__).resolve().parents[4]
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))
    from concilium.presentation.ui.config import DEFAULT_ACTOR, DEFAULT_BASE_URL
    from concilium.presentation.ui.molecules.common import render_page_heading

from ._catalogo_helpers import *  # noqa: F401,F403


def render_catalogo_page_template(project: dict) -> None:
    """Render catalog management page template."""
    base_url = DEFAULT_BASE_URL
    actor = DEFAULT_ACTOR
    project_id = project["project_id"]

    render_page_heading(
        "Gerenciamento de Catálogo",
        "Extenda e versione CPUs do projeto com trilha de governança.",
    )

    cpu_data = st.session_state.get("catalog-cpu-data", {})
    if cpu_data:
        with st.expander("Inspecionar JSON da CPU (somente leitura)", expanded=False):
            st.json(cpu_data)

    tabs = st.tabs(["📚 Catálogo paginado", "🧩 Edição avançada por ID"])

    with tabs[0]:
        _render_catalogo_tab0(project, project_id, base_url, actor)

    with tabs[1]:
        _render_catalogo_tab1(project_id, base_url, actor)
