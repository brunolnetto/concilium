"""Independent oracle: weekly P16 tariff from a catalog price and declared terms (N8).

active = V_mensal / s_mes for a monthly price, c_h * d * h for an hourly price
(FORMALISMO_LONGO XIV.2, s_mes = 1461/336), exact — never rounded. The standby
regime, MOB/DEMOB and the idle gap are declared, never inferred (P13-A):
FULL_RATE_STANDBY sets idle = active; DISCOUNTED_STANDBY needs a declared idle
tariff below the active one. Anything missing is an unknown contract.
Stdlib only; written from the rule, not from production code.
"""

from __future__ import annotations

from fractions import Fraction as F
from typing import Any

VERSION = "formalism-contract-tariff/1"
S_MES = F(1461, 336)


class ContractTariffError(ValueError):
    pass


def evaluate_contract_tariff(case: dict[str, Any]) -> dict[str, str]:
    terms = {**case.get("default", {}), **case.get("override", {})}
    for field in ("regime", "mobilize", "demobilize", "max_idle_gap", "source"):
        if field not in terms:
            raise ContractTariffError(f"contract terms not declared: {field}")
    price, unit = F(case["price"]), case["price_unit"]
    if unit == "mes":
        active = price / S_MES
    elif unit == "h":
        active = price * case["dias_semana"] * F(case["horas_dia"])
    else:
        raise ContractTariffError("price unit must be 'mes' or 'h'")
    if terms["regime"] == "FULL_RATE_STANDBY":
        idle = active
    elif terms["regime"] == "DISCOUNTED_STANDBY":
        if "idle_week" not in terms:
            raise ContractTariffError("discounted standby needs a declared idle tariff")
        idle = F(terms["idle_week"])
        if idle >= active:
            raise ContractTariffError("discounted idle tariff must be below the active tariff")
    else:
        raise ContractTariffError("standby regime not declared")
    return {
        "active_week": str(active),
        "idle_week": str(idle),
        "mobilize": str(F(terms["mobilize"])),
        "demobilize": str(F(terms["demobilize"])),
        "max_idle_gap": str(terms["max_idle_gap"]),
    }
