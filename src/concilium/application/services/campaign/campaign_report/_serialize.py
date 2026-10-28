"""ADR-070 — Campaign report generation — serialize_campaign_report."""

from __future__ import annotations

from concilium.domain.models.campaign.campaign import CampaignBundleCube, CampaignOutputBundle

from ._helpers import _vetor_EF_dict, _vetor_O_dict


def serialize_campaign_report(
    bundle: CampaignOutputBundle,
    cube: CampaignBundleCube,
) -> dict:
    """Converts CampaignOutputBundle + CampaignBundleCube to a JSON-serializable dict."""
    n_av = bundle.n_cenarios_avaliados
    n_vi = bundle.n_cenarios_viaveis
    cobertura = n_vi / n_av if n_av else 0.0

    meta = {
        "campaign_id": bundle.campaign_id,
        "campaign_version": bundle.campaign_version,
        "gerado_em": str(bundle.gerado_em),
        "status": bundle.status,
        "n_avaliados": n_av,
        "n_viaveis": n_vi,
        "n_falhas": bundle.n_falhas,
        "cobertura_pct": round(cobertura * 100, 1),
    }

    shortlist = []
    for ranked in bundle.shortlist:
        c = ranked.cenario
        j = ranked.justificativa
        shortlist.append(
            {
                "rank": ranked.rank,
                "cenario_id": c.cenario_id,
                "motivo_inclusao": j.motivo_inclusao,
                "destaques_O": j.destaques_O,
                "destaques_EF": j.destaques_EF,
                "alertas": j.alertas,
                "parametros_chave": j.parametros_chave,
                "vetor_O": _vetor_O_dict(c.vetor_O),
                "vetor_EF": _vetor_EF_dict(c.vetor_EF),
            }
        )

    cenarios = []
    for c in bundle.cenarios:
        cenarios.append(
            {
                "cenario_id": c.cenario_id,
                "viabilidade": c.viabilidade,
                "motivo_nao_avaliado": c.motivo_nao_avaliado,
                "classificacao_O": c.classificacao_O,
                "classificacao_EF": c.classificacao_EF,
                "pareto_O": c.pareto_O,
                "pareto_EF": c.pareto_EF,
                "pareto_intersecao": c.pareto_intersecao,
                "rank_final": c.rank_final,
                "vetor_O": _vetor_O_dict(c.vetor_O),
                "vetor_EF": _vetor_EF_dict(c.vetor_EF),
                "parametros_variados": c.parametros_variados,
                "erro": c.erro,
            }
        )

    dimensoes = [{"nome": d.nome, "campo": d.campo, "valores": d.valores} for d in cube.dimensoes]

    resumos_marginais = [
        {
            "dimensao": r.dimensao,
            "metrica": r.metrica,
            "valores": r.valores,
            "medias": r.medias,
            "tendencia": r.tendencia,
        }
        for r in cube.resumos_marginais
    ]

    faces = [
        {
            "dim_x": f.dim_x,
            "dim_y": f.dim_y,
            "metrica": f.metrica,
            "valores_x": f.valores_x,
            "valores_y": f.valores_y,
            "grade": f.grade,
        }
        for f in cube.faces
    ]

    cubo = {
        "dimensoes": dimensoes,
        "n_celulas_total": cube.n_celulas_total,
        "n_celulas_avaliadas": cube.n_celulas_avaliadas,
        "cobertura_pct": round(cube.cobertura_pct * 100, 1),
        "resumos_marginais": resumos_marginais,
        "faces": faces,
    }

    return {"meta": meta, "shortlist": shortlist, "cenarios": cenarios, "cubo": cubo}


