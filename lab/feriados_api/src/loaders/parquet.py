from __future__ import annotations

from pathlib import Path

from ..models import CalendarDay
from ..exporters.polars import calendar_to_polars


def calendar_to_parquet(
    days: list[CalendarDay],
    path: str | Path,
):

    df = calendar_to_polars(days)

    df.write_parquet(
        path
    )
