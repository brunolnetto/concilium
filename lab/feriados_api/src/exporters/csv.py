from __future__ import annotations

import csv
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Iterable, Any


def export_csv(
    records: Iterable[Any],
    path: str | Path,
):
    """
    Export dataclass objects to CSV.
    """

    path = Path(path)

    iterator = iter(records)

    try:
        first = next(iterator)

    except StopIteration:
        return

    if not is_dataclass(first):
        raise TypeError(
            "CSV exporter expects dataclass objects"
        )

    rows = [
        asdict(first)
    ]

    rows.extend(
        asdict(item)
        for item in iterator
    )

    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=rows[0].keys(),
        )

        writer.writeheader()

        writer.writerows(rows)
