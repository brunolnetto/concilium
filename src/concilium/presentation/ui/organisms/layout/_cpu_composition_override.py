"""Camada de apresentação — layout Streamlit (parte extraída de layout.py)."""

from __future__ import annotations

import streamlit as st

from ...infra.api import api_call
from ._cpu_productivity_override import _catalog_cpus_by_codigo, _process_comp_row, _resolve_cpu_ids_with_fallback


def _cpu_insumo_info(insumo_id: str, insumos_cat: dict) -> tuple[str, float]:
    """Returns (descricao, preco_unitario) for an insumo ID."""
    i = insumos_cat.get(str(insumo_id), {})
    return (i.get("descricao") or insumo_id, float(i.get("preco_unitario") or 0))


def _insumos_dict_from_list(items: list) -> dict:
    """Builds codigo->insumo dict from a list of insumo dicts."""
    return {str(i.get("codigo") or i.get("id") or ""): i for i in items if isinstance(i, dict)}


def _fetch_insumos_from_catalog_api(project_id: str, base_url: str, actor: str) -> list:
    """Fetches insumos from the catalog API. Returns list or [] on failure."""
    try:
        _proj_meta = api_call("GET", f"/api/projects/{project_id}", base_url=base_url, actor=actor)
        _ctx_id = _proj_meta.get("contexto_id", "")
        _ctx = api_call("GET", f"/api/contextos/{_ctx_id}/versions", base_url=base_url, actor=actor)
        _current_v = _ctx.get("versions", [{}])[-1] if _ctx.get("versions") else {}
        _cat_id = _current_v.get("catalogo_id") or _ctx_id
        _ins_resp = api_call(
            "GET", f"/api/catalogs/{_cat_id}/insumos", params={"limit": 500}, base_url=base_url, actor=actor
        )
        return _ins_resp.get("items") or []
    except Exception:
        return []


def _load_cpu_insumos_catalog(reference: dict, base_url: str, project_id: str, actor: str) -> dict:
    """Loads insumos catalog dict from snapshot or API fallback."""
    raw = (reference.get("catalog") or {}).get("insumos") or []
    insumos_cat = _insumos_dict_from_list(raw)
    if not insumos_cat:
        insumos_cat = _insumos_dict_from_list(_fetch_insumos_from_catalog_api(project_id, base_url, actor))
    return insumos_cat


def _resolve_catalog_id_for_project(project_id: str, base_url: str, actor: str) -> str:
    """Resolve catalog_id currently associated to the project's context."""
    try:
        project_meta = api_call("GET", f"/api/projects/{project_id}", base_url=base_url, actor=actor)
        contexto_id = str(project_meta.get("contexto_id") or "").strip()
        if not contexto_id:
            return ""
        ctx = api_call("GET", f"/api/contextos/{contexto_id}/versions", base_url=base_url, actor=actor)
        versions = ctx.get("versions") or []
        if isinstance(versions, list) and versions:
            return str((versions[-1] or {}).get("catalogo_id") or contexto_id)
        return contexto_id
    except Exception:
        return ""


def _fetch_cpu_from_master_catalog(cpu_id: str, catalog_id: str, base_url: str, actor: str) -> dict:
    """Fetch CPU from master catalog API. Returns {} on failure."""
    if not catalog_id:
        return {}
    try:
        payload = api_call(
            method="GET",
            path=f"/api/catalogs/{catalog_id}/cpus/{cpu_id}",
            base_url=base_url,
            actor=actor,
        )
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _cpu_equipe_parts(cpu: dict) -> tuple[list, list, list]:
    """Extracts (funcoes, equipamentos, composicao_itens) from a CPU dict."""
    equipe_block = cpu.get("equipe")
    if not isinstance(equipe_block, dict):
        equipe_block = (
            cpu.get("composicao_padrao_equipe") if isinstance(cpu.get("composicao_padrao_equipe"), dict) else {}
        )
    funcoes = list((equipe_block or {}).get("funcoes") or [])
    equipamentos = list((equipe_block or {}).get("equipamentos") or [])
    composicao_itens = list(cpu.get("composicao_itens") or cpu.get("composicao_completa") or [])
    return funcoes, equipamentos, composicao_itens


def _build_cpu_comp_rows(cpu: dict, insumos_cat: dict) -> list[dict]:
    """Builds the composition rows list for a CPU."""
    funcoes, equipamentos, composicao_itens = _cpu_equipe_parts(cpu)
    rows: list[dict] = []
    for f in funcoes:
        fid = f.get("funcao_id", "")
        desc, preco = _cpu_insumo_info(fid, insumos_cat)
        rows.append(
            {
                "remover": False,
                "tipo": "MÃO_OBRA",
                "id": fid,
                "descricao": desc,
                "quantidade": float(f.get("num_pessoas") or 0),
                "custo_unit (R$/mês)": preco,
                "custo_total (R$/mês)": round(preco * float(f.get("num_pessoas") or 0), 2),
            }
        )
    for e in equipamentos:
        eid = e.get("equip_id", "")
        desc, preco = _cpu_insumo_info(eid, insumos_cat)
        rows.append(
            {
                "remover": False,
                "tipo": "EQUIPAMENTO",
                "id": eid,
                "descricao": desc,
                "quantidade": float(e.get("num_unidades") or 0),
                "custo_unit (R$/mês)": preco,
                "custo_total (R$/mês)": round(preco * float(e.get("num_unidades") or 0), 2),
            }
        )
    for item in composicao_itens:
        iid = item.get("insumo_id", "")
        desc, preco = _cpu_insumo_info(iid, insumos_cat)
        coef = float(item.get("coeficiente") or 0)
        rows.append(
            {
                "remover": False,
                "tipo": item.get("categoria_custo", "MATERIAL"),
                "id": iid,
                "descricao": desc,
                "quantidade": coef,
                "custo_unit (R$/mês)": preco,
                "custo_total (R$/mês)": round(preco * coef, 2),
            }
        )
    return rows


def _save_cpu_comp(
    edited_rows: list[dict],
    cpu: dict,
    project_id: str,
    cpu_id: str,
    base_url: str,
    actor: str,
) -> None:
    """Handles saving the edited CPU composition."""
    funcoes, equipamentos, composicao_itens = _cpu_equipe_parts(cpu)
    orig_funcoes = {f.get("funcao_id"): f for f in funcoes}
    orig_equips = {e.get("equip_id"): e for e in equipamentos}
    orig_itens = {i.get("insumo_id"): i for i in composicao_itens}
    new_funcoes: list[dict] = []
    new_equipamentos: list[dict] = []
    new_composicao: list[dict] = []
    for row in edited_rows:
        if row.get("remover"):
            continue
        _process_comp_row(row, orig_funcoes, orig_equips, orig_itens, new_funcoes, new_equipamentos, new_composicao)
    payload = {"equipe": {"funcoes": new_funcoes, "equipamentos": new_equipamentos}, "composicao_itens": new_composicao}
    try:
        api_call(
            method="POST",
            path=f"/api/projects/{project_id}/catalog/cpus/{cpu_id}",
            base_url=base_url,
            payload=payload,
            actor=actor,
        )
        st.success(f"Composição salva para {cpu_id}.")
    except Exception as exc:
        st.error(f"Erro ao salvar {cpu_id}: {exc}")


def _cpu_comp_badge(funcoes: list, equipamentos: list, composicao_itens: list, comp_cats: list) -> str:
    """Monta o badge de resumo (MO/EQ/INS/categorias) exibido no título do expander de uma CPU."""
    parts: list[str] = []
    if funcoes:
        parts.append(f"MO:{len(funcoes)}")
    if equipamentos:
        parts.append(f"EQ:{len(equipamentos)}")
    if composicao_itens:
        parts.append(f"INS:{len(composicao_itens)}")
    if comp_cats:
        parts.extend(comp_cats)
    return " · ".join(parts) if parts else "sem composição"


def _render_cpu_comp_expander(
    cpu_id: str,
    cpu: dict,
    insumos_cat: dict,
    project_id: str,
    base_url: str,
    actor: str,
) -> None:
    """Renders the composition editor expander for one CPU."""
    descricao = cpu.get("descricao", "")
    funcoes, equipamentos, composicao_itens = _cpu_equipe_parts(cpu)
    _comp_cats = sorted({it.get("categoria_custo", "?") for it in composicao_itens})
    _badge = _cpu_comp_badge(funcoes, equipamentos, composicao_itens, _comp_cats)
    with st.expander(f"{cpu_id} — {descricao[:60]}  `{_badge}`", expanded=False):
        rows = _build_cpu_comp_rows(cpu, insumos_cat)
        if not rows:
            st.caption(
                "Esta CPU não possui composição de insumos registrada no catálogo. "
                "Para adicionar, edite o arquivo `config/catalogos/{id}/cpus/{cpu_id}.json` "
                "ou use a página **Catálogo** → aba CPUs → Editar composição."
            )
            return
        edited = st.data_editor(
            rows,
            width="stretch",
            hide_index=True,
            column_config={
                "remover": st.column_config.CheckboxColumn("🗑️", width="small"),
                "tipo": st.column_config.TextColumn("Categoria", disabled=True, width="medium"),
                "id": st.column_config.TextColumn("ID", disabled=True, width="medium"),
                "descricao": st.column_config.TextColumn("Descrição", disabled=True, width="large"),
                "quantidade": st.column_config.NumberColumn("✏️ Qtd", format="%.2f", step=0.5, min_value=0.0),
                "custo_unit (R$/mês)": st.column_config.NumberColumn("Custo Unit. (R$)", disabled=True, format="%.2f"),
                "custo_total (R$/mês)": st.column_config.NumberColumn(
                    "Custo Total (R$/mês)", disabled=True, format="%.2f"
                ),
            },
            disabled=["tipo", "id", "descricao", "custo_unit (R$/mês)", "custo_total (R$/mês)"],
            key=f"cpu-comp-editor-{project_id}-{cpu_id}",
        )
        if st.button(f"Salvar composição — {cpu_id}", key=f"save-comp-{project_id}-{cpu_id}", type="primary"):
            edited_rows = (
                edited
                if isinstance(edited, list)
                else (edited.to_dict("records") if hasattr(edited, "to_dict") else [])
            )  # noqa: E501
            _save_cpu_comp(edited_rows, cpu, project_id, cpu_id, base_url, actor)


def _hydrate_cpu_from_project_endpoint(cpu_id: str, cpu: dict, project_id: str, base_url: str, actor: str) -> dict:
    """Reidrata a CPU via endpoint resolvido do projeto quando o snapshot local não tem equipe/equipamentos."""
    try:
        resolved = (
            api_call(
                method="GET",
                path=f"/api/projects/{project_id}/catalog/cpus/{cpu_id}",
                base_url=base_url,
                actor=actor,
            )
            or {}
        )
        if isinstance(resolved, dict):
            cpu = {**cpu, **resolved} if cpu else resolved
    except Exception:
        if not cpu:
            cpu = {"codigo": cpu_id}
    return cpu


def _hydrate_cpu_from_master_catalog(
    cpu_id: str, cpu: dict, catalog_id: str, base_url: str, actor: str, master_cache: dict[str, dict]
) -> dict:
    """Reidrata a CPU a partir do catálogo mestre do contexto (com cache por cpu_id)."""
    if cpu_id not in master_cache:
        master_cache[cpu_id] = _fetch_cpu_from_master_catalog(cpu_id, catalog_id, base_url, actor)
    master_cpu = master_cache.get(cpu_id) or {}
    if master_cpu:
        cpu = {**cpu, **master_cpu}
    return cpu


def _resolve_hydrated_cpu(
    cpu_id: str, cpu: dict, catalog_id: str, project_id: str, base_url: str, actor: str, master_cache: dict[str, dict]
) -> dict:
    """Garante que a CPU tenha equipe/equipamentos, reidratando via endpoint do projeto e catálogo mestre."""
    # Snapshot de referência pode trazer apenas INS (sem equipe/equipamentos).
    # Nesses casos, reidrata via endpoint resolvido do projeto.
    funcoes, equipamentos, _ = _cpu_equipe_parts(cpu)
    needs_hydration = (not cpu) or (not funcoes and not equipamentos)
    if needs_hydration:
        cpu = _hydrate_cpu_from_project_endpoint(cpu_id, cpu, project_id, base_url, actor)

    # Se ainda faltar equipe, consulta catálogo mestre do contexto explicitamente.
    funcoes, equipamentos, _ = _cpu_equipe_parts(cpu)
    if not funcoes and not equipamentos:
        cpu = _hydrate_cpu_from_master_catalog(cpu_id, cpu, catalog_id, base_url, actor, master_cache)
    return cpu


def render_cpu_composition_override(base_url: str, project_id: str, actor: str) -> None:
    """Override da composição das CPUs — mão de obra, equipamentos e materiais."""
    st.caption(
        "Edite as quantidades de mão de obra, equipamentos e materiais por CPU. "
        "CPUs deduplicadas — alterações aqui aplicam-se a **todas** as atividades que usam essa CPU. IDs são somente leitura."  # noqa: E501
    )
    try:
        reference = api_call(
            method="GET", path=f"/api/projects/{project_id}/benchmark-reference", base_url=base_url, actor=actor
        )
    except Exception:
        reference = {}
    cpu_ids = _resolve_cpu_ids_with_fallback(reference, base_url, project_id, actor)
    if not cpu_ids:
        st.info("Nenhuma CPU encontrada. Execute o pipeline ou adicione itens à EAP.")
        return
    insumos_cat = _load_cpu_insumos_catalog(reference, base_url, project_id, actor)
    catalog_cpus = _catalog_cpus_by_codigo(reference.get("catalog") or {})
    catalog_id = _resolve_catalog_id_for_project(project_id, base_url, actor)
    master_cache: dict[str, dict] = {}
    for cpu_id in sorted(cpu_ids):
        cpu: dict = dict(catalog_cpus.get(cpu_id) or {})
        cpu = _resolve_hydrated_cpu(cpu_id, cpu, catalog_id, project_id, base_url, actor, master_cache)
        if not cpu:
            st.warning(f"CPU '{cpu_id}' não encontrada.")
            continue
        _render_cpu_comp_expander(cpu_id, cpu, insumos_cat, project_id, base_url, actor)


