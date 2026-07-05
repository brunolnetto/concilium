"""Funções auxiliares de catálogo. Extraído de catalogo_page."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any, cast

import streamlit as st

try:
    from ..atoms.form_contracts import (
        CPU_EDITABLE_FIELDS,
        CPU_READONLY_FIELDS,
        render_typed_form,
    )
    from ..config import DEFAULT_ACTOR, DEFAULT_BASE_URL
    from ..infra.api import api_call
except ImportError:
    src_root = Path(__file__).resolve().parents[4]
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))
    from concilium.presentation.ui.atoms.form_contracts import (
        CPU_EDITABLE_FIELDS,
        CPU_READONLY_FIELDS,
        render_typed_form,
    )
    from concilium.presentation.ui.config import DEFAULT_ACTOR, DEFAULT_BASE_URL
    from concilium.presentation.ui.infra.api import api_call


def _cat_workspace_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _cat_catalogs_root() -> Path:
    return _cat_workspace_root() / "config" / "catalogos"


def _cat_ctx_entry(ctx: dict) -> tuple[str, dict] | None:
    cid = str(ctx.get("id") or "")
    if not cid:
        return None
    versions = ctx.get("versions") or []
    current_v = ctx.get("current_version", "v1")
    current = next((v for v in versions if v.get("version") == current_v), ctx)
    catalogo_id = str(current.get("catalogo_id") or ctx.get("catalogo_id") or "")
    return cid, {"catalogo_id": catalogo_id}


def _cat_context_from_api() -> dict | None:
    try:
        resp = api_call(method="GET", path="/api/contextos", base_url=DEFAULT_BASE_URL, actor=DEFAULT_ACTOR)
    except Exception:
        return None
    out: dict[str, dict[str, str]] = {}
    for ctx in resp.get("items") or []:
        entry = _cat_ctx_entry(ctx)
        if entry is not None:
            out[entry[0]] = entry[1]
    return out


def _cat_context_from_fs() -> dict[str, dict[str, str]]:
    contextos_dir = _cat_workspace_root() / "config" / "contextos"
    out: dict[str, dict[str, str]] = {}
    for ctx_dir in sorted(contextos_dir.iterdir()) if contextos_dir.exists() else []:
        if ctx_dir.is_dir():
            meta_file = ctx_dir / "contexto.json"
            if meta_file.exists():
                try:
                    payload = json.loads(meta_file.read_text(encoding="utf-8"))
                    cid = str(payload.get("id") or ctx_dir.name)
                    out[cid] = {"catalogo_id": str(payload.get("catalogo_id") or "")}
                except Exception:
                    pass
    return out


def _cat_context_metadata() -> dict[str, dict[str, str]]:
    result = _cat_context_from_api()
    if result is not None:
        return result
    return _cat_context_from_fs()


def _cat_list_catalog_ids() -> list[str]:
    root = _cat_catalogs_root()
    if not root.exists():
        return []
    return sorted([p.name for p in root.iterdir() if p.is_dir() and not p.name.endswith("_backup_ids")])


def _cat_catalog_cpu_paths(catalog_id: str) -> list[Path]:
    cpus_dir = _cat_catalogs_root() / catalog_id / "cpus"
    if not cpus_dir.exists():
        return []
    return sorted(cpus_dir.glob("*.json"))


def _cat_load_cpu_payload(cpu_file: Path) -> dict:
    try:
        return json.loads(cpu_file.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _cat_cpu_row(payload: dict, fallback_id: str) -> dict:
    return {
        "codigo": str(payload.get("codigo") or fallback_id),
        "descricao": str(payload.get("descricao") or ""),
        "categoria": str(payload.get("categoria") or ""),
        "unidade": str(payload.get("unidade") or ""),
        "origem": str(payload.get("origem") or ""),
        "producao_horaria": float(payload.get("producao_horaria") or 0.0),
        "fonte_preco": str(payload.get("fonte_preco") or ""),
        "data_referencia_preco": str(payload.get("data_referencia_preco") or ""),
    }


def _catalogo_search_text(row: dict) -> str:
    return " ".join(
        [
            str(row.get("codigo") or ""),
            str(row.get("descricao") or ""),
            str(row.get("categoria") or ""),
            str(row.get("origem") or ""),
        ]
    ).lower()


def _apply_catalogo_filter(rows: list, search: str, selected_categorias: list) -> list:
    filtered = []
    for row in rows:
        if selected_categorias and str(row.get("categoria") or "") not in selected_categorias:
            continue
        if search and search not in _catalogo_search_text(row):
            continue
        filtered.append(row)
    return filtered


def _get_categorias(rows: list) -> list[str]:
    return sorted({str(r.get("categoria") or "") for r in rows if str(r.get("categoria") or "")})


def _build_catalog_rows(cpu_files: list) -> tuple[dict, list]:
    payload_by_codigo: dict[str, dict] = {}
    rows: list[dict] = []
    for cpu_file in cpu_files:
        payload = _cat_load_cpu_payload(cpu_file)
        fallback_code = cpu_file.stem
        row = _cat_cpu_row(payload, fallback_code)
        codigo = str(row["codigo"])
        payload_by_codigo[codigo] = payload if payload else {"codigo": codigo}
        rows.append(row)
    return payload_by_codigo, rows


def _get_source_rows(page_rows: list, cached_rows: object) -> list:
    page_codes = {str(r.get("codigo")) for r in page_rows}
    if isinstance(cached_rows, list):
        # cast: isinstance(x, list) sobre object não parametriza os elementos no ty
        cached_list = cast("list[dict[str, Any]]", cached_rows)
        cached_codes = {str(r.get("codigo")) for r in cached_list}
        if cached_codes == page_codes:
            return cached_list
    return [dict(row, __status="Base") for row in page_rows]


def _track_edited_status(edited_rows_raw: list, base_map: dict) -> tuple[list, list]:
    changed_rows: list[dict] = []
    rows_with_status: list[dict] = []
    for row in edited_rows_raw:
        clean_row = {k: v for k, v in row.items() if k != "__status"}
        codigo = str(clean_row.get("codigo") or "").strip()
        if not codigo or codigo not in base_map:
            continue
        if clean_row != base_map[codigo]:
            changed_rows.append(clean_row)
            rows_with_status.append(dict(clean_row, __status="Alterada"))
        else:
            rows_with_status.append(dict(clean_row, __status="Base"))
    return changed_rows, rows_with_status


def _save_catalogo_rows(
    changed_rows: list,
    payload_by_codigo: dict,
    project_id: str,
    base_url: str,
    actor: str,
    motivo: str,
) -> int:
    changed_count = 0
    for row in changed_rows:
        codigo = str(row.get("codigo") or "").strip()
        payload: dict[str, Any] = dict(payload_by_codigo.get(codigo) or {"codigo": codigo})
        payload["descricao"] = row.get("descricao", payload.get("descricao", ""))
        payload["categoria"] = row.get("categoria", payload.get("categoria", ""))
        payload["unidade"] = row.get("unidade", payload.get("unidade", ""))
        payload["origem"] = row.get("origem", payload.get("origem", ""))
        payload["producao_horaria"] = float(row.get("producao_horaria") or 0.0)
        payload["fonte_preco"] = row.get("fonte_preco", payload.get("fonte_preco", ""))
        payload["data_referencia_preco"] = row.get("data_referencia_preco", payload.get("data_referencia_preco", ""))
        try:
            api_call(
                "POST",
                f"/api/projects/{project_id}/catalog/cpus/{codigo}",
                base_url=base_url,
                payload=payload,
                actor=actor,
                params={"motivo": motivo},
            )
            changed_count += 1
        except Exception as exc:
            st.error(f"Falha ao salvar {codigo}: {exc}")
    return changed_count


def _df_to_records(edited: object) -> list:
    to_dict = getattr(edited, "to_dict", None)
    if callable(to_dict):
        records = to_dict("records")
        return records if isinstance(records, list) else []
    return list(edited) if isinstance(edited, list) else []


def _render_catalogo_tab0(project: dict, project_id: str, base_url: str, actor: str) -> None:
    context_meta = _cat_context_metadata()
    project_contexto = str(project.get("contexto_id") or "")
    default_catalog = context_meta.get(project_contexto, {}).get("catalogo_id") or ""

    catalog_ids = _cat_list_catalog_ids()
    if not catalog_ids:
        st.warning("Nenhum catálogo encontrado em config/catalogos.")
        return

    default_idx = catalog_ids.index(default_catalog) if default_catalog in catalog_ids else 0
    with st.container(border=True):
        st.caption("Contexto de catálogo")
        catalog_id = st.selectbox("Catálogo", options=catalog_ids, index=default_idx, key="catalog-page-catalog-id")
        st.caption(f"Projeto: {project.get('nome', '-')} | Contexto: {project_contexto or '-'}")

    cpu_files = _cat_catalog_cpu_paths(catalog_id)
    if not cpu_files:
        st.info("Este catálogo não possui CPUs em config/catalogos/<id>/cpus.")
        return

    payload_by_codigo, rows = _build_catalog_rows(cpu_files)

    with st.container(border=True):
        st.caption("Filtros rápidos")
        col_filter1, col_filter2 = st.columns([2, 1])
        with col_filter1:
            search = (
                st.text_input(
                    "Buscar CPU",
                    value="",
                    placeholder="Código, descrição, categoria ou origem",
                    key="catalog-page-search",
                )
                .strip()
                .lower()
            )
        categorias = _get_categorias(rows)
        with col_filter2:
            selected_categorias = st.multiselect(
                "Categoria", options=categorias, default=[], key="catalog-page-categorias"
            )

    filtered = _apply_catalogo_filter(rows, search, selected_categorias)
    total = len(filtered)
    with st.container(border=True):
        st.caption("Controle de paginação")
        col_page1, col_page2, col_page3 = st.columns([1, 1, 2])
        with col_page1:
            page_size = st.selectbox("Itens por página", options=[10, 25, 50, 100], index=1, key="catalog-page-size")
        total_pages = max(1, math.ceil(total / page_size))
        with col_page2:
            page_number = st.number_input(
                "Página", min_value=1, max_value=total_pages, value=1, step=1, key="catalog-page-number"
            )
        with col_page3:
            st.caption(f"Total filtrado: {total} | Páginas: {total_pages}")

    total_pages = max(1, math.ceil(total / page_size))
    start = (int(page_number) - 1) * page_size
    end = start + page_size
    page_rows = filtered[start:end]
    base_map = {str(r.get("codigo")): r for r in page_rows}

    editor_cache_key = f"catalog-page-edit-cache-{catalog_id}-{page_number}"
    cached_rows = st.session_state.get(editor_cache_key)
    source_rows = _get_source_rows(page_rows, cached_rows)

    with st.container(border=True):
        st.caption("Dados da página")
        st.caption(f"Exibindo {len(page_rows)} de {total} CPUs (catálogo: {catalog_id}).")
        edited = st.data_editor(
            source_rows,
            hide_index=True,
            width="stretch",
            key=f"catalog-page-editor-{catalog_id}-{page_number}",
            disabled=["codigo", "__status"],
            column_config={
                "__status": st.column_config.TextColumn("Status", disabled=True, width="small"),
                "codigo": st.column_config.TextColumn("ID (bloqueado)", disabled=True, width="medium"),
                "descricao": st.column_config.TextColumn("Descrição", width="large"),
                "categoria": st.column_config.TextColumn("Categoria", width="medium"),
                "unidade": st.column_config.TextColumn("Unidade", width="small"),
                "origem": st.column_config.TextColumn("Origem", width="small"),
                "producao_horaria": st.column_config.NumberColumn("Produção/h", min_value=0.0, step=0.1, format="%.4f"),
                "fonte_preco": st.column_config.TextColumn("Fonte de preço", width="medium"),
                "data_referencia_preco": st.column_config.TextColumn("Data referência", width="small"),
            },
        )

    edited_rows_raw = _df_to_records(edited)
    changed_rows, rows_with_status = _track_edited_status(edited_rows_raw, base_map)
    st.session_state[editor_cache_key] = rows_with_status

    with st.container(border=True):
        st.caption("Publicação das alterações")
        st.metric("Linhas alteradas (tempo real)", len(changed_rows))
        motivo_bulk = st.text_input("Motivo da alteração", value="ajuste via UI paginada", key="catalog-page-motivo")
        save_clicked = st.button(
            "💾 Aplicar alterações da página no projeto",
            key="catalog-page-save",
            use_container_width=True,
            type="primary",
        )
    if save_clicked:
        changed_count = _save_catalogo_rows(changed_rows, payload_by_codigo, project_id, base_url, actor, motivo_bulk)
        if changed_count:
            st.success(f"{changed_count} CPU(s) atualizadas no projeto {project_id}.")
        else:
            st.info("Nenhuma alteração detectada na página atual.")


def _render_catalogo_tab1(project_id: str, base_url: str, actor: str) -> None:
    st.subheader("🧩 Estender Projeto com Item do Catálogo")

    with st.container(border=True):
        col_search, col_action = st.columns(2)
        with col_search:
            cpu_id = st.text_input("ID da CPU para importar/editar")
        with col_action:
            buscar_clicked = st.button("🔍 Buscar CPU do catálogo", type="secondary")

    if buscar_clicked:
        if cpu_id:
            try:
                cpu = api_call(
                    "GET",
                    f"/api/projects/{project_id}/catalog/cpus/{cpu_id}",
                    base_url=base_url,
                    actor=actor,
                )
                st.session_state["catalog-cpu-data"] = cpu
                st.success(f"CPU {cpu_id} carregada!")
            except Exception as exc:
                st.error(f"Não encontrada: {exc}")
                st.session_state["catalog-cpu-data"] = {}
        else:
            st.warning("Informe um ID de CPU.")

    cpu_data = st.session_state.get("catalog-cpu-data", {})
    if cpu_data:
        with st.container(border=True):
            st.caption(f"**Editando:** `{cpu_data.get('codigo', cpu_id)}`")

            # ADR-064 §D4: formulário tipado — sem json.loads(user_text)
            edited_fields = render_typed_form(
                cpu_data,
                CPU_EDITABLE_FIELDS,
                CPU_READONLY_FIELDS,
                key=f"cpu-edit-{cpu_id}",
            )

            motivo = st.text_input("Motivo da edição", key="cpu-edit-motivo")
            save_adv_clicked = st.button("💾 Salvar/Estender CPU", type="primary")

            # ADR-064 §D5: inspecionar JSON bruto (read-only)
            with st.expander("🔍 Inspecionar JSON completo (read-only)", expanded=False):
                st.json(cpu_data)
        if save_adv_clicked:
            if cpu_id:
                cpu_obj = {**cpu_data, **edited_fields}
                try:
                    api_call(
                        "POST",
                        f"/api/projects/{project_id}/catalog/cpus/{cpu_id}",
                        base_url=base_url,
                        payload=cpu_obj,
                        actor=actor,
                        params={"motivo": motivo},
                    )
                    st.success(f"✨ CPU {cpu_id} salva/estendida!")
                    st.session_state["catalog-cpu-data"] = {}
                except Exception as exc:
                    st.error(f"Falha ao salvar: {exc}")
            else:
                st.warning("Informe o ID da CPU antes de salvar.")
