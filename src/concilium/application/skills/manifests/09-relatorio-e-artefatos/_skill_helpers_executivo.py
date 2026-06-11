"""Relatório executivo consolidado — absorvido de 15-relatorio-executivo (NEP-041 Fase 1).

Gera RelatorioCriticidade, RelatorioSensibilidade, RelatorioIntervencao e o
BridgeWaterfall como estágio interno do skill 09. Originalmente em skill-15,
agora computado dentro de 09 para eliminar o passo intermediário (ADR-026).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from concilium.domain.models.artifact import ArtifactEnvelope, ArtifactKind
from concilium.domain.models.canonical import ValidacaoItem
from concilium.domain.models.reports import (
    EixoIntervencao,
    ItemCriticidadeRelatorio,
    ItemSensibilidade,
    RelatorioCriticidade,
    RelatorioIntervencao,
    RelatorioSensibilidade,
)

_CREATED_BY = "09-relatorio-e-artefatos"


def _rre_get_margin_status(resultado) -> tuple[str, float]:
    """Returns (status_margem, margem_entrada) from resultado, defaulting safely."""
    status_margem = getattr(resultado, "status_margem", "VERDE") if resultado else "VERDE"
    margem_entrada = getattr(resultado, "margem", 0.0) if resultado else 0.0
    return status_margem, margem_entrada


def _rre_build_criticidade(ccr, proj, now) -> tuple:
    """Builds RelatorioCriticidade, its artifact and validation, or (None, None, None)."""
    if not ccr:
        return None, None, None
    itens_crit = []
    for item in getattr(ccr, "itens", []):
        itens_crit.append(
            ItemCriticidadeRelatorio(
                atividade_id=str(getattr(item, "atividade_id", getattr(item, "item_id", ""))),
                descricao=str(getattr(item, "descricao", "")),
                classificacao=getattr(item, "classificacao", "C"),
                pareto_frontier=bool(getattr(item, "pareto_frontier", False)),
                custo_share=float(getattr(item, "custo_share", 0.0)),
                duracao_share=float(getattr(item, "duracao_share", 0.0)),
                sensibilidade=float(getattr(item, "sensibilidade", 0.0)),
                recurso_status=getattr(item, "recurso_status", "LIVRE"),
                decisoes_vinculadas=list(getattr(item, "decisoes_vinculadas", [])),
            )
        )
    relatorio = RelatorioCriticidade(
        projeto_id=str(proj.id),
        versao=str(proj.revisao),
        gerado_em=now,
        itens=itens_crit,
    ).calcular_estatisticas()
    artifact = ArtifactEnvelope.create(
        payload=relatorio,
        kind=ArtifactKind.RELATORIO_CRITICIDADE,
        schema_name="RelatorioCriticidade",
        schema_version="1.0.0",
        created_by=_CREATED_BY,
    )
    validacao = ValidacaoItem(
        codigo="VAL-REX-CRIT",
        status="OK",
        mensagem=f"Criticidade: {relatorio.total_A_mais} A+, {relatorio.total_A} A.",
    )
    return relatorio, artifact, validacao


def _rre_build_sensibilidade(rp, proj, now, status_margem: str, margem_entrada: float) -> tuple:
    """Builds RelatorioSensibilidade, its artifact and validation."""
    if rp:
        passos = []
        oportunidades = []
        _TIPO_TO_LEVER = {
            "CRONOGRAMA": "REDUCE_DURATION",
            "EQUIPES": "ADD_TEAMS",
            "RECURSOS": "EXPAND_POOL",
            "ESCOPO": "REVIEW_BDI",
            "BDI": "REVIEW_BDI",
        }
        for sugestao in getattr(rp, "sugestoes", []):
            raw_tipo = getattr(sugestao, "tipo", "BDI")
            item = ItemSensibilidade(
                lever_tipo=_TIPO_TO_LEVER.get(raw_tipo, raw_tipo),
                lever_checkpoint=str(getattr(sugestao, "checkpoint", "")),
                delta_margem=float(getattr(sugestao, "delta_margem", 0.0)),
                custo_aplicacao=getattr(sugestao, "custo_aplicacao", None),
                confianca=getattr(sugestao, "confianca", "MEDIA"),
                atividades_afetadas=list(getattr(sugestao, "atividades_afetadas", [])),
            )
            if status_margem in ("AMARELO", "VERMELHO"):
                passos.append(item)
            else:
                oportunidades.append(item)
        relatorio = RelatorioSensibilidade(
            projeto_id=str(proj.id),
            versao=str(proj.revisao),
            gerado_em=now,
            status_margem=status_margem,
            margem_entrada=margem_entrada,
            margem_alvo_min=float(getattr(rp, "margem_alvo_min", 0.0)),
            repair_viavel=bool(getattr(rp, "repair_viavel", False)),
            passos_repair=passos,
            oportunidades=oportunidades,
            margem_pos_repair=getattr(rp, "margem_projetada", None),
        )
    else:
        relatorio = RelatorioSensibilidade(
            projeto_id=str(proj.id),
            versao=str(proj.revisao),
            gerado_em=now,
            status_margem=status_margem,
            margem_entrada=margem_entrada,
            margem_alvo_min=0.0,
        )
    artifact = ArtifactEnvelope.create(
        payload=relatorio,
        kind=ArtifactKind.RELATORIO_SENSIBILIDADE,
        schema_name="RelatorioSensibilidade",
        schema_version="1.0.0",
        created_by=_CREATED_BY,
    )
    validacao = ValidacaoItem(
        codigo="VAL-REX-SENS",
        status="OK",
        mensagem=f"Sensibilidade: {len(relatorio.passos_repair)} repair, {len(relatorio.oportunidades)} oport.",
    )
    return relatorio, artifact, validacao


def _rre_oport_eixo(oport) -> EixoIntervencao:
    """Builds an EixoIntervencao from a psr opportunity."""
    l_tipo = str(getattr(oport.lever, "tipo", "")) if getattr(oport, "lever", None) else ""
    confianca = getattr(oport, "confianca", "MEDIA") if hasattr(oport, "confianca") else "MEDIA"
    return EixoIntervencao(
        nome=f"Oportunidade {l_tipo}",
        margem_estimada=float(getattr(oport, "margem_adicional_estimada", 0.0)),
        confianca=confianca,
        risco=getattr(oport, "risco", "BAIXO"),
        levers_combinados=[l_tipo] if l_tipo else [],
    )


def _rre_build_intervencao(psr, proj, now, status_margem: str) -> tuple:
    """Builds RelatorioIntervencao, its artifact and validation."""
    if psr:
        eixos = []
        fronteira = []
        repair_path = getattr(psr, "repair_path", None)
        if repair_path:
            e_rep = EixoIntervencao(
                nome="Repair (AMARELO/VERMELHO->VERDE)",
                margem_estimada=float(getattr(repair_path, "margem_projetada", 0.0)),
                prazo_delta_dias=getattr(repair_path, "prazo_delta_dias", None),
                confianca=getattr(repair_path, "confianca", "MEDIA"),
                risco=getattr(repair_path, "risco", "MEDIO"),
                levers_combinados=[str(getattr(s, "tipo", "")) for s in getattr(repair_path, "steps", [])],
            )
            eixos.append(e_rep)
            fronteira.append(e_rep)
        for oport in getattr(psr, "oportunidades", []):
            eixos.append(_rre_oport_eixo(oport))
        recomendacao = fronteira[0] if fronteira else (eixos[0] if eixos else None)
        relatorio = RelatorioIntervencao(
            projeto_id=str(proj.id),
            versao=str(proj.revisao),
            gerado_em=now,
            status_entrada=getattr(psr, "status_entrada", "VERDE"),
            eixos_intervencao=eixos,
            fronteira_pareto=fronteira,
            recomendacao_primaria=recomendacao,
        )
    else:
        relatorio = RelatorioIntervencao(
            projeto_id=str(proj.id),
            versao=str(proj.revisao),
            gerado_em=now,
            status_entrada=status_margem,
        )
        recomendacao = relatorio.recomendacao_primaria
    artifact = ArtifactEnvelope.create(
        payload=relatorio,
        kind=ArtifactKind.RELATORIO_INTERVENCAO,
        schema_name="RelatorioIntervencao",
        schema_version="1.0.0",
        created_by=_CREATED_BY,
    )
    rec_nome = recomendacao.nome if recomendacao else "Nenhuma"
    validacao = ValidacaoItem(
        codigo="VAL-REX-INT",
        status="OK",
        mensagem=f"Intervenção: Recomendação '{rec_nome}'.",
    )
    return relatorio, artifact, validacao


def _rre_build_bridge(bridge_analysis, proj, now) -> tuple:
    """Builds bridge waterfall artifact and validation."""
    if not (bridge_analysis and isinstance(bridge_analysis, dict)):
        validacao = ValidacaoItem(
            codigo="VAL-REX-BRIDGE",
            status="AVISO",
            mensagem="Bridge Analysis ausente — execute a Skill 08 (Consolidação Financeira) antes.",
        )
        return None, validacao
    n1 = bridge_analysis.get("nivel_1_catalogo_base", 0)
    n2 = bridge_analysis.get("nivel_2_catalogo_escalado", 0)
    n3 = bridge_analysis.get("nivel_3_catalogo_normalizado", 0)
    n4 = bridge_analysis.get("nivel_4_operacional")
    status_bridge = bridge_analysis.get("status_alerta", "SEM_DADOS")
    delta_real = bridge_analysis.get("delta_real_abs")
    delta_pct = bridge_analysis.get("delta_real_percentual")
    waterfall = {
        "nota_metodologica": (
            "ADR-039 The Bridge: N1=catálogo base puro | "
            "N2=escalado por quantização de frentes (overhead de escala) | "
            "N3=normalizado por praticabilidade climática (parada forçada por chuva) | "
            "N4=custo operacional real medido. "
            "O delta real (N4−N3) isola a ineficiência gestional genuína, "
            "separada de causas estruturais não controláveis pelo orçamentista."
        ),
        "niveis": {
            "N1_catalogo_base": round(n1, 2),
            "N2_catalogo_escalado": round(n2, 2),
            "N3_catalogo_normalizado": round(n3, 2),
            "N4_operacional_real": round(n4, 2) if n4 is not None else None,
        },
        "desvios": {
            "desvio_escala_abs": bridge_analysis.get("desvio_escala_abs"),
            "desvio_clima_abs": bridge_analysis.get("desvio_clima_abs"),
            "delta_estrutural_abs": bridge_analysis.get("delta_estrutural_abs"),
            "delta_real_abs": delta_real,
            "delta_real_pct": delta_pct,
        },
        "fatores": {
            "fator_quantizacao": bridge_analysis.get("fator_quantizacao"),
            "fator_praticabilidade": bridge_analysis.get("fator_praticabilidade"),
        },
        "status_alerta": status_bridge,
    }
    # NEP-041 Fase 1: como estágio interno do skill de saída (09), um bridge VERMELHO
    # é um achado diagnóstico a reportar — não uma falha de geração de relatório.
    # Mantém-se como AVISO (visível) em vez de ERRO (que bloquearia o nó terminal).
    status_val = "OK" if status_bridge in ("VERDE", "SEM_DADOS") else "AVISO"
    n4_str = f" → N4={n4:,.0f}" if n4 is not None else ""
    delta_str = f" | Δreal={delta_pct:+.1f}%" if delta_pct is not None else ""
    validacao = ValidacaoItem(
        codigo="VAL-REX-BRIDGE",
        status=status_val,
        mensagem=(f"Bridge {status_bridge}: N1={n1:,.0f} → N2={n2:,.0f} → N3={n3:,.0f}{n4_str}{delta_str}"),
    )
    artifact = ArtifactEnvelope.create(
        payload=waterfall,
        kind=ArtifactKind.RELATORIO_EXECUTIVO,
        schema_name="BridgeWaterfall",
        schema_version="1.0.0",
        created_by=_CREATED_BY,
    )
    return artifact, validacao


def build_relatorio_executivo(canonical_in: Any) -> tuple[dict, list, list]:
    """NEP-041 Fase 1: computa os relatórios executivos como estágio interno de 09.

    Returns:
        (canonical_update, artifacts, validacoes) — onde canonical_update tem as
        chaves relatorio_criticidade/sensibilidade/intervencao para model_copy.
    """
    now = datetime.now(UTC)
    proj = canonical_in.projeto
    resultado = canonical_in.resultado
    artifacts: list = []
    validacoes: list[ValidacaoItem] = []
    status_margem, margem_entrada = _rre_get_margin_status(resultado)

    relatorio_crit, art_crit, val_crit = _rre_build_criticidade(canonical_in.cost_criticality_report, proj, now)
    if art_crit is not None:
        artifacts.append(art_crit)
        validacoes.append(val_crit)
    relatorio_sens, art_sens, val_sens = _rre_build_sensibilidade(
        canonical_in.replan_suggestions, proj, now, status_margem, margem_entrada
    )
    artifacts.append(art_sens)
    validacoes.append(val_sens)
    relatorio_int, art_int, val_int = _rre_build_intervencao(canonical_in.plan_space_result, proj, now, status_margem)
    artifacts.append(art_int)
    validacoes.append(val_int)
    art_bridge, val_bridge = _rre_build_bridge(canonical_in.bridge_analysis, proj, now)
    if art_bridge is not None:
        artifacts.append(art_bridge)
    validacoes.append(val_bridge)

    canonical_update = {
        "relatorio_criticidade": relatorio_crit,
        "relatorio_sensibilidade": relatorio_sens,
        "relatorio_intervencao": relatorio_int,
    }
    return canonical_update, artifacts, validacoes
