"""Curação do catálogo — parte extraída de cure_schema.py (grupo _io)."""

from __future__ import annotations

import json
from pathlib import Path

from ._core import ROOT


def _context_base(contexto_id: str) -> Path:
    base = ROOT / "config" / "catalogos" / contexto_id
    if not base.exists():
        raise FileNotFoundError(f"Contexto não encontrado: {contexto_id}")
    return base


def _load_entity_files(base: Path, subdirs: tuple[str, ...]) -> list[tuple[Path, dict]]:
    rows: list[tuple[Path, dict]] = []
    for subdir in subdirs:
        directory = base / subdir
        if not directory.exists():
            continue
        for file_path in sorted(directory.rglob("*.json")):
            if file_path.name.startswith("."):
                continue
            try:
                payload = json.loads(file_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(payload, dict):
                rows.append((file_path, payload))
    return rows


def _persist_entity_files(entries: list[tuple[Path, dict]], apply: bool) -> int:
    if not apply:
        return 0
    written = 0
    for file_path, payload in entries:
        should_write = True
        try:
            current = json.loads(file_path.read_text(encoding="utf-8"))
            should_write = current != payload
        except Exception:
            should_write = True
        if should_write:
            file_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            written += 1
    return written


