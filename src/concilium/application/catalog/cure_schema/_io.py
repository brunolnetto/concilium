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


def _persist_entity_files(
    entries: list[tuple[Path, dict]], apply: bool, catalog_root: Path | None = None
) -> int:
    if not apply:
        return 0
    from concilium.application.runtime.mixins._catalog_storage import (
        catalog_storage_backend,
        gravar_catalogo_blob,
    )
    use_storage = catalog_root is not None and catalog_storage_backend() != "filesystem"
    written = 0
    for file_path, payload in entries:
        content = (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        if use_storage:
            relative = str(file_path.relative_to(catalog_root))  # type: ignore[arg-type]
            gravar_catalogo_blob(catalog_root.parent.parent, catalog_root.name, relative, content)  # type: ignore[union-attr]
            written += 1
        else:
            should_write = True
            try:
                current = json.loads(file_path.read_text(encoding="utf-8"))
                should_write = current != payload
            except Exception:
                should_write = True
            if should_write:
                file_path.write_bytes(content)
                written += 1
    return written


