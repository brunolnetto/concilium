"""DuckDB-backed catalog query engine — ADR-100 — carregamento de linhas a partir de arquivos/diretórios do catálogo."""

from __future__ import annotations

import json
from pathlib import Path

from ._rows import _cpu_row, _insumo_row, _prod_row


def _load_cpu_rows_from_dir(cpus_dir: Path) -> list[tuple[str, str, str, str, str]]:
    """Layout de diretório: cpus/<ID>.json — cada arquivo é uma CPU individual."""
    rows: list[tuple[str, str, str, str, str]] = []
    for f in sorted(cpus_dir.glob("*.json")):
        try:
            raw = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                rows.append(_cpu_row(raw))
        except Exception:
            continue
    return rows


def _load_cpu_rows_from_file(cpus_file: Path) -> list[tuple[str, str, str, str, str]]:
    """Layout de arquivo único: cpus.json contendo uma lista de CPUs."""
    rows: list[tuple[str, str, str, str, str]] = []
    try:
        payload = json.loads(cpus_file.read_text(encoding="utf-8"))
        cpus = payload.get("cpus", payload) if isinstance(payload, dict) else payload
        for raw in cpus or []:
            if isinstance(raw, dict):
                rows.append(_cpu_row(raw))
    except Exception:
        pass
    return rows


def _load_insumo_rows_layout_a(ins_dir: Path) -> list[tuple[str, str, str, str]]:
    """Layout A: insumos/<tipo>/<ID>.json — cada arquivo é um insumo individual."""
    rows: list[tuple[str, str, str, str]] = []
    for tipo_dir in sorted(ins_dir.iterdir()):
        if not tipo_dir.is_dir():
            continue
        tipo = tipo_dir.name
        for f in sorted(tipo_dir.glob("*.json")):
            try:
                raw = json.loads(f.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    rows.append(_insumo_row(raw, tipo))
            except Exception:
                continue
    return rows


def _load_insumo_rows_layout_b(ins_dir: Path) -> list[tuple[str, str, str, str]]:
    """Layout B: insumos/<tipo>.json — cada arquivo é uma lista por tipo."""
    rows: list[tuple[str, str, str, str]] = []
    for f in sorted(ins_dir.glob("*.json")):
        tipo = f.stem
        try:
            payload = json.loads(f.read_text(encoding="utf-8"))
            items = payload.get("insumos", payload) if isinstance(payload, dict) else payload
            for raw in items or []:
                if isinstance(raw, dict):
                    rows.append(_insumo_row(raw, tipo))
        except Exception:
            continue
    return rows


def _load_insumo_rows(ins_dir: Path) -> list[tuple[str, str, str, str]]:
    """Detecta o layout A ou B do diretório de insumos e carrega as rows."""
    if not ins_dir.exists():
        return []
    has_subdirs = any(d.is_dir() for d in ins_dir.iterdir())
    if has_subdirs:
        return _load_insumo_rows_layout_a(ins_dir)
    return _load_insumo_rows_layout_b(ins_dir)


def _load_prod_rows_from_dir(prod_dir: Path) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for f in sorted(prod_dir.glob("*.json")):
        try:
            raw = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                rows.append(_prod_row(raw))
        except Exception:
            continue
    return rows


def _load_prod_rows_from_dirs(base_dir: Path) -> list[tuple[str, str, str]]:
    """Mescla 'produtividades/' (layout atual) e 'producoes/' (legado, robustez apenas)."""
    rows: list[tuple[str, str, str]] = []
    for dir_name in ("produtividades", "producoes"):
        prod_dir = base_dir / dir_name
        if prod_dir.exists():
            rows.extend(_load_prod_rows_from_dir(prod_dir))
    return rows


def _load_prod_rows_fallback_file(prod_file: Path) -> list[tuple[str, str, str]]:
    """Fallback: arquivo único produtividades.json contendo uma lista."""
    rows: list[tuple[str, str, str]] = []
    if not prod_file.exists():
        return rows
    try:
        payload = json.loads(prod_file.read_text(encoding="utf-8"))
        items = payload.get("produtividades", payload) if isinstance(payload, dict) else payload
        for raw in items or []:
            if isinstance(raw, dict):
                rows.append(_prod_row(raw))
    except Exception:
        pass
    return rows


