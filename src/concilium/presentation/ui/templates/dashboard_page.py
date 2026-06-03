"""Dashboard page template."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

try:
    from ..config import DEFAULT_ACTOR, DEFAULT_BASE_URL
    from ..infra.api import api_call
    from ..molecules.common import render_kpi_cards, render_page_heading, render_standard_table
except ImportError:
    src_root = Path(__file__).resolve().parents[4]
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))
    from concilium.presentation.ui.config import DEFAULT_ACTOR, DEFAULT_BASE_URL
    from concilium.presentation.ui.infra.api import api_call
    from concilium.presentation.ui.molecules.common import render_kpi_cards, render_page_heading, render_standard_table


def _rdt_load_projects() -> list | None:
    try:
        return api_call(method="GET", path="/api/projects", base_url=DEFAULT_BASE_URL, actor=DEFAULT_ACTOR).get(
            "items", []
        )
    except Exception as exc:
        st.error(f"Falha ao carregar projetos: {exc}")
        return None


def _rdt_load_runs(selected_id: str) -> list | None:
    try:
        return api_call(
            method="GET",
            path=f"/api/projects/{selected_id}/runs",
            base_url=DEFAULT_BASE_URL,
            actor=DEFAULT_ACTOR,
        ).get("items", [])
    except Exception as exc:
        st.warning(f"Não foi possível carregar runs do projeto selecionado: {exc}")
        return None


def _rdt_project_kpi(projects: list) -> tuple[int, int, list[str]]:
    total_hot = sum(1 for p in projects if (p.get("tipo_projeto") or "hot_project").lower() == "hot_project")
    contextos = sorted({str(p.get("contexto_id") or "-") for p in projects})
    return total_hot, len(projects) - total_hot, contextos


def _rdt_project_rows(projects: list) -> list[dict]:
    return [
        {
            "nome": p.get("nome", "-"),
            "project_id": p.get("project_id", "-"),
            "tipo": (p.get("tipo_projeto") or "hot_project").upper(),
            "contexto": p.get("contexto_id", "-"),
            "versao_atual": p.get("current_version", "-"),
            "benchmark": p.get("benchmark_slug", "-"),
            "atualizado_em": p.get("updated_at", "-"),
        }
        for p in projects
    ]


def _rdt_run_rows(runs: list) -> list[dict]:
    return [
        {
            "run_id": r.get("run_id", "-"),
            "status": r.get("status", "-"),
            "versao": r.get("version", "-"),
            "ator": r.get("actor", "-"),
            "inicio": r.get("started_at", "-"),
            "fim": r.get("finished_at", "-"),
        }
        for r in runs
    ]


def render_dashboard_page_template(compact: bool = False) -> None:
    """Render portfolio dashboard with project-level KPIs."""
    if compact:
        st.caption("Métricas consolidadas do portfólio e histórico de execuções por projeto.")
    else:
        render_page_heading(
            "Dashboard de Projetos",
            "Visão consolidada do portfólio com status, versões ativas e histórico de execução.",
        )

    projects = _rdt_load_projects()
    if projects is None:
        return

    total_hot, total_normal, contextos = _rdt_project_kpi(projects)
    render_kpi_cards(
        [
            {"label": "Projetos", "value": len(projects)},
            {"label": "HOT_PROJECT", "value": total_hot},
            {"label": "PROJECT", "value": total_normal},
            {"label": "Contextos", "value": len(contextos)},
        ]
    )

    if not projects:
        st.info("Nenhum projeto cadastrado até o momento.")
        return

    render_standard_table(
        "Projetos ativos",
        _rdt_project_rows(projects),
        empty_message="Sem projetos ativos.",
        height=260 if compact else 330,
    )

    selected_id = st.selectbox(
        "Projeto para resumo de runs",
        options=[str(p.get("project_id")) for p in projects if p.get("project_id")],
        label_visibility="collapsed" if compact else "visible",
        placeholder="Projeto para resumo de runs",
        key="dashboard-project-select",
    )

    if not selected_id:
        return

    runs = _rdt_load_runs(selected_id)
    if runs is None:
        return

    if compact:
        st.markdown("**Resumo de execuções**")
    else:
        st.subheader("Resumo de execuções")
    if not runs:
        st.info("Projeto sem histórico de runs.")
        return

    last_run = runs[0]
    render_kpi_cards(
        [
            {"label": "Status da última run", "value": last_run.get("status", "-")},
            {"label": "Versão da última run", "value": last_run.get("version", "-")},
            {"label": "Início", "value": last_run.get("started_at", "-")},
            {"label": "Fim", "value": last_run.get("finished_at", "-")},
        ]
    )

    render_standard_table(
        "Histórico de runs",
        _rdt_run_rows(runs),
        empty_message="Sem runs para o projeto selecionado.",
        height=260 if compact else 330,
    )
