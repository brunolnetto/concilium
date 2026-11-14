"""Independent oracle: project declaration merged over the profile's markup layers (N9.1).

The company profile declares, per category, overhead (AC, RSG, DF), profit (L)
and taxes on the sale price. A project may declare its own profit and, tax by
tax, whether the tax applies and at which rate. The merge is field by field:

    l_eff   = project l              if the project declares it, else profile l
    t_x_eff = 0                      if the project declares x not applicable
            = project rate of x      if the project declares x applicable
            = profile rate of x      otherwise
    AC, RSG, DF                      always the profile's

and the price follows from the effective rates by the TCU structure,
P = C (1 + AC + RSG) (1 + DF) (1 + l_eff) / (1 - sum t_x_eff). Every effective
field is attributed to ``profile`` or ``project``.
Stdlib only; written from the rule, not from production code.
"""

from __future__ import annotations

from fractions import Fraction as F
from typing import Any

VERSION = "formalism-project-markup-merge/1"


class ProjectMarkupMergeError(ValueError):
    pass


def _exact(value: Any, what: str) -> F:
    if not isinstance(value, str):
        raise ProjectMarkupMergeError(f"{what} must be an exact string")
    try:
        number = F(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise ProjectMarkupMergeError(f"{what} must be an exact string") from exc
    if number < 0:
        raise ProjectMarkupMergeError(f"{what} must be nonnegative")
    return number


def _effective(base: dict[str, Any], declared: dict[str, Any] | None, category: str) -> tuple[dict[str, Any], dict]:
    rates: dict[str, Any] = {k: _exact(base[k], f"{category}.{k}") for k in ("ac", "rsg", "df", "l")}
    rates["taxes"] = {name: _exact(rate, f"{category}.{name}") for name, rate in base["taxes"].items()}
    origin: dict[str, Any] = {"ac": "profile", "rsg": "profile", "df": "profile", "l": "profile"}
    origin["taxes"] = dict.fromkeys(base["taxes"], "profile")
    if declared is not None:
        if not declared or set(declared) - {"l", "taxes"}:
            raise ProjectMarkupMergeError(f"{category}: a project declares only l and taxes, at least one of them")
        if "l" in declared:
            rates["l"] = _exact(declared["l"], f"{category}.l")
            origin["l"] = "project"
        if "taxes" in declared and not declared["taxes"]:
            raise ProjectMarkupMergeError(f"{category}: a project declares only l and taxes, at least one of them")
        for name, entry in declared.get("taxes", {}).items():
            if name not in base["taxes"]:
                raise ProjectMarkupMergeError(f"{category}: unknown tax {name}")
            if set(entry) - {"applicable", "rate"} or type(entry.get("applicable")) is not bool:
                raise ProjectMarkupMergeError(f"{category}.{name}: applicable must be an explicit boolean")
            if entry["applicable"] != ("rate" in entry):
                raise ProjectMarkupMergeError(f"{category}.{name}: a rate is declared exactly when the tax applies")
            rates["taxes"][name] = _exact(entry["rate"], f"{category}.{name}") if entry["applicable"] else F(0)
            origin["taxes"][name] = "project"
    if sum(rates["taxes"].values(), F(0)) >= 1:
        raise ProjectMarkupMergeError(f"{category}: taxes on the sale price must be below 100%")
    return rates, origin


def evaluate_project_markup_merge(case: dict[str, Any]) -> dict[str, Any]:
    base, project = case["base"], case.get("project")
    if project is not None:
        if not project:
            raise ProjectMarkupMergeError("a project declaration must declare at least one category")
        unknown = sorted(set(project) - set(base))
        if unknown:
            raise ProjectMarkupMergeError(f"unknown category {unknown[0]}")
    out: dict[str, Any] = {"rates": {}, "origin": {}, "beta": {}, "by_category": {}}
    totals = {key: F(0) for key in ("cost", "overhead", "profit", "taxes", "price")}
    for category in base:
        rates, origin = _effective(base[category], None if project is None else project.get(category), category)
        tax = sum(rates["taxes"].values(), F(0))
        factor = (1 + rates["ac"] + rates["rsg"]) * (1 + rates["df"]) * (1 + rates["l"]) / (1 - tax)
        out["rates"][category] = {
            **{k: str(rates[k]) for k in ("ac", "rsg", "df", "l")},
            "taxes": {name: str(rate) for name, rate in rates["taxes"].items()},
        }
        out["origin"][category] = origin
        out["beta"][category] = str(factor - 1)
        if category in case.get("costs", {}):
            cost = _exact(case["costs"][category], f"cost {category}")
            loaded = cost * (1 + rates["ac"] + rates["rsg"])
            with_df = loaded * (1 + rates["df"])
            price = cost * factor
            layers = {
                "cost": cost,
                "overhead": cost * (rates["ac"] + rates["rsg"]) + loaded * rates["df"],
                "profit": with_df * rates["l"],
                "taxes": tax * price,
                "price": price,
            }
            if layers["cost"] + layers["overhead"] + layers["profit"] + layers["taxes"] != price:
                raise ProjectMarkupMergeError("layers do not add up to the price")
            out["by_category"][category] = {key: str(value) for key, value in layers.items()}
            for key, value in layers.items():
                totals[key] += value
    out["total"] = {key: str(value) for key, value in totals.items()}
    return out
