"""EAP/cycle-detection helpers for projetos_page (extracted)."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

try:
    from ..config import DEFAULT_ACTOR, DEFAULT_BASE_URL
    from ..infra.api import api_call
except ImportError:
    src_root = Path(__file__).resolve().parents[4]
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))
    from concilium.presentation.ui.config import DEFAULT_ACTOR, DEFAULT_BASE_URL
    from concilium.presentation.ui.infra.api import api_call


def _load_catalog_cpus(project_id: str) -> list[dict]:
    """Load available CPUs from project catalog (for search helper)."""
    try:
        resp = api_call(
            "GET", f"/api/projects/{project_id}/catalog/cpus", base_url=DEFAULT_BASE_URL, actor=DEFAULT_ACTOR
        )
        return resp if isinstance(resp, list) else resp.get("items", [])
    except Exception:
        return []


def _dcim_build_in_degree(items: list, ids: set) -> dict:
    result = {}
    for it in items:
        nid = it.get("item_id", "")
        count = 0
        for p in it.get("predecessores", []):
            if p in ids:
                count += 1
        result[nid] = count
    return result


def _detect_cycle_in_memory(items: list[dict]) -> bool:
    """Return True if the current predecessores selections form a cycle (Kahn's)."""
    ids = {it.get("item_id", "") for it in items}
    in_degree = _dcim_build_in_degree(items, ids)
    queue = [nid for nid, deg in in_degree.items() if deg == 0]
    visited = 0
    while queue:
        node = queue.pop(0)
        visited += 1
        for it in items:
            if node in it.get("predecessores", []):
                nid = it.get("item_id", "")
                in_degree[nid] -= 1
                if in_degree[nid] == 0:
                    queue.append(nid)
    return visited != len(items)


def _search_cpus_with_fallback(project_id: str, q: str) -> list:
    try:
        results = api_call(
            "GET",
            "/api/catalog/search",
            params={"q": q, "limit": 10},
            base_url=DEFAULT_BASE_URL,
            actor=DEFAULT_ACTOR,
        )
        return results.get("items", []) if isinstance(results, dict) else results
    except Exception:
        all_cpus = _load_catalog_cpus(project_id)
        q_lower = q.lower()
        return [
            c
            for c in all_cpus
            if q_lower in (c.get("codigo") or "").lower() or q_lower in (c.get("descricao") or "").lower()
        ][:10]


def _render_eap_cpu_search(project_id: str, key: str) -> None:
    with st.expander("🔍 Buscar CPU no catálogo", expanded=False):
        cpu_search_q = st.text_input(
            "Código ou descrição",
            key=f"{key}-cpu-search-q",
            placeholder="Ex: ESCO, COMPACT, PAV-BASE…",
        )
        if cpu_search_q:
            cpus_found = _search_cpus_with_fallback(project_id, cpu_search_q)
            if cpus_found:
                for cpu in cpus_found:
                    codigo = cpu.get("codigo", "")
                    desc = cpu.get("descricao", "")[:60]
                    un = cpu.get("unidade", "")
                    st.code(f"{codigo}  |  {desc}  |  {un}", language=None)
                st.caption("Copie o código e cole no campo CPU da linha desejada.")
            else:
                st.info("Nenhuma CPU encontrada para este termo.")


def _render_eap_row(key: str, i: int, item: dict, all_ids: list) -> dict:
    row = st.columns([1, 3, 2, 1, 2, 3])
    item_id = row[0].text_input(
        "", value=item.get("item_id", f"IT-{i + 1:03d}"), key=f"{key}-id-{i}", label_visibility="collapsed"
    )
    descricao = row[1].text_input(
        "", value=item.get("descricao", ""), key=f"{key}-desc-{i}", label_visibility="collapsed"
    )
    cpu_id = row[2].text_input(
        "", value=item.get("cpu_id", ""), key=f"{key}-cpu-{i}", label_visibility="collapsed", placeholder="código CPU"
    )
    qtd = row[3].number_input(
        "",
        value=float(item.get("quantitativo", 1.0)),
        min_value=0.001,
        key=f"{key}-qtd-{i}",
        label_visibility="collapsed",
    )
    unidade = row[4].text_input("", value=item.get("unidade", "m³"), key=f"{key}-un-{i}", label_visibility="collapsed")
    pred_options = [x for x in all_ids if x and x != item.get("item_id", "")]
    pred_default = [p for p in item.get("predecessores", []) if p in pred_options]
    predecessores = row[5].multiselect(
        "", options=pred_options, default=pred_default, key=f"{key}-pred-{i}", label_visibility="collapsed"
    )
    return {
        "item_id": item_id,
        "ordem": i + 1,
        "descricao": descricao,
        "cpu_id": cpu_id.strip(),
        "quantitativo": qtd,
        "unidade": unidade,
        "predecessores": predecessores,
    }


def _render_eap_items_table(key: str, current: list) -> list:
    all_ids = [it.get("item_id", "") for it in current if it.get("item_id")]
    cols = st.columns([1, 3, 2, 1, 2, 3])
    for col, label in zip(cols, ["ID", "Descrição", "CPU", "Qtd", "Unidade", "Predecessores"], strict=True):
        col.caption(label)
    updated = []
    for i, item in enumerate(current):
        updated.append(_render_eap_row(key, i, item, all_ids))
    return updated


def _render_eap_feedback(updated: list) -> bool:
    has_cycle = _detect_cycle_in_memory(updated)
    items_sem_cpu = [it["item_id"] for it in updated if not it.get("cpu_id")]
    eap_pronta = len(updated) > 0 and not items_sem_cpu and not has_cycle
    if has_cycle:
        st.error("⛔ **Ciclo detectado** na predecessão. Corrija antes de salvar.")
    elif items_sem_cpu:
        st.warning(
            f"⚠️ {len(items_sem_cpu)} item(s) sem CPU definida: "
            + ", ".join(f"`{x}`" for x in items_sem_cpu[:5])
            + (f" e mais {len(items_sem_cpu) - 5}…" if len(items_sem_cpu) > 5 else "")
            + " — status ficará como **RASCUNHO** ao salvar."
        )
    elif eap_pronta:
        st.success(f"✅ EAP completa — {len(updated)} item(s) com CPU e sem ciclos. Pronto para salvar.")
    return has_cycle


def _render_eap_action_buttons(key: str, project_id: str, current: list, has_cycle: bool) -> None:
    btn_add, btn_remove, btn_save = st.columns(3)
    if btn_add.button("➕ Adicionar item", key=f"{key}-add"):
        st.session_state[key].append(
            {
                "item_id": f"IT-{len(current) + 1:03d}",
                "ordem": len(current) + 1,
                "descricao": "",
                "cpu_id": "",
                "quantitativo": 1.0,
                "unidade": "m³",
                "predecessores": [],
            }
        )
        st.rerun()
    if btn_remove.button("➖ Remover último", key=f"{key}-rm", disabled=len(current) == 0):
        if st.session_state[key]:
            st.session_state[key].pop()
            st.rerun()
    save_label = "💾 Salvar EAP" if not has_cycle else "💾 Salvar EAP (ciclo — corrija primeiro)"
    if btn_save.button(save_label, key=f"{key}-save", type="primary", disabled=has_cycle):
        try:
            result = api_call(
                "PUT",
                f"/api/projects/{project_id}/eap",
                payload=st.session_state[key],
                base_url=DEFAULT_BASE_URL,
                actor=DEFAULT_ACTOR,
            )
            new_status = result.get("status_eap", "RASCUNHO")
            if new_status == "RASCUNHO_PRONTO":
                st.success(f"EAP salva. Status: **{new_status}** — projeto pronto para executar!")
            else:
                st.warning(f"EAP salva. Status: **{new_status}** — defina cpu_id em todos os itens para ficar pronto.")
            st.session_state.pop(key, None)
            st.rerun()
        except Exception as exc:
            st.error(f"Erro ao salvar: {exc}")


def _render_eap_editor(project_id: str) -> None:
    """Editor tabular de EAP para projetos do tipo 'project' (ADR-063 §F5)."""
    try:
        eap_resp = api_call("GET", f"/api/projects/{project_id}/eap", base_url=DEFAULT_BASE_URL, actor=DEFAULT_ACTOR)
        items: list[dict] = eap_resp.get("items", [])
        status_eap = eap_resp.get("status_eap", "RASCUNHO")
    except Exception as exc:
        st.error(f"Erro ao carregar EAP: {exc}")
        return

    st.caption(f"Status: **{status_eap}** | {len(items)} item(s)")

    key = f"eap_edit_{project_id}"
    if key not in st.session_state:
        st.session_state[key] = [dict(it) for it in items]

    current: list[dict] = st.session_state[key]
    _render_eap_cpu_search(project_id, key)
    updated = _render_eap_items_table(key, current)
    st.session_state[key] = updated
    has_cycle = _render_eap_feedback(updated)
    _render_eap_action_buttons(key, project_id, current, has_cycle)
