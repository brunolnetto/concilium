"""DuckDB-backed catalog query engine — ADR-100 — normalizadores de linha (cpu/insumo/produtividade/funcao)."""

from __future__ import annotations

import json


def _cpu_row(raw: dict) -> tuple[str, str, str, str, str]:
    return (
        str(raw.get("codigo") or raw.get("id") or raw.get("cpu_id") or ""),
        str(raw.get("descricao") or ""),
        str(raw.get("categoria") or ""),
        str(raw.get("unidade") or ""),
        json.dumps(raw, ensure_ascii=False),
    )


def _insumo_row(raw: dict, tipo: str) -> tuple[str, str, str, str]:
    return (
        str(raw.get("id") or raw.get("codigo") or ""),
        str(raw.get("descricao") or ""),
        tipo,
        json.dumps(raw, ensure_ascii=False),
    )


def _prod_row(raw: dict) -> tuple[str, str, str]:
    return (
        str(raw.get("id") or raw.get("producao_id") or ""),
        str(raw.get("cpu_id") or raw.get("codigo_cpu") or ""),
        json.dumps(raw, ensure_ascii=False),
    )


def _funcao_row(raw: dict) -> tuple[str, str, str]:
    return (
        str(raw.get("id") or ""),
        str(raw.get("descricao") or ""),
        json.dumps(raw, ensure_ascii=False),
    )


def _first_field(d: dict, *keys: str, default: object = 0):
    """Retorna o valor da primeira chave presente e truthy em ``d``, ou ``default``.

    Colapsa cadeias `d.get(k1) or d.get(k2) or default` em uma única chamada.
    """
    for k in keys:
        v = d.get(k)
        if v:
            return v
    return default


