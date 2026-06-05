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

from ._projetos_eap_helpers import (
    _render_eap_editor,
)
from .dashboard_page import render_dashboard_page_template

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _lc_process_ctx(ctx: dict, out: dict) -> None:
    cid = str(ctx.get("id") or "")
    if not cid:
        return
    versions = ctx.get("versions") or []
    current_v = ctx.get("current_version", "v1")
    current = next((v for v in versions if v.get("version") == current_v), ctx)
    out[cid] = {
        "perfil_id": str(current.get("perfil_id") or ctx.get("perfil_id") or "-"),
        "catalogo_id": str(current.get("catalogo_id") or ctx.get("catalogo_id") or "-"),
    }


def _load_contextos() -> dict[str, dict]:
    try:
        resp = api_call("GET", "/api/contextos", base_url=DEFAULT_BASE_URL, actor=DEFAULT_ACTOR)
        out = {}
        for ctx in resp.get("items") or []:
            _lc_process_ctx(ctx, out)
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
    """Render a single clickable project card + delete action."""
    pid = p.get("project_id", "")
    nome = p.get("nome") or pid[:8]
    tipo = (p.get("tipo_projeto") or "hot_project").lower()
    status_eap = p.get("status_eap", "ATIVO")
    versoes = p.get("versions") or []
    ctx = p.get("contexto_id", "-")

    col_card, col_delete = st.columns([10, 1])
    card_label = (
        f"{_badge(tipo)} {nome}\n"
        f"{pid[:12]}... | contexto: {ctx} | {_status_eap_color(status_eap)} {status_eap} | {len(versoes)} versão(ões)"
    )
    if col_card.button(card_label, key=f"open-proj-card-{pid}", use_container_width=True, type="secondary"):
        StateManager.set_project(p)
        st.rerun()

    if col_delete.button("🗑️", key=f"delete-proj-btn-{pid}", type="secondary", use_container_width=True):
        st.session_state["proj-delete-confirm"] = pid

    if st.session_state.get("proj-delete-confirm") == pid:
        st.warning(f"Excluir projeto '{nome}'? Esta ação remove todas as versões e artefatos.")
        c_yes, c_no = st.columns([1, 1])
        if c_yes.button("Confirmar exclusão", key=f"delete-proj-confirm-{pid}", type="primary"):
            try:
                api_call("DELETE", f"/api/projects/{pid}", base_url=DEFAULT_BASE_URL, actor=DEFAULT_ACTOR)
                if (StateManager.get().selected_project or {}).get("project_id") == pid:
                    StateManager.set_project(None)
                st.session_state.pop("proj-delete-confirm", None)
                st.success("Projeto excluído com sucesso.")
                st.rerun()
            except Exception as exc:
                st.error(f"Erro ao excluir projeto: {exc}")
        if c_no.button("Cancelar", key=f"delete-proj-cancel-{pid}", type="secondary"):
            st.session_state.pop("proj-delete-confirm", None)
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

    tab_dashboard, tab_lista, tab_novo = st.tabs(["📊 Dashboard", "📋 Meus Projetos", "✚ Novo Projeto"])

    with tab_dashboard:
        render_dashboard_page_template(compact=True)

    with tab_lista:
        _render_meus_projetos()

    with tab_novo:
        _render_novo_projeto()
