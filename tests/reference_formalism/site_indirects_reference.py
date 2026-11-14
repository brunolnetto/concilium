"""Independent oracle: declared site indirects (FORMALISMO_LONGO Part XII, N10).

A ``perm`` line charges, in every mobilised week, its monthly cost per
sub-category divided by ``s_mes = 1461/336``; MO, EQ and COMB keep their own
markup category and VM takes IND. A ``onetime`` line charges its mobilisation
in the first mobilised week and its demobilisation in the last one, both IND.
With the category markups, the price is the sum of each category's cost times
``1 + beta`` (XII.4). Stdlib only; written from the rule, not from production
code.
"""

from __future__ import annotations

import datetime as dt
from fractions import Fraction as F
from typing import Any

VERSION = "formalism-site-indirects/1"
WEEKS_PER_MONTH = F(1461, 336)
MARKUP_CATEGORY = {"MO": "MO", "EQ": "EQ", "COMB": "COMB", "VM": "IND"}


class SiteIndirectsError(ValueError):
    pass


def _exact(value: Any, label: str) -> F:
    if not isinstance(value, str) or not value.strip():
        raise SiteIndirectsError(f"{label}: exact string required")
    try:
        amount = F(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise SiteIndirectsError(f"{label}: exact string required") from exc
    if amount < 0:
        raise SiteIndirectsError(f"{label}: nonnegative amount required")
    return amount


def _monday(week: Any) -> dt.date:
    if not isinstance(week, str) or len(week) != 8 or week[4:6] != "-W":
        raise SiteIndirectsError("ISO week YYYY-Www required")
    try:
        return dt.date.fromisocalendar(int(week[:4]), int(week[6:]), 1)
    except ValueError as exc:
        raise SiteIndirectsError("ISO week YYYY-Www required") from exc


def mobilised_weeks(first: Any, last: Any) -> list[str]:
    start, end = _monday(first), _monday(last)
    if end < start:
        raise SiteIndirectsError("mobilised window ends before it starts")
    out = []
    while start <= end:
        iso = start.isocalendar()
        out.append(f"{iso[0]}-W{iso[1]:02d}")
        start += dt.timedelta(days=7)
    return out


def evaluate_site_indirects(case: dict[str, Any]) -> dict[str, Any]:
    weeks = mobilised_weeks(case["mobilised_weeks"]["first"], case["mobilised_weeks"]["last"])
    if not case["lines"]:
        raise SiteIndirectsError("at least one declared line required")
    postings: list[tuple[str, str, str, F]] = []  # (event, week, category, amount)
    by_line: dict[str, dict[str, F]] = {}
    for line in case["lines"]:
        line_id = line.get("line_id")
        if not isinstance(line_id, str) or not line_id:
            raise SiteIndirectsError("line identity required")
        if line_id in by_line:
            raise SiteIndirectsError(f"duplicate line {line_id}")
        by_line[line_id] = {}
        driver = line.get("driver")
        if driver == "perm":
            if set(line) != {"line_id", "driver", "source", "monthly"} or set(line["monthly"]) != set(MARKUP_CATEGORY):
                raise SiteIndirectsError(f"{line_id}: perm line declares monthly MO, EQ, COMB and VM only")
            for sub in ("MO", "EQ", "COMB", "VM"):
                weekly = _exact(line["monthly"][sub], f"{line_id}.{sub}") / WEEKS_PER_MONTH
                if weekly:
                    postings.extend((f"{line_id}/{sub}/{week}", week, MARKUP_CATEGORY[sub], weekly) for week in weeks)
        elif driver == "onetime":
            if set(line) != {"line_id", "driver", "source", "mobilize", "demobilize"}:
                raise SiteIndirectsError(f"{line_id}: onetime line declares mobilize and demobilize only")
            for event, key, week in (("MOB", "mobilize", weeks[0]), ("DEMOB", "demobilize", weeks[-1])):
                amount = _exact(line[key], f"{line_id}.{key}")
                if amount:
                    postings.append((f"{line_id}/{event}", week, "IND", amount))
        else:
            raise SiteIndirectsError(f"{line_id}: driver must be perm or onetime")
        if not isinstance(line.get("source"), str) or not line["source"].strip():
            raise SiteIndirectsError(f"{line_id}: source required")

    by_category: dict[str, F] = {}
    by_week: dict[str, F] = {}
    for event, week, category, amount in postings:
        line_totals = by_line[event.split("/")[0]]
        line_totals[category] = line_totals.get(category, F(0)) + amount
        by_category[category] = by_category.get(category, F(0)) + amount
        by_week[week] = by_week.get(week, F(0)) + amount
    result: dict[str, Any] = {
        "weeks": weeks,
        "postings": {event: [week, category, str(amount)] for event, week, category, amount in postings},
        "by_line": {line: {c: str(v) for c, v in sorted(t.items())} for line, t in by_line.items()},
        "by_category": {c: str(v) for c, v in sorted(by_category.items())},
        "by_week": {w: str(v) for w, v in sorted(by_week.items())},
        "cost": str(sum(by_category.values(), F(0))),
    }
    markups = case.get("markup_by_category")
    if markups is not None:
        result["price"] = str(
            sum((cost * (1 + _exact(markups[category], category)) for category, cost in by_category.items()), F(0))
        )
    return result
