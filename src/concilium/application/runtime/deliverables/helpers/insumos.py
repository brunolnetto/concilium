"""Helpers de carga/deduplicação de insumos."""

from __future__ import annotations

import json
from pathlib import Path


def ingest_insumos(data: object, insumos: list) -> None:
    if isinstance(data, list):
        insumos.extend(data)
    elif isinstance(data, dict) and "insumos" in data:
        insumos.extend(data["insumos"])
    elif isinstance(data, dict):
        insumos.append(data)


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
