"""Atomic design templates - Full page layouts."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

from ._project_page_helpers_a import (
    _deserialize_backtracking,
    _deserialize_diagnostico,
)
from ._project_page_helpers_b import (
    _render_project_catalog_section,
)

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
        render_cube_analytics_by_version,
        render_deliverables_config,
        render_diagnostico_pe,
        render_history,
        render_indiretos_config,
        render_overview_tab,
        render_pipeline_monitor,
        render_planning_tab,
        render_run,
        render_saved_override,
        render_version_detail,
        render_version_management,
        render_version_summary,
    )
except ImportError:
    src_root = Path(__file__).resolve().parents[4]
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))
    from concilium.presentation.ui.config import DEFAULT_ACTOR, DEFAULT_BASE_URL
    from concilium.presentation.ui.infra.api import api_call
    from concilium.presentation.ui.molecules.common import render_page_heading
    from concilium.presentation.ui.organisms.layout import (
        render_artifacts_tab,
        render_audit,
        render_backtracking_pe,
        render_bdi_tab,
        render_compare,
        render_cpu_composition_override,
        render_cpu_productivity_override,
        render_cube_analytics_by_version,
        render_deliverables_config,
        render_diagnostico_pe,
        render_history,
        render_indiretos_config,
        render_overview_tab,
        render_pipeline_monitor,
        render_planning_tab,
        render_run,
        render_saved_override,
        render_version_detail,
        render_version_management,
        render_version_summary,
    )


def render_hot_project_template(project: dict) -> None:
    """Render HOT project template with tabs."""
    base_url = DEFAULT_BASE_URL
    actor = DEFAULT_ACTOR
    project_id = project["project_id"]

    render_page_heading(
        f"Projeto HOT: {project.get('nome', project_id)}",
        "Painel completo com planejamento, controle de versões, comparação e auditoria.",
    )

    tab_overview, tab_control_panel = st.tabs(["📊 Overview", "🛠️ Painel de Controle"])

    with tab_overview:
        _render_hot_overview_tab(base_url, actor, project, project_id)

    with tab_control_panel:
        _render_hot_control_panel_tab(base_url, actor, project, project_id)

    # tab_config removed — configuration is now embedded in tab_overview


def render_normal_project_template(project: dict) -> None:
    """Render normal project template with columns."""
    base_url = DEFAULT_BASE_URL
    actor = DEFAULT_ACTOR
    project_id = project["project_id"]

    render_page_heading(
        f"Projeto: {project.get('nome', project_id)}",
        "Operações essenciais de execução, overrides, histórico e artefatos.",
    )

    col_a, col_b = st.columns(2)
    with col_a:
        render_run(base_url, project_id, actor, project.get("current_version"), project=project)
        st.divider()
        render_pipeline_monitor(base_url, project_id, actor, context="normal")
        st.divider()
        render_saved_override(base_url, project_id, actor)
        st.divider()
        render_history(base_url, project_id, actor, context="normal")
    with col_b:
        render_compare(base_url, project, actor)
        st.divider()
        render_artifacts_tab(base_url, project_id, project, actor)
        st.divider()
        render_audit(base_url, project_id, actor)


def _render_hot_overview_tab(base_url: str, actor: str, project: dict, project_id: str) -> None:
    sub_proj, sub_exec, sub_audit = st.tabs(["🔍 Projeto", "📈 Execuções", "📝 Auditoria"])

    with sub_proj:
        render_overview_tab(base_url, project, actor)

    with sub_exec:
        with st.expander("Resumo", expanded=True):
            render_version_summary(base_url, project, actor)

        with st.expander("Execuções", expanded=False):
            sub_hist, sub_detail = st.tabs(["Histórico", "Detalhe"])

            with sub_hist:
                render_history(base_url, project_id, actor, context="overview")

            with sub_detail:
                render_pipeline_monitor(base_url, project_id, actor, context="overview")
                try:
                    _diag_resp = api_call(
                        method="GET",
                        path=f"/api/projects/{project_id}/diagnostico-pe",
                        base_url=DEFAULT_BASE_URL,
                        actor=DEFAULT_ACTOR,
                    )
                    _diag_obj = _deserialize_diagnostico(_diag_resp.get("diagnostico_pe"))
                    _back_obj = _deserialize_backtracking(_diag_resp.get("backtracking_pe"))
                    if _diag_obj and _diag_obj.n_itens_deficit > 0:
                        st.divider()
                        render_diagnostico_pe(base_url, project_id, actor, _diag_obj)
                        render_backtracking_pe(_back_obj)
                except Exception:
                    pass

    with sub_audit:
        render_audit(base_url, project_id, actor)


def _render_hot_control_panel_tab(base_url: str, actor: str, project: dict, project_id: str) -> None:
    sub_catalog, sub_plan, sub_versions = st.tabs(
        ["🔍 Catálogo", "📊 Planejamento", "🗂️ Versões"]
    )

    with sub_catalog:
        _render_project_catalog_section(base_url, project_id, actor)

    with sub_plan:
        versions = project.get("versions") or []
        version_options = versions if versions else [project.get("current_version") or "v1"]
        base_version = st.selectbox(
            "Versão base para replanejamento",
            options=version_options,
            index=0,
            key=f"control-base-version-{project_id}",
            help="Fork a partir desta versão ao executar um novo run.",
        )
        st.divider()

        with st.expander("📈 Custos", expanded=False):
            with st.expander("🏢 Indiretos", expanded=False):
                render_indiretos_config(base_url, project_id, actor)
            with st.expander("🏗️ Diretos", expanded=False):
                with st.expander("🔧 CPUs", expanded=False):
                    with st.expander("📜 Composição", expanded=False):
                        render_cpu_composition_override(base_url, project_id, actor)
                    with st.expander("💪🏽 Produtividade", expanded=False):
                        render_cpu_productivity_override(base_url, project_id, actor)
                with st.expander("📋 Políticas de Mobilização de Equipes", expanded=False):
                    render_planning_tab(base_url, project, actor, base_version)

        with st.expander("💰 BDI e Regime Tributário", expanded=False):
            render_bdi_tab(base_url, project, actor)

        with st.expander("📦 Saídas do Planejamento", expanded=False):
            render_deliverables_config(base_url, project_id, actor)

        st.divider()
        render_run(base_url, project_id, actor, base_version, project=project)

    with sub_versions:
        sub_detail, sub_compare, sub_cube, sub_artifacts, sub_mgmt = st.tabs(
            ["🔍 Detalhe", "🔀 Comparação", "🧊 Cubo Analítico", "📦 Artefatos", "⚙️ Gerenciamento"]
        )
        with sub_detail:
            render_version_detail(base_url, project, actor)
        with sub_compare:
            render_compare(base_url, project, actor)
        with sub_cube:
            render_cube_analytics_by_version(base_url, project, actor)
        with sub_artifacts:
            render_artifacts_tab(base_url, project_id, project, actor)
        with sub_mgmt:
            render_version_management(base_url, project, actor)
