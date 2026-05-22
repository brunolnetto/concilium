# ruff: noqa: E402,F401,F404
"""Private helpers for perfis_contextos_page — Part A.

Página de gestão de Perfis e Contextos — ADR-062.

Perfis e Contextos compartilham a mesma lógica de versionamento
(ConfigVersionService). Esta página expõe o histórico, comparação e
criação de novas versões para ambas as entidades.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_AUDIT_KEYS = {"version", "created_at", "created_by", "motivo", "$comment"}
_SKIP_DISPLAY = {"_make_current"}

import streamlit as st

try:
    from ..config import DEFAULT_ACTOR, DEFAULT_BASE_URL
    from ..infra.api import api_call
    from ..molecules.common import render_page_heading
except ImportError:
    src_root = Path(__file__).resolve().parents[4]
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))
    from concilium.presentation.ui.infra.api import api_call


# ═══════════════════════════════════════════════════════════════════════════
# Página principal
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


def _render_entity_card(data: dict, title: str = "Configuração", expanded: bool = False) -> None:
    """Painel resumido de campos de uma entidade — substitui st.json() bruto.

    Mostra campos escalares como métricas/texto, dicts aninhados como expanders,
    e ignora campos de auditoria e chaves internas.
    """
    display = {
        k: v
        for k, v in data.items()
        if k not in _AUDIT_KEYS and k not in _SKIP_DISPLAY and not k.startswith("$") and v is not None
    }
    if not display:
        return

    scalars = {k: v for k, v in display.items() if not isinstance(v, (dict, list))}
    nested = {k: v for k, v in display.items() if isinstance(v, (dict, list))}

    with st.expander(title, expanded=expanded):
        if scalars:
            cols = st.columns(min(3, len(scalars)))
            for i, (k, v) in enumerate(scalars.items()):
                label = k.replace("_", " ").title()
                cols[i % len(cols)].caption(label)
                cols[i % len(cols)].text(str(v)[:80])

        for k, v in nested.items():
            if isinstance(v, dict) and v:
                label = k.replace("_", " ").title()
                pairs = [f"**{fk}:** {fv}" for fk, fv in v.items() if fv is not None]
                if pairs:
                    st.caption(label)
                    st.markdown("  ".join(pairs[:6]))
            elif isinstance(v, list) and v:
                st.caption(f"{k.replace('_', ' ').title()} ({len(v)} itens)")
