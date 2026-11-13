"""ADR-081 / NEP-031 L4: Helpers de derivação de DAG com threshold e tipos SS/FF.

Este módulo expõe ``extract_dag_from_spec_or_eap`` — ponto único de construção
do ActivityDAG para o skill-04. Separa a lógica do arquivo principal do skill
para facilitar importação nos testes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from concilium.application.scheduling.rcpsp_precedence import parse_rcpsp_precedence

if TYPE_CHECKING:
    from concilium.application.scheduling.cpsat_scheduler import ExtendedPrecedence
    from concilium.domain.models.canonical import EapItem

from concilium.application.scheduling.models import Activity, ActivityDAG


def _derive_edges_from_eap_items(
    eap_items: list[EapItem] | None,
    extended_precedence_cls: type[ExtendedPrecedence],
) -> tuple[dict[tuple[str, str], float], list[ExtendedPrecedence]]:
    """Deriva thresholds FS e precedências estendidas (SS/FF) a partir da EAP."""
    edge_thresholds: dict[tuple[str, str], float] = {}
    extended: list[ExtendedPrecedence] = []

    if eap_items:
        for item in eap_items:
            for pred in item.predecessores_tipados():
                key = (pred.item_id, item.item_id)
                tipo = str(getattr(pred, "tipo", "FS") or "FS").upper()
                lag = int(getattr(pred, "lag", 0) or 0)
                if tipo == "FS":
                    # FS com completion_threshold_pct — usa caminho existente
                    edge_thresholds[key] = float(pred.completion_threshold_pct)
                elif tipo == "SS":
                    # SS/FF: coloca em extended_precedences (NEP-031 L4)
                    # Também registra em precedence para topological_order funcionar
                    edge_thresholds[key] = 1.0  # sentinela: aresta existe no grafo
                    extended.append(extended_precedence_cls(pred=pred.item_id, succ=item.item_id, tipo="SS", lag=lag))
                elif tipo == "FF":
                    edge_thresholds[key] = 1.0  # sentinela: aresta existe no grafo
                    extended.append(extended_precedence_cls(pred=pred.item_id, succ=item.item_id, tipo="FF", lag=lag))

    return edge_thresholds, extended


def _apply_precedence_overrides(spec: dict, edge_thresholds: dict[tuple[str, str], float]) -> None:
    """Aplica overrides de rcpsp_spec.precedence (apenas FS legado) em edge_thresholds."""
    for edge in parse_rcpsp_precedence(spec.get("precedence")):
        edge_thresholds[(edge.pred, edge.succ)] = edge.theta


def extract_dag_from_spec_or_eap(
    spec: dict,
    activities: list[Activity],
    eap_items: list[EapItem] | None = None,
) -> ActivityDAG:
    """Constrói ActivityDAG a partir de rcpsp_spec e/ou spec.eap (ADR-081 + NEP-031 L4).

    Regra de fusão:
    1. ``spec.eap[].predecessores`` → fonte canônica (inclui tipo, completion_threshold_pct, lag)
    2. ``rcpsp_spec.precedence``     → override/suplemento; para o mesmo par, prevalece

    Tipos suportados em EapItem.predecessores:
      - FS (default): start_j ≥ start_i + ceil(θ × dur_i) — codificado em thresholds
      - SS: start_j ≥ start_i + lag — codificado em extended_precedences
      - FF: finish_j ≥ finish_i + lag — codificado em extended_precedences

    Formato de rcpsp_spec.precedence (legado, apenas FS):
      - [pred_id, succ_id]           → θ = 1.0 (FS clássico)
      - [pred_id, succ_id, theta]    → θ = float(theta)
    """
    from concilium.application.scheduling.cpsat_scheduler import ExtendedPrecedence

    # ── Passo 1: derivar arestas da EAP ──────────────────────────────────────
    edge_thresholds, extended = _derive_edges_from_eap_items(eap_items, ExtendedPrecedence)

    # ── Passo 2: aplicar overrides de rcpsp_spec.precedence (apenas FS legado) ──
    _apply_precedence_overrides(spec, edge_thresholds)

    precedence = list(edge_thresholds.keys())
    return ActivityDAG(
        activities=activities,
        precedence=precedence,
        thresholds=edge_thresholds,
        extended_precedences=extended,
    )
