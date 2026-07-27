"""Skill 05 — ADR-159: popula composicao_funcoes_mo/composicao_equipamentos_eq
(ADR-156/157) em RecursoContrato a partir da composição real do catálogo.

Puramente descritivo — não recalcula nenhum custo. Reaproveita a mesma cadeia de
lookup (cpu -> produção -> composicao_padrao_equipe) já usada por
_derive_item_tipo_requerido, e _tipo_recurso_fungivel (importada, não
reimplementada) para casamento exato de tipo_id — zero risco de divergência de
hash em relação ao tipo_id já usado para construir os contratos.
"""

from __future__ import annotations

from typing import Any

from concilium.domain.models.canonical import RecursoContrato

from ._pool_contrato_construcao import (  # ty: ignore[unresolved-import]
    _positive_qty,
    _safe_str_field,
    _tipo_recurso_fungivel,
)


def _obter_composicao_bruta(item: Any, cpu_lookup: dict, prod_lookup: dict) -> dict:
    """Mesma cadeia de lookup de `_derive_item_tipo_requerido` — cpu -> produção -> composição."""
    cpu = cpu_lookup.get(item.cpu_id, {})
    prod_id = cpu.get("producao_id_ref")
    prod = prod_lookup.get(prod_id or "", {})
    return prod.get("composicao_padrao_equipe", {}) if prod else {}


def _extrair_funcoes_mo(composicao: dict) -> dict[str, int]:
    return {
        _safe_str_field(f, "funcao_id"): int(_positive_qty(f, "num_pessoas"))
        for f in (composicao.get("funcoes") or [])
        if _safe_str_field(f, "funcao_id")
    }


def _extrair_equipamentos_eq(composicao: dict) -> dict[str, int]:
    return {
        _safe_str_field(e, "equip_id"): int(_positive_qty(e, "num_unidades"))
        for e in (composicao.get("equipamentos") or [])
        if _safe_str_field(e, "equip_id")
    }


def enriquecer_composicao_por_tipo(
    contratos: list[RecursoContrato],
    eap_items: Any,
    sched_lookup: dict,
    cpu_lookup: dict,
    prod_lookup: dict,
) -> None:
    """Popula `composicao_funcoes_mo`/`composicao_equipamentos_eq` em cada
    `RecursoContrato` (ADR-156/157) — mutação in-place, mesmo padrão de outros
    enriquecimentos pós-hoc de skill-05 (ex.: `_aplicar_custo_instancial`).

    Puramente descritivo: nenhum campo de custo é alterado por esta função.
    """
    if not contratos:
        return
    contrato_por_tipo = {c.tipo_id: c for c in contratos}
    tipos_pendentes = set(contrato_por_tipo)
    for item in eap_items:
        if not tipos_pendentes:
            break
        if item.item_id not in sched_lookup:
            continue
        composicao = _obter_composicao_bruta(item, cpu_lookup, prod_lookup)
        if not composicao:
            continue
        tipo_id = _tipo_recurso_fungivel(str(item.cpu_id or ""), composicao)
        if tipo_id not in tipos_pendentes:
            continue
        contrato = contrato_por_tipo[tipo_id]
        contrato.composicao_funcoes_mo = _extrair_funcoes_mo(composicao)
        contrato.composicao_equipamentos_eq = _extrair_equipamentos_eq(composicao)
        tipos_pendentes.discard(tipo_id)
