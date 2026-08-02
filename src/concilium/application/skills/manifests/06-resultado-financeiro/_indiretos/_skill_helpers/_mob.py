"""Skill 06 (_indiretos) — Indiretos (ADR-009, ADR-023 §D4).

Custo MOB composicional (item a item: mobilizações, baixadas, alimentação por
equipe) e fases explícitas de mobilização/operação/desmobilização.
"""

from __future__ import annotations

import logging

from concilium.application.scheduling.mob_scheduling import calcular_custo_indireto_mob
from concilium.domain.constants import SEMANAS_POR_MES as _SEMANAS_POR_MES
from concilium.domain.models.canonical import (
    CanonicalModel,
    IndirectoCategoria,
    IndirectoCostComponent,
    Indireto,
    IndiretoSemanal,
    Mobilizacao,
)
from concilium.domain.models.project.decision_variables import DecisionVariables
from concilium.domain.services.financial.rh_custo_catalogo import (
    beneficios_ativos as _beneficios_ativos,
)
from concilium.domain.services.financial.rh_custo_catalogo import (
    custo_mensal_beneficio_por_funcao as _custo_mensal_beneficio_por_funcao,
)
from concilium.domain.services.financial.rh_custo_catalogo import (
    tipo_contrato_por_funcao as _tipo_contrato_por_funcao,
)
from concilium.domain.services.financial.roster_custo_mo_substituicao import (
    cobertura_funcao_suficiente as _cobertura_funcao_suficiente,
)

from ._breakdown import _build_semanal_breakdown  # ty: ignore[unresolved-import]

logger = logging.getLogger(__name__)

# ADR-166 D3: dias/mês para converter benefício diário (café/almoço/jantar) em mensal.
_DIAS_POR_MES = _SEMANAS_POR_MES * 7


def _headcount_agregado_por_funcao(equipes_diretas: list) -> dict[str, int]:
    headcount: dict[str, int] = {}
    for eq in equipes_diretas:
        for f in getattr(eq, "funcoes", None) or []:
            funcao_id = getattr(f, "funcao_id", "")
            headcount[funcao_id] = headcount.get(funcao_id, 0) + f.num_pessoas
    return headcount


def _num_pessoas_efetivo(
    funcao_id: str,
    num_pessoas_equipe: int,
    headcount_agregado: dict[str, int],
    roster_mo: list,
) -> float:
    """ADR-173 D9/D10: quando o roster cobre integralmente o headcount agregado
    (across todas as equipes) desta função, redistribui a contagem real de
    indivíduos proporcionalmente ao `num_pessoas` de cada equipe — preserva a
    ponderação por `permanencia_efetiva_meses` própria de cada equipe (ADR-136
    F4) mesmo quando a mesma função aparece em mais de uma equipe. Se a função
    aparecer numa única equipe (caso comum), a proporção é 1:1 e o resultado é
    exatamente a contagem real. Sem cobertura suficiente, mantém `num_pessoas_equipe`
    (degradação segura)."""
    necessario = headcount_agregado.get(funcao_id, num_pessoas_equipe)
    if necessario <= 0 or not _cobertura_funcao_suficiente(roster_mo, funcao_id, necessario):
        return num_pessoas_equipe
    contagem_real = len({m.individuo_id for m in roster_mo if m.funcao_id == funcao_id})
    return num_pessoas_equipe * (contagem_real / necessario)


def _composicao_mob_beneficio_bottom_up(
    equipes_diretas: list, catalogo: dict | None, roster_mo: list | None = None
) -> float | None:
    """ADR-166 D3: bottom-up de benefício (café/almoço/jantar/vale-alimentação/
    cesta-básica/seguro-vida) por função, substituindo o termo flat
    `custo_pessoa_mes` de `_custo_alimentacao_por_equipe`. Preserva a
    granularidade de `permanencia_efetiva_meses` própria de cada equipe (ADR-136
    F4). Retorna `None` se o catálogo não tiver nenhum BENEFICIO ativo — o
    chamador cai então para o termo legado (degradação segura).

    `roster_mo` (ADR-173, opcional): quando cobre integralmente uma função
    (agregada across todas as equipes), a contagem real de indivíduos substitui
    o `num_pessoas` cadastrado — ver `_num_pessoas_efetivo`."""
    beneficios = _beneficios_ativos(catalogo)
    if not beneficios:
        return None
    tipo_contrato_map = _tipo_contrato_por_funcao(catalogo)
    headcount_agregado = _headcount_agregado_por_funcao(equipes_diretas) if roster_mo else {}
    total = 0.0
    for eq in equipes_diretas:
        permanencia = float(getattr(eq, "permanencia_efetiva_meses", 0.0) or 0.0)
        for f in getattr(eq, "funcoes", None) or []:
            funcao_id = getattr(f, "funcao_id", "")
            custo_unitario = _custo_mensal_beneficio_por_funcao(funcao_id, beneficios, tipo_contrato_map.get(funcao_id))
            num_pessoas = f.num_pessoas
            if roster_mo:
                num_pessoas = _num_pessoas_efetivo(funcao_id, f.num_pessoas, headcount_agregado, roster_mo)
            total += num_pessoas * custo_unitario * permanencia
    return round(total, 2)


def _custo_alimentacao_por_equipe(equipes_diretas: list, custo_pessoa_mes: float) -> float:
    """ADR-136 F4: custo de alimentação/seguro de vida/cesta básica por equipe.

    Cada `EquipeDireta` carrega sua própria `permanencia_efetiva_meses` (calculada
    pela skill-05 a partir do cronograma real — ver `_dimensionamento_orquestracao.py`),
    refletindo o fato de que equipes diferentes entram/saem da obra em momentos
    diferentes. Somar por equipe, em vez de usar um headcount e um prazo agregados
    para o projeto inteiro, é o que a planilha de referência do AGIS modela (7
    equipes com permanências de 1,3 a 12,0 meses) e que a fórmula legada abaixo
    (``num_pessoas_direta * custo_pessoa_mes * prazo_meses``) não reproduz.
    """
    total = 0.0
    for eq in equipes_diretas:
        num_pessoas = sum(f.num_pessoas for f in getattr(eq, "funcoes", None) or [])
        permanencia = float(getattr(eq, "permanencia_efetiva_meses", 0.0) or 0.0)
        total += num_pessoas * custo_pessoa_mes * permanencia
    return total


def _custo_mob_composicional(
    dados_mob: dict,
    num_pessoas_direta: int,
    prazo_meses: int,
    equipes_diretas: list | None = None,
    catalogo: dict | None = None,
    roster_mo: list | None = None,
) -> tuple[float, list[Mobilizacao]]:
    """Calcula custo MOB a partir da composição item a item (não de um total pré-agregado).

    Soma três componentes de negócio, cada um com sua própria regra:
    mobilizações (``num_unidades × distancia_km × custo_km`` por item),
    alimentação/seguro de vida/cesta básica (por pessoa × mês, ver
    ``_custo_alimentacao_por_equipe``) e baixadas recorrentes (por
    ``meses_ocorrencia``). É o caminho usado quando a categoria MOB não vem
    com ``custo_fixo_total`` já pré-agregado via ``categorias_config``
    (ver ``_process_mob_categoria``) — não é código morto nem um modelo
    substituído: é o único dos dois caminhos que deriva o custo de dados
    granulares em vez de aceitar um número já fechado.

    Aceita o formato de entrada anterior ao ADR-009 (dict cru
    ``dados_mobilizacao``, sem o schema ``IndirectoCategoria``) — é isso que é
    retrocompatível aqui, não a lógica de negócio em si.

    ``equipes_diretas`` (ADR-136 F4, opcional): quando fornecida e não-vazia, o
    termo de alimentação/seguro/cesta básica é calculado por equipe (headcount ×
    permanência própria de cada uma), em vez do agregado
    ``num_pessoas_direta * prazo_meses``. Retrocompatível — sem ela (ou vazia),
    o comportamento é idêntico ao anterior.

    ``catalogo`` (ADR-166 D3, opcional): quando fornecido e com BENEFICIO ativo
    (ADR-165), o termo de alimentação/seguro/cesta básica é o bottom-up por
    função (`_composicao_mob_beneficio_bottom_up`) em vez do `custo_pessoa_mes`
    flat — mesma granularidade de `permanencia_efetiva_meses` por equipe.
    """
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

    custo_beneficio_bottom_up = (
        _composicao_mob_beneficio_bottom_up(equipes_diretas, catalogo, roster_mo) if equipes_diretas else None
    )
    if custo_beneficio_bottom_up is not None:
        custo_total += custo_beneficio_bottom_up
    else:
        custo_pessoa_mes = dados_mob.get(
            "custo_pessoa_mes", 1850
        )  # B3-known: R$1.850 legado; idealmente derivar do catálogo
        if equipes_diretas:
            custo_total += _custo_alimentacao_por_equipe(equipes_diretas, custo_pessoa_mes)
        else:
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
    equipes_diretas: list | None = None,
    catalogo: dict | None = None,
    roster_mo: list | None = None,
) -> tuple[Indireto, list[IndiretoSemanal]]:
    descricao: str = cat["descricao"]
    cat_cfg_raw = next((c for c in categorias_config_raw if c.get("categoria") == "MOB"), None)
    if cat_cfg_raw:
        cat_obj = IndirectoCategoria(**cat_cfg_raw)
        custo = cat_obj.custo_fixo_total
        mobs: list[Mobilizacao] = []
    else:
        custo, mobs = _custo_mob_composicional(
            dados_mob, num_pessoas_direta, prazo_meses, equipes_diretas, catalogo=catalogo, roster_mo=roster_mo
        )
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
                "Falha ao calcular custo MOB com mob_schedule — usando custo já calculado R$%.2f: %s",
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
    return indir, _build_semanal_breakdown(cat_obj, n_semanas, mobs=mobs)


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
