"""ADR-070 — Campaign service (parte extraída de campaign_service.py)."""

from __future__ import annotations

from concilium.domain.models.campaign.campaign import (
    CampaignStatus,
    CenarioAvaliado,
    CenarioRankeado,
    JustificativaCenario,
    PerfilExpectativas,
    VetorEspacoEF,
    VetorEspacoO,
)

from ._pareto import calcular_pareto


def _destaques_O_justificativa(v_O: VetorEspacoO) -> list[str]:
    destaques_O = []
    if v_O.folga_semanas is not None:
        tag = "OK" if v_O.folga_semanas >= 0 else "WARN"
        destaques_O.append(f"[{tag}] Folga {v_O.folga_semanas:+.0f} sem")
    if v_O.fe_nec_medio is not None:
        destaques_O.append(f"fe_nec medio {v_O.fe_nec_medio:.2f}")
    if v_O.itens_criticos_pct == 0:
        destaques_O.append("0 itens criticos")
    elif v_O.itens_criticos_pct is not None:
        destaques_O.append(f"{v_O.itens_criticos_pct * 100:.0f}% itens criticos")
    return destaques_O


def _destaques_EF_justificativa(v_EF: VetorEspacoEF) -> list[str]:
    destaques_EF = []
    if v_EF.margem_pct is not None:
        destaques_EF.append(f"Margem {v_EF.margem_pct * 100:.1f}%")
    if v_EF.ratio_pool_vs_cat is not None:
        if v_EF.ratio_pool_vs_cat <= 1:
            destaques_EF.append(f"Pool {(1 - v_EF.ratio_pool_vs_cat) * 100:.1f}% abaixo mercado")
        else:
            destaques_EF.append(f"Pool {(v_EF.ratio_pool_vs_cat - 1) * 100:.1f}% acima mercado")
    return destaques_EF


def _alertas_justificativa(c: CenarioAvaliado) -> list[str]:
    alertas = []
    if c.classificacao_O == "ATENCAO":
        alertas.append("O-space: atencao em alguma dimensao")
    if c.classificacao_EF == "ATENCAO":
        alertas.append("EF-space: margem proxima da meta")
    return alertas


def _build_justificativa(c: CenarioAvaliado, motivo: str) -> JustificativaCenario:
    v_O, v_EF = c.vetor_O, c.vetor_EF
    destaques_O = _destaques_O_justificativa(v_O)
    destaques_EF = _destaques_EF_justificativa(v_EF)
    alertas = _alertas_justificativa(c)

    return JustificativaCenario(
        motivo_inclusao=motivo,
        destaques_O=destaques_O,
        destaques_EF=destaques_EF,
        alertas=alertas,
        parametros_chave=c.parametros_variados,
    )


def _marcar_flags_pareto(viaveis: list[CenarioAvaliado]) -> None:
    pareto_O_ids = calcular_pareto(viaveis, "O")
    pareto_EF_ids = calcular_pareto(viaveis, "EF")
    for c in viaveis:
        c.pareto_O = c.cenario_id in pareto_O_ids
        c.pareto_EF = c.cenario_id in pareto_EF_ids
        c.pareto_intersecao = c.pareto_O and c.pareto_EF


def _selecionar_pool_shortlist(viaveis: list[CenarioAvaliado]) -> list[CenarioAvaliado]:
    intersecao = [c for c in viaveis if c.pareto_intersecao]
    return intersecao if intersecao else ([c for c in viaveis if c.pareto_EF] or viaveis)


def _rank_key_shortlist(c: CenarioAvaliado) -> tuple:
    return (
        c.classificacao_O != "IDEAL",
        c.classificacao_EF != "DENTRO_EXPECTATIVA",
        -(c.vetor_EF.margem_pct or 0),
        (c.vetor_O.prazo_semanas or 9999),
        (c.vetor_O.fe_nec_medio or 9999),
        c.cenario_id,
    )


def _montar_shortlist(ranked: list[CenarioAvaliado], top_k: int) -> list[CenarioRankeado]:
    shortlist = []
    for i, c in enumerate(ranked[:top_k]):
        c.rank_final = i + 1
        motivo = "pareto_intersecao" if c.pareto_intersecao else ("pareto_EF" if c.pareto_EF else "melhor_viavel")
        shortlist.append(
            CenarioRankeado(
                rank=i + 1,
                cenario=c,
                justificativa=_build_justificativa(c, motivo),
            )
        )
    return shortlist


def curar_shortlist(
    cenarios: list[CenarioAvaliado],
    top_k: int,
    perfil: PerfilExpectativas,
) -> list[CenarioRankeado]:
    viaveis = [c for c in cenarios if c.viabilidade in {"APROVADO", "APROVADO_COM_RESSALVAS"}]
    if not viaveis:
        return []

    _marcar_flags_pareto(viaveis)
    pool = _selecionar_pool_shortlist(viaveis)
    ranked = sorted(pool, key=_rank_key_shortlist)
    return _montar_shortlist(ranked, top_k)


def _status_bundle_sem_viaveis(cenarios: list[CenarioAvaliado], falhas: list[CenarioAvaliado]) -> CampaignStatus:
    return "ABORTADO" if len(falhas) == len(cenarios) else "INFEASIBLE"


def _tem_fronteira_unica(viaveis: list[CenarioAvaliado]) -> bool:
    pareto_O = [c for c in viaveis if c.pareto_O]
    pareto_EF = [c for c in viaveis if c.pareto_EF]
    return bool(pareto_O and pareto_EF)


def _status_bundle_com_viaveis(viaveis: list[CenarioAvaliado]) -> CampaignStatus:
    intersecao = [c for c in viaveis if c.pareto_intersecao]
    if intersecao:
        return "SUCESSO"
    if _tem_fronteira_unica(viaveis):
        return "FRONTEIRA_UNICA"
    return "SUCESSO_PARCIAL"


def classificar_bundle(cenarios: list[CenarioAvaliado]) -> CampaignStatus:
    viaveis = [c for c in cenarios if c.viabilidade in {"APROVADO", "APROVADO_COM_RESSALVAS"}]
    if not viaveis:
        falhas = [c for c in cenarios if c.erro]
        return _status_bundle_sem_viaveis(cenarios, falhas)
    return _status_bundle_com_viaveis(viaveis)


