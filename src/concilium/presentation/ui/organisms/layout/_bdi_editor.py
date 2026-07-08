"""Camada de apresentação — layout Streamlit (parte extraída de layout.py)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import streamlit as st

if TYPE_CHECKING:
    from collections.abc import Callable

    from concilium.domain.models.financial.bdi import (
        ComponentesBdi,
        TabelaBdi,
        TaxRegimeVersion,
        TaxSimulationScenario,
    )

from ...helpers.helpers import (
    extract_bdi_dict,
    extract_skill_base_inputs,
)
from ...infra.api import api_call


def _fetch_s07_categorias_config(base_url: str, project_id: str, actor: str) -> list:
    """Busca a lista categorias_config salva no override da skill 06, ou [] em qualquer falha/formato inesperado."""
    try:
        ov = api_call(method="GET", path=f"/api/projects/{project_id}/overrides", base_url=base_url, actor=actor)
    except Exception:
        return []
    s07 = ov.get("06-resultado-financeiro") if isinstance(ov, dict) else None
    if not isinstance(s07, dict):
        return []
    cats = s07.get("categorias_config") or []
    return cats if isinstance(cats, list) else []


def _mob_fallback_custo(cat: dict) -> dict:
    """Constrói o fallback de custo fixo total para a categoria MOB."""
    return {"custo_fixo_total": float(cat.get("custo_fixo_total") or cat.get("custo_total") or 0.0)}


def _consolidated_custo_verba(cat: dict) -> list:
    """Fallback de verba única de custo consolidado quando a categoria não tem mão de obra/equipamentos/verbas."""
    total_month = float(cat.get("custo_fixo_mensal") or 0.0)
    if total_month > 0:
        return [{"descricao": "custo consolidado", "valor_mensal": total_month}]
    return []


def _equipe_fallback_from_categoria(cat: dict) -> dict:
    """Extrai mão de obra/equipamentos/verbas de uma categoria de override, com fallback de custo consolidado."""
    mo = ((cat.get("mao_de_obra") or {}).get("itens") or []) if isinstance(cat.get("mao_de_obra"), dict) else []
    equips = cat.get("equipamentos") or []
    verbas = cat.get("verbas_mensais") or []
    if not mo and not equips and not verbas:
        verbas = _consolidated_custo_verba(cat)
    return {"mao_obra": mo, "equipamentos": equips, "verbas_mensais": verbas}


def _hydrate_indiretos_from_overrides(base_url: str, project_id: str, actor: str) -> tuple[dict, dict]:
    """Fallback: use saved skill 07 overrides when benchmark reference has no indirect baseline."""
    cats = _fetch_s07_categorias_config(base_url, project_id, actor)
    equipes_fallback: dict[str, dict] = {}
    ind_det_fallback: dict[str, dict] = {}
    for cat in cats:
        if not isinstance(cat, dict):
            continue
        cid = str(cat.get("categoria") or "").upper().strip()
        if not cid:
            continue
        if cid == "MOB":
            ind_det_fallback["MOB"] = _mob_fallback_custo(cat)
            continue
        equipes_fallback[cid] = {"categoria": cid, **_equipe_fallback_from_categoria(cat)}
    return equipes_fallback, ind_det_fallback


def _bdi_tcu_cv(saved_comp: dict, key: str, dom_val: float) -> float:
    """Returns component value from saved or default, scaled to percentage."""
    return float(saved_comp.get(key, dom_val)) * 100


def _compute_bdi_from_tabela(tabela_bdi: dict, bdi_base: dict) -> None:
    """Computes BDI values from tabela_bdi components into bdi_base in-place."""
    for cat, comps in tabela_bdi.items():
        if not isinstance(comps, dict) or "ac" not in comps:
            continue
        ac = float(comps.get("ac", 0))
        df_ = float(comps.get("df", 0))
        r_ = float(comps.get("r", 0))
        cr_ = float(comps.get("cr", 0))
        l_ = float(comps.get("l") or comps.get("lucro") or 0)
        t_ = sum(float(comps.get(k, 0)) for k in ("cofins", "iss", "pis", "cssl", "ir"))
        bdi_val = ((1 + ac + df_ + r_ + cr_ + l_) / (1 - t_) - 1) if t_ < 1 else 0.0
        bdi_base[cat] = round(bdi_val, 6)
    if "equipamentos" not in bdi_base:
        # ADR-023 §D3 revisado: bucket equipamentos = locação (SV-31/STF: sem ISS) → taxa de material
        bdi_base["equipamentos"] = bdi_base.get("material", 0.0)


def _render_tcu_cat_expander(
    cat: str, cat_label: str, dom_comp: ComponentesBdi, saved_comp: dict, project_id: str, tcu_edited: dict
) -> None:
    """Renders the TCU decomposition expander for one BDI category."""
    with st.expander(cat_label, expanded=False):
        st.markdown("**Overhead (numerador)**")
        oh_c1, oh_c2, oh_c3, oh_c4, oh_c5 = st.columns(5)
        ac_v = (
            oh_c1.number_input(
                "AC %",
                0.0,
                20.0,
                _bdi_tcu_cv(saved_comp, "ac", dom_comp.ac),
                step=0.1,
                key=f"tcu-{project_id}-{cat}-ac",
            )
            / 100
        )  # type: ignore[union-attr]
        df_v = (
            oh_c2.number_input(
                "DF %",
                0.0,
                10.0,
                _bdi_tcu_cv(saved_comp, "df", dom_comp.df),
                step=0.1,
                key=f"tcu-{project_id}-{cat}-df",
            )
            / 100
        )  # type: ignore[union-attr]
        r_v = (
            oh_c3.number_input(
                "R %", 0.0, 10.0, _bdi_tcu_cv(saved_comp, "r", dom_comp.r), step=0.1, key=f"tcu-{project_id}-{cat}-r"
            )
            / 100
        )  # type: ignore[union-attr]
        cr_v = (
            oh_c4.number_input(
                "CR %",
                0.0,
                10.0,
                _bdi_tcu_cv(saved_comp, "cr", dom_comp.cr),
                step=0.1,
                key=f"tcu-{project_id}-{cat}-cr",
            )
            / 100
        )  # type: ignore[union-attr]
        l_v = (
            oh_c5.number_input(
                "L %", 0.0, 30.0, _bdi_tcu_cv(saved_comp, "l", dom_comp.l), step=0.1, key=f"tcu-{project_id}-{cat}-l"
            )
            / 100
        )  # type: ignore[union-attr]
        st.markdown("**Tributos (denominador)**")
        tr_c1, tr_c2, tr_c3, tr_c4, tr_c5 = st.columns(5)
        cofins_v = (
            tr_c1.number_input(
                "COFINS %",
                0.0,
                10.0,
                _bdi_tcu_cv(saved_comp, "cofins", dom_comp.cofins),
                step=0.1,
                key=f"tcu-{project_id}-{cat}-cofins",
            )
            / 100
        )  # type: ignore[union-attr]
        iss_v = (
            tr_c2.number_input(
                "ISS %",
                0.0,
                10.0,
                _bdi_tcu_cv(saved_comp, "iss", dom_comp.iss),
                step=0.1,
                key=f"tcu-{project_id}-{cat}-iss",
            )
            / 100
        )  # type: ignore[union-attr]
        pis_v = (
            tr_c3.number_input(
                "PIS %",
                0.0,
                5.0,
                _bdi_tcu_cv(saved_comp, "pis", dom_comp.pis),
                step=0.05,
                key=f"tcu-{project_id}-{cat}-pis",
            )
            / 100
        )  # type: ignore[union-attr]
        cssl_v = (
            tr_c4.number_input(
                "CSLL %",
                0.0,
                5.0,
                _bdi_tcu_cv(saved_comp, "cssl", dom_comp.cssl),
                step=0.1,
                key=f"tcu-{project_id}-{cat}-cssl",
            )
            / 100
        )  # type: ignore[union-attr]
        ir_v = (
            tr_c5.number_input(
                "IR %", 0.0, 5.0, _bdi_tcu_cv(saved_comp, "ir", dom_comp.ir), step=0.1, key=f"tcu-{project_id}-{cat}-ir"
            )
            / 100
        )  # type: ignore[union-attr]
        t_total = cofins_v + iss_v + pis_v + cssl_v + ir_v
        oh_total = ac_v + df_v + r_v + cr_v + l_v
        bdi_calc = (1 + oh_total) / (1 - t_total) - 1 if t_total < 1 else 0.0
        st.metric(f"BDI {cat_label}", f"{bdi_calc * 100:.2f}%", help="Calculado em tempo real pela fórmula TCU")
        tcu_edited[cat] = {
            "ac": ac_v,
            "df": df_v,
            "r": r_v,
            "cr": cr_v,
            "l": l_v,
            "cofins": cofins_v,
            "iss": iss_v,
            "pis": pis_v,
            "cssl": cssl_v,
            "ir": ir_v,
        }


def _resolve_bdi_pre_reforma_defaults(
    reference: dict, current: dict, skill06_current: dict, DEFAULT_BDI_TABELA: TabelaBdi
) -> tuple[dict, list[str]]:
    """Resolves bdi_defaults and bdi_keys for pre-reforma editor."""
    skill06_base = extract_skill_base_inputs(reference, "06-resultado-financeiro")
    skill08_base = extract_skill_base_inputs(reference, "06-resultado-financeiro")
    skill08_current = (
        current.get("06-resultado-financeiro", {}) if isinstance(current.get("06-resultado-financeiro"), dict) else {}
    )
    bdi_base = extract_bdi_dict(skill06_base) or extract_bdi_dict(skill08_base)
    if not bdi_base:
        tabela_bdi = skill06_base.get("tabela_bdi") or {}
        if tabela_bdi and isinstance(tabela_bdi, dict):
            _compute_bdi_from_tabela(tabela_bdi, bdi_base)
    bdi_cur = extract_bdi_dict(skill06_current) or extract_bdi_dict(skill08_current)
    bdi_keys_l = ["mao_obra", "equipamentos", "material", "diesel", "indireto"]
    _dft = {
        "mao_obra": float(DEFAULT_BDI_TABELA.mao_obra.bdi_total),
        "equipamentos": float(DEFAULT_BDI_TABELA.servicos.bdi_total),
        "material": float(DEFAULT_BDI_TABELA.material.bdi_total),
        "diesel": float(DEFAULT_BDI_TABELA.diesel.bdi_total),
        "indireto": float(DEFAULT_BDI_TABELA.indireto.bdi_total),
    }
    bdi_defaults = {k: float(bdi_cur.get(k, bdi_base.get(k, _dft.get(k, 0.0)))) for k in bdi_keys_l}
    return bdi_defaults, bdi_keys_l


def _render_bdi_simple_save(project_id: str, edited_bdi: dict, bdi_keys: list, base_url: str, actor: str) -> None:
    """Handles saving the simplified BDI values."""
    api_call(
        method="POST",
        path=f"/api/projects/{project_id}/overrides",
        base_url=base_url,
        payload={
            "skill_id": "06-resultado-financeiro",
            "inputs": {"bdi_aplicado": {k: edited_bdi[k] for k in bdi_keys if k != "indireto"}},
        },
        actor=actor,
    )
    api_call(
        method="POST",
        path=f"/api/projects/{project_id}/overrides",
        base_url=base_url,
        payload={"skill_id": "06-resultado-financeiro", "inputs": {"bdi_aplicado": edited_bdi}},
        actor=actor,
    )
    st.success("BDI salvo.")


def _render_tcu_expander_section(
    project_id: str,
    skill06_current: dict,
    tcu_cats: list,
    tcu_labels: dict,
    dom_map: dict,
    base_url: str,
    actor: str,
) -> None:
    """Renders the TCU decomposition expander section."""
    saved_tabela = skill06_current.get("tabela_bdi") or {}
    with st.expander("▶ Ver decomposição TCU por categoria", expanded=False):
        st.caption(
            "Edite os componentes individuais (AC, DF, R, CR, L, tributos). "
            "O BDI total é recalculado pela fórmula TCU: `(1 + AC + DF + R + CR + L) / (1 − T) − 1`."
        )
        tcu_edited: dict[str, dict] = {}
        for cat in tcu_cats:
            _render_tcu_cat_expander(
                cat, tcu_labels[cat], dom_map[cat], saved_tabela.get(cat) or {}, project_id, tcu_edited
            )
        if st.button("Salvar decomposição TCU", key=f"save-tcu-{project_id}", type="primary", use_container_width=True):
            api_call(
                method="POST",
                path=f"/api/projects/{project_id}/overrides",
                base_url=base_url,
                payload={"skill_id": "06-resultado-financeiro", "inputs": {"tabela_bdi": tcu_edited}},
                actor=actor,
            )
            st.success("Decomposição TCU salva. Recalcule o BDI total com 'Salvar BDI' acima.")


def _render_bdi_pre_reforma(
    project_id: str,
    reference: dict,
    current: dict,
    skill06_current: dict,
    base_url: str,
    actor: str,
    DEFAULT_BDI_TABELA: TabelaBdi,
) -> None:
    """Renders the pre-reforma BDI editor section."""
    st.caption("Modo legado — edite os fatores BDI diretamente. Ex.: 0.35 = 35%.")
    bdi_defaults, bdi_keys_l = _resolve_bdi_pre_reforma_defaults(
        reference, current, skill06_current, DEFAULT_BDI_TABELA
    )
    st.dataframe(
        [
            {"categoria": k, "fator": round(bdi_defaults[k], 4), "percentual": f"{bdi_defaults[k] * 100:.2f}%"}
            for k in bdi_keys_l
        ],
        width="stretch",
        hide_index=True,
    )
    c1, c2, c3, c4, c5 = st.columns(5)
    edited_bdi = {
        "mao_obra": c1.number_input(
            "MO", min_value=0.0, max_value=5.0, value=bdi_defaults["mao_obra"], step=0.01, key=f"bdi-mo-{project_id}"
        ),
        "equipamentos": c2.number_input(
            "Equip.",
            min_value=0.0,
            max_value=5.0,
            value=bdi_defaults["equipamentos"],
            step=0.01,
            key=f"bdi-eq-{project_id}",
        ),
        "material": c3.number_input(
            "Material",
            min_value=0.0,
            max_value=5.0,
            value=bdi_defaults["material"],
            step=0.01,
            key=f"bdi-mat-{project_id}",
        ),
        "diesel": c4.number_input(
            "Diesel", min_value=0.0, max_value=5.0, value=bdi_defaults["diesel"], step=0.01, key=f"bdi-dsl-{project_id}"
        ),
        "indireto": c5.number_input(
            "Indireto",
            min_value=0.0,
            max_value=5.0,
            value=bdi_defaults["indireto"],
            step=0.01,
            key=f"bdi-ind-{project_id}",
        ),
    }
    if st.button("Salvar BDI", key=f"save-bdi-{project_id}", use_container_width=True, type="primary"):
        _render_bdi_simple_save(project_id, edited_bdi, bdi_keys_l, base_url, actor)
    _tcu_cats = ["mao_obra", "equipamentos", "material", "diesel", "indireto"]
    _tcu_labels = {
        "mao_obra": "Mão de Obra",
        "equipamentos": "Equipamentos",
        "material": "Material",
        "diesel": "Diesel",
        "indireto": "Indireto",
    }
    _dom_map = {
        "mao_obra": DEFAULT_BDI_TABELA.mao_obra,
        "equipamentos": DEFAULT_BDI_TABELA.servicos,
        "material": DEFAULT_BDI_TABELA.material,
        "diesel": DEFAULT_BDI_TABELA.diesel,
        "indireto": DEFAULT_BDI_TABELA.indireto,
    }
    _render_tcu_expander_section(project_id, skill06_current, _tcu_cats, _tcu_labels, _dom_map, base_url, actor)


def _render_bdi_cbs_ibs(
    project_id: str,
    saved_tax_scenario: dict,
    selected_regime: TaxRegimeVersion,
    selected_regime_key: str,
    cenario_base: TaxSimulationScenario,
    default_bdi_tabela: TabelaBdi,
    resolver_bdi_cbs_ibs_fn: Callable[[TabelaBdi, TaxSimulationScenario], TabelaBdi],
    tax_sim_scenario_cls: type[TaxSimulationScenario],
    regime_labels: dict,
    base_url: str,
    actor: str,
) -> None:
    """Renders the CBS/IBS BDI editor section."""
    st.caption(
        "Modo CBS/IBS — defina as premissas de crédito por categoria. "
        "O BDI é derivado automaticamente pela fórmula TCU com T_efetivo = CBS_IBS×(1−ratio)+CSSL+IR."
    )
    if cenario_base.split_payment:
        st.info(
            "ℹ️ **Split payment** ativo neste regime — o tomador retém o imposto na fonte. "
            "Não altera o BDI, mas impacta o fluxo de caixa.",
            icon="💡",
        )

    def _f(key: str, default: float) -> float:
        return (
            float(saved_tax_scenario.get(key, default))
            if saved_tax_scenario.get("regime_version") == selected_regime_key
            else default
        )

    st.markdown("**Alíquota CBS+IBS combinada (bruta sobre o preço de venda)**")
    cbs_ibs_rate = (
        st.slider(
            "CBS+IBS combinado (%)",
            min_value=0.0,
            max_value=35.0,
            value=round(_f("cbs_ibs_combined_rate", cenario_base.cbs_ibs_combined_rate) * 100, 1),
            step=0.1,
            key=f"bdi-cbs-rate-{project_id}",
        )
        / 100.0
    )
    st.markdown("**Crédito recuperável por categoria (premissa do planejador)**")
    cr_col1, cr_col2, cr_col3, cr_col4 = st.columns(4)
    cr_mo = (
        cr_col1.number_input(
            "MO (%)",
            0.0,
            100.0,
            round(_f("credit_ratio_mao_obra", cenario_base.credit_ratio_mao_obra) * 100, 1),
            step=1.0,
            key=f"bdi-cr-mo-{project_id}",
        )
        / 100.0
    )
    cr_mat = (
        cr_col2.number_input(
            "Material (%)",
            0.0,
            100.0,
            round(_f("credit_ratio_material", cenario_base.credit_ratio_material) * 100, 1),
            step=1.0,
            key=f"bdi-cr-mat-{project_id}",
        )
        / 100.0
    )
    cr_srv = (
        cr_col3.number_input(
            "Serviços (%)",
            0.0,
            100.0,
            round(_f("credit_ratio_servicos", cenario_base.credit_ratio_servicos) * 100, 1),
            step=1.0,
            key=f"bdi-cr-srv-{project_id}",
        )
        / 100.0
    )
    cr_dsl = (
        cr_col4.number_input(
            "Diesel (%)",
            0.0,
            100.0,
            round(_f("credit_ratio_diesel", cenario_base.credit_ratio_diesel) * 100, 1),
            step=1.0,
            key=f"bdi-cr-dsl-{project_id}",
        )
        / 100.0
    )
    with st.expander("⚙️ Parâmetros avançados (lag e taxa financeira)", expanded=False):
        lag_col, taxa_col, sp_col = st.columns(3)
        lag = int(
            lag_col.number_input(
                "Lag recuperação (sem.)",
                0,
                26,
                int(_f("credit_lag_semanas", cenario_base.credit_lag_semanas)),
                step=1,
                key=f"bdi-lag-{project_id}",
            )
        )
        taxa = (
            taxa_col.number_input(
                "Taxa financ. anual (%)",
                0.0,
                50.0,
                round(_f("taxa_financ_anual", cenario_base.taxa_financ_anual) * 100, 1),
                step=0.5,
                key=f"bdi-taxa-{project_id}",
            )
            / 100.0
        )
        sp = sp_col.checkbox(
            "Split payment",
            value=bool(saved_tax_scenario.get("split_payment", cenario_base.split_payment)),
            key=f"bdi-sp-{project_id}",
        )
        cssl = float(saved_tax_scenario.get("cssl_rate", cenario_base.cssl_rate))
        ir = float(saved_tax_scenario.get("ir_rate", cenario_base.ir_rate))
    scenario_preview = tax_sim_scenario_cls(
        regime_version=selected_regime,
        cbs_ibs_combined_rate=cbs_ibs_rate,
        credit_ratio_mao_obra=cr_mo,
        credit_ratio_material=cr_mat,
        credit_ratio_servicos=cr_srv,
        credit_ratio_diesel=cr_dsl,
        credit_lag_semanas=lag,
        taxa_financ_anual=taxa,
        split_payment=sp,
        cssl_rate=cssl,
        ir_rate=ir,
    )
    tabela_preview = resolver_bdi_cbs_ibs_fn(default_bdi_tabela, scenario_preview)
    t_ef = scenario_preview.tributos_efetivos_por_categoria()
    preview_rows = [
        {
            "Categoria": cat,
            "T_bruto (%)": f"{cbs_ibs_rate * 100:.1f}%",
            "Crédito (%)": f"{ratio * 100:.0f}%",
            "T_efetivo (%)": f"{t_ef[cat2] * 100:.2f}%",
            "BDI derivado (%)": f"{getattr(tabela_preview, cat2).bdi_total * 100:.2f}%",
        }
        for cat, ratio, cat2 in [
            ("Mão de Obra", cr_mo, "mao_obra"),
            ("Material", cr_mat, "material"),
            ("Serviços/Equip.", cr_srv, "servicos"),
            ("Diesel", cr_dsl, "diesel"),
            ("Indireto", cr_srv, "indireto"),
        ]
    ]
    st.markdown("**BDI derivado — fórmula TCU Ac. 2622/2013**")
    st.caption(
        "**T_bruto**: alíquota CBS+IBS sobre o preço de venda. **Crédito (%)**: fração recuperável. "
        "**T_efetivo**: carga líquida após crédito + CSSL + IR."
        " **BDI**: markup total = (1 + overhead) / (1 − T_efetivo) − 1."
    )
    st.dataframe(preview_rows, width="stretch", hide_index=True)
    if st.button("Salvar cenário CBS/IBS", key=f"save-tax-scenario-{project_id}", type="primary"):
        payload_ts = scenario_preview.to_dict()
        for skill_id in ["06-resultado-financeiro"]:
            api_call(
                method="POST",
                path=f"/api/projects/{project_id}/overrides",
                base_url=base_url,
                payload={"skill_id": skill_id, "inputs": {"tax_scenario": payload_ts}},
                actor=actor,
            )
        st.success(f"Cenário {regime_labels[selected_regime_key]} salvo nos skills 06 e 08.")


def render_bdi_editor(base_url: str, project_id: str, actor: str, reference: dict) -> None:
    """Editor de BDI — Modo Legado (PRE_REFORMA) ou CBS/IBS (ADR-055)."""
    from concilium.domain.models.financial.bdi import (
        CENARIOS_TRIBUTARIOS,
        DEFAULT_BDI_TABELA,
        TaxRegimeVersion,
        TaxSimulationScenario,
        resolver_bdi_cbs_ibs,
    )

    try:
        current = api_call(method="GET", path=f"/api/projects/{project_id}/overrides", base_url=base_url, actor=actor)
    except Exception:
        current = {}
    skill06_current = (
        current.get("06-resultado-financeiro", {}) if isinstance(current.get("06-resultado-financeiro"), dict) else {}
    )
    saved_tax_scenario: dict = skill06_current.get("tax_scenario", {}) if isinstance(skill06_current, dict) else {}
    REGIME_LABELS = {
        "pre_reforma": "Pré-Reforma (PIS/COFINS/ISS vigente)",
        "transicao": "Transição 2026–2032 (CBS/IBS parcial)",
        "pleno_cbs_ibs": "Pleno CBS/IBS (2033+ / cenário prospectivo)",
    }
    regime_keys = list(REGIME_LABELS.keys())
    current_regime_val = saved_tax_scenario.get("regime_version", "pre_reforma")
    default_idx = regime_keys.index(current_regime_val) if current_regime_val in regime_keys else 0
    selected_regime_key = st.selectbox(
        "Regime tributário",
        options=regime_keys,
        format_func=lambda k: REGIME_LABELS[k],
        index=default_idx,
        key=f"bdi-regime-{project_id}",
    )
    selected_regime = TaxRegimeVersion(selected_regime_key)
    if selected_regime == TaxRegimeVersion.PRE_REFORMA:
        _render_bdi_pre_reforma(project_id, reference, current, skill06_current, base_url, actor, DEFAULT_BDI_TABELA)
        return
    cenario_base = CENARIOS_TRIBUTARIOS[selected_regime]
    _render_bdi_cbs_ibs(
        project_id,
        saved_tax_scenario,
        selected_regime,
        selected_regime_key,
        cenario_base,
        DEFAULT_BDI_TABELA,
        resolver_bdi_cbs_ibs,
        TaxSimulationScenario,
        REGIME_LABELS,
        base_url,
        actor,
    )


