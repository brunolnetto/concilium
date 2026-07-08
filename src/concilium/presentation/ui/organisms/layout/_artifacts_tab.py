"""Camada de apresentação — layout Streamlit (parte extraída de layout.py)."""

from __future__ import annotations

import streamlit as st

from ...infra.api import (
    api_call,
    fetch_artifact_bytes,
)
from ...molecules.components import render_download_button
from ._markdown_preview import _render_md_with_mermaid


def _render_md_preview_for(
    base_url: str,
    project_id: str,
    version: str | None,
    actor: str,
    md_filename: str,
    pdf_filename: str,
) -> None:
    """Renderiza preview de um arquivo .md com botões de download .md e .pdf."""
    try:
        artifacts = api_call(
            method="GET",
            path=f"/api/projects/{project_id}/artifacts",
            base_url=base_url,
            params={"version": version} if version else None,
            actor=actor,
        )
    except Exception as exc:
        st.info(f"Artefatos não disponíveis: {exc}")
        return

    outputs = list(artifacts.get("outputs") or [])
    if md_filename not in outputs:
        st.info(f"`{md_filename}` não encontrado nos outputs desta versão.")
        return

    try:
        payload = fetch_artifact_bytes(base_url, project_id, "outputs", md_filename, version, actor)
        text = payload.decode("utf-8", errors="replace")
    except Exception as exc:
        st.warning(f"Falha ao carregar {md_filename}: {exc}")
        return

    col_md, col_pdf = st.columns(2)
    with col_md:
        render_download_button(
            base_url,
            project_id,
            "outputs",
            md_filename,
            version,
            actor,
            f"⬇️ {md_filename}",
            key=f"prev-dl-md-{project_id}-{md_filename}",
            use_container_width=True,
        )
    with col_pdf:
        if pdf_filename in outputs:
            render_download_button(
                base_url,
                project_id,
                "outputs",
                pdf_filename,
                version,
                actor,
                f"⬇️ {pdf_filename}",
                key=f"prev-dl-pdf-{project_id}-{pdf_filename}",
                use_container_width=True,
            )
        else:
            st.caption(f"`{pdf_filename}` não gerado nesta versão.")

    _render_md_with_mermaid(text)
    with st.expander("Ver fonte Markdown", expanded=False):
        st.code(text, language="markdown")


def _resolve_artifacts_tab_versions(base_url: str, project_id: str, actor: str, versions: list) -> list:
    """Tenta atualizar a lista de versões via API; mantém a lista original em caso de falha/vazio."""
    try:
        live_versions = api_call(
            method="GET",
            path=f"/api/projects/{project_id}/versions",
            base_url=base_url,
            actor=actor,
        ).get("items", [])
        if isinstance(live_versions, list) and live_versions:
            return live_versions
    except Exception:
        pass
    return versions


def _render_artifact_files_list(
    base_url: str,
    project_id: str,
    category: str,
    filenames: list,
    version_selected: str,
    actor: str,
    label: str,
    empty_msg: str,
) -> None:
    """Renderiza a legenda e os botões de download de uma categoria de artefatos (outputs/intermediate)."""
    st.caption(f"**{label}** ({len(filenames)})")
    if not filenames:
        st.caption(empty_msg)
        return
    for filename in filenames:
        render_download_button(
            base_url,
            project_id,
            category,
            filename,
            version_selected,
            actor,
            f"📥 {filename}",
            use_container_width=True,
        )


def _render_artifacts_output_columns(
    base_url: str, project_id: str, artifacts: dict, version_selected: str, actor: str
) -> None:
    """Renderiza as duas colunas de artefatos (outputs e intermediários)."""
    outputs = artifacts.get("outputs", [])
    intermediate = artifacts.get("intermediate", [])

    col_artifact_output, col_artifact_intermediate = st.columns(2)
    with col_artifact_output:
        _render_artifact_files_list(
            base_url, project_id, "outputs", outputs, version_selected, actor, "Outputs", "Sem outputs"
        )
    with col_artifact_intermediate:
        _render_artifact_files_list(
            base_url,
            project_id,
            "intermediate",
            intermediate,
            version_selected,
            actor,
            "Intermediários",
            "Sem intermediários",
        )


def _fetch_and_render_artifacts_tab(base_url: str, project_id: str, version_selected: str, actor: str) -> None:
    """Busca os artefatos da versão selecionada e renderiza suas colunas, com fallback de erro."""
    try:
        artifacts = api_call(
            method="GET",
            path=f"/api/projects/{project_id}/artifacts",
            base_url=base_url,
            params={"version": version_selected},
            actor=actor,
        )
        _render_artifacts_output_columns(base_url, project_id, artifacts, version_selected, actor)
    except Exception as exc:
        st.error(f"Falha ao carregar artefatos: {exc}")


def render_artifacts_tab(base_url: str, project_id: str, project: dict, actor: str) -> None:
    """Tab: Artifacts - Version artifacts downloader."""
    st.subheader("📦 Artefatos por Versão")
    versions = project.get("versions") or []
    versions = _resolve_artifacts_tab_versions(base_url, project_id, actor, versions)
    version_selected = st.selectbox(
        "Versão",
        options=versions if versions else [project.get("current_version") or "v1"],
        key="artifacts-version-select",
    )
    _fetch_and_render_artifacts_tab(base_url, project_id, version_selected, actor)
    st.divider()
    # ── Pré-visualizações colapsáveis ─────────────────────────────────────
    with st.expander("📝 Relatório Analítico", expanded=False):
        _render_md_preview_for(base_url, project_id, version_selected, actor, "relatorio.md", "relatorio.pdf")
    with st.expander("🔢 Memorial BDI", expanded=False):
        _render_md_preview_for(base_url, project_id, version_selected, actor, "memorial_bdi.md", "memorial_bdi.pdf")


