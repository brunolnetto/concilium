"""Skill 05 — Equipes e Alocação (parte extraída de skill.py).

Reconciliação de custo com planejamento (ADR-107).
"""

from __future__ import annotations

from typing import Any

from concilium.domain.models.canonical import (
    CanonicalModel,
    ValidacaoItem,
)


def _or_chain(*values: Any) -> Any:
    """Colapsa uma cadeia `v1 or v2 or ... or vn` em uma única chamada (mesma semântica)."""
    last = None
    for v in values:
        if v:
            return v
        last = v
    return last


def _plan_subtotal_dict_total(subtotal: dict) -> float | None:
    """Extrai subtotal.sem_bdi.total quando `subtotal` é um dict (formato legado)."""
    sem_bdi = subtotal.get("sem_bdi") or {}
    if isinstance(sem_bdi, dict):
        total = sem_bdi.get("total")
        if isinstance(total, (int, float)):
            return float(total)
    return None


def _plan_subtotal_obj_total(subtotal: Any) -> float | None:
    """Extrai subtotal.sem_bdi.total quando `subtotal` é um objeto (formato atual)."""
    sem_bdi = getattr(subtotal, "sem_bdi", None)
    if sem_bdi is not None:
        total = getattr(sem_bdi, "total", None)
        if isinstance(total, (int, float)):
            return float(total)
    return None


def _plan_custo_sem_bdi_total(plan: Any) -> float:
    """Extrai subtotal sem BDI do planejamento em formatos legado/atual."""
    try:
        direto = getattr(plan, "custo_sem_bdi", None)
        if isinstance(direto, (int, float)) and direto > 0:
            return float(direto)

        subtotal = getattr(plan, "subtotal", None)
        total: float | None = None
        if isinstance(subtotal, dict):
            total = _plan_subtotal_dict_total(subtotal)
        elif subtotal is not None:
            total = _plan_subtotal_obj_total(subtotal)
        if total is not None:
            return total
    except Exception:
        return 0.0
    return 0.0


def _extract_planejamento_ref_map(inputs: dict[str, Any]) -> dict[str, float]:
    """Extrai o mapa item_id → custo de referência a partir de `inputs['planejamento_ref']`."""
    planejamento_ref_map: dict[str, float] = {}
    for item in inputs.get("planejamento_ref") or []:
        if not isinstance(item, dict):
            continue
        item_id = item.get("item_id")
        subtotal = ((item.get("subtotal") or {}).get("sem_bdi") or {}).get("total")
        if isinstance(item_id, str) and isinstance(subtotal, (int, float)):
            planejamento_ref_map[item_id] = float(subtotal)
    return planejamento_ref_map


def _resolve_planejamento_maps(
    canonical_in: CanonicalModel, inputs: dict[str, Any], benchmark_mode: bool
) -> tuple[dict[str, Any], dict[str, float]]:
    """ADR-107: resolve os mapas de planejamento (canônico e de benchmark) usados na reconciliação."""
    planejamento_map: dict[str, Any] = {}
    if hasattr(canonical_in, "planejamento") and canonical_in.planejamento:
        planejamento_map = {p.item_id: p for p in canonical_in.planejamento}
    planejamento_ref_map: dict[str, float] = {}
    if benchmark_mode and isinstance(inputs.get("planejamento_ref"), list):
        planejamento_ref_map = _extract_planejamento_ref_map(inputs)
    return planejamento_map, planejamento_ref_map


def _aplicar_reconciliacao_planejamento(
    equipes: list,
    planejamento_map: dict[str, Any],
    planejamento_ref_map: dict[str, float],
    validacoes: list[ValidacaoItem],
) -> None:
    """ADR-107: usa custo_sem_bdi do planejamento como fonte de verdade de custo_total."""
    for eq in equipes:
        custo_ref = 0.0
        if eq.item_id in planejamento_map:
            custo_ref = _plan_custo_sem_bdi_total(planejamento_map[eq.item_id])
        elif eq.item_id in planejamento_ref_map:
            custo_ref = planejamento_ref_map[eq.item_id]

        if custo_ref > 0 and abs(custo_ref - eq.custo_total) > 1.0:
            desvio = abs(custo_ref - eq.custo_total)
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-PLANEJAMENTO-OVERRIDE",
                    status="AVISO",
                    mensagem=(
                        f"Item {eq.item_id}: custo_total ajustado "
                        f"(recalc R$ {eq.custo_total:,.2f} → planejamento R$ {custo_ref:,.2f}, "
                        f"desvio R$ {desvio:,.2f})"
                    ),
                )
            )
            eq.custo_total = round(custo_ref, 2)


