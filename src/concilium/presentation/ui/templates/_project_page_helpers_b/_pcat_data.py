"""Helpers extracted from project_page.py (parte extraída de _project_page_helpers_b.py, grupo _pcat_data)."""

from __future__ import annotations

from typing import Any

from ...infra.api import api_call
from ._pcat_helpers import _pcat_catalog_cpus_index, _pcat_cpu_parts


def _pcat_resolve_catalog_id(project_id: str, base_url: str, actor: str) -> str:
    try:
        proj = api_call("GET", f"/api/projects/{project_id}", base_url=base_url, actor=actor)
        return str(proj.get("contexto_id") or "mendeslobo")
    except Exception:
        return "mendeslobo"


def _pcat_fetch_base_index(catalog_id: str, base_url: str, actor: str) -> dict[str, dict[str, Any]]:
    try:
        cpus = api_call(
            "GET", f"/api/catalogs/{catalog_id}/cpus", params={"limit": 1200}, base_url=base_url, actor=actor
        ).get("items", [])
    except Exception:
        cpus = []
    return {str(c.get("codigo") or ""): c for c in cpus if isinstance(c, dict) and c.get("codigo")}


def _pcat_fetch_override_index(project_id: str, base_url: str, actor: str) -> dict[str, dict[str, Any]]:
    try:
        overrides = api_call("GET", f"/api/projects/{project_id}/catalog/overrides", base_url=base_url, actor=actor)
    except Exception:
        overrides = {}
    return {str(k): v for k, v in (overrides or {}).items() if isinstance(v, dict)}


def _pcat_fetch_reference(project_id: str, base_url: str, actor: str) -> dict[str, Any]:
    try:
        return api_call("GET", f"/api/projects/{project_id}/benchmark-reference", base_url=base_url, actor=actor)
    except Exception:
        return {}


def _pcat_load_panel_data(
    project_id: str, base_url: str, actor: str
) -> tuple[str, dict[str, dict], dict[str, dict], dict[str, Any]]:
    catalog_id = _pcat_resolve_catalog_id(project_id, base_url, actor)
    base_index = _pcat_fetch_base_index(catalog_id, base_url, actor)
    override_index = _pcat_fetch_override_index(project_id, base_url, actor)
    reference = _pcat_fetch_reference(project_id, base_url, actor)

    if not base_index:
        base_index = _pcat_catalog_cpus_index(reference)

    return catalog_id, base_index, override_index, reference


def _pcat_row_matches_search(row: dict[str, Any], ql: str, cat_filters: list[str]) -> bool:
    if ql and ql not in row["search_text"]:
        return False
    if cat_filters and row["categoria"] not in cat_filters:
        return False
    return True


def _pcat_row_matches_toggles(
    row: dict[str, Any], only_used: bool, only_incomplete: bool, only_stale_price: bool
) -> bool:
    if only_used and not row["used_in_eap"]:
        return False
    if only_incomplete and not row["composicao_incompleta"]:
        return False
    if only_stale_price and not row["preco_defasado"]:
        return False
    return True


def _pcat_row_matches_filters(
    row: dict[str, Any],
    ql: str,
    cat_filters: list[str],
    only_used: bool,
    only_incomplete: bool,
    only_stale_price: bool,
) -> bool:
    return _pcat_row_matches_search(row, ql, cat_filters) and _pcat_row_matches_toggles(
        row, only_used, only_incomplete, only_stale_price
    )


def _pcat_apply_filters(
    rows: list[dict[str, Any]],
    q: str,
    cat_filters: list[str],
    only_used: bool,
    only_incomplete: bool,
    only_stale_price: bool,
) -> list[dict[str, Any]]:
    ql = q.lower().strip()
    return [
        row
        for row in rows
        if _pcat_row_matches_filters(row, ql, cat_filters, only_used, only_incomplete, only_stale_price)
    ]


def _pcat_scale_producao(new_cpu: dict[str, Any], base_cpu: dict[str, Any], prod_k: float) -> None:
    if base_cpu.get("producao_horaria") is not None:
        new_cpu["producao_horaria"] = round(float(base_cpu.get("producao_horaria") or 0.0) * prod_k, 6)


def _pcat_scale_equipe(
    new_cpu: dict[str, Any], funcoes: list[dict[str, Any]], equips: list[dict[str, Any]], team_k: float
) -> None:
    if not (funcoes or equips):
        return
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


def _pcat_scale_composicao(new_cpu: dict[str, Any], comp: list[dict[str, Any]], comp_k: float) -> None:
    if not comp:
        return
    new_comp = []
    for c in comp:
        entry = dict(c)
        entry["coeficiente"] = round(float(c.get("coeficiente") or 0.0) * comp_k, 6)
        new_comp.append(entry)
    new_cpu["composicao_itens"] = new_comp


def _pcat_build_preview_cpu(base_cpu: dict[str, Any], prod_k: float, team_k: float, comp_k: float) -> dict[str, Any]:
    new_cpu = dict(base_cpu)
    _pcat_scale_producao(new_cpu, base_cpu, prod_k)
    funcoes, equips, comp = _pcat_cpu_parts(base_cpu)
    _pcat_scale_equipe(new_cpu, funcoes, equips, team_k)
    _pcat_scale_composicao(new_cpu, comp, comp_k)
    return new_cpu


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
        out[cpu_id] = _pcat_build_preview_cpu(base_cpu, prod_k, team_k, comp_k)
    return out


