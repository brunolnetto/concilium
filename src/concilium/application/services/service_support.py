from __future__ import annotations

from typing import Any

from concilium.application.scheduling.exact_financial_view import build_exact_financial_view


def deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def build_summary(canonical: Any) -> dict[str, Any]:
    """Run/version summary: the exact financial view plus the break-even counters.

    ``financeiro_exato`` is the one exact financial view
    (:mod:`concilium.application.scheduling.exact_financial_view`); the legacy
    float keys (``preco_venda_total``, ``custo_total``, ``resultado_bruto``,
    ``margem_pct``, ``status_margem``) no longer exist. The run's certificate
    is not copied here: it is re-fingerprinted on every read and lives at
    ``run["formalism_certificate"]``.
    """
    if canonical is None:
        return {}

    ponto_equilibrio = getattr(canonical, "ponto_equilibrio", []) or []
    pe_deficit_items = sum(1 for item in ponto_equilibrio if getattr(item, "status_validacao", "") == "ERRO")
    pe_alerta_items = sum(1 for item in ponto_equilibrio if getattr(item, "status_validacao", "") == "AVISO")
    return {
        "financeiro_exato": build_exact_financial_view(canonical),
        "pe_deficit_items": pe_deficit_items,
        "pe_alerta_items": pe_alerta_items,
    }
