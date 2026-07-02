"""Helpers extracted from project_page.py.

Atomic design templates - Full page layouts.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import Any

import streamlit as st

try:
    from ..atoms.form_contracts import CPU_EDITABLE_FIELDS, CPU_READONLY_FIELDS, render_typed_form
    from ..infra.api import api_call
    from ..organisms.layout import render_saved_override
except ImportError:
    src_root = Path(__file__).resolve().parents[4]
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))
    from concilium.presentation.ui.atoms.form_contracts import (
        CPU_EDITABLE_FIELDS,
        CPU_READONLY_FIELDS,
        render_typed_form,
    )
    from concilium.presentation.ui.infra.api import api_call
    from concilium.presentation.ui.organisms.layout import render_saved_override



def _render_project_cpu_editor(
    base_url: str,
    project_id: str,
    actor: str,
    cpu_id: str,
    cpu_data: dict,
    label: str = "Editar CPU",
) -> None:
    """Editor de override de CPU no projeto (restaurado do project_page.py original)."""
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


def _render_project_catalog_section(base_url: str, project_id: str, actor: str) -> None:
    """Seção de catálogo do projeto focada em overrides salvos."""
    st.caption(
        "Visualize as customizações de CPU já aplicadas neste projeto. "
        "As edições detalhadas permanecem no Painel de Planejamento."
    )
    render_saved_override(base_url, project_id, actor)


_VALID_COST_CATS = {"MAO_OBRA", "MATERIAL", "EQUIPAMENTO", "DIESEL", "SERVICO"}


def _pcat_extract_eap_rows(reference: dict[str, Any]) -> list[dict[str, Any]]:
    cpus_block = reference.get("cpus")
    if isinstance(cpus_block, dict):
        items = cpus_block.get("itens_eap")
        if isinstance(items, list):
            return [it for it in items if isinstance(it, dict)]
    eap = reference.get("eap")
    if isinstance(eap, list):
        return [it for it in eap if isinstance(it, dict)]
    return []


def _pcat_cpus_used_in_eap(reference: dict[str, Any]) -> set[str]:
    used: set[str] = set()
    for it in _pcat_extract_eap_rows(reference):
        cpu_id = str(it.get("cpu_id") or "").strip()
        if cpu_id:
            used.add(cpu_id)
    return used


def _pcat_insumo_index(reference: dict[str, Any]) -> dict[str, dict[str, Any]]:
    cat = reference.get("catalog") or {}
    raw = cat.get("insumos") or []
    out: dict[str, dict[str, Any]] = {}
    for row in raw:
        if not isinstance(row, dict):
            continue
        code = str(row.get("codigo") or row.get("id") or "").strip()
        if code:
            out[code] = row
    return out


def _pcat_catalog_cpus_index(reference: dict[str, Any]) -> dict[str, dict[str, Any]]:
    cat = reference.get("catalog") or {}
    out: dict[str, dict[str, Any]] = {}
    for cpu in cat.get("cpus") or []:
        if isinstance(cpu, dict):
            code = str(cpu.get("codigo") or "").strip()
            if code:
                out[code] = cpu
    return out


def _pcat_parse_ref_yyyy_mm(text: str) -> tuple[int, int] | None:
    s = (text or "").strip()
    if len(s) < 7 or s[4] != "-":
        return None
    try:
        y = int(s[:4])
        m = int(s[5:7])
        if m < 1 or m > 12:
            return None
        return y, m
    except Exception:
        return None


def _pcat_is_price_reference_stale(ref: str, max_age_months: int = 6) -> bool:
    parsed = _pcat_parse_ref_yyyy_mm(ref)
    if parsed is None:
        return True
    y, m = parsed
    today = date.today()
    age = (today.year - y) * 12 + (today.month - m)
    return age > max_age_months


def _pcat_cpu_parts(cpu: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    equipe = cpu.get("equipe")
    if not isinstance(equipe, dict):
        equipe = cpu.get("composicao_padrao_equipe") if isinstance(cpu.get("composicao_padrao_equipe"), dict) else {}
    funcoes = [f for f in (equipe.get("funcoes") or []) if isinstance(f, dict)]
    equips = [e for e in (equipe.get("equipamentos") or []) if isinstance(e, dict)]
    comp = [c for c in (cpu.get("composicao_itens") or cpu.get("composicao_completa") or []) if isinstance(c, dict)]
    return funcoes, equips, comp


def _pcat_has_complete_composition(cpu: dict[str, Any]) -> bool:
    funcoes, equips, comp = _pcat_cpu_parts(cpu)
    return bool(funcoes or equips or comp)


def _pcat_cpu_diff_flags(base_cpu: dict[str, Any], ov_cpu: dict[str, Any]) -> dict[str, bool]:
    out = {"producao": False, "equipe": False, "composicao": False}
    if not ov_cpu:
        return out
    base_prod = float(base_cpu.get("producao_horaria") or 0.0)
    ov_prod = float(ov_cpu.get("producao_horaria") or base_prod)
    out["producao"] = abs(base_prod - ov_prod) > 1e-9

    base_fun, base_eq, base_comp = _pcat_cpu_parts(base_cpu)
    ov_fun, ov_eq, ov_comp = _pcat_cpu_parts(ov_cpu)
    out["equipe"] = bool(ov_fun or ov_eq) and ((ov_fun != base_fun) or (ov_eq != base_eq))
    out["composicao"] = bool(ov_comp) and (ov_comp != base_comp)
    return out


def _pcat_override_badge(base_cpu: dict[str, Any], ov_cpu: dict[str, Any]) -> str:
    if not ov_cpu:
        return "Sem override"
    flags = _pcat_cpu_diff_flags(base_cpu, ov_cpu)
    changed = sum(1 for v in flags.values() if v)
    if changed == 0:
        return "Sem override"
    if changed == 3:
        return "Override total"
    return "Override parcial"


def _pcat_mini_diff_text(base_cpu: dict[str, Any], ov_cpu: dict[str, Any]) -> str:
    if not ov_cpu:
        return "—"
    flags = _pcat_cpu_diff_flags(base_cpu, ov_cpu)
    parts: list[str] = []
    if flags["producao"]:
        bp = float(base_cpu.get("producao_horaria") or 0.0)
        op = float(ov_cpu.get("producao_horaria") or bp)
        parts.append(f"Prod.: {bp:.2f} -> {op:.2f}")
    if flags["equipe"]:
        bf, be, _ = _pcat_cpu_parts(base_cpu)
        of, oe, _ = _pcat_cpu_parts(ov_cpu)
        parts.append(f"Equipe: {len(bf) + len(be)} -> {len(of) + len(oe)}")
    if flags["composicao"]:
        _, _, bc = _pcat_cpu_parts(base_cpu)
        _, _, oc = _pcat_cpu_parts(ov_cpu)
        parts.append(f"Composição: {len(bc)} -> {len(oc)}")
    return " | ".join(parts) if parts else "—"


def _pcat_insumo_price(insumo: dict[str, Any]) -> float:
    return float(insumo.get("preco_unitario") or 0.0)


def _pcat_equipment_monthly_cost(insumo: dict[str, Any]) -> float:
    attrs = insumo.get("atributos_especificos") or {}
    if attrs.get("valor_locacao_mensal") is not None:
        return float(attrs.get("valor_locacao_mensal") or 0.0)
    if insumo.get("custo_mensal") is not None:
        return float(insumo.get("custo_mensal") or 0.0)
    if insumo.get("preco_unitario") is not None and attrs.get("horas_mes") is not None:
        return float(insumo.get("preco_unitario") or 0.0) * float(attrs.get("horas_mes") or 0.0)
    return 0.0


def _pcat_estimate_cpu_monthly_cost(cpu: dict[str, Any], insumos_idx: dict[str, dict[str, Any]]) -> float:
    funcoes, equips, comp = _pcat_cpu_parts(cpu)
    total = 0.0
    for f in funcoes:
        fid = str(f.get("funcao_id") or "")
        qty = float(f.get("num_pessoas") or 0.0)
        unit = float(f.get("salario_base") or 0.0)
        if unit <= 0.0:
            unit = _pcat_insumo_price(insumos_idx.get(fid) or {})
        total += qty * unit
    for e in equips:
        eid = str(e.get("equip_id") or "")
        qty = float(e.get("num_unidades") or 0.0)
        unit = float(e.get("custo_mensal") or 0.0)
        if unit <= 0.0:
            unit = _pcat_equipment_monthly_cost(insumos_idx.get(eid) or {})
        total += qty * unit
    for c in comp:
        iid = str(c.get("insumo_id") or "")
        coef = float(c.get("coeficiente") or 0.0)
        unit = _pcat_insumo_price(insumos_idx.get(iid) or {})
        total += coef * unit
    return round(total, 2)


def _pcat_estimate_batch_impact(
    base_index: dict[str, dict[str, Any]],
    new_index: dict[str, dict[str, Any]],
    eap_rows: list[dict[str, Any]],
    insumos_idx: dict[str, dict[str, Any]],
) -> tuple[float, float]:
    delta_monthly = 0.0
    for cpu_id, new_cpu in new_index.items():
        base_cpu = base_index.get(cpu_id) or {}
        delta_monthly += _pcat_estimate_cpu_monthly_cost(new_cpu, insumos_idx) - _pcat_estimate_cpu_monthly_cost(
            base_cpu, insumos_idx
        )

    base_hours = 0.0
    new_hours = 0.0
    for row in eap_rows:
        cpu_id = str(row.get("cpu_id") or "")
        if cpu_id not in new_index:
            continue
        qtd = float(row.get("quantitativo") or 0.0)
        b_prod = float((base_index.get(cpu_id) or {}).get("producao_horaria") or 0.0)
        n_prod = float((new_index.get(cpu_id) or {}).get("producao_horaria") or b_prod)
        if b_prod > 0:
            base_hours += qtd / b_prod
        if n_prod > 0:
            new_hours += qtd / n_prod
    if base_hours <= 0:
        return round(delta_monthly, 2), 0.0
    prazo_pct = ((new_hours / base_hours) - 1.0) * 100.0
    return round(delta_monthly, 2), round(prazo_pct, 2)


def _pcat_health_checks(cpu: dict[str, Any], insumos_idx: dict[str, dict[str, Any]]) -> list[str]:
    alerts: list[str] = []
    funcoes, _, comp = _pcat_cpu_parts(cpu)

    missing_desc = [str(f.get("funcao_id") or "?") for f in funcoes if not str(f.get("descricao") or "").strip()]
    if missing_desc:
        alerts.append(f"função sem descrição: {', '.join(missing_desc[:3])}")

    missing_insumos = [str(c.get("insumo_id") or "?") for c in comp if str(c.get("insumo_id") or "") not in insumos_idx]
    if missing_insumos:
        alerts.append(f"insumo inexistente: {', '.join(missing_insumos[:3])}")

    invalid_cats = [
        str(c.get("categoria_custo") or "")
        for c in comp
        if str(c.get("categoria_custo") or "").upper() not in _VALID_COST_CATS
    ]
    if invalid_cats:
        alerts.append(f"categoria_custo inválida: {', '.join(invalid_cats[:3])}")

    ref = str(cpu.get("data_referencia_preco") or "").strip()
    if _pcat_is_price_reference_stale(ref):
        alerts.append("referência de preço defasada")

    return alerts


def _pcat_resolve_catalog_id(project_id: str, base_url: str, actor: str) -> str:
    try:
        proj = api_call("GET", f"/api/projects/{project_id}", base_url=base_url, actor=actor)
        return str(proj.get("contexto_id") or "mendeslobo")
    except Exception:
        return "mendeslobo"


def _pcat_load_panel_data(
    project_id: str, base_url: str, actor: str
) -> tuple[str, dict[str, dict], dict[str, dict], dict[str, Any]]:
    catalog_id = _pcat_resolve_catalog_id(project_id, base_url, actor)
    try:
        cpus = api_call(
            "GET", f"/api/catalogs/{catalog_id}/cpus", params={"limit": 1200}, base_url=base_url, actor=actor
        ).get("items", [])
    except Exception:
        cpus = []
    base_index = {str(c.get("codigo") or ""): c for c in cpus if isinstance(c, dict) and c.get("codigo")}

    try:
        overrides = api_call("GET", f"/api/projects/{project_id}/catalog/overrides", base_url=base_url, actor=actor)
    except Exception:
        overrides = {}
    override_index = {str(k): v for k, v in (overrides or {}).items() if isinstance(v, dict)}

    try:
        reference = api_call("GET", f"/api/projects/{project_id}/benchmark-reference", base_url=base_url, actor=actor)
    except Exception:
        reference = {}

    if not base_index:
        base_index = _pcat_catalog_cpus_index(reference)

    return catalog_id, base_index, override_index, reference


def _pcat_apply_filters(
    rows: list[dict[str, Any]],
    q: str,
    cat_filters: list[str],
    only_used: bool,
    only_incomplete: bool,
    only_stale_price: bool,
) -> list[dict[str, Any]]:
    ql = q.lower().strip()
    out: list[dict[str, Any]] = []
    for row in rows:
        if ql and ql not in row["search_text"]:
            continue
        if cat_filters and row["categoria"] not in cat_filters:
            continue
        if only_used and not row["used_in_eap"]:
            continue
        if only_incomplete and not row["composicao_incompleta"]:
            continue
        if only_stale_price and not row["preco_defasado"]:
            continue
        out.append(row)
    return out


def _pcat_build_batch_preview(
    selected_cpu_ids: list[str],
    base_index: dict[str, dict[str, Any]],
    prod_factor_pct: float,
    team_factor_pct: float,
    comp_factor_pct: float,
) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    prod_k = 1.0 + (prod_factor_pct / 100.0)
    team_k = 1.0 + (team_factor_pct / 100.0)
    comp_k = 1.0 + (comp_factor_pct / 100.0)

    for cpu_id in selected_cpu_ids:
        base_cpu = dict(base_index.get(cpu_id) or {})
        if not base_cpu:
            continue
        new_cpu = dict(base_cpu)
        if base_cpu.get("producao_horaria") is not None:
            new_cpu["producao_horaria"] = round(float(base_cpu.get("producao_horaria") or 0.0) * prod_k, 6)

        funcoes, equips, comp = _pcat_cpu_parts(base_cpu)
        if funcoes or equips:
            new_fun = []
            for f in funcoes:
                entry = dict(f)
                entry["num_pessoas"] = round(float(f.get("num_pessoas") or 0.0) * team_k, 3)
                new_fun.append(entry)
            new_eq = []
            for e in equips:
                entry = dict(e)
                entry["num_unidades"] = round(float(e.get("num_unidades") or 0.0) * team_k, 3)
                new_eq.append(entry)
            new_cpu["equipe"] = {"funcoes": new_fun, "equipamentos": new_eq}

        if comp:
            new_comp = []
            for c in comp:
                entry = dict(c)
                entry["coeficiente"] = round(float(c.get("coeficiente") or 0.0) * comp_k, 6)
                new_comp.append(entry)
            new_cpu["composicao_itens"] = new_comp

        out[cpu_id] = new_cpu
    return out


def _pcat_render_health_panel(
    cpu_ids: list[str],
    index: dict[str, dict[str, Any]],
    insumos_idx: dict[str, dict[str, Any]],
) -> None:
    rows: list[dict[str, str]] = []
    for cpu_id in cpu_ids:
        alerts = _pcat_health_checks(index.get(cpu_id) or {}, insumos_idx)
        for alert in alerts:
            rows.append({"CPU": cpu_id, "Alerta": alert})

    if rows:
        st.warning(f"{len(rows)} alerta(s) de saúde detectado(s).")
        st.dataframe(rows, hide_index=True, use_container_width=True)
    else:
        st.success("Sem alertas de saúde para o conjunto selecionado.")


def _pcat_render_catalog_filters(
    project_id: str, rows: list[dict[str, Any]]
) -> tuple[str, list[str], bool, bool, bool]:
    c1, c2, c3 = st.columns([3, 2, 3])
    q = c1.text_input("Buscar CPU", placeholder="Código, descrição ou diff", key=f"pcat-q-{project_id}")
    categorias = sorted({r["categoria"] for r in rows if r["categoria"]})
    cat_filters = c2.multiselect("Categoria", options=categorias, key=f"pcat-cats-{project_id}")
    with c3:
        only_used = st.checkbox("usadas na EAP atual", key=f"pcat-used-{project_id}")
        only_incomplete = st.checkbox("composição incompleta", key=f"pcat-incomplete-{project_id}")
        only_stale_price = st.checkbox("sem preço referência recente", key=f"pcat-stale-{project_id}")
    return q, cat_filters, only_used, only_incomplete, only_stale_price


def _pcat_select_rows_table(project_id: str, filtered_rows: list[dict[str, Any]]) -> list[str]:
    view_rows = [
        {
            "CPU": r["cpu_id"],
            "Descrição": r["descricao"],
            "Categoria": r["categoria"],
            "Status": r["override_status"],
            "Mini diff": r["mini_diff"],
            "EAP": "Sim" if r["used_in_eap"] else "Não",
            "Saúde": "⚠" if r["health_count"] else "✓",
        }
        for r in filtered_rows
    ]
    sel = st.dataframe(
        view_rows,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="multi-row",
        key=f"pcat-table-{project_id}",
    )
    indices = (sel.selection.rows or []) if hasattr(sel, "selection") else []
    return [filtered_rows[i]["cpu_id"] for i in indices if i < len(filtered_rows)]


def _pcat_render_step_edit(project_id: str, selected_cpu_ids: list[str], base_index: dict[str, dict[str, Any]]) -> None:
    st.markdown("**Passo 2/3 — Editar**")
    if not selected_cpu_ids:
        st.info("Selecione pelo menos uma CPU no passo anterior.")
        return

    st.caption(f"CPUs selecionadas: {len(selected_cpu_ids)}")
    c1, c2, c3 = st.columns(3)
    prod_factor = c1.number_input("Ajuste produtividade (%)", value=0.0, step=1.0, key=f"pcat-prod-{project_id}")
    team_factor = c2.number_input("Ajuste equipe (%)", value=0.0, step=1.0, key=f"pcat-team-{project_id}")
    comp_factor = c3.number_input("Ajuste composição (%)", value=0.0, step=1.0, key=f"pcat-comp-{project_id}")

    preview = _pcat_build_batch_preview(selected_cpu_ids, base_index, prod_factor, team_factor, comp_factor)
    st.session_state[f"pcat-preview-{project_id}"] = preview

    table = []
    for cpu_id in selected_cpu_ids:
        base_cpu = base_index.get(cpu_id) or {}
        new_cpu = preview.get(cpu_id) or base_cpu
        table.append(
            {
                "CPU": cpu_id,
                "Prod. base": float(base_cpu.get("producao_horaria") or 0.0),
                "Prod. nova": float(new_cpu.get("producao_horaria") or 0.0),
                "Equipe base": len(_pcat_cpu_parts(base_cpu)[0]) + len(_pcat_cpu_parts(base_cpu)[1]),
                "Equipe nova": len(_pcat_cpu_parts(new_cpu)[0]) + len(_pcat_cpu_parts(new_cpu)[1]),
                "Comp. base": len(_pcat_cpu_parts(base_cpu)[2]),
                "Comp. nova": len(_pcat_cpu_parts(new_cpu)[2]),
            }
        )
    st.dataframe(table, hide_index=True, use_container_width=True)


def _pcat_render_step_review(
    project_id: str,
    selected_cpu_ids: list[str],
    base_index: dict[str, dict[str, Any]],
    eap_rows: list[dict[str, Any]],
    insumos_idx: dict[str, dict[str, Any]],
    base_url: str,
    actor: str,
) -> None:
    st.markdown("**Passo 3/3 — Revisar impacto e aplicar**")
    preview = st.session_state.get(f"pcat-preview-{project_id}") or {}
    if not selected_cpu_ids or not preview:
        st.info("Gere o preview no passo 2 antes de revisar.")
        return

    delta_monthly, prazo_pct = _pcat_estimate_batch_impact(base_index, preview, eap_rows, insumos_idx)
    k1, k2 = st.columns(2)
    k1.metric("Impacto mensal estimado", f"R$ {delta_monthly:,.2f}")
    k2.metric("Impacto estimado no prazo (EAP)", f"{prazo_pct:+.2f}%")

    diff_rows = []
    for cpu_id in selected_cpu_ids:
        base_cpu = base_index.get(cpu_id) or {}
        new_cpu = preview.get(cpu_id) or base_cpu
        diff_rows.append(
            {
                "CPU": cpu_id,
                "Badge": _pcat_override_badge(base_cpu, new_cpu),
                "Mini diff": _pcat_mini_diff_text(base_cpu, new_cpu),
            }
        )
    st.dataframe(diff_rows, hide_index=True, use_container_width=True)

    _pcat_render_health_panel(selected_cpu_ids, preview, insumos_idx)

    motivo = st.text_input(
        "Motivo único da ação em lote *",
        placeholder="Ex: calibração de produtividade/composição após revisão de campo",
        key=f"pcat-motivo-{project_id}",
    )
    if st.button("Aplicar em lote", type="primary", key=f"pcat-apply-{project_id}"):
        if not motivo.strip():
            st.error("Informe o motivo único para registrar auditoria padronizada.")
            return
        done = 0
        reason = f"[lote-catalogo] {motivo.strip()}"
        for cpu_id in selected_cpu_ids:
            payload = preview.get(cpu_id)
            if not isinstance(payload, dict):
                continue
            try:
                api_call(
                    "POST",
                    f"/api/projects/{project_id}/catalog/cpus/{cpu_id}",
                    base_url=base_url,
                    actor=actor,
                    payload=payload,
                    params={"motivo": reason},
                )
                done += 1
            except Exception as exc:
                st.error(f"Falha ao aplicar em {cpu_id}: {exc}")
        if done:
            st.success(f"{done} CPU(s) atualizada(s) com auditoria única ({reason}).")
            st.session_state.pop(f"pcat-preview-{project_id}", None)


def _pcat_build_catalog_rows(
    base_index: dict[str, dict[str, Any]],
    override_index: dict[str, dict[str, Any]],
    used_in_eap: set[str],
    insumos_idx: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for cpu_id, base_cpu in sorted(base_index.items()):
        ov_cpu = override_index.get(cpu_id) or {}
        merged = {**base_cpu, **ov_cpu} if ov_cpu else base_cpu
        health = _pcat_health_checks(merged, insumos_idx)
        categoria = str(base_cpu.get("categoria") or "")
        descricao = str(base_cpu.get("descricao") or cpu_id)
        status = _pcat_override_badge(base_cpu, ov_cpu)
        mini = _pcat_mini_diff_text(base_cpu, ov_cpu)
        ref_price = str(merged.get("data_referencia_preco") or base_cpu.get("data_referencia_preco") or "")
        rows.append(
            {
                "cpu_id": cpu_id,
                "descricao": descricao,
                "categoria": categoria,
                "override_status": status,
                "mini_diff": mini,
                "used_in_eap": cpu_id in used_in_eap,
                "composicao_incompleta": not _pcat_has_complete_composition(merged),
                "preco_defasado": _pcat_is_price_reference_stale(ref_price),
                "health_count": len(health),
                "search_text": f"{cpu_id} {descricao} {categoria} {status} {mini}".lower(),
            }
        )
    return rows


def _render_project_catalog_section(base_url: str, project_id: str, actor: str) -> None:
    """Painel de catálogo por projeto com delta visual, pipeline de edição e saúde de dados."""
    st.caption(
        "Delta Base x Override por CPU, filtros operacionais, edição em 3 passos, ações em lote e health checks."
    )

    catalog_id, base_index, override_index, reference = _pcat_load_panel_data(project_id, base_url, actor)
    if not base_index:
        st.info("Não foi possível carregar CPUs do catálogo para este projeto.")
        return

    used_in_eap = _pcat_cpus_used_in_eap(reference)
    insumos_idx = _pcat_insumo_index(reference)
    rows = _pcat_build_catalog_rows(base_index, override_index, used_in_eap, insumos_idx)

    total = len(rows)
    sem = sum(1 for r in rows if r["override_status"] == "Sem override")
    parcial = sum(1 for r in rows if r["override_status"] == "Override parcial")
    total_ov = sum(1 for r in rows if r["override_status"] == "Override total")
    h1, h2, h3, h4 = st.columns(4)
    h1.metric("CPUs", total)
    h2.metric("Sem override", sem)
    h3.metric("Override parcial", parcial)
    h4.metric("Override total", total_ov)
    st.caption(f"Catálogo ativo (contexto): {catalog_id}")

    q, cat_filters, only_used, only_incomplete, only_stale_price = _pcat_render_catalog_filters(project_id, rows)
    filtered = _pcat_apply_filters(rows, q, cat_filters, only_used, only_incomplete, only_stale_price)
    st.caption(f"Filtradas: {len(filtered)} CPU(s)")

    selected_cpu_ids = _pcat_select_rows_table(project_id, filtered)

    step = st.radio(
        "Pipeline de edição",
        options=["Selecionar CPU", "Editar", "Revisar impacto"],
        horizontal=True,
        key=f"pcat-step-{project_id}",
    )

    eap_rows = _pcat_extract_eap_rows(reference)
    if step == "Selecionar CPU":
        st.info("Selecione uma ou mais CPUs na tabela acima para avançar ao passo de edição.")
        _pcat_render_health_panel(
            selected_cpu_ids, {cid: base_index.get(cid) or {} for cid in selected_cpu_ids}, insumos_idx
        )
    elif step == "Editar":
        _pcat_render_step_edit(project_id, selected_cpu_ids, base_index)
    else:
        _pcat_render_step_review(project_id, selected_cpu_ids, base_index, eap_rows, insumos_idx, base_url, actor)
