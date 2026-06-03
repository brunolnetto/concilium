from __future__ import annotations

from typing import Any


def deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def build_summary(canonical: Any) -> dict[str, Any]:
    if canonical is None:
        return {}

    result = getattr(canonical, "resultado", None)
    ponto_equilibrio = getattr(canonical, "ponto_equilibrio", []) or []
    pe_deficit_items = sum(1 for item in ponto_equilibrio if getattr(item, "status_validacao", "") == "ERRO")
    pe_alerta_items = sum(1 for item in ponto_equilibrio if getattr(item, "status_validacao", "") == "AVISO")
    if result is None:
        return {
            "pe_deficit_items": pe_deficit_items,
            "pe_alerta_items": pe_alerta_items,
        }

    return {
        "preco_venda_total": float(result.venda.total_com_bdi),
        "custo_total": float(result.custo.total),
        "resultado_bruto": float(result.resultado_financeiro),
        "margem_pct": float(result.margem_pct),
        "status_margem": result.status_margem,
        "pe_deficit_items": pe_deficit_items,
        "pe_alerta_items": pe_alerta_items,
    }
