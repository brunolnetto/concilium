"""Extrai referÃªncias de catÃ¡logo (CPUs, produÃ§Ãµes, insumos) para um benchmark."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_DEFAULT_ROOT = Path(__file__).resolve().parents[5]


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


def _safe_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def extract_cpu_references(slug: str, root: Path | None = None) -> dict[str, Any]:
    """Extrai definiÃ§Ãµes de CPUs do catÃ¡logo usadas no benchmark.

    Args:
        slug: ex. "CTC"
        root: raiz do repositÃ³rio

    ADR-053 (Fase 3): CPU deve referenciar produtividade exclusivamente via
                      producao_id_ref. Campos legados não são usados.
    """
    r = root or _DEFAULT_ROOT
    bench_root = r / "benchmarks" / "data"
    cpus_dir = r / "config" / "catalogos" / "mendeslobo" / "cpus"
    produtividades_dir = r / "config" / "catalogos" / "mendeslobo" / "produtividades"

    referencia = _load_json(bench_root / slug / "referencia.json")
    eap_itens = referencia.get("eap") or []
    cpu_ids = {item.get("cpu_id") for item in eap_itens if item.get("cpu_id")}

    catalog_cpus: dict[str, Any] = {}
    for cpu_id in sorted(cpu_ids):
        cpu_def = _load_json(cpus_dir / f"{cpu_id}.json")
        if not cpu_def:
            catalog_cpus[cpu_id] = {"status": "NAO_ENCONTRADO_NO_CATALOGO"}
            continue

        producao_horaria_final = None
        producoes: dict[str, Any] = {}

        producao_id_ref = cpu_def.get("producao_id_ref")
        if not producao_id_ref:
            catalog_cpus[cpu_id] = {"status": "ERRO_SEM_PRODUCAO_ID_REF"}
            continue

        prod_def = _load_json(produtividades_dir / f"{producao_id_ref}.json")
        if not prod_def:
            catalog_cpus[cpu_id] = {"status": "ERRO_PRODUTIVIDADE_NAO_ENCONTRADA", "producao_id_ref": producao_id_ref}
            continue

        producao_horaria_final = _safe_float(prod_def.get("producao_horaria"))
        producoes[producao_id_ref] = {
            "descricao": prod_def.get("descricao"),
            "producao_horaria": producao_horaria_final,
            "cpu_ids": prod_def.get("cpu_ids", []),
        }

        catalog_cpus[cpu_id] = {
            "descricao": cpu_def.get("descricao"),
            "unidade": cpu_def.get("unidade"),
            "producao_horaria": producao_horaria_final,
            "producao_id_ref": producao_id_ref,
            "producoes": producoes,
        }

    return {
        "slug": slug,
        "cpu_referencias": {
            "total": len(cpu_ids),
            "catalog_cpus": catalog_cpus,
        },
    }
