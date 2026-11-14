"""Independent oracle: markup layers of the sale price (N9).

P = C (1 + (AC + RSG)) (1 + DF) (1 + L) / (1 - T), decomposed in the order the
TCU formula builds it: overhead (C*AC, C*RSG, then DF on the loaded cost),
profit (L on cost + overhead), taxes (each a share of the price). The layers
add up to the price, are linear in the cost, and aggregate by plain addition.
Also: the profit layer's share of the price, and the aggregate BDI floor as
the per-category floors weighted by the catalog composition. Layers are
mandatory: a cost whose category declares no layers has no price.
Stdlib only; written from the rule, not from production code.
"""

from __future__ import annotations

from fractions import Fraction as F
from typing import Any

VERSION = "formalism-markup-layers/1"


class MarkupLayersError(ValueError):
    pass


def _layers(cost: F, rates: dict[str, Any]) -> dict[str, F]:
    ac, rsg, df, lucro = (F(rates[k]) for k in ("ac", "rsg", "df", "l"))
    taxes = {name: F(rate) for name, rate in rates["taxes"].items()}
    total_tax = sum(taxes.values(), F(0))
    if min([ac, rsg, df, lucro, *taxes.values()]) < 0:
        raise MarkupLayersError("layer rates must be nonnegative")
    if total_tax >= 1:
        raise MarkupLayersError("taxes on the sale price must be below 100%")
    loaded = cost * (1 + ac + rsg)
    with_df = loaded * (1 + df)
    net = with_df * (1 + lucro)
    price = net / (1 - total_tax)
    return {
        "cost": cost,
        "overhead": cost * (ac + rsg) + loaded * df,
        "profit": with_df * lucro,
        "taxes": total_tax * price,
        "price": price,
    }


def evaluate_markup_layers(case: dict[str, Any]) -> dict[str, Any]:
    totals = {key: F(0) for key in ("cost", "overhead", "profit", "taxes", "price")}
    by_category: dict[str, dict[str, str]] = {}
    declared = case.get("rates")
    for category, cost in case["costs"].items():
        # Layers are mandatory: a cost with no declared layers has no price
        # (there is no flat or default rate to fall back on).
        if not isinstance(declared, dict) or not isinstance(declared.get(category), dict):
            raise MarkupLayersError(f"category {category} has no declared markup layers: no price")
        layers = _layers(F(cost), declared[category])
        if layers["cost"] + layers["overhead"] + layers["profit"] + layers["taxes"] != layers["price"]:
            raise MarkupLayersError("layers do not add up to the price")
        by_category[category] = {key: str(value) for key, value in layers.items()}
        for key, value in layers.items():
            totals[key] += value
    result: dict[str, Any] = {"by_category": by_category, "total": {k: str(v) for k, v in totals.items()}}
    if totals["price"] > 0:
        result["profit_layer_share"] = str(totals["profit"] / totals["price"])
    floor = case.get("floor")
    if floor is not None:
        k, v = F(floor["contractual"]), F(floor["consumable"])
        if k + v <= 0:
            raise MarkupLayersError("catalog composition must be positive")
        result["aggregate_floor"] = str(
            (k * F(floor["floor_contractual"]) + v * F(floor["floor_consumable"])) / (k + v)
        )
    return result
