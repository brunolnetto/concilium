"""Skill 14 — Plan Space Explorer (ADR-021 / ADR-082 revisado).

Explora o espaço de intervenções sobre o plano:
  - AMARELO/VERMELHO: busca greedy por sequência mínima que atinge VERDE
  - VERDE: scan de oportunidades de aumento de margem

Levers derivados diretamente dos LeverEquilibrio reais (ADR-082) já calculados em
``canonical.ponto_equilibrio[].levers_equilibrio`` — com deltas em R$ auditáveis e
base de margem operacional honesta (venda_plus, custo instancial real, ADR-085).

Mapeamento lever_id → Lever.tipo:
  fechar_gap_escala           → SERIALIZAR_CRONOGRAMA
  fechar_gap_praticabilidade  → MELHORAR_PRATICABILIDADE
  fechar_gap_pool             → OTIMIZAR_POOL
  revisao_bdi_minima          → RECALIBRAR_PU
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from concilium.application.skills.base import SkillResult
from concilium.domain.models.canonical import (
    CanonicalModel,
    Lever,
    OportunidadeVerde,
    PlanSpaceResult,
    RepairPath,
    RepairStep,
    StatusMargem,
    ValidacaoItem,
)

_LEVER_ID_TO_TIPO: dict[str, str] = {
    "fechar_gap_escala":          "SERIALIZAR_CRONOGRAMA",
    "fechar_gap_praticabilidade": "MELHORAR_PRATICABILIDADE",
    "fechar_gap_pool":            "OTIMIZAR_POOL",
    "revisao_bdi_minima":         "RECALIBRAR_PU",
}
_LEVER_CHECKPOINT: dict[str, str] = {
    "SERIALIZAR_CRONOGRAMA":    "04-cronograma",
    "MELHORAR_PRATICABILIDADE": "04-cronograma",
    "OTIMIZAR_POOL":            "05-equipes-e-alocacao",
    "RECALIBRAR_PU":            "06-precificacao-unitaria",
}
_LEVER_CONFIANCA: dict[str, str] = {
    "SERIALIZAR_CRONOGRAMA":    "ALTA",
    "MELHORAR_PRATICABILIDADE": "MEDIA",
    "OTIMIZAR_POOL":            "ALTA",
    "RECALIBRAR_PU":            "MEDIA",
}


def _classify_status(margem: float, faixa_alvo: dict, faixa_aceitavel: dict) -> StatusMargem:
    if margem >= faixa_alvo["min"]:
        return "VERDE"
    if margem >= faixa_aceitavel["min"]:
        return "AMARELO"
    return "VERMELHO"


def _build_levers(
    canonical_in: CanonicalModel,
    venda: float,
) -> list[Lever]:
    """Agrega LeverEquilibrio reais (ADR-082) de ponto_equilibrio em Levers do PlanSpace.

    Cada LeverEquilibrio tem ``delta_margin`` em R$ e ``delta_margin_pct`` como fração
    da venda_cpu do item. Agrupa por tipo de ação e soma os deltas para obter o impacto
    total de cada intervenção sobre toda a carteira de atividades.

    Base: venda_plus (custo instancial × BDI) — o preço operacional honesto.
    Todos os overheads imputados são explicáveis e auditáveis no CuboPoolInstancial.
    """
    if venda <= 0:
        return []

    # Agrega por tipo PSE: soma delta_margin_pct de todos os itens
    agg: dict[str, dict] = defaultdict(lambda: {
        "delta_rs": 0.0, "delta_pct": 0.0, "itens": [], "restricoes": []
    })

    for pe in (canonical_in.ponto_equilibrio or []):
        for lv in (pe.levers_equilibrio or []):
            tipo_pse = _LEVER_ID_TO_TIPO.get(lv.id)
            if tipo_pse is None:
                continue
            d = agg[tipo_pse]
            d["delta_rs"] += float(lv.delta_margin or 0.0)
            # delta_margin_pct é relativo à venda_cpu do item; reescalamos para venda total
            item_venda = float(pe.custo_venda_cpu or 0.0)
            if item_venda > 0 and venda > 0:
                d["delta_pct"] += float(lv.delta_margin or 0.0) / venda
            d["itens"].append(pe.item_id)
            d["restricoes"].extend(lv.restricoes or [])

    levers: list[Lever] = []
    for tipo_pse, d in agg.items():
        delta_rs = round(d["delta_rs"], 2)
        delta_pct = round(d["delta_pct"], 6)
        if delta_rs <= 0:
            continue
        n_itens = len(set(d["itens"]))
        restricoes_unicas = list(dict.fromkeys(d["restricoes"]))[:3]
        restr_txt = "; ".join(restricoes_unicas) if restricoes_unicas else ""
        levers.append(
            Lever(
                tipo=tipo_pse,
                checkpoint_skill=_LEVER_CHECKPOINT[tipo_pse],
                parametros={
                    "delta_margem_rs": str(int(delta_rs)),
                    "n_atividades": str(n_itens),
                    "itens": ",".join(sorted(set(d["itens"])))[:200],
                },
                delta_margem_estimado=delta_pct,
                custo_aplicacao=0.0,
                ratio_beneficio=round(delta_pct, 6),
                confianca=_LEVER_CONFIANCA[tipo_pse],
                controle="TUNAVEL",
                justificativa=(
                    f"{tipo_pse} — {n_itens} atividade(s). "
                    f"Δ margem R$ {delta_rs:,.0f} ({delta_pct * 100:.2f}% da venda). "
                    + (f"Restrições: {restr_txt}" if restr_txt else "Sem restrições identificadas.")
                ),
            )
        )

    # Fallback: se ponto_equilibrio não populado, lever heurístico conservador
    if not levers:
        indiretos = canonical_in.indiretos or []
        custo_ind = sum(i.custo_total for i in indiretos)
        proj = canonical_in.projeto
        semanas_total = max(int((proj.data_termino - proj.data_inicio).days / 7), 1)
        if custo_ind > 0:
            dm = round(0.10 * custo_ind / venda, 6)
            levers.append(Lever(
                tipo="REDUCE_DURATION", checkpoint_skill="04-cronograma",
                parametros={"deadline_weeks": str(int(semanas_total * 0.9))},
                delta_margem_estimado=dm, custo_aplicacao=0.0, ratio_beneficio=dm,
                confianca="BAIXA", controle="TUNAVEL",
                justificativa="Fallback: redução de 10% no prazo → corte proporcional de indiretos.",
            ))

    levers.sort(key=lambda lv: -lv.ratio_beneficio)
    return levers


def _repair_path(
    levers: list[Lever],
    margem_entrada: float,
    faixa_alvo: dict,
    faixa_aceitavel: dict,
) -> RepairPath:
    """Busca greedy: aplica levers em ordem de ratio até cruzar faixa_alvo.min."""
    margem = margem_entrada
    passos: list[RepairStep] = []

    for lever in levers:
        if margem >= faixa_alvo["min"]:
            break
        margem = round(margem + lever.delta_margem_estimado, 6)
        status = _classify_status(margem, faixa_alvo, faixa_aceitavel)
        passos.append(
            RepairStep(
                ordem=len(passos) + 1,
                lever=lever,
                margem_acumulada_apos=margem,
                status_apos=status,
            )
        )

    viavel = margem >= faixa_alvo["min"]
    return RepairPath(
        viavel=viavel,
        passos=passos,
        margem_projetada=round(margem, 6),
        status_projetado=_classify_status(margem, faixa_alvo, faixa_aceitavel),
    )


def _risco_lever(lever: Lever) -> str:
    if lever.confianca == "ALTA":
        return "BAIXO"
    if lever.confianca == "BAIXA":
        return "ALTO"
    return "MEDIO"


def _rec_build_oportunidades(levers: list, levers_nao_usados: list | None = None) -> list:
    """Builds OportunidadeVerde list from levers."""
    source = levers_nao_usados if levers_nao_usados is not None else levers
    result = []
    for lv in source:
        result.append(
            OportunidadeVerde(lever=lv, margem_adicional_estimada=lv.delta_margem_estimado, risco=_risco_lever(lv))
        )
    return result


def run_explorador_cenarios(
    canonical_in: CanonicalModel,
    inputs: dict[str, Any],
    perfil: dict[str, Any] | None = None,
) -> SkillResult:
    """Popula 'plan_space_result' com repair_path e/ou oportunidades.

    Base de margem: venda_plus (preço operacional honesto, ADR-085 D5).
    Levers: derivados de canonical.ponto_equilibrio[].levers_equilibrio (ADR-082).
    """
    validacoes: list[ValidacaoItem] = []

    resultado = canonical_in.resultado
    recon = canonical_in.resultado_reconciliado

    if resultado is None:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-PSE-PRECONDICAO",
                status="ERRO",
                mensagem="resultado (08) ausente — execute 08-consolidar antes.",
            )
        )
        return SkillResult(canonical_in, validacoes)

    # Base operacional honesta: venda_plus (custo instancial × BDI, ADR-085)
    # Fallback para total_com_bdi (catálogo) se venda_plus ausente
    venda_plus = float(resultado.venda.total_custo_plus or 0.0)
    venda = venda_plus if venda_plus > 0 else float(resultado.venda.total_com_bdi or 0.0)

    # Margem operacional: resultado_financeiro / venda_plus (já calculado em skill-08)
    margem_entrada = float(resultado.margem_pct or 0.0)
    status_entrada: StatusMargem = resultado.status_margem or "VERMELHO"

    # Thresholds
    faixa_alvo = {"min": 0.08, "max": 0.10}
    faixa_aceitavel = {"min": 0.06, "max": 0.12}
    if perfil:
        faixa_alvo = perfil.get("faixa_margem_alvo", faixa_alvo)
        faixa_aceitavel = perfil.get("faixa_margem_aceitavel", faixa_aceitavel)

    levers = _build_levers(canonical_in, venda)

    repair: RepairPath | None = None
    oportunidades: list[OportunidadeVerde] = []

    if status_entrada != "VERDE":
        repair = _repair_path(levers, margem_entrada, faixa_alvo, faixa_aceitavel)
        levers_nao_usados = levers[len(repair.passos):]
        oportunidades = _rec_build_oportunidades(levers, levers_nao_usados)
    else:
        oportunidades = sorted(_rec_build_oportunidades(levers), key=lambda o: -o.margem_adicional_estimada)

    psr = PlanSpaceResult(
        status_entrada=status_entrada,
        margem_entrada=round(margem_entrada, 6),
        repair_path=repair,
        oportunidades=oportunidades,
    )

    novo = canonical_in.model_copy(update={"plan_space_result": psr})
    validacoes.append(ValidacaoItem(codigo="VAL-PSE-01", status="OK"))

    if repair is not None:
        viavel_str = "viável" if repair.viavel else "incompleto"
        status_rep = "OK" if repair.viavel else "AVISO"
        # Converte delta de frações para R$ para a mensagem
        delta_total_rs = sum(lv.delta_margem_estimado * venda for lv in levers)
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-PSE-02",
                status=status_rep,
                mensagem=(
                    f"Repair {viavel_str}: margem projetada {repair.margem_projetada * 100:.2f}%"
                    f" em {len(repair.passos)} passo(s). "
                    f"Potencial total dos levers: R$ {delta_total_rs:,.0f} "
                    f"({len(levers)} lever(s) de {', '.join(set(lv.tipo for lv in levers))})."
                ),
            )
        )
    else:
        delta_total_rs = sum(lv.delta_margem_estimado * venda for lv in levers)
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-PSE-02",
                status="OK",
                mensagem=(
                    f"Plano {status_entrada}. {len(oportunidades)} oportunidade(s). "
                    f"Potencial R$ {delta_total_rs:,.0f} em melhorias adicionais de margem."
                ),
            )
        )

    return SkillResult(novo, validacoes)
