"""ADR-063 §D4: Validação de DAG para predecessão de itens EAP."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from concilium.domain.models.canonical import EapItem


class CicloPredecessaoError(ValueError):
    """Lançado quando o grafo de predecessão tem ciclo."""


def _dag_build_id_set(eap: list) -> set:
    ids = set()
    for item in eap:
        ids.add(item.item_id)
    return ids


def _dag_validate_refs(eap: list, ids: set) -> None:
    for item in eap:
        desconhecidos = [p for p in item.predecessores if p not in ids]
        if desconhecidos:
            raise ValueError(f"Item '{item.item_id}' referencia predecessores inexistentes: {desconhecidos}")


def _dag_build_indegree(eap: list) -> dict:
    in_degree: dict[str, int] = {}
    for item in eap:
        in_degree[item.item_id] = len(item.predecessores)
    return in_degree


def _dag_initial_queue(in_degree: dict) -> list:
    queue = []
    for nid, deg in in_degree.items():
        if deg == 0:
            queue.append(nid)
    return queue


def _dag_kahn_traverse(eap: list, queue: list, in_degree: dict) -> int:
    visited = 0
    while queue:
        node = queue.pop(0)
        visited += 1
        for item in eap:
            if node in item.predecessores:
                in_degree[item.item_id] -= 1
                if in_degree[item.item_id] == 0:
                    queue.append(item.item_id)
    return visited


def validar_dag_predecessores(eap: list[EapItem]) -> None:
    """Valida que os predecessores dos itens EAP formam um DAG (sem ciclos).

    Raises:
        CicloPredecessaoError: Se detectar ciclo no grafo de predecessão.
        ValueError: Se predecessores referenciam item_id inexistente na EAP.
    """
    ids = _dag_build_id_set(eap)
    _dag_validate_refs(eap, ids)
    in_degree = _dag_build_indegree(eap)
    queue = _dag_initial_queue(in_degree)
    visited = _dag_kahn_traverse(eap, queue, in_degree)
    if visited != len(eap):
        raise CicloPredecessaoError("O grafo de predecessão contém ciclo(s). Verifique as dependências entre itens.")
