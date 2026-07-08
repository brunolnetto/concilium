"""Camada de apresentação — layout Streamlit (parte extraída de layout.py)."""

from __future__ import annotations

import json

import streamlit as st

from ...helpers.helpers import (
    collect_skill_candidates,
    extract_bdi_dict,
    extract_skill_base_inputs,
    set_path,
)
from ...infra.api import api_call
from ...molecules.components import (
    render_mapping_table,
    render_numeric_override_editor,
)


def _render_numeric_override_section(
    project_id: str, reference: dict, current: dict, base_url: str, actor: str
) -> None:
    """Renders the numeric override editor section."""
    st.divider()
    st.subheader("Override numérico rápido")
    skill_options = collect_skill_candidates(reference, current)
    numeric_skill_id = st.selectbox(
        "Skill para edição simplificada", options=skill_options, key=f"numeric-override-skill-{project_id}"
    )
    base_inputs = extract_skill_base_inputs(reference, numeric_skill_id)
    current_inputs = current.get(numeric_skill_id, {}) if isinstance(current.get(numeric_skill_id), dict) else {}
    with st.expander(f"Composição base - {numeric_skill_id}", expanded=False):
        if base_inputs:
            render_mapping_table("Base de referência", base_inputs)
        else:
            st.info("Sem composição base encontrada para este skill na referência.")
    numeric_rows = render_numeric_override_editor(project_id, numeric_skill_id, base_inputs, current_inputs)
    if numeric_rows:
        if st.button("Salvar override numérico", key=f"save-numeric-{project_id}", type="primary"):
            new_inputs = json.loads(json.dumps(base_inputs)) if isinstance(base_inputs, dict) else {}
            for row in numeric_rows:
                dotted = str(row.get("campo") or "")
                if not dotted:
                    continue
                set_path(new_inputs, dotted, float(row.get("novo_valor") or 0.0))
            result = api_call(
                method="POST",
                path=f"/api/projects/{project_id}/overrides",
                base_url=base_url,
                payload={"skill_id": numeric_skill_id, "inputs": new_inputs},
                actor=actor,
            )
            st.success(f"Override numérico salvo para {numeric_skill_id}")
            render_mapping_table("Overrides atualizados", result)


def _render_saved_bdi_section(project_id: str, reference: dict, current: dict, base_url: str, actor: str) -> None:
    """Renders the BDI quick-edit section in saved overrides."""
    st.divider()
    st.subheader("BDI da versão base")
    st.caption("Edite os fatores de BDI e salve como override dos skills financeiros. Ex.: 0.25 = 25%.")
    skill06_base = extract_skill_base_inputs(reference, "06-resultado-financeiro")
    skill08_base = extract_skill_base_inputs(reference, "06-resultado-financeiro")
    skill06_cur = (
        current.get("06-resultado-financeiro", {}) if isinstance(current.get("06-resultado-financeiro"), dict) else {}
    )
    skill08_cur = (
        current.get("06-resultado-financeiro", {}) if isinstance(current.get("06-resultado-financeiro"), dict) else {}
    )
    bdi_base = extract_bdi_dict(skill06_base) or extract_bdi_dict(skill08_base)
    bdi_cur = extract_bdi_dict(skill06_cur) or extract_bdi_dict(skill08_cur)
    bdi_keys = ["mao_obra", "equipamentos", "material", "diesel", "indireto"]
    bdi_defaults = {k: float(bdi_cur.get(k, bdi_base.get(k, 0.0))) for k in bdi_keys}
    st.dataframe(
        [
            {"categoria": k, "fator": round(bdi_defaults[k], 4), "percentual": f"{bdi_defaults[k] * 100:.2f}%"}
            for k in bdi_keys
        ],
        width="stretch",
        hide_index=True,
    )
    bdi_col1, bdi_col2, bdi_col3, bdi_col4, bdi_col5 = st.columns(5)
    edited_bdi = {
        "mao_obra": bdi_col1.number_input(
            "MO",
            min_value=0.0,
            max_value=5.0,
            value=bdi_defaults["mao_obra"],
            step=0.01,
            key=f"ov-bdi-mo-{project_id}",
        ),
        "equipamentos": bdi_col2.number_input(
            "Equip.",
            min_value=0.0,
            max_value=5.0,
            value=bdi_defaults["equipamentos"],
            step=0.01,
            key=f"ov-bdi-eq-{project_id}",
        ),
        "material": bdi_col3.number_input(
            "Material",
            min_value=0.0,
            max_value=5.0,
            value=bdi_defaults["material"],
            step=0.01,
            key=f"ov-bdi-mat-{project_id}",
        ),
        "diesel": bdi_col4.number_input(
            "Diesel",
            min_value=0.0,
            max_value=5.0,
            value=bdi_defaults["diesel"],
            step=0.01,
            key=f"ov-bdi-dsl-{project_id}",
        ),
        "indireto": bdi_col5.number_input(
            "Indireto",
            min_value=0.0,
            max_value=5.0,
            value=bdi_defaults["indireto"],
            step=0.01,
            key=f"ov-bdi-ind-{project_id}",
        ),
    }
    if st.button("Salvar BDI", key=f"save-ov-bdi-{project_id}", use_container_width=True, type="primary"):
        p06 = {"bdi_aplicado": {k: edited_bdi[k] for k in ["mao_obra", "equipamentos", "material", "diesel"]}}
        p08 = {"bdi_aplicado": edited_bdi}
        for skill_id, payload in [("06-resultado-financeiro", {**p06, **p08})]:
            api_call(
                method="POST",
                path=f"/api/projects/{project_id}/overrides",
                base_url=base_url,
                payload={"skill_id": skill_id, "inputs": payload},
                actor=actor,
            )
        st.success("BDI salvo.")


def _render_remove_override_section(project_id: str, current: dict, base_url: str, actor: str) -> None:
    """Renders the quick-remove override section."""
    st.divider()
    st.caption("Remoção rápida de override por skill")
    removable_skills = sorted([k for k, v in current.items() if isinstance(v, dict)])
    if not removable_skills:
        st.info("Nenhum override explícito para remover no momento.")
        return
    remove_skill_id = st.selectbox(
        "Skill para remover override", options=removable_skills, key=f"remove-override-skill-{project_id}"
    )
    if st.button("Remover override da skill selecionada", key=f"remove-override-btn-{project_id}", type="secondary"):
        result = api_call(
            method="DELETE",
            path=f"/api/projects/{project_id}/overrides/{remove_skill_id}",
            base_url=base_url,
            actor=actor,
        )
        st.success("Override removido")
        render_mapping_table("Override atualizado", result)


def render_saved_override(base_url: str, project_id: str, actor: str) -> None:
    """Render saved overrides editor."""
    st.subheader("4) Overrides salvos")
    try:
        current = api_call(method="GET", path=f"/api/projects/{project_id}/overrides", base_url=base_url, actor=actor)
    except Exception as exc:
        st.error(f"Falha ao carregar overrides: {exc}")
        return
    st.caption("Overrides atualmente salvos")
    render_mapping_table("Overrides atuais", current)
    if not any(isinstance(v, dict) for v in current.values()):
        st.info("Sem override explícito salvo. Abaixo você pode editar diretamente a composição base por skill.")
    try:
        reference = api_call(
            method="GET", path=f"/api/projects/{project_id}/benchmark-reference", base_url=base_url, actor=actor
        )
    except Exception:
        reference = {}
    _render_numeric_override_section(project_id, reference, current, base_url, actor)
    _render_saved_bdi_section(project_id, reference, current, base_url, actor)
    _render_remove_override_section(project_id, current, base_url, actor)


