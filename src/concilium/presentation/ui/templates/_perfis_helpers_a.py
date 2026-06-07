# ruff: noqa: E402,F401,F404
"""Private helpers for perfis_contextos_page — Part A.

Página de gestão de Perfis e Contextos — ADR-062.

Perfis e Contextos compartilham a mesma lógica de versionamento
(ConfigVersionService). Esta página expõe o histórico, comparação e
criação de novas versões para ambas as entidades.
"""

from __future__ import annotations

import json
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
# Private helpers — entity card rendering
# ═══════════════════════════════════════════════════════════════════════════


def _vget(v: dict, key: str, default: str = "—") -> str:
    return str(v.get(key) or default)


def _is_display_key(k: str, v: Any) -> bool:
    return k not in _AUDIT_KEYS and k not in _SKIP_DISPLAY and not k.startswith("$") and v is not None


def _filter_display_keys(data: dict) -> dict:
    return {k: v for k, v in data.items() if _is_display_key(k, v)}


def _partition_display(display: dict) -> tuple[dict, dict]:
    scalars = {k: v for k, v in display.items() if not isinstance(v, (dict, list))}
    nested = {k: v for k, v in display.items() if isinstance(v, (dict, list))}
    return scalars, nested


def _render_scalar_fields(scalars: dict) -> None:
    cols = st.columns(min(3, len(scalars)))
    for i, (k, v) in enumerate(scalars.items()):
        label = k.replace("_", " ").title()
        cols[i % len(cols)].caption(label)
        cols[i % len(cols)].text(str(v)[:80])


def _render_nested_dict(k: str, v: dict) -> None:
    label = k.replace("_", " ").title()
    pairs = [f"**{fk}:** {fv}" for fk, fv in v.items() if fv is not None]
    if pairs:
        st.caption(label)
        st.markdown("  ".join(pairs[:6]))


def _render_one_nested_field(k: str, v: Any) -> None:
    if isinstance(v, dict) and v:
        _render_nested_dict(k, v)
    elif isinstance(v, list) and v:
        st.caption(f"{k.replace('_', ' ').title()} ({len(v)} itens)")


def _render_nested_fields(nested: dict) -> None:
    for k, v in nested.items():
        _render_one_nested_field(k, v)


# ═══════════════════════════════════════════════════════════════════════════
# Private helpers — version history rendering
# ═══════════════════════════════════════════════════════════════════════════


def _version_detail_keys(v: dict) -> dict:
    _SKIP = {"version", "created_at", "created_by", "motivo"}
    return {k: v[k] for k in v if k not in _SKIP and not k.startswith("$") and v[k] is not None}


def _render_version_detail_extras(v: dict) -> None:
    details = _version_detail_keys(v)
    if details:
        _render_entity_card(details)


def _render_version_details(v: dict) -> None:
    col_a, col_b, col_c = st.columns(3)
    col_a.caption("Criado em")
    col_a.write(_vget(v, "created_at")[:19].replace("T", " "))
    col_b.caption("Por")
    col_b.write(_vget(v, "created_by"))
    for field in ("catalogo_id", "jurisdicao_id", "perfil_id", "nome"):
        if v.get(field):
            col_c.caption(field)
            col_c.write(v[field])
            break
    st.caption(f"**Motivo:** {_vget(v, 'motivo')}")
    _render_version_detail_extras(v)


# ═══════════════════════════════════════════════════════════════════════════
# Private helpers — entity section rendering
# ═══════════════════════════════════════════════════════════════════════════


def _fetch_entities(base_url: str, actor: str, list_path: str, entity_label: str) -> list | None:
    try:
        resp = api_call(method="GET", path=list_path, base_url=base_url, actor=actor)
        return resp.get("items") or []
    except Exception as exc:
        st.error(f"Não foi possível carregar {entity_label.lower()}s: {exc}")
        return None


def _build_entity_map(entities: list) -> tuple[list, dict]:
    ids = [e.get("id") for e in entities if e.get("id")]
    emap = {e.get("id"): e for e in entities}
    return ids, emap


def _render_entity_tabs(
    base_url: str,
    actor: str,
    compare_path: str,
    selected: str,
    entity: dict,
    versions: list,
    key_prefix: str,
    extra_renderer: Any,
) -> None:
    if extra_renderer:
        tabs_labels = ["🔍 Detalhe", "📜 Histórico", "🔀 Comparar versões"]
    else:
        tabs_labels = ["📜 Histórico", "🔀 Comparar versões"]
    tabs = st.tabs(tabs_labels)
    if extra_renderer and len(tabs) > 2:
        with tabs[0]:
            extra_renderer(entity, versions, base_url=base_url, actor=actor)
        with tabs[1]:
            _render_version_history(versions, entity.get("current_version", "v1"))
        with tabs[2]:
            _render_version_compare(base_url, actor, compare_path, selected, versions, key_prefix)
    else:
        with tabs[0]:
            _render_version_history(versions, entity.get("current_version", "v1"))
        with tabs[1]:
            _render_version_compare(base_url, actor, compare_path, selected, versions, key_prefix)


# ═══════════════════════════════════════════════════════════════════════════
# Private helpers — new version form
# ═══════════════════════════════════════════════════════════════════════════


def _collect_config_fields(versions: list) -> dict:
    latest = versions[-1] if versions else {}
    return {
        k: latest.get(k) or ""
        for k in ("catalogo_id", "jurisdicao_id", "perfil_id", "referencia_id", "nome", "descricao")
        if k in latest
    }


def _render_config_field_inputs(config_fields: dict, key_prefix: str, entity_id: str) -> dict:
    edited: dict[str, Any] = {}
    if not config_fields:
        return edited
    cols = st.columns(min(3, len(config_fields)))
    for i, (field, current_val) in enumerate(config_fields.items()):
        val = cols[i % len(cols)].text_input(field, value=str(current_val or ""))
        if val.strip():
            edited[field] = val.strip()
    return edited


def _submit_new_version(
    base_url: str,
    actor: str,
    post_path: str,
    motivo: str,
    edited_fields: dict,
    make_current: bool,
) -> None:
    if not motivo.strip():
        st.error("O campo 'motivo' é obrigatório.")
        return
    payload: dict[str, Any] = {"motivo": motivo.strip(), **edited_fields}
    if not make_current:
        payload["_make_current"] = False
    try:
        result = api_call(method="POST", path=post_path, base_url=base_url, payload=payload, actor=actor)
        st.success(f"Versão **{result.get('version', '?')}** criada com sucesso.")
        st.rerun()
    except Exception as exc:
        st.error(f"Erro ao criar versão: {exc}")


# ═══════════════════════════════════════════════════════════════════════════
# Private helpers — version compare rendering
# ═══════════════════════════════════════════════════════════════════════════


def _display_changed_fields(changed: dict) -> None:
    st.markdown(f"**{len(changed)} campo(s) alterado(s)**")
    rows = [
        {"Campo": f, "De": _format_diff_value(d.get("de")), "Para": _format_diff_value(d.get("para"))}
        for f, d in changed.items()
    ]
    st.dataframe(rows, hide_index=True, use_container_width=True)


def _display_unchanged_fields(unchanged: list) -> None:
    if unchanged:
        st.caption(f"Campos inalterados: {', '.join(str(u) for u in unchanged)}")


def _display_diff_results(diff: dict) -> None:
    changed = diff.get("changed") or {}
    if changed:
        _display_changed_fields(changed)
    else:
        st.success("As versões são idênticas nos campos de configuração.")
    _display_unchanged_fields(diff.get("unchanged") or [])


def _fetch_and_display_diff(
    base_url: str,
    actor: str,
    compare_path: str,
    entity_id: str,
    vA: str,
    vB: str,
) -> None:
    try:
        diff = api_call(
            method="GET",
            path=compare_path,
            base_url=base_url,
            actor=actor,
            params={"id": entity_id, "vA": vA, "vB": vB},
        )
        _display_diff_results(diff)
    except Exception as exc:
        st.error(f"Erro ao comparar: {exc}")


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
    entities = _fetch_entities(base_url, actor, list_path, entity_label)
    if not entities:
        return
    ids, emap = _build_entity_map(entities)
    selected = st.selectbox(
        entity_label,
        options=ids,
        key=f"{key_prefix}-selected",
        format_func=lambda eid: f"{emap[eid].get('nome') or eid}  (atual: {emap[eid].get('current_version', 'v1')})",
    )
    entity = emap.get(selected, {})
    versions = entity.get("versions") or []
    with st.expander("➕ Nova versão", expanded=False):
        _render_new_version_form(base_url, actor, versions_path_tpl.format(id=selected), selected, versions, key_prefix)
    _render_entity_tabs(base_url, actor, compare_path, selected, entity, versions, key_prefix, extra_renderer)


def _render_version_history(versions: list[dict], current_v: str) -> None:
    if not versions:
        st.info("Nenhum histórico de versões disponível.")
        return
    st.caption(f"**{len(versions)}** versão(ões) · ativa: **{current_v}**")
    for v in reversed(versions):
        is_current = v.get("version") == current_v
        label = f"**{v.get('version')}**" + (" ← atual" if is_current else "")
        with st.expander(label, expanded=is_current):
            _render_version_details(v)


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
        _fetch_and_display_diff(base_url, actor, compare_path, entity_id, vA, vB)


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
    config_fields = _collect_config_fields(versions)
    with st.form(key=f"{key_prefix}-new-version-{entity_id}"):
        motivo = st.text_area(
            "Motivo da nova versão *",
            placeholder="Ex.: Atualização do catálogo para tabela de preços Q2/2026",
            help="Campo obrigatório — documenta a intenção para auditoria futura.",
        )
        edited_fields = _render_config_field_inputs(config_fields, key_prefix, entity_id)
        make_current = st.checkbox("Tornar esta a versão ativa", value=True)
        submitted = st.form_submit_button("Criar nova versão", use_container_width=True)
        if submitted:
            _submit_new_version(base_url, actor, post_path, motivo, edited_fields, make_current)


def _render_entity_card(data: dict, title: str = "Configuração", expanded: bool = False) -> None:
    """Painel resumido de campos de uma entidade — substitui st.json() bruto.

    Mostra campos escalares como métricas/texto, dicts aninhados como expanders,
    e ignora campos de auditoria e chaves internas.
    """
    display = _filter_display_keys(data)
    if not display:
        return
    scalars, nested = _partition_display(display)
    with st.expander(title, expanded=expanded):
        if scalars:
            _render_scalar_fields(scalars)
        _render_nested_fields(nested)


def _format_diff_value(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)
