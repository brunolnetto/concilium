"""Grafo de dependências EAP (networkx + matplotlib, layout hierárquico por nível topológico)."""

from __future__ import annotations

from ._common import init_mpl

# --- Constantes visuais ---
_NODE_W = 2.8
_NODE_H = 0.7
_H_SPACING = 4.0  # distância horizontal entre níveis
_V_SPACING = 1.4  # distância vertical entre nós no mesmo nível
_FG_DARK = "#1a3a5c"
_FG_LIGHT = "#d6e4f0"


def build_dependencia_eap(cronograma: dict) -> bytes | None:
    tasks = list(cronograma.get("tasks", [])) if isinstance(cronograma, dict) else []
    if not tasks:
        return None
    return _build_networkx(tasks)


# ---------------------------------------------------------------------------
# Helpers de grafo
# ---------------------------------------------------------------------------


def _pred_id_from(pred) -> str:
    return pred.get("item_id") if isinstance(pred, dict) else str(pred)


def _add_predecessors_to_adj(adj: dict, task: dict) -> None:
    succ = str(task.get("item_id", ""))
    for pred in task.get("predecessores") or []:
        pred_id = _pred_id_from(pred)
        if pred_id in adj:
            adj[pred_id].add(succ)


def _build_adj(tasks: list) -> dict[str, set[str]]:
    """Retorna adjacência successores: pred → {successores}."""
    adj: dict[str, set[str]] = {str(t.get("item_id", "")): set() for t in tasks}
    for task in tasks:
        _add_predecessors_to_adj(adj, task)
    return adj


def _accumulate_predecessors(pred_count: dict, succ: str, task: dict) -> None:
    for pred in task.get("predecessores") or []:
        pred_id = _pred_id_from(pred)
        if pred_id in pred_count:
            pred_count[succ].add(pred_id)


def _build_pred_count(tasks: list) -> tuple[list[str], dict[str, set[str]]]:
    nodes = [str(t.get("item_id", "")) for t in tasks]
    pred_count: dict[str, set[str]] = {n: set() for n in nodes}
    for task in tasks:
        succ = str(task.get("item_id", ""))
        _accumulate_predecessors(pred_count, succ, task)
    return nodes, pred_count


def _init_queue(nodes: list, pred_count: dict):
    from collections import deque

    in_deg = {n: len(pred_count[n]) for n in nodes}
    return deque(n for n in nodes if in_deg[n] == 0), in_deg


def _bfs_relax_neighbors(level: dict, in_deg: dict, queue, adj: dict, n: str) -> None:
    for succ in adj.get(n, set()):
        level[succ] = max(level[succ], level[n] + 1)
        in_deg[succ] -= 1
        if in_deg[succ] == 0:
            queue.append(succ)


def _bfs_levels(nodes: list, adj: dict, pred_count: dict) -> dict[str, int]:
    level: dict[str, int] = {n: 0 for n in nodes}
    queue, in_deg = _init_queue(nodes, pred_count)
    while queue:
        _bfs_relax_neighbors(level, in_deg, queue, adj, queue.popleft())
    return level


def _topological_levels(tasks: list, adj: dict[str, set[str]]) -> dict[str, int]:
    """Calcula o nível topológico de cada nó (longest-path DAG)."""
    nodes, pred_count = _build_pred_count(tasks)
    return _bfs_levels(nodes, adj, pred_count)


def _barycenter_order(layer: list[str], prev_pos: dict[str, float], pred_adj: dict[str, set[str]]) -> list[str]:
    """Ordena nós de uma camada pelo baricentro dos predecessores na camada anterior.

    Algoritmo de barycenter (Sugiyama Fase 3): cada nó recebe como chave de ordenação
    a média das posições y dos seus predecessores no nível anterior. Nós sem predecessores
    mantêm a posição relativa original. Minimiza cruzamentos de arestas entre camadas.
    """
    scores: dict[str, float] = {}
    for n in layer:
        preds = [p for p in pred_adj.get(n, set()) if p in prev_pos]
        scores[n] = sum(prev_pos[p] for p in preds) / len(preds) if preds else float("inf")
    # Score alto = predecessores no topo (y alto) → nó deve ficar no topo também.
    # Nós sem predecessores (score=inf) ficam no final.
    return sorted(layer, key=lambda n: (scores[n] == float("inf"), -scores[n], n))


def _assign_positions(tasks: list) -> tuple[dict, dict]:
    """Retorna {item_id: (x, y)} para layout hierárquico esquerda-direita.

    Usa o algoritmo de barycenter (Sugiyama) para ordenar nós dentro de cada nível
    de forma a minimizar cruzamentos de arestas. Faz uma passagem para frente
    (predecessor → successor) e uma para trás para convergir.
    """
    adj = _build_adj(tasks)
    # adj reverso: sucessor → predecessores (necessário para barycenter)
    pred_adj: dict[str, set[str]] = {n: set() for n in adj}
    for p, succs in adj.items():
        for s in succs:
            pred_adj.setdefault(s, set()).add(p)

    levels = _topological_levels(tasks, adj)
    by_level: dict[int, list[str]] = {}
    for node, lv in levels.items():
        by_level.setdefault(lv, []).append(node)

    # Passagem inicial: ordenação alfabética no nível 0 (sem predecessores)
    max_lv = max(by_level.keys(), default=0)
    ordered: dict[int, list[str]] = {0: sorted(by_level.get(0, []))}

    # Passagem para frente: cada nível é ordenado pelo baricentro do nível anterior
    prev_y: dict[str, float] = {}
    for n in ordered[0]:
        i = ordered[0].index(n)
        prev_y[n] = -(i - (len(ordered[0]) - 1) / 2.0)

    for lv in range(1, max_lv + 1):
        layer = by_level.get(lv, [])
        ordered[lv] = _barycenter_order(layer, prev_y, pred_adj)
        for n in ordered[lv]:
            i = ordered[lv].index(n)
            prev_y[n] = -(i - (len(ordered[lv]) - 1) / 2.0)

    # Passagem para trás: refinar com baricentro dos sucessores
    succ_adj = adj  # adj já é pred → {succs}
    next_y: dict[str, float] = dict(prev_y)
    for lv in range(max_lv - 1, -1, -1):
        layer = ordered[lv]
        # Baricentro reverso: posição média dos sucessores
        scores: dict[str, float] = {}
        for n in layer:
            succs = [s for s in succ_adj.get(n, set()) if s in next_y]
            scores[n] = sum(next_y[s] for s in succs) / len(succs) if succs else float("inf")
        ordered[lv] = sorted(layer, key=lambda n: (scores[n] == float("inf"), -scores[n], n))
        for n in ordered[lv]:
            i = ordered[lv].index(n)
            next_y[n] = -(i - (len(ordered[lv]) - 1) / 2.0)

    # Construir posições finais
    pos: dict[str, tuple[float, float]] = {}
    for lv, nodes in ordered.items():
        for i, n in enumerate(nodes):
            x = lv * _H_SPACING
            y = -(i - (len(nodes) - 1) / 2.0) * _V_SPACING
            pos[n] = (x, y)
    return pos, adj


# ---------------------------------------------------------------------------
# Renderer principal
# ---------------------------------------------------------------------------


def _build_name_map(tasks: list) -> dict[str, str]:
    return {str(t.get("item_id", "")): (t.get("name") or str(t.get("item_id", ""))) for t in tasks}


def _setup_figure(plt, pos: dict):
    xs = [p[0] for p in pos.values()]
    ys = [p[1] for p in pos.values()]
    fig_w = max(14, (max(xs) - min(xs) + _NODE_W * 2) * 1.1)
    fig_h = max(6, (max(ys) - min(ys) + _NODE_H * 3) * 1.2)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.axis("off")
    ax.set_title("Rede de Dependências EAP", fontsize=13, fontweight="bold", pad=14)
    return fig, ax, xs, ys


def _edge_rad(y0: float, y1: float) -> float:
    if abs(y0 - y1) <= 0.01:
        return 0.0
    return 0.25 if y1 < y0 else -0.25


def _draw_single_edge(ax, pos: dict, pred_id: str, succ_id: str, edge_label: str, pe) -> None:
    x0, y0 = pos[pred_id]
    x1, y1 = pos[succ_id]
    start = (x0 + _NODE_W / 2, y0)
    end = (x1 - _NODE_W / 2, y1)
    rad = _edge_rad(y0, y1)
    ax.annotate(
        "",
        xy=end,
        xytext=start,
        arrowprops=dict(
            arrowstyle="-|>",
            color=_FG_DARK,
            lw=1.3,
            connectionstyle=f"arc3,rad={rad}",
        ),
        annotation_clip=False,
    )
    mx, my = (start[0] + end[0]) / 2, (start[1] + end[1]) / 2 + 0.18
    ax.text(
        mx,
        my,
        edge_label,
        ha="center",
        va="bottom",
        fontsize=7,
        color=_FG_DARK,
        path_effects=[pe.withStroke(linewidth=2, foreground="white")],
    )


def _get_edge_info(pred: dict | str) -> tuple[str, str, int, str]:
    pred_id = _pred_id_from(pred)
    tipo = pred.get("tipo", "FS") if isinstance(pred, dict) else "FS"
    lag = int(pred.get("lag", 0)) if isinstance(pred, dict) else 0
    edge_label = tipo if lag == 0 else f"{tipo}+{lag}sem"
    return pred_id, tipo, lag, edge_label


def _draw_edges(ax, tasks: list, pos: dict, pe) -> None:
    for task in tasks:
        succ_id = str(task.get("item_id", ""))
        for pred in task.get("predecessores") or []:
            pred_id, _tipo, _lag, edge_label = _get_edge_info(pred)
            if pred_id not in pos or succ_id not in pos:
                continue
            _draw_single_edge(ax, pos, pred_id, succ_id, edge_label, pe)


def _break_long_label(label: str) -> str:
    if len(label) <= 28:
        return label
    mid = len(label) // 2
    for offset in range(0, 12):
        for d in (offset, -offset):
            idx = mid + d
            if 0 < idx < len(label) and label[idx] == " ":
                return label[:idx] + "\n" + label[idx + 1 :]
    return label


def _draw_nodes(ax, tasks: list, pos: dict, name_map: dict, mpatches) -> None:
    for item_id, (x, y) in pos.items():
        label = _break_long_label(name_map.get(item_id, item_id))
        rect = mpatches.FancyBboxPatch(
            (x - _NODE_W / 2, y - _NODE_H / 2),
            _NODE_W,
            _NODE_H,
            boxstyle="round,pad=0.04",
            facecolor=_FG_LIGHT,
            edgecolor=_FG_DARK,
            linewidth=1.5,
            zorder=3,
        )
        ax.add_patch(rect)
        ax.text(
            x,
            y,
            label,
            ha="center",
            va="center",
            fontsize=7.5,
            fontweight="bold",
            color=_FG_DARK,
            zorder=4,
            wrap=False,
        )


def _finalize_axes(ax, xs: list, ys: list) -> None:
    pad_x = _NODE_W * 0.8
    pad_y = _NODE_H * 1.5
    ax.set_xlim(min(xs) - pad_x, max(xs) + pad_x)
    ax.set_ylim(min(ys) - pad_y, max(ys) + pad_y)


def _build_networkx(tasks: list) -> bytes | None:
    try:
        import matplotlib.patches as mpatches
        import matplotlib.patheffects as pe

        plt, fig_to_bytes = init_mpl()
    except ImportError:
        return None
    try:
        pos, adj = _assign_positions(tasks)
        if not pos:
            return None
        fig, ax, xs, ys = _setup_figure(plt, pos)
        name_map = _build_name_map(tasks)
        _draw_edges(ax, tasks, pos, pe)
        _draw_nodes(ax, tasks, pos, name_map, mpatches)
        _finalize_axes(ax, xs, ys)
        fig.tight_layout()
        return fig_to_bytes(fig)
    except Exception:
        plt.close("all")
        return None
