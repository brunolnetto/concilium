"""Master catalog management page — browse CPUs, insumos, and search across catalogs."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

try:
    from ..atoms.form_contracts import CPU_EDITABLE_FIELDS, CPU_READONLY_FIELDS, render_typed_form
    from ..config import DEFAULT_ACTOR, DEFAULT_BASE_URL
    from ..infra.api import api_call
    from ..molecules.common import render_page_heading
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
    from concilium.presentation.ui.molecules.common import render_page_heading

_PAGE_SIZE = 30


def render_catalogo_master_page() -> None:
    render_page_heading(
        "Catálogo Mestre",
        "Consulte e gerencie CPUs, insumos e produções do catálogo corporativo.",
    )

    base_url = DEFAULT_BASE_URL
    actor = DEFAULT_ACTOR

    try:
        resp = api_call("GET", "/api/catalogs", base_url=base_url, actor=actor)
        catalogs = [c["id"] for c in (resp.get("items") or []) if c.get("id")]
    except Exception as exc:
        st.error(f"Não foi possível listar catálogos: {exc}")
        return

    if not catalogs:
        st.warning("Nenhum catálogo encontrado em `config/catalogos/`.")
        return

    col_sel, col_n_cpus, col_n_ins = st.columns([4, 1, 1])
    with col_sel:
        catalog_id = st.selectbox("Catálogo", options=catalogs, key="master-cat-id")
    try:
        stat = api_call("GET", f"/api/catalogs/{catalog_id}", base_url=base_url, actor=actor)
        col_n_cpus.metric("CPUs", stat.get("n_cpus", "—"))
        col_n_ins.metric("Insumos", stat.get("n_insumos", "—"))
    except Exception:
        pass

    st.divider()
    tab_cpus, tab_insumos = st.tabs(["🔧 CPUs", "🧱 Insumos"])

    with tab_cpus:
        _render_cpu_browser(base_url, actor, catalog_id)

    with tab_insumos:
        _render_insumo_browser(base_url, actor, catalog_id)


# ─── CPUs ─────────────────────────────────────────────────────────────────────


def _cmb_comp_badge(cpu: dict) -> str:
    """Build a short composition badge string (e.g. 'MO + EQ + MAT')."""
    parts: list[str] = []
    equipe = cpu.get("equipe") or {}
    if equipe.get("funcoes"):
        parts.append("MO")
    if equipe.get("equipamentos"):
        parts.append("EQ")
    abbr = {"MAO_OBRA": "MO", "EQUIPAMENTO": "EQ", "MATERIAL": "MAT", "DIESEL": "DIESEL", "SERVICO": "SERV"}
    for it in cpu.get("composicao_itens") or []:
        if isinstance(it, dict):
            mapped = abbr.get(it.get("categoria_custo", ""), "")
            if mapped and mapped not in parts:
                parts.append(mapped)
    return " + ".join(parts) if parts else "(sem composição)"


def _cmb_get_categorias(all_cpus: list) -> list:
    """Return sorted list of distinct non-empty categoria values."""
    return sorted({str(c.get("categoria") or "") for c in all_cpus if c.get("categoria")})


def _cmb_filter_cpus(all_cpus: list, q: str, sel_cats: list) -> list:
    """Filter CPUs by free-text q and selected categories."""
    filtered = all_cpus
    if q:
        q_lower = q.lower()
        filtered = [
            c
            for c in filtered
            if q_lower in (c.get("codigo") or "").lower() or q_lower in (c.get("descricao") or "").lower()
        ]
    if sel_cats:
        filtered = [c for c in filtered if c.get("categoria") in sel_cats]
    return filtered


def _cmb_build_cpu_rows(page_cpus: list) -> list:
    """Build the list-of-dicts used in the CPU dataframe."""
    return [
        {
            "Código": c.get("codigo", ""),
            "Descrição": (c.get("descricao") or "")[:55],
            "Unidade": c.get("unidade", ""),
            "Categoria": c.get("categoria", ""),
            "Prod. Hor.": c.get("producao_horaria") or "—",
            "Composição": _cmb_comp_badge(c),
        }
        for c in page_cpus
    ]


def _cmb_render_cpu_nav(page: int, n_pages: int, page_key: str, total: int, catalog_id: str) -> None:
    """Render centred pagination nav for the CPU browser."""
    info_html = (
        "<div style='text-align:center;padding:0.35rem 0;font-size:0.85rem;'>"
        f"<strong>{total}</strong> CPUs &nbsp;·&nbsp; página {page + 1}/{n_pages}"
        "</div>"
    )
    col_prev, col_info, col_next = st.columns([1, 5, 1])
    with col_prev:
        if page > 0 and st.button("←", key=f"master-cpu-prev-{catalog_id}", type="secondary", use_container_width=True):
            st.session_state[page_key] = page - 1
            st.rerun()
    col_info.markdown(info_html, unsafe_allow_html=True)
    with col_next:
        if page < n_pages - 1 and st.button(
            "→", key=f"master-cpu-next-{catalog_id}", type="secondary", use_container_width=True
        ):
            st.session_state[page_key] = page + 1
            st.rerun()


def _cmb_handle_cpu_selection(sel: list, page_cpus: list, base_url: str, actor: str, catalog_id: str) -> None:
    """Handle CPU row selection: show detail, edit button, composition dialog."""
    if sel:
        cpu = page_cpus[sel[0]]
        st.divider()
        _render_cpu_detail(base_url, actor, catalog_id, cpu)
        if st.button("✏️ Editar composição", key=f"open-comp-dialog-{cpu.get('codigo')}", type="secondary"):
            st.session_state[f"comp-dialog-cpu-{catalog_id}"] = cpu
        if st.session_state.get(f"comp-dialog-cpu-{catalog_id}", {}).get("codigo") == cpu.get("codigo"):
            _render_composition_dialog(base_url, actor, catalog_id, cpu)


def _render_cpu_browser(base_url: str, actor: str, catalog_id: str) -> None:
    cache_key = f"master-cpus-all-{catalog_id}"
    if cache_key not in st.session_state:
        try:
            resp = api_call(
                "GET", f"/api/catalogs/{catalog_id}/cpus", params={"limit": 500}, base_url=base_url, actor=actor
            )
            st.session_state[cache_key] = resp.get("items", [])
        except Exception as exc:
            st.error(f"Erro ao carregar CPUs: {exc}")
            return

    all_cpus: list[dict] = st.session_state[cache_key]

    col_q, col_cat, col_ref = st.columns([3, 2, 1])
    q = col_q.text_input(
        "Buscar", placeholder="Código ou descrição…", key=f"master-cpu-q-{catalog_id}", label_visibility="collapsed"
    )
    categorias = _cmb_get_categorias(all_cpus)
    sel_cats = col_cat.multiselect(
        "Categoria",
        options=categorias,
        key=f"master-cpu-cats-{catalog_id}",
        label_visibility="collapsed",
        placeholder="Todas as categorias",
    )
    if col_ref.button("↺ Recarregar", key=f"master-cpu-reload-{catalog_id}"):
        st.session_state.pop(cache_key, None)
        st.rerun()

    filtered = _cmb_filter_cpus(all_cpus, q, sel_cats)
    total = len(filtered)

    page_key = f"master-cpu-page-{catalog_id}"
    if page_key not in st.session_state:
        st.session_state[page_key] = 0

    n_pages = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE)
    page = min(st.session_state[page_key], n_pages - 1)
    st.session_state[page_key] = page

    start = page * _PAGE_SIZE
    page_cpus = filtered[start : start + _PAGE_SIZE]

    _cmb_render_cpu_nav(page, n_pages, page_key, total, catalog_id)

    rows = _cmb_build_cpu_rows(page_cpus)
    selected_rows = st.dataframe(
        rows,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key=f"master-cpu-table-{catalog_id}-p{page}",
    )

    sel = (selected_rows.selection.rows or []) if hasattr(selected_rows, "selection") else []
    _cmb_handle_cpu_selection(sel, page_cpus, base_url, actor, catalog_id)


def _cmb_render_equipe_expander(funcoes: list, equipamentos: list) -> None:
    """Render the team composition expander for a CPU."""
    if funcoes or equipamentos:
        with st.expander("⚙️ Composição de Equipe", expanded=True):
            if funcoes:
                st.caption("**Mão de obra**")
                st.dataframe(
                    [
                        {
                            "Função": f.get("funcao_id", ""),
                            "Qtd": f.get("num_pessoas", 1),
                            "Reg.": f.get("regime", "—"),
                            "Salário base": f.get("salario_base", "—"),
                        }
                        for f in funcoes
                        if isinstance(f, dict)
                    ],
                    hide_index=True,
                    use_container_width=True,
                )
            if equipamentos:
                st.caption("**Equipamentos**")
                st.dataframe(
                    [
                        {
                            "Equipamento": e.get("equip_id", ""),
                            "Qtd": e.get("num_unidades", 1),
                            "Custo mensal": e.get("custo_mensal", "—"),
                        }
                        for e in equipamentos
                        if isinstance(e, dict)
                    ],
                    hide_index=True,
                    use_container_width=True,
                )


def _cmb_render_composicao_expander(composicao: list) -> None:
    """Render the direct inputs expander for a CPU."""
    if composicao:
        with st.expander("🧱 Insumos Diretos", expanded=True):
            comp_rows = [
                {
                    "Insumo": it.get("insumo_id", ""),
                    "Coeficiente": it.get("coeficiente", 0),
                    "Categoria custo": it.get("categoria_custo", ""),
                }
                for it in composicao
                if isinstance(it, dict)
            ]
            st.caption(f"{len(composicao)} item(s)")
            st.dataframe(comp_rows, use_container_width=True, hide_index=True)


def _cmb_render_edit_expander(base_url: str, catalog_id: str, cpu: dict, codigo: str) -> None:
    """Render the master-catalog edit form expander for a CPU."""
    with st.expander("✏️ Editar no catálogo mestre", expanded=False):
        edited = render_typed_form(cpu, CPU_EDITABLE_FIELDS, CPU_READONLY_FIELDS, key=f"master-cpu-edit-{codigo}")
        motivo = st.text_input("Motivo *", placeholder="Ex: Atualização pós-medição", key=f"master-cpu-motivo-{codigo}")
        col_save, col_hint = st.columns([2, 3])
        if col_save.button(
            "💾 Salvar no mestre", type="primary", key=f"master-cpu-save-{codigo}", disabled=not motivo.strip()
        ):
            payload = {**cpu, **edited}
            try:
                result = api_call(
                    "PUT",
                    f"/api/catalogs/{catalog_id}/cpus/{codigo}",
                    payload={"cpu_data": payload, "motivo": motivo},
                    base_url=base_url,
                    actor=DEFAULT_ACTOR,
                )
                st.success(f"✅ `{codigo}` salva. Bundle invalidado: {result.get('bundle_invalidated')}")
                st.session_state.pop(f"master-cpus-all-{catalog_id}", None)
                st.rerun()
            except Exception as exc:
                st.error(f"Erro: {exc}")
        col_hint.caption("Salva em `cpus/{codigo}.json` e invalida o bundle cache.")


def _render_cpu_detail(base_url: str, actor: str, catalog_id: str, cpu: dict) -> None:
    codigo = cpu.get("codigo", "")
    st.subheader(f"`{codigo}` — {cpu.get('descricao', '')}")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Unidade", cpu.get("unidade") or "—")
    col2.metric("Categoria", cpu.get("categoria") or "—")
    col3.metric("Produção horária", cpu.get("producao_horaria") or "—")
    col4.metric("Origem", cpu.get("origem") or "—")

    equipe = cpu.get("equipe") or {}
    funcoes = equipe.get("funcoes") or []
    equipamentos = equipe.get("equipamentos") or []
    _cmb_render_equipe_expander(funcoes, equipamentos)

    composicao = cpu.get("composicao_itens") or []
    _cmb_render_composicao_expander(composicao)

    _cmb_render_edit_expander(base_url, catalog_id, cpu, codigo)


# ─── Insumos ──────────────────────────────────────────────────────────────────


def _cmb_filter_insumos(all_insumos: list, q: str) -> list:
    """Filter insumos by free-text query on codigo/descricao."""
    if not q:
        return all_insumos
    q_lower = q.lower()
    return [
        i
        for i in all_insumos
        if q_lower in (i.get("codigo") or "").lower() or q_lower in (i.get("descricao") or "").lower()
    ]


def _cmb_build_insumo_rows(page_items: list) -> list:
    """Build the list-of-dicts used in the insumo dataframe."""
    return [
        {
            "Código": ins.get("codigo") or ins.get("id", ""),
            "Descrição": (ins.get("descricao") or "")[:55],
            "Unidade": ins.get("unidade", ""),
            "Preço unit.": ins.get("preco_unitario") or "—",
            "Data ref.": (ins.get("data_referencia_preco") or "")[:10],
        }
        for ins in page_items
        if isinstance(ins, dict)
    ]


def _render_insumo_browser(base_url: str, actor: str, catalog_id: str) -> None:
    cache_key = f"master-insumos-all-{catalog_id}"
    if cache_key not in st.session_state:
        try:
            resp = api_call(
                "GET", f"/api/catalogs/{catalog_id}/insumos", params={"limit": 500}, base_url=base_url, actor=actor
            )
            st.session_state[cache_key] = resp.get("items", [])
        except Exception as exc:
            st.error(f"Erro ao carregar insumos: {exc}")
            return

    all_insumos: list[dict] = st.session_state[cache_key]

    col_q, col_ref = st.columns([5, 1])
    q = col_q.text_input(
        "Buscar", placeholder="Código ou descrição…", key=f"master-ins-q-{catalog_id}", label_visibility="collapsed"
    )
    if col_ref.button("↺", key=f"master-ins-reload-{catalog_id}"):
        st.session_state.pop(cache_key, None)
        st.rerun()

    filtered = _cmb_filter_insumos(all_insumos, q)

    total = len(filtered)

    page_key = f"master-ins-page-{catalog_id}"
    if page_key not in st.session_state:
        st.session_state[page_key] = 0
    page = min(st.session_state[page_key], max(0, (total - 1) // _PAGE_SIZE))
    st.session_state[page_key] = page

    start = page * _PAGE_SIZE
    page_items = filtered[start : start + _PAGE_SIZE]
    n_pages = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE)

    has_prev = page > 0
    has_next = page < n_pages - 1
    info_html = (
        "<div style='text-align:center;padding:0.35rem 0;font-size:0.85rem;'>"
        f"<strong>{total}</strong> insumos &nbsp;·&nbsp; página {page + 1}/{n_pages}"
        "</div>"
    )
    col_prev, col_info, col_next = st.columns([1, 5, 1])
    with col_prev:
        if has_prev and st.button("←", key=f"master-ins-prev-{catalog_id}", type="secondary", use_container_width=True):
            st.session_state[page_key] = page - 1
            st.rerun()
    col_info.markdown(info_html, unsafe_allow_html=True)
    with col_next:
        if has_next and st.button("→", key=f"master-ins-next-{catalog_id}", type="secondary", use_container_width=True):
            st.session_state[page_key] = page + 1
            st.rerun()

    rows = _cmb_build_insumo_rows(page_items)
    st.dataframe(rows, use_container_width=True, hide_index=True)


# ─── Editor de composição ─────────────────────────────────────────────────────

_CAT_OPTIONS = ["MAO_OBRA", "EQUIPAMENTO", "MATERIAL", "DIESEL", "SERVICO"]
_CAT_LABELS = {
    "MAO_OBRA": "🧑‍🔧 Mão de Obra",
    "EQUIPAMENTO": "⚙️ Equipamento",
    "MATERIAL": "🧱 Material",
    "DIESEL": "⛽ Diesel / Combustível",
    "SERVICO": "📋 Serviço",
}


def _render_composition_dialog(base_url: str, actor: str, catalog_id: str, cpu: dict) -> None:
    """Editor detalhado de composicao_itens para uma CPU do catalogo mestre (ADR-064/067)."""
    codigo = cpu.get("codigo", "")
    composicao = list(cpu.get("composicao_itens") or [])

    st.markdown(
        f"### ✏️ Composição: `{codigo}`    <br><small>{cpu.get('descricao', '')[:80]}</small>",
        unsafe_allow_html=True,
    )
    st.caption(
        "Edite os insumos que compõem esta CPU. O **coeficiente** representa a quantidade "
        "por unidade de serviço (ex: 1.0 L de emulsão por m²). "
        "Salvar grava em `config/catalogos/…` e invalida o bundle cache."
    )
    st.divider()

    # ── Tabela editável de composição ─────────────────────────────────────
    if composicao:
        st.caption(f"**{len(composicao)} item(s) na composição atual**")
        edited = st.data_editor(
            composicao,
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            column_config={
                "insumo_id": st.column_config.TextColumn(
                    "ID do Insumo",
                    help="Código do insumo (ex: MA-EMULSAO-RR-2C-IMPRIMACAO)",
                    width="large",
                ),
                "coeficiente": st.column_config.NumberColumn(
                    "Coeficiente",
                    help="Quantidade por unidade de serviço",
                    min_value=0.0,
                    step=0.001,
                    format="%.4f",
                    width="medium",
                ),
                "categoria_custo": st.column_config.SelectboxColumn(
                    "Categoria",
                    options=_CAT_OPTIONS,
                    help="Classificação do custo para BDI",
                    width="large",
                ),
            },
            key=f"comp-editor-{catalog_id}-{codigo}",
        )
    else:
        st.info("Nenhum insumo cadastrado. Use o botão abaixo para adicionar o primeiro item.")
        # Empty editor with template row
        edited = st.data_editor(
            [{"insumo_id": "", "coeficiente": 1.0, "categoria_custo": "MATERIAL"}],
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            column_config={
                "insumo_id": st.column_config.TextColumn("ID do Insumo", width="large"),
                "coeficiente": st.column_config.NumberColumn(
                    "Coeficiente", min_value=0.0, step=0.001, format="%.4f", width="medium"
                ),
                "categoria_custo": st.column_config.SelectboxColumn("Categoria", options=_CAT_OPTIONS, width="large"),
            },
            key=f"comp-editor-new-{catalog_id}-{codigo}",
        )

    # ── Guia de categorias ────────────────────────────────────────────────
    with st.expander("📖 Guia de categorias de custo", expanded=False):
        for k, v in _CAT_LABELS.items():
            st.markdown(f"- **{k}** — {v}")
        st.caption(
            "A categoria define qual alíquota de BDI é aplicada ao custo deste insumo. "
            "Mão de obra e equipamentos têm BDIs diferentes (ADR-023)."
        )

    st.divider()
    motivo = st.text_input(
        "Motivo da alteração *",
        placeholder="Ex: Adição de emulsão pós-revisão de projeto",
        key=f"comp-motivo-{catalog_id}-{codigo}",
    )

    col_save, col_cancel = st.columns(2)
    if col_save.button(
        "💾 Salvar composição", type="primary", key=f"comp-save-{catalog_id}-{codigo}", disabled=not motivo.strip()
    ):
        # Build updated CPU with new composicao_itens
        new_items = edited.to_dict("records") if hasattr(edited, "to_dict") else list(edited or [])
        # Filter out blank rows
        new_items = [it for it in new_items if it.get("insumo_id", "").strip()]
        updated_cpu = {**cpu, "composicao_itens": new_items}
        try:
            result = api_call(
                "PUT",
                f"/api/catalogs/{catalog_id}/cpus/{codigo}",
                payload={"cpu_data": updated_cpu, "motivo": motivo},
                base_url=base_url,
                actor=actor,
            )
            st.success(
                f"✅ Composição de `{codigo}` salva — {len(new_items)} item(s). "
                f"Bundle invalidado: {result.get('bundle_invalidated', True)}"
            )
            # Clear caches
            for k in list(st.session_state.keys()):
                if k.startswith("master-cpus-all-"):
                    del st.session_state[k]
            st.session_state.pop(f"comp-dialog-cpu-{catalog_id}", None)
            st.rerun()
        except Exception as exc:
            st.error(f"Erro ao salvar: {exc}")

    if col_cancel.button("Cancelar", type="secondary", key=f"comp-cancel-{catalog_id}-{codigo}"):
        st.session_state.pop(f"comp-dialog-cpu-{catalog_id}", None)
        st.rerun()
