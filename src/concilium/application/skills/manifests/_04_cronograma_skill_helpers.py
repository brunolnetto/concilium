"""ADR-081: Helpers de derivação de DAG com threshold de conclusão parcial.

Este módulo expõe ``extract_dag_from_spec_or_eap`` — ponto único de construção
do ActivityDAG para o skill-04. Separa a lógica do arquivo principal do skill
para facilitar importação nos testes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from concilium.domain.models.canonical import EapItem

from concilium.application.scheduling.models import Activity, ActivityDAG


def extract_dag_from_spec_or_eap(
    spec: dict,
    activities: list[Activity],
    eap_items: list[EapItem] | None = None,
) -> ActivityDAG:
    """Constrói ActivityDAG a partir de rcpsp_spec e/ou spec.eap (ADR-081).

    Regra de fusão:
    1. ``spec.eap[].predecessores`` → fonte canônica (inclui completion_threshold_pct)
    2. ``rcpsp_spec.precedence``     → override/suplemento; para o mesmo par, prevalece

    Formato de rcpsp_spec.precedence:
      - [pred_id, succ_id]           → θ = 1.0 (FS clássico, legado)
      - [pred_id, succ_id, theta]    → θ = float(theta)
    """
    # ── Passo 1: derivar arestas da EAP ──────────────────────────────────────
    # dict para permitir override por par
    edge_thresholds: dict[tuple[str, str], float] = {}

    if eap_items:
        for item in eap_items:
            for pred in item.predecessores_tipados():
                key = (pred.item_id, item.item_id)
                edge_thresholds[key] = float(pred.completion_threshold_pct)

    # ── Passo 2: aplicar overrides de rcpsp_spec.precedence ──────────────────
    for p in spec.get("precedence", []):
        if len(p) < 2:
            continue
        pred_id = str(p[0])
        succ_id = str(p[1])
        # θ opcional no terceiro elemento; default 1.0 (FS estrito)
        theta = float(p[2]) if len(p) > 2 else 1.0
        theta = max(0.0, min(1.0, theta))
        key = (pred_id, succ_id)
        edge_thresholds[key] = theta  # override prevalece

    precedence = list(edge_thresholds.keys())
    return ActivityDAG(activities=activities, precedence=precedence, thresholds=edge_thresholds)
