"""Camada de apresentação — layout Streamlit (parte extraída de layout.py)."""

from __future__ import annotations

import streamlit as st

from ...helpers.helpers import (
    build_team_adjustment_rows,
    extract_all_skill_inputs,
    safe_count_eap,
)
from ...infra.api import api_call
from ...molecules.common import (
    render_info_row,
    render_kpi_cards,
)


def render_overview_tab(base_url: str, project: dict, actor: str) -> None:
    """Tab: Overview - Dashboard de métricas do projeto."""
    project_id = project["project_id"]

    try:
        reference = api_call(
            method="GET",
            path=f"/api/projects/{project_id}/benchmark-reference",
            base_url=base_url,
            actor=actor,
        )
    except Exception:
        reference = {}

    from concilium.presentation.ui.templates._project_page_helpers_a import _render_context_section, _render_eap_section

    with st.expander("ℹ️ Resumo do Projeto", expanded=True):
        render_kpi_cards(
            [
                {"label": "Tipo", "value": str(project.get("tipo_projeto", "-")).upper()},
                {"label": "Contexto", "value": project.get("contexto_id", "-")},
                {"label": "Benchmark", "value": project.get("benchmark_slug", "-")},
            ]
        )
        render_info_row(
            [
                ("Projeto", str(project.get("nome") or "-")),
                ("ID", str(project_id)),
            ]
        )

        eap_count = safe_count_eap(reference)
        all_base_skills = extract_all_skill_inputs(reference)
        extra_count = len(all_base_skills)
        team_count = len(build_team_adjustment_rows(reference))

        render_kpi_cards(
            [
                {"label": "Itens de EAP", "value": eap_count},
                {"label": "Skills configuradas", "value": extra_count},
                {"label": "Atividades com equipes", "value": team_count},
            ]
        )

    with st.expander("📋 Atividades da EAP", expanded=False):
        _render_eap_section(reference, base_url, project_id, actor)

    with st.expander("🌐 Contexto e Perfil", expanded=False):
        _render_context_section(base_url, project, project_id, actor)


