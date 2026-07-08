"""Camada de apresentação — layout Streamlit (parte extraída de layout.py)."""

from __future__ import annotations

import streamlit as st

from ...infra.api import api_call
from ...molecules.common import render_paginated_table
from ...molecules.components import render_mapping_table
from ._run_version_pipeline import render_history, render_pipeline_monitor


def render_ops_audit_tab(base_url: str, project_id: str, actor: str) -> None:
    """Tab: Ops Audit - Pipeline monitor + history + audit trail."""
    with st.expander("📡 Monitor de Execuções", expanded=False):
        render_pipeline_monitor(base_url, project_id, actor, context="audit")
    with st.expander("📋 Histórico de execuções", expanded=False):
        render_history(base_url, project_id, actor, context="audit")
    with st.expander("🔍 Audit Trail", expanded=False):
        render_audit(base_url, project_id, actor)


def _render_version_tree_lines(
    node: str | None, version_meta: dict, children: dict, prefix: str = "", is_last: bool = True
) -> list[str]:
    """Recursively builds version tree display lines."""
    kids = sorted(children.get(node, []))
    lines: list[str] = []
    if node is not None:
        run = version_meta.get(node, {})
        ts = str(run.get("started_at") or "")[:16].replace("T", " ")
        status = run.get("status", "")
        status_icon = "[OK]" if status == "OK" else ("[ERRO]" if status == "ERRO" else "[--]")
        connector = "└─" if is_last else "├─"
        lines.append(f"{prefix}{connector} {status_icon} {node} — {ts or '–'}")
        child_prefix = prefix + ("   " if is_last else "│  ")
    else:
        child_prefix = ""
    for i, kid in enumerate(kids):
        lines.extend(_render_version_tree_lines(kid, version_meta, children, child_prefix, i == len(kids) - 1))
    return lines


def _render_compare_tree(project_id: str, versions: list, base_url: str, actor: str) -> None:
    """Renders version lineage tree inside an expander."""
    try:
        runs = api_call(method="GET", path=f"/api/projects/{project_id}/runs", base_url=base_url, actor=actor).get(
            "items", []
        )
        version_meta = {r.get("version"): r for r in runs if r.get("version")}
        children: dict[str | None, list[str]] = {}
        for v in versions:
            run = version_meta.get(v, {})
            parent = run.get("base_version") or None
            children.setdefault(parent, []).append(v)
        tree_lines = _render_version_tree_lines(None, version_meta, children)
        if tree_lines:
            with st.expander("📜 Linhagem de versões", expanded=False):
                st.code("\n".join(tree_lines), language=None)
    except Exception:
        pass


def _do_compare(project_id: str, left: str, right: str, base_url: str, actor: str) -> None:
    """Executes comparison and shows delta metrics."""
    if not st.button("Comparar", type="secondary"):
        return
    try:
        result = api_call(
            method="POST",
            path=f"/api/projects/{project_id}/compare",
            base_url=base_url,
            payload={"left_version": left, "right_version": right},
            actor=actor,
        )
    except RuntimeError as exc:
        err = str(exc)
        if "sem canônico" in err or "400" in err:
            st.warning(
                "Uma das versões selecionadas ainda não possui dados de pipeline executados. "
                "Execute o pipeline nessa versão antes de comparar."
            )
        else:
            st.error(f"Erro ao comparar versões: {exc}")
        return
    deltas = result.get("deltas", {})
    col1, col2, col3 = st.columns(3)
    col1.metric(
        "Delta custo total",
        f"{deltas.get('custo_total', 0.0):,.2f}",
        delta=f"{deltas.get('custo_total', 0.0):,.2f}",
        delta_color="inverse",
    )
    col2.metric(
        "Delta margem %", f"{deltas.get('margem_pct', 0.0):,.2f}", delta=f"{deltas.get('margem_pct', 0.0):,.2f}"
    )
    col3.metric(
        "Delta PE deficit",
        f"{deltas.get('pe_deficit_items', 0.0):,.0f}",
        delta=f"{deltas.get('pe_deficit_items', 0.0):,.0f}",
        delta_color="inverse",
    )
    st.subheader("Deltas detalhados")
    st.dataframe([{"indicador": k, "delta": v} for k, v in deltas.items()], width="stretch")
    render_mapping_table("Comparação de versões", result)


def render_compare(base_url: str, project: dict, actor: str) -> None:
    """Render version comparison."""
    st.subheader("🔀 Comparar versões")
    project_id = project["project_id"]
    try:
        versions = api_call(
            method="GET", path=f"/api/projects/{project_id}/versions", base_url=base_url, actor=actor
        ).get("items", [])
    except Exception as exc:
        st.error(f"Falha ao carregar versões: {exc}")
        return
    if len(versions) < 2:
        st.info("São necessárias ao menos duas versões para comparar.")
        return
    _render_compare_tree(project_id, versions, base_url, actor)
    left = st.selectbox("Versão base (esquerda)", options=versions, index=0)
    right = st.selectbox("Versão comparada (direita)", options=versions, index=len(versions) - 1)
    _do_compare(project_id, left, right, base_url, actor)


def render_audit(base_url: str, project_id: str, actor: str) -> None:
    """Render audit trail — paginated."""
    cache_key = f"audit-rows-{project_id}"
    col_q, col_reload = st.columns([5, 1])
    q = col_q.text_input(
        "Buscar evento ou actor",
        key=f"audit-q-{project_id}",
        label_visibility="collapsed",
        placeholder="Filtrar auditoria…",
    )
    if col_reload.button("↺", key=f"audit-reload-{project_id}"):
        st.session_state.pop(cache_key, None)

    if cache_key not in st.session_state:
        try:
            st.session_state[cache_key] = api_call(
                method="GET",
                path=f"/api/projects/{project_id}/audit",
                base_url=base_url,
                params={"limit": 1000},
                actor=actor,
            ).get("items", [])
        except Exception as exc:
            msg = str(exc)
            if "404" in msg or "Not Found" in msg:
                st.info("Audit trail indisponivel para este ambiente/API.")
            else:
                st.warning(f"Audit trail indisponivel nesta API: {exc}")
            return

    rows = st.session_state[cache_key]
    if not rows:
        st.info("Sem eventos de auditoria para este projeto.")
        return

    if q:
        q_l = q.lower()
        rows = [r for r in rows if q_l in str(r).lower()]

    render_paginated_table(rows, page_key=f"audit-page-{project_id}", label="eventos")


