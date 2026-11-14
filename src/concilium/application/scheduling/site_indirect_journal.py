"""N10: exact journal of declared site indirects (FORMALISMO_LONGO Part XII, #206).

Site administration, topography, laboratory, QSMS and site mobilisation are
real costs that the exact ledger only carries when the project **declares**
them. Each declared line ``l`` has one driver:

- ``perm``: a monthly cost per sub-category ``k`` in MO, EQ, COMB, VM, charged
  every week ``j`` the site is mobilised: ``gamma_l^k = Gamma_l^{k,mensal} / s_mes``
  with ``s_mes = 1461/336`` (XII.3);
- ``onetime``: ``c_l^mob`` in the first mobilised week and ``c_l^demob`` in the
  last one (they add up when the site is mobilised a single week).

Every posting is ``INDIRECT`` by nature and keeps the sub-category as its
markup category (XII.4): MO, EQ and COMB take their own category layers, VM
and the one-off events take IND. Nothing is dimensioned, defaulted or
estimated here: teams, salaries, monthly costs and the mobilised window are
declared with provenance, as exact decimal or rational strings. A missing or
inexact field raises and no journal exists.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from fractions import Fraction
from typing import Literal, cast

from .catalog_cost_envelope import S_MES
from .contractual_cost_ledger import CostPosting, ExclusiveCostLedger, PostingNature

SCHEMA = "concilium.n10.site-indirects.v1"
SubCategory = Literal["MO", "EQ", "COMB", "VM"]
SUB_CATEGORIES: tuple[SubCategory, ...] = ("MO", "EQ", "COMB", "VM")
# XII.4: each sub-category is marked up by its own category; VM takes IND.
LEDGER_CATEGORY: dict[str, Literal["MO", "EQ", "COMB", "IND"]] = {
    "MO": "MO",
    "EQ": "EQ",
    "COMB": "COMB",
    "VM": "IND",
}
EVENT_PREFIX = "SITE_INDIRECT"


class SiteIndirectDeclarationError(ValueError):
    """The site-indirects declaration is missing, inexact or inconsistent."""


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SiteIndirectDeclarationError(f"{label} must be nonempty text")
    return value.strip()


def _amount(value: object, label: str) -> Fraction:
    if not isinstance(value, str) or not value.strip():
        raise SiteIndirectDeclarationError(f"{label} must be an exact decimal or rational string")
    try:
        amount = Fraction(value.strip())
    except (ValueError, ZeroDivisionError) as exc:
        raise SiteIndirectDeclarationError(f"{label} must be an exact decimal or rational string") from exc
    if amount < 0:
        raise SiteIndirectDeclarationError(f"{label} must be nonnegative")
    return amount


def _mapping(value: object, label: str, fields: set[str]) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise SiteIndirectDeclarationError(f"{label} must be a JSON object with string keys")
    if set(value) != fields:
        raise SiteIndirectDeclarationError(f"{label} must declare exactly {', '.join(sorted(fields))}")
    return cast(Mapping[str, object], value)


def _iso_monday(week: object, label: str) -> date:
    if (
        not isinstance(week, str)
        or len(week) != 8
        or week[4:6] != "-W"
        or not week[:4].isdigit()
        or not week[6:].isdigit()
    ):
        raise SiteIndirectDeclarationError(f"{label} must be an ISO week YYYY-Www")
    try:
        return date.fromisocalendar(int(week[:4]), int(week[6:]), 1)
    except ValueError as exc:
        raise SiteIndirectDeclarationError(f"{label} is not a valid ISO week") from exc


def enumerate_iso_weeks(first: object, last: object) -> tuple[str, ...]:
    """Every ISO week from ``first`` to ``last``, inclusive and contiguous."""
    start = _iso_monday(first, "mobilised_weeks.first")
    end = _iso_monday(last, "mobilised_weeks.last")
    if end < start:
        raise SiteIndirectDeclarationError("mobilised_weeks.last precedes mobilised_weeks.first")
    weeks: list[str] = []
    monday = start
    while monday <= end:
        year, number, _ = monday.isocalendar()
        weeks.append(f"{year}-W{number:02d}")
        monday += timedelta(weeks=1)
    return tuple(weeks)


@dataclass(frozen=True)
class SiteIndirectLine:
    """One declared indirect line ``l`` with its driver (XII.2)."""

    line_id: str
    driver: Literal["perm", "onetime"]
    source: str
    monthly: tuple[tuple[SubCategory, Fraction], ...] = ()
    mobilize: Fraction | None = None
    demobilize: Fraction | None = None

    def __post_init__(self) -> None:
        if any(not isinstance(v, str) or not v.strip() for v in (self.line_id, self.source)):
            raise ValueError("site indirect line needs an identity and a source")
        if self.driver == "perm":
            if tuple(k for k, _ in self.monthly) != SUB_CATEGORIES:
                raise ValueError(f"{self.line_id}: perm line declares monthly MO, EQ, COMB and VM")
            if self.mobilize is not None or self.demobilize is not None:
                raise ValueError(f"{self.line_id}: perm line has no one-off events")
            amounts: tuple[Fraction | None, ...] = tuple(amount for _, amount in self.monthly)
        elif self.driver == "onetime":
            if self.monthly:
                raise ValueError(f"{self.line_id}: onetime line has no monthly cost")
            amounts = (self.mobilize, self.demobilize)
        else:
            raise ValueError(f"{self.line_id}: driver must be perm or onetime")
        if any(type(amount) is not Fraction or amount < 0 for amount in amounts):
            raise ValueError(f"{self.line_id}: amounts must be exact nonnegative fractions")


@dataclass(frozen=True)
class SiteIndirectDeclaration:
    """Declared lines, mobilised window and provenance. Never a derived estimate."""

    lines: tuple[SiteIndirectLine, ...]
    calendar_weeks: tuple[str, ...]
    currency: str
    source: str
    reference_id: str

    def __post_init__(self) -> None:
        if not self.lines or any(not isinstance(line, SiteIndirectLine) for line in self.lines):
            raise ValueError("site indirects need at least one typed declared line")
        ids = [line.line_id for line in self.lines]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate site indirect line")
        if (
            not self.calendar_weeks
            or len(set(self.calendar_weeks)) != len(self.calendar_weeks)
            or any(not isinstance(week, str) or not week.strip() for week in self.calendar_weeks)
        ):
            raise ValueError("site indirects need a nonempty mobilised window of unique weeks")
        if any(not isinstance(v, str) or not v.strip() for v in (self.currency, self.source, self.reference_id)):
            raise ValueError("site indirects need currency, source and reference")


def parse_site_indirects_declaration(raw: object) -> SiteIndirectDeclaration:
    """Typed declaration from plain JSON; exact strings only, nothing defaulted."""
    doc = _mapping(raw, "site_indirects", {"schema", "currency", "source", "reference_id", "mobilised_weeks", "lines"})
    if doc["schema"] != SCHEMA:
        raise SiteIndirectDeclarationError(f"site_indirects.schema must be {SCHEMA}")
    window = _mapping(doc["mobilised_weeks"], "site_indirects.mobilised_weeks", {"first", "last"})
    weeks = enumerate_iso_weeks(window["first"], window["last"])
    rows = doc["lines"]
    if not isinstance(rows, list) or not rows:
        raise SiteIndirectDeclarationError("site_indirects.lines must declare at least one line")
    lines: list[SiteIndirectLine] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        label = f"site_indirects.lines[{index}]"
        driver = row.get("driver") if isinstance(row, Mapping) else None
        if driver == "perm":
            line = _mapping(row, label, {"line_id", "driver", "source", "monthly"})
            monthly_raw = _mapping(line["monthly"], f"{label}.monthly", set(SUB_CATEGORIES))
            parsed = SiteIndirectLine(
                line_id=_text(line["line_id"], f"{label}.line_id"),
                driver="perm",
                source=_text(line["source"], f"{label}.source"),
                monthly=tuple((k, _amount(monthly_raw[k], f"{label}.monthly.{k}")) for k in SUB_CATEGORIES),
            )
        elif driver == "onetime":
            line = _mapping(row, label, {"line_id", "driver", "source", "mobilize", "demobilize"})
            parsed = SiteIndirectLine(
                line_id=_text(line["line_id"], f"{label}.line_id"),
                driver="onetime",
                source=_text(line["source"], f"{label}.source"),
                mobilize=_amount(line["mobilize"], f"{label}.mobilize"),
                demobilize=_amount(line["demobilize"], f"{label}.demobilize"),
            )
        else:
            raise SiteIndirectDeclarationError(f"{label}.driver must be perm or onetime")
        if parsed.line_id in seen:
            raise SiteIndirectDeclarationError(f"duplicate site indirect line {parsed.line_id}")
        seen.add(parsed.line_id)
        lines.append(parsed)
    return SiteIndirectDeclaration(
        lines=tuple(lines),
        calendar_weeks=weeks,
        currency=_text(doc["currency"], "site_indirects.currency"),
        source=_text(doc["source"], "site_indirects.source"),
        reference_id=_text(doc["reference_id"], "site_indirects.reference_id"),
    )


def site_indirect_postings(declaration: SiteIndirectDeclaration) -> tuple[CostPosting, ...]:
    """The exact postings the declaration justifies; zero amounts post nothing."""
    if not isinstance(declaration, SiteIndirectDeclaration):
        raise ValueError("typed site-indirects declaration required")
    weeks = declaration.calendar_weeks
    postings: list[CostPosting] = []
    for line in declaration.lines:
        source = f"{EVENT_PREFIX}:{line.line_id}"
        if line.driver == "perm":
            for sub, monthly in line.monthly:
                weekly = monthly / S_MES
                if weekly == 0:
                    continue
                postings.extend(
                    CostPosting(
                        (EVENT_PREFIX, line.line_id, sub, week),
                        PostingNature.INDIRECT,
                        LEDGER_CATEGORY[sub],
                        weekly,
                        source,
                        week,
                    )
                    for week in weeks
                )
        else:
            for event, amount, week in (
                ("MOB", line.mobilize, weeks[0]),
                ("DEMOB", line.demobilize, weeks[-1]),
            ):
                if amount:
                    postings.append(
                        CostPosting(
                            (EVENT_PREFIX, line.line_id, event), PostingNature.INDIRECT, "IND", amount, source, week
                        )
                    )
    return tuple(postings)


@dataclass(frozen=True)
class SiteIndirectJournal:
    """Base ledger plus exactly the declared site-indirect postings."""

    ledger: ExclusiveCostLedger
    declaration: SiteIndirectDeclaration
    authority: str = "SITE_INDIRECTS_DECLARED_PREVIEW_NOT_PROJECT_GO"

    @property
    def postings(self) -> tuple[CostPosting, ...]:
        return tuple(row for row in self.ledger.postings if row.event_id[0] == EVENT_PREFIX)

    @property
    def cost(self) -> Fraction:
        return sum((row.amount for row in self.postings), Fraction(0))

    def cost_by_line(self) -> dict[str, dict[str, Fraction]]:
        """``C_l^{ind,o}`` split by ledger category, for every declared line."""
        totals: dict[str, dict[str, Fraction]] = {line.line_id: {} for line in self.declaration.lines}
        for row in self.postings:
            line = totals[row.event_id[1]]
            line[row.category] = line.get(row.category, Fraction(0)) + row.amount
        return totals


def post_exact_site_indirects(
    base: ExclusiveCostLedger,
    declaration: SiteIndirectDeclaration,
) -> SiteIndirectJournal:
    """Append the declared site indirects once; direct cost is left untouched."""
    if not isinstance(base, ExclusiveCostLedger):
        raise ValueError("exact base ledger required")
    if any(row.event_id[0] == EVENT_PREFIX for row in base.postings):
        raise ValueError("base ledger already carries site indirects")
    added = site_indirect_postings(declaration)
    ledger = ExclusiveCostLedger(base.postings + added, contract_scope=base.contract_scope)
    if ledger.direct != base.direct or ledger.indirect != base.indirect + sum(
        (row.amount for row in added), Fraction(0)
    ):
        raise ValueError("site indirect postings did not reconcile to the exclusive ledger")
    return SiteIndirectJournal(ledger, declaration)


def weeks_cover(calendar_weeks: Sequence[str], required: Sequence[str]) -> bool:
    """True when every required week lies in the declared mobilised window."""
    return set(required) <= set(calendar_weeks)
