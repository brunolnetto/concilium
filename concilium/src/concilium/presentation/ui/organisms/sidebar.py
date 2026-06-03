"""Sidebar — styled navigation menu + compact active-context widget."""

from __future__ import annotations

from html import escape
import sys
from pathlib import Path

import streamlit as st

try:
    from ..config import NAVIGATION_OPTIONS
    from ..state import StateManager
except ImportError:
    src_root = Path(__file__).resolve().parents[4]
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))
    from concilium.presentation.ui.config import NAVIGATION_OPTIONS
    from concilium.presentation.ui.state import StateManager

_NAV_ICONS: dict[str, str] = {
    "Catálogo": "📚",
    "Configuração": "⚙️",
    "Projetos": "📁",
}
_THEME_ICON = {"light": "🌙", "dark": "☀️"}
_THEME_LABEL = {"light": "Modo escuro", "dark": "Modo claro"}


def render_sidebar() -> str:
    """Render sidebar and return the active navigation key."""
    theme = StateManager.get_theme()
    current = st.session_state.get("nav-choice", NAVIGATION_OPTIONS[0])
    if current not in NAVIGATION_OPTIONS:
        current = NAVIGATION_OPTIONS[0]
        st.session_state["nav-choice"] = current

    # ── Header ────────────────────────────────────────────────────────────
    st.sidebar.markdown("### 🏗️ Concilium")

    # Theme toggle — full-width, secondary
    toggle_label = f"{_THEME_ICON[theme]}  {_THEME_LABEL[theme]}"
    if st.sidebar.button(toggle_label, key="sidebar-theme-toggle", use_container_width=True, type="secondary"):
        StateManager.toggle_theme()
        st.rerun()

    st.sidebar.divider()

    # ── Navegação: um botão por opção ─────────────────────────────────────
    # CSS classes ml-nav-active / ml-nav-item controlam o visual.
    # Botão ativo recebe type="primary" (navy preenchido) para distinção clara.
    nav_choice = current
    for option in NAVIGATION_OPTIONS:
        icon = _NAV_ICONS.get(option, "")
        is_active = option == current
        label = f"{icon}  {option}"
        if st.sidebar.button(
            label,
            key=f"nav-btn-{option}",
            use_container_width=True,
            type="primary" if is_active else "secondary",
        ):
            nav_choice = option
            st.session_state["nav-choice"] = option
            st.rerun()

    # ── Contexto do projeto ativo ─────────────────────────────────────────
    project = StateManager.get().selected_project
    if project and nav_choice == "Projetos":
        st.sidebar.divider()
        _render_project_context(project)

    return nav_choice


def _render_project_context(project: dict) -> None:
    """Compact project info — visible when a project is open."""
    pid = project.get("project_id", "")
    nome = escape(str(project.get("nome") or pid[:12]))
    tipo = (project.get("tipo_projeto") or "hot_project").lower()
    versao = escape(str(project.get("current_version") or "—"))
    status_eap = escape(str(project.get("status_eap", "")))
    badge = "🔥" if tipo == "hot_project" else "📐"

    st.sidebar.markdown(
        f"""
        <div class="ml-project-ctx">
            <div class="ml-project-ctx-name">{badge} {nome}</div>
            <div class="ml-project-ctx-meta">
                versão <code>{versao}</code>
                {f"&nbsp;·&nbsp;EAP <code>{status_eap}</code>" if tipo == "project" and status_eap else ""}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.sidebar.button("↩ Trocar projeto", key="sidebar-switch-project", use_container_width=True, type="secondary"):
        StateManager.set_project(None)
        st.rerun()
