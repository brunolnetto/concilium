"""Helpers de serialização de deliverables."""

from __future__ import annotations

from uuid import UUID


def json_default(obj: object) -> object:
    if isinstance(obj, UUID):
        return str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")
