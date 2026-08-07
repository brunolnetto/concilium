"""Helpers for project page EAP/catalog cross-reference analysis.

Provides utilities to extract, index, and compare CPU (composite production unit) data
from catalog references within project EAP (WBS) structures. Handles:
  - EAP row extraction and CPU ID resolution from project reference data
  - Catalog indexing (insumos, CPUs) for fast O(1) lookups
  - Price reference staleness checks (e.g., prices older than 6 months)
  - CPU composition analysis (team, equipment, direct inputs)
  - CPU override detection and diff badge generation for UI display

Key entities:
  - CPU (Composite Production Unit): pricing/productivity baseline with optional overrides
  - EAP (Estrutura Analítica de Projeto / WBS): work breakdown structure
  - Override: user-modified CPU fields (producao_horaria, equipe, composicao_itens)
"""

from __future__ import annotations

from datetime import date
from typing import Any

_VALID_COST_CATS = {"MAO_OBRA", "MATERIAL", "EQUIPAMENTO", "DIESEL", "SERVICO"}


def _pcat_extract_eap_rows(reference: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract EAP (WBS) row items from project reference data.

    Tries two locations in order:
      1. reference.cpus.itens_eap (newer nested format)
      2. reference.eap (legacy flat format)

    Filters non-dict items and returns empty list if neither location found.
    """
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
    """Get the set of CPU IDs referenced in the project's EAP.

    Extracts unique cpu_id values from all EAP rows. Used to determine which
    CPUs are actually deployed in the project (vs catalog breadth).
    """
    used: set[str] = set()
    for it in _pcat_extract_eap_rows(reference):
        cpu_id = str(it.get("cpu_id") or "").strip()
        if cpu_id:
            used.add(cpu_id)
    return used


def _pcat_insumo_index(reference: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Build an O(1) lookup index of insumos (materials/inputs) from catalog.

    Indexes by codigo (primary) or id (fallback). Returns empty dict if catalog
    or insumos list not found in reference.
    """
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
    """Build an O(1) lookup index of CPUs from catalog.

    Indexes CPUs by codigo field. Returns empty dict if catalog or cpus list
    not found in reference.
    """
    cat = reference.get("catalog") or {}
    out: dict[str, dict[str, Any]] = {}
    for cpu in cat.get("cpus") or []:
        if isinstance(cpu, dict):
            code = str(cpu.get("codigo") or "").strip()
            if code:
                out[code] = cpu
    return out


def _pcat_parse_ref_yyyy_mm(text: str) -> tuple[int, int] | None:
    """Parse YYYY-MM date string (e.g., '2024-08') into (year, month) tuple.

    Expected format: 'YYYY-MM' (ISO 8601 prefix). Returns None if format invalid
    or month out of range [1, 12].
    """
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
    """Check if a price reference date (YYYY-MM) is stale (older than max_age_months).

    Returns True if reference is unparseable, or age exceeds max_age_months.
    Default threshold is 6 months (ADR-XXX: pricing recalibration baseline).
    """
    parsed = _pcat_parse_ref_yyyy_mm(ref)
    if parsed is None:
        return True
    y, m = parsed
    today = date.today()
    age = (today.year - y) * 12 + (today.month - m)
    return age > max_age_months


def _pcat_resolve_equipe(cpu: dict[str, Any]) -> dict[str, Any]:
    """Resolve CPU team composition (equipe) from explicit or default source.

    Priority:
      1. cpu.equipe (explicit team override)
      2. cpu.composicao_padrao_equipe (default team template)

    Returns empty dict if neither found.
    """
    equipe = cpu.get("equipe")
    if isinstance(equipe, dict):
        return equipe
    raw_equipe = cpu.get("composicao_padrao_equipe")
    return raw_equipe if isinstance(raw_equipe, dict) else {}


def _pcat_dict_items(raw: Any) -> list[dict[str, Any]]:
    """Filter list-like to extract only dict items. Safe for None/non-list inputs."""
    return [item for item in (raw or []) if isinstance(item, dict)]


def _pcat_cpu_parts(cpu: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Decompose CPU into its three composition parts: (funcoes, equipamentos, composicao_itens).

    Returns:
        (funcoes, equipamentos, composicao_itens) - three lists of dict items
    """
    equipe = _pcat_resolve_equipe(cpu)
    funcoes = _pcat_dict_items(equipe.get("funcoes"))
    equips = _pcat_dict_items(equipe.get("equipamentos"))
    comp = _pcat_dict_items(cpu.get("composicao_itens") or cpu.get("composicao_completa"))
    return funcoes, equips, comp


def _pcat_has_complete_composition(cpu: dict[str, Any]) -> bool:
    """Check if CPU has any composition defined (team, equipment, or direct inputs)."""
    funcoes, equips, comp = _pcat_cpu_parts(cpu)
    return bool(funcoes or equips or comp)


def _pcat_cpu_diff_flags(base_cpu: dict[str, Any], ov_cpu: dict[str, Any]) -> dict[str, bool]:
    """Detect which CPU fields differ between base and override versions.

    Returns dict with three boolean flags:
      - producao: productivity_hourly changed
      - equipe: team (funcoes/equipamentos) changed
      - composicao: direct inputs (composicao_itens) changed
    """
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
    """Generate UI badge label for CPU override status.

    Returns one of:
      - 'Sem override': No override present or no changes detected
      - 'Override total': All 3 fields changed (producao + equipe + composicao)
      - 'Override parcial': 1-2 fields changed
    """
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
    """Generate compact text summary of CPU override changes for UI display.

    Format: 'Prod.: 5.00 -> 6.50 | Equipe: 3 -> 2 | Composição: 5 -> 4'
    Returns '—' if no override or no changes detected.
    """
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


def _pcat_funcoes_cost(funcoes: list[dict[str, Any]], insumos_idx: dict[str, dict[str, Any]]) -> float:
    total = 0.0
    for f in funcoes:
        fid = str(f.get("funcao_id") or "")
        qty = float(f.get("num_pessoas") or 0.0)
        unit = float(f.get("salario_base") or 0.0)
        if unit <= 0.0:
            unit = _pcat_insumo_price(insumos_idx.get(fid) or {})
        total += qty * unit
    return total


def _pcat_equips_cost(equips: list[dict[str, Any]], insumos_idx: dict[str, dict[str, Any]]) -> float:
    total = 0.0
    for e in equips:
        eid = str(e.get("equip_id") or "")
        qty = float(e.get("num_unidades") or 0.0)
        unit = float(e.get("custo_mensal") or 0.0)
        if unit <= 0.0:
            unit = _pcat_equipment_monthly_cost(insumos_idx.get(eid) or {})
        total += qty * unit
    return total


def _pcat_comp_cost(comp: list[dict[str, Any]], insumos_idx: dict[str, dict[str, Any]]) -> float:
    total = 0.0
    for c in comp:
        iid = str(c.get("insumo_id") or "")
        coef = float(c.get("coeficiente") or 0.0)
        unit = _pcat_insumo_price(insumos_idx.get(iid) or {})
        total += coef * unit
    return total


def _pcat_estimate_cpu_monthly_cost(cpu: dict[str, Any], insumos_idx: dict[str, dict[str, Any]]) -> float:
    funcoes, equips, comp = _pcat_cpu_parts(cpu)
    total = (
        _pcat_funcoes_cost(funcoes, insumos_idx)
        + _pcat_equips_cost(equips, insumos_idx)
        + _pcat_comp_cost(comp, insumos_idx)
    )
    return round(total, 2)


def _pcat_delta_monthly_cost(
    base_index: dict[str, dict[str, Any]],
    new_index: dict[str, dict[str, Any]],
    insumos_idx: dict[str, dict[str, Any]],
) -> float:
    delta_monthly = 0.0
    for cpu_id, new_cpu in new_index.items():
        base_cpu = base_index.get(cpu_id) or {}
        delta_monthly += _pcat_estimate_cpu_monthly_cost(new_cpu, insumos_idx) - _pcat_estimate_cpu_monthly_cost(
            base_cpu, insumos_idx
        )
    return delta_monthly


def _pcat_hours_for_row(
    row: dict[str, Any], base_index: dict[str, dict[str, Any]], new_index: dict[str, dict[str, Any]]
) -> tuple[float, float]:
    cpu_id = str(row.get("cpu_id") or "")
    qtd = float(row.get("quantitativo") or 0.0)
    b_prod = float((base_index.get(cpu_id) or {}).get("producao_horaria") or 0.0)
    n_prod = float((new_index.get(cpu_id) or {}).get("producao_horaria") or b_prod)
    base_hours = qtd / b_prod if b_prod > 0 else 0.0
    new_hours = qtd / n_prod if n_prod > 0 else 0.0
    return base_hours, new_hours


def _pcat_hours_delta(
    base_index: dict[str, dict[str, Any]],
    new_index: dict[str, dict[str, Any]],
    eap_rows: list[dict[str, Any]],
) -> tuple[float, float]:
    base_hours = 0.0
    new_hours = 0.0
    for row in eap_rows:
        cpu_id = str(row.get("cpu_id") or "")
        if cpu_id not in new_index:
            continue
        row_base_hours, row_new_hours = _pcat_hours_for_row(row, base_index, new_index)
        base_hours += row_base_hours
        new_hours += row_new_hours
    return base_hours, new_hours


def _pcat_estimate_batch_impact(
    base_index: dict[str, dict[str, Any]],
    new_index: dict[str, dict[str, Any]],
    eap_rows: list[dict[str, Any]],
    insumos_idx: dict[str, dict[str, Any]],
) -> tuple[float, float]:
    delta_monthly = _pcat_delta_monthly_cost(base_index, new_index, insumos_idx)
    base_hours, new_hours = _pcat_hours_delta(base_index, new_index, eap_rows)
    if base_hours <= 0:
        return round(delta_monthly, 2), 0.0
    prazo_pct = ((new_hours / base_hours) - 1.0) * 100.0
    return round(delta_monthly, 2), round(prazo_pct, 2)


def _pcat_missing_desc_alert(funcoes: list[dict[str, Any]]) -> str | None:
    missing_desc = [str(f.get("funcao_id") or "?") for f in funcoes if not str(f.get("descricao") or "").strip()]
    if missing_desc:
        return f"função sem descrição: {', '.join(missing_desc[:3])}"
    return None


def _pcat_missing_insumos_alert(comp: list[dict[str, Any]], insumos_idx: dict[str, dict[str, Any]]) -> str | None:
    missing_insumos = [str(c.get("insumo_id") or "?") for c in comp if str(c.get("insumo_id") or "") not in insumos_idx]
    if missing_insumos:
        return f"insumo inexistente: {', '.join(missing_insumos[:3])}"
    return None


def _pcat_invalid_cats_alert(comp: list[dict[str, Any]]) -> str | None:
    invalid_cats = [
        str(c.get("categoria_custo") or "")
        for c in comp
        if str(c.get("categoria_custo") or "").upper() not in _VALID_COST_CATS
    ]
    if invalid_cats:
        return f"categoria_custo inválida: {', '.join(invalid_cats[:3])}"
    return None


def _pcat_stale_price_alert(cpu: dict[str, Any]) -> str | None:
    ref = str(cpu.get("data_referencia_preco") or "").strip()
    if _pcat_is_price_reference_stale(ref):
        return "referência de preço defasada"
    return None


def _pcat_health_checks(cpu: dict[str, Any], insumos_idx: dict[str, dict[str, Any]]) -> list[str]:
    funcoes, _, comp = _pcat_cpu_parts(cpu)
    checks = [
        _pcat_missing_desc_alert(funcoes),
        _pcat_missing_insumos_alert(comp, insumos_idx),
        _pcat_invalid_cats_alert(comp),
        _pcat_stale_price_alert(cpu),
    ]
    return [alert for alert in checks if alert is not None]


