"""Skill 06 (_precificacao) — Planejamento e BDI.

Extração de valor BDI e construção de lookups do catálogo.
"""

from __future__ import annotations

from typing import Any


def _get_bdi_value(manual: dict[str, Any], *keys: str, default: float = 0.0) -> float:
    for key in keys:
        if key in manual and manual.get(key) is not None:
            try:
                return float(manual.get(key) or 0.0)
            except Exception:
                continue
    return float(default)


def _build_lookups(catalogo: dict[str, Any]) -> tuple[dict[str, dict], dict[str, dict], dict[str, dict]]:
    """NEP-032: prod_lookup agora mapeia prod_id → full production dict (não mais float).

    O acesso ao valor_horario deve ser feito via prod.get("producao_horaria").
    Mantém retrocompatibilidade: prod_lookup.get(id) is None ainda funciona para
    verificar existência.
    """
    cpus = {c["codigo"]: c for c in catalogo.get("cpus", [])}
    insumos = {i["codigo"]: i for i in catalogo.get("insumos", [])}

    # Produtividades: dict completo por id (para precificação bottom-up, NEP-032)
    prods_raw = catalogo.get("produtividades", []) or catalogo.get("producoes", [])
    produtividades: dict[str, dict] = {}
    for p in prods_raw:
        pid = p.get("id")
        if not pid:
            continue
        # Normaliza campo legado
        if p.get("producao_horaria") is None and p.get("valor_horario") is not None:
            p = {**p, "producao_horaria": p["valor_horario"]}
        produtividades[pid] = p

    return cpus, insumos, produtividades


