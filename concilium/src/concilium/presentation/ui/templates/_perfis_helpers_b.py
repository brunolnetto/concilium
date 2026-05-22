# ruff: noqa: E402,F401,F404
"""Private helpers for perfis_contextos_page — Part B.

Página de gestão de Perfis e Contextos — ADR-062.

Perfis e Contextos compartilham a mesma lógica de versionamento
(ConfigVersionService). Esta página expõe o histórico, comparação e
criação de novas versões para ambas as entidades.
"""

from __future__ import annotations

import sys
from pathlib import Path

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

from ._perfis_helpers_a import _render_new_version_form, _render_version_history
from ._perfis_helpers_c import _render_tema_editor

# ═══════════════════════════════════════════════════════════════════════════
# Página principal
# ═══════════════════════════════════════════════════════════════════════════


def _render_perfil_detail(entity: dict, versions: list[dict], base_url: str = "", actor: str = "") -> None:
    """Detalhe do perfil: metas financeiras, editor tipado, categorias de indireto."""
    current_v = entity.get("current_version", "v1")
    entity_id = entity.get("id", "")
    current_data = next((v for v in versions if v.get("version") == current_v), entity)

    # ── Resumo rápido ──────────────────────────────────────────────────────
    col_a, col_b, col_c, col_d = st.columns(4)
    col_a.metric("Jurisdição", current_data.get("jurisdicao_id") or "—")
    margem_alvo = current_data.get("faixa_margem_alvo") or {}
    col_b.metric(
        "Margem alvo",
        f"{margem_alvo.get('min', 0) * 100:.0f}% – {margem_alvo.get('max', 0) * 100:.0f}%" if margem_alvo else "—",
    )
    margem_ac = current_data.get("faixa_margem_aceitavel") or {}
    col_c.metric(
        "Margem aceitável",
        f"{margem_ac.get('min', 0) * 100:.0f}% – {margem_ac.get('max', 0) * 100:.0f}%" if margem_ac else "—",
    )
    razao = current_data.get("razao_indireto_direto_alvo") or {}
    col_d.metric(
        "Razão ind./direto",
        f"{razao.get('min', 0) * 100:.0f}% – {razao.get('max', 0) * 100:.0f}%" if razao else "—",
    )

    # ── Editor de parâmetros financeiros ───────────────────────────────────
    with st.expander("✏️ Editar parâmetros financeiros", expanded=False):
        st.caption("Altere os targets financeiros do perfil. Cada save cria uma nova versão auditável.")
        perfil_id = entity_id
        versions_path = f"/api/perfis/{perfil_id}/versions"

        def _pct(faixa: dict, key: str, default: float) -> float:
            return float((faixa or {}).get(key, default)) * 100

        with st.form(f"perfil-fin-form-{perfil_id}"):
            st.markdown("**Margem alvo**")
            c1, c2 = st.columns(2)
            ma_min = c1.number_input(
                "Mínimo (%)",
                min_value=0.0,
                max_value=100.0,
                step=0.5,
                value=_pct(margem_alvo, "min", 0.15),
                key=f"pfin-ma-min-{perfil_id}",
            )
            ma_max = c2.number_input(
                "Máximo (%)",
                min_value=0.0,
                max_value=100.0,
                step=0.5,
                value=_pct(margem_alvo, "max", 0.25),
                key=f"pfin-ma-max-{perfil_id}",
            )

            st.markdown("**Margem aceitável**")
            c3, c4 = st.columns(2)
            mac_min = c3.number_input(
                "Mínimo (%)",
                min_value=0.0,
                max_value=100.0,
                step=0.5,
                value=_pct(margem_ac, "min", 0.08),
                key=f"pfin-mac-min-{perfil_id}",
            )
            mac_max = c4.number_input(
                "Máximo (%)",
                min_value=0.0,
                max_value=100.0,
                step=0.5,
                value=_pct(margem_ac, "max", 0.30),
                key=f"pfin-mac-max-{perfil_id}",
            )

            st.markdown("**Razão indireto / direto alvo**")
            c5, c6 = st.columns(2)
            raz_min = c5.number_input(
                "Mínimo (%)",
                min_value=0.0,
                max_value=200.0,
                step=0.5,
                value=_pct(razao, "min", 0.20),
                key=f"pfin-raz-min-{perfil_id}",
            )
            raz_max = c6.number_input(
                "Máximo (%)",
                min_value=0.0,
                max_value=200.0,
                step=0.5,
                value=_pct(razao, "max", 0.40),
                key=f"pfin-raz-max-{perfil_id}",
            )

            st.markdown("**Categorias de custo indireto**")
            cats_raw = current_data.get("categorias_indireto") or []
            cats_seed = [
                {
                    "Código": c.get("codigo", ""),
                    "Descrição": c.get("descricao", ""),
                    "Driver": c.get("driver") or (c.get("regra_dimensionamento") or {}).get("tipo") or "permanencia",
                }
                for c in cats_raw
                if isinstance(c, dict)
            ]
            edited_cats = st.data_editor(
                cats_seed,
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
                key=f"pfin-cats-{perfil_id}",
            )

            motivo = st.text_input(
                "Motivo da alteração *", placeholder="Ex: Ajuste de targets Q2/2026", key=f"pfin-motivo-{perfil_id}"
            )
            submitted = st.form_submit_button("💾 Salvar como nova versão", type="primary", use_container_width=True)

        if submitted and base_url:
            if not motivo.strip():
                st.warning("Informe o motivo antes de salvar.")
            else:
                cats_list = (
                    edited_cats
                    if isinstance(edited_cats, list)
                    else (edited_cats.to_dict("records") if hasattr(edited_cats, "to_dict") else [])
                )
                new_cats = [
                    {
                        "codigo": r.get("Código", ""),
                        "descricao": r.get("Descrição", ""),
                        "driver": r.get("Driver", "permanencia"),
                    }
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
                    result = api_call(
                        method="POST", path=versions_path, payload=payload, base_url=base_url, actor=actor
                    )
                    st.success(f"Versão **{result.get('version', '?')}** criada com sucesso.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Erro ao salvar: {exc}")

    # ── Categorias resumo (somente leitura quando editor está fechado) ─────
    cats = current_data.get("categorias_indireto") or []
    if cats:
        with st.expander("Categorias de custo indireto (resumo)", expanded=False):
            rows = [
                {
                    "Código": c.get("codigo") or "—",
                    "Descrição": c.get("descricao") or "—",
                    "Driver": c.get("driver") or (c.get("regra_dimensionamento") or {}).get("tipo") or "—",
                }
                for c in cats
                if isinstance(c, dict)
            ]
            if rows:
                st.dataframe(rows, hide_index=True, use_container_width=True)


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
    versions = tema_data.get("versions") or []

    tab_hist, tab_edit, tab_nova = st.tabs(["📜 Histórico", "✏️ Editar tema", "➕ Nova versão"])

    with tab_hist:
        _render_version_history(versions, tema_data.get("current_version", "v1"))

    with tab_edit:
        _render_tema_editor(base_url, actor, selected, tema_data)

    with tab_nova:
        _render_new_version_form(
            base_url=base_url,
            actor=actor,
            post_path=f"/api/temas/{selected}/versions",
            entity_id=selected,
            versions=versions,
            key_prefix="tema",
        )
