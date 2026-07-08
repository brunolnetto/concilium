"""Curação do catálogo — parte extraída de cure_schema.py (grupo _remap)."""

from __future__ import annotations


def _remap_code_value(value: object, remap: dict[str, str]) -> object:
    if isinstance(value, str) and value in remap:
        return remap[value]
    return value


def _remap_cpu_composicao_itens(cpus: list[dict], remap: dict[str, str]) -> None:
    for cpu in cpus:
        itens = cpu.get("composicao_itens")
        if isinstance(itens, list):
            for item in itens:
                if isinstance(item, dict):
                    item["insumo_id"] = _remap_code_value(item.get("insumo_id"), remap)


def _remap_equipe_ids(equipe: dict, remap: dict[str, str]) -> None:
    funcoes = equipe.get("funcoes")
    if isinstance(funcoes, list):
        for f in funcoes:
            if isinstance(f, dict):
                f["funcao_id"] = _remap_code_value(f.get("funcao_id"), remap)
    equipamentos = equipe.get("equipamentos")
    if isinstance(equipamentos, list):
        for e in equipamentos:
            if isinstance(e, dict):
                e["equip_id"] = _remap_code_value(e.get("equip_id"), remap)


def _remap_prod_variantes_ids(prod: dict, remap: dict[str, str]) -> None:
    variantes = prod.get("variantes")
    if not isinstance(variantes, list):
        return
    for var in variantes:
        if not isinstance(var, dict):
            continue
        v_eq = var.get("equipe")
        if not isinstance(v_eq, dict):
            continue
        _remap_equipe_ids(v_eq, remap)


def _remap_prods_ids(prods: list[dict], remap: dict[str, str]) -> None:
    for prod in prods:
        equipe = prod.get("composicao_padrao_equipe")
        if isinstance(equipe, dict):
            _remap_equipe_ids(equipe, remap)
        _remap_prod_variantes_ids(prod, remap)


def _apply_insumo_code_remap(cpus: list[dict], prods: list[dict], remap: dict[str, str]) -> None:
    if not remap:
        return
    _remap_cpu_composicao_itens(cpus, remap)
    _remap_prods_ids(prods, remap)


