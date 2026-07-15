"""Skill 11 — Replan Advisor.

Analisa o canonical após 06-resultado-financeiro/_consolidacao e gera sugestões concretas de re-planejamento
quando status_margem é AMARELO ou VERMELHO.

Cada sugestão inclui: checkpoint_skill, parametros_sugeridos, delta_margem_estimado
e confiança — prontos para uso com `concilium replan plan --from ... --set ...`.

ADR-019 §D1.2.
"""

from datetime import UTC, datetime
from typing import Any

from concilium.application.skills.base import SkillResult
from concilium.domain.models.canonical import (
    CanonicalModel,
    ReplanSugestao,
    ReplanSuggestions,
    StatusMargem,
    ValidacaoItem,
)

_VALID_CHECKPOINTS = {
    "03-catalogo-de-recursos",
    "04-cronograma",
    "05-equipes-e-alocacao",
    "06-resultado-financeiro",
}


def _tem_buy_ou_hire(recomendacoes: list[str]) -> bool:
    termos = ("BUY", "HIRE", "CONTRATAR", "ADQUIRIR", "AQUISIÇÃO")
    return any(any(t in r.upper() for t in termos) for r in recomendacoes)


def _score_sugestao(s: ReplanSugestao) -> float:
    conf_weight = {"ALTA": 1.0, "MEDIA": 0.7, "BAIXA": 0.4}[s.confianca]
    return s.delta_margem_estimado * conf_weight


def _build_history_entry(secao: ReplanSuggestions, margem_atual: float, status_gatilho: str) -> dict:
    """ADR-056 §T5 — constrói entrada para replanning_history."""
    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "status_gatilho": status_gatilho,
        "margem_atual_pct": round(margem_atual * 100, 2),
        "delta_margem_necessario_pct": round(secao.delta_margem_necessario * 100, 2),
        "n_sugestoes": len(secao.sugestoes),
        "sugestao_prioritaria": secao.sugestao_prioritaria,  # str ID, e.g. "REPLAN-001"
    }


def _build_sugestao_pool(conflitos_com_aquisicao: list, delta_necessario: float) -> "ReplanSugestao | None":
    if not conflitos_com_aquisicao:
        return None
    params: dict = {}
    nomes = []
    for c in conflitos_com_aquisicao[:3]:
        params[f"pool.{c.tipo_nome}.quantidade_total"] = f"+{max(1, int(c.excedente) + 1)}"
        nomes.append(c.tipo_nome)
    return ReplanSugestao(
        id="REPLAN-001",
        tipo="RECURSOS",
        checkpoint_skill="03-catalogo-de-recursos",
        parametros_sugeridos=params,
        delta_margem_estimado=round(abs(delta_necessario) * 0.45, 4),
        confianca="MEDIA",
        controle="SEMI_TUNAVEL",
        justificativa=(
            f"Expandir pool de {', '.join(nomes)} elimina custos de aquisição. "
            f"{len(conflitos_com_aquisicao)} conflito(s) BUY/HIRE identificado(s) por 03C."
        ),
        restricoes=[
            "Verificar disponibilidade de equipamento no mercado",
            "Confirmar prazo de mobilização compatível com cronograma",
        ],
    )


def _get_a_plus_atividades(ccr: Any) -> list:
    atividades_cc = getattr(ccr, "atividades", None)
    if atividades_cc is None:
        atividades_cc = ccr.get("atividades", [])  # type: ignore[union-attr]
    return [a for a in atividades_cc if (getattr(a, "classe", None) or a.get("class", "")) == "A+"]  # type: ignore[union-attr]


def _equipes_params_and_meta(top3: list) -> "tuple[dict, float, list]":
    params_equipes: dict = {
        (getattr(a, "atividade_id", None) or a.get("atividade_id", "")): "aumentar num_equipes em +1"  # type: ignore[union-attr]
        for a in top3
    }
    cost_share_total = sum(
        (getattr(a, "custo", None) and a.custo.valor_raw)  # type: ignore[union-attr]
        or a.get("cost_share", 0)  # type: ignore[union-attr]
        for a in top3
    )
    nomes = [getattr(a, "atividade_id", None) or a.get("atividade_id", "") for a in top3]  # type: ignore[union-attr]
    return params_equipes, cost_share_total, nomes


def _build_sugestao_equipes(ccr: Any, delta_necessario: float) -> "ReplanSugestao | None":
    a_plus = _get_a_plus_atividades(ccr)
    if not a_plus:
        return None
    top3 = a_plus[:3]
    params_equipes, cost_share_total, nomes = _equipes_params_and_meta(top3)
    return ReplanSugestao(
        id="REPLAN-002",
        tipo="EQUIPES",
        checkpoint_skill="05-equipes-e-alocacao",
        parametros_sugeridos=params_equipes,
        delta_margem_estimado=round(abs(delta_necessario) * 0.20, 4),
        confianca="BAIXA",
        controle="TUNAVEL",
        justificativa=(
            f"Itens {', '.join(nomes)} são classe A+ e "
            f"representam {cost_share_total * 100:.1f}% do custo. "
            "Mais equipes reduz permanência e custo fixo."
        ),
        restricoes=[
            "Pode não reduzir margem se custo variável superar ganho de prazo",
            "Validar produtividade esperada com equipes paralelas",
        ],
    )


def _build_sugestao_cronograma(canonical_in: "CanonicalModel", delta_necessario: float) -> "ReplanSugestao | None":
    if not (canonical_in.indiretos and canonical_in.resultado):
        return None
    custo_indireto = sum(i.custo_total for i in canonical_in.indiretos)
    custo_total_base = canonical_in.resultado.custo.total
    ratio_ind = custo_indireto / custo_total_base if custo_total_base > 0 else 0.0
    if ratio_ind <= 0.30:
        return None
    return ReplanSugestao(
        id="REPLAN-003",
        tipo="CRONOGRAMA",
        checkpoint_skill="04-cronograma",
        parametros_sugeridos={"algorithm": "MINSLK", "deadline_margin_pct": "0.05"},
        delta_margem_estimado=round((ratio_ind - 0.25) * 0.6, 4),
        confianca="MEDIA",
        controle="TUNAVEL",
        justificativa=(
            f"Indiretos representam {ratio_ind * 100:.1f}% do custo total (acima de 30%). "
            "Compactar cronograma reduz permanências de ADM/TOP/LAB/QSMS."
        ),
        restricoes=[
            "Verificar praticabilidade do prazo compactado",
            "Confirmar capacidade de equipes para ritmo acelerado",
        ],
    )


def _build_sugestao_bdi(margem_atual: float, delta_necessario: float) -> ReplanSugestao:
    return ReplanSugestao(
        id="REPLAN-005",
        tipo="BDI",
        checkpoint_skill="06-resultado-financeiro",
        parametros_sugeridos={},
        delta_margem_estimado=round(abs(delta_necessario) * 0.25, 4),
        confianca="BAIXA",
        justificativa=(
            f"Margem {margem_atual * 100:.1f}% abaixo da faixa alvo. "
            "Revisar composição de BDI e custos indiretos (ADM/TOP/LAB/QSMS/MOB) "
            "pode revelar espaço para redução."
        ),
        restricoes=[
            "Necessário levantamento detalhado dos indiretos para estimativa precisa",
            "Execute 06-resultado-financeiro antes para dados completos",
        ],
    )


def _collect_sugestoes(
    canonical_in: "CanonicalModel", delta_necessario: float, margem_atual: float, status_gatilho: Any
) -> list:
    sugestoes: list[ReplanSugestao] = []
    conflitos_com_aquisicao = [c for c in canonical_in.conflitos_pico if _tem_buy_ou_hire(c.recomendacoes)]
    s1 = _build_sugestao_pool(conflitos_com_aquisicao, delta_necessario)
    if s1:
        sugestoes.append(s1)
    if canonical_in.cost_criticality_report:
        s2 = _build_sugestao_equipes(canonical_in.cost_criticality_report, delta_necessario)
        if s2:
            sugestoes.append(s2)
    s3 = _build_sugestao_cronograma(canonical_in, delta_necessario)
    if s3:
        sugestoes.append(s3)
    if not sugestoes:
        sugestoes.append(_build_sugestao_bdi(margem_atual, delta_necessario))
    return sugestoes


def _build_validacoes_replan(
    sugestoes: list, delta_necessario: float, sugestao_prioritaria: "str | None", status_gatilho: Any
) -> list:
    validacoes: list[ValidacaoItem] = []
    if not sugestoes:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-REPLAN-01",
                status="AVISO",
                mensagem=f"Status {status_gatilho} mas sem sugestões geradas. Dados insuficientes para análise.",
            )
        )
    else:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-REPLAN-01",
                status="OK",
                mensagem=(
                    f"{len(sugestoes)} sugestão(ões) para recuperar Δ={delta_necessario * 100:.2f}% de margem. "
                    f"Prioritária: {sugestao_prioritaria}."
                ),
            )
        )
    checkpoints_invalidos = [s.id for s in sugestoes if s.checkpoint_skill not in _VALID_CHECKPOINTS]
    if checkpoints_invalidos:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-REPLAN-02",
                status="ERRO",
                mensagem=f"Sugestões com checkpoint inválido: {checkpoints_invalidos}",
            )
        )
    else:
        validacoes.append(ValidacaoItem(codigo="VAL-REPLAN-02", status="OK"))
    return validacoes


def run_assessor_replanejamento(
    canonical_in: CanonicalModel,
    inputs: dict[str, Any],
    perfil: dict[str, Any] | None = None,
) -> SkillResult:
    """Popula 'replan_suggestions' com sugestões priorizadas de re-planejamento.

    Pré-condições: resultado (06) populado.
    Se margem VERDE, retorna seção vazia sem erro.
    """
    validacoes: list[ValidacaoItem] = []

    if canonical_in.resultado is None:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-REPLAN-PRECONDICAO",
                status="ERRO",
                mensagem="06-resultado-financeiro/_consolidacao deve ser executada antes: canonical.resultado ausente.",
            )
        )
        return SkillResult(canonical_in, validacoes)

    # Prefere resultado reconciliado se disponível
    recon = canonical_in.resultado_reconciliado
    if recon is not None:
        margem_atual = recon.margem_reconciliada_pct
        status_gatilho: StatusMargem = recon.status_margem_reconciliado
    else:
        margem_atual = canonical_in.resultado.margem_pct
        status_gatilho = canonical_in.resultado.status_margem

    # VERDE -> nada a fazer
    if status_gatilho == "VERDE":
        secao = ReplanSuggestions(
            status_gatilho="VERDE",
            delta_margem_necessario=0.0,
            sugestoes=[],
            sugestao_prioritaria=None,
        )
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-REPLAN-01",
                status="OK",
                mensagem=f"Margem {margem_atual * 100:.2f}% VERDE. Nenhum replanejamento necessário.",
            )
        )
        history = list(canonical_in.replanning_history or [])
        history.append(_build_history_entry(secao, margem_atual, str(status_gatilho)))
        return SkillResult(
            canonical_in.model_copy(update={"replan_suggestions": secao, "replanning_history": history}),
            validacoes,
        )

    # Thresholds do perfil
    faixa_alvo = {"min": 0.08, "max": 0.10}
    faixa_aceitavel = {"min": 0.06, "max": 0.12}
    if perfil:
        faixa_alvo = perfil.get("faixa_margem_alvo", faixa_alvo)
        faixa_aceitavel = perfil.get("faixa_margem_aceitavel", faixa_aceitavel)

    meta_override = inputs.get("meta_margem_alvo")
    if meta_override is not None:
        faixa_alvo["min"] = float(meta_override)

    delta_necessario = round(
        faixa_alvo["min"] - margem_atual if status_gatilho == "AMARELO" else faixa_aceitavel["min"] - margem_atual,
        6,
    )

    sugestoes = _collect_sugestoes(canonical_in, delta_necessario, margem_atual, status_gatilho)
    sugestoes.sort(key=_score_sugestao, reverse=True)
    sugestao_prioritaria = sugestoes[0].id if sugestoes else None

    validacoes = _build_validacoes_replan(sugestoes, delta_necessario, sugestao_prioritaria, status_gatilho)

    secao = ReplanSuggestions(
        status_gatilho=status_gatilho,
        delta_margem_necessario=delta_necessario,
        sugestoes=sugestoes,
        sugestao_prioritaria=sugestao_prioritaria,
    )
    history = list(canonical_in.replanning_history or [])
    history.append(_build_history_entry(secao, margem_atual, str(status_gatilho)))
    return SkillResult(
        canonical_in.model_copy(update={"replan_suggestions": secao, "replanning_history": history}),
        validacoes,
    )
