"""ADR-063 §D4: Validação de DAG para predecessão de itens EAP."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from concilium.domain.models.canonical import EapItem


class CicloPredecessaoError(ValueError):
    """Lançado quando o grafo de predecessão tem ciclo."""


def validar_dag_predecessores(eap: list[EapItem]) -> None:
    """Valida que os predecessores dos itens EAP formam um DAG (sem ciclos).

    Raises:
        CicloPredecessaoError: Se detectar ciclo no grafo de predecessão.
        ValueError: Se predecessores referenciam item_id inexistente na EAP.
    """
    ids = {item.item_id for item in eap}

    for item in eap:
        desconhecidos = [p for p in item.predecessores if p not in ids]
        if desconhecidos:
            raise ValueError(f"Item '{item.item_id}' referencia predecessores inexistentes: {desconhecidos}")

    # Kahn's algorithm para detecção de ciclo
    in_degree: dict[str, int] = {item.item_id: 0 for item in eap}
    for item in eap:
        in_degree[item.item_id] = len(item.predecessores)

    queue = [nid for nid, deg in in_degree.items() if deg == 0]
    visited = 0

    while queue:
        node = queue.pop(0)
        visited += 1
        # Find all nodes that have `node` as predecessor
        for item in eap:
            if node in item.predecessores:
                in_degree[item.item_id] -= 1
                if in_degree[item.item_id] == 0:
                    queue.append(item.item_id)

    if visited != len(eap):
        raise CicloPredecessaoError("O grafo de predecessão contém ciclo(s). Verifique as dependências entre itens.")
