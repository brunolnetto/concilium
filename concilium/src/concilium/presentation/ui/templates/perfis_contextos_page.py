"""Página de gestão de Perfis e Contextos — ADR-062.

Perfis e Contextos compartilham a mesma lógica de versionamento
(ConfigVersionService). Esta página expõe o histórico, comparação e
criação de novas versões para ambas as entidades.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import streamlit as st

try:
    from ..config import DEFAULT_ACTOR, DEFAULT_BASE_URL
    from ..infra.api import api_call
    from ..molecules.common import render_page_heading
except ImportError:
    src_root = Path(__file__).resolve().parents[4]
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))
    from concilium.presentation.ui.config import DEFAULT_ACTOR, DEFAULT_BASE_URL
    from concilium.presentation.ui.infra.api import api_call
    from concilium.presentation.ui.molecules.common import render_page_heading


# ═══════════════════════════════════════════════════════════════════════════
# Página principal
# ═══════════════════════════════════════════════════════════════════════════


def render_configuracao_page() -> None:
    render_page_heading(
        "Configuração",
        "Gerencie perfis financeiros, contextos, temas visuais e overlays de jurisdição.",
    )

    base_url = DEFAULT_BASE_URL
    actor = DEFAULT_ACTOR

    tabs = st.tabs(["⚖️ Jurisdições", "📋 Perfis", "🌐 Contextos", "🎨 Temas"])

    with tabs[0]:
        _render_jurisdicoes_section(base_url=base_url, actor=actor)

    with tabs[1]:
        _render_entity_section(
            base_url=base_url,
            actor=actor,
            list_path="/api/perfis",
            versions_path_tpl="/api/perfis/{id}/versions",
            compare_path="/api/perfis/compare",
            entity_label="Perfil",
            key_prefix="perf",
            extra_renderer=_render_perfil_detail,
        )

    with tabs[2]:
        _render_entity_section(
            base_url=base_url,
            actor=actor,
            list_path="/api/contextos",
            versions_path_tpl="/api/contextos/{id}/versions",
            compare_path="/api/contextos/compare",
            entity_label="Contexto",
            key_prefix="ctx",
        )

    with tabs[3]:
        _render_temas_section(base_url=base_url, actor=actor)

    st.divider()


# ═══════════════════════════════════════════════════════════════════════════
# Secção genérica de entidade versionada (usada por Perfis E Contextos)
# ═══════════════════════════════════════════════════════════════════════════


def _render_entity_section(
    base_url: str,
    actor: str,
    list_path: str,
    versions_path_tpl: str,
    compare_path: str,
    entity_label: str,
    key_prefix: str,
    extra_renderer=None,
) -> None:
    try:
        resp = api_call(method="GET", path=list_path, base_url=base_url, actor=actor)
        entities = resp.get("items") or []
    except Exception as exc:
        st.error(f"Não foi possível carregar {entity_label.lower()}s: {exc}")
        return

    if not entities:
        st.info(f"Nenhum(a) {entity_label.lower()} encontrado(a).")
        return

    ids = [e.get("id") for e in entities if e.get("id")]
    emap = {e.get("id"): e for e in entities}

    selected = st.selectbox(
        entity_label,
        options=ids,
        key=f"{key_prefix}-selected",
        format_func=lambda eid: f"{emap[eid].get('nome') or eid}  (atual: {emap[eid].get('current_version', 'v1')})",
    )
    entity = emap.get(selected, {})
    versions = entity.get("versions") or []

    # Tabs de versionamento
    tabs_labels = ["📜 Histórico", "🔀 Comparar versões", "➕ Nova versão"]
    if extra_renderer:
        tabs_labels.append("🔍 Detalhe")
    tabs = st.tabs(tabs_labels)

    with tabs[0]:
        _render_version_history(versions, entity.get("current_version", "v1"))

    with tabs[1]:
        _render_version_compare(base_url, actor, compare_path, selected, versions, key_prefix)

    with tabs[2]:
        _render_new_version_form(
            base_url,
            actor,
            versions_path_tpl.format(id=selected),
            selected,
            versions,
            key_prefix,
        )

    if extra_renderer and len(tabs) > 3:
        with tabs[3]:
            extra_renderer(entity, versions, base_url=base_url, actor=actor)


# ═══════════════════════════════════════════════════════════════════════════
# Helpers de versão compartilhados
# ═══════════════════════════════════════════════════════════════════════════


def _render_version_history(versions: list[dict], current_v: str) -> None:
    if not versions:
        st.info("Nenhum histórico de versões disponível.")
        return

    st.caption(f"**{len(versions)}** versão(ões) · ativa: **{current_v}**")
    for v in reversed(versions):
        is_current = v.get("version") == current_v
        label = f"**{v.get('version')}**" + (" ← atual" if is_current else "")
        with st.expander(label, expanded=is_current):
            col_a, col_b, col_c = st.columns(3)
            col_a.caption("Criado em")
            col_a.write(str(v.get("created_at") or "—")[:19].replace("T", " "))
            col_b.caption("Por")
            col_b.write(v.get("created_by") or "—")
            # Show most relevant config field
            for field in ("catalogo_id", "jurisdicao_id", "perfil_id", "nome"):
                if v.get(field):
                    col_c.caption(field)
                    col_c.write(v[field])
                    break
            st.caption(f"**Motivo:** {v.get('motivo') or '—'}")
            details = {
                k: v[k]
                for k in v
                if k not in ("version", "created_at", "created_by", "motivo")
                and not k.startswith("$")
                and v[k] is not None
            }
            if details:
                _render_entity_card(details)


def _render_version_compare(
    base_url: str,
    actor: str,
    compare_path: str,
    entity_id: str,
    versions: list[dict],
    key_prefix: str,
) -> None:
    v_ids = [v.get("version") for v in versions if v.get("version")]
    if len(v_ids) < 2:
        st.info("São necessárias ao menos duas versões para comparar.")
        return

    c1, c2 = st.columns(2)
    vA = c1.selectbox("Versão A (base)", options=v_ids, index=0, key=f"{key_prefix}-cmp-va")
    vB = c2.selectbox("Versão B (nova)", options=v_ids, index=len(v_ids) - 1, key=f"{key_prefix}-cmp-vb")

    if st.button("Comparar", key=f"{key_prefix}-btn-compare", type="secondary"):
        try:
            diff = api_call(
                method="GET",
                path=compare_path,
                base_url=base_url,
                actor=actor,
                params={"id": entity_id, "vA": vA, "vB": vB},
            )
            changed = diff.get("changed") or {}
            if changed:
                st.markdown(f"**{len(changed)} campo(s) alterado(s)**")
                st.dataframe(
                    [
                        {"Campo": f, "De": str(d.get("de") or "—"), "Para": str(d.get("para") or "—")}
                        for f, d in changed.items()
                    ],
                    hide_index=True,
                    use_container_width=True,
                )
            else:
                st.success("As versões são idênticas nos campos de configuração.")
            unchanged = diff.get("unchanged") or []
            if unchanged:
                st.caption(f"Campos inalterados: {', '.join(str(u) for u in unchanged)}")
        except Exception as exc:
            st.error(f"Erro ao comparar: {exc}")


def _render_new_version_form(
    base_url: str,
    actor: str,
    post_path: str,
    entity_id: str,
    versions: list[dict],
    key_prefix: str,
) -> None:
    st.caption(
        "Uma nova versão é criada a partir da versão ativa. "
        "Informe apenas os campos que deseja alterar e o motivo da mudança (obrigatório)."
    )

    # Detect available fields from the latest version
    latest = versions[-1] if versions else {}
    config_fields = {
        k: latest.get(k) or ""
        for k in ("catalogo_id", "jurisdicao_id", "perfil_id", "referencia_id", "nome", "descricao")
        if k in latest
    }

    with st.form(key=f"{key_prefix}-new-version-{entity_id}"):
        motivo = st.text_area(
            "Motivo da nova versão *",
            placeholder="Ex.: Atualização do catálogo para tabela de preços Q2/2026",
            help="Campo obrigatório — documenta a intenção para auditoria futura.",
        )
        edited_fields: dict[str, Any] = {}
        if config_fields:
            cols = st.columns(min(3, len(config_fields)))
            for i, (field, current_val) in enumerate(config_fields.items()):
                val = cols[i % len(cols)].text_input(field, value=str(current_val or ""))
                if val.strip():
                    edited_fields[field] = val.strip()

        make_current = st.checkbox("Tornar esta a versão ativa", value=True)
        submitted = st.form_submit_button("Criar nova versão", use_container_width=True)

        if submitted:
            if not motivo.strip():
                st.error("O campo 'motivo' é obrigatório.")
            else:
                payload = {"motivo": motivo.strip(), **edited_fields}
                if not make_current:
                    payload["_make_current"] = False
                try:
                    result = api_call(
                        method="POST",
                        path=post_path,
                        base_url=base_url,
                        payload=payload,
                        actor=actor,
                    )
                    st.success(f"Versão **{result.get('version', '?')}** criada com sucesso.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Erro ao criar versão: {exc}")


# ═══════════════════════════════════════════════════════════════════════════
# Componente reutilizável: card de entidade (substitui JSON bruto)
# ═══════════════════════════════════════════════════════════════════════════

_AUDIT_KEYS = {"version", "created_at", "created_by", "motivo", "$comment"}
_SKIP_DISPLAY = {"_make_current"}


def _pctx_split_display(data: dict) -> tuple:
    """Split entity data into (display, scalars, nested) dicts."""
    display = {
        k: v
        for k, v in data.items()
        if k not in _AUDIT_KEYS and k not in _SKIP_DISPLAY and not k.startswith("$") and v is not None
    }
    scalars = {k: v for k, v in display.items() if not isinstance(v, (dict, list))}
    nested = {k: v for k, v in display.items() if isinstance(v, (dict, list))}
    return display, scalars, nested


def _pctx_render_nested_item(k: str, v) -> None:
    """Render one nested (dict or list) field inside an entity card."""
    if isinstance(v, dict) and v:
        label = k.replace("_", " ").title()
        pairs = [f"**{fk}:** {fv}" for fk, fv in v.items() if fv is not None]
        if pairs:
            st.caption(label)
            st.markdown("  ".join(pairs[:6]))
    elif isinstance(v, list) and v:
        st.caption(f"{k.replace('_', ' ').title()} ({len(v)} itens)")


def _render_entity_card(data: dict, title: str = "Configuração", expanded: bool = False) -> None:
    """Painel resumido de campos de uma entidade — substitui st.json() bruto.

    Mostra campos escalares como métricas/texto, dicts aninhados como expanders,
    e ignora campos de auditoria e chaves internas.
    """
    display, scalars, nested = _pctx_split_display(data)
    if not display:
        return

    with st.expander(title, expanded=expanded):
        if scalars:
            cols = st.columns(min(3, len(scalars)))
            for i, (k, v) in enumerate(scalars.items()):
                label = k.replace("_", " ").title()
                cols[i % len(cols)].caption(label)
                cols[i % len(cols)].text(str(v)[:80])

        for k, v in nested.items():
            _pctx_render_nested_item(k, v)


# ═══════════════════════════════════════════════════════════════════════════
# Renderer extra específico para Perfis
# ═══════════════════════════════════════════════════════════════════════════


def _get_perfil_current_data(entity: dict, versions: list) -> tuple:
    current_v = entity.get("current_version", "v1")
    current_data = next((v for v in versions if v.get("version") == current_v), entity)
    margem_alvo = current_data.get("faixa_margem_alvo") or {}
    margem_ac = current_data.get("faixa_margem_aceitavel") or {}
    razao = current_data.get("razao_indireto_direto_alvo") or {}
    return current_data, margem_alvo, margem_ac, razao


def _fmt_faixa(faixa: dict) -> str:
    return f"{faixa.get('min', 0) * 100:.0f}% – {faixa.get('max', 0) * 100:.0f}%" if faixa else "—"


def _build_cats_seed(cats_raw: list) -> list:
    return [
        {
            "Código": c.get("codigo", ""),
            "Descrição": c.get("descricao", ""),
            "Driver": c.get("driver") or (c.get("regra_dimensionamento") or {}).get("tipo") or "permanencia",
        }
        for c in cats_raw
        if isinstance(c, dict)
    ]


def _build_cats_summary_rows(cats: list) -> list:
    return [
        {
            "Código": c.get("codigo") or "—",
            "Descrição": c.get("descricao") or "—",
            "Driver": c.get("driver") or (c.get("regra_dimensionamento") or {}).get("tipo") or "—",
        }
        for c in cats
        if isinstance(c, dict)
    ]


def _save_perfil_fin_version(
    entity_id: str,
    edited_cats: object,
    motivo: str,
    ma_min: float,
    ma_max: float,
    mac_min: float,
    mac_max: float,
    raz_min: float,
    raz_max: float,
    base_url: str,
    actor: str,
    versions_path: str,
) -> None:
    cats_list = (
        edited_cats
        if isinstance(edited_cats, list)
        else (edited_cats.to_dict("records") if hasattr(edited_cats, "to_dict") else [])  # type: ignore[union-attr]
    )
    new_cats = [
        {"codigo": r.get("Código", ""), "descricao": r.get("Descrição", ""), "driver": r.get("Driver", "permanencia")}
        for r in cats_list
        if str(r.get("Código", "")).strip()
    ]
    payload = {
        "motivo": motivo.strip(),
        "faixa_margem_alvo": {"min": ma_min / 100, "max": ma_max / 100},
        "faixa_margem_aceitavel": {"min": mac_min / 100, "max": mac_max / 100},
        "razao_indireto_direto_alvo": {"min": raz_min / 100, "max": raz_max / 100},
        "categorias_indireto": new_cats,
    }
    try:
        result = api_call(method="POST", path=versions_path, payload=payload, base_url=base_url, actor=actor)
        st.success(f"Versão **{result.get('version', '?')}** criada com sucesso.")
        st.rerun()
    except Exception as exc:
        st.error(f"Erro ao salvar: {exc}")


def _render_perfil_fin_form(
    entity_id: str,
    current_data: dict,
    margem_alvo: dict,
    margem_ac: dict,
    razao: dict,
    base_url: str,
    actor: str,
) -> None:
    versions_path = f"/api/perfis/{entity_id}/versions"
    cats_raw = current_data.get("categorias_indireto") or []

    def _pct(faixa: dict, key: str, default: float) -> float:
        return float((faixa or {}).get(key, default)) * 100

    with st.form(f"perfil-fin-form-{entity_id}"):
        st.markdown("**Margem alvo**")
        c1, c2 = st.columns(2)
        ma_min = c1.number_input(
            "Mínimo (%)",
            min_value=0.0,
            max_value=100.0,
            step=0.5,
            value=_pct(margem_alvo, "min", 0.15),
            key=f"pfin-ma-min-{entity_id}",
        )
        ma_max = c2.number_input(
            "Máximo (%)",
            min_value=0.0,
            max_value=100.0,
            step=0.5,
            value=_pct(margem_alvo, "max", 0.25),
            key=f"pfin-ma-max-{entity_id}",
        )
        st.markdown("**Margem aceitável**")
        c3, c4 = st.columns(2)
        mac_min = c3.number_input(
            "Mínimo (%)",
            min_value=0.0,
            max_value=100.0,
            step=0.5,
            value=_pct(margem_ac, "min", 0.08),
            key=f"pfin-mac-min-{entity_id}",
        )
        mac_max = c4.number_input(
            "Máximo (%)",
            min_value=0.0,
            max_value=100.0,
            step=0.5,
            value=_pct(margem_ac, "max", 0.30),
            key=f"pfin-mac-max-{entity_id}",
        )
        st.markdown("**Razão indireto / direto alvo**")
        c5, c6 = st.columns(2)
        raz_min = c5.number_input(
            "Mínimo (%)",
            min_value=0.0,
            max_value=200.0,
            step=0.5,
            value=_pct(razao, "min", 0.20),
            key=f"pfin-raz-min-{entity_id}",
        )
        raz_max = c6.number_input(
            "Máximo (%)",
            min_value=0.0,
            max_value=200.0,
            step=0.5,
            value=_pct(razao, "max", 0.40),
            key=f"pfin-raz-max-{entity_id}",
        )
        st.markdown("**Categorias de custo indireto**")
        edited_cats = st.data_editor(
            _build_cats_seed(cats_raw),
            column_config={
                "Código": st.column_config.TextColumn(width="small"),
                "Descrição": st.column_config.TextColumn(width="large"),
                "Driver": st.column_config.SelectboxColumn(
                    options=["permanencia", "one_time", "por_medicao"],
                    width="medium",
                ),
            },
            num_rows="dynamic",
            hide_index=True,
            use_container_width=True,
            key=f"pfin-cats-{entity_id}",
        )
        motivo = st.text_input(
            "Motivo da alteração *", placeholder="Ex: Ajuste de targets Q2/2026", key=f"pfin-motivo-{entity_id}"
        )
        submitted = st.form_submit_button("💾 Salvar como nova versão", type="primary", use_container_width=True)

    if submitted and base_url:
        if not motivo.strip():
            st.warning("Informe o motivo antes de salvar.")
        else:
            _save_perfil_fin_version(
                entity_id,
                edited_cats,
                motivo,
                ma_min,
                ma_max,
                mac_min,
                mac_max,
                raz_min,
                raz_max,
                base_url,
                actor,
                versions_path,
            )


def _render_perfil_detail(entity: dict, versions: list[dict], base_url: str = "", actor: str = "") -> None:
    """Detalhe do perfil: metas financeiras, editor tipado, categorias de indireto."""
    current_data, margem_alvo, margem_ac, razao = _get_perfil_current_data(entity, versions)
    entity_id = entity.get("id", "")

    col_a, col_b, col_c, col_d = st.columns(4)
    col_a.metric("Jurisdição", current_data.get("jurisdicao_id") or "—")
    col_b.metric("Margem alvo", _fmt_faixa(margem_alvo))
    col_c.metric("Margem aceitável", _fmt_faixa(margem_ac))
    col_d.metric("Razão ind./direto", _fmt_faixa(razao))

    with st.expander("✏️ Editar parâmetros financeiros", expanded=False):
        st.caption("Altere os targets financeiros do perfil. Cada save cria uma nova versão auditável.")
        _render_perfil_fin_form(entity_id, current_data, margem_alvo, margem_ac, razao, base_url, actor)

    cats = current_data.get("categorias_indireto") or []
    if cats:
        rows = _build_cats_summary_rows(cats)
        with st.expander("Categorias de custo indireto (resumo)", expanded=False):
            if rows:
                st.dataframe(rows, hide_index=True, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════════════
# Seção de Temas Visuais (ADR-065)
# ═══════════════════════════════════════════════════════════════════════════


def _render_temas_section(base_url: str, actor: str) -> None:
    """Aba de gerenciamento de temas visuais (ADR-065)."""
    try:
        resp = api_call(method="GET", path="/api/temas", base_url=base_url, actor=actor)
        temas = resp.get("items") or []
    except Exception as exc:
        st.error(f"Não foi possível carregar temas: {exc}")
        return

    if not temas:
        st.info("Nenhum tema encontrado em `config/temas/`.")
        return

    ids = [t.get("id") for t in temas if t.get("id")]
    tmap = {t.get("id"): t for t in temas}

    selected = st.selectbox(
        "Tema",
        options=ids,
        key="tema-selected",
        format_func=lambda tid: f"{tmap[tid].get('empresa') or tid}  (atual: {tmap[tid].get('current_version', 'v1')})",
    )
    tema_data = tmap.get(selected) or {}
    current_fields = _pctx_get_tema_current_fields(tema_data)
    cores = current_fields.get("cores") or {}
    fontes = current_fields.get("fontes") or {}
    (
        empresa,
        perfil_exibicao,
        picked_colors,
        fonte_cab,
        fonte_corpo,
        tam_titulo,
        tam_cab,
        tam_corpo,
        motivo,
        submitted,
    ) = _pctx_render_tema_form(tema_id, current_fields, cores, fontes)
    if submitted:
        if not motivo.strip():
            st.warning("Informe o motivo da alteração antes de salvar.")
            return
        new_fields = {
            **current_fields,
            "empresa": empresa,
            "perfil_exibicao": perfil_exibicao,
            "cores": {**cores, **picked_colors},
            "fontes": {
                **(fontes or {}),
                "cabecalho": fonte_cab,
                "corpo": fonte_corpo,
                "tamanho_titulo": tam_titulo,
                "tamanho_cabecalho": tam_cab,
                "tamanho_corpo": tam_corpo,
            },
        }
        try:
            api_call(
                method="POST",
                path=f"/api/temas/{tema_id}/versions",
                payload={"fields": new_fields, "motivo": motivo},
                base_url=base_url,
                actor=actor,
            )
            st.success(f"Nova versão do tema `{tema_id}` criada com sucesso!")
            st.rerun()
        except Exception as exc:
            st.error(f"Erro ao salvar: {exc}")
    _render_entity_card(current_fields, title="Resumo do tema ativo")


# ═══════════════════════════════════════════════════════════════════════════
# Secao de Jurisdicoes (ADR-066)
# ═══════════════════════════════════════════════════════════════════════════


def _render_jurisdicoes_section(base_url: str, actor: str) -> None:
    """Secao de gestao de overlays de jurisdicao (ADR-066)."""
    try:
        resp = api_call(method="GET", path="/api/jurisdicoes", base_url=base_url, actor=actor)
        jurisdicoes = resp.get("items") or []
    except Exception as exc:
        st.error(f"Nao foi possivel carregar jurisdicoes: {exc}")
        return

    if not jurisdicoes:
        st.info("Nenhuma jurisdicao encontrada em `config/jurisdicoes/`.")
        return

    ids = [j.get("id") for j in jurisdicoes if j.get("id")]
    jmap = {j.get("id"): j for j in jurisdicoes}

    selected = st.selectbox(
        "Jurisdicao",
        options=ids,
        key="jur-selected",
        format_func=lambda jid: f"{jmap[jid].get('nome') or jid}  (atual: {jmap[jid].get('current_version', 'v1')})",
    )
    jur_data = jmap.get(selected) or {}
    versions = jur_data.get("versions") or []

    tab_hist, tab_edit, tab_nova = st.tabs(["📜 Historico", "✏️ Editar overlay", "➕ Nova versao"])

    with tab_hist:
        _render_version_history(versions, jur_data.get("current_version", "v1"))

    with tab_edit:
        _render_jurisdicao_editor(base_url, actor, selected, jur_data)

    with tab_nova:
        _render_new_version_form(
            base_url=base_url,
            actor=actor,
            post_path=f"/api/jurisdicoes/{selected}/versions",
            entity_id=selected,
            versions=versions,
            key_prefix="jur",
        )


def _find_current_version_data(jur_data: dict) -> dict:
    versions = jur_data.get("versions") or []
    current_v = jur_data.get("current_version", "v1")
    current: dict = {}
    for v in reversed(versions):
        if v.get("version") == current_v:
            current = {k: vv for k, vv in v.items() if k not in ("version", "created_at", "created_by", "motivo")}
            break
    if not current:
        current = {k: vv for k, vv in jur_data.items() if k not in ("versions", "current_version")}
    return current


def _compute_provedor_badge(ref: str, today: date) -> str:  # type: ignore[name-defined]
    try:
        ano, mes = int(str(ref)[:4]), int(str(ref)[5:7])
        meses_atraso = (today.year - ano) * 12 + (today.month - mes)
        if meses_atraso <= 3:
            return "🟢 Vigente"
        if meses_atraso <= 6:
            return "🟡 Desatualizado"
        return "🔴 Desatualizado (+6 meses)"
    except Exception:
        return "⚪ Sem referência"


def _save_provedor_update(
    prov: dict,
    i: int,
    new_ref: str,
    provedores: list,
    jur_id: str,
    base_url: str,
    actor: str,
) -> None:
    updated_provs = list(provedores)
    updated_provs[i] = {**prov, "data_referencia": new_ref.strip()}
    try:
        api_call(
            method="POST",
            path=f"/api/jurisdicoes/{jur_id}/versions",
            payload={
                "motivo": f"Atualização de referência {prov.get('id', '?')} → {new_ref}",
                "provedores_referencia": updated_provs,
            },
            base_url=base_url,
            actor=actor,
        )
        st.success("Provedor atualizado — nova versão criada.")
        st.rerun()
    except Exception as exc:
        st.error(f"Erro: {exc}")


def _render_provedor_card(
    prov: dict,
    i: int,
    jur_id: str,
    provedores: list,
    base_url: str,
    actor: str,
    hoje: date,  # type: ignore[name-defined]
) -> None:
    base = prov.get("base") or "—"
    ref = prov.get("data_referencia") or ""
    url = prov.get("url_fonte") or ""
    badge = _compute_provedor_badge(ref, hoje)
    st.caption(badge)
    st.markdown(f"**{prov.get('id', '?')}** — {base}")
    st.caption(f"Referência: **{ref or '—'}**")
    if url:
        st.markdown(f"[🔗 Fonte]({url})", unsafe_allow_html=False)
    new_ref = st.text_input(
        "Atualizar data_referencia",
        value=ref,
        key=f"jur-prov-ref-{jur_id}-{i}",
        placeholder="AAAA-MM",
    )
    if st.button(f"Atualizar {prov.get('id', '?')}", key=f"jur-prov-save-{jur_id}-{i}", type="secondary"):
        _save_provedor_update(prov, i, new_ref, provedores, jur_id, base_url, actor)


def _render_provedores_section(provedores: list, jur_id: str, base_url: str, actor: str) -> None:
    if not provedores:
        return
    from datetime import date as _date

    _hoje = _date.today()
    st.markdown("**📡 Provedores de Referência**")
    prov_cols = st.columns(len(provedores))
    for i, prov in enumerate(provedores):
        if not isinstance(prov, dict):
            continue
        with prov_cols[i]:
            _render_provedor_card(prov, i, jur_id, provedores, base_url, actor, _hoje)
    st.divider()


def _render_overlay_expander(title: str, overlay: dict, row_key: str) -> None:
    if not overlay:
        return
    with st.expander(title, expanded=False):
        rows = [
            {row_key: key, **{k: str(v)[:40] for k, v in fields.items()}}
            for key, fields in overlay.items()
            if isinstance(fields, dict)
        ]
        if rows:
            st.dataframe(rows, hide_index=True, use_container_width=True)


def _render_jurisdicao_editor(base_url: str, actor: str, jur_id: str, jur_data: dict) -> None:
    """Editor de overlay de jurisdicao — CPUs e insumos regionais."""
    st.caption(
        "Defina precos ou produtividades especificos desta jurisdicao. "
        "Campos aqui sobrepõem o catalogo mestre para projetos nesta regiao."
    )

    current = _find_current_version_data(jur_data)
    cpus_overlay = current.get("cpus") or {}
    insumos_overlay = current.get("insumos") or {}
    provedores = current.get("provedores_referencia") or []

    _render_provedores_section(provedores, jur_id, base_url, actor)

    col1, col2 = st.columns(2)
    col1.metric("CPUs com override", len(cpus_overlay))
    col2.metric("Insumos com override", len(insumos_overlay))

    _render_overlay_expander("CPUs com override nesta jurisdicao", cpus_overlay, "CPU")
    _render_overlay_expander("Insumos com override nesta jurisdicao", insumos_overlay, "Insumo")

    st.divider()
    st.caption("Para criar um novo overlay, use a aba ➕ Nova versao acima.")
