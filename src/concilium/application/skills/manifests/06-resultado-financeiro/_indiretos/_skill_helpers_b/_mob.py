"""Skill 05 — Indiretos (ADR-009, ADR-023 §D4).

Custo MOB legado, fases explícitas de mobilização/operação/desmobilização.
"""

from __future__ import annotations

import logging

from concilium.application.scheduling.mob_scheduling import calcular_custo_indireto_mob
from concilium.domain.models.canonical import (
    CanonicalModel,
    IndirectoCategoria,
    IndirectoCostComponent,
    Indireto,
    IndiretoSemanal,
    Mobilizacao,
)
from concilium.domain.models.project.decision_variables import DecisionVariables

from ._breakdown import _build_semanal_breakdown  # ty: ignore[unresolved-import]

logger = logging.getLogger(__name__)


def _custo_mob_legado(dados_mob: dict, num_pessoas_direta: int, prazo_meses: int) -> tuple[float, list[Mobilizacao]]:
    """Calcula custo MOB legado (retrocompatível com formato anterior)."""
    custo_total = 0.0
    mobilizacoes: list[Mobilizacao] = []
    for m in dados_mob.get("mobilizacoes", []):
        mob = Mobilizacao(
            descricao=m["descricao"],
            num_unidades=m["num_unidades"],
            origem=m["origem"],
            destino=m["destino"],
            distancia_km=m["distancia_km"],
            custo_km=m["custo_km"],
            custo_total=m["num_unidades"] * m["distancia_km"] * m["custo_km"],
        )
        mobilizacoes.append(mob)
        custo_total += mob.custo_total
    custo_pessoa_mes = dados_mob.get(
        "custo_pessoa_mes", 1850
    )  # B3-known: R$1.850 legado; idealmente derivar do catálogo
    custo_total += num_pessoas_direta * custo_pessoa_mes * prazo_meses
    for b in dados_mob.get("baixadas", []):
        n_ocorrencias = len(b.get("meses_ocorrencia", []))
        custo_total += b.get("num_pessoas", 0) * b.get("valor_por_pessoa", 0) * n_ocorrencias
    return round(custo_total, 2), mobilizacoes


def _extract_overrides(inputs: dict) -> dict | None:
    val = inputs.get("insumos_override")
    if isinstance(val, dict):
        return val
    return None


def _count_pessoas_diretas(canonical_in: CanonicalModel) -> int:
    return sum(sum(f.num_pessoas for f in eq.funcoes) for eq in canonical_in.equipes_diretas)


def _get_pipeline_blocked(canonical_in: CanonicalModel) -> set:
    return set(canonical_in.pipeline_blocked_from or [])


def _extract_dv4_policy(inputs: dict) -> str | None:
    dv_obj = inputs.get("decision_variables") or inputs.get("dv")
    if dv_obj is None:
        return None
    if isinstance(dv_obj, dict):
        return dv_obj.get("dv4_indirect_policy")
    if isinstance(dv_obj, DecisionVariables):
        return dv_obj.dv4_indirect_policy
    return getattr(dv_obj, "dv4_indirect_policy", None)


def _process_mob_categoria(
    cat: dict,
    categorias_config_raw: list,
    dados_mob: dict,
    num_pessoas_direta: int,
    prazo_meses: int,
    n_semanas: int,
    dv4_policy: str | None,
    policy_scale: dict,
    mob_schedule: dict | None = None,
) -> tuple[Indireto, list[IndiretoSemanal]]:
    descricao: str = cat["descricao"]
    cat_cfg_raw = next((c for c in categorias_config_raw if c.get("categoria") == "MOB"), None)
    if cat_cfg_raw:
        cat_obj = IndirectoCategoria(**cat_cfg_raw)
        custo = cat_obj.custo_fixo_total
        mobs: list[Mobilizacao] = []
    else:
        custo, mobs = _custo_mob_legado(dados_mob, num_pessoas_direta, prazo_meses)
        cat_obj = IndirectoCategoria(
            categoria="MOB",
            driver="one_time",
            custo_fixo_total=custo,
            verbas=IndirectoCostComponent(nome="MOB", custo_fixo_mensal=0.0),
        )
    if dv4_policy and dv4_policy in policy_scale:
        custo = round(custo * policy_scale[dv4_policy], 2)
        cat_obj = cat_obj.model_copy(update={"custo_fixo_total": custo})

    # ADR-105: Se mob_schedule disponível, calcular distribuição por fase MOB/OP/DEMOB.
    # B1-fix (2026-06-19): resultado era descartado (try/pass dead code); agora loga
    # a distribuição e atualiza custo quando mob_schedule fornece total mais preciso.
    if mob_schedule:
        try:
            indiretos_mob = [
                {
                    "tipo": "MOB",
                    "categoria": "MOB",
                    "fase": "mobilizacao",
                    "driver": "projeto",
                    "custo_fixo_total": custo,  # B2-fix: usar custo real, não 0.15×custo
                }
            ]
            mob_result = calcular_custo_indireto_mob(indiretos_mob, mob_schedule)
            mob_total = mob_result.get("custo_mob_total", 0.0)
            if mob_total > 0:
                custo = round(mob_total, 2)
                cat_obj = cat_obj.model_copy(update={"custo_fixo_total": custo})
                logger.debug(
                    "MOB custo atualizado via mob_schedule: R$%.2f (fases: %s)",
                    custo,
                    list(mob_result.get("mob", {}).keys()),
                )
        except Exception as e:  # pragma: no cover
            logger.warning(
                "Falha ao calcular custo MOB com mob_schedule — usando custo legado R$%.2f: %s",
                custo,
                e,
                exc_info=True,
            )

    indir = Indireto(
        categoria="MOB",
        descricao=descricao,
        mobilizacoes=mobs,
        permanencia_meses=float(prazo_meses),
        custo_total=custo,
        # ADR-090: MOB é overhead administrativo → BDI_indireto
        custo_mobilizacao=round(custo, 2),
    )
    return indir, _build_semanal_breakdown(cat_obj, n_semanas)


def _accrue_mobilizacao_fase(item: dict, semanal: dict[int, float], duracao_semanas: int) -> float:
    custo = float(item.get("custo_fixo_total", 0.0) or 0.0)
    if duracao_semanas > 0:
        semanal[0] = round(semanal[0] + custo, 2)
    return custo


def _accrue_operacao_fase(item: dict, semanal: dict[int, float], duracao_semanas: int, duracao_meses: float) -> float:
    custo_mensal = float(item.get("custo_fixo_mensal", 0.0) or 0.0)
    custo_total_op = custo_mensal * duracao_meses
    if duracao_semanas > 0:
        custo_por_semana = custo_total_op / duracao_semanas
        acumulado = 0.0
        for s in range(duracao_semanas):
            if s < duracao_semanas - 1:
                parcela = round(custo_por_semana, 2)
            else:
                # última semana recebe o resíduo para preservar conservação
                parcela = round(custo_total_op - acumulado, 2)
            semanal[s] = round(semanal[s] + parcela, 2)
            acumulado += parcela
    return custo_total_op


def _accrue_desmobilizacao_fase(
    item: dict, semanal: dict[int, float], semana_final: int, duracao_semanas: int
) -> float:
    custo = float(item.get("custo_fixo_total", 0.0) or 0.0)
    if duracao_semanas > 0:
        semanal[semana_final] = round(semanal[semana_final] + custo, 2)
    return custo


def _distribuir_mob_fases(
    mob_items: list[dict],
    duracao_semanas: int,
) -> dict:
    """Distribui itens MOB com fases explícitas em custos por semana (ADR-105 F4/F5).

    Suporta três fases tipificadas para itens com campo ``fase``:

    - ``driver="projeto", fase="mobilizacao"``: custo único na semana 0 (início).
    - ``driver="mensal", fase="operacao"``: custo distribuído proporcionalmente
      ao longo de todas as semanas (custo_fixo_mensal × duracao_meses).
    - ``driver="projeto", fase="desmobilizacao"``: custo único na semana final
      (semana duracao_semanas - 1).

    Itens sem campo ``fase`` (legado) são passados adiante sem processamento
    — backward compat: não alteram o resultado.

    Args:
        mob_items: lista de dicts com chaves ``tipo``, ``fase``, ``driver``,
            ``custo_fixo_total`` ou ``custo_fixo_mensal``.
        duracao_semanas: duração total do projeto em semanas (>= 1).

    Returns:
        Dict com:
          - ``total_mob``: soma dos ``custo_fixo_total`` de fase=mobilizacao
          - ``total_operacao``: custo total de fase=operacao (mensal × meses)
          - ``total_demob``: soma dos ``custo_fixo_total`` de fase=desmobilizacao
          - ``semanal``: Dict[int, float] → custo por semana (0-indexed)
    """
    from concilium.domain.constants import SEMANAS_POR_MES as _SEM_MES

    total_mob = 0.0
    total_operacao = 0.0
    total_demob = 0.0

    # Semana última do projeto (0-indexed)
    semana_final = max(duracao_semanas - 1, 0)
    duracao_meses = duracao_semanas / _SEM_MES

    # semanal[s] acumula custo de todos os itens na semana s
    semanal: dict[int, float] = {s: 0.0 for s in range(duracao_semanas)}

    for item in mob_items:
        fase = item.get("fase")
        driver = item.get("driver", "")

        if fase is None:
            # Legado: item sem fase — sem modificação, backward compat
            continue

        if fase == "mobilizacao" and driver == "projeto":
            total_mob += _accrue_mobilizacao_fase(item, semanal, duracao_semanas)
        elif fase == "operacao" and driver == "mensal":
            total_operacao += _accrue_operacao_fase(item, semanal, duracao_semanas, duracao_meses)
        elif fase == "desmobilizacao" and driver == "projeto":
            total_demob += _accrue_desmobilizacao_fase(item, semanal, semana_final, duracao_semanas)

    return {
        "total_mob": round(total_mob, 2),
        "total_operacao": round(total_operacao, 2),
        "total_demob": round(total_demob, 2),
        "semanal": semanal,
    }


