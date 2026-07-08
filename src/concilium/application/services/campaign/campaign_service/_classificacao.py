"""ADR-070 — Campaign service (parte extraída de campaign_service.py)."""

from __future__ import annotations

from concilium.domain.models.campaign.campaign import (
    ClassificacaoEF,
    ClassificacaoO,
    PerfilExpectativas,
    VetorEspacoEF,
    VetorEspacoO,
)


def _scores_vetor_O(v: VetorEspacoO) -> list[str]:
    scores = []
    if v.folga_semanas is not None:
        scores.append("IDEAL" if v.folga_semanas >= 0 else ("ATENCAO" if v.folga_semanas >= -2 else "CRITICO"))
    if v.fe_nec_medio is not None:
        scores.append("IDEAL" if v.fe_nec_medio <= 1.0 else ("ATENCAO" if v.fe_nec_medio <= 1.25 else "CRITICO"))
    if v.itens_criticos_pct is not None:
        scores.append(
            "IDEAL" if v.itens_criticos_pct == 0 else ("ATENCAO" if v.itens_criticos_pct <= 0.20 else "CRITICO")
        )
    return scores


def classificar_O(v: VetorEspacoO, perfil: PerfilExpectativas) -> ClassificacaoO:
    scores = _scores_vetor_O(v)
    if not scores:
        return "ATENCAO"
    if "CRITICO" in scores:
        return "CRITICO"
    if "ATENCAO" in scores:
        return "ATENCAO"
    return "IDEAL"


def _scores_vetor_EF(v: VetorEspacoEF, perfil: PerfilExpectativas) -> list[str]:
    scores = []
    if v.margem_pct is not None:
        meta = perfil.meta_margem_pct
        tol = perfil.tolerancia_margem
        scores.append(
            "DENTRO_EXPECTATIVA"
            if v.margem_pct >= meta
            else ("ATENCAO" if v.margem_pct >= meta - tol else "FORA_EXPECTATIVA")
        )
    if v.ratio_pool_vs_cat is not None:
        scores.append(
            "DENTRO_EXPECTATIVA"
            if v.ratio_pool_vs_cat <= 1.0
            else ("ATENCAO" if v.ratio_pool_vs_cat <= 1.10 else "FORA_EXPECTATIVA")
        )
    if v.fidelidade_gates is not None:
        scores.append("DENTRO_EXPECTATIVA" if v.fidelidade_gates else "FORA_EXPECTATIVA")
    return scores


def classificar_EF(v: VetorEspacoEF, perfil: PerfilExpectativas) -> ClassificacaoEF:
    scores = _scores_vetor_EF(v, perfil)
    if not scores:
        return "ATENCAO"
    if "FORA_EXPECTATIVA" in scores:
        return "FORA_EXPECTATIVA"
    if "ATENCAO" in scores:
        return "ATENCAO"
    return "DENTRO_EXPECTATIVA"


