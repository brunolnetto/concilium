"""Skill 14 — Plan Space Explorer (ADR-021).

Explora o espaço combinatorial de intervenções sobre o plano:
  - AMARELO/VERMELHO: busca greedy por sequência mínima de levers que atinge VERDE
  - VERDE: scan de sensibilidade revelando oportunidades de aumento de margem

Levers disponíveis:
  EXPAND_POOL       — elimina delta de BUY/HIRE via pool próprio
  REDUCE_DURATION   — reduz indiretos proporcionalmente à compressão de prazo
  ADD_TEAMS         — reduz permanência em atividades A+ (confiança BAIXA)
  REVIEW_BDI        — revisão de composição de BDI (confiança BAIXA, catch-all)
"""

from __future__ import annotations

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

_REVIEW_BDI_DELTA = 0.018  # estimativa heurística conservadora de ganho de margem
_ADD_TEAMS_PERMANENCIA_GAIN = 0.20  # redução de permanência com mais equipes
_ADD_TEAMS_COST_SENSITIVITY = 0.10  # % de redução de custo direto por menos permanência
_EXPAND_POOL_EFFICIENCY = 0.80  # fração do delta_reconciliado evitável com pool próprio


def _classify_status(margem: float, faixa_alvo: dict, faixa_aceitavel: dict) -> StatusMargem:
    if margem >= faixa_alvo["min"]:
        return "VERDE"
    if margem >= faixa_aceitavel["min"]:
        return "AMARELO"
    return "VERMELHO"


def _semanas_projeto(canonical_in: CanonicalModel) -> int:
    """Retorna duração total do projeto em semanas a partir das datas do projeto."""
    proj = canonical_in.projeto
    delta = (proj.data_termino - proj.data_inicio).days
    return max(int(delta / 7), 1)


def _bl_expand_pool_lever(recon, venda: float):
    """Builds EXPAND_POOL lever or returns None if not applicable."""
    if recon is None or recon.delta_custo_total <= 0 or venda <= 0:
        return None
    delta_evitavel = recon.delta_custo_total * _EXPAND_POOL_EFFICIENCY
    dm = round(delta_evitavel / venda, 6)
    nomes = list({item.tipo_nome for item in recon.itens_aquisicao})[:3]
    return Lever(
        tipo="EXPAND_POOL",
        checkpoint_skill="03-catalogo-de-recursos",
        parametros={f"pool.{n}.quantidade_total": "+1" for n in nomes},
        delta_margem_estimado=dm,
        custo_aplicacao=recon.delta_custo_total * 0.20,
        ratio_beneficio=round(dm / max(recon.delta_custo_total * 0.20 / venda, 1e-6), 4),
        confianca="ALTA",
        controle="SEMI_TUNAVEL",
        justificativa=(
            f"Elimina {dm * 100:.2f}% de custo de aquisi\u00e7\u00e3o BUY/HIRE ({len(recon.itens_aquisicao)} item(s)). "
            "Requer verifica\u00e7\u00e3o de disponibilidade de mercado."
        ),
    )


def _bl_reduce_duration_lever(canonical_in, venda: float, inputs: dict):
    """Builds REDUCE_DURATION lever or returns None if not applicable."""
    indiretos = canonical_in.indiretos or []
    custo_indireto_total = sum(i.custo_total for i in indiretos)
    if custo_indireto_total <= 0 or venda <= 0:
        return None
    semanas_total = _semanas_projeto(canonical_in)
    semanas_reducao = int(inputs.get("semanas_reducao_alvo", max(2, semanas_total * 0.10)))
    fracao_reducao = semanas_reducao / semanas_total
    dm = round(fracao_reducao * custo_indireto_total / venda, 6)
    return Lever(
        tipo="REDUCE_DURATION",
        checkpoint_skill="04-cronograma",
        parametros={
            "deadline_weeks": str(semanas_total - semanas_reducao),
            "algorithm": "MINSLK",
        },
        delta_margem_estimado=dm,
        custo_aplicacao=0.0,
        ratio_beneficio=round(dm / max(fracao_reducao, 1e-6), 4),
        confianca="MEDIA",
        controle="TUNAVEL",
        justificativa=(
            f"Reduzir {semanas_reducao} sem. ({fracao_reducao * 100:.0f}% do prazo) "
            f"corta indiretos em ~{dm * 100:.2f}% de margem. "
            "Verificar praticabilidade do ritmo acelerado."
        ),
    )


def _batl_custo_a_plus(a_plus: list, resultado: Any) -> float:
    """Computes custo_a_plus sum for ADD_TEAMS lever."""
    total = resultado.custo.total or 0
    result = 0.0
    for a in a_plus:
        result += getattr(a.custo, "valor_raw", 0.0) * total
    return result


def _bl_add_teams_lever(canonical_in, venda: float):
    """Builds ADD_TEAMS lever or returns None if not applicable."""
    ccr = canonical_in.cost_criticality_report
    if ccr is None:
        return None
    atividades_cc = getattr(ccr, "atividades", None) or []
    a_plus = [a for a in atividades_cc if getattr(a, "classe", "") == "A+"]
    if not a_plus or not canonical_in.resultado:
        return None
    custo_a_plus = _batl_custo_a_plus(a_plus, canonical_in.resultado)
    dm = round(custo_a_plus * _ADD_TEAMS_COST_SENSITIVITY * _ADD_TEAMS_PERMANENCIA_GAIN / max(venda, 1), 6)
    if dm <= 0:
        return None
    top3 = a_plus[:3]
    params = {}
    for a in top3:
        params[getattr(a, "atividade_id", "?")] = "+1 equipe"
    return Lever(
        tipo="ADD_TEAMS",
        checkpoint_skill="03-equipes-diretas",
        parametros=params,
        delta_margem_estimado=dm,
        custo_aplicacao=0.0,
        ratio_beneficio=round(dm, 6),
        confianca="BAIXA",
        controle="TUNAVEL",
        justificativa=(
            f"{len(a_plus)} atividade(s) A+. Mais equipes reduz permanência em "
            f"~{_ADD_TEAMS_PERMANENCIA_GAIN * 100:.0f}% -> ganho estimado de {dm * 100:.2f}% de margem."
        ),
    )


def _build_levers(
    canonical_in: CanonicalModel,
    margem_atual: float,
    venda: float,
    faixa_alvo: dict,
    inputs: dict,
) -> list[Lever]:
    """Constrói lista de levers disponíveis a partir do estado canônico."""
    levers: list[Lever] = []
    recon = canonical_in.resultado_reconciliado
    lv = _bl_expand_pool_lever(recon, venda)
    if lv is not None:
        levers.append(lv)
    lv = _bl_reduce_duration_lever(canonical_in, venda, inputs)
    if lv is not None:
        levers.append(lv)
    lv = _bl_add_teams_lever(canonical_in, venda)
    if lv is not None:
        levers.append(lv)
    # ── REVIEW_BDI: catch-all heurístico ─────────────────────
    if venda > 0:
        levers.append(
            Lever(
                tipo="REVIEW_BDI",
                checkpoint_skill="07-custos-indiretos",
                parametros={},
                delta_margem_estimado=_REVIEW_BDI_DELTA,
                custo_aplicacao=0.0,
                ratio_beneficio=_REVIEW_BDI_DELTA,
                confianca="BAIXA",
                controle="SEMI_TUNAVEL",
                justificativa=(
                    "Revisão da composição de BDI e custos indiretos. "
                    "Estimativa conservadora de 1.8% de ganho de margem com otimização de categorias."
                ),
            )
        )
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
    if lever.confianca == "ALTA" and lever.tipo in ("REDUCE_DURATION", "EXPAND_POOL"):
        return "BAIXO"
    if lever.confianca == "BAIXA" or lever.tipo == "ADD_TEAMS":
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

    Pré-condição: resultado (06) populado.
    """
    validacoes: list[ValidacaoItem] = []

    recon = canonical_in.resultado_reconciliado
    resultado = canonical_in.resultado

    if resultado is None:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-PSE-PRECONDICAO",
                status="ERRO",
                mensagem="resultado (06) ausente — execute 06-consolidar antes.",
            )
        )
        return SkillResult(canonical_in, validacoes)

    # Prefere resultado reconciliado
    margem_entrada = recon.margem_reconciliada_pct if recon else resultado.margem_pct
    status_entrada: StatusMargem = recon.status_margem_reconciliado if recon else resultado.status_margem
    venda = recon.venda_total_com_bdi if recon else resultado.venda.total_com_bdi

    # Thresholds
    faixa_alvo = {"min": 0.08, "max": 0.10}
    faixa_aceitavel = {"min": 0.06, "max": 0.12}
    if perfil:
        faixa_alvo = perfil.get("faixa_margem_alvo", faixa_alvo)
        faixa_aceitavel = perfil.get("faixa_margem_aceitavel", faixa_aceitavel)

    levers = _build_levers(canonical_in, margem_entrada, venda, faixa_alvo, inputs)

    repair: RepairPath | None = None
    oportunidades: list[OportunidadeVerde] = []

    if status_entrada != "VERDE":
        repair = _repair_path(levers, margem_entrada, faixa_alvo, faixa_aceitavel)
        levers_nao_usados = levers[len(repair.passos) :]
        oportunidades = _rec_build_oportunidades(levers, levers_nao_usados)
    else:
        # VERDE: todos os levers são oportunidades de melhoria
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
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-PSE-02",
                status=status_rep,
                mensagem=(
                    f"Repair {viavel_str}: margem projetada {repair.margem_projetada * 100:.2f}%"
                    f" em {len(repair.passos)} passo(s)."
                ),
            )
        )
    else:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-PSE-02",
                status="OK",
                mensagem=f"Plano VERDE. {len(oportunidades)} oportunidade(s) de melhoria mapeadas.",
            )
        )

    return SkillResult(novo, validacoes)
