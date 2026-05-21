"""ADR-063: Página de gerenciamento e criação de projetos com tabs.

Tab 1 — Meus Projetos: lista com badge de tipo, status EAP, acesso rápido.
Tab 2 — Novo Projeto: seleção de tipo + formulário específico.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

try:
    from ..config import DEFAULT_ACTOR, DEFAULT_BASE_URL
    from ..infra.api import api_call
    from ..state import StateManager
except ImportError:
    src_root = Path(__file__).resolve().parents[4]
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))
    from concilium.presentation.ui.config import DEFAULT_ACTOR, DEFAULT_BASE_URL
    from concilium.presentation.ui.infra.api import api_call
    from concilium.presentation.ui.state import StateManager


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _load_contextos() -> dict[str, dict]:
    try:
        resp = api_call("GET", "/api/contextos", base_url=DEFAULT_BASE_URL, actor=DEFAULT_ACTOR)
        out = {}
        for ctx in resp.get("items") or []:
            cid = str(ctx.get("id") or "")
            if cid:
                versions = ctx.get("versions") or []
                current_v = ctx.get("current_version", "v1")
                current = next((v for v in versions if v.get("version") == current_v), ctx)
                out[cid] = {
                    "perfil_id": str(current.get("perfil_id") or ctx.get("perfil_id") or "-"),
                    "catalogo_id": str(current.get("catalogo_id") or ctx.get("catalogo_id") or "-"),
                }
        return out
    except Exception:
        return {}


def _load_benchmarks() -> list[str]:
    try:
        resp = api_call("GET", "/api/benchmarks", base_url=DEFAULT_BASE_URL, actor=DEFAULT_ACTOR)
        return resp.get("items", [])
    except Exception:
        return []


def _badge(tipo: str) -> str:
    if (tipo or "").lower() == "hot_project":
        return "🔥 HOT"
    return "📐 PROJ"


def _status_eap_color(status: str) -> str:
    return {"RASCUNHO": "🟡", "RASCUNHO_PRONTO": "🟢", "ATIVO": "✅"}.get(status, "⬜")


# ─────────────────────────────────────────────────────────────────────────────
# Tab: Meus Projetos
# ─────────────────────────────────────────────────────────────────────────────


def _render_page_nav(page: int, n_pages: int, page_key: str, total: int, label: str = "") -> None:
    """Centred page info, always 3 columns. Buttons only appear when applicable."""
    suffix = f" {label}" if label else ""
    info_html = (
        f"<div style='text-align:center;padding:0.35rem 0;font-size:0.85rem;'>"
        f"<strong>{total}</strong>{suffix} &nbsp;·&nbsp; página {page + 1}/{n_pages}"
        f"</div>"
    )
    col_prev, col_info, col_next = st.columns([1, 5, 1])
    with col_prev:
        if page > 0 and st.button("←", key=f"{page_key}-prev", type="secondary", use_container_width=True):
            st.session_state[page_key] = page - 1
            st.rerun()
    col_info.markdown(info_html, unsafe_allow_html=True)
    with col_next:
        if page < n_pages - 1 and st.button("→", key=f"{page_key}-next", type="secondary", use_container_width=True):
            st.session_state[page_key] = page + 1
            st.rerun()


def _pp_matches_tipo_filter(p: dict, tipo_filter: str) -> bool:
    """Return False when a project's type doesn't match the active filter."""
    tipo = (p.get("tipo_projeto") or "hot_project").lower()
    if tipo_filter == "🔥 Hot Project" and tipo != "hot_project":
        return False
    if tipo_filter == "📐 Projeto" and tipo != "project":
        return False
    return True


def _pp_filter_projects(projects: list, tipo_filter: str, search: str) -> list:
    """Filter project list by tipo_filter and search text."""
    filtered = []
    for p in projects:
        if not _pp_matches_tipo_filter(p, tipo_filter):
            continue
        if search:
            text = " ".join([str(p.get("nome") or ""), str(p.get("project_id") or "")]).lower()
            if search not in text:
                continue
        filtered.append(p)
    return filtered


def _pp_render_project_card(p: dict) -> None:
    """Render a single project row with badge, info, and open button."""
    pid = p.get("project_id", "")
    nome = p.get("nome") or pid[:8]
    tipo = (p.get("tipo_projeto") or "hot_project").lower()
    status_eap = p.get("status_eap", "ATIVO")
    versoes = p.get("versions") or []
    ctx = p.get("contexto_id", "-")

    col_badge, col_info, col_btn = st.columns([1, 5, 2])
    col_badge.markdown(f"### {_badge(tipo)}")
    col_info.markdown(
        f"**{nome}**  \n"
        f"`{pid[:12]}…`  |  contexto: `{ctx}`  |  "
        f"{_status_eap_color(status_eap)} `{status_eap}`  |  "
        f"{len(versoes)} versão(ões)"
    )
    if col_btn.button("Abrir", key=f"open-proj-{pid}", use_container_width=True):
        StateManager.set_project(p)
        st.rerun()

    if tipo == "project" and status_eap in ("RASCUNHO", "RASCUNHO_PRONTO"):
        with st.expander(f"✏️ Editar EAP — {nome}", expanded=False):
            _render_eap_editor(pid)

    st.divider()


def _render_meus_projetos() -> None:
    try:
        projects = api_call("GET", "/api/projects", base_url=DEFAULT_BASE_URL, actor=DEFAULT_ACTOR).get("items", [])
    except Exception as exc:
        st.error(f"Erro ao listar projetos: {exc}")
        return

    if not projects:
        st.info("Nenhum projeto cadastrado. Use a aba **Novo Projeto** para começar.")
        return

    search = st.text_input("Buscar", placeholder="Nome ou ID…", key="proj-page-search").strip().lower()
    tipo_filter = st.radio(
        "Tipo",
        options=["Todos", "🔥 Hot Project", "📐 Projeto"],
        horizontal=True,
        key="proj-page-tipo-filter",
    )

    filtered = _pp_filter_projects(projects, tipo_filter, search)

    _PAGE = 20
    total = len(filtered)
    n_pages = max(1, (total + _PAGE - 1) // _PAGE)
    page_key = "proj-list-page"
    if page_key not in st.session_state:
        st.session_state[page_key] = 0
    page = min(int(st.session_state[page_key]), n_pages - 1)
    st.session_state[page_key] = page
    start = page * _PAGE
    page_projects = filtered[start : start + _PAGE]

    _render_page_nav(page, n_pages, page_key, total, "projeto(s)")

    for p in page_projects:
        _pp_render_project_card(p)


# ─────────────────────────────────────────────────────────────────────────────
# EAP Editor (F5: ADR-063 §D5)
# ─────────────────────────────────────────────────────────────────────────────


def _load_catalog_cpus(project_id: str) -> list[dict]:
    """Load available CPUs from project catalog (for search helper)."""
    try:
        resp = api_call(
            "GET", f"/api/projects/{project_id}/catalog/cpus", base_url=DEFAULT_BASE_URL, actor=DEFAULT_ACTOR
        )
        return resp if isinstance(resp, list) else resp.get("items", [])
    except Exception:
        return []


def _detect_cycle_in_memory(items: list[dict]) -> bool:
    """Return True if the current predecessores selections form a cycle (Kahn's)."""
    ids = {it.get("item_id", "") for it in items}
    in_degree = {it.get("item_id", ""): len([p for p in it.get("predecessores", []) if p in ids]) for it in items}
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


# ─────────────────────────────────────────────────────────────────────────────
# Tab: Novo Projeto
# ─────────────────────────────────────────────────────────────────────────────


def _render_novo_projeto() -> None:
    st.subheader("Selecione o tipo de projeto")

    col_hot, col_proj = st.columns(2)
    with col_hot:
        st.markdown("""
        ### 🔥 Hot Project
        **A partir de um benchmark**

        - EAP pré-populada com quantidades e CPUs
        - Você calibra parâmetros (BDI, equipes, praticabilidade)
        - Pipeline roda imediatamente
        """)
        if st.button("Criar Hot Project", key="new-hot", use_container_width=True, type="primary"):
            st.session_state["new_proj_type"] = "hot_project"

    with col_proj:
        st.markdown("""
        ### 📐 Projeto
        **Composição gradual de EAP**

        - Você define itens, quantidades e CPUs
        - Predecessão explícita entre atividades
        - Pipeline roda após EAP estar completa
        """)
        if st.button("Criar Projeto", key="new-proj", type="primary", use_container_width=True):
            st.session_state["new_proj_type"] = "project"

    tipo = st.session_state.get("new_proj_type")
    if not tipo:
        return

    st.divider()
    if tipo == "hot_project":
        _render_form_hot_project()
    else:
        _render_form_project()


def _render_form_hot_project() -> None:
    st.subheader("🔥 Novo Hot Project")
    contextos = _load_contextos()
    benchmarks = _load_benchmarks()

    with st.form("form-hot-project"):
        nome = st.text_input("Nome do projeto", placeholder="Ex: Lote 3 — Terraplenagem BR-116")
        contexto_id = st.selectbox("Contexto", options=sorted(contextos.keys()) or ["mendeslobo"])
        benchmark_slug = st.selectbox(
            "Benchmark de referência",
            options=[""] + benchmarks,
            help="Define a EAP e as quantidades de partida",
        )
        tipo_obra = st.selectbox("Tipo de obra", ["terraplenagem", "pavimentacao", "saneamento", "estrutura"])
        col1, col2 = st.columns(2)
        localizacao = col1.text_input("Localização", value="Brasil")
        data_inicio = col1.text_input("Data início", value="2026-01-01")
        data_termino = col2.text_input("Data término", value="2026-12-31")
        submitted = st.form_submit_button("✅ Criar Hot Project", type="primary")

    if submitted:
        payload = {
            "nome": nome,
            "contexto_id": contexto_id,
            "benchmark_slug": benchmark_slug or None,
            "tipo_obra": tipo_obra,
            "localizacao": localizacao,
            "data_inicio": data_inicio,
            "data_termino": data_termino,
        }
        try:
            result = api_call("POST", "/api/projects", payload=payload, base_url=DEFAULT_BASE_URL, actor=DEFAULT_ACTOR)
            st.success(f"Projeto criado: `{result.get('project_id', '')}` — tipo: **hot_project**")
            st.session_state.pop("new_proj_type", None)
            st.rerun()
        except Exception as exc:
            st.error(f"Erro ao criar: {exc}")


def _render_form_project() -> None:
    st.subheader("📐 Novo Projeto (composição gradual)")
    contextos = _load_contextos()

    with st.form("form-project"):
        nome = st.text_input("Nome do projeto", placeholder="Ex: Contorno Viário — Trecho 1")
        contexto_id = st.selectbox("Contexto", options=sorted(contextos.keys()) or ["mendeslobo"])
        tipo_obra = st.selectbox("Tipo de obra", ["terraplenagem", "pavimentacao", "saneamento", "estrutura"])
        col1, col2 = st.columns(2)
        localizacao = col1.text_input("Localização", value="Brasil")
        data_inicio = col1.text_input("Data início", value="2026-01-01")
        data_termino = col2.text_input("Data término", value="2026-12-31")
        st.info(
            "O projeto será criado no status **RASCUNHO**. "
            "Defina a EAP (itens + CPUs + predecessão) antes de executar o pipeline.",
            icon="ℹ️",
        )
        submitted = st.form_submit_button("✅ Criar Projeto", type="primary")

    if submitted:
        payload = {
            "nome": nome,
            "contexto_id": contexto_id,
            "benchmark_slug": None,  # no benchmark → tipo = "project"
            "tipo_obra": tipo_obra,
            "localizacao": localizacao,
            "data_inicio": data_inicio,
            "data_termino": data_termino,
        }
        try:
            result = api_call("POST", "/api/projects", payload=payload, base_url=DEFAULT_BASE_URL, actor=DEFAULT_ACTOR)
            project_id = result.get("project_id", "")
            st.success(
                f"Projeto `{project_id}` criado no status **RASCUNHO**. "
                "Abra-o na aba **Meus Projetos** para definir a EAP."
            )
            st.session_state.pop("new_proj_type", None)
            st.rerun()
        except Exception as exc:
            st.error(f"Erro ao criar: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# Entrypoint público
# ─────────────────────────────────────────────────────────────────────────────


def render_projetos_page() -> None:
    """Página principal de projetos com tabs (ADR-063)."""
    st.header("Projetos")

    tab_lista, tab_novo = st.tabs(["📋 Meus Projetos", "✚ Novo Projeto"])

    with tab_lista:
        _render_meus_projetos()

    with tab_novo:
        _render_novo_projeto()
