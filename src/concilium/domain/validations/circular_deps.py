"""ADR-032 §D5 — Detecção de Dependência Circular entre CPUs e Insumos.

Implementa busca em profundidade (DFS) sobre o grafo de composição de CPUs
para detectar loops antes que sejam persistidos no catálogo.

Um loop ocorre quando:
    CPU-A -> Insumo-X (cujo preço deriva de) CPU-B -> Insumo-Y -> CPU-A

Uso:
    from concilium.domain.validations.circular_deps import verificar_ciclos_cpu

    erros = verificar_ciclos_cpu(cpu_id="ESCO-CARGA-1CAT", catalogo=catalogo_dict)
    if erros:
        raise ValueError(erros[0])
"""

from __future__ import annotations


def _construir_grafo_cpus(catalogo: dict) -> dict[str, set[str]]:
    """Constrói grafo de dependências CPU -> set[CPU_ids_referenciadas].

    Para cada CPU, os nós adjacentes são:
    - CPUs referenciadas por insumos do tipo TERCEIRIZADO (composição via sub-CPU)
    - CPUs cujo `cpu_referencia_id` aponta para outra CPU
    """
    # Mapa insumo_id -> cpu_id (insumos que são proxy de outra CPU)
    insumo_para_cpu: dict[str, str] = {}
    for cpu in catalogo.get("cpus", []):
        ref_id = cpu.get("cpu_referencia_id")
        if ref_id:
            # Insumos que representam o custo desta CPU sub-contratada
            for item in cpu.get("composicao_itens", []):
                if item.get("categoria_custo") == "TERCEIRIZADO":
                    insumo_para_cpu[item["insumo_id"]] = cpu["codigo"]

    grafo: dict[str, set[str]] = {}
    for cpu in catalogo.get("cpus", []):
        vizinhos: set[str] = set()
        # Dependências via cpu_referencia_id
        ref = cpu.get("cpu_referencia_id")
        if ref:
            vizinhos.add(ref)
        # Dependências via insumos TERCEIRIZADO que mapeiam outra CPU
        for item in cpu.get("composicao_itens", []):
            cpu_dep = insumo_para_cpu.get(item.get("insumo_id", ""))
            if cpu_dep and cpu_dep != cpu["codigo"]:
                vizinhos.add(cpu_dep)
        grafo[cpu["codigo"]] = vizinhos

    return grafo


def _dfs_detecta_ciclo(
    no: str,
    grafo: dict[str, set[str]],
    visitados: set[str],
    stack: list[str],
) -> list[str] | None:
    """DFS recursiva. Retorna o caminho do ciclo ou None."""
    visitados.add(no)
    stack.append(no)

    for vizinho in grafo.get(no, set()):
        if vizinho not in visitados:
            resultado = _dfs_detecta_ciclo(vizinho, grafo, visitados, stack)
            if resultado is not None:
                return resultado
        elif vizinho in stack:
            # Ciclo encontrado — retorna o caminho a partir do nó que fecha o loop
            idx = stack.index(vizinho)
            return stack[idx:] + [vizinho]

    stack.pop()
    return None


def verificar_ciclos_cpu(
    catalogo: dict,
    cpu_id: str | None = None,
) -> list[str]:
    """Verifica dependências circulares no catálogo de CPUs.

    Args:
        catalogo: Dicionário de catálogo com chave "cpus".
        cpu_id:   Se informado, verifica apenas a partir desta CPU.
                  Se None, verifica todo o grafo.

    Returns:
        Lista de mensagens de erro descrevendo cada ciclo encontrado.
        Lista vazia indica que não há ciclos.
    """
    grafo = _construir_grafo_cpus(catalogo)
    erros: list[str] = []
    visitados: set[str] = set()

    nos = [cpu_id] if cpu_id else list(grafo.keys())

    for no in nos:
        if no not in visitados and no in grafo:
            ciclo = _dfs_detecta_ciclo(no, grafo, visitados, [])
            if ciclo:
                caminho = " -> ".join(ciclo)
                erros.append(f"Dependência circular detectada na composição de CPUs: {caminho}")

    return erros


def validar_sem_ciclos(catalogo: dict, cpu_id: str | None = None) -> None:
    """Levanta ValueError se houver ciclo no catálogo.

    Conveniente para uso como guard em operações de criação/atualização.

    Raises:
        ValueError: com descrição do ciclo encontrado.
    """
    erros = verificar_ciclos_cpu(catalogo, cpu_id)
    if erros:
        raise ValueError("\n".join(erros))
