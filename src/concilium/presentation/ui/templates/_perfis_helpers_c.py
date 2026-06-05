# ruff: noqa: E402,F401,F404
"""Private helpers for perfis_contextos_page — Part C.

Página de gestão de Perfis e Contextos — ADR-062.

Perfis e Contextos compartilham a mesma lógica de versionamento
(ConfigVersionService). Esta página expõe o histórico, comparação e
criação de novas versões para ambas as entidades.
"""

from __future__ import annotations

import sys
from datetime import date
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

from ._perfis_helpers_a import _render_entity_card, _render_new_version_form, _render_version_history

# ═══════════════════════════════════════════════════════════════════════════
# Página principal
# ═══════════════════════════════════════════════════════════════════════════


def _render_tema_editor(base_url: str, actor: str, tema_id: str, tema_data: dict) -> None:
    """Formulário tipado para edição de TemaVisual (ADR-064/065)."""
    st.caption(
        "Edite os campos abaixo. Ao salvar, uma nova versão é criada automaticamente. "
        "Cores usam o seletor de cor — hex 6 dígitos sem '#' armazenado."
    )

    versions = tema_data.get("versions") or []
    current_v = tema_data.get("current_version", "v1")
    current_fields: dict = {}
    for v in reversed(versions):
        if v.get("version") == current_v:
            current_fields = {
                k: vv for k, vv in v.items() if k not in ("version", "created_at", "created_by", "motivo")
            }
            break
    if not current_fields:
        current_fields = {k: vv for k, vv in tema_data.items() if k not in ("versions", "current_version")}

    cores = current_fields.get("cores") or {}
    fontes = current_fields.get("fontes") or {}

    def _hex(val: str | None) -> str:
        h = str(val or "FFFFFF").lstrip("#").upper()
        return f"#{h if len(h) == 6 else 'FFFFFF'}"

    with st.form(f"tema-edit-form-{tema_id}"):
        # ── Identidade ──────────────────────────────────────────────────
        col_emp, col_perf = st.columns(2)
        empresa = col_emp.text_input(
            "Nome da empresa",
            value=str(current_fields.get("empresa") or ""),
            key=f"tema-empresa-{tema_id}",
            placeholder="Ex: MendesLobo Construtora",
        )
        perfil_opts = ["EXECUTIVO", "SIMPLES", "TECNICO"]
        cur_perf = str(current_fields.get("perfil_exibicao") or "SIMPLES")
        perfil_exibicao = col_perf.selectbox(
            "Perfil de exibição",
            options=perfil_opts,
            index=perfil_opts.index(cur_perf) if cur_perf in perfil_opts else 0,
            key=f"tema-perfil-{tema_id}",
            help="Controla densidade e nível de detalhe dos artefatos",
        )

        # ── 🎨 Cores (3 colunas) ────────────────────────────────────────
        st.markdown("**🎨 Cores**")
        _color_defs = [
            ("cabecalho_fundo", "Cabeçalho — fundo"),
            ("cabecalho_texto", "Cabeçalho — texto"),
            ("destaque", "Destaque"),
            ("zebra_impar", "Zebra — linha ímpar"),
            ("borda", "Bordas"),
        ]
        color_cols = st.columns(3)
        picked_colors: dict[str, str] = {}
        for i, (key_c, label_c) in enumerate(_color_defs):
            picked = color_cols[i % 3].color_picker(
                label_c,
                value=_hex(cores.get(key_c)),
                key=f"tema-cor-{key_c}-{tema_id}",
            )
            picked_colors[key_c] = picked.lstrip("#").upper()

        st.divider()

        # ── 🔤 Tipografia ────────────────────────────────────────────────
        st.markdown("**🔤 Tipografia**")
        font_opts = ["Arial", "Helvetica", "Calibri", "Times New Roman", "Courier"]
        fc_cur = str(fontes.get("cabecalho") or "Arial")
        fb_cur = str(fontes.get("corpo") or "Arial")
        typ_col1, typ_col2 = st.columns(2)
        fonte_cab = typ_col1.selectbox(
            "Fonte cabeçalho",
            options=font_opts,
            index=font_opts.index(fc_cur) if fc_cur in font_opts else 0,
            key=f"tema-fc-{tema_id}",
        )
        fonte_corpo = typ_col2.selectbox(
            "Fonte corpo",
            options=font_opts,
            index=font_opts.index(fb_cur) if fb_cur in font_opts else 0,
            key=f"tema-fb-{tema_id}",
        )
        siz_col1, siz_col2, siz_col3 = st.columns(3)
        tam_titulo = siz_col1.number_input(
            "Tamanho título (pt)",
            min_value=10,
            max_value=24,
            step=1,
            value=int(fontes.get("tamanho_titulo") or 16),
            key=f"tema-tt-{tema_id}",
        )
        tam_cab = siz_col2.number_input(
            "Tamanho cabeçalho (pt)",
            min_value=8,
            max_value=16,
            step=1,
            value=int(fontes.get("tamanho_cabecalho") or 12),
            key=f"tema-tc-{tema_id}",
        )
        tam_corpo = siz_col3.number_input(
            "Tamanho corpo (pt)",
            min_value=8,
            max_value=14,
            step=1,
            value=int(fontes.get("tamanho_corpo") or 10),
            key=f"tema-tb-{tema_id}",
        )

        st.divider()
        motivo = st.text_input(
            "Motivo da alteração", placeholder="Ex: Rebrand para cliente X", key=f"tema-motivo-{tema_id}"
        )
        submitted = st.form_submit_button("💾 Salvar como nova versão", type="primary", use_container_width=True)

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

    with st.expander("➕ Nova versão", expanded=False):
        _render_new_version_form(
            base_url=base_url,
            actor=actor,
            post_path=f"/api/jurisdicoes/{selected}/versions",
            entity_id=selected,
            versions=versions,
            key_prefix="jur",
        )

    tab_detail, tab_hist, tab_edit = st.tabs(["🔍 Detalhe", "📜 Histórico", "✏️ Editar overlay"])

    with tab_detail:
        _render_jurisdicao_detail(jur_data, versions)

    with tab_hist:
        _render_version_history(versions, jur_data.get("current_version", "v1"))

    with tab_edit:
        _render_jurisdicao_editor(base_url, actor, selected, jur_data)


def _render_jurisdicao_detail(jur_data: dict, versions: list[dict]) -> None:
    current_v = jur_data.get("current_version", "v1")
    current_data = next((v for v in versions if v.get("version") == current_v), jur_data)

    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Código", current_data.get("codigo") or jur_data.get("id") or "—")
    col_b.metric("Nome", current_data.get("nome") or "—")
    col_c.metric("Versão ativa", current_data.get("version") or current_v)

    provedores = current_data.get("provedores_referencia") or []
    if provedores:
        st.caption("Provedores de referência")
        st.dataframe(
            [
                {
                    "ID": p.get("id") or "—",
                    "Base": p.get("base") or "—",
                    "Referência": p.get("data_referencia") or "—",
                }
                for p in provedores
                if isinstance(p, dict)
            ],
            hide_index=True,
            use_container_width=True,
        )

    st.caption(
        "Origem da versão ativa: "
        f"{current_data.get('version') or current_v} · "
        f"{str(current_data.get('created_at') or '—')[:19].replace('T', ' ')} · "
        f"{current_data.get('created_by') or '—'}"
    )
    if current_data.get("motivo"):
        st.caption(f"Motivo: {current_data.get('motivo')}")


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
