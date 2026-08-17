from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date

from ..models import HolidayRecord

# Two-stage conservative entity resolution.
#
# Stage 1 — exact name match, same date, any level/uf/ibge. Identical
# text (case/whitespace-insensitive) is unambiguous regardless of
# where it occurs — e.g. "Corpus Christi" recurring across dozens of
# cities on the same date is obviously one holiday, not one per city.
# Date is still required: "Dia do Evangélico" appears verbatim on both
# 23/01 (AC) and 30/11 (AP/DF/AL/TO) — same name, genuinely different
# occasions — so it correctly stays as two entries.
#
# Stage 2 — fuzzy match (>=90% similarity) within the exact same
# context (date, level, uf, ibge) for whatever stage 1 left ungrouped.
# This catches spelling variants of a single occurrence (e.g. "Quarta
# Feira de Cinzas" vs "Quarta-feira de Cinzas" in the same city) without
# the risk of matching across different real entities that merely have
# similar names (e.g. "Aniversário de Goiânia" vs "Aniversário de
# Manaus" score 63% similar but are different municipalities).
#
# Anything below the threshold, or with differing context, is left as
# a distinct entry rather than guessed — ambiguous cases (e.g. the bare
# name "Padroeira") stay unresolved.
SIMILARITY_THRESHOLD = 0.90


@dataclass(slots=True)
class HolidayOccurrence:

    uf: str | None

    ibge: int | None

    level: str

    is_facultativo: bool

    is_bancario: bool


@dataclass(slots=True)
class DimHoliday:

    # Natural key is (holiday_key, year) — holiday_key is a
    # deterministic slug of the canonical name, not a run-order
    # counter, so re-running the pipeline for the same year always
    # produces the same key and can be upserted instead of duplicated.

    holiday_key: str

    year: int

    canonical_name: str

    aliases: list[str]

    date: date

    # A single row can span several levels/ufs/facultativo statuses at
    # once (e.g. Corpus Christi is ESTADUAL in DF/RJ, MUNICIPAL in many
    # capitals, and a NACIONAL facultativo elsewhere) — kept as a list
    # of structs, not parallel arrays, so each occurrence's fields stay
    # correctly tied together.
    occurrences: list[HolidayOccurrence]


def _normalize(name: str) -> str:

    return " ".join(name.strip().lower().split())


def _slugify(name: str) -> str:

    ascii_name = (
        unicodedata.normalize("NFKD", name)
        .encode("ascii", "ignore")
        .decode("ascii")
    )

    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")

    return slug or "holiday"


def _levenshtein(a: str, b: str) -> int:

    if a == b:
        return 0

    previous_row = list(range(len(b) + 1))

    for i, char_a in enumerate(a, start=1):

        current_row = [i] + [0] * len(b)

        for j, char_b in enumerate(b, start=1):

            cost = 0 if char_a == char_b else 1

            current_row[j] = min(
                previous_row[j] + 1,
                current_row[j - 1] + 1,
                previous_row[j - 1] + cost,
            )

        previous_row = current_row

    return previous_row[-1]


def _similarity(a: str, b: str) -> float:

    longest = max(len(a), len(b))

    if longest == 0:
        return 1.0

    distance = _levenshtein(a.lower(), b.lower())

    return 1 - distance / longest


def _build_cluster(
    cluster: list[HolidayRecord],
    dim_holidays: list[DimHoliday],
    used_keys: dict[tuple[int, str], int],
) -> None:

    names = sorted(
        {record.name for record in cluster},
        key=len,
        reverse=True,
    )

    canonical_name = names[0]

    slug = _slugify(canonical_name)

    year = cluster[0].year

    # Scoped by year: the same holiday recurring every year must keep
    # the same holiday_key (year already disambiguates it in the
    # natural key). Only two genuinely different holidays colliding on
    # the same slug WITHIN THE SAME YEAR get a numeric suffix.
    used_keys[(year, slug)] = used_keys.get((year, slug), 0) + 1

    holiday_key = (
        slug
        if used_keys[(year, slug)] == 1
        else f"{slug}-{used_keys[(year, slug)]}"
    )

    dim_holidays.append(
        DimHoliday(
            holiday_key=holiday_key,
            year=cluster[0].year,
            canonical_name=canonical_name,
            aliases=names,
            date=cluster[0].date,
            occurrences=[
                HolidayOccurrence(
                    uf=record.uf,
                    ibge=record.ibge,
                    level=record.level,
                    is_facultativo=record.is_facultativo,
                    is_bancario=record.is_bancario,
                )
                for record in cluster
            ],
        )
    )

    for record in cluster:
        record.holiday_key = holiday_key


def build_dim_holiday(
    records: list[HolidayRecord],
) -> list[DimHoliday]:

    # Also mutates `holiday_key` in place on each record, so the flat
    # `holidays` export keeps its FK into dim_holiday in sync.

    dim_holidays: list[DimHoliday] = []
    used_keys: dict[tuple[int, str], int] = {}


    # Stage 1 — exact name, same date, any context.

    exact_groups: dict[tuple, list[HolidayRecord]] = {}

    for record in records:

        key = (
            record.date,
            _normalize(record.name),
        )

        exact_groups.setdefault(key, []).append(record)


    remaining: list[HolidayRecord] = []

    for group in exact_groups.values():

        if len(group) > 1:
            _build_cluster(group, dim_holidays, used_keys)
        else:
            remaining.extend(group)


    # Stage 2 — fuzzy match, same exact context.

    context_groups: dict[tuple, list[HolidayRecord]] = {}

    for record in remaining:

        key = (
            record.date,
            record.level,
            record.uf,
            record.ibge,
        )

        context_groups.setdefault(key, []).append(record)


    for group in context_groups.values():

        clusters: list[list[HolidayRecord]] = []

        for record in group:

            match = next(
                (
                    cluster
                    for cluster in clusters
                    if _similarity(cluster[0].name, record.name)
                    >= SIMILARITY_THRESHOLD
                ),
                None,
            )

            if match is not None:
                match.append(record)
            else:
                clusters.append([record])


        for cluster in clusters:
            _build_cluster(cluster, dim_holidays, used_keys)


    return dim_holidays
