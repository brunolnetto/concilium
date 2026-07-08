"""Camada de apresentação — layout Streamlit (parte extraída de layout.py)."""

from __future__ import annotations

from ...infra.api import api_call
from ._mobilizacao_policy import render_mobilizacao_policy_editor


def render_planning_tab(base_url: str, project: dict, actor: str, base_version: str | None) -> None:
    """Tab: Planejamento — política de mobilização de equipes."""
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

    render_mobilizacao_policy_editor(base_url, project_id, actor, reference, base_version)


