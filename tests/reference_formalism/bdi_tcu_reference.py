"""Independent oracle: category BDI by the TCU formula (Acórdão 2622/2013-Plenário, N9).

BDI = (1 + (AC + R + S + G)) (1 + DF) (1 + L) / (1 - T) - 1, exact rationals.
AC central administration; R risk, S insurance, G guarantee (added, not
multiplied); DF financial expenses; L profit; T taxes on the sale price.
Stdlib only; written from the published formula, not from production code.
"""

from __future__ import annotations

from fractions import Fraction as F
from typing import Any

VERSION = "formalism-bdi-tcu/1"


class BdiError(ValueError):
    pass


def evaluate_bdi(case: dict[str, Any]) -> str:
    try:
        ac, rsg, df, lucro, taxes = (F(case[k]) for k in ("AC", "RSG", "DF", "L", "T"))
    except (KeyError, ValueError) as exc:
        raise BdiError("BDI components must be exact numbers") from exc
    if min(ac, rsg, df, lucro, taxes) < 0:
        raise BdiError("BDI components must be nonnegative")
    if taxes >= 1:
        raise BdiError("taxes on the sale price must be below 100%")
    return str((1 + ac + rsg) * (1 + df) * (1 + lucro) / (1 - taxes) - 1)
