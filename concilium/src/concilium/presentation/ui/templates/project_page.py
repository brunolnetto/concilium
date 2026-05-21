"""Atomic design templates - Full page layouts."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

try:
    from ..atoms.form_contracts import CPU_EDITABLE_FIELDS, CPU_READONLY_FIELDS, render_typed_form
    from ..config import DEFAULT_ACTOR, DEFAULT_BASE_URL
    from ..infra.api import api_call
    from ..molecules.common import render_page_heading
    from ..organisms.layout import (
        render_artifacts_tab,
        render_audit,
        render_backtracking_pe,
        render_bdi_tab,
        render_compare,
        render_cpu_composition_override,
        render_cpu_productivity_override,
        render_deliverables_config,
        render_diagnostico_pe,
        render_history,
        render_indiretos_config,
        render_ops_audit_tab,
        render_overview_tab,
        render_pipeline_monitor,
        render_planning_tab,
        render_run,
        render_saved_override,
        render_version_management,
    )
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
    from concilium.presentation.ui.organisms.layout import (
        render_artifacts_tab,
        render_audit,
        render_backtracking_pe,
        render_bdi_tab,
        render_compare,
        render_cpu_composition_override,
        render_cpu_productivity_override,
        render_deliverables_config,
        render_diagnostico_pe,
        render_history,
        render_indiretos_config,
        render_ops_audit_tab,
        render_overview_tab,
        render_pipeline_monitor,
        render_planning_tab,
        render_run,
        render_saved_override,
        render_version_management,
    )


def _deserialize_diagnostico(data: dict | None):
    """Reconstrói DiagnosticoPERelatorio a partir do dict da API."""
    if not data:
        return None
    try:
        from concilium.domain.models.diagnostico_pe import DiagnosticoPEItem, DiagnosticoPERelatorio, FatorPE

        itens = []
        for id_ in data.get("itens_deficit", []):
            fatores = tuple(
                FatorPE(codigo=f["codigo"], gap_rs=f["gap_rs"], pct_gap=f["pct_gap"]) for f in id_.get("fatores", [])
            )
            itens.append(
                DiagnosticoPEItem(
                    atividade_id=id_["atividade_id"],
                    cpu_id=id_.get("cpu_id", ""),
                    descricao=id_.get("descricao", ""),
                    preco_venda=id_.get("preco_venda", 0),
                    custo_realizado=id_.get("custo_realizado", 0),
                    gap_rs=id_.get("gap_rs", 0),
                    pct_gap_sobre_venda=id_.get("pct_gap_sobre_venda", 0),
                    eta_real=id_.get("eta_real", 1),
                    p_medio_uniforme=id_.get("p_medio_uniforme", 1),
                    cov_n_p=id_.get("cov_n_p", 0),
                    eps_cross=id_.get("eps_cross", 0),
                    validez_aproximacao=id_.get("validez_aproximacao", True),
                    n_total=id_.get("n_total", 0),
                    fatores=fatores,
                    l_aplicado=id_.get("l_aplicado", 0.09),
                    l_requerido=id_.get("l_requerido", 0.09),
                    delta_l=id_.get("delta_l", 0),
                )
            )
        return DiagnosticoPERelatorio(
            projeto_id=data.get("projeto_id", ""),
            gerado_em=data.get("gerado_em", ""),
            n_itens_deficit=data.get("n_itens_deficit", 0),
            gap_total_rs=data.get("gap_total_rs", 0),
            gap_evitavel_rs=data.get("gap_evitavel_rs", 0),
            gap_estrutural_rs=data.get("gap_estrutural_rs", 0),
            fator_dominante_label=data.get("fator_dominante_label", "—"),
            aviso_cross_term=data.get("aviso_cross_term", False),
            l_medio_requerido=data.get("l_medio_requerido", 0),
            itens_deficit=tuple(itens),
            consistencia_validada=data.get("consistencia_validada", True),
        )
    except Exception:
        return None


def _deserialize_backtracking(data: dict | None):
    """Reconstrói BacktrackingPERelatorio a partir do dict da API."""
    if not data:
        return None
    try:
        from concilium.domain.models.backtracking_pe import BacktrackingPEItem, BacktrackingPERelatorio, SolucaoInversa

        itens = []
        for it in data.get("itens", []):
            sols = []
            for s in it.get("solucoes", []):
                sols.append(SolucaoInversa(**{k: s[k] for k in SolucaoInversa.__dataclass_fields__ if k in s}))
            recom_data = it.get("solucao_recomendada")
            recom = (
                SolucaoInversa(**{k: recom_data[k] for k in SolucaoInversa.__dataclass_fields__ if k in recom_data})
                if recom_data
                else None
            )
            itens.append(
                BacktrackingPEItem(
                    atividade_id=it["atividade_id"],
                    descricao=it.get("descricao", ""),
                    pe_gap_atual=it.get("pe_gap_atual", 0),
                    pe_gap_alvo=it.get("pe_gap_alvo", 0),
                    solucoes=tuple(sols),
                    solucao_recomendada=recom,
                    roundtrips_falharam=tuple(it.get("roundtrips_falharam", [])),
                )
            )
        return BacktrackingPERelatorio(
            projeto_id=data.get("projeto_id", ""),
            gerado_em=data.get("gerado_em", ""),
            pe_gap_alvo=data.get("pe_gap_alvo", 0),
            itens=tuple(itens),
            consistencia_global=data.get("consistencia_global", True),
            n_roundtrips_falharam=data.get("n_roundtrips_falharam", 0),
        )
    except Exception:
        return None


def render_hot_project_template(project: dict) -> None:
    """Render HOT project template with tabs."""
    base_url = DEFAULT_BASE_URL
    actor = DEFAULT_ACTOR
    project_id = project["project_id"]

    render_page_heading(
        f"Projeto HOT: {project.get('nome', project_id)}",
        "Painel completo com planejamento, controle de versões, comparação e auditoria.",
    )

    tab_overview, tab_control_panel, tab_audit = st.tabs(["📊 Overview", "🛠️ Painel de Controle", "📝 Auditoria"])

    with tab_overview:
        sub_proj, sub_exec = st.tabs(["🔍 Projeto", "📈 Execuções"])

        with sub_proj:
            render_overview_tab(base_url, project, actor)
            st.divider()
            _render_project_config_tab(base_url, project, actor)

        with sub_exec:
            render_history(base_url, project_id, actor, context="overview")
            st.divider()
            render_pipeline_monitor(base_url, project_id, actor, context="overview")
            # Diagnóstico de PE e backtracking — carregados via API
            try:
                _diag_resp = api_call(
                    method="GET",
                    path=f"/api/projects/{project_id}/diagnostico-pe",
                    base_url=DEFAULT_BASE_URL,
                    actor=DEFAULT_ACTOR,
                )
                _diag_obj = _deserialize_diagnostico(_diag_resp.get("diagnostico_pe"))
                _back_obj = _deserialize_backtracking(_diag_resp.get("backtracking_pe"))
                if _diag_obj and _diag_obj.n_itens_deficit > 0:
                    st.divider()
                    render_diagnostico_pe(base_url, project_id, actor, _diag_obj)
                    render_backtracking_pe(_back_obj)
            except Exception:
                pass  # Diagnóstico é best-effort

    with tab_control_panel:
        sub_catalog, sub_plan, sub_versions, sub_artifacts = st.tabs(
            ["🔍 Catálogo", "📊 Planejamento", "🗂️ Versões", "📦 Artefatos"]
        )

        with sub_catalog:
            _render_project_catalog_section(base_url, project_id, actor)

        with sub_plan:
            # Versão base — dentro do Planejamento (item 1)
            versions = project.get("versions") or []
            version_options = versions if versions else [project.get("current_version") or "v1"]
            base_version = st.selectbox(
                "Versão base para replanejamento",
                options=version_options,
                index=0,
                key=f"control-base-version-{project_id}",
                help="Fork a partir desta versão ao executar um novo run.",
            )
            st.divider()

            # ── 🏗️ Custos Diretos ──────────────────────────────────────
            with st.expander("🏗️ Custos Diretos", expanded=False):
                with st.expander("🔧 Composição das CPUs", expanded=False):
                    render_cpu_composition_override(base_url, project_id, actor)
                with st.expander("📋 Políticas de Mobilização de Equipes", expanded=False):
                    render_planning_tab(base_url, project, actor, base_version)
                with st.expander("💪🏽 Produtividade das CPUs", expanded=False):
                    render_cpu_productivity_override(base_url, project_id, actor)

            # ── 🏢 Custos Indiretos (tabs internas por categoria) ────────
            with st.expander("🏢 Custos Indiretos", expanded=False):
                render_indiretos_config(base_url, project_id, actor)

            # ── BDI e Saídas ─────────────────────────────────────────────
            with st.expander("💰 BDI e Regime Tributário", expanded=False):
                render_bdi_tab(base_url, project, actor)

            with st.expander("📦 Saídas do Planejamento", expanded=False):
                render_deliverables_config(base_url, project_id, actor)

            # Run ao final, após todas as configurações
            st.divider()
            render_run(base_url, project_id, actor, base_version, project=project)

        with sub_versions:
            render_compare(base_url, project, actor)
            st.divider()
            render_version_management(base_url, project, actor)

        with sub_artifacts:
            render_artifacts_tab(base_url, project_id, project, actor)

    with tab_audit:
        render_ops_audit_tab(base_url, project_id, actor)

    # tab_config removed — configuration is now embedded in tab_overview


def _build_prod_map(catalog_snap: dict) -> dict:
    return {p["id"]: p for p in (catalog_snap.get("produtividades") or []) if isinstance(p, dict) and "id" in p}


def _build_raw_cpus(catalog_snap: dict) -> list:
    return [c for c in (catalog_snap.get("cpus") or []) if isinstance(c, dict) and c.get("codigo")]


def _enrich_cpu_with_prod(c: dict, prod_map: dict) -> dict:
    ref = c.get("producao_id_ref")
    prod = prod_map.get(ref) if ref else None
    if prod and not c.get("equipe") and prod.get("equipe"):
        return {**c, "equipe": prod["equipe"]}
    return c


def _build_project_cpu_map(reference: dict) -> dict:
    catalog_snap = reference.get("catalog") or {}
    prod_map = _build_prod_map(catalog_snap)
    raw_cpus = _build_raw_cpus(catalog_snap)
    cpu_map: dict = {}
    for c in raw_cpus:
        c = _enrich_cpu_with_prod(c, prod_map)
        cpu_map[str(c.get("codigo", ""))] = c
    return cpu_map


def _build_equipe_rows(equipe: dict) -> list:
    funcoes = equipe.get("funcoes") or []
    equipamentos = equipe.get("equipamentos") or []
    rows = []
    for f in funcoes:
        if isinstance(f, dict):
            rows.append({"Tipo": "👷 " + str(f.get("funcao_id", "")), "Qtd": f.get("num_pessoas", 1)})
    for e in equipamentos:
        if isinstance(e, dict):
            rows.append({"Tipo": "🚜 " + str(e.get("equip_id", "")), "Qtd": e.get("num_unidades", 1)})
    return rows


def _render_eap_equipe_section(equipe: dict) -> None:
    eq_rows = _build_equipe_rows(equipe)
    if eq_rows:
        st.caption("**⚙️ Equipe**")
        st.dataframe(eq_rows, hide_index=True, use_container_width=True)


def _render_eap_composicao_section(composicao: list, has_equipe: bool) -> None:
    if composicao:
        st.caption("**🧱 Insumos diretos**")
        st.dataframe(
            [
                {
                    "Insumo": it.get("insumo_id", ""),
                    "Coef.": it.get("coeficiente", 0),
                    "Categoria": it.get("categoria_custo", ""),
                }
                for it in composicao
                if isinstance(it, dict)
            ],
            hide_index=True,
            use_container_width=True,
        )
    elif not has_equipe:
        st.caption("Composição não registrada para esta CPU.")


def _render_eap_item_body(item: dict, cpu_data: dict, qtd: object, unidade: str) -> None:
    cpu_id = item.get("cpu_id", "—")
    c1, c2, c3 = st.columns(3)
    c1.caption("CPU")
    c1.code(cpu_id)
    c2.caption("Quantitativo")
    c2.metric("", f"{qtd} {unidade}")
    prod = cpu_data.get("producao_horaria") or "—"
    c3.caption("Produtividade")
    c3.metric("", f"{prod} {unidade}/h" if prod != "—" else "—")
    equipe = cpu_data.get("equipe") or {}
    funcoes = equipe.get("funcoes") or []
    equipamentos = equipe.get("equipamentos") or []
    composicao = cpu_data.get("composicao_itens") or []
    has_equipe = bool(funcoes or equipamentos)
    if has_equipe:
        _render_eap_equipe_section(equipe)
    _render_eap_composicao_section(composicao, has_equipe)


def _render_eap_item_expander(item: dict, cpu_map: dict) -> None:
    cpu_id = item.get("cpu_id", "—")
    qtd = item.get("quantitativo", "—")
    unidade = item.get("unidade", "")
    descricao = item.get("descricao") or cpu_id
    item_id = item.get("item_id", "?")
    label = f"📌 **{item_id}** — {descricao[:60]}  ·  {qtd} {unidade}"
    cpu_data = cpu_map.get(cpu_id) or {}
    with st.expander(label, expanded=False):
        _render_eap_item_body(item, cpu_data, qtd, unidade)


def _render_eap_section(reference: dict) -> None:
    st.caption(
        "Versões já executadas preservam o canonical completo do momento do run. "
        "Re-executar com nova EAP produzirá resultados diferentes. "
        "**Recomendação:** crie um novo projeto para mudanças estruturais de escopo."
    )
    eap_items = (reference.get("cpus") or {}).get("itens_eap", [])
    cpu_map = _build_project_cpu_map(reference)
    if eap_items:
        st.caption(f"**{len(eap_items)}** atividade(s)")
        for item in eap_items:
            _render_eap_item_expander(item, cpu_map)
    else:
        st.info("Nenhum item de EAP encontrado na referência deste projeto.")


def _render_context_section(base_url: str, project: dict, project_id: str, actor: str) -> None:
    st.caption("Alterar contexto afeta cálculos de runs **futuros**. Versões anteriores preservam snapshots imutáveis.")
    try:
        ctxs_resp = api_call(method="GET", path="/api/contextos", base_url=base_url, actor=actor)
        ctx_options = [c.get("id") for c in (ctxs_resp.get("items") or []) if c.get("id")]
    except Exception:
        ctx_options = []

    current_ctx = project.get("contexto_id", "")
    if ctx_options:
        selected_ctx = st.selectbox(
            "Contexto",
            options=ctx_options,
            index=ctx_options.index(current_ctx) if current_ctx in ctx_options else 0,
            key=f"cfg-ctx-{project_id}",
            help="Contexto define catálogo, jurisdição e BDI padrão.",
        )
        if st.button("Aplicar novo contexto", key=f"cfg-ctx-save-{project_id}", type="primary"):
            try:
                api_call(
                    method="PATCH",
                    path=f"/api/projects/{project_id}/config",
                    base_url=base_url,
                    payload={"contexto_id": selected_ctx},
                    actor=actor,
                )
                st.success(f"Contexto alterado para '{selected_ctx}'. Re-execute o pipeline para aplicar.")
                st.rerun()
            except Exception as exc:
                st.error(f"Erro ao alterar contexto: {exc}")
    else:
        st.caption(f"Contexto atual: **{current_ctx}** | Benchmark: **{project.get('benchmark_slug', '—')}**")
        st.info("API de contextos não disponível.")


def _render_project_config_tab(base_url: str, project: dict, actor: str) -> None:
    """Seção de configuração — EAP e contexto integrados ao Overview."""
    project_id = project["project_id"]

    # Carrega referência uma vez para reutilizar nas duas seções abaixo
    try:
        reference = api_call(
            method="GET",
            path=f"/api/projects/{project_id}/benchmark-reference",
            base_url=base_url,
            actor=actor,
        )
    except Exception:
        reference = {}

    with st.expander("📋 Atividades da EAP", expanded=False):
        _render_eap_section(reference)

    with st.expander("🌐 Contexto e Perfil", expanded=False):
        _render_context_section(base_url, project, project_id, actor)


def render_normal_project_template(project: dict) -> None:
    """Render normal project template with columns."""
    base_url = DEFAULT_BASE_URL
    actor = DEFAULT_ACTOR
    project_id = project["project_id"]

    render_page_heading(
        f"Projeto: {project.get('nome', project_id)}",
        "Operações essenciais de execução, overrides, histórico e artefatos.",
    )

    col_a, col_b = st.columns(2)
    with col_a:
        render_run(base_url, project_id, actor, project.get("current_version"), project=project)
        st.divider()
        render_pipeline_monitor(base_url, project_id, actor, context="normal")
        st.divider()
        render_saved_override(base_url, project_id, actor)
        st.divider()
        render_history(base_url, project_id, actor, context="normal")
    with col_b:
        render_compare(base_url, project, actor)
        st.divider()
        render_artifacts_tab(base_url, project_id, project, actor)
        st.divider()
        render_audit(base_url, project_id, actor)


def _render_overrides_section(base_url: str, project_id: str, actor: str, overrides: dict) -> None:
    if overrides:
        st.caption(f"**Overrides deste projeto** — {len(overrides)} CPU(s) customizada(s)")
        ov_rows = [
            {
                "Código": k,
                "Descrição": (v.get("descricao") or "")[:50],
                "Unidade": v.get("unidade", ""),
                "Prod. Hor.": v.get("producao_horaria") or "—",
            }
            for k, v in overrides.items()
            if isinstance(v, dict)
        ]
        ov_sel = st.dataframe(
            ov_rows,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key=f"proj-ov-table-{project_id}",
        )
        ov_sel_rows = (ov_sel.selection.rows or []) if hasattr(ov_sel, "selection") else []
        if ov_sel_rows:
            sel_code = ov_rows[ov_sel_rows[0]]["Código"]
            sel_data = overrides.get(sel_code, {})
            st.divider()
            _render_project_cpu_editor(
                base_url, project_id, actor, sel_code, sel_data, label="Editar override existente"
            )
        st.divider()
    else:
        st.caption("Nenhum override de CPU neste projeto ainda.")


def _load_catalog_cpus(project_id: str, base_url: str, actor: str) -> tuple[str, str, list]:
    try:
        project_meta = api_call("GET", f"/api/projects/{project_id}", base_url=base_url, actor=actor)
    except Exception:
        project_meta = {}
    catalog_id = project_meta.get("contexto_id", "mendeslobo")
    cache_key = f"proj-cat-cpus-{project_id}"
    if cache_key not in st.session_state:
        try:
            resp = api_call(
                "GET", f"/api/catalogs/{catalog_id}/cpus", params={"limit": 500}, base_url=base_url, actor=actor
            )
            st.session_state[cache_key] = resp.get("items", [])
        except Exception:
            st.session_state[cache_key] = []
    return catalog_id, cache_key, st.session_state[cache_key]


def _cpu_matches_query(c: dict, ql: str) -> bool:
    return ql in (c.get("codigo") or "").lower() or ql in (c.get("descricao") or "").lower()


def _filter_catalog_cpus(all_cpus: list, q: str, sel_cats: list) -> list:
    filtered = all_cpus
    if q:
        ql = q.lower()
        filtered = [c for c in filtered if _cpu_matches_query(c, ql)]
    if sel_cats:
        filtered = [c for c in filtered if c.get("categoria") in sel_cats]
    return filtered


def _render_catalog_filter_row(project_id: str, all_cpus: list, cache_key: str) -> tuple[str, list]:
    col_q, col_cats, col_ref = st.columns([3, 2, 1])
    q = col_q.text_input(
        "Buscar CPU", placeholder="Código ou descrição…", key=f"proj-cat-q-{project_id}", label_visibility="collapsed"
    )
    categorias = sorted({str(c.get("categoria") or "") for c in all_cpus if c.get("categoria")})
    sel_cats = col_cats.multiselect(
        "Categoria",
        options=categorias,
        key=f"proj-cat-cats-{project_id}",
        label_visibility="collapsed",
        placeholder="Todas as categorias",
    )
    if col_ref.button("↺", key=f"proj-cat-reload-{project_id}", help="Recarregar catálogo"):
        st.session_state.pop(cache_key, None)
        st.rerun()
    return q, sel_cats


def _get_catalog_page(project_id: str, total: int, page_size: int) -> tuple[int, int, str]:
    page_key = f"proj-cat-page-{project_id}"
    if page_key not in st.session_state:
        st.session_state[page_key] = 0
    page = min(st.session_state[page_key], max(0, (total - 1) // page_size))
    st.session_state[page_key] = page
    n_pages = max(1, (total + page_size - 1) // page_size)
    return page, n_pages, page_key


def _render_catalog_page_nav(
    project_id: str, page: int, n_pages: int, catalog_id: str, total: int, page_key: str
) -> None:
    info_html = (
        "<div style='text-align:center;padding:0.35rem 0;font-size:0.85rem;'>"
        f"Catálogo <strong>{catalog_id}</strong> &nbsp;·&nbsp; "
        f"<strong>{total}</strong> CPUs &nbsp;·&nbsp; página {page + 1}/{n_pages}"
        "</div>"
    )
    col_prev, col_info, col_next = st.columns([1, 5, 1])
    with col_prev:
        if page > 0 and st.button("←", key=f"proj-cat-prev-{project_id}", type="secondary", use_container_width=True):
            st.session_state[page_key] = page - 1
            st.rerun()
    col_info.markdown(info_html, unsafe_allow_html=True)
    with col_next:
        if page < n_pages - 1 and st.button(
            "→", key=f"proj-cat-next-{project_id}", type="secondary", use_container_width=True
        ):
            st.session_state[page_key] = page + 1
            st.rerun()


def _build_catalog_page_rows(page_cpus: list, overrides: dict) -> list:
    rows = []
    for c in page_cpus:
        code = c.get("codigo", "")
        status = "✏️ Customizado" if code in overrides else "🔵 Mestre"
        rows.append(
            {
                "Código": code,
                "Descrição": (c.get("descricao") or "")[:50],
                "Unidade": c.get("unidade", ""),
                "Categoria": c.get("categoria", ""),
                "Prod. Hor.": c.get("producao_horaria") or "—",
                "Status": status,
            }
        )
    return rows


def _render_catalog_selection(
    sel_tbl: object, page_cpus: list, overrides: dict, base_url: str, project_id: str, actor: str
) -> None:
    sel_rows = (sel_tbl.selection.rows or []) if hasattr(sel_tbl, "selection") else []  # type: ignore[union-attr]
    if sel_rows:
        cpu = page_cpus[sel_rows[0]]
        cpu_code = cpu.get("codigo", "")
        current = {**cpu, **(overrides.get(cpu_code) or {})}
        st.divider()
        _render_project_cpu_editor(
            base_url, project_id, actor, cpu_code, current, label="Sobrescrever CPU neste projeto"
        )


def _render_project_catalog_section(base_url: str, project_id: str, actor: str) -> None:
    """Gestao paginada do catalogo do projeto (ADR-040/066).

    Mostra imediatamente os overrides existentes + tabela paginada do catalogo master
    para busca e sobrescrita inline.
    """
    _PAGE = 25

    try:
        overrides = api_call("GET", f"/api/projects/{project_id}/catalog/overrides", base_url=base_url, actor=actor)
    except Exception:
        overrides = {}

    _render_overrides_section(base_url, project_id, actor, overrides)
    catalog_id, cache_key, all_cpus = _load_catalog_cpus(project_id, base_url, actor)
    q, sel_cats = _render_catalog_filter_row(project_id, all_cpus, cache_key)
    filtered = _filter_catalog_cpus(all_cpus, q, sel_cats)
    total = len(filtered)
    page, n_pages, page_key = _get_catalog_page(project_id, total, _PAGE)
    _render_catalog_page_nav(project_id, page, n_pages, catalog_id, total, page_key)
    start = page * _PAGE
    page_cpus = filtered[start : start + _PAGE]
    rows = _build_catalog_page_rows(page_cpus, overrides)
    sel_tbl = st.dataframe(
        rows,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key=f"proj-cat-tbl-{project_id}-p{page}",
    )
    _render_catalog_selection(sel_tbl, page_cpus, overrides, base_url, project_id, actor)


def _render_project_cpu_editor(
    base_url: str,
    project_id: str,
    actor: str,
    cpu_id: str,
    cpu_data: dict,
    label: str = "Editar CPU",
) -> None:
    st.caption(f"**{label}:** `{cpu_id}` — {cpu_data.get('descricao', '')}")
    edited = render_typed_form(
        cpu_data, CPU_EDITABLE_FIELDS, CPU_READONLY_FIELDS, key=f"proj-cpu-form-{project_id}-{cpu_id}"
    )
    motivo = st.text_input("Motivo do override", key=f"proj-cpu-motivo-{project_id}-{cpu_id}")
    if st.button(
        "💾 Salvar override", type="primary", key=f"proj-cpu-save-{project_id}-{cpu_id}", disabled=not motivo.strip()
    ):
        payload = {**cpu_data, **edited}
        try:
            api_call(
                "POST",
                f"/api/projects/{project_id}/catalog/cpus/{cpu_id}",
                payload=payload,
                base_url=base_url,
                actor=actor,
                params={"motivo": motivo},
            )
            st.success(f"Override de `{cpu_id}` salvo!")
            st.session_state.pop(f"proj-cat-cpus-{project_id}", None)
            st.rerun()
        except Exception as exc:
            st.error(f"Erro: {exc}")
