"""Independent oracle for the catalog envelope C^cat (FORMALISMO_LONGO Parts II–III, §XIII).

    c_r = V_r^mensal / (s_mes · d · h)        cat(r) ∈ {EQ, MO}, monthly price
    c_r = price per hour                      cat(r) ∈ {EQ, MO}, hourly price
    γ_i^K = Σ_r c_r n_r                       per front, [R$/h]
    C_i^K = Q_i γ_i^K / ρ_i
    C_i^V = Q_i Σ_g κ_g^out p_g               κ^out per delivered unit (= κ_g / ρ_i)
    C^cat = Σ_i (C_i^K + C_i^V)

Stdlib only and deliberately written from the formulas, not from the
production module. Exact rationals; this is a reference witness, never GO.
"""

from __future__ import annotations

from fractions import Fraction as F
from typing import Any

VERSION = "formalism-catalog-envelope/1"
S_MES = F(1461, 336)  # FORMALISMO_LONGO Part II: (365·3+366)/(4·12·7) weeks/month
CONTRACTUAL = frozenset({"EQ", "MO"})


class CatalogEnvelopeContractError(ValueError):
    pass


def _q(value: Any, label: str) -> F:
    if not isinstance(value, str):
        raise CatalogEnvelopeContractError(f"{label} must be an exact string")
    try:
        result = F(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise CatalogEnvelopeContractError(f"{label} is not rational") from exc
    return result


def evaluate_catalog_envelope(case: dict[str, Any]) -> dict[str, Any]:
    inputs = case["inputs"]
    days, hours = F(inputs["regime"]["d"]), F(inputs["regime"]["h"])
    if days <= 0 or hours <= 0:
        raise CatalogEnvelopeContractError("regime d and h must be positive")
    if _q(inputs["s_mes"], "s_mes") != S_MES:
        raise CatalogEnvelopeContractError("s_mes must be the normative 1461/336")
    per_activity: dict[str, dict[str, str]] = {}
    total = F(0)
    for activity in inputs["activities"]:
        quantity, rho = _q(activity["Q"], "Q"), _q(activity["rho"], "rho")
        if quantity <= 0 or rho <= 0:
            raise CatalogEnvelopeContractError("Q and rho must be positive")
        gamma_k = F(0)
        for resource in activity["contractual"]:
            if resource["cat"] not in CONTRACTUAL:
                raise CatalogEnvelopeContractError("contractual resources are EQ or MO")
            price = _q(resource["price"], "price")
            if resource["price_unit"] == "mes":
                hourly = price / (S_MES * days * hours)
            elif resource["price_unit"] == "h":
                hourly = price
            else:
                raise CatalogEnvelopeContractError("contractual price unit must be mes or h")
            gamma_k += hourly * F(resource["n"])
        c_k = quantity * gamma_k / rho
        c_v = quantity * sum((_q(g["coef"], "coef") * _q(g["price"], "price") for g in activity["consumables"]), F(0))
        per_activity[activity["id"]] = {"K": str(c_k), "V": str(c_v), "total": str(c_k + c_v)}
        total += c_k + c_v
    return {"activities": per_activity, "total": str(total)}
