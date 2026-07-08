"""Helpers extracted from project_page.py (parte extraída de _project_page_helpers_b.py, grupo _pcat_render)."""

from __future__ import annotations

from typing import Any

import streamlit as st

from ...helpers.helpers import dataframe_selected_rows
from ...infra.api import api_call
from ._pcat_data import _pcat_apply_filters, _pcat_build_batch_preview, _pcat_load_panel_data
from ._pcat_helpers import (
    _pcat_cpu_parts,
    _pcat_cpus_used_in_eap,
    _pcat_estimate_batch_impact,
    _pcat_extract_eap_rows,
    _pcat_has_complete_composition,
    _pcat_health_checks,
    _pcat_insumo_index,
    _pcat_is_price_reference_stale,
    _pcat_mini_diff_text,
    _pcat_override_badge,
)


def _pcat_render_health_panel(
    cpu_ids: list[str],
    index: dict[str, dict[str, Any]],
    insumos_idx: dict[str, dict[str, Any]],
) -> None:
    rows: list[dict[str, str]] = []
    for cpu_id in cpu_ids:
        alerts = _pcat_health_checks(index.get(cpu_id) or {}, insumos_idx)
        for alert in alerts:
            rows.append({"CPU": cpu_id, "Alerta": alert})

    if rows:
        st.warning(f"{len(rows)} alerta(s) de saúde detectado(s).")
        st.dataframe(rows, hide_index=True, use_container_width=True)
    else:
        st.success("Sem alertas de saúde para o conjunto selecionado.")


def _pcat_render_catalog_filters(
    project_id: str, rows: list[dict[str, Any]]
) -> tuple[str, list[str], bool, bool, bool]:
    c1, c2, c3 = st.columns([3, 2, 3])
    q = c1.text_input("Buscar CPU", placeholder="Código, descrição ou diff", key=f"pcat-q-{project_id}")
    categorias = sorted({r["categoria"] for r in rows if r["categoria"]})
    cat_filters = c2.multiselect("Categoria", options=categorias, key=f"pcat-cats-{project_id}")
    with c3:
        only_used = st.checkbox("usadas na EAP atual", key=f"pcat-used-{project_id}")
        only_incomplete = st.checkbox("composição incompleta", key=f"pcat-incomplete-{project_id}")
        only_stale_price = st.checkbox("sem preço referência recente", key=f"pcat-stale-{project_id}")
    return q, cat_filters, only_used, only_incomplete, only_stale_price


def _pcat_select_rows_table(project_id: str, filtered_rows: list[dict[str, Any]]) -> list[str]:
    view_rows = [
        {
            "CPU": r["cpu_id"],
            "Descrição": r["descricao"],
            "Categoria": r["categoria"],
            "Status": r["override_status"],
            "Mini diff": r["mini_diff"],
            "EAP": "Sim" if r["used_in_eap"] else "Não",
            "Saúde": "⚠" if r["health_count"] else "✓",
        }
        for r in filtered_rows
    ]
    sel = st.dataframe(
        view_rows,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="multi-row",
        key=f"pcat-table-{project_id}",
    )
    indices = dataframe_selected_rows(sel)
    return [filtered_rows[i]["cpu_id"] for i in indices if i < len(filtered_rows)]


def _pcat_render_step_edit(project_id: str, selected_cpu_ids: list[str], base_index: dict[str, dict[str, Any]]) -> None:
    st.markdown("**Passo 2/3 — Editar**")
    if not selected_cpu_ids:
        st.info("Selecione pelo menos uma CPU no passo anterior.")
        return

    st.caption(f"CPUs selecionadas: {len(selected_cpu_ids)}")
    c1, c2, c3 = st.columns(3)
    prod_factor = c1.number_input("Ajuste produtividade (%)", value=0.0, step=1.0, key=f"pcat-prod-{project_id}")
    team_factor = c2.number_input("Ajuste equipe (%)", value=0.0, step=1.0, key=f"pcat-team-{project_id}")
    comp_factor = c3.number_input("Ajuste composição (%)", value=0.0, step=1.0, key=f"pcat-comp-{project_id}")

    preview = _pcat_build_batch_preview(selected_cpu_ids, base_index, prod_factor, team_factor, comp_factor)
    st.session_state[f"pcat-preview-{project_id}"] = preview

    table = []
    for cpu_id in selected_cpu_ids:
        base_cpu = base_index.get(cpu_id) or {}
        new_cpu = preview.get(cpu_id) or base_cpu
        table.append(
            {
                "CPU": cpu_id,
                "Prod. base": float(base_cpu.get("producao_horaria") or 0.0),
                "Prod. nova": float(new_cpu.get("producao_horaria") or 0.0),
                "Equipe base": len(_pcat_cpu_parts(base_cpu)[0]) + len(_pcat_cpu_parts(base_cpu)[1]),
                "Equipe nova": len(_pcat_cpu_parts(new_cpu)[0]) + len(_pcat_cpu_parts(new_cpu)[1]),
                "Comp. base": len(_pcat_cpu_parts(base_cpu)[2]),
                "Comp. nova": len(_pcat_cpu_parts(new_cpu)[2]),
            }
        )
    st.dataframe(table, hide_index=True, use_container_width=True)


def _pcat_render_diff_table(
    selected_cpu_ids: list[str], base_index: dict[str, dict[str, Any]], preview: dict[str, dict[str, Any]]
) -> None:
    diff_rows = []
    for cpu_id in selected_cpu_ids:
        base_cpu = base_index.get(cpu_id) or {}
        new_cpu = preview.get(cpu_id) or base_cpu
        diff_rows.append(
            {
                "CPU": cpu_id,
                "Badge": _pcat_override_badge(base_cpu, new_cpu),
                "Mini diff": _pcat_mini_diff_text(base_cpu, new_cpu),
            }
        )
    st.dataframe(diff_rows, hide_index=True, use_container_width=True)


def _pcat_apply_batch(
    project_id: str,
    selected_cpu_ids: list[str],
    preview: dict[str, dict[str, Any]],
    motivo: str,
    base_url: str,
    actor: str,
) -> None:
    if not motivo.strip():
        st.error("Informe o motivo único para registrar auditoria padronizada.")
        return
    done = 0
    reason = f"[lote-catalogo] {motivo.strip()}"
    for cpu_id in selected_cpu_ids:
        payload = preview.get(cpu_id)
        if not isinstance(payload, dict):
            continue
        try:
            api_call(
                "POST",
                f"/api/projects/{project_id}/catalog/cpus/{cpu_id}",
                base_url=base_url,
                actor=actor,
                payload=payload,
                params={"motivo": reason},
            )
            done += 1
        except Exception as exc:
            st.error(f"Falha ao aplicar em {cpu_id}: {exc}")
    if done:
        st.success(f"{done} CPU(s) atualizada(s) com auditoria única ({reason}).")
        st.session_state.pop(f"pcat-preview-{project_id}", None)


def _pcat_render_step_review(
    project_id: str,
    selected_cpu_ids: list[str],
    base_index: dict[str, dict[str, Any]],
    eap_rows: list[dict[str, Any]],
    insumos_idx: dict[str, dict[str, Any]],
    base_url: str,
    actor: str,
) -> None:
    st.markdown("**Passo 3/3 — Revisar impacto e aplicar**")
    preview = st.session_state.get(f"pcat-preview-{project_id}") or {}
    if not selected_cpu_ids or not preview:
        st.info("Gere o preview no passo 2 antes de revisar.")
        return

    delta_monthly, prazo_pct = _pcat_estimate_batch_impact(base_index, preview, eap_rows, insumos_idx)
    k1, k2 = st.columns(2)
    k1.metric("Impacto mensal estimado", f"R$ {delta_monthly:,.2f}")
    k2.metric("Impacto estimado no prazo (EAP)", f"{prazo_pct:+.2f}%")

    _pcat_render_diff_table(selected_cpu_ids, base_index, preview)
    _pcat_render_health_panel(selected_cpu_ids, preview, insumos_idx)

    motivo = st.text_input(
        "Motivo único da ação em lote *",
        placeholder="Ex: calibração de produtividade/composição após revisão de campo",
        key=f"pcat-motivo-{project_id}",
    )
    if st.button("Aplicar em lote", type="primary", key=f"pcat-apply-{project_id}"):
        _pcat_apply_batch(project_id, selected_cpu_ids, preview, motivo, base_url, actor)


def _pcat_build_catalog_rows(
    base_index: dict[str, dict[str, Any]],
    override_index: dict[str, dict[str, Any]],
    used_in_eap: set[str],
    insumos_idx: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for cpu_id, base_cpu in sorted(base_index.items()):
        ov_cpu = override_index.get(cpu_id) or {}
        merged = {**base_cpu, **ov_cpu} if ov_cpu else base_cpu
        health = _pcat_health_checks(merged, insumos_idx)
        categoria = str(base_cpu.get("categoria") or "")
        descricao = str(base_cpu.get("descricao") or cpu_id)
        status = _pcat_override_badge(base_cpu, ov_cpu)
        mini = _pcat_mini_diff_text(base_cpu, ov_cpu)
        ref_price = str(merged.get("data_referencia_preco") or base_cpu.get("data_referencia_preco") or "")
        rows.append(
            {
                "cpu_id": cpu_id,
                "descricao": descricao,
                "categoria": categoria,
                "override_status": status,
                "mini_diff": mini,
                "used_in_eap": cpu_id in used_in_eap,
                "composicao_incompleta": not _pcat_has_complete_composition(merged),
                "preco_defasado": _pcat_is_price_reference_stale(ref_price),
                "health_count": len(health),
                "search_text": f"{cpu_id} {descricao} {categoria} {status} {mini}".lower(),
            }
        )
    return rows


def _pcat_render_summary_header(catalog_id: str, rows: list[dict[str, Any]]) -> None:
    total = len(rows)
    sem = sum(1 for r in rows if r["override_status"] == "Sem override")
    parcial = sum(1 for r in rows if r["override_status"] == "Override parcial")
    total_ov = sum(1 for r in rows if r["override_status"] == "Override total")
    h1, h2, h3, h4 = st.columns(4)
    h1.metric("CPUs", total)
    h2.metric("Sem override", sem)
    h3.metric("Override parcial", parcial)
    h4.metric("Override total", total_ov)
    st.caption(f"Catálogo ativo (contexto): {catalog_id}")


def _pcat_dispatch_step(
    step: str,
    project_id: str,
    selected_cpu_ids: list[str],
    base_index: dict[str, dict[str, Any]],
    reference: dict[str, Any],
    insumos_idx: dict[str, dict[str, Any]],
    base_url: str,
    actor: str,
) -> None:
    eap_rows = _pcat_extract_eap_rows(reference)
    if step == "Selecionar CPU":
        st.info("Selecione uma ou mais CPUs na tabela acima para avançar ao passo de edição.")
        _pcat_render_health_panel(
            selected_cpu_ids, {cid: base_index.get(cid) or {} for cid in selected_cpu_ids}, insumos_idx
        )
    elif step == "Editar":
        _pcat_render_step_edit(project_id, selected_cpu_ids, base_index)
    else:
        _pcat_render_step_review(project_id, selected_cpu_ids, base_index, eap_rows, insumos_idx, base_url, actor)


def _render_project_catalog_section(base_url: str, project_id: str, actor: str) -> None:
    """Painel de catálogo por projeto com delta visual, pipeline de edição e saúde de dados."""
    st.caption(
        "Delta Base x Override por CPU, filtros operacionais, edição em 3 passos, ações em lote e health checks."
    )

    catalog_id, base_index, override_index, reference = _pcat_load_panel_data(project_id, base_url, actor)
    if not base_index:
        st.info("Não foi possível carregar CPUs do catálogo para este projeto.")
        return

    used_in_eap = _pcat_cpus_used_in_eap(reference)
    insumos_idx = _pcat_insumo_index(reference)
    rows = _pcat_build_catalog_rows(base_index, override_index, used_in_eap, insumos_idx)

    _pcat_render_summary_header(catalog_id, rows)

    q, cat_filters, only_used, only_incomplete, only_stale_price = _pcat_render_catalog_filters(project_id, rows)
    filtered = _pcat_apply_filters(rows, q, cat_filters, only_used, only_incomplete, only_stale_price)
    st.caption(f"Filtradas: {len(filtered)} CPU(s)")

    selected_cpu_ids = _pcat_select_rows_table(project_id, filtered)

    step = st.radio(
        "Pipeline de edição",
        options=["Selecionar CPU", "Editar", "Revisar impacto"],
        horizontal=True,
        key=f"pcat-step-{project_id}",
    )

    _pcat_dispatch_step(step, project_id, selected_cpu_ids, base_index, reference, insumos_idx, base_url, actor)


