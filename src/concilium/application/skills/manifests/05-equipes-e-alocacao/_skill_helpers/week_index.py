"""Shared ISO-8601 week indexing for Skill 05 scheduling and pool economics."""
from __future__ import annotations

import datetime
import re

_ISO_WEEK = re.compile(r"^(\d{4})-W(\d{2})$")


def iso_week_index(value: str) -> int:
    """Return an absolute integer index for a valid ISO week (Monday-based).

    The epoch is ISO week 2000-W01. Invalid ISO dates/weeks are rejected rather
    than silently mapped to week zero, which can corrupt gaps across year ends.
    """
    if not isinstance(value, str):
        raise ValueError("ISO week must be text in YYYY-Www format")
    match = _ISO_WEEK.fullmatch(value.strip())
    if match is None:
        raise ValueError(f"invalid ISO week format: {value!r}")
    year, week = (int(part) for part in match.groups())
    try:
        monday = datetime.date.fromisocalendar(year, week, 1)
    except ValueError as exc:
        raise ValueError(f"invalid ISO week: {value!r}") from exc
    epoch = datetime.date.fromisocalendar(2000, 1, 1)
    return (monday - epoch).days // 7
