"""Reusable Streamlit UI components."""

from __future__ import annotations

import streamlit as st

from ..helpers.helpers import stringify_table_value


def render_project_kind_badge(project: dict) -> None:
    """Display project type badge."""
    kind = (project.get("tipo_projeto") or "hot_project").lower()
    if kind == "hot_project":
        st.markdown("### Tipo: HOT_PROJECT")
    else:
        st.markdown("### Tipo: PROJECT")


def render_mapping_table(title: str, mapping: dict | None) -> None:
    """Render a key-value mapping as a dataframe."""
    if mapping is None:
        return
    rows = [{"chave": key, "valor": stringify_table_value(value)} for key, value in mapping.items()]
    st.subheader(title)
    st.dataframe(rows, width="stretch", hide_index=True)


def render_list_table(title: str, rows: list[dict] | list[str] | list[int] | list[float]) -> None:
    """Render a list as a dataframe."""
    st.subheader(title)
    if not rows:
        st.info("Sem itens.")
        return
    if isinstance(rows[0], dict):
        st.dataframe(rows, width="stretch", hide_index=True)
        return
    st.dataframe([{"valor": item} for item in rows], width="stretch", hide_index=True)


def render_download_button(
    base_url: str,
    project_id: str,
    kind: str,
    filename: str,
    version: str | None,
    actor: str,
    label: str | None = None,
    key: str | None = None,
    use_container_width: bool = False,
) -> None:
    """Render a download button for an artifact."""
    from ..infra.api import fetch_artifact_bytes

    try:
        payload = fetch_artifact_bytes(base_url, project_id, kind, filename, version, actor)
        st.download_button(
            label=label or f"📥 {filename}",
            data=payload,
            file_name=filename,
            key=key or f"download-{project_id}-{kind}-{filename}",
            use_container_width=use_container_width,
        )
    except Exception as exc:
        st.caption(f"❌ {filename}: {str(exc)[:50]}...")


def render_team_editor(
    project_id: str,
    reference: dict,
    state_key: str,
) -> object:
    """Render team adjustment data editor."""
    from ..helpers.helpers import apply_global_team_adjustment, build_team_adjustment_rows

    if not st.session_state.get(state_key):
        st.session_state[state_key] = build_team_adjustment_rows(reference)
    action_col1, action_col2, action_col3, action_col4 = st.columns([1, 1, 1, 2])
    pct = action_col1.number_input(
        "Ajuste global (%)", min_value=-90.0, max_value=300.0, value=0.0, step=5.0, key=f"team-global-pct-{project_id}"
    )
    if action_col2.button("Aplicar ajuste", key=f"team-apply-pct-{project_id}"):
        st.session_state[state_key] = apply_global_team_adjustment(st.session_state[state_key], float(pct))
    if action_col3.button("Restaurar base", key=f"team-reset-{project_id}"):
        st.session_state[state_key] = build_team_adjustment_rows(reference)
    action_col4.caption("Use o ajuste global para alterações rápidas e refine item a item na tabela abaixo.")
    edited_rows = st.data_editor(
        st.session_state[state_key],
        width="stretch",
        hide_index=True,
        column_config={
            "item_id": st.column_config.TextColumn("Item ID", width="small", disabled=True),
            "descricao": st.column_config.TextColumn("Descrição", width="large", disabled=True),
            "cpu_id": st.column_config.TextColumn("CPU", width="small", disabled=True),
            "num_equipes_base": st.column_config.NumberColumn("Base", disabled=True, format="%.2f", width="small"),
            "num_equipes_maximo": st.column_config.NumberColumn(
                "✏️ Máx. equipes", min_value=1.0, step=1.0, format="%.0f", width="small"
            ),
            "start_week": st.column_config.NumberColumn("Sem. início", disabled=True, format="%.0f", width="small"),
            "end_week": st.column_config.NumberColumn("Sem. fim", disabled=True, format="%.0f", width="small"),
            "duration_weeks": st.column_config.NumberColumn(
                "Duração (sem.)", disabled=True, format="%.0f", width="small"
            ),
        },
        disabled=[
            "item_id",
            "descricao",
            "cpu_id",
            "num_equipes_base",
            "start_week",
            "end_week",
            "duration_weeks",
            "producao_diaria",
            "quantitativo",
        ],
        key=f"team-editor-{project_id}",
    )
    if hasattr(edited_rows, "to_dict"):
        st.session_state[state_key] = edited_rows.to_dict("records")
    else:
        st.session_state[state_key] = list(edited_rows or [])
    return edited_rows


def render_numeric_override_editor(
    project_id: str,
    skill_id: str,
    base_inputs: dict,
    current_inputs: dict,
) -> list[dict]:
    """Render numeric override editor."""
    from ..helpers.helpers import flatten_numeric_paths

    base_flat = dict(flatten_numeric_paths(base_inputs))
    current_flat = dict(flatten_numeric_paths(current_inputs))
    all_paths = sorted(set(base_flat.keys()) | set(current_flat.keys()))
    if not all_paths:
        st.info("Sem campos numéricos detectados para este skill na base/override atual.")
        return []
    numeric_rows = []
    for path in all_paths:
        base_value = float(base_flat.get(path, 0.0))
        current_value = float(current_flat.get(path, base_value))
        numeric_rows.append(
            {
                "campo": path,
                "base": base_value,
                "override_atual": current_value,
                "novo_valor": current_value,
            }
        )
    edited_numeric = st.data_editor(
        numeric_rows,
        width="stretch",
        hide_index=True,
        column_config={
            "campo": st.column_config.TextColumn("Campo", disabled=True),
            "base": st.column_config.NumberColumn("Base", disabled=True, format="%.6f"),
            "override_atual": st.column_config.NumberColumn("Atual", disabled=True, format="%.6f"),
            "novo_valor": st.column_config.NumberColumn("Novo valor", format="%.6f", step=0.01),
        },
        disabled=["campo", "base", "override_atual"],
        key=f"numeric-editor-{project_id}-{skill_id}",
    )
    to_dict = getattr(edited_numeric, "to_dict", None)
    if callable(to_dict):
        records = to_dict("records")
        return [r for r in records if isinstance(r, dict)] if isinstance(records, list) else []
    return [r for r in edited_numeric if isinstance(r, dict)] if isinstance(edited_numeric, list) else []
