"""Centralized state management for Streamlit UI."""

from __future__ import annotations

from dataclasses import dataclass, field

import streamlit as st


@dataclass
class UIState:
    """Centralized UI state."""

    # Navigation
    current_view: str = "Projeto"

    # Project state
    selected_project: dict | None = None
    selected_project_id: str | None = None
    projects_cache: list[dict] = field(default_factory=list)

    # Project view state
    base_version: str | None = None
    selected_version: str | None = None
    selected_run_id: str | None = None

    # Editor state
    team_rows_state: list[dict] = field(default_factory=list)
    override_skill_selected: str | None = None

    # Theme
    theme: str = "light"  # "light" | "dark"

    # Catalog state
    catalog_cpu_data: dict = field(default_factory=dict)

    # Cache
    reference_cache: dict[str, dict] = field(default_factory=dict)
    benchmarks_cache: list[str] = field(default_factory=list)
    overrides_cache: dict[str, dict] = field(default_factory=dict)


class StateManager:
    """Manages global UI state using Streamlit session_state."""

    _KEY = "_ui_state"

    @classmethod
    def init(cls) -> None:
        """Initialize state manager."""
        if cls._KEY not in st.session_state:
            st.session_state[cls._KEY] = UIState()

    @classmethod
    def get(cls) -> UIState:
        """Get current UI state."""
        cls.init()
        return st.session_state[cls._KEY]

    @classmethod
    def set_project(cls, project: dict | None) -> None:
        """Set selected project."""
        state = cls.get()
        state.selected_project = project
        state.selected_project_id = project.get("project_id") if project else None
        state.selected_version = project.get("current_version") if project else None
        state.reference_cache = {}  # Clear reference cache on project change

    @classmethod
    def set_view(cls, view: str) -> None:
        """Set current view."""
        state = cls.get()
        state.current_view = view

    @classmethod
    def set_nav(cls, nav: str) -> None:
        """Navigate to a different page (ADR-063: used by sidebar to redirect to Projetos page)."""
        st.session_state["nav-choice"] = nav

    @classmethod
    def toggle_theme(cls) -> str:
        """Toggle between light and dark theme. Returns the new theme."""
        state = cls.get()
        state.theme = "dark" if state.theme == "light" else "light"
        return state.theme

    @classmethod
    def get_theme(cls) -> str:
        return cls.get().theme

    @classmethod
    def get_reference_cached(cls, project_id: str) -> dict | None:
        """Get cached reference for project."""
        state = cls.get()
        return state.reference_cache.get(project_id)

    @classmethod
    def cache_reference(cls, project_id: str, reference: dict) -> None:
        """Cache reference for project."""
        state = cls.get()
        state.reference_cache[project_id] = reference

    @classmethod
    def cache_benchmarks(cls, benchmarks: list[str]) -> None:
        """Cache benchmarks list."""
        state = cls.get()
        state.benchmarks_cache = benchmarks

    @classmethod
    def get_benchmarks_cached(cls) -> list[str]:
        """Get cached benchmarks."""
        state = cls.get()
        return state.benchmarks_cache

    @classmethod
    def cache_overrides(cls, project_id: str, overrides: dict) -> None:
        """Cache overrides for project."""
        state = cls.get()
        state.overrides_cache[project_id] = overrides

    @classmethod
    def get_overrides_cached(cls, project_id: str) -> dict:
        """Get cached overrides for project."""
        state = cls.get()
        return state.overrides_cache.get(project_id, {})

    @classmethod
    def clear_cache(cls) -> None:
        """Clear all caches."""
        state = cls.get()
        state.reference_cache = {}
        state.benchmarks_cache = []
        state.overrides_cache = {}
