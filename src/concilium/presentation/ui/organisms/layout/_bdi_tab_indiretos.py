"""Streamlit UI layer for indirect costs (BDI) editor with category breakdown.

Provides interactive UI for team composition (ADM/TOP/LAB/QSMS) and mobilization (MOB)
cost configuration. Renders labor/equipment/allowances tables with live cost totals,
supports regime-based overhead calculation, and persists overrides via skill 06 endpoint.

Key responsibilities:
  - Load reference state from benchmark-reference API (equipes, detalhamento, encargos)
  - Render category-specific editor tabs (Equipe de Apoio, MOB/desmob)
  - Support nested labor (funcoes + equipment + verbas) with regime-based rates
  - Fallback to saved overrides if reference empty (hydration pattern)
  - Persist edited configuration to project overrides (skill_id: 06-resultado-financeiro)

Used by: project page, layout.py expanders, BDI configuration workflow.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import streamlit as st

if TYPE_CHECKING:
    from streamlit.delta_generator import DeltaGenerator


from ...infra.api import api_call
from ._bdi_editor import _hydrate_indiretos_from_overrides, render_bdi_editor


def render_bdi_tab(base_url: str, project: dict, actor: str) -> None:
    """Render isolated BDI editor for use in standalone expander or tab.

    Fetches benchmark-reference from API and delegates to render_bdi_editor.
    """
    project_id = project["project_id"]
    try:
        reference = api_call(
            method="GET",
            path=f"/api/projects/{project_id}/benchmark-reference",
            base_url=base_url,
            actor=actor,
        )
    except Exception:
        reference = {}
    render_bdi_editor(base_url, project_id, actor, reference)


_INDIR_REGIMES = ["PJ", "CLT-mensalista", "CLT-horista"]


_INDIR_PERM_CATS = [
    ("ADM", "Administração central (ADM)"),
    ("TOP", "Topografia (TOP)"),
    ("LAB", "Laboratório (LAB)"),
    ("QSMS", "Qualidade, Segurança, Meio Ambiente e Saúde (QSMS)"),
]


def _verbas_from_dict(raw: dict) -> list[tuple[str, float]]:
    """Extract verbas (allowances) from dict mapping name -> value.

    Filters fields starting with '_' and non-numeric values.
    """
    return [(k, float(v)) for k, v in raw.items() if not str(k).startswith("_") and isinstance(v, (int, float))]


def _verbas_from_list_items(raw: list) -> list[tuple[str, float]]:
    """Extract verbas from list of dicts or numeric items.

    Handles both dict (with descricao/nome/valor_mensal keys) and bare numbers.
    """
    result: list[tuple[str, float]] = []
    for item in raw:
        if isinstance(item, dict):
            result.append((item.get("descricao") or item.get("nome") or "—", float(item.get("valor_mensal") or 0)))
        elif isinstance(item, (int, float)):
            result.append(("—", float(item)))
    return result


def _indir_verbas_list(raw: object) -> list[tuple[str, float]]:
    """Normalize verbas_mensais (dict or list format) to [(descricao, valor)]."""
    if isinstance(raw, dict):
        return _verbas_from_dict(raw)
    if isinstance(raw, list):
        return _verbas_from_list_items(raw)
    return []


def _indir_equips_list(raw: object) -> list[dict]:
    """Normalize equipamentos (list or dict format) to list[dict].

    Handles list of dicts directly, or dict with (tipo -> value/dict) entries.
    """
    if isinstance(raw, list):
        return [e for e in raw if isinstance(e, dict)]
    if isinstance(raw, dict):
        result: list[dict] = []
        for k, v in raw.items():
            if str(k).startswith("_"):
                continue
            if isinstance(v, dict):
                result.append({"tipo": k, **v})
            else:
                valor = v if isinstance(v, (int, float)) else 0
                result.append({"tipo": k, "aluguel_mensal": float(valor)})
        return result
    return []


def _render_indir_mo_section(
    mo_pessoas: list, encargos: dict, regimes: list, project_id: str, cat_id: str
) -> tuple[float, list[dict]]:
    """Render labor table for one indirect category. Returns (total_mo, itens_mo).

    Creates editable DataFrame with salary, regime, encargos, and cost calculations.
    Computes custo_unitario = salario × (1 + encargos), custo_mensal = custo_unitario × qty.
    """
    import pandas as pd

    total_mo = 0.0
    itens_mo: list[dict] = []
    if not mo_pessoas:
        st.info(f"Sem dados de mão de obra para {cat_id}.")
        return total_mo, itens_mo
    df_rows = []
    for p in mo_pessoas:
        regime = p.get("tipo_contratacao", "PJ") if p.get("tipo_contratacao") in regimes else "PJ"
        enc = encargos.get(regime, 0.0)
        sal = float(p.get("salario_base", 0))
        qtd = int(p.get("quantidade", 1))
        c_unit = sal * (1 + enc)
        df_rows.append(
            {
                "Função": p.get("funcao", "—"),
                "Qtd": qtd,
                "Salário Base (R$)": sal,
                "Regime": regime,
                "Encargos": f"{enc * 100:.0f}%",
                "Custo Unit. (R$)": round(c_unit, 2),
                "Custo Mensal (R$)": round(c_unit * qtd, 2),
            }
        )
    edited_mo = st.data_editor(
        pd.DataFrame(df_rows),
        column_config={
            "Função": st.column_config.TextColumn(width="large"),
            "Qtd": st.column_config.NumberColumn(min_value=0, max_value=999, step=1, width="small"),
            "Salário Base (R$)": st.column_config.NumberColumn(min_value=0.0, format="%.2f"),
            "Regime": st.column_config.SelectboxColumn(options=regimes, width="medium"),
            "Encargos": st.column_config.TextColumn(disabled=True, width="small"),
            "Custo Unit. (R$)": st.column_config.NumberColumn(disabled=True, format="%.2f"),
            "Custo Mensal (R$)": st.column_config.NumberColumn(disabled=True, format="%.2f"),
        },
        hide_index=True,
        use_container_width=True,
        key=f"indir-mo-{project_id}-{cat_id}",
        num_rows="dynamic",
    )
    for _, row in edited_mo.iterrows():
        enc = encargos.get(str(row["Regime"]), 0.0)
        c_unit = float(row["Salário Base (R$)"]) * (1 + enc)
        c_mensal = c_unit * int(row["Qtd"])
        total_mo += c_mensal
        itens_mo.append(
            {
                "funcao": row["Função"],
                "quantidade": int(row["Qtd"]),
                "salario_base": float(row["Salário Base (R$)"]),
                "tipo_contratacao": str(row["Regime"]),
                "encargos_pct": enc,
                "custo_unitario": round(c_unit, 2),
                "custo_mensal": round(c_mensal, 2),
            }
        )
    return total_mo, itens_mo


def _build_eq_seed_list(equips: list) -> list[dict]:
    """Build seed DataFrame rows for equipment editor."""
    return [
        {
            "Tipo": e.get("tipo") or e.get("descricao") or "",
            "Qtd": int(e.get("quantidade") or 1),
            "Aluguel Unit. (R$/mês)": float(
                e.get("aluguel_mensal") or e.get("valor_mensal") or e.get("custo_mensal") or 0
            ),
        }
        for e in equips
    ]


def _process_eq_edited_rows(edited_list: list) -> tuple[float, list[dict]]:
    """Process edited equipment rows. Returns (total_eq, equips_out).

    Filters empty Tipo entries and computes total_mes_e = aluguel_u × qtd per item.
    """
    total_eq = 0.0
    equips_out: list[dict] = []
    for row in edited_list:
        tipo = str(row.get("Tipo") or "").strip()
        if not tipo:
            continue
        aluguel_u = float(row.get("Aluguel Unit. (R$/mês)") or 0)
        qtd_e = int(row.get("Qtd") or 1)
        total_mes_e = aluguel_u * qtd_e
        total_eq += total_mes_e
        equips_out.append({"tipo": tipo, "quantidade": qtd_e, "aluguel_mensal": aluguel_u, "custo_mensal": total_mes_e})
    return total_eq, equips_out


def _render_indir_equips_section(equips: list, project_id: str, cat_id: str) -> tuple[float, list[dict]]:
    """Render equipment table for one indirect category. Returns (total_eq, equips_out)."""
    st.caption("**Equipamentos**")
    edited_eq = st.data_editor(
        _build_eq_seed_list(equips),
        column_config={
            "Tipo": st.column_config.TextColumn(width="large"),
            "Qtd": st.column_config.NumberColumn(min_value=0, max_value=999, step=1, width="small"),
            "Aluguel Unit. (R$/mês)": st.column_config.NumberColumn(min_value=0.0, format="%.2f"),
        },
        num_rows="dynamic",
        hide_index=True,
        use_container_width=True,
        key=f"indir-eq-{project_id}-{cat_id}",
    )
    edited_list = (
        edited_eq
        if isinstance(edited_eq, list)
        else (edited_eq.to_dict("records") if hasattr(edited_eq, "to_dict") else [])
    )
    return _process_eq_edited_rows(edited_list)


def _render_indir_verbas_section(verbas: list, project_id: str, cat_id: str) -> tuple[float, list[dict]]:
    """Render allowances table for one indirect category. Returns (total_verbas, verbas_out)."""
    st.caption("**Verbas mensais**")
    verbas_seed = [{"Descrição": n, "R$/mês": v} for n, v in verbas]
    edited_verbas = st.data_editor(
        verbas_seed,
        column_config={
            "Descrição": st.column_config.TextColumn(width="large"),
            "R$/mês": st.column_config.NumberColumn(min_value=0.0, format="%.2f"),
        },
        num_rows="dynamic",
        hide_index=True,
        use_container_width=True,
        key=f"indir-verbas-{project_id}-{cat_id}",
    )
    edited_list = (
        edited_verbas
        if isinstance(edited_verbas, list)
        else (edited_verbas.to_dict("records") if hasattr(edited_verbas, "to_dict") else [])
    )
    total_verbas = 0.0
    verbas_out: list[dict] = []
    for row in edited_list:
        desc = str(row.get("Descrição") or "").strip()
        val = float(row.get("R$/mês") or 0)
        if desc:
            total_verbas += val
            verbas_out.append({"descricao": desc, "valor_mensal": val})
    return total_verbas, verbas_out


def _render_indir_cat_equipe(
    cat_id: str, cat_label: str, equipes: dict, encargos: dict, regimes: list, project_id: str
) -> tuple[dict, float]:
    """Render one indirect support category (ADM/TOP/LAB/QSMS) with sub-tabs.

    Returns (entry dict with categoria/driver/costs, total_monthly).
    """
    eq = equipes.get(cat_id) or {}
    mo_pessoas = eq.get("mao_obra") or []
    equips = _indir_equips_list(eq.get("equipamentos"))
    verbas = _indir_verbas_list(eq.get("verbas_mensais"))
    with st.expander(cat_label, expanded=False):
        total_mo, itens_mo = _render_indir_mo_section(mo_pessoas, encargos, regimes, project_id, cat_id)
        total_eq, equips_out = _render_indir_equips_section(equips, project_id, cat_id)
        total_verbas, verbas_out = _render_indir_verbas_section(verbas, project_id, cat_id)
        total_cat = total_mo + total_eq + total_verbas
        st.metric(f"Total {cat_id}/mês", f"R$ {total_cat:,.0f}")
    entry: dict = {"categoria": cat_id, "driver": "permanencia", "custo_fixo_mensal": round(total_cat, 2)}
    if itens_mo:
        entry["mao_de_obra"] = {"nome": f"MO {cat_id}", "custo_fixo_mensal": round(total_mo, 2), "itens": itens_mo}
    if equips_out:
        entry["equipamentos"] = equips_out
    if verbas_out:
        entry["verbas_mensais"] = verbas_out
    return entry, total_cat


def _render_indir_mob_section(equipes: dict, ind_det: dict, project_id: str) -> dict:
    """Render MOB/DESMOB (mobilization) tab with transport and personnel lowering costs.

    Returns entry dict with categoria=MOB, driver=one_time, custo_fixo_total.
    """
    eq = equipes.get("MOB") or {}
    det = ind_det.get("MOB") or {}
    custo_mob_ref = float(eq.get("custo_total") or det.get("custo_fixo_total") or 0)
    st.caption("Informe os custos de transporte de equipamentos e baixadas de pessoal.")
    col_t, col_b = st.columns(2)
    with col_t:
        st.caption("Transporte de Equipamentos")
        n_veic = st.number_input(
            "Nº de carretas/bi-trens",
            min_value=0,
            step=1,
            value=int(custo_mob_ref / 15000 / 2) or 1,
            key=f"mob-veic-{project_id}",
        )
        custo_por_viagem = st.number_input(
            "Custo por viagem (R$)",
            min_value=0.0,
            step=1000.0,
            value=15000.0,
            format="%.2f",
            key=f"mob-viag-{project_id}",
        )
        n_viagens = st.number_input(
            "Viagens por veículo (ida + volta)", min_value=1, step=1, value=2, key=f"mob-nv-{project_id}"
        )
        custo_transporte = n_veic * custo_por_viagem * n_viagens
    with col_b:
        st.caption("Baixada de Pessoal")
        n_pessoas = st.number_input(
            "Nº de pessoas",
            min_value=0,
            step=1,
            value=int(custo_mob_ref * 0.3 / 2500) or 1,
            key=f"mob-pes-{project_id}",
        )
        custo_por_pessoa = st.number_input(
            "Custo por pessoa (R$)", min_value=0.0, step=100.0, value=2500.0, format="%.2f", key=f"mob-cpp-{project_id}"
        )
        custo_baixada = n_pessoas * custo_por_pessoa
    total_mob = custo_transporte + custo_baixada
    st.metric(
        "Total MOB/DESMOB", f"R$ {total_mob:,.2f}", delta=f"Ref: R$ {custo_mob_ref:,.2f}" if custo_mob_ref else None
    )
    return {"categoria": "MOB", "driver": "one_time", "custo_fixo_total": total_mob}


def _fill_indir_totals_placeholder(placeholder: DeltaGenerator, totals_by_cat: dict) -> None:
    """Update metrics bar at top with totals per category, or empty if empty dict."""
    if totals_by_cat:
        with placeholder.container():
            cols_t = st.columns(len(totals_by_cat))
            for col_t, (cat_id_t, total_t) in zip(cols_t, totals_by_cat.items(), strict=False):
                col_t.metric(f"Total {cat_id_t}/mês", f"R$ {total_t:,.0f}")
            st.divider()
    else:
        placeholder.empty()


def _fallback_indiretos_from_overrides_if_empty(
    equipes: dict, ind_det: dict, base_url: str, project_id: str, actor: str
) -> tuple[dict, dict]:
    """If equipes/detalhamento empty, try hydrating from saved overrides (skill 07)."""
    if equipes or ind_det:
        return equipes, ind_det
    equipes_fb, ind_det_fb = _hydrate_indiretos_from_overrides(base_url, project_id, actor)
    if equipes_fb or ind_det_fb:
        st.caption("Base de indiretos carregada de overrides salvos (skill 07).")
        return equipes_fb, ind_det_fb
    return equipes, ind_det


def _load_indiretos_reference_state(base_url: str, project_id: str, actor: str) -> tuple[dict, dict, dict[str, float]]:
    """Load indirect costs reference state from benchmark-reference API.

    Returns: (equipes_indexed_by_cat, indiretos_detalhamento, encargos_by_regime).
    Includes fallback to overrides if reference empty.
    """
    try:
        reference = api_call(
            method="GET", path=f"/api/projects/{project_id}/benchmark-reference", base_url=base_url, actor=actor
        )
    except Exception:
        reference = {}
    equipes = {str(e.get("categoria", "")).upper(): e for e in (reference.get("equipes_indiretas") or [])}
    ind_det = reference.get("indiretos_detalhamento") or {}
    equipes, ind_det = _fallback_indiretos_from_overrides_if_empty(equipes, ind_det, base_url, project_id, actor)
    _enc_raw = reference.get("encargos_sociais") or {}
    encargos: dict[str, float] = {
        "PJ": float(_enc_raw.get("pj", 0.0)),
        "CLT-mensalista": float(_enc_raw.get("clt_mensalista", 0.92)),
        "CLT-horista": float(_enc_raw.get("clt_horista", 0.80)),
    }
    if _enc_raw:
        st.caption(
            f"Encargos da jurisdição: PJ={encargos['PJ'] * 100:.0f}% | "
            f"CLT-mensalista={encargos['CLT-mensalista'] * 100:.0f}% | "
            f"CLT-horista={encargos['CLT-horista'] * 100:.0f}%"
        )
    return equipes, ind_det, encargos


def _render_indir_equipe_tab(equipes: dict, encargos: dict[str, float], project_id: str) -> list[dict]:
    """Render Equipe de Apoio tab with all permanent categories (ADM/TOP/LAB/QSMS).

    Returns list of entry dicts ready for save.
    """
    st.caption(
        "Salário base: valor contratado. "
        "Custo unitário = salário × (1 + encargos). "
        "Custo mensal = custo unitário × quantidade."
    )
    _totals_placeholder = st.empty()
    totals_by_cat: dict[str, float] = {}
    entries: list[dict] = []
    for cat_id, cat_label in _INDIR_PERM_CATS:
        entry, total = _render_indir_cat_equipe(cat_id, cat_label, equipes, encargos, _INDIR_REGIMES, project_id)
        entries.append(entry)
        totals_by_cat[cat_id] = total
    _fill_indir_totals_placeholder(_totals_placeholder, totals_by_cat)
    return entries


def _save_indiretos_config(base_url: str, project_id: str, actor: str, cats_config_edited: list[dict]) -> None:
    """Render save button and persist indirect costs configuration to project overrides.

    Posts to /api/projects/{id}/overrides with skill_id=06-resultado-financeiro.
    """
    if not st.button(
        "Salvar custos indiretos", key=f"save-indir-{project_id}", use_container_width=True, type="primary"
    ):
        return
    try:
        api_call(
            method="POST",
            path=f"/api/projects/{project_id}/overrides",
            base_url=base_url,
            payload={"skill_id": "06-resultado-financeiro", "inputs": {"categorias_config": cats_config_edited}},
            actor=actor,
        )
        st.success("Salvo. Re-execute o pipeline para refletir as alterações.")
    except Exception as exc:
        st.error(f"Erro ao salvar: {exc}")


def render_indiretos_config(base_url: str, project_id: str, actor: str) -> None:
    """Render main indirect costs editor UI with Equipe de Apoio and MOB tabs.

    Integrates: reference loading, category tabs, save logic.
    """
    equipes, ind_det, encargos = _load_indiretos_reference_state(base_url, project_id, actor)
    tab_equipe, tab_mob = st.tabs(["👥 Equipe de Apoio", "🚛 Mobilização/desmobilização"])
    cats_config_edited: list[dict] = []
    with tab_equipe:
        cats_config_edited.extend(_render_indir_equipe_tab(equipes, encargos, project_id))
    with tab_mob:
        mob_entry = _render_indir_mob_section(equipes, ind_det, project_id)
        cats_config_edited.append(mob_entry)
    st.divider()
    _save_indiretos_config(base_url, project_id, actor, cats_config_edited)


