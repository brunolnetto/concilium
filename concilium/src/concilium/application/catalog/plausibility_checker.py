"""Verificação de plausibilidade dos dados do catálogo."""

from __future__ import annotations

from typing import Any

from ._plausibility_checks import (
    Anomalia,
    _pc_check_equipe_refs,  # noqa: F401
    _pc_check_prod_item,
    _pc_check_prod_zscore,
    _pc_eq_diesel,
    _pc_eq_locacao,
    _pc_eq_zscore,
    _pc_mo_duplicatas,
    _pc_mo_encargos,
    _pc_mo_salario_minimo,
    _pc_mo_semantica,
    _pc_mo_staleness,
    _pc_mo_zscore,
    _pc_prod_vhs,  # noqa: F401
)


def _check_mao_obra(insumos: list[dict]) -> list[Anomalia]:
    anomalias: list[Anomalia] = []
    mo = [i for i in insumos if i.get("tipo") == "MAO_OBRA" and i.get("preco_unitario", 0) > 0]
    if not mo:
        return anomalias
    anomalias.extend(_pc_mo_zscore(mo))
    anomalias.extend(_pc_mo_salario_minimo(mo))
    anomalias.extend(_pc_mo_encargos(mo))
    anomalias.extend(_pc_mo_duplicatas(mo))
    anomalias.extend(_pc_mo_semantica(mo))
    anomalias.extend(_pc_mo_staleness(mo))
    return anomalias


def _check_equipamento(insumos: list[dict]) -> list[Anomalia]:
    anomalias: list[Anomalia] = []
    eq = [i for i in insumos if i.get("tipo") == "EQUIPAMENTO" and i.get("preco_unitario", 0) > 0]
    if not eq:
        return anomalias
    anomalias.extend(_pc_eq_diesel(eq))
    anomalias.extend(_pc_eq_zscore(eq))
    anomalias.extend(_pc_eq_locacao(eq))
    return anomalias


def _check_produtividades(producoes: list[dict], insumo_index: dict[str, dict]) -> list[Anomalia]:
    anomalias: list[Anomalia] = []
    for prod in producoes:
        anomalias.extend(_pc_check_prod_item(prod, insumo_index))
    anomalias.extend(_pc_check_prod_zscore(producoes))
    return anomalias


def _count_severidades(anomalias: list) -> tuple[int, int, int]:
    erros = avisos = infos = 0
    for a in anomalias:
        if a.severidade == "ERRO":
            erros += 1
        elif a.severidade == "AVISO":
            avisos += 1
        elif a.severidade == "INFO":
            infos += 1
    return erros, avisos, infos


def verificar_plausibilidade(
    insumos: list[dict],
    producoes: list[dict],
    cpus: list[dict] | None = None,
) -> dict[str, Any]:
    """Verifica plausibilidade física e estatística do catálogo."""
    insumo_index: dict = {i["codigo"]: i for i in insumos if i.get("codigo")}

    anomalias: list[Anomalia] = []
    anomalias += _check_mao_obra(insumos)
    anomalias += _check_equipamento(insumos)
    anomalias += _check_produtividades(producoes, insumo_index)

    por_tipo: dict[str, list[dict]] = {}
    for a in anomalias:
        por_tipo.setdefault(a.tipo, []).append(a.to_dict())

    erros, avisos, infos = _count_severidades(anomalias)
    return {
        "ok": erros == 0,
        "resumo": {
            "total_insumos": len(insumos),
            "total_producoes": len(producoes),
            "anomalias_total": len(anomalias),
            "erros": erros,
            "avisos": avisos,
            "infos": infos,
        },
        "anomalias": [a.to_dict() for a in anomalias],
        "por_tipo": por_tipo,
    }
