#!/usr/bin/env python3
"""
analyzer.py — Sheet Layer Precedence Analyzer
==============================================
Detecta e classifica violações de precedência em workbooks Excel (.xlsx)
com base em uma partição de camadas definida pelo usuário.

Uso:
    python analyzer.py <planilha.xlsx> <layers_config.json>

Saída:
    - Relatório textual no terminal
    - violations_report.json com todos os detalhes exportados
"""

from __future__ import annotations

import os
import json
import re
import sys
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import networkx as nx
import openpyxl


# ══════════════════════════════════════════════════════════════════════════════
# Constantes
# ══════════════════════════════════════════════════════════════════════════════

MAX_CONE_SIZE = 500   # Limite para evitar cálculos de cone em grafos muito densos
MAX_CONE_DEPTH = 50   # Profundidade máxima de busca no cone


# ══════════════════════════════════════════════════════════════════════════════
# Estruturas de dados
# ══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class CellNode:
    """Nó do grafo representando uma célula específica."""
    sheet: str
    address: str  # e.g. "A1", "BC42"

    def __str__(self) -> str:
        return f"'{self.sheet}'!{self.address}"

    def __repr__(self) -> str:
        return str(self)


@dataclass
class LayerConfig:
    """Configuração de camadas carregada do JSON de configuração."""
    layers: list[dict]  # [{"name": str, "order": int, "sheets": [str]}]

    def sheet_to_layer(self) -> dict[str, tuple[int, str]]:
        """Retorna {sheet_name: (order, layer_name)} para lookup O(1)."""
        mapping: dict[str, tuple[int, str]] = {}
        for layer in self.layers:
            for sheet in layer["sheets"]:
                mapping[sheet] = (layer["order"], layer["name"])
        return mapping

    def layer_names(self) -> dict[int, str]:
        """Retorna {order: name}."""
        return {layer["order"]: layer["name"] for layer in self.layers}


@dataclass
class TailMetrics:
    """Métricas do subgrafo cauda de referência (dependências a partir da violação)."""
    size: int
    longest_path: list[CellNode]
    layers_spread: list[str]
    source_nodes: list[CellNode]


@dataclass
class ConeMetrics:
    """Métricas do subgrafo (cone) ao redor da violação."""
    size: int               # |Cone| — número total de células
    depth: int              # Comprimento do caminho mais longo (-1 se tem ciclo)
    width: int              # Máximo (in_degree + out_degree) no cone
    layers_crossed: int     # Quantas camadas distintas o cone atravessa
    has_cycle: bool         # True se o cone contém algum ciclo
    bridge_edges: list[tuple[CellNode, CellNode]]  # Arestas ponte (candidatas a correção)
    ref_tail: Optional[TailMetrics] = None # Cauda de referência sugerida para inspeção
    truncated: bool = False # True se o cone foi cortado por MAX_CONE_SIZE


@dataclass
class Violation:
    """Violação de precedência completamente categorizada."""
    id: str
    edge: tuple[CellNode, CellNode]

    # Eixos de classificação
    nature: str     # V-UP | V-CYCLE | V-SELF
    scope: str      # S-LOCAL | S-CHAIN | S-CROSS
    grade: str      # G1 | G2 | G3 | G4

    # Contexto de camadas
    origin_layer: tuple[int, str]   # (order, name)
    target_layer: tuple[int, str]   # (order, name)

    # Métricas estruturais
    cone: ConeMetrics

    # Ação recomendada
    suggestion: str  # AUTOMATICA | ASSISTIDA | REFATORACAO | BLOQUEANTE
    action_plan: str = "" # Descrição amigável para o analista

    # Violações que compartilham o mesmo cone (preenchido em pós-processo)
    shared_with: list[str] = field(default_factory=list)
    is_quick_fix: bool = False


@dataclass
class Fix:
    """Registro de uma correção automática aplicada em uma célula."""
    violation_id: str
    cell: str            # repr da célula (ex: 'Custos_Base'!C8)
    sheet: str
    address: str
    original_formula: str
    fixed_formula: str
    removed_ref: str     # referência que foi substituída por 0


@dataclass
class PropFix:
    """Registro de uma correção por propagação (inlining de fórmula/valor)."""
    violation_id: str
    cell: str
    sheet: str
    address: str
    original_formula: str
    fixed_formula: str
    strategy: str   # LITERAL | INLINED | SKIPPED_EMPTY | SKIPPED_DEPTH | SKIPPED_COMPLEX
    depth_used: int


# ══════════════════════════════════════════════════════════════════════════════
# Parser de fórmulas
# ══════════════════════════════════════════════════════════════════════════════

# Captura referências cross-sheet:
#   'Nome com espaço'!A1   →  grupo 1 = Nome com espaço, grupo 3 = A1
#   SheetName!$B$2         →  grupo 2 = SheetName,        grupo 3 = B2
# Exclui referências externas como [Arquivo.xlsx]Aba!A1
_CROSS_REF_RE = re.compile(
    r"(?<!\[)"                                            # não precedido de [
    r"(?:'([^'!]+)'|([A-Za-z_\u00C0-\u024F][A-Za-z0-9_.\u00C0-\u024F]*))!"
    r"(\$?[A-Z]{1,3}\$?[0-9]{1,7})"                      # endereço da célula
)

# Captura ranges: Sheet!A1:B10  →  extrai célula inicial do range
_RANGE_RE = re.compile(r"(\$?[A-Z]{1,3}\$?[0-9]{1,7}):(\$?[A-Z]{1,3}\$?[0-9]{1,7})")


def _normalize_address(addr: str) -> str:
    """Remove $ de endereços absolutos para normalização."""
    return addr.replace("$", "")


def extract_cross_refs(formula: str, source_sheet: str) -> list[tuple[str, str]]:
    """
    Extrai referências cross-sheet de uma fórmula Excel.

    Retorna lista de (sheet_destino, endereço_célula).
    Para ranges (A1:B10), retorna apenas a célula inicial do range.
    Referências para a própria aba (source_sheet) são ignoradas.
    """
    refs: list[tuple[str, str]] = []

    for match in _CROSS_REF_RE.finditer(formula):
        sheet = match.group(1) or match.group(2)
        raw_addr = match.group(3)

        # Verifica se é início de um range (A1:B10) — usa só o primeiro extremo
        full_ref = match.group(0)
        range_match = _RANGE_RE.search(formula[match.start():match.start() + len(full_ref) + 10])
        addr = _normalize_address(range_match.group(1) if range_match else raw_addr)

        if sheet and sheet != source_sheet:
            refs.append((sheet, addr))

    return refs


# ══════════════════════════════════════════════════════════════════════════════
# Construtor do grafo
# ══════════════════════════════════════════════════════════════════════════════

def build_reference_graph(wb: openpyxl.Workbook) -> tuple[nx.DiGraph, dict]:
    """
    Constrói o grafo dirigido G = (C, E) onde (u → v) significa
    "célula u referencia célula v em outra aba".

    Retorna:
        G         — grafo de referências
        skipped   — contagem de referências ignoradas (externas, abas inexistentes)
    """
    G: nx.DiGraph = nx.DiGraph()
    sheet_names = set(wb.sheetnames)
    stats = {"external_refs": 0, "missing_sheets": 0, "formula_cells": 0}

    # 1. Coleta sequencial de conteúdos (Otimizado para read_only)
    contents = {}
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        for row in ws.iter_rows():
            for cell in row:
                val = cell.value
                if val is not None:
                    contents[(sheet_name, cell.coordinate)] = val

    # 2. Construção do grafo apenas para cross-refs
    for (sheet_name, coord), val in contents.items():
        if isinstance(val, str) and val.startswith("="):
            stats["formula_cells"] += 1
            formula = val[1:]
            refs = extract_cross_refs(formula, sheet_name)

            if not refs:
                continue

            src = CellNode(sheet=sheet_name, address=coord)
            G.add_node(src, content=val)

            for target_sheet, target_addr in refs:
                if target_sheet not in sheet_names:
                    stats["missing_sheets"] += 1
                    continue
                
                dst = CellNode(sheet=target_sheet, address=target_addr)
                # Pega conteúdo do cache O(1)
                target_val = contents.get((target_sheet, target_addr))
                G.add_node(dst, content=str(target_val) if target_val is not None else None)
                G.add_edge(src, dst)

    return G, stats


# ══════════════════════════════════════════════════════════════════════════════
# Cálculo do cone
# ══════════════════════════════════════════════════════════════════════════════

def compute_cone(
    G: nx.DiGraph,
    u: CellNode,
    v: CellNode,
    layer_map: dict[str, tuple[int, str]],
) -> ConeMetrics:
    """
    Calcula métricas do cone da violação:
        Cone(u→v) = ancestrais(u) ∪ {u, v} ∪ descendentes(v)

    Limitado por MAX_CONE_SIZE para garantir performance.
    """
    # Coleta ancestrais e descendentes com limite de tamanho
    try:
        ancestors = nx.ancestors(G, u)
        if len(ancestors) > MAX_CONE_SIZE:
            ancestors = set(list(ancestors)[:MAX_CONE_SIZE])
    except Exception:
        ancestors = set()

    try:
        descendants = nx.descendants(G, v)
        if len(descendants) > MAX_CONE_SIZE:
            descendants = set(list(descendants)[:MAX_CONE_SIZE])
    except Exception:
        descendants = set()

    cone_nodes = ancestors | {u, v} | descendants
    truncated = len(cone_nodes) >= MAX_CONE_SIZE

    subgraph = G.subgraph(cone_nodes).copy()

    # Profundidade: caminho mais longo (somente em DAGs)
    has_cycle = not nx.is_directed_acyclic_graph(subgraph)
    if has_cycle:
        depth = -1
    else:
        try:
            depth = nx.dag_longest_path_length(subgraph)
        except Exception:
            depth = 0

    # Largura: máximo grau (in + out) no cone
    width = max(
        (subgraph.in_degree(n) + subgraph.out_degree(n) for n in subgraph.nodes),
        default=0,
    )

    # Camadas distintas no cone
    layers = {
        layer_map[n.sheet][0]
        for n in cone_nodes
        if n.sheet in layer_map
    }

    # Bridges: arestas cuja remoção desconecta o grafo não-orientado subjacente
    # São candidatas prioritárias de correção
    bridge_edges: list[tuple[CellNode, CellNode]] = []
    try:
        undirected = subgraph.to_undirected()
        for a, b in nx.bridges(undirected):
            if subgraph.has_edge(a, b):
                bridge_edges.append((a, b))
            elif subgraph.has_edge(b, a):
                bridge_edges.append((b, a))
    except Exception:
        pass

    # Grafo-cauda de referência a partir de v
    try:
        desc_subgraph = G.subgraph(descendants | {v})
        t_size = desc_subgraph.number_of_nodes()
        
        # Fontes de dados reais são aquelas que não dependem de nada (out_degree == 0)
        source_nodes = [n for n, d in desc_subgraph.out_degree() if d == 0]
        
        layers_spread = list({
            layer_map[n.sheet][1] for n in desc_subgraph.nodes if n.sheet in layer_map
        })
        
        if nx.is_directed_acyclic_graph(desc_subgraph):
            longest_path = nx.dag_longest_path(desc_subgraph)
        else:
            try:
                cycle = nx.find_cycle(desc_subgraph)
                longest_path = [edge[0] for edge in cycle]
                if v not in longest_path:
                    longest_path = [v] + longest_path
            except nx.NetworkXNoCycle:
                longest_path = [v]

        ref_tail = TailMetrics(
            size=t_size,
            longest_path=longest_path,
            layers_spread=layers_spread,
            source_nodes=source_nodes,
        )
    except Exception:
        ref_tail = None

    return ConeMetrics(
        size=len(cone_nodes),
        depth=max(depth, 0),
        width=width,
        layers_crossed=len(layers),
        has_cycle=has_cycle,
        bridge_edges=bridge_edges,
        ref_tail=ref_tail,
        truncated=truncated,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Classificadores
# ══════════════════════════════════════════════════════════════════════════════

def classify_grade(cone: ConeMetrics) -> str:
    """
    Grau de entrelaçamento do subgrafo ao redor da violação.

    G1 — Cone isolado, 1 aresta direta e simples          → correção automática viável
    G2 — Cadeia acíclica pequena (prof ≤ 3, largura ≤ 2) → correção assistida
    G3 — Malha acíclica densa                             → refatoração necessária
    G4 — Cone contém ciclo                                → bloqueante
    """
    if cone.has_cycle:
        return "G4"
    if cone.size <= 3 and cone.depth <= 1 and cone.width <= 3:
        return "G1"
    if cone.depth <= 3 and cone.width <= 4:
        return "G2"
    return "G3"


def classify_scope(
    G: nx.DiGraph,
    u: CellNode,
    v: CellNode,
    cone: ConeMetrics,
    layer_map: dict[str, tuple[int, str]],
) -> str:
    """
    Escopo da violação no contexto do grafo completo.

    S-LOCAL  — Violação contida em um único par de abas
    S-CHAIN  — Parte de uma cadeia de múltiplas violações
    S-CROSS  — Conecta subgrafos que deveriam ser disjuntos (estrutural)
    """
    if cone.layers_crossed > 2:
        return "S-CROSS"

    # Conta violações de precedência dentro do cone
    ancestors = nx.ancestors(G, u)
    descendants = nx.descendants(G, v)
    cone_nodes = ancestors | {u, v} | descendants
    subgraph = G.subgraph(cone_nodes)

    violation_edges_in_cone = sum(
        1
        for a, b in subgraph.edges()
        if a.sheet in layer_map
        and b.sheet in layer_map
        and layer_map[a.sheet][0] < layer_map[b.sheet][0]
    )

    if violation_edges_in_cone > 1:
        return "S-CHAIN"
    return "S-LOCAL"


def classify_suggestion(nature: str, scope: str, grade: str) -> tuple[str, str]:
    if nature == "V-CYCLE":
        return "BLOQUEANTE", "CIRCULARIDADE: Esta celula faz parte de um ciclo. Remova a referencia para evitar erros de calculo."
    if scope == "S-CROSS" or grade == "G3":
        return "REFATORACAO", "ARQUITETURA: Esta celula depende de uma cadeia complexa de camadas superiores. Mova a logica para uma aba de nivel inferior."
    if grade == "G2":
        return "ASSISTIDA", "SIMPLIFICACAO: Referencia pontual a uma camada superior. Verifique se pode ser substituida por um valor fixo ou movida."
    return "AUTOMATICA", "CORRECAO AUTOMATICA: Referencia simples a camada superior. Pode ser limpa automaticamente."


# Globais para trabalhadores paralelos
_G_worker = None
_layer_map_worker = None

def _init_worker(G, layer_map):
    global _G_worker, _layer_map_worker
    _G_worker = G
    _layer_map_worker = layer_map

def _process_violation_task(edge_data):
    """Função worker otimizada que usa globais para evitar re-pickle do grafo."""
    u, v, nature, o_layer, t_layer = edge_data
    cone = compute_cone(_G_worker, u, v, _layer_map_worker)
    grade = classify_grade(cone)
    scope = classify_scope(_G_worker, u, v, cone, _layer_map_worker)
    suggestion, action_plan = classify_suggestion(nature, scope, grade)
    
    # Pega conteúdo do nó v (destino) dos atributos do grafo
    v_content = _G_worker.nodes[v].get("content", "") or ""
    
    # Detecção de QUICK-WIN: O destino é uma referência PURA (pass-through)
    # Regra: Deve começar com '=', conter '!', e não ter operadores matemáticos.
    is_quick_win = False
    if v_content.startswith("=") and "!" in v_content:
        # Remove '=', aspas simples e espaços ao redor do '!' para testar pureza
        clean = v_content.replace("=", "").replace("'", "").strip()
        # Se após remover a referência (letras, números, !, $) não sobrar nada, é pura
        import re
        # Regex que valida se é APENAS uma referência de aba (com ou sem $)
        # O nome da aba pode conter quase qualquer caractere antes do !
        if re.fullmatch(r"[^!]+\!(\$?[A-Z]+\$?[0-9]+)", clean):
            is_quick_win = True

    if is_quick_win:
        action_plan = f"[QUICK-WIN] {action_plan}"

    return (u, v, nature, o_layer, t_layer, cone, grade, scope, suggestion, action_plan, is_quick_win, v_content)


# ══════════════════════════════════════════════════════════════════════════════
# Detector principal
# ══════════════════════════════════════════════════════════════════════════════

def detect_violations(
    G: nx.DiGraph,
    layer_map: dict[str, tuple[int, str]],
) -> tuple[list[Violation], list[tuple[CellNode, CellNode]]]:
    """
    Varre todas as arestas do grafo e identifica violações de precedência.
    """
    # -- Passo 1: Mapeamento SCC -----------------------------------------------
    node_to_scc: dict[CellNode, int] = {}
    scc_size: dict[int, int] = {}

    for scc_id, scc in enumerate(nx.strongly_connected_components(G)):
        scc_size[scc_id] = len(scc)
        for node in scc:
            node_to_scc[node] = scc_id

    # -- Passo 2: Análise por aresta (Prepara Tarefas) --------------------------
    candidate_edges = []
    seen_cycle_sccs: set[int] = set()

    for u, v in G.edges():
        if u.sheet not in layer_map or v.sheet not in layer_map:
            continue

        u_order, u_layer_name = layer_map[u.sheet]
        v_order, v_layer_name = layer_map[v.sheet]

        scc_id_u = node_to_scc.get(u, -1)
        in_same_scc = (
            scc_id_u == node_to_scc.get(v)
            and scc_size.get(scc_id_u, 1) > 1
        )

        nature = None
        if in_same_scc:
            if scc_id_u not in seen_cycle_sccs:
                seen_cycle_sccs.add(scc_id_u)
                nature = "V-CYCLE"
        elif u_order < v_order:
            nature = "V-UP"

        if nature:
            candidate_edges.append((u, v, nature, (u_order, u_layer_name), (v_order, v_layer_name)))

    # -- Passo 3: Cálculo de Cones em Paralelo ---------------------------------
    print(f"     Calculando cones para {len(candidate_edges)} violacoes (paralelo)...")
    violations: list[Violation] = []
    
    with ProcessPoolExecutor(initializer=_init_worker, initargs=(G, layer_map)) as executor:
        results = list(executor.map(_process_violation_task, candidate_edges))

    for i, res in enumerate(results):
        u, v, nature, o_layer, t_layer, cone, grade, scope, suggestion, action_plan, is_quick_win, v_content = res
        violation = Violation(
            id=f"V{i:04d}",
            edge=(u, v),
            nature=nature,
            scope=scope,
            grade=grade,
            origin_layer=o_layer,
            target_layer=t_layer,
            cone=cone,
            suggestion=suggestion,
            action_plan=action_plan,
            is_quick_fix=is_quick_win,
        )
        # Atribui dinamicamente o v_content para uso no relatório
        violation.v_content = v_content
        violations.append(violation)

    # -- Passo 4: Análise de Abas Não Mapeadas (Leaks) -------------------------
    unmapped_refs = []
    for u, v in G.edges():
        u_mapped = u.sheet in layer_map
        v_mapped = v.sheet in layer_map
        if not u_mapped or not v_mapped:
            if u_mapped or v_mapped:
                unmapped_refs.append((u, v))

    # -- Passo 5: Agrupa violações com cone compartilhado ---------------------
    _mark_shared_cones(violations, G)

    return violations, unmapped_refs


def _mark_shared_cones(violations: list[Violation], G: nx.DiGraph) -> None:
    """
    Pós-processo: marca violações cujos cones se intersectam.
    Violações com cone compartilhado pertencem ao mesmo problema estrutural.
    """
    # Para cada violação, coleta o conjunto de nós do seu cone
    cone_nodesets: list[frozenset[CellNode]] = []
    for v in violations:
        u, dst = v.edge
        try:
            nodes = nx.ancestors(G, u) | {u, dst} | nx.descendants(G, dst)
            if len(nodes) > MAX_CONE_SIZE:
                nodes = set(list(nodes)[:MAX_CONE_SIZE])
        except Exception:
            nodes = {u, dst}
        cone_nodesets.append(frozenset(nodes))

    # Marca pares com intersecção não vazia
    for i, v_i in enumerate(violations):
        for j, v_j in enumerate(violations):
            if i >= j:
                continue
            if cone_nodesets[i] & cone_nodesets[j]:
                if v_j.id not in v_i.shared_with:
                    v_i.shared_with.append(v_j.id)
                if v_i.id not in v_j.shared_with:
                    v_j.shared_with.append(v_i.id)


def analyze_references_by_layer(
    violations: list[Violation],
    layer_names: dict[int, str],
) -> dict[str, dict[str, list[Violation]]]:
    """
    Analisa violações agrupadas por camada de origem e destino.

    Retorna dict[origem_layer_name -> dict[destino_layer_name -> [violações]]]
    """
    refs_by_layer: dict[str, dict[str, list[Violation]]] = defaultdict(
        lambda: defaultdict(list)
    )

    for v in violations:
        origin = v.origin_layer[1]
        target = v.target_layer[1]
        refs_by_layer[origin][target].append(v)

    return refs_by_layer


# ══════════════════════════════════════════════════════════════════════════════
# Relatório
# ══════════════════════════════════════════════════════════════════════════════

_ICONS = {
    "BLOQUEANTE":  "[!!!]",
    "REFATORACAO": "[WRN]",
    "ASSISTIDA":   "[AST]",
    "AUTOMATICA":  "[OK ]",
}

_PRIORITY_ORDER = ["BLOQUEANTE", "REFATORACAO", "ASSISTIDA", "AUTOMATICA"]


def print_flow_report(violations: list[Violation]) -> None:
    """Imprime matriz granular de fluxo: Camada -> Aba Origem -> Aba Destino."""
    if not violations:
        return

    # Estrutura: flow[origin_layer_ord][origin_sheet][(target_layer_name, target_sheet)] = count
    flow = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    layer_names = {}

    for v in violations:
        o_ord, o_name = v.origin_layer
        t_ord, t_name = v.target_layer
        u, dst = v.edge
        
        flow[o_ord][u.sheet][(t_name, dst.sheet)] += 1
        layer_names[o_ord] = o_name

    SEP = "=" * 72
    print(f"\n{SEP}")
    print("  MATRIZ DE FLUXO GRANULAR DE VIOLAÇÕES")
    print(SEP)

    for o_ord in sorted(flow.keys()):
        o_name = layer_names[o_ord]
        total_layer = sum(sum(targets.values()) for targets in flow[o_ord].values())
        
        print(f"\n  CAMADA L{o_ord}: {o_name} ({total_layer} violação(ões))")
        
        for o_sheet in sorted(flow[o_ord].keys()):
            print(f"    '{o_sheet}':")
            targets = flow[o_ord][o_sheet]
            # Ordena destinos por nome da camada e nome da aba
            for (t_name, t_sheet), count in sorted(targets.items()):
                print(f"      → '{t_sheet}' [{t_name}] : {count} item(ns)")

    print(f"\n{SEP}\n")


def print_layer_references_report(
    violations: list[Violation],
    layer_names: dict[int, str],
) -> None:
    """
    Imprime relatório de referências organizadas por camada.
    Mostra quais camadas referenciam quais outras camadas e quantas violações.
    """
    if not violations:
        print("\n  [i] Nenhuma violação para relatório por camada.\n")
        return

    refs_by_layer = analyze_references_by_layer(violations, layer_names)

    SEP = "=" * 72
    print(f"\n{SEP}")
    print("  REFERÊNCIAS POR CAMADA")
    print(SEP)

    all_layers = sorted(set(list(refs_by_layer.keys())))
    for origin_layer in all_layers:
        targets = refs_by_layer.get(origin_layer, {})
        total = sum(len(vs) for vs in targets.values())
        print(f"\n  [{origin_layer}] -> {total} violação(ões)")
        for target_layer in sorted(targets.keys()):
            viols = targets[target_layer]
            count = len(viols)
            suggestions = Counter(v.suggestion for v in viols)
            suggests_str = "  ".join(f"{k}={v}" for k, v in sorted(suggestions.items()))
            print(f"    → [{target_layer}]  {count} violação(ões)  ({suggests_str})")

    print(f"\n{SEP}\n")


def print_report(
    violations: list[Violation],
    layer_map: dict[str, tuple[int, str]],
    layer_names: dict[int, str],
    stats: dict,
) -> None:
    """Imprime relatório estruturado no terminal e exporta JSON."""

    SEP = "=" * 72
    sep = "-" * 72

    print(f"\n{SEP}")
    print("  RELATÓRIO DE VIOLAÇÕES DE PRECEDÊNCIA DE CAMADAS")
    print(SEP)

    # Estatísticas do grafo
    print(f"\n  (G) Grafo de referências")
    print(f"     Células com fórmula : {stats['formula_cells']}")
    print(f"     Refs. cross-sheet   : {stats.get('cross_refs', '-')}")
    print(f"     Refs. externas/skip : {stats['external_refs'] + stats['missing_sheets']}")

    if not violations:
        print("\n  [OK] Nenhuma violação de precedência encontrada.\n")
        print(SEP)
        return

    # NOVO: Relatório de Fluxo Granular
    print_flow_report(violations)

    # Sumário geral
    nature_c = Counter(v.nature for v in violations)
    grade_c   = Counter(v.grade for v in violations)
    suggest_c = Counter(v.suggestion for v in violations)

    print(f"\n  (!) {len(violations)} violação(ões) encontrada(s)\n")
    print(f"  Por natureza  : {_fmt_counter(nature_c)}")
    print(f"  Por grau      : {_fmt_counter(grade_c)}")
    print(f"  Por ação      : {_fmt_counter(suggest_c)}")

    # Summary by Origin Layer
    print(f"\n  (L) Distribuição por Camada de Origem")
    origin_layers = sorted(set(v.origin_layer for v in violations))
    for l_ord, l_name in origin_layers:
        l_vios = [v for v in violations if v.origin_layer == (l_ord, l_name)]
        print(f"     L{l_ord} ({l_name:<25}) : {len(l_vios)} violação(ões)")

    # Violations grouped by Origin Layer
    for l_ord, l_name in origin_layers:
        group = [v for v in violations if v.origin_layer == (l_ord, l_name)]
        
        print(f"\n{sep}")
        print(f"  CAMADA L{l_ord}: {l_name} ({len(group)} violação(ões))")
        print(sep)

        # Sort within group by priority and then by sheet/address
        group.sort(key=lambda x: (_PRIORITY_ORDER.index(x.suggestion), x.edge[0].sheet, x.edge[0].address))

        for v in group:
            u, dst = v.edge
            o_ord, o_name = v.origin_layer
            t_ord, t_name = v.target_layer
            icon = _ICONS[v.suggestion]

            print(f"\n  [{v.id}] {icon} {v.nature} | {v.scope} | {v.grade}")
            print(f"    Aresta   :  {u}  ->  {dst}")
            print(f"    Camadas  :  L{o_ord}({o_name})  ->  L{t_ord}({t_name})")

            cone = v.cone
            trunc = " [cone truncado]" if cone.truncated else ""
            cycle = "sim" if cone.has_cycle else "não"
            print(
                f"    Cone     :  {cone.size} nós{trunc} | "
                f"prof={cone.depth} | larg={cone.width} | "
                f"camadas={cone.layers_crossed} | ciclo={cycle}"
            )

            if cone.bridge_edges:
                v_bridges = [
                    (ba, bb) for ba, bb in cone.bridge_edges
                    if ba.sheet in layer_map and bb.sheet in layer_map
                    and layer_map[ba.sheet][0] < layer_map[bb.sheet][0]
                ]
                display_bridges = v_bridges if v_bridges else cone.bridge_edges
                
                print(f"    Bridges  :  {len(display_bridges)} aresta(s) candidata(s) a correcao")
                for ba, bb in display_bridges[:3]:
                    print(f"               {ba}  ->  {bb}")

            if v.shared_with:
                print(f"    Cone compartilhado com: {', '.join(v.shared_with)}")

    # Exportação JSON
    export = []
    for v in violations:
        u, dst = v.edge
        export.append({
            "id": v.id,
            "origem": str(u),
            "destino": str(dst),
            "natureza": v.nature,
            "sugestao": v.suggestion,
            "plano_acao": v.action_plan,
        })
    
    out_json = Path(os.path.join(os.getcwd(), "violations_report.json"))
    out_json.write_text(json.dumps(export, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n  [F] Dados tecnicos exportados -> {out_json.resolve()}")
    print(f"{SEP}\n")


def print_business_report(violations: list[Violation], unmapped_refs: list[tuple[CellNode, CellNode]], out_file: Optional[str] = None) -> None:
    """Gera um relatório focado em ações para analistas de negócios e executivos."""
    lines = []
    SEP_DBL = "=" * 80
    SEP_SNG = "-" * 80
    
    lines.append(SEP_DBL)
    lines.append("  RESUMO EXECUTIVO: ARQUITETURA E FLUXO DE DADOS")
    lines.append(SEP_DBL)

    if not violations:
        lines.append("\n  [PARABÉNS] Nenhuma violação encontrada nas camadas mapeadas.")
    else:
        # 1. Estatísticas Macro por Camada
        counts = Counter(v.suggestion for v in violations)
        quick_fixes = sum(1 for v in violations if v.is_quick_fix)
        lines.append(f"\n  [!] Total de Transgressões: {len(violations)}")
        lines.append(f"      Críticos (Ciclos)    : {counts['BLOQUEANTE']}")
        lines.append(f"      Refatoração Sugerida : {counts['REFATORACAO'] + counts['ASSISTIDA'] + counts['AUTOMATICA']}")
        lines.append(f"      Oportunidades QUICK-FIX (Propagação Direta): {quick_fixes}")

        lines.append("\n  [L] Transgressões por Camada de Origem:")
        origin_layers = sorted(set(v.origin_layer for v in violations))
        for l_ord, l_name in origin_layers:
            l_vios = [v for v in violations if v.origin_layer == (l_ord, l_name)]
            lines.append(f"      L{l_ord} ({l_name:<25}) : {len(l_vios)} item(ns)")
            
            # Detalhamento por aba dentro da camada
            sheet_counts = Counter(v.edge[0].sheet for v in l_vios)
            for sheet, count in sorted(sheet_counts.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"         L{l_ord}.{sheet:<23} : {count} item(ns)")

        # 2. Matriz de Fluxo (Camada.Aba -> Camada.Aba)
        lines.append("\n  [F] Matriz de Fluxo de Violações (Origem -> Destino):")
        flow_groups = defaultdict(list)
        for v in violations:
            o_ord, _ = v.origin_layer
            t_ord, _ = v.target_layer
            u, dst = v.edge
            flow_key = f"L{o_ord}.{u.sheet} -> L{t_ord}.{dst.sheet}"
            flow_groups[flow_key].append(v)
        
        # Ordenação: Camada Origem (asc), Aba Origem (asc), Quantidade (desc)
        sorted_flows = sorted(
            flow_groups.items(),
            key=lambda x: (x[1][0].origin_layer[0], x[1][0].edge[0].sheet, -len(x[1]))
        )
        
        for flow_key, v_list in sorted_flows:
            count = len(v_list)
            lines.append(f"      {flow_key:<40} : {count} item(ns)")
            
            # Lista todas as células de origem únicas envolvidas nesse fluxo
            source_cells = sorted(set(v.edge[0].address for v in v_list))
            cells_str = ", ".join(source_cells)
            
            lines.append(f"        └─ Células em '{v_list[0].edge[0].sheet}': {cells_str}")

        # 3. Lista de QUICK-WINS (Ação Imediata)
        quick_vios = [v for v in violations if v.is_quick_fix]
        if quick_vios:
            lines.append(f"\n{SEP_SNG}")
            lines.append("  [Q] LISTA DE QUICK-WINS (Ação Imediata - Propagação de Referência)")
            lines.append(SEP_SNG)
            lines.append("      Estes itens apontam para referências que podem ser propagadas diretamente:")
            
            # Agrupa por Aba de Origem para facilitar a navegação
            qw_by_sheet = defaultdict(list)
            for v in quick_vios:
                qw_by_sheet[v.edge[0].sheet].append(v)
            
            for sheet in sorted(qw_by_sheet.keys()):
                group = qw_by_sheet[sheet]
                lines.append(f"\n      Na aba '{sheet}' ({len(group)} item(ns)):")
                for v in group:
                    u, dst = v.edge
                    # O conteúdo do destino foi passado no resultado do worker
                    v_content = getattr(v, 'v_content', 'ERRO_REF')
                    lines.append(f"        └─ {u.address:<6} : Apontar diretamente para '{v_content}' (pulando aba '{dst.sheet}')")

        # 4. Alerta de Abas Não Mapeadas (Leaks)
        if unmapped_refs:
            lines.append(f"\n{SEP_SNG}")
            lines.append("  [!] ALERTAS: REFERÊNCIAS ENVOLVENDO ABAS NÃO MAPEADAS")
            lines.append(SEP_SNG)
            leaks = defaultdict(int)
            for u, v in unmapped_refs:
                leaks[f"'{u.sheet}' -> '{v.sheet}'"] += 1
            
            for flow, count in sorted(leaks.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"      {flow:<40} : {count} referência(s)")
            lines.append("      Nota: Estas abas não estão no JSON de camadas. Avalie se devem ser incluídas.")

        # 4. Agrupamento de Cones (Problemas Estruturais)
        lines.append(f"\n{SEP_SNG}")
        lines.append("  [#] GRUPOS DE CONE COMPARTILHADO (Mesmo Problema Estrutural)")
        lines.append(SEP_SNG)
        
        visited: set[str] = set()
        group_idx = 1
        for v in violations:
            if v.id in visited or not v.shared_with: continue
            group = [vv for vv in violations if vv.id in {v.id} | set(v.shared_with)]
            ids = ", ".join(vv.id for vv in group)
            suggestions = Counter(vv.suggestion for vv in group)
            worst = next(s for s in _PRIORITY_ORDER if s in suggestions)
            lines.append(f"  Grupo {group_idx:02d} ({len(group):02d} itens): {ids}")
            lines.append(f"            Ação Consolidada: {_ICONS[worst]} {worst}")
            visited |= {vv.id for vv in group}
            group_idx += 1

        # 5. Detalhamento por Camada
        lines.append(f"\n{SEP_SNG}")
        lines.append("  [D] PLANO DE AÇÃO DETALHADO POR CAMADA")
        lines.append(SEP_SNG)

        for l_ord, l_name in origin_layers:
            group = [v for v in violations if v.origin_layer == (l_ord, l_name)]
            lines.append(f"\n  >>> CAMADA L{l_ord}: {l_name}")
            lines.append(f"  {'─' * 40}")
            
            group.sort(key=lambda x: _PRIORITY_ORDER.index(x.suggestion))

            for v in group:
                u, dst = v.edge
                icon = _ICONS[v.suggestion]
                lines.append(f"\n  [ITEM {v.id}] {icon} Onde: {u}")
                lines.append(f"    PROBLEMA: Referência inválida para {dst}")
                lines.append(f"    AÇÃO: {v.action_plan}")
                if v.suggestion != "AUTOMATICA" and v.cone.ref_tail:
                    tm = v.cone.ref_tail
                    lines.append(f"    CONTEXTO: Cadeia de {tm.size} dependências afetadas.")
                    lines.append(f"    CAMINHO: {' -> '.join(str(n) for n in tm.longest_path[:3])} ...")

    content = "\n".join(lines)
    if out_file:
        Path(out_file).write_text(content, encoding="utf-8")
        print(f"  [OK] Relatório Executivo consolidado: {Path(out_file).resolve()}")
    else:
        print(content)

    # Exporta JSON
    _export_json(violations)

    content = "\n".join(lines)
    if out_file:
        Path(out_file).write_text(content, encoding="utf-8")
        print(f"  [OK] Relatório Executivo consolidado: {Path(out_file).resolve()}")
    else:
        print(content)

    # Exporta JSON
    _export_json(violations)


def _fmt_counter(c: Counter) -> str:
    return "  ".join(f"{k}={v}" for k, v in sorted(c.items()))


def _print_cone_groups(violations: list[Violation]) -> None:
    """(Legado) Imprime grupos no terminal. Agora integrado ao print_business_report."""
    pass


def _export_json(violations: list[Violation]) -> None:
    """Exporta relatório completo em JSON."""
    export = []
    for v in violations:
        u, dst = v.edge
        export.append({
            "id": v.id,
            "natureza": v.nature,
            "escopo": v.scope,
            "grau": v.grade,
            "sugestao": v.suggestion,
            "aresta": {
                "origem": str(u),
                "destino": str(dst),
                "aba_origem": u.sheet,
                "aba_destino": dst.sheet,
            },
            "camadas": {
                "origem": {"ordem": v.origin_layer[0], "nome": v.origin_layer[1]},
                "destino": {"ordem": v.target_layer[0], "nome": v.target_layer[1]},
            },
            "cone": {
                "tamanho": v.cone.size,
                "profundidade": v.cone.depth,
                "largura": v.cone.width,
                "camadas_cruzadas": v.cone.layers_crossed,
                "tem_ciclo": v.cone.has_cycle,
                "num_bridges": len(v.cone.bridge_edges),
                "bridges": [
                    {"origem": str(a), "destino": str(b)}
                    for a, b in v.cone.bridge_edges
                ],
                "truncado": v.cone.truncated,
            },
            "cone_compartilhado_com": v.shared_with,
        })

    out_path = Path("violations_report.json")
    out_path.write_text(json.dumps(export, indent=2, ensure_ascii=False))
    print(f"  [F] Relatório JSON exportado -> {out_path.resolve()}\n")


# ==============================================================================
# Corretor automatico
# ==============================================================================

def _replace_ref_with_zero(formula: str, sheet: str, address: str) -> str:
    """
    Substitui a referencia Sheet!Cell (e variantes com $ e aspas simples)
    pelo literal 0 dentro de uma formula Excel.

    Exemplos:
      =Resumo!C6        ->  =0
      =SUM(Resumo!C6,B2) ->  =SUM(0,B2)
      ='Resumo Exec'!$C$6 -> =0
    """
    addr_clean = address.replace("$", "")
    m = re.match(r"([A-Za-z]+)(\d+)", addr_clean)
    if not m:
        return formula
    col, row = m.group(1).upper(), m.group(2)
    sheet_esc = re.escape(sheet)
    pattern = re.compile(
        rf"'?{sheet_esc}'?!\$?{re.escape(col)}\$?{row}(?!\d)",
        re.IGNORECASE,
    )
    return pattern.sub("0", formula)


def _absolutize_formula_refs(formula: str, source_sheet: str) -> str:
    """
    Converte referências relativas (A1, Sheet!B2) para absolutas ($A$1, Sheet!$B$2).
    Preserva o prefixo de aba quando presente. Se não estiver presente,
    injeta a aba de origem para evitar vazamento de escopo no inlining.
    """
    # Captura: prefixo de aba opcional + col + row
    REF_PAT = re.compile(
        r"((?:'[^']+'|[A-Za-z_\u00C0-\u024F][\w.\u00C0-\u024F]*)!)?"
        r"(\$?)([A-Za-z]{1,3})(\$?)(\d{1,7})(?![\w\d])",
        re.IGNORECASE,
    )

    def _make_abs(m: re.Match) -> str:
        sheet_pfx = m.group(1)
        col = m.group(3).upper()
        row = m.group(5)
        
        # Se não tem aba definida, era uma referência local da aba original
        if not sheet_pfx:
            sheet_pfx = f"'{source_sheet}'!"
            
        return f"{sheet_pfx}${col}${row}"

    return REF_PAT.sub(_make_abs, formula)


def _replace_ref_with_expr(formula: str, sheet: str, address: str, replacement: str) -> str:
    """
    Substitui uma referência sheet!addr dentro de formula pela expressão replacement.
    Envolve em parênteses se o replacement contiver operadores, para preservar precedência.
    """
    addr_clean = address.replace("$", "")
    m = re.match(r"([A-Za-z]+)(\d+)", addr_clean)
    if not m:
        return formula
    col, row = m.group(1).upper(), m.group(2)
    sheet_esc = re.escape(sheet)
    pattern = re.compile(
        rf"'?{sheet_esc}'?!\$?{re.escape(col)}\$?{row}(?!\d)",
        re.IGNORECASE,
    )
    needs_wrap = any(op in replacement for op in ('+', '-', '*', '/', '&', ',', '('))
    wrapped = f"({replacement})" if needs_wrap else replacement
    return pattern.sub(wrapped, formula)



def apply_propagate_fixes(
    wb: openpyxl.Workbook,
    violations: list[Violation],
    layer_map: dict,
    dry_run: bool = False,
    max_depth: int = 3,
) -> list[PropFix]:
    """
    Correção por propagação (Shift-Left):
    Em vez de substituir a referência inválida por 0, copia a fórmula/valor
    da célula de destino para dentro da fórmula de origem, mantendo a lógica.
    """
    def get_value(sheet_name: str, addr: str):
        if sheet_name not in wb.sheetnames:
            return None
        return wb[sheet_name][addr].value

    SHEET_REF = re.compile(
        r"(?:'([^']+)'|([A-Za-z_\u00C0-\u024F][\w.\u00C0-\u024F]*))!"
        r"(\$?[A-Za-z]{1,3}\$?\d{1,7})",
        re.IGNORECASE,
    )

    def refs_violate(formula: str, src_sheet: str) -> list[tuple[str, str]]:
        src_layer = layer_map.get(src_sheet, (0,))[0]
        bad = []
        for m in SHEET_REF.finditer(formula):
            ref_sheet = (m.group(1) or m.group(2)).strip("'")
            ref_addr  = m.group(3).replace("$", "")
            ref_layer = layer_map.get(ref_sheet, (0,))[0]
            if ref_layer > src_layer:
                bad.append((ref_sheet, ref_addr))
        return bad

    def resolve(formula: str, src_sheet: str, depth: int) -> tuple[str, str]:
        if depth <= 0:
            bad = refs_violate(formula, src_sheet)
            if bad:
                return formula, "SKIPPED_DEPTH"
            return formula, "OK"

        current = formula
        strategy = "OK"

        for ref_sheet, ref_addr in refs_violate(current, src_sheet):
            target_val = get_value(ref_sheet, ref_addr)

            if target_val is None:
                current = _replace_ref_with_zero(current, ref_sheet, ref_addr)
                strategy = "LITERAL"
            elif not isinstance(target_val, str) or not target_val.startswith("="):
                lit = str(target_val) if not isinstance(target_val, str) else f'"{target_val}"'
                current = _replace_ref_with_expr(current, ref_sheet, ref_addr, lit)
                strategy = "LITERAL"
            else:
                inner = target_val[1:]
                inner_abs = _absolutize_formula_refs(inner, ref_sheet)
                current = _replace_ref_with_expr(current, ref_sheet, ref_addr, inner_abs)
                strategy = "INLINED"

                if refs_violate(current, src_sheet):
                    current, inner_strategy = resolve(current, src_sheet, depth - 1)
                    if inner_strategy != "OK":
                        strategy = inner_strategy

        return current, strategy

    fixes: list[PropFix] = []
    processed: set[tuple[str, str]] = set()

    for v in violations:
        u, dst = v.edge
        key = (u.sheet, u.address)
        if key in processed:
            continue
        if u.sheet not in wb.sheetnames:
            continue

        cell = wb[u.sheet][u.address]
        original = cell.value

        if not (isinstance(original, str) and original.startswith("=")):
            continue

        fixed, strategy = resolve(original, u.sheet, max_depth)
        processed.add(key)

        if fixed == original and strategy not in ("LITERAL", "INLINED", "OK"):
            strategy = "SKIPPED_COMPLEX"

        fix = PropFix(
            violation_id=v.id,
            cell=str(u),
            sheet=u.sheet,
            address=u.address,
            original_formula=original,
            fixed_formula=fixed,
            strategy=strategy,
            depth_used=max_depth,
        )
        fixes.append(fix)

        if not dry_run and fixed != original:
            cell.value = fixed

    return fixes

def print_propagate_report(fixes: list[PropFix], dry_run: bool = False) -> None:
    SEP = "=" * 72
    mode = "[DRY-RUN]" if dry_run else "[APLICADO]"
    totals = Counter(f.strategy for f in fixes)

    print(f"\n{SEP}")
    print(f"  CORREÇÃO POR PROPAGAÇÃO {mode}")
    print(SEP)
    print(f"\n  Total de células processadas : {len(fixes)}")
    print(f"  Literais injetados           : {totals['LITERAL']}")
    print(f"  Fórmulas inline expandidas   : {totals['INLINED']}")
    print(f"  Não alterados (OK/sem viols) : {totals['OK']}")
    print(f"  Pulados (profundidade)       : {totals['SKIPPED_DEPTH']}")
    print(f"  Pulados (complexidade)       : {totals['SKIPPED_COMPLEX']}\n")

    changed = [f for f in fixes if f.fixed_formula != f.original_formula]
    if changed:
        print(f"  Detalhes das {len(changed)} alterações:\n")
        for fix in changed:
            print(f"  [{fix.violation_id}]  {fix.cell}  [{fix.strategy}]")
            print(f"    Antes : {fix.original_formula}")
            print(f"    Depois: {fix.fixed_formula}")
            print()
    print(SEP)

def apply_auto_fixes(
    wb: openpyxl.Workbook,
    violations: list[Violation],
    dry_run: bool = False,
    fix_all: bool = False,
    select_by_suggestion: Optional[list[str]] = None,
    select_by_grade: Optional[list[str]] = None,
    select_by_layer_from: Optional[list[str]] = None,
    select_by_layer_to: Optional[list[str]] = None,
) -> list[Fix]:
    """
    Aplica correcoes automaticas para violacoes com seleção granular.

    Estrategia:
      Substitui a referencia ascendente (de camada inferior para superior)
      pelo literal 0 na formula da celula de origem, quebrando a dependencia
      invalida e mantendo a formula sintaticamente valida.

    Parametros de seleção (gradual fix):
      - select_by_suggestion: lista de sugestões ['AUTOMATICA', 'ASSISTIDA', ...]
      - select_by_grade: lista de graus ['G1', 'G2', ...]
      - select_by_layer_from: lista de camadas de origem
      - select_by_layer_to: lista de camadas de destino

    Em dry_run=True calcula as correcoes sem modificar o workbook.
    Retorna lista de Fix com o historico de cada alteracao.
    """
    # Filtra violações baseado nos critérios
    violations_to_fix = violations
    if select_by_suggestion or select_by_grade or select_by_layer_from or select_by_layer_to:
        violations_to_fix = [
            v
            for v in violations
            if (
                (not select_by_suggestion or v.suggestion in select_by_suggestion)
                and (not select_by_grade or v.grade in select_by_grade)
                and (
                    not select_by_layer_from
                    or v.origin_layer[1] in select_by_layer_from
                )
                and (not select_by_layer_to or v.target_layer[1] in select_by_layer_to)
            )
        ]
    elif not fix_all:
        # Se não especificado, aplica apenas AUTOMATICA
        violations_to_fix = [v for v in violations if v.suggestion == "AUTOMATICA"]
    try:
        from openpyxl.comments import Comment
        _has_comments = True
    except ImportError:
        _has_comments = False

    fixes: list[Fix] = []
    fixes: list[Fix] = []

    for v in violations_to_fix:
        u, dst = v.edge
        if u.sheet not in wb.sheetnames:
            continue

        ws = wb[u.sheet]
        cell = ws[u.address]
        original = cell.value

        if not (isinstance(original, str) and original.startswith("=")):
            continue

        fixed = _replace_ref_with_zero(original, dst.sheet, dst.address)
        if fixed == original:
            continue  # referencia nao encontrada (range ou padrao incomum)

        fix = Fix(
            violation_id=v.id,
            cell=str(u),
            sheet=u.sheet,
            address=u.address,
            original_formula=original,
            fixed_formula=fixed,
            removed_ref=f"{dst.sheet}!{dst.address}",
        )
        fixes.append(fix)

        if not dry_run:
            cell.value = fixed
            if _has_comments:
                note = (
                    f"[AUTO-FIX {v.id}] Referencia ascendente removida\n"
                    f"Antes : {original}\n"
                    f"Depois: {fixed}\n"
                    f"Ref removida: {dst}"
                )
                cell.comment = Comment(note, author="analyzer.py")

    return fixes


def print_fix_report(fixes: list[Fix], dry_run: bool = False) -> None:
    """Imprime relatorio das correcoes automaticas."""
    SEP = "=" * 72
    sep = "-" * 72
    mode = "[DRY-RUN — nenhuma alteracao salva]" if dry_run else "[APLICADO]"

    print(f"\n{SEP}")
    print(f"  CORRECOES AUTOMATICAS {mode}")
    print(SEP)

    if not fixes:
        print("\n  Nenhuma correcao automatica disponivel (sem violacoes G1).\n")
        print(SEP)
        return

    print(f"\n  {len(fixes)} correcao(oes) realizadas:\n")
    for fix in fixes:
        print(f"  [{fix.violation_id}]  {fix.cell}")
        print(f"    Antes      : {fix.original_formula}")
        print(f"    Depois     : {fix.fixed_formula}")
        print(f"    Ref cortada: {fix.removed_ref}")
        print()
    print(SEP)


# ==============================================================================
# Ponto de entrada
# ==============================================================================

def _build_arg_parser() -> "argparse.ArgumentParser":
    import argparse
    p = argparse.ArgumentParser(
        prog="analyzer.py",
        description="Sheet Layer Precedence Analyzer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemplos:\n"
            "  python analyzer.py plan.xlsx config.json\n"
            "  python analyzer.py plan.xlsx config.json --fix\n"
            "  python analyzer.py plan.xlsx config.json --fix --fix-out corrigido.xlsx\n"
            "  python analyzer.py plan.xlsx config.json --fix --dry-run\n"
        ),
    )
    p.add_argument("xlsx",   help="Planilha Excel (.xlsx)")
    p.add_argument("config", help="Arquivo de configuracao de camadas (.json)")
    p.add_argument(
        "--fix",
        action="store_true",
        help="Aplica correcoes automaticas (violacoes AUTOMATICA/G1) e salva resultado",
    )
    p.add_argument(
        "--fix-all",
        action="store_true",
        help="Aplica correcoes automaticas EM TODAS as violacoes (força quebra com 0 para Refatoracao/Assistida/Bloqueante)",
    )
    p.add_argument(
        "--fix-propagate",
        action="store_true",
        help="Correção por propagação: inline a fórmula/valor do nó destino, preservando a lógica de negócio",
    )
    p.add_argument(
        "--max-depth",
        type=int,
        default=3,
        metavar="N",
        help="Profundidade máxima de recursão para --fix-propagate (padrão: 3)",
    )
    p.add_argument(
        "--fix-out",
        metavar="FILE",
        default=None,
        help="Destino da planilha corrigida (padrao: <nome>_fixed.xlsx)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Simula correcoes e exibe o que seria alterado, sem salvar",
    )
    p.add_argument(
        "--business",
        action="store_true",
        help="Gera relatório focado em negócios (menos técnico)",
    )
    p.add_argument(
        "--report-out",
        metavar="FILE",
        help="Nome do arquivo para salvar o relatório de negócios",
    )
    p.add_argument(
        "--layers",
        action="store_true",
        help="Mostra relatório de referências organizadas por camada de origem/destino",
    )
    p.add_argument(
        "--by-suggestion",
        nargs="+",
        metavar="SUGGESTION",
        choices=["AUTOMATICA", "ASSISTIDA", "REFATORACAO", "BLOQUEANTE"],
        help="Filtra fixes por tipo de sugestão (ex: --by-suggestion AUTOMATICA ASSISTIDA)",
    )
    p.add_argument(
        "--by-grade",
        nargs="+",
        metavar="GRADE",
        choices=["G1", "G2", "G3", "G4"],
        help="Filtra fixes por grau de complexidade (ex: --by-grade G1 G2)",
    )
    p.add_argument(
        "--by-layer-from",
        nargs="+",
        metavar="LAYER",
        help="Filtra fixes por camada de origem (ex: --by-layer-from 'Custos_Base')",
    )
    p.add_argument(
        "--by-layer-to",
        nargs="+",
        metavar="LAYER",
        help="Filtra fixes por camada de destino (ex: --by-layer-to 'Planejamento')",
    )
    return p


def _run_analysis(xlsx_path: Path, config_path: Path, wb: openpyxl.Workbook):
    """Executa analise completa e retorna (violations, layer_map, layer_names, stats)."""
    raw_config = json.loads(config_path.read_text(encoding="utf-8"))
    config = LayerConfig(raw_config["layers"])
    layer_map = config.sheet_to_layer()
    layer_names = config.layer_names()

    unmapped = [s for s in wb.sheetnames if s not in layer_map]
    if unmapped:
        print(f"  (!) Abas nao mapeadas: {unmapped}  (ignoradas na analise)")

    print("  [#] Construindo grafo de referencias...")
    G, stats = build_reference_graph(wb)
    stats["cross_refs"] = G.number_of_edges()
    print(f"     Nos              : {G.number_of_nodes()}")
    print(f"     Arestas cross-sh.: {G.number_of_edges()}")

    print("  [?] Detectando violacoes de precedencia...")
    violations, unmapped_refs = detect_violations(G, layer_map)
    return violations, unmapped_refs, layer_map, layer_names, stats

import os

def main() -> None:
    import argparse
    parser = _build_arg_parser()
    args = parser.parse_args()

    # Resolução robusta de caminhos
    xlsx_path   = Path(os.path.abspath(os.path.join(os.getcwd(), args.xlsx)))
    config_path = Path(os.path.abspath(os.path.join(os.getcwd(), args.config)))
    do_fix      = args.fix or args.fix_all or args.fix_propagate or args.dry_run

    # ── Analise inicial ──────────────────────────────────────────────────────
    print(f"\n  [I] Carregando planilha  : {xlsx_path}")
    if not xlsx_path.exists():
        print(f"  [!] ERRO: Arquivo nao encontrado em {xlsx_path}")
        sys.exit(1)

    import warnings
    warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

    # Otimização: Usa read_only=True se não for aplicar correções
    wb = openpyxl.load_workbook(str(xlsx_path), data_only=False, read_only=not do_fix)
    print(f"     Abas encontradas    : {wb.sheetnames}")
    print(f"  [S] Configuracao         : {config_path}")

    if not config_path.exists():
        print(f"  [!] ERRO: Arquivo de configuracao nao encontrado em {config_path}")
        sys.exit(1)

    violations, unmapped_refs, layer_map, layer_names, stats = _run_analysis(
        xlsx_path, config_path, wb
    )
    
    # Mostra referências por camada se solicitado
    if getattr(args, 'layers', False):
        print_layer_references_report(violations, layer_names)

    if args.business or args.report_out:
        report_path = os.path.abspath(os.path.join(os.getcwd(), args.report_out)) if args.report_out else None
        print_business_report(violations, unmapped_refs, report_path)
    else:
        print_report(violations, layer_map, layer_names, stats)

    if not do_fix:
        return

    # ── Correção por propagação (Shift-Left) ──────────────────────────────────
    changed = False
    if args.fix_propagate:
        print("  [~] Aplicando correcoes por propagacao (inlining de formula/valor)...")
        prop_fixes = apply_propagate_fixes(
            wb, violations, layer_map,
            dry_run=args.dry_run,
            max_depth=args.max_depth,
        )
        print_propagate_report(prop_fixes, dry_run=args.dry_run)
        changed = any(f.fixed_formula != f.original_formula for f in prop_fixes)

    # ── Correção automática (substituição por 0) ──────────────────────────────
    else:
        if not args.fix_all:
            n_auto = sum(1 for v in violations if v.suggestion == "AUTOMATICA")
            if n_auto == 0:
                print("\n  (i) Nenhuma violacao AUTOMATICA para corrigir.\n")
                return

        fixes = apply_auto_fixes(
            wb,
            violations,
            dry_run=args.dry_run,
            fix_all=args.fix_all,
            select_by_suggestion=getattr(args, 'by_suggestion', None),
            select_by_grade=getattr(args, 'by_grade', None),
            select_by_layer_from=getattr(args, 'by_layer_from', None),
            select_by_layer_to=getattr(args, 'by_layer_to', None),
        )
        print_fix_report(fixes, dry_run=args.dry_run)
        changed = bool(fixes)

    if args.dry_run or not changed:
        return

    # Salva planilha corrigida
    if args.fix_out:
        out_path = Path(os.path.abspath(os.path.join(os.getcwd(), args.fix_out)))
    else:
        out_path = xlsx_path.with_stem(xlsx_path.stem + "_fixed")
    
    wb.save(str(out_path))
    print(f"  [OK] Planilha corrigida salva: {out_path.resolve()}\n")

    # Re-analise pos-correcao
    print(f"  [I] Re-analisando planilha corrigida: {out_path.name}")
    wb2 = openpyxl.load_workbook(str(out_path), data_only=False)
    violations2, layer_map2, layer_names2, stats2 = _run_analysis(
        out_path, config_path, wb2
    )
    
    if args.business or args.report_out:
        out_report2 = None
        if args.report_out:
            p = Path(report_path)
            out_report2 = str(p.with_stem(p.stem + "_post_fix"))
        print_business_report(violations2, out_report2)
    else:
        print_report(violations2, layer_map2, layer_names2, stats2)


if __name__ == "__main__":
    main()
