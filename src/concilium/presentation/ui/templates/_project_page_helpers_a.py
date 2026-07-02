"""Helpers extracted from project_page.py.

Atomic design templates - Full page layouts.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

try:
    from ..infra.api import api_call
except ImportError:
    src_root = Path(__file__).resolve().parents[4]
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))
    from concilium.presentation.ui.infra.api import api_call


def _deserialize_diagnostico(data: dict | None):
    """Reconstrói DiagnosticoPERelatorio a partir do dict da API."""
    if not data:
        return None
    try:
        from concilium.domain.models.analytics.diagnostico_pe import DiagnosticoPEItem, DiagnosticoPERelatorio, FatorPE

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
        from concilium.domain.models.financial.backtracking_pe import (
            BacktrackingPEItem,
            BacktrackingPERelatorio,
            SolucaoInversa,
        )

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


def _build_prod_map(catalog_snap: dict) -> dict:
    return {p["id"]: p for p in (catalog_snap.get("produtividades") or []) if isinstance(p, dict) and "id" in p}


def _build_raw_cpus(catalog_snap: dict) -> list:
    return [c for c in (catalog_snap.get("cpus") or []) if isinstance(c, dict) and c.get("codigo")]


def _enrich_cpu_with_prod(c: dict, prod_map: dict) -> dict:
    ref = c.get("producao_id_ref")
    prod = prod_map.get(ref) if ref else None
    if prod and not c.get("equipe"):
        equipe = prod.get("equipe")
        if not isinstance(equipe, dict):
            equipe = prod.get("composicao_padrao_equipe")
        if isinstance(equipe, dict):
            return {**c, "equipe": equipe}
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


def _cpu_has_composition(cpu_data: dict) -> bool:
    if not isinstance(cpu_data, dict):
        return False
    equipe = cpu_data.get("equipe") or {}
    composicao = cpu_data.get("composicao_itens") or cpu_data.get("composicao_completa") or []
    return bool(equipe.get("funcoes") or equipe.get("equipamentos") or composicao)


def _fetch_cpu_details(project_id: str, cpu_id: str, base_url: str, actor: str) -> dict:
    try:
        payload = api_call(
            method="GET",
            path=f"/api/projects/{project_id}/catalog/cpus/{cpu_id}",
            base_url=base_url,
            actor=actor,
        )
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _resolve_cpu_data(
    cpu_id: str,
    cpu_map: dict,
    cpu_cache: dict[str, dict],
    project_id: str,
    base_url: str,
    actor: str,
) -> dict:
    base_data = cpu_map.get(cpu_id) or {}
    if _cpu_has_composition(base_data):
        return base_data
    if cpu_id in cpu_cache:
        merged = dict(base_data)
        merged.update(cpu_cache[cpu_id])
        return merged
    fetched = _fetch_cpu_details(project_id, cpu_id, base_url, actor)
    cpu_cache[cpu_id] = fetched
    merged = dict(base_data)
    merged.update(fetched)
    return merged


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
    # Descrição: preferência para o campo da EAP, fallback para CPU
    descricao_item = item.get("descricao") or ""
    descricao_cpu = cpu_data.get("descricao") or cpu_data.get("nome") or ""
    if descricao_item:
        st.caption(f"**{descricao_item}**")
    elif descricao_cpu:
        st.caption(f"*CPU — {descricao_cpu}*")
    observacao = item.get("observacao") or item.get("nota") or ""
    if observacao:
        st.caption(f"📝 {observacao}")
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


def _render_eap_item_expander(
    item: dict,
    cpu_map: dict,
    cpu_cache: dict[str, dict],
    project_id: str,
    base_url: str,
    actor: str,
) -> None:
    cpu_id = item.get("cpu_id", "—")
    qtd = item.get("quantitativo", "—")
    unidade = item.get("unidade", "")
    descricao = item.get("descricao") or cpu_id
    item_id = item.get("item_id", "?")
    label = f"📌 **{item_id}** — {descricao[:60]}  ·  {qtd} {unidade}"
    cpu_data = _resolve_cpu_data(cpu_id, cpu_map, cpu_cache, project_id, base_url, actor)
    with st.expander(label, expanded=False):
        _render_eap_item_body(item, cpu_data, qtd, unidade)


def _render_eap_section(reference: dict, base_url: str, project_id: str, actor: str) -> None:
    st.caption(
        "Versões já executadas preservam o canonical completo do momento do run. "
        "Re-executar com nova EAP produzirá resultados diferentes. "
        "**Recomendação:** crie um novo projeto para mudanças estruturais de escopo."
    )
    eap_items = (reference.get("cpus") or {}).get("itens_eap", [])
    cpu_map = _build_project_cpu_map(reference)
    cpu_cache: dict[str, dict] = {}
    if eap_items:
        st.caption(f"**{len(eap_items)}** atividade(s)")
        for item in eap_items:
            _render_eap_item_expander(item, cpu_map, cpu_cache, project_id, base_url, actor)
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
