"""Concilium Prototype Streamlit UI - Main entry point."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

try:
    from .organisms.sidebar import render_sidebar
    from .state import StateManager
    from .templates.catalogo_master_page import render_catalogo_master_page
    from .templates.configuracao_page import render_configuracao_page
    from .templates.formulario_qqp_page import render_formulario_qqp_page
    from .templates.project_page import (
        render_hot_project_template,
        render_normal_project_template,
    )
    from .templates.projetos_page import render_projetos_page
    from .theme import apply_visual_identity
except ImportError:
    src_root = Path(__file__).resolve().parents[3]
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))
    from concilium.presentation.ui.organisms.sidebar import render_sidebar
    from concilium.presentation.ui.state import StateManager
    from concilium.presentation.ui.templates.catalogo_master_page import render_catalogo_master_page
    from concilium.presentation.ui.templates.configuracao_page import render_configuracao_page
    from concilium.presentation.ui.templates.formulario_qqp_page import render_formulario_qqp_page
    from concilium.presentation.ui.templates.project_page import (
        render_hot_project_template,
        render_normal_project_template,
    )
    from concilium.presentation.ui.templates.projetos_page import render_projetos_page
    from concilium.presentation.ui.theme import apply_visual_identity


def main() -> None:
    """Main Streamlit application entry point."""
    st.set_page_config(
        page_title="Concilium | MendesLobo",
        page_icon="🏗️",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    apply_visual_identity()
    st.markdown(
        """
        <section class="ui-app-hero">
            <h1>Concilium</h1>
            <p>Planejamento temporal e financeiro de projetos de construção civil — MendesLobo Construtora.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )

    StateManager.init()
    nav_choice = render_sidebar()
    apply_visual_identity(StateManager.get_theme())

    if nav_choice == "Projetos":
        project = StateManager.get().selected_project
        if not project:
            render_projetos_page()
            return
        tipo = (project.get("tipo_projeto") or "hot_project").lower()
        if tipo == "hot_project":
            render_hot_project_template(project)
        else:
            render_normal_project_template(project)
    elif nav_choice == "Catálogo":
        render_catalogo_master_page()
    elif nav_choice == "Novo QQP":
        render_formulario_qqp_page()
    elif nav_choice == "Configuração":
        render_configuracao_page()


if __name__ == "__main__":
    main()
