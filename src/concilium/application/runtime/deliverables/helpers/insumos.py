"""Helpers de carga/deduplicação de insumos."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast


def ingest_insumos(data: object, insumos: list) -> None:
    if isinstance(data, list):
        insumos.extend(data)
    elif isinstance(data, dict):
        data_dict = cast("dict[str, Any]", data)
        nested = data_dict.get("insumos")
        if nested is not None:
            insumos.extend(nested)
        else:
            insumos.append(data_dict)


def load_insumos_subdir(sub: Path, insumos: list) -> None:
    for file_path in sub.glob("*.json"):
        try:
            ingest_insumos(json.loads(file_path.read_text(encoding="utf-8")), insumos)
        except Exception:
            pass


def dedup_insumos(insumos: list) -> list:
    seen: set = set()
    unique = []
    for item in insumos:
        item_id = item.get("id") or item.get("codigo")
        if item_id and item_id not in seen:
            seen.add(item_id)
            unique.append(item)
    return unique
