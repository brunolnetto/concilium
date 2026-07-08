"""ADR-070 — Campaign service (parte extraída de campaign_service.py)."""

from __future__ import annotations

from concilium.domain.models.campaign.campaign import CenarioAvaliado


def _domina_O(a: CenarioAvaliado, b: CenarioAvaliado) -> bool:
    """a dominates b in O-space (minimizing prazo, fe_nec, gap_pool)."""
    va, vb = a.vetor_O, b.vetor_O
    dims = [
        (va.prazo_semanas, vb.prazo_semanas),
        (va.fe_nec_medio, vb.fe_nec_medio),
        (va.gap_pool_total, vb.gap_pool_total),
    ]
    dims = [(x, y) for x, y in dims if x is not None and y is not None]
    if not dims:
        return False
    no_worse = all(x <= y for x, y in dims)
    strictly_better = any(x < y for x, y in dims)
    return no_worse and strictly_better


def _domina_EF(a: CenarioAvaliado, b: CenarioAvaliado) -> bool:
    """a dominates b in EF-space (maximize margem, minimize custo_indireto)."""
    va, vb = a.vetor_EF, b.vetor_EF
    if va.margem_pct is None or vb.margem_pct is None:
        return False
    margem_ok = va.margem_pct >= vb.margem_pct
    ind_ok = True
    if va.custo_indireto is not None and vb.custo_indireto is not None:
        ind_ok = va.custo_indireto <= vb.custo_indireto
    strictly = va.margem_pct > vb.margem_pct or (
        va.custo_indireto is not None and vb.custo_indireto is not None and va.custo_indireto < vb.custo_indireto
    )
    return margem_ok and ind_ok and strictly


def calcular_pareto(cenarios: list[CenarioAvaliado], espaco: str) -> set[str]:
    """Returns set of cenario_ids on the Pareto frontier for espaco='O'|'EF'."""
    domina = _domina_O if espaco == "O" else _domina_EF
    pareto_ids = set()
    for c in cenarios:
        dominated = any(domina(other, c) for other in cenarios if other.cenario_id != c.cenario_id)
        if not dominated:
            pareto_ids.add(c.cenario_id)
    return pareto_ids


