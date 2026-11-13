"""Independent oracle: exact variable cost per activity under N6 (P18).

C_i^{V,op} = Q_i * Σ_g κ_g^out p_g for an activity with a per-delivered-unit
BOM; 0 only when the CPU declares NENHUM (with justification and source) and
has no consumable rows or hourly consumption; otherwise not certifiable.
Stdlib only; written from the rule, not from production code.
"""

from __future__ import annotations

from fractions import Fraction as F
from typing import Any

VERSION = "formalism-consumption-declaration/1"


class ConsumptionDeclarationError(ValueError):
    pass


def evaluate_activity_consumption(activity: dict[str, Any]) -> str:
    bom = activity.get("bom") or []
    declaration = activity.get("declaration")
    hourly = bool(activity.get("hourly_consumption"))
    if declaration is not None:
        if declaration.get("status") != "NENHUM" or not str(declaration.get("justificativa", "")).strip() or not str(
            declaration.get("fonte", "")
        ).strip():
            raise ConsumptionDeclarationError("incomplete declaration")
        if bom or hourly:
            raise ConsumptionDeclarationError("declaration contradicted")
        return "0"
    if hourly and not bom:
        raise ConsumptionDeclarationError("hourly consumption needs observed operating hours")
    if not bom:
        raise ConsumptionDeclarationError("no BOM and no declaration")
    q = F(activity["Q"])
    return str(q * sum((F(g["coef"]) * F(g["price"]) for g in bom), F(0)))
