from __future__ import annotations

import json

from dataclasses import asdict, is_dataclass
from pathlib import Path
from datetime import date, datetime
from typing import Iterable, Any


def json_serializer(value):

    if isinstance(
        value,
        (date, datetime),
    ):
        return value.isoformat()

    raise TypeError(
        f"Unsupported type: {type(value)}"
    )


def export_json(
    records: Iterable[Any],
    path: str | Path,
):
    """
    Export dataclass objects to JSON.
    """

    path = Path(path)

    payload = []

    for item in records:

        if not is_dataclass(item):
            raise TypeError(
                "JSON exporter expects dataclass objects"
            )

        payload.append(
            asdict(item)
        )

    with path.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            payload,
            file,
            ensure_ascii=False,
            indent=2,
            default=json_serializer,
        )
