"""Camada de apresentação — layout Streamlit (parte extraída de layout.py)."""

from __future__ import annotations

import streamlit as st

from ...infra.api import api_call
from ...molecules.common import render_paginated_table
from ...molecules.components import render_mapping_table


def render_run(
    base_url: str, project_id: str, actor: str, base_version: str | None, project: dict | None = None
) -> None:
    """Render pipeline run control."""
    st.subheader("▶️ Run / Re-run")

    # NEP-016: bloqueia pipeline se EAP está vazia ou ainda em rascunho
    status_eap = (project or {}).get("status_eap", "")
    if status_eap == "RASCUNHO":
        st.warning(
            "⚠️ **EAP em rascunho** — adicione ao menos uma atividade à EAP antes de iniciar o pipeline. "
            "Acesse **📋 Atividades da EAP** no painel de Overview para cadastrar os itens.",
            icon=None,
        )
        st.button("Iniciar pipeline", use_container_width=True, type="primary", disabled=True)
        return

    fork = st.checkbox("Criar nova versão (fork)", value=True)

    if st.button("Iniciar pipeline", use_container_width=True, type="primary"):
        payload = {  # type: ignore[var-annotated]
            "base_version": base_version or None,
            "fork_version": fork,
            "skill_inputs_override": {},
            "use_saved_overrides": True,
        }
        result = api_call(
            method="POST",
            path=f"/api/projects/{project_id}/runs/start",
            base_url=base_url,
            payload=payload,
            actor=actor,
        )
        st.session_state["selected_run_id"] = result.get("run_id")
        st.success(f"Run iniciado: {result.get('run_id')}")
        render_mapping_table("Run iniciado", result)


def render_version_management(base_url: str, project: dict, actor: str) -> None:
    """Render version management controls."""
    project_id = project["project_id"]
    st.subheader("🗑️ Excluir versão")
    st.warning(
        "Excluir versão remove seus artefatos/canônico daquela pasta. Runs que apontavam para ela permanecem no histórico e podem ficar órfãos."  # noqa: E501
    )

    versions = list(project.get("versions") or [])
    current_version = project.get("current_version")
    if not versions:
        st.info("Projeto sem versões para remover.")
        return

    col_v1, col_v2 = st.columns([2, 3])
    delete_version = col_v1.selectbox(
        "Versão para excluir",
        options=versions,
        key=f"delete-version-select-{project_id}",
    )
    confirm_text = col_v2.text_input(
        "Confirmação (digite exatamente a versão)",
        value="",
        key=f"delete-version-confirm-{project_id}",
        placeholder=f"Digite {delete_version}",
    )

    if delete_version == current_version:
        st.caption("A versão atual será removida. O sistema promoverá automaticamente a última versão remanescente.")

    if st.button("Excluir versão selecionada", type="primary", key=f"delete-version-btn-{project_id}"):
        if confirm_text.strip() != delete_version:
            st.error("Confirmação inválida. Digite exatamente o nome da versão para excluir.")
            return
        result = api_call(
            method="DELETE",
            path=f"/api/projects/{project_id}/versions/{delete_version}",
            base_url=base_url,
            actor=actor,
        )
        st.success(
            f"Versão {result.get('deleted_version')} removida. Nova atual: {result.get('current_version') or '-'} | Runs órfãs: {result.get('orphaned_runs', 0)}"  # noqa: E501
        )
        st.rerun()


def _render_run_details(run: dict, run_id: str, project_id: str, context: str) -> None:
    """Displays skills progress and error for a run."""
    st.caption(f"Status: {run.get('status')} | Inicio: {run.get('started_at')} | Fim: {run.get('finished_at')}")
    skills_data = run.get("skills_progress") or run.get("skills_log") or []
    if skills_data:
        render_paginated_table(
            skills_data, page_key=f"skills-page-{project_id}-{run_id}-{context}", page_size=15, label="skills"
        )
    else:
        st.info("Aguardando primeiras skills no log de invocacoes.")
    if run.get("error"):
        st.error(run["error"])


def render_pipeline_monitor(base_url: str, project_id: str, actor: str, context: str = "main") -> None:
    """Render pipeline execution monitor."""
    try:
        runs = api_call(method="GET", path=f"/api/projects/{project_id}/runs", base_url=base_url, actor=actor).get(
            "items", []
        )
    except Exception as exc:
        st.warning(
            f"Monitor indisponivel nesta API. Reinicie a API com a versao atual ou use execucao sync. Detalhe: {exc}"
        )
        return
    if not runs:
        st.info("Nenhuma execucao encontrada.")
        return

    run_ids = [item.get("run_id", "") for item in runs]
    default_idx = 0
    selected_run_id = st.session_state.get("selected_run_id")
    if selected_run_id in run_ids:
        default_idx = run_ids.index(selected_run_id)
    run_id = st.selectbox("Run ID", options=run_ids, index=default_idx, key=f"pm-run-id-{project_id}-{context}")
    st.session_state["selected_run_id"] = run_id

    if st.button("Atualizar monitor", key=f"pm-refresh-{project_id}-{context}", type="secondary"):
        pass

    try:
        run = api_call(method="GET", path=f"/api/projects/{project_id}/runs/{run_id}", base_url=base_url, actor=actor)
    except Exception as exc:
        st.error(f"Falha ao consultar run {run_id}: {exc}")
        return
    _render_run_details(run, run_id, project_id, context)


def _build_history_timeline(runs: list) -> list[dict]:
    """Builds the timeline rows list from runs."""
    return [
        {
            "run_id": item.get("run_id", "")[:12],
            "status": item.get("status"),
            "versão": item.get("version"),
            "base": item.get("base_version"),
            "solicitado": (item.get("requested_at") or "")[:16].replace("T", " "),
            "início": (item.get("started_at") or "")[:16].replace("T", " "),
            "fim": (item.get("finished_at") or "")[:16].replace("T", " "),
            "actor": item.get("actor"),
        }
        for item in runs
    ]


def _filter_history(timeline: list[dict], q: str, sel_status: list) -> list[dict]:
    """Applies text and status filters to the timeline list."""
    if q:
        q_l = q.lower()
        timeline = [
            r for r in timeline if q_l in str(r.get("run_id", "")).lower() or q_l in str(r.get("versão", "")).lower()
        ]
    if sel_status:
        timeline = [r for r in timeline if r.get("status") in sel_status]
    return timeline


def render_history(base_url: str, project_id: str, actor: str, context: str = "main") -> None:
    """Render execution history timeline — paginated."""
    try:
        runs = api_call(method="GET", path=f"/api/projects/{project_id}/runs", base_url=base_url, actor=actor).get(
            "items", []
        )
    except Exception as exc:
        st.warning(f"Historico indisponivel nesta API: {exc}")
        return
    if not runs:
        st.info("Sem historico de runs.")
        return

    col_q, col_status = st.columns([4, 2])
    q = col_q.text_input(
        "Buscar run ID ou versão",
        key=f"hist-q-{project_id}-{context}",
        label_visibility="collapsed",
        placeholder="Filtrar runs…",
    )
    status_opts = sorted({r.get("status", "") for r in runs if r.get("status")})
    sel_status = col_status.multiselect(
        "Status",
        options=status_opts,
        key=f"hist-status-{project_id}-{context}",
        label_visibility="collapsed",
        placeholder="Todos os status",
    )

    timeline = _build_history_timeline(runs)
    timeline = _filter_history(timeline, q, sel_status)
    render_paginated_table(timeline, page_key=f"hist-page-{project_id}-{context}", label="runs")


