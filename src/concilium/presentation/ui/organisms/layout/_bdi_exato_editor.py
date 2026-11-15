"""Editor Streamlit da declaração exata de BDI do projeto (N9.1, #206).

É a única edição de BDI de projeto que o preço exato lê. Lê e grava pela API
(`/api/projects/{id}/bdi-exato`); os campos são texto e seguem para o servidor
como digitados — nada é convertido de/para ponto flutuante.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from ...helpers.bdi_exato import (
    ROW_LABELS,
    ROWS,
    TAX_MODE_LABELS,
    TAX_MODES,
    TAXES,
    build_save_request,
    current_version,
    form_from_declaration,
    layers_rows,
    profile_value,
    status_banner,
)
from ...infra.api import api_call

_BANNERS = {"success": st.success, "error": st.error, "info": st.info}


def _render_status(status: dict[str, Any]) -> None:
    level, text = status_banner(status)
    _BANNERS[level](text)
    registro = status.get("registro")
    if registro:
        st.markdown(
            f"**Versão** {registro['versao']} · **Confirmado por** {registro['confirmado_por']} · "
            f"**Data** {registro['confirmado_em']}  \n**Content hash** `{registro['content_hash']}`"
            + (f"  \n**Motivo da revisão** {registro['motivo_revisao']}" if registro.get("motivo_revisao") else "")
            + f"  \n**Fonte** {status['declaracao']['fonte']}"
        )
        st.markdown("**Campos declarados pelo projeto** (os demais são do perfil da construtora)")
        st.dataframe(status["campos_declarados"], width="stretch", hide_index=True)
    rows = layers_rows(status)
    if rows:
        st.markdown(f"**Camadas efetivas por categoria** — perfil `{status.get('perfil_id')}` fundido com o projeto")
        st.caption(
            "Valores exatos com a origem entre parênteses. A coluna “Markup ≈” é apenas uma aproximação "
            "decimal para leitura; o preço usa o valor exato."
        )
        st.dataframe(rows, width="stretch", hide_index=True)
    elif status.get("camadas_motivo"):
        st.caption(f"Camadas efetivas não exibidas: {status['camadas_motivo']}")
    legado = status.get("perfil_legado") or {}
    if legado.get("existe"):
        st.caption(
            f"Perfil legado em ponto flutuante (bdi/perfil_bdi.json v{legado.get('versao', '?')}): "
            "não é usado pelo preço exato e nunca é convertido."
        )


def _render_form(project_id: str, status: dict[str, Any], actor: str) -> tuple[bool, dict[str, Any], str, str]:
    """Desenha o formulário; devolve (enviado, formulário em texto, confirmado_por, motivo_revisao)."""
    form = form_from_declaration(status.get("declaracao"))
    versao = current_version(status)
    with st.form(f"bdi-exato-form-{project_id}"):
        st.caption(
            "Digite decimais ou frações exatas (ex.: 0.08, 1/12). Deixe em branco / “do perfil” para manter o "
            "valor do perfil da construtora. Overhead (AC, R+S+G, DF) e natureza são da empresa e não se editam aqui."
        )
        form["fonte"] = st.text_input(
            "Fonte da declaração (documento, lei municipal, negociação)",
            value=form["fonte"],
            key=f"bdi-exato-fonte-{project_id}",
        )
        for tab, row in zip(st.tabs([ROW_LABELS[row] for row in ROWS]), ROWS, strict=True):
            with tab:
                fields = form["linhas"][row]
                hint = profile_value(status, row, "l")
                fields["l"] = st.text_input(
                    "Lucro L (exato)",
                    value=fields["l"],
                    key=f"bdi-exato-{project_id}-{row}-l",
                    help=f"Valor efetivo atual: {hint}" if hint else None,
                )
                for tax in TAXES:
                    entry = fields["tributos"][tax]
                    mode_col, rate_col = st.columns([2, 1])
                    entry["modo"] = mode_col.selectbox(
                        tax.upper(),
                        options=list(TAX_MODES),
                        index=TAX_MODES.index(entry["modo"]),
                        format_func=lambda mode: TAX_MODE_LABELS[mode],
                        key=f"bdi-exato-{project_id}-{row}-{tax}-modo",
                    )
                    hint = profile_value(status, row, tax)
                    entry["aliquota"] = rate_col.text_input(
                        f"Alíquota {tax.upper()} (exata)",
                        value=entry["aliquota"],
                        key=f"bdi-exato-{project_id}-{row}-{tax}-aliquota",
                        help=f"Valor efetivo atual: {hint}" if hint else None,
                    )
        confirmado_por = st.text_input(
            "Confirmado por (obrigatório)",
            value="" if actor == "anonymous" else actor,
            key=f"bdi-exato-confirmado-{project_id}",
        )
        motivo = st.text_input(
            "Motivo da revisão" + (f" (obrigatório — versão atual: {versao})" if versao is not None else ""),
            value="",
            key=f"bdi-exato-motivo-{project_id}",
        )
        submitted = st.form_submit_button(
            "Salvar declaração exata" + (f" (v{versao + 1})" if versao is not None else " (v1)"), type="primary"
        )
    return submitted, form, confirmado_por, motivo


def render_bdi_exato(base_url: str, project_id: str, actor: str) -> None:
    """Estado da declaração exata, camadas efetivas e formulário de edição."""
    st.markdown("#### Declaração exata de BDI do projeto — usada pelo preço exato")
    try:
        status = api_call(method="GET", path=f"/api/projects/{project_id}/bdi-exato", base_url=base_url, actor=actor)
    except Exception as exc:
        st.error(f"Não foi possível ler a declaração exata de BDI: {exc}")
        return
    flash_key = f"bdi-exato-flash-{project_id}"
    if st.session_state.get(flash_key):
        st.success(st.session_state.pop(flash_key))
    _render_status(status)
    submitted, form, confirmado_por, motivo = _render_form(project_id, status, actor)
    if not submitted:
        return
    payload, refusal = build_save_request(
        form, confirmado_por=confirmado_por, motivo_revisao=motivo, versao_atual=current_version(status)
    )
    if payload is None:
        st.error(refusal)
        return
    try:
        saved = api_call(
            method="POST",
            path=f"/api/projects/{project_id}/bdi-exato",
            base_url=base_url,
            payload=payload,
            actor=actor,
        )
    except Exception as exc:
        st.error(f"Declaração exata não salva: {exc}")
        return
    st.session_state[flash_key] = (
        f"Declaração exata v{saved['salvo']['versao']} salva (hash {saved['salvo']['content_hash']})."
    )
    st.rerun()
